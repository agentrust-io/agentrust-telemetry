"""Does TRACE finalization notice an executed action whose digest differs from the approved one?

Usage: python approval_binding_probe.py SOURCE_DIR   (an agentrust-telemetry tree)
"""
import json, sys
from pathlib import Path
ROOT = Path(sys.argv[1]); sys.path.insert(0, str(ROOT / 'src'))
from agentrust_telemetry import EvidenceAccumulator, SchemaValidator, TraceConfiguration, finalize_trace
from agentrust_trace import generate_key
fx = lambda n: json.loads((ROOT / 'conformance/fixtures/valid' / n).read_text())
v = SchemaValidator(ROOT / 'spec/schema')
config = TraceConfiguration(subject='spiffe://example.test/agent/workflow', model_provider='example', model_id='m', model_version='1',
    build_digest='sha256:' + 'b' * 64, build_slsa_level=1, origin_kind='self', origin_producer='example-runtime',
    appraisal_verifier='https://example.test/verifier', classification_taxonomy='example.enterprise.v1',
    classification_order=('public', 'internal', 'confidential', 'restricted'))
policy = fx('policy-decision.json'); policy['decision'] = 'challenge'
request = fx('approval.json'); request.update(event_type='approval.requested', event_id='018f0f7d-7a13-7cc2-8000-000000000010',
    policy_event_id=policy['event_id'], chain_id='operators', chain_version='3', expires_at_unix_nano='1787080100000000000', time_unix_nano='1787079500000000000')
approval = fx('approval.json'); approval.update(event_type='approval.approved', policy_event_id=policy['event_id'], chain_id='operators',
    chain_version='3', expires_at_unix_nano=request['expires_at_unix_nano'])
for label, digest in (('same digest as approved', 'b' * 64), ('different digest', 'c' * 64)):
    action = fx('action.json'); action['action_digest'] = {'algorithm': 'sha256', 'value': digest}
    acc = EvidenceAccumulator(policy['run_id'], v)
    for e in (policy, request, approval, fx('data-flow.json'), action): acc.append(e)
    rec = finalize_trace(acc.seal(completeness='complete'), config, signing_key=generate_key())
    print(f'executed action with {label}: appraisal={rec["appraisal"]["status"]}')
