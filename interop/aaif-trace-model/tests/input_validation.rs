use serde_json::{json, Value};
use std::process::Command;
use std::sync::atomic::{AtomicUsize, Ordering};

fn run(doc: &str, mode: &str) -> (i32, Value) {
    static NEXT: AtomicUsize = AtomicUsize::new(0);
    let path = std::env::temp_dir().join(format!("trace-input-{}-{}.json",
        std::process::id(), NEXT.fetch_add(1, Ordering::Relaxed)));
    std::fs::write(&path, doc).unwrap();
    let mut cmd = Command::new(env!("CARGO_BIN_EXE_trace-reader"));
    #[cfg(windows)] {
        use std::os::windows::process::CommandExt;
        cmd.creation_flags(0x08000000);
    }
    cmd.args([mode, "--input"]).arg(&path);
    if mode == "verify-receipts" {
        cmd.args(["--key", concat!(env!("CARGO_MANIFEST_DIR"),
            "/inputs/kit/trust/test-ticket-service.pub.pem")]);
    }
    let result = cmd.output().unwrap();
    std::fs::remove_file(path).unwrap();
    (result.status.code().unwrap(), serde_json::from_slice(&result.stdout)
        .unwrap_or_else(|_| panic!("{}", String::from_utf8_lossy(&result.stderr))))
}

#[test]
fn unsupported_json_is_an_input_error_in_both_modes() {
    for mode in ["interpret", "verify-receipts"] {
        for doc in ["[]", "null", "true", "42", "\"text\"",
            r#"{"bundle_format":"cigar-aac-evidence-bundle/v1","capsules":[]}"#,
            r#"{"schema":"cigar-aac-native-execution/v1"}"#,
            r#"[{"kind":"stage.enter","seq":0}]"#,
            r#"{"resourceLogs":[]}"#] {
            let (code, report) = run(doc, mode);
            assert_eq!(code, 1, "{mode}: {doc}: {report}");
            assert_eq!(report["processing"], "input_error");
            assert!(report["error"].as_str().unwrap().contains("OTLP"));
            assert!(report.get("answers").is_none());
        }
    }
}

#[test]
fn malformed_collections_and_entries_are_not_silently_dropped() {
    for bad in [json!({}), json!("bad"), json!(3), json!(true)] {
        for (doc, location) in [
            (json!({"resourceSpans":bad}), "resourceSpans"),
            (json!({"resourceSpans":[{}, {"scopeSpans":bad}]}), "resourceSpans[1].scopeSpans"),
            (json!({"resourceSpans":[{"scopeSpans":[{}, {"spans":bad}]}]}), "resourceSpans[0].scopeSpans[1].spans"),
        ] {
            let (code, report) = run(&doc.to_string(), "interpret");
            assert_eq!(code, 1, "{doc}: {report}");
            assert!(report["error"].as_str().unwrap().contains(location));
        }
    }
    for bad in [Value::Null, json!([]), json!(false), json!(7), json!("bad")] {
        for doc in [json!({"resourceSpans":[{},bad]}),
            json!({"resourceSpans":[{"scopeSpans":[{},bad]}]}),
            json!({"resourceSpans":[{"scopeSpans":[{"spans":[{"name":"valid"},bad]}]}]})] {
            let (code, report) = run(&doc.to_string(), "interpret");
            assert_eq!(code, 1, "{doc}: {report}");
            assert_eq!(report["processing"], "input_error");
        }
    }
}

#[test]
fn empty_exports_and_unset_repeated_fields_remain_valid() {
    for doc in [json!({}), json!({"resourceSpans":[]}), json!({"resourceSpans":null}),
        json!({"resourceSpans":[{}]}), json!({"resourceSpans":[{"scopeSpans":null}]}),
        json!({"resourceSpans":[{"scopeSpans":[{}, {"spans":[]}, {"spans":null}]}]}),
        json!({"resourceSpans":[],"futureField":true})] {
        for mode in ["interpret", "verify-receipts"] {
            let (code, report) = run(&doc.to_string(), mode);
            assert_eq!(code, 0, "{doc}: {report}");
            assert_eq!(report["processing"], "complete");
            assert_eq!(report["input"]["spans"], 0);
        }
    }
}

#[test]
fn duplicate_keys_and_trailing_json_still_fail() {
    for doc in [r#"{"resourceSpans":[],"resourceSpans":[]}"#, r#"{"resourceSpans":[]} {}"#] {
        let (code, report) = run(doc, "interpret");
        assert_eq!(code, 1);
        assert_eq!(report["processing"], "input_error");
    }
}
