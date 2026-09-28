//! trace-compare --report R --signatures S --expected E --basis B
//!
//! Separate from the reader. Maps the reader's report onto the kit's answer fields, field by
//! field, and says which program each compared value came from. A field the contract reader has
//! no rule for is reported as not answered, never as a pass.

use aaif_trace_reader::parse_strict;
use serde_json::{json, Value};

fn load(p: &str) -> Value {
    parse_strict(&std::fs::read(p).unwrap_or_else(|e| panic!("{p}: {e}"))).unwrap_or_else(|e| panic!("{p}: {e}"))
}

fn main() {
    let a: Vec<String> = std::env::args().collect();
    let arg = |f: &str| a.iter().position(|x| x == f).and_then(|i| a.get(i + 1)).cloned().unwrap_or_else(|| panic!("{f} required"));
    let (report, sigs, expected, basis) = (load(&arg("--report")), load(&arg("--signatures")), load(&arg("--expected")), load(&arg("--basis")));

    let effects: Vec<&Value> = report["answers"].as_array().unwrap().iter()
        .filter(|x| x["query"] == "effects-for-execution").collect();
    let ans = effects.iter().find(|x| x["subject"]["references"]["proposal"] == expected["action"]).copied();

    let (effect, tickets) = match ans {
        None => (json!("no answer for this action"), Value::Null),
        Some(x) => {
            let t: Vec<Value> = x["observed"]["correlated_effects"].as_array().unwrap().iter()
                .map(|e| e["ticket_id"].clone()).collect();
            match x["state"].as_str().unwrap() {
                "established" => (json!("confirmed"), json!(t)),
                "unknown" => (json!("unconfirmed"), Value::Null),
                s => (json!(s), Value::Null),
            }
        }
    };
    // externally_verified comes from verify-receipts, not from the contract reader.
    let correlated: Vec<&str> = ans.map(|x| x["observed"]["correlated_effects"].as_array().unwrap().iter()
        .flat_map(|e| e["receipts"].as_array().unwrap().iter().filter_map(|r| r["receipt"].as_str())).collect()).unwrap_or_default();
    let sig_rows: Vec<&Value> = sigs["receipts"].as_array().unwrap().iter()
        .filter(|r| r["receipt"].as_str().map(|id| correlated.contains(&id)).unwrap_or(false)).collect();
    let ext = !sig_rows.is_empty() && sig_rows.iter().all(|r| r["signature"] == "verifies");

    let field = |name: &str, got: Value, from: &str| {
        let want = expected[name].clone();
        json!({"field": name, "expected": want, "actual": got, "match": got == want, "from": from})
    };
    let v07_scope = basis["answer_follows"]["outside"].is_null();
    let mut ext_field = field("externally_verified", json!(ext), "trace-reader verify-receipts (no v0.7-draft rule)");
    ext_field["contract_reader_answer"] = json!("not answered: v0.7-draft section 6 treats a receipt as correlation evidence");
    let out = json!({
        "case_basis": basis["answer_follows"]["document"],
        "in_scope_for_v0_7_reader": v07_scope,
        "method_defaults": report["method_defaults"],
        "fields": [
            field("action", ans.map(|x| x["subject"]["references"]["proposal"].clone()).unwrap_or(Value::Null), "trace-reader interpret"),
            field("effect", effect, "trace-reader interpret"),
            field("confirmed_tickets", tickets, "trace-reader interpret"),
            ext_field,
        ],
    });
    println!("{}", serde_json::to_string_pretty(&out).unwrap());
}
