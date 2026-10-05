//! trace-reader interpret --input <records.otlp.json> [--method-default R6=external-correlation-key ...]
//! trace-reader verify-receipts --input <records.otlp.json> --key <pub.pem>
//!
//! There is deliberately no flag for expected answers.

use aaif_trace_reader::*;
use serde_json::json;
use std::collections::BTreeMap;

fn main() {
    let args: Vec<String> = std::env::args().collect();
    let cmd = args.get(1).map(String::as_str).unwrap_or("");
    let mut input = None;
    let mut key = None;
    let mut defaults = BTreeMap::new();
    let mut declared_by = None;
    let mut query_action = None;
    let mut query_service = None;
    let mut query_tenant = None;
    let mut i = 2;
    while i < args.len() {
        let v = args.get(i + 1).cloned().unwrap_or_default();
        if v.is_empty() || v.starts_with("--") {
            eprintln!("{} needs a nonempty value", args[i]);
            std::process::exit(2);
        }
        match args[i].as_str() {
            "--input" => input = Some(v),
            "--key" => key = Some(v),
            "--method-default" => {
                let (rel, m) = v.split_once('=').expect("--method-default takes REL=METHOD");
                defaults.insert(rel.to_owned(), m.to_owned());
            }
            "--defaults-declared-by" => declared_by = Some(v),
            "--query-action" => query_action = Some(v),
            "--query-service" => query_service = Some(v),
            "--query-tenant" => query_tenant = Some(v),
            other => { eprintln!("unknown argument {other}"); std::process::exit(2) }
        }
        i += 2;
    }
    let query = match (query_action, query_service, query_tenant) {
        (None, None, None) => None,
        (Some(action), Some(service), tenant) if cmd == "interpret" =>
            Some(EffectQuery { action, service, tenant }),
        _ => { eprintln!("interpret query requires --query-action and --query-service; --query-tenant is optional"); std::process::exit(2) }
    };
    let path = input.expect("--input is required");
    let bytes = std::fs::read(&path).expect("read input");
    let digest = sha256_hex(&bytes);

    let doc = match parse_otlp(&bytes) {
        Ok(d) => d,
        Err(e) => {
            let r = json!({"processing": "input_error", "input": {"path": path, "sha256": digest}, "error": e});
            println!("{}", serde_json::to_string_pretty(&r).unwrap());
            std::process::exit(1);
        }
    };
    let mut diags = Vec::new();
    let spans = flatten(&doc, &mut diags);

    let mut out = match cmd {
        "interpret" => {
            if !defaults.is_empty() && declared_by.is_none() {
                eprintln!("--method-default needs --defaults-declared-by, so the report says who declared it");
                std::process::exit(2);
            }
            interpret(&spans, &Options { method_defaults: defaults, defaults_declared_by: declared_by, query })
        }
        "verify-receipts" => {
            let pem = std::fs::read_to_string(key.expect("--key is required")).expect("read key");
            verify_receipts(&spans, &pem)
        }
        _ => { eprintln!("usage: trace-reader interpret|verify-receipts --input FILE"); std::process::exit(2) }
    };
    let processing = if diags.is_empty() { "complete" } else { "partial" };
    let o = out.as_object_mut().unwrap();
    o.insert("reader".into(), json!({"name": "aaif-trace-reader-rs", "version": env!("CARGO_PKG_VERSION")}));
    o.insert("input".into(), json!({"path": path.replace('\\', "/"), "sha256": digest, "spans": spans.len()}));
    o.insert("processing".into(), json!(processing));
    o.insert("diagnostics".into(), json!(diags));
    println!("{}", serde_json::to_string_pretty(&out).unwrap());
}
