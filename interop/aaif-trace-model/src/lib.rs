//! Second independent reader for AAIF Observability & Traceability Task 7 (issue #45).
//!
//! Written from the shared contract text (#51, v0.7-draft at e82abf1) and the #57 test-kit
//! inputs only. It shares no code or mapping with the Python reader, and it has no interface
//! for receiving expected answers: `trace-compare` is a separate program.
//!
//! Records are read as a set. Every answer is computed after the whole input is indexed, and
//! nothing depends on arrival order.

use serde::de::{self, Deserializer, MapAccess, SeqAccess, Visitor};
use serde::Deserialize;
use serde_json::{json, Map, Value};
use std::collections::{BTreeMap, BTreeSet};
use std::fmt;

pub const CONTRACT: &str = "AGENT-BEHAVIOR-TRACE-MODEL-CONTRACT.md v0.7-draft @ e82abf1e58b066c586c25767edfba862c4ebd027";
pub const METHODS: [&str; 4] = ["span-link", "attribute-reference", "causal-flag", "external-correlation-key"];

// ---------------------------------------------------------------------------------------------
// Strict JSON: duplicate object members are rejected at the byte-parsing boundary.

struct Strict(Value);

impl<'de> Deserialize<'de> for Strict {
    fn deserialize<D: Deserializer<'de>>(d: D) -> Result<Self, D::Error> {
        d.deserialize_any(StrictVisitor)
    }
}

struct StrictVisitor;

impl<'de> Visitor<'de> for StrictVisitor {
    type Value = Strict;
    fn expecting(&self, f: &mut fmt::Formatter) -> fmt::Result {
        f.write_str("any JSON value")
    }
    fn visit_bool<E>(self, v: bool) -> Result<Strict, E> { Ok(Strict(Value::Bool(v))) }
    fn visit_i64<E>(self, v: i64) -> Result<Strict, E> { Ok(Strict(Value::from(v))) }
    fn visit_u64<E>(self, v: u64) -> Result<Strict, E> { Ok(Strict(Value::from(v))) }
    fn visit_f64<E>(self, v: f64) -> Result<Strict, E> { Ok(Strict(Value::from(v))) }
    fn visit_str<E>(self, v: &str) -> Result<Strict, E> { Ok(Strict(Value::String(v.to_owned()))) }
    fn visit_string<E>(self, v: String) -> Result<Strict, E> { Ok(Strict(Value::String(v))) }
    fn visit_unit<E>(self) -> Result<Strict, E> { Ok(Strict(Value::Null)) }
    fn visit_seq<A: SeqAccess<'de>>(self, mut s: A) -> Result<Strict, A::Error> {
        let mut out = Vec::new();
        while let Some(Strict(v)) = s.next_element()? {
            out.push(v);
        }
        Ok(Strict(Value::Array(out)))
    }
    fn visit_map<A: MapAccess<'de>>(self, mut m: A) -> Result<Strict, A::Error> {
        let mut out = Map::new();
        while let Some(k) = m.next_key::<String>()? {
            if out.contains_key(&k) {
                return Err(de::Error::custom(format!("duplicate object member {k:?}")));
            }
            let Strict(v) = m.next_value()?;
            out.insert(k, v);
        }
        Ok(Strict(Value::Object(out)))
    }
}

pub fn parse_strict(bytes: &[u8]) -> Result<Value, String> {
    let mut d = serde_json::Deserializer::from_slice(bytes);
    let Strict(v) = Strict::deserialize(&mut d).map_err(|e| e.to_string())?;
    d.end().map_err(|e| e.to_string())?;
    Ok(v)
}

// ---------------------------------------------------------------------------------------------
// OTLP/JSON spans, flattened. The locator is diagnostic only and never becomes an identity.

#[derive(Clone, Debug)]
pub struct Span {
    pub locator: String,
    pub resource_service: Option<String>,
    pub name: String,
    pub attrs: BTreeMap<String, Value>,
}

impl Span {
    pub fn s(&self, k: &str) -> Option<&str> {
        self.attrs.get(k).and_then(|v| v.get("stringValue")).and_then(Value::as_str)
    }
}

pub fn flatten(doc: &Value, diags: &mut Vec<Value>) -> Vec<Span> {
    let mut out = Vec::new();
    let empty = vec![];
    for (i, rs) in doc["resourceSpans"].as_array().unwrap_or(&empty).iter().enumerate() {
        let svc = rs["resource"]["attributes"].as_array().and_then(|a| {
            a.iter().find(|kv| kv["key"] == "service.name").and_then(|kv| kv["value"]["stringValue"].as_str())
        });
        for (j, ss) in rs["scopeSpans"].as_array().unwrap_or(&empty).iter().enumerate() {
            for (k, sp) in ss["spans"].as_array().unwrap_or(&empty).iter().enumerate() {
                let locator = format!("resourceSpans[{i}].scopeSpans[{j}].spans[{k}]");
                let mut attrs = BTreeMap::new();
                for kv in sp["attributes"].as_array().unwrap_or(&empty) {
                    let Some(key) = kv["key"].as_str() else { continue };
                    if attrs.insert(key.to_owned(), kv["value"].clone()).is_some() {
                        diags.push(json!({"code": "duplicate_attribute_key", "key": key, "at": locator}));
                    }
                }
                out.push(Span {
                    locator,
                    resource_service: svc.map(str::to_owned),
                    name: sp["name"].as_str().unwrap_or("").to_owned(),
                    attrs,
                });
            }
        }
    }
    out
}

// ---------------------------------------------------------------------------------------------
// Local mapping (MAPPING.md). Fixture attribute names are illustrative identities, per the kit.

#[derive(Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Debug)]
enum Kind { Turn, Proposal, Execution, Receipt }

fn classify(s: &Span) -> Option<Kind> {
    if s.name == "ticket.create.receipt" || s.attrs.keys().any(|k| k.starts_with("receipt.")) {
        Some(Kind::Receipt)
    } else if s.name.starts_with("execute_tool") {
        Some(Kind::Execution)
    } else if s.name == "propose_action" {
        Some(Kind::Proposal)
    } else if s.attrs.contains_key("turn.id") {
        Some(Kind::Turn)
    } else {
        None
    }
}

const KNOWN_ATTRS: [&str; 5] = ["conversation.id", "turn.id", "action.id", "action.intent", "tool.name"];
const PRODUCER_CLAIMS: [&str; 1] = ["evidence.externally_verified"];
const RECEIPT_FIELDS: [&str; 6] = ["receipt.id", "receipt.action_id", "receipt.ticket_id", "receipt.created_at", "receipt.service", "receipt.signature"];

/// Method defaults are the contract's §4 step 2. The contract gives that role to the example's
/// mapping file. When the operator supplies them instead, the report says so.
#[derive(Clone, Default, Debug)]
pub struct Options {
    pub method_defaults: BTreeMap<String, String>,
    pub defaults_declared_by: Option<String>,
}

// ---------------------------------------------------------------------------------------------

pub fn interpret(spans: &[Span], opts: &Options) -> Value {
    let mut losses: Vec<Value> = Vec::new();
    let mut not_used: Vec<Value> = Vec::new();
    let mut by_kind: BTreeMap<Kind, Vec<&Span>> = BTreeMap::new();

    for s in spans {
        match classify(s) {
            Some(k) => by_kind.entry(k).or_default().push(s),
            None => losses.push(json!({"code": "unsupported_record_kind", "name": s.name, "at": s.locator})),
        }
        for k in s.attrs.keys() {
            if PRODUCER_CLAIMS.contains(&k.as_str()) {
                not_used.push(json!({"attribute": k, "at": s.locator,
                    "why": "producer claim about external verification; not re-derived by this reader"}));
            } else if !KNOWN_ATTRS.contains(&k.as_str()) && !RECEIPT_FIELDS.contains(&k.as_str()) {
                losses.push(json!({"code": "unmapped_attribute", "attribute": k, "at": s.locator}));
            }
        }
    }
    let get = |k: Kind| by_kind.get(&k).cloned().unwrap_or_default();

    // §4: a relationship is established only with a method, from the record or a declared default.
    // No attribute in this input names a method, so only step 2 can apply.
    let method_for = |rel: &str, losses: &mut Vec<Value>, at: &str| -> Option<String> {
        match opts.method_defaults.get(rel) {
            Some(m) if METHODS.contains(&m.as_str()) => Some(m.clone()),
            Some(m) => {
                losses.push(json!({"code": "unrecognized_method_default", "relationship": rel, "value": m, "at": at}));
                None
            }
            None => {
                losses.push(json!({"code": "relationship_method_absent", "relationship": rel, "at": at,
                    "why": "record carries no method and no mapping-file default is declared (contract §4 step 3)"}));
                None
            }
        }
    };

    let mut answers: Vec<Value> = Vec::new();

    // Continuity, R1.
    for t in get(Kind::Turn) {
        let turn = t.s("turn.id");
        let conv = t.s("conversation.id");
        let (state, gaps, via) = match conv {
            None => ("unknown", vec!["conversation_identity_not_exported"], None),
            Some(_) => match method_for("R1", &mut losses, &t.locator) {
                Some(m) => ("established", vec![], Some(m)),
                None => ("unknown", vec!["r1_not_established"], None),
            },
        };
        answers.push(json!({"query": "continuity", "subject": {"kind": "turn", "id": turn},
            "state": state, "observed": {"conversation": if state == "established" { json!(conv) } else { Value::Null },
            "method": via}, "gaps": gaps, "conflicts": [], "evidence": [t.locator]}));
    }

    // Calls and retries, R2. No model-call records are mapped in this input.
    for t in get(Kind::Turn) {
        answers.push(json!({"query": "calls", "subject": {"kind": "turn", "id": t.s("turn.id")},
            "state": "unknown", "observed": {"model_calls": [], "usage": Value::Null},
            "gaps": ["no_model_call_observed"], "conflicts": [], "evidence": []}));
    }

    // Proposal origin, R3: no proposal carries a turn reference; span ancestry is not used.
    for p in get(Kind::Proposal) {
        answers.push(json!({"query": "proposal-origin", "subject": {"kind": "proposed_action", "id": p.s("action.id")},
            "state": "unknown", "observed": {"turn": Value::Null},
            "gaps": ["r3_not_exported"], "conflicts": [], "evidence": [p.locator]}));
    }

    let proposals: BTreeSet<&str> = get(Kind::Proposal).iter().filter_map(|p| p.s("action.id")).collect();
    let agent_scopes: BTreeSet<&str> = get(Kind::Execution).iter().filter_map(|e| e.resource_service.as_deref()).collect();

    for e in get(Kind::Execution) {
        let action = e.s("action.id");
        let subject = json!({"kind": "tool_execution", "id": Value::Null, "scope": e.resource_service,
            "references": {"proposal": action}});

        // Approvals, R4/R5. No decision records are mapped in this input.
        let r5 = action.and_then(|_| method_for("R5", &mut losses, &e.locator));
        let proposal_resolved = action.map(|a| proposals.contains(a)).unwrap_or(false);
        let mut agaps = vec!["no_decision_recorded"];
        if r5.is_none() { agaps.push("r5_not_established"); }
        else if !proposal_resolved { agaps.push("r5_target_unresolved"); }
        answers.push(json!({"query": "approval-for-execution", "subject": subject.clone(), "state": "unknown",
            "observed": {"execution": true, "proposal": if r5.is_some() && proposal_resolved { json!(action) } else { Value::Null },
                "decisions_recorded": [], "enforcement": "unknown"},
            "gaps": agaps, "conflicts": [], "evidence": [e.locator]}));

        // Effects, R6.
        let r6 = method_for("R6", &mut losses, &e.locator);
        answers.push(effects_for(e, action, &get(Kind::Receipt), &agent_scopes, &r6));
    }

    // Receipts that no execution correlates with stay visible as external reports.
    let exec_actions: BTreeSet<&str> = get(Kind::Execution).iter().filter_map(|e| e.s("action.id")).collect();
    for r in get(Kind::Receipt) {
        if !r.s("receipt.action_id").map(|a| exec_actions.contains(a)).unwrap_or(false) {
            answers.push(json!({"query": "uncorrelated-external-report", "subject": {"kind": "receipt",
                "id": r.s("receipt.id"), "scope": r.s("receipt.service")}, "state": "unknown",
                "observed": {"execution": Value::Null}, "gaps": ["r6_execution_unresolved"], "conflicts": [],
                "evidence": [r.locator]}));
        }
    }

    answers.sort_by_key(|a| (a["query"].to_string(), a["subject"].to_string()));
    losses.sort_by_key(|v| v.to_string());
    losses.dedup();
    not_used.sort_by_key(|v| v.to_string());

    json!({
        "contract": CONTRACT,
        "method_defaults": {"values": opts.method_defaults, "declared_by": opts.defaults_declared_by},
        "answers": answers,
        "mapping_losses": losses,
        "not_used": not_used,
    })
}

fn effects_for(e: &Span, action: Option<&str>, receipts: &[&Span], agent_scopes: &BTreeSet<&str>, r6: &Option<String>) -> Value {
    let subject = json!({"kind": "tool_execution", "id": Value::Null, "scope": e.resource_service,
        "references": {"proposal": action}});
    let candidates: Vec<&&Span> = receipts.iter().filter(|r| action.is_some() && r.s("receipt.action_id") == action).collect();
    let mut gaps: Vec<String> = Vec::new();
    let mut conflicts: Vec<Value> = Vec::new();
    let mut evidence: Vec<String> = vec![e.locator.clone()];

    if r6.is_none() {
        gaps.push("r6_not_established".into());
        return json!({"query": "effects-for-execution", "subject": subject, "state": "unknown",
            "observed": {"execution": true, "correlated_effects": [], "external_reports_seen": candidates.len()},
            "gaps": gaps, "conflicts": [], "evidence": evidence});
    }
    // receipt.action_id does not state which scope issued the action id. It can be joined only
    // when the input holds one agent scope; otherwise the join is refused.
    if agent_scopes.len() != 1 {
        gaps.push("identity_scope_unresolved".into());
        return json!({"query": "effects-for-execution", "subject": subject, "state": "unknown",
            "observed": {"execution": true, "correlated_effects": []}, "gaps": gaps, "conflicts": [], "evidence": evidence});
    }

    // Group by scoped receipt identity, then by scoped effect identity (service, ticket id).
    let mut by_receipt: BTreeMap<(String, String), Vec<&Span>> = BTreeMap::new();
    for r in &candidates {
        let scope = r.s("receipt.service");
        if scope.is_none() || r.resource_service.as_deref() != scope {
            gaps.push("receipt_scope_unresolved".into());
            evidence.push(r.locator.clone());
            continue;
        }
        match r.s("receipt.id") {
            Some(id) => by_receipt.entry((scope.unwrap().to_owned(), id.to_owned())).or_default().push(r),
            None => { gaps.push("receipt_identity_missing".into()); evidence.push(r.locator.clone()); }
        }
    }
    let mut effects: BTreeMap<(String, String), Vec<Value>> = BTreeMap::new();
    for ((scope, rid), deliveries) in &by_receipt {
        let first = &deliveries[0].attrs;
        let agree = deliveries.iter().all(|d| &d.attrs == first);
        let mut locs: Vec<&str> = deliveries.iter().map(|d| d.locator.as_str()).collect();
        locs.sort();
        evidence.extend(locs.iter().map(|s| s.to_string()));
        if !agree {
            conflicts.push(json!({"code": "receipt_deliveries_disagree", "receipt": rid, "scope": scope, "at": locs}));
            continue;
        }
        match deliveries[0].s("receipt.ticket_id") {
            Some(t) => effects.entry((scope.clone(), t.to_owned())).or_default()
                .push(json!({"receipt": rid, "deliveries": deliveries.len()})),
            None => gaps.push("effect_identity_missing".into()),
        }
    }
    let correlated: Vec<Value> = effects.iter().map(|((scope, ticket), rs)| {
        json!({"scope": scope, "ticket_id": ticket, "receipts": rs})
    }).collect();

    let state = if !conflicts.is_empty() { "conflict" }
        else if correlated.is_empty() { gaps.push("external_effect_observation_missing".into()); "unknown" }
        else { "established" };
    gaps.sort(); gaps.dedup(); evidence.sort(); evidence.dedup();
    json!({"query": "effects-for-execution", "subject": subject, "state": state,
        "observed": {"execution": true, "correlated_effects": correlated, "correlation_method": r6},
        "gaps": gaps, "conflicts": conflicts, "evidence": evidence})
}

/// The report with diagnostic locators removed, for permutation comparison.
pub fn semantic(report: &Value) -> Value {
    fn strip(v: &Value) -> Value {
        match v {
            Value::Object(m) => Value::Object(m.iter().filter(|(k, _)| *k != "evidence" && *k != "at")
                .map(|(k, v)| (k.clone(), strip(v))).collect()),
            Value::Array(a) => Value::Array(a.iter().map(strip).collect()),
            _ => v.clone(),
        }
    }
    strip(report)
}

// ---------------------------------------------------------------------------------------------
// Receipt signatures, per the kit README "Signing input". Separate from the contract reader:
// v0.7-draft treats a receipt as correlation evidence, so nothing above depends on this.

pub fn ascii_json_string(s: &str) -> String {
    let mut o = String::from("\"");
    for c in s.chars() {
        match c {
            '"' => o.push_str("\\\""),
            '\\' => o.push_str("\\\\"),
            '\n' => o.push_str("\\n"),
            '\r' => o.push_str("\\r"),
            '\t' => o.push_str("\\t"),
            '\u{08}' => o.push_str("\\b"),
            '\u{0c}' => o.push_str("\\f"),
            c if (c as u32) < 0x20 || (c as u32) > 0x7f => {
                let mut buf = [0u16; 2];
                for u in c.encode_utf16(&mut buf) {
                    o.push_str(&format!("\\u{:04x}", u));
                }
            }
            c => o.push(c),
        }
    }
    o.push('"');
    o
}

pub fn signing_input(r: &Span) -> Result<Vec<u8>, String> {
    let fields = [("action_id", "receipt.action_id"), ("created_at", "receipt.created_at"),
        ("receipt_id", "receipt.id"), ("service", "receipt.service"), ("ticket_id", "receipt.ticket_id")];
    let mut parts = Vec::new();
    for (name, attr) in fields {
        let v = r.s(attr).ok_or_else(|| format!("{attr} missing or not a string"))?;
        parts.push(format!("{}:{}", ascii_json_string(name), ascii_json_string(v)));
    }
    Ok(format!("{{{}}}", parts.join(",")).into_bytes())
}

pub fn verify_receipts(spans: &[Span], pem: &str) -> Value {
    use base64::Engine;
    use ed25519_dalek::pkcs8::DecodePublicKey;
    let key = match ed25519_dalek::VerifyingKey::from_public_key_pem(pem) {
        Ok(k) => k,
        Err(e) => return json!({"error": format!("key: {e}")}),
    };
    let mut out = Vec::new();
    for r in spans.iter().filter(|s| classify(s) == Some(Kind::Receipt)) {
        let res = (|| -> Result<(usize, bool), String> {
            let msg = signing_input(r)?;
            let sig_b64 = r.s("receipt.signature").ok_or("receipt.signature missing")?;
            let raw = base64::engine::general_purpose::STANDARD.decode(sig_b64).map_err(|e| e.to_string())?;
            let sig = ed25519_dalek::Signature::from_slice(&raw).map_err(|e| e.to_string())?;
            Ok((msg.len(), key.verify_strict(&msg, &sig).is_ok()))
        })();
        out.push(match res {
            Ok((n, ok)) => json!({"receipt": r.s("receipt.id"), "at": r.locator, "signing_input_bytes": n,
                "signature": if ok { "verifies" } else { "does_not_verify" }}),
            Err(e) => json!({"receipt": r.s("receipt.id"), "at": r.locator, "signature": "unverifiable", "why": e}),
        });
    }
    json!({"receipts": out})
}

pub fn sha256_hex(b: &[u8]) -> String {
    use sha2::{Digest, Sha256};
    Sha256::digest(b).iter().map(|x| format!("{x:02x}")).collect()
}
