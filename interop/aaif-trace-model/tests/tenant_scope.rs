use aaif_trace_reader::*;
use serde_json::{json, Value};

fn fixture() -> Value {
    parse_strict(include_bytes!("../results/2026-10-04/b658795/inputs/test-kit/cases/effects-action-id-reused-in-another-scope/records.otlp.json")).unwrap()
}

fn options(tenant: Option<&str>) -> Options {
    Options {
        method_defaults: [("R5".into(), "attribute-reference".into()),
            ("R6".into(), "external-correlation-key".into())].into(),
        defaults_declared_by: Some("kit mapping.md @ b658795".into()),
        query: Some(EffectQuery { action: "P1".into(), service: "test-ticket-service".into(),
            tenant: tenant.map(str::to_owned) }),
    }
}

fn read(doc: &Value, opts: &Options) -> Value {
    interpret(&flatten(doc, &mut vec![]), opts)
}

fn effects(report: &Value) -> Vec<&Value> {
    report["answers"].as_array().unwrap().iter()
        .filter(|a| a["query"] == "effects-for-execution").collect()
}

fn assert_ticket(doc: &Value, tenant: &str, ticket: &str) {
    let report = read(doc, &options(Some(tenant)));
    let answers = effects(&report);
    assert_eq!(answers.len(), 1);
    assert_eq!(answers[0]["state"], "established");
    assert_eq!(answers[0]["subject"]["tenant"], tenant);
    let found = answers[0]["observed"]["correlated_effects"].as_array().unwrap();
    assert_eq!(found.len(), 1);
    assert_eq!(found[0]["ticket_id"], ticket);
    assert_eq!(found[0]["tenant"], tenant);
}

#[test]
fn reused_action_and_receipt_ids_stay_in_their_tenant() {
    assert_ticket(&fixture(), "tenant-a", "T-1042");
    assert_ticket(&fixture(), "tenant-b", "T-2088");
    let mut opts = options(None);
    opts.query = None;
    let report = read(&fixture(), &opts);
    let answers = effects(&report);
    assert_eq!(answers.len(), 2);
    assert_ne!(answers[0]["subject"], answers[1]["subject"]);
    assert!(answers.iter().all(|a| a["state"] == "established"));
}

#[test]
fn resource_order_and_span_order_do_not_change_scoped_results() {
    fn permute(values: &mut [Value], i: usize, f: &mut impl FnMut(&[Value])) {
        if i == values.len() { f(values); return; }
        for j in i..values.len() {
            values.swap(i, j);
            permute(values, i + 1, f);
            values.swap(i, j);
        }
    }
    let original = fixture();
    let mut opts = options(None); opts.query = None;
    let expected = semantic(&read(&original, &opts));
    let mut resources = original["resourceSpans"].as_array().unwrap().clone();
    let mut count = 0;
    permute(&mut resources, 0, &mut |rs| {
        // Both three-span agent resources: all 6 x 6 orders for every resource order.
        let mut doc = json!({"resourceSpans": rs});
        let agents: Vec<usize> = rs.iter().enumerate().filter(|(_, r)|
            r["scopeSpans"][0]["spans"].as_array().unwrap().len() == 3).map(|(i, _)| i).collect();
        let mut first = rs[agents[0]]["scopeSpans"][0]["spans"].as_array().unwrap().clone();
        let mut second = rs[agents[1]]["scopeSpans"][0]["spans"].as_array().unwrap().clone();
        permute(&mut first, 0, &mut |a| {
            permute(&mut second, 0, &mut |b| {
                doc["resourceSpans"][agents[0]]["scopeSpans"][0]["spans"] = json!(a);
                doc["resourceSpans"][agents[1]]["scopeSpans"][0]["spans"] = json!(b);
                assert_eq!(semantic(&read(&doc, &opts)), expected);
                count += 1;
            });
        });
    });
    assert_eq!(count, 864);
}

#[test]
fn missing_or_other_tenant_receipt_cannot_confirm_selected_tenant() {
    for replacement in [None, Some("tenant-b")] {
        let mut doc = fixture();
        let attrs = doc["resourceSpans"][1]["resource"]["attributes"].as_array_mut().unwrap();
        attrs.retain(|a| a["key"] != "tenant.id");
        if let Some(t) = replacement { attrs.push(json!({"key":"tenant.id","value":{"stringValue":t}})); }
        let report = read(&doc, &options(Some("tenant-a")));
        assert_eq!(effects(&report)[0]["state"], "unknown");
        assert_eq!(effects(&report)[0]["observed"]["correlated_effects"], json!([]));
    }
}

#[test]
fn absent_tenant_query_is_not_a_wildcard() {
    assert!(effects(&read(&fixture(), &options(None))).is_empty());
    let mut doc = fixture();
    for index in [0, 1] {
        doc["resourceSpans"][index]["resource"]["attributes"].as_array_mut().unwrap()
            .retain(|a| a["key"] != "tenant.id");
    }
    let report = read(&doc, &options(None));
    assert_eq!(effects(&report).len(), 1);
    assert_eq!(effects(&report)[0]["observed"]["correlated_effects"][0]["ticket_id"], "T-1042");
}

#[test]
fn same_ticket_id_in_two_tenants_remains_two_scoped_effects() {
    let mut doc = fixture();
    doc["resourceSpans"][3]["scopeSpans"][0]["spans"][0]["attributes"].as_array_mut().unwrap()
        .iter_mut().find(|a| a["key"] == "receipt.ticket_id").unwrap()["value"]["stringValue"] = json!("T-1042");
    let mut opts = options(None); opts.query = None;
    let report = read(&doc, &opts);
    let answers = effects(&report);
    assert_eq!(answers.len(), 2);
    assert!(answers.iter().all(|a| a["state"] == "established"));
    assert_ne!(answers[0]["observed"]["correlated_effects"][0], answers[1]["observed"]["correlated_effects"][0]);
}

#[test]
fn tenant_query_does_not_supply_a_missing_relationship_method() {
    let mut opts = options(Some("tenant-a"));
    opts.method_defaults.remove("R6");
    let report = read(&fixture(), &opts);
    assert_eq!(effects(&report)[0]["state"], "unknown");
    assert!(effects(&report)[0]["gaps"].as_array().unwrap().contains(&json!("r6_not_established")));
    opts.query.as_mut().unwrap().action = "missing-action".into();
    assert!(effects(&read(&fixture(), &opts)).is_empty());
}

#[test]
fn malformed_or_duplicate_resource_scope_never_falls_back_to_absent() {
    for index in [0, 1] {
        for key in ["tenant.id", "service.name"] {
            for invalid in [json!({"intValue":"1"}), json!({"stringValue":""}),
                json!({"stringValue":"tenant-a","intValue":"1"}), Value::Null] {
                let mut doc = fixture();
                let attrs = doc["resourceSpans"][index]["resource"]["attributes"].as_array_mut().unwrap();
                let entry = attrs.iter_mut().find(|a| a["key"] == key).unwrap();
                if invalid.is_null() { let duplicate = entry.clone(); attrs.push(duplicate); }
                else { entry["value"] = invalid; }
                let mut diags = vec![];
                let spans = flatten(&doc, &mut diags);
                assert_eq!(diags.len(), 1);
                // Query-free interpretation must not allow malformed tenant to become a legacy join.
                let mut opts = options(None); opts.query = None;
                let report = interpret(&spans, &opts);
                let first = effects(&report).into_iter().find(|a|
                    a["evidence"].as_array().unwrap().contains(&json!("resourceSpans[0].scopeSpans[0].spans[2]"))).unwrap();
                assert_ne!(first["state"], "established");
            }
        }
    }
}

#[test]
fn query_service_must_match_both_receipt_service_fields() {
    for resource in [true, false] {
        let mut doc = fixture();
        let attrs = if resource { &mut doc["resourceSpans"][1]["resource"]["attributes"] }
            else { &mut doc["resourceSpans"][1]["scopeSpans"][0]["spans"][0]["attributes"] };
        let key = if resource { "service.name" } else { "receipt.service" };
        attrs.as_array_mut().unwrap().iter_mut().find(|a| a["key"] == key).unwrap()["value"]["stringValue"] = json!("other-service");
        let report = read(&doc, &options(Some("tenant-a")));
        assert_eq!(effects(&report)[0]["state"], "unknown");
    }
    let mut opts = options(Some("tenant-a"));
    opts.query.as_mut().unwrap().service = "missing-service".into();
    assert_eq!(effects(&read(&fixture(), &opts))[0]["state"], "unknown");
}

#[test]
fn duplicate_and_conflicting_deliveries_are_local_to_tenant() {
    let mut doc = fixture();
    let duplicate = doc["resourceSpans"][1].clone();
    doc["resourceSpans"].as_array_mut().unwrap().push(duplicate);
    assert_ticket(&doc, "tenant-a", "T-1042");
    doc["resourceSpans"][4]["scopeSpans"][0]["spans"][0]["attributes"].as_array_mut().unwrap()
        .iter_mut().find(|a| a["key"] == "receipt.ticket_id").unwrap()["value"]["stringValue"] = json!("conflicting-ticket");
    assert_eq!(effects(&read(&doc, &options(Some("tenant-a"))))[0]["state"], "conflict");
    assert_ticket(&doc, "tenant-b", "T-2088");
}

#[test]
fn query_cannot_hide_ambiguous_agent_scope() {
    let mut doc = fixture();
    let mut other_agent = doc["resourceSpans"][0].clone();
    other_agent["resource"]["attributes"][0]["value"]["stringValue"] = json!("another-agent");
    doc["resourceSpans"].as_array_mut().unwrap().push(other_agent);
    let report = read(&doc, &options(Some("tenant-a")));
    assert_eq!(effects(&report).len(), 2);
    assert!(effects(&report).iter().all(|a| a["state"] == "unknown"));
}

#[test]
fn proposal_and_orphan_receipt_do_not_join_across_tenants() {
    let mut doc = fixture();
    doc["resourceSpans"][0]["scopeSpans"][0]["spans"].as_array_mut().unwrap()
        .retain(|s| s["name"] != "propose_action");
    doc["resourceSpans"][2]["scopeSpans"][0]["spans"].as_array_mut().unwrap()
        .retain(|s| !s["name"].as_str().unwrap().starts_with("execute_tool"));
    let report = read(&doc, &options(Some("tenant-a")));
    assert!(report["answers"].as_array().unwrap().iter().any(|a|
        a["query"] == "approval-for-execution" && a["gaps"].as_array().unwrap().contains(&json!("r5_target_unresolved"))));
    assert!(report["answers"].as_array().unwrap().iter().any(|a|
        a["query"] == "uncorrelated-external-report" && a["subject"]["tenant"] == "tenant-b"));
}

#[test]
fn cli_uses_query_context_without_expected_answers() {
    let file = format!("{}/results/2026-10-04/b658795/inputs/test-kit/cases/effects-action-id-reused-in-another-scope/records.otlp.json", env!("CARGO_MANIFEST_DIR"));
    let mut cmd = std::process::Command::new(env!("CARGO_BIN_EXE_trace-reader"));
    #[cfg(windows)] {
        use std::os::windows::process::CommandExt;
        cmd.creation_flags(0x08000000);
    }
    let result = cmd.args(["interpret", "--input", &file, "--method-default", "R6=external-correlation-key",
        "--defaults-declared-by", "test", "--query-action", "P1", "--query-service", "test-ticket-service",
        "--query-tenant", "tenant-a"]).output().unwrap();
    assert!(result.status.success());
    let report: Value = serde_json::from_slice(&result.stdout).unwrap();
    assert_eq!(effects(&report).len(), 1);
    assert_eq!(effects(&report)[0]["observed"]["correlated_effects"][0]["ticket_id"], "T-1042");
    assert_eq!(report["evaluation_context"]["tenant"], "tenant-a");
}
