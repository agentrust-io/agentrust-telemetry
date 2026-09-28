//! Arrival order must not change any answer, and the degraded cases must stay degraded.

use aaif_trace_reader::*;
use serde_json::{json, Value};
use std::collections::BTreeMap;

const CASES: [&str; 4] = ["effects-receipt-delivered-twice", "effects-receipt-missing",
    "evidence-grade-pair-fails", "evidence-grade-pair-verifies"];

fn load(case: &str) -> Vec<Span> {
    let p = format!("{}/inputs/kit/cases/{case}/records.otlp.json", env!("CARGO_MANIFEST_DIR"));
    let doc = parse_strict(&std::fs::read(p).unwrap()).unwrap();
    let mut d = vec![];
    flatten(&doc, &mut d)
}

fn assumed() -> Options {
    let mut m = BTreeMap::new();
    for (r, v) in [("R1", "attribute-reference"), ("R5", "attribute-reference"), ("R6", "external-correlation-key")] {
        m.insert(r.to_owned(), v.to_owned());
    }
    Options { method_defaults: m, defaults_declared_by: Some("test".into()) }
}

fn permutations(n: usize) -> Vec<Vec<usize>> {
    if n == 0 { return vec![vec![]]; }
    let mut out = vec![];
    for p in permutations(n - 1) {
        for i in 0..=p.len() {
            let mut q = p.clone();
            q.insert(i, n - 1);
            out.push(q);
        }
    }
    out
}

#[test]
fn every_permutation_gives_the_same_answers() {
    for opts in [Options::default(), assumed()] {
        for case in CASES {
            let spans = load(case);
            let base = semantic(&interpret(&spans, &opts));
            let perms = permutations(spans.len());
            for p in &perms {
                let shuffled: Vec<Span> = p.iter().map(|&i| spans[i].clone()).collect();
                assert_eq!(semantic(&interpret(&shuffled, &opts)), base, "{case} under {p:?}");
            }
            assert!(perms.len() >= 6, "{case}: {} permutations", perms.len());
        }
    }
}

fn effect(report: &Value) -> Value {
    report["answers"].as_array().unwrap().iter()
        .find(|a| a["query"] == "effects-for-execution").unwrap().clone()
}

fn receipt(id: &str, service: &str, ticket: &str, created: &str) -> Span {
    let mut attrs = std::collections::BTreeMap::new();
    for (k, v) in [("receipt.id", id), ("receipt.action_id", "P1"), ("receipt.ticket_id", ticket),
        ("receipt.created_at", created), ("receipt.service", service)] {
        attrs.insert(k.to_owned(), json!({"stringValue": v}));
    }
    Span { locator: format!("{service}/{id}/{created}"), resource_service: Some(service.into()),
        name: "ticket.create.receipt".into(), attrs }
}

fn execution() -> Span {
    let mut attrs = std::collections::BTreeMap::new();
    attrs.insert("action.id".into(), json!({"stringValue": "P1"}));
    Span { locator: "exec".into(), resource_service: Some("support-agent".into()), name: "execute_tool t".into(), attrs }
}

#[test]
fn conflicting_deliveries_survive_deduplication() {
    let spans = vec![execution(), receipt("R-1", "svc", "T-1", "a"), receipt("R-1", "svc", "T-1", "b")];
    assert_eq!(effect(&interpret(&spans, &assumed()))["state"], "conflict");
}

#[test]
fn same_ticket_in_two_services_is_two_effects() {
    let spans = vec![execution(), receipt("R-1", "svc-a", "42", "a"), receipt("R-1", "svc-b", "42", "a")];
    let e = effect(&interpret(&spans, &assumed()));
    assert_eq!(e["state"], "established");
    assert_eq!(e["observed"]["correlated_effects"].as_array().unwrap().len(), 2);
}

#[test]
fn missing_receipt_is_unknown_not_zero() {
    let e = effect(&interpret(&[execution()], &assumed()));
    assert_eq!(e["state"], "unknown");
    assert!(e["gaps"].as_array().unwrap().contains(&json!("external_effect_observation_missing")));
}

#[test]
fn no_method_means_not_established() {
    let spans = vec![execution(), receipt("R-1", "svc", "T-1", "a")];
    let e = effect(&interpret(&spans, &Options::default()));
    assert_eq!(e["state"], "unknown");
    assert!(e["gaps"].as_array().unwrap().contains(&json!("r6_not_established")));
}

#[test]
fn unrecognized_default_is_a_loss_not_a_fallback() {
    let mut o = assumed();
    o.method_defaults.insert("R6".into(), "shared-attribute".into());
    let r = interpret(&[execution(), receipt("R-1", "svc", "T-1", "a")], &o);
    assert_eq!(effect(&r)["state"], "unknown");
    assert!(r["mapping_losses"].to_string().contains("shared-attribute"));
}

#[test]
fn duplicate_json_member_is_an_input_error() {
    assert!(parse_strict(br#"{"a":1,"a":2}"#).is_err());
}

#[test]
fn readme_signing_input_is_126_bytes() {
    let r = receipt("R-7", "test-ticket-service", "T-1042", "2026-09-21T15:00:00Z");
    let s = signing_input(&r).unwrap();
    assert_eq!(String::from_utf8(s.clone()).unwrap(),
        r#"{"action_id":"P1","created_at":"2026-09-21T15:00:00Z","receipt_id":"R-7","service":"test-ticket-service","ticket_id":"T-1042"}"#);
    assert_eq!(s.len(), 126);
}
