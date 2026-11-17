#!/usr/bin/env python3
"""Read-only stage transition validation against actual artifacts and review records."""
import argparse
import hashlib
import json
import importlib.util
from types import SimpleNamespace
from pathlib import Path

_tone_spec = importlib.util.spec_from_file_location('stage_tone_contract', Path(__file__).with_name('tone_contract.py'))
tone = importlib.util.module_from_spec(_tone_spec)
_tone_spec.loader.exec_module(tone)

PROFESSIONS=Path(__file__).resolve().parents[2]/'professions'

def load_flows(directory=PROFESSIONS):
    """Stage flows are declared in the profession registries; the gate holds no per-profession lists."""
    stages,review,authority,upstream,rank={},{},{},{},{}
    for f in sorted(Path(directory).glob('*/profession.json')):
        for flow in json.loads(f.read_text(encoding='utf-8')).get('stage_flows',[]):
            key=flow['key']
            if key in stages:raise ValueError('duplicate stage flow: '+key)
            stages[key]=list(flow['stages'])+['complete']
            review[key]=set(flow.get('review',[]))
            if flow.get('authority'):authority[key]=set(flow['authority'])
            if 'authority_rank' in flow:rank[key]=flow['authority_rank']
            for stage,(up,up_stage) in flow.get('upstream',{}).items():upstream[(key,stage)]=(up,up_stage)
    # Upstream first: a confirmation may come from a decider of this flow or of any flow above it.
    chain=['project']+sorted(rank,key=rank.get)
    return stages,review,chain,authority,upstream

STAGES,REVIEW,CHAIN,AUTHORITY,UPSTREAM=load_flows()
ROSTER='management/people.json'

def framework(root, role, stage):
    """Read the same framework declaration used for imported expert admission."""
    directory = root / 'matrix/professions'
    if not directory.is_dir():
        directory = PROFESSIONS
    for path in sorted(directory.glob('*/profession.json')):
        registry = json.loads(path.read_text(encoding='utf-8'))
        if any(flow['key'] == role for flow in registry.get('stage_flows', [])):
            return registry['id'], tone.practice.stage_requirements(registry).get(stage, {})
    raise ValueError('unknown professional flow: ' + role)

def upstream_check(root, role, current, state, registry_root=None):
    need = UPSTREAM.get((role, current))
    if need:
        if not state.get('upstream'):
            raise ValueError('upstream review record required: %s %s' % need)
        up = json.loads(checked_file(root, state['upstream']).read_text())
        if (up.get('role'), up.get('current')) != need:
            raise ValueError('upstream record is not the required review: %s %s' % need)
        try:
            check(root, up, conversation=False, registry_root=registry_root)
        except (ValueError, KeyError, TypeError) as error:
            raise ValueError('upstream review not confirmed or changed: ' + str(error)) from error
    return need

def check_entry(root, state):
    root = Path(root).resolve()
    role, stage = state['role'], state['current']
    if stage not in STAGES.get(role, [])[:-1]:
        raise ValueError('dispatch must name a registered professional stage')
    profession, requirements = framework(root, role, stage)
    upstream_check(root, role, stage, state)
    triggered = tone.check_stage(root, state, [], requirements, phase='entry')
    return {'profession': profession, 'triggered': triggered}

def framework_outputs(root, state, result, registry_root=None):
    """Files that demonstrate newly checked obligations produced by this stage."""
    _, requirements = framework(registry_root or root, state['role'], state['current'])
    completed = [row for row in result.get('framework', {}).get('triggered', [])
                 if row['requirement'] in requirements.get('complete', ())]
    paths = {item['path'] for item in state['artifacts']}
    if any(row['requirement'] == 'direction_fit' for row in completed):
        direction = tone.read(root, tone.DEFAULT_PATH)
        paths.update(direction['parts'][key]['path'] for key in ('scene', 'preview', 'samples', 'practice_profile'))
        paths.update(direction['parts'][key]['path'] for key in ('screenshot', 'manual_review') if key in direction['parts'])
        paths.add(state['tone_fit_review'])
    for row in completed:
        key, scope = row['requirement'], row['scope']
        if key in {'tone_contract', 'direction_profile', 'direction_fit'}:
            continue
        ref = tone.evidence_ref(state, key, scope)
        paths.add(ref['path'])
        record = json.loads(tone.verify_ref(root, ref).read_text(encoding='utf-8'))
        paths.update(item['path'] for item in record['artifacts'])
        paths.update(record[key]['path'] for key in ('screenshot', 'manual_review') if key in record)
        paths.update(item['path'] for item in record.get('anchors', ()))
    return completed, paths

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def checked_file(root,ref):
    root=Path(root).resolve()
    rel=Path(ref)
    if rel.is_absolute() or '..' in rel.parts:raise ValueError('evidence path must stay in project')
    p=root/rel
    if p.is_symlink() or not p.resolve().is_relative_to(root) or not p.is_file():raise ValueError('evidence is missing or unsafe: '+ref)
    return p

def artifact_digest(root,artifacts):
    if not artifacts:raise ValueError('artifacts required')
    pairs=[]
    for a in artifacts:
        actual=digest(checked_file(root,a['path']))
        if a.get('sha256')!=actual:raise ValueError('artifact changed: '+a['path'])
        pairs.append([a['path'],actual])
    if len({p[0] for p in pairs})!=len(pairs):raise ValueError('duplicate artifact')
    return hashlib.sha256(json.dumps(sorted(pairs),ensure_ascii=False,separators=(',',':')).encode()).hexdigest()

def deciding_person(root,role,reply):
    """In projects with two or more listed people, the reply names a person who may decide for this flow."""
    path=Path(root).resolve()/ROSTER
    if not path.is_file():return None
    people={p.get('id'):p for p in json.loads(path.read_text(encoding='utf-8')).get('people',[]) if isinstance(p,dict)}
    if not people:raise ValueError('explicit people registry is empty')
    pid=reply.get('person_id')
    if pid not in people:raise ValueError('team project: reply must name a listed person (person_id)')
    allowed=AUTHORITY.get(role) or set(CHAIN[:CHAIN.index(role)+1])
    if not allowed&set(people[pid].get('decides',[])):raise ValueError('person has no decision authority for this flow or its upstream')
    return pid

def check(root,state,conversation=True,registry_root=None):
    root=Path(root).resolve();role=state['role'];stages=STAGES[role]
    current=state['current'];following=state['next']
    if current not in stages[:-1] or stages[stages.index(current)+1]!=following:raise ValueError('invalid or skipped stage transition')
    scope=state['scope']
    if not isinstance(scope,list) or not scope or not all(isinstance(s,str) and s.strip() for s in scope) or len(set(scope))!=len(scope):raise ValueError('explicit unique scope required')
    if state.get('blockers')!=[]:raise ValueError('unresolved or unspecified blockers')
    if conversation:
        # Requests made in conversation must reach files before moving on (FEEDBACK-PROTOCOL §6).
        ref=state.get('conversation_check')
        if not isinstance(ref,str) or not ref.strip():raise ValueError('conversation check record required')
        record=''.join(checked_file(root,ref).read_text(encoding='utf-8').split())
        if not any(current+arrow+following in record for arrow in ('→','->')):raise ValueError('conversation check record has no entry for '+current+' → '+following)
    content_hash=artifact_digest(root,state['artifacts'])
    # Review/evidence files are projections of existing sources, not a new authority.
    delegated={};person=None
    if current in REVIEW[role] and state.get('delegated_decision'):
        spec=importlib.util.spec_from_file_location('delegation_gate',Path(__file__).with_name('delegation_gate.py'))
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        delegated=module.check(SimpleNamespace(**globals()),root,state,content_hash)
    elif current in REVIEW[role]:
        req=json.loads(checked_file(root,state['request']).read_text())
        reply=json.loads(checked_file(root,state['response']).read_text())
        if not req.get('request_id') or req.get('stage')!=current or req.get('role')!=role:raise ValueError('request does not match stage')
        if req.get('artifact_sha256')!=content_hash or set(req.get('scope',[]))!=set(scope):raise ValueError('request content or scope is stale')
        shown=checked_file(root,req['display_evidence'])
        if not shown.read_text().strip():raise ValueError('missing displayed review evidence')
        if reply.get('actor') not in {'user','person'} or reply.get('choice')!='confirm':raise ValueError('explicit human confirmation required')
        person=deciding_person(root,role,reply)
        if reply.get('request_id')!=req['request_id'] or reply.get('artifact_sha256')!=content_hash or set(reply.get('scope',[]))!=set(scope):raise ValueError('reply is stale or partially scoped')
        evidence=checked_file(root,reply['source'])
        if not evidence.read_text().strip():raise ValueError('response source is empty')
    need=upstream_check(root, role, current, state, registry_root)
    profession, requirements = framework(registry_root or root, role, current)
    triggered = tone.check_stage(root, state, state['artifacts'], requirements)
    result={'allowed':True,'role':role,'from':current,'to':following,'scope':scope,'artifact_sha256':content_hash,'limitation':'Validates records and files, not human identity or professional quality.'}
    if triggered:
        result['framework'] = {'profession': profession, 'triggered': triggered, 'tone_contract': state['tone_contract']}
    result.update(delegated)
    if current in REVIEW[role] and person:result['confirmed_by']=person
    if need:result['upstream']=state['upstream']
    return result

def digests(root,paths):
    """Helper for preparing gate input: per-file sha256 and the combined artifact digest."""
    root=Path(root).resolve()
    artifacts=[{'path':ref,'sha256':digest(checked_file(root,ref))} for ref in paths]
    return {'artifacts':artifacts,'artifact_sha256':artifact_digest(root,artifacts)}

def main():
    p=argparse.ArgumentParser(description='Check a stage transition, or print artifact digests with --digest.')
    p.add_argument('--project',type=Path,required=True)
    g=p.add_mutually_exclusive_group(required=True)
    g.add_argument('--state',type=Path,help='gate input JSON')
    g.add_argument('--digest',nargs='+',metavar='PATH',help='project-relative artifact paths')
    a=p.parse_args()
    try:result=digests(a.project,a.digest) if a.digest else check(a.project,json.loads(a.state.read_text()))
    except (ValueError,KeyError,TypeError,OSError,AttributeError) as e:print(json.dumps({'allowed':False,'error':str(e)},ensure_ascii=False));return 1
    print(json.dumps(result,ensure_ascii=False,indent=2));return 0
if __name__=='__main__':raise SystemExit(main())
