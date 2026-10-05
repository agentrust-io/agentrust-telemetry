"""Offline comparison against both pinned kit revisions. Build trace-reader first.

No kit generator or other reader is imported. Query context comes from basis.json,
never expected.json. The older kit's single-action/service mapping is explicit below.
Run: python check_pinned_kit.py [--reader PATH] [--output DIR]
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parent
REVISIONS = ["4a028675ef9b5727e614762df305f5f037b04b98",
             "b6587950986eb4ec501e080cc9730fd21dcb69fa"]


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reader", type=Path, default=ROOT / "target/debug" /
                        ("trace-reader.exe" if os.name == "nt" else "trace-reader"))
    parser.add_argument("--output", type=Path, default=ROOT / "results/2026-10-05")
    args = parser.parse_args()
    evidence = []
    hashes = {}

    def digest(path):
        hashes[path.relative_to(ROOT).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()

    def run(arguments, destination):
        result = subprocess.run([str(args.reader.resolve()), *arguments], cwd=ROOT,
                                capture_output=True, text=True,
                                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        if result.returncode:
            raise RuntimeError(f"reader exit {result.returncode}: {result.stderr}")
        value = json.loads(result.stdout)
        save(destination, value)
        return value

    for revision in REVISIONS:
        short = revision[:7]
        inputs = ROOT / "results/2026-10-04" / short / "inputs/test-kit"
        for case in sorted((inputs / "cases").iterdir()):
            basis = load(case / "basis.json")
            context = basis.get("evaluation_context", {
                "action": "P1", "service": "test-ticket-service", "tenant": None})
            output = args.output / short / case.name
            command = ["interpret", "--input", str((case / "records.otlp.json").relative_to(ROOT)),
                       "--query-action", context["action"], "--query-service", context["service"],
                       "--defaults-declared-by", f"kit mapping.md @ {revision}"]
            for relationship, method in [("R1", "attribute-reference"), ("R5", "attribute-reference"),
                                         ("R6", "external-correlation-key")]:
                command += ["--method-default", f"{relationship}={method}"]
            if context.get("tenant") is not None:
                command += ["--query-tenant", context["tenant"]]
            report = run(command, output / "correlation.json")
            answers = [a for a in report["answers"] if a["query"] == "effects-for-execution"
                       and a["subject"]["references"]["proposal"] == context["action"]
                       and a["subject"]["tenant"] == context.get("tenant")]
            # Cardinality is part of success: never silently pick the first matching execution.
            actual = {}
            if len(answers) == 1:
                answer = answers[0]
                effects = answer["observed"]["correlated_effects"]
                assert all(e["scope"] == context["service"] and
                           e["tenant"] == context.get("tenant") for e in effects)
                actual = {"action": answer["subject"]["references"]["proposal"],
                          "effect": {"established": "confirmed", "unknown": "unconfirmed"}
                          .get(answer["state"], answer["state"]),
                          "confirmed_tickets": sorted(e["ticket_id"] for e in effects)
                          if answer["state"] == "established" else None}
            if "receipt_signature" in basis["checks"]:
                # These pinned signature cases contain one service and no tenant; signatures
                # do not cover tenant.id. No tenant authentication is inferred here.
                assert context.get("tenant") is None
                signature_command = ["verify-receipts", "--input", str((case / "records.otlp.json").relative_to(ROOT)),
                                     "--key", str((inputs / "trust/test-ticket-service.pub.pem").relative_to(ROOT))]
                sigs = run(signature_command, output / "signatures.json")["receipts"]
                actual["receipt_signature_verified"] = bool(sigs) and all(s["signature"] == "verifies" for s in sigs)
            expected_path = ROOT / "results/2026-10-05" / short / case.name / "expected.json"
            expected = load(expected_path)
            fields = [{"field": key, "actual": actual.get(key), "expected": value,
                       "match": key in actual and actual[key] == value} for key, value in expected.items()]
            result = {"revision": revision, "case": case.name, "query": context,
                      "command": command, "exit_code": 0, "selected_answers": len(answers),
                      "fields": fields, "pass": len(answers) == 1 and all(f["match"] for f in fields)}
            save(output / "comparison.json", result)
            evidence.append(result)
            for source in [case / "basis.json", case / "records.otlp.json", inputs / "mapping.md", expected_path]:
                digest(source)
    for source in [ROOT / "src/lib.rs", ROOT / "src/bin/trace-reader.rs", Path(__file__).resolve()]:
        digest(source)
    save(args.output / "comparison.json", evidence)
    save(args.output / "sha256.json", hashes)
    print(json.dumps({"passed": sum(e["pass"] for e in evidence), "total": len(evidence)}, indent=2))
    return 0 if all(e["pass"] for e in evidence) else 1


if __name__ == "__main__":
    raise SystemExit(main())
