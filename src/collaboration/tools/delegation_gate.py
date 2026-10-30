"""Validate scoped delegation records; never manufacture human approvals."""
import json
from datetime import datetime, timezone


def check(gate, root, state, content_hash):
    if state['role'] == 'release' and state['current'] == 'E4.2':
        raise ValueError('release decision cannot be delegated')
    registry = json.loads(gate.checked_file(root, 'collaboration/delegations.json').read_text())
    grants = registry.get('delegations', [])
    ids = [g['id'] for g in grants]
    if len(ids) != len(set(ids)):
        raise ValueError('duplicate delegation id')
    reply = json.loads(gate.checked_file(root, state['delegated_decision']).read_text())
    grant = next((g for g in grants if g['id'] == reply.get('delegation_id')), None)
    if not grant or grant.get('revoked') is not False or type(grant.get('revision')) is not int or grant['revision'] < 1 or reply.get('delegation_revision') != grant.get('revision'):
        raise ValueError('delegation missing, revoked or stale')
    expiry = datetime.fromisoformat(grant['expires_at'])
    if expiry.tzinfo is None or expiry <= datetime.now(timezone.utc):
        raise ValueError('delegation expired or timezone missing')
    if grant.get('role') != state['role'] or state['current'] not in grant.get('stages', []) or not set(state['scope']) <= set(grant.get('scope', [])):
        raise ValueError('decision outside delegated stage or scope')
    source = gate.checked_file(root, grant['source'])
    if not source.read_text().strip() or gate.digest(source) != grant.get('source_sha256'):
        raise ValueError('delegation source missing or changed')
    person = gate.deciding_person(root, state['role'], grant)
    if person is None and grant.get('person_id') != 'user':
        raise ValueError('unlisted delegation issuer')
    if not grant.get('instance_id') or reply.get('instance_id') != grant['instance_id'] or reply.get('decision_kind') != 'routine':
        raise ValueError('wrong delegate or non-routine decision')
    if reply.get('role') != state['role'] or reply.get('stage') != state['current'] or reply.get('artifact_sha256') != content_hash or set(reply.get('scope', [])) != set(state['scope']):
        raise ValueError('delegated decision is stale or partially scoped')
    if not gate.checked_file(root, reply['source']).read_text().strip():
        raise ValueError('delegated rationale missing')
    producers = reply.get('producers')
    if not isinstance(producers, list) or not producers or not all(isinstance(x, str) and x.strip() for x in producers):
        raise ValueError('actual artifact producers required')
    review = json.loads(gate.checked_file(root, reply['review']).read_text())
    if not review.get('checker') or review['checker'] in set(producers + [reply['instance_id']]) or review.get('outcome') != 'passed' or review.get('artifact_sha256') != content_hash or set(review.get('scope', [])) != set(state['scope']):
        raise ValueError('current independent verification required for delegated gate')
    if not gate.checked_file(root, review['evidence']).read_text().strip():
        raise ValueError('verification evidence missing')
    return {'decision_basis': 'delegated', 'delegation_id': grant['id'],
            'delegation_revision': grant['revision'], 'decided_by': reply['instance_id']}
