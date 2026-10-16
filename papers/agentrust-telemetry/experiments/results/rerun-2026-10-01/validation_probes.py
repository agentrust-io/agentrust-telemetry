"""Paper 1 Section 7 claims: validation edge cases and reentrant-callback deadlock.

Usage: python validation_probes.py SOURCE_DIR   (an agentrust-telemetry tree)
Records what each case raised; does not assert.
"""
import json, sys, threading
from copy import deepcopy
from pathlib import Path
SRC = Path(sys.argv[1])
sys.path.insert(0, str(SRC / 'src'))
from agentrust_telemetry import EvidenceAccumulator, SchemaValidator

v = SchemaValidator(SRC / 'spec/schema')
base = json.loads((SRC / 'conformance/fixtures/valid/policy-decision.json').read_text())

def outcome(fn):
    try:
        fn(); return 'accepted'
    except Exception as exc:
        return type(exc).__name__

deep = deepcopy(base); node = {}; deep['attributes'] = node
for _ in range(5000):
    node['x'] = {}; node = node['x']
nonstr = deepcopy(base); nonstr.setdefault('attributes', {})[1] = 'v'
va = SchemaValidator(SRC / 'spec/schema', allowed_attribute_keys=frozenset({'k'}))
nan = deepcopy(base); nan['attributes'] = {'k': float('nan')}
inf = deepcopy(base); inf['attributes'] = {'k': float('inf')}
print('deep nesting (5000):', outcome(lambda: v.validate(deep)))
print('non-string key:', outcome(lambda: v.validate(nonstr)))
print('NaN attribute, validate:', outcome(lambda: va.validate(nan)))
print('Infinity attribute, validate:', outcome(lambda: va.validate(inf)))
print('NaN attribute, accumulator append:', outcome(lambda: EvidenceAccumulator(base['run_id'], va).append(nan)))

holder = {}
def reenter(entry):
    holder['acc'].snapshot()
    return True
acc = EvidenceAccumulator(base['run_id'], v, durable_append=reenter); holder['acc'] = acc
result = {}
t = threading.Thread(target=lambda: result.setdefault('r', outcome(lambda: acc.append(base))), daemon=True)
t.start(); t.join(5)
print('callback re-entering snapshot():', 'deadlocked (no return in 5 s)' if t.is_alive() else result['r'])
