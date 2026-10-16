"""Paper 1 (agentrust-telemetry v1) boundary probes P1 to P4, reconstructed from Section 6.

Usage: python telemetry_probes.py SOURCE_DIR   (an agentrust-telemetry tree)
Prints one line per probe; records observations, does not assert.
"""
import json, sys
from pathlib import Path
SRC = Path(sys.argv[1])
sys.path.insert(0, str(SRC / 'src'))
from agentrust_telemetry import EvidenceAccumulator, SchemaValidator, TelemetryClient, EvidencePersistenceError

v = SchemaValidator(SRC / 'spec/schema')
event = json.loads((SRC / 'conformance/fixtures/valid/policy-decision.json').read_text())

class Log:
    def __init__(self, fail=False): self.calls = 0; self.fail = fail
    def emit(self, rec):
        self.calls += 1
        if self.fail: raise RuntimeError('exporter down')

# P1: durable callback refuses (returns False)
a = EvidenceAccumulator(event['run_id'], v, durable_append=lambda e: False)
log = Log(); raised = False
try: TelemetryClient(v, span_resolver=lambda: None, evidence_sink=a, log_emitter=log).emit(event)
except EvidencePersistenceError: raised = True
print(f'P1 refused ack: EvidencePersistenceError raised={raised}; log projection calls={log.calls}; accepted entries={len(a.snapshot().entries)}')

# P2: log exporter raises after acceptance
a = EvidenceAccumulator(event['run_id'], v)
r = TelemetryClient(v, span_resolver=lambda: None, evidence_sink=a, log_emitter=Log(True)).emit(event)
print(f'P2 failing exporter: entries={len(a.snapshot().entries)}; projection_errors={list(r.projection_errors)}')

# P3: empty accumulator sealed as complete
s = EvidenceAccumulator('empty-run', v).seal(completeness='complete')
print(f'P3 empty seal: entries={len(s.entries)} completeness={s.completeness}')

# P4: callback commits externally, then raises once; caller retries
external = []; state = {'n': 0}
def flaky(entry):
    external.append(entry.event_id); state['n'] += 1
    if state['n'] == 1: raise RuntimeError('ack lost after external commit')
    return True
a = EvidenceAccumulator(event['run_id'], v, durable_append=flaky)
for _ in range(2):
    try: a.append(event); break
    except EvidencePersistenceError: pass
print(f'P4 lost ack then retry: external writes={len(external)}; local entries={len(a.snapshot().entries)}')
