#!/usr/bin/env python3
"""Read-only stage transition validation against actual artifacts and review records."""
import argparse
import hashlib
import json
import importlib.util
from datetime import datetime, timezone
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
            inherited = None
            for stage in flow['stages']:
                if stage in flow.get('upstream', {}):inherited = tuple(flow['upstream'][stage])
                if stage in flow.get('upstream', {}) or flow.get('inherit_upstream') and inherited:
                    upstream[(key,stage)] = inherited
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
        if not state.get('upstream_bundle'):
            raise ValueError('upstream_bundle of the successful review is required')
        upstream_root, manifest = tone.evidence.stage_receipt(registry_root or root, state['upstream_bundle'])
        if manifest['context'].get('state_path') != state['upstream']:
            raise ValueError('upstream snapshot does not bind the required review state')
        up = json.loads(checked_file(upstream_root, state['upstream']).read_text())
        if state.get('tone_contract') and up.get('tone_contract'):
            tone.check_contract_scope(upstream_root, up['tone_contract'], root, state['tone_contract'], state.get('practice_scope') or state['scope'], registry_root=registry_root or root)
        if (up.get('role'), up.get('current')) != need:
            raise ValueError('upstream record is not the required review: %s %s' % need)
        try:
            check(upstream_root, up, conversation=False, registry_root=registry_root or root, seal=False)
        except (ValueError, KeyError, TypeError) as error:
            raise ValueError('upstream review not confirmed or changed: ' + str(error)) from error
    return need

def check_entry(root, state, task_context=None):
    root = Path(root).resolve()
    role, stage = state['role'], state['current']
    if stage not in STAGES.get(role, [])[:-1]:
        raise ValueError('dispatch must name a registered professional stage')
    profession, requirements = framework(root, role, stage)
    upstream_check(root, role, stage, state)
    triggered = tone.check_stage(root, state, [], requirements, phase='entry', registry_root=root, task_context=task_context)
    return {'profession': profession, 'triggered': triggered}

def framework_outputs(root, state, result, registry_root=None):
    """Files that demonstrate newly checked obligations produced by this stage."""
    _, requirements = framework(registry_root or root, state['role'], state['current'])
    completed = [row for row in result.get('framework', {}).get('triggered', [])
                 if row['requirement'] in requirements.get('complete', ()) or result.get('increment_review') and row['requirement'] in {'implementation_walkthrough','increment_fit'}]
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
        if key=='asset_anchors':paths.update(record['comparison'][name]['path'] for name in ('review_page','scene_sample'))
    return completed, paths

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def checked_file(root,ref):
    return tone.evidence.file(root,ref)

def artifact_digest(root,artifacts):
    if not artifacts:raise ValueError('artifacts required')
    pairs=[]
    for a in artifacts:
        actual=digest(checked_file(root,a['path']))
        if a.get('sha256')!=actual:raise ValueError('artifact changed: '+a['path'])
        reviewed = tone.direction_binding(tone.DEFAULT_PATH,tone.read(root,tone.DEFAULT_PATH))['direction_sha256'] if a['path'] == tone.DEFAULT_PATH else actual
        pairs.append([a['path'],reviewed])
    if len({p[0] for p in pairs})!=len(pairs):raise ValueError('duplicate artifact')
    return hashlib.sha256(json.dumps(sorted(pairs),ensure_ascii=False,separators=(',',':')).encode()).hexdigest()

def deciding_person(root,role,reply):
    """In projects with two or more listed people, the reply names a person who may decide for this flow."""
    path=Path(root).resolve()/ROSTER
    if not path.is_file():return None
    people={p.get('id'):p for p in json.loads(checked_file(root, ROSTER).read_text(encoding='utf-8')).get('people',[]) if isinstance(p,dict)}
    if not people:raise ValueError('explicit people registry is empty')
    pid=reply.get('person_id')
    if pid not in people:raise ValueError('team project: reply must name a listed person (person_id)')
    allowed=AUTHORITY.get(role) or set(CHAIN[:CHAIN.index(role)+1])
    if not allowed&set(people[pid].get('decides',[])):raise ValueError('person has no decision authority for this flow or its upstream')
    return pid

def _check(root,state,conversation=True,registry_root=None,seal=True,task_context=None,historical=False,checked_at=None):
    root=Path(root).resolve();role=state['role'];stages=STAGES[role]
    current=state['current'];following=state['next']
    if current not in stages[:-1] or stages[stages.index(current)+1]!=following:raise ValueError('invalid or skipped stage transition')
    scope=state['scope']
    if not isinstance(scope,list) or not scope or not all(isinstance(s,str) and s.strip() for s in scope) or len(set(scope))!=len(scope):raise ValueError('explicit unique scope required')
    if state.get('blockers')!=[]:raise ValueError('unresolved or unspecified blockers')
    if task_context:
        dispatched=task_context.get('dispatched',{})
        for key in ('role','current','scope','practice_scope','tone_contract','upstream','upstream_bundle'):
            if key in dispatched and state.get(key)!=dispatched[key]:raise ValueError('completion differs from dispatched '+key)
        _, declared=framework(registry_root or root,role,current)
        for key in declared.get('entry',[]):
            if state.get('practice_evidence',{}).get(key)!=dispatched.get('practice_evidence',{}).get(key):raise ValueError('completion replaced dispatched historical evidence: '+key)
    if conversation:
        # Requests made in conversation must reach files before moving on (FEEDBACK-PROTOCOL §6).
        ref=state.get('conversation_check')
        if not isinstance(ref,str) or not ref.strip():raise ValueError('conversation check record required')
        record=''.join(checked_file(root,ref).read_text(encoding='utf-8').split())
        if not any(current+arrow+following in record for arrow in ('→','->')):raise ValueError('conversation check record has no entry for '+current+' → '+following)
    content_hash=artifact_digest(root,state['artifacts'])
    if role=='design' and current=='D-4':
        request=json.loads(checked_file(root,state['request']).read_text()) if state.get('request') else {}
        tone.check_asset_submission(root,state,request.get('display_evidence'),registry_root=registry_root or root,historical=historical)
    # Review/evidence files are projections of existing sources, not a new authority.
    delegated={};person=None
    if current in REVIEW[role] and state.get('delegated_decision'):
        spec=importlib.util.spec_from_file_location('delegation_gate',Path(__file__).with_name('delegation_gate.py'))
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        delegated=module.check(SimpleNamespace(**globals()),root,state,content_hash,checked_at=checked_at)
    elif current in REVIEW[role]:
        req=json.loads(checked_file(root,state['request']).read_text())
        reply=json.loads(checked_file(root,state['response']).read_text())
        if not req.get('request_id') or req.get('stage')!=current or req.get('role')!=role:raise ValueError('request does not match stage')
        if req.get('artifact_sha256')!=content_hash or set(req.get('scope',[]))!=set(scope):raise ValueError('request content or scope is stale')
        shown=checked_file(root,req['display_evidence'])
        if not shown.read_text().strip():raise ValueError('missing displayed review evidence')
        if req.get('display_sha256') != digest(shown):raise ValueError('displayed review evidence changed or was not frozen')
        if reply.get('actor') not in {'user','person'} or reply.get('choice')!='confirm':raise ValueError('explicit human confirmation required')
        person=deciding_person(root,role,reply)
        if reply.get('request_id')!=req['request_id'] or reply.get('artifact_sha256')!=content_hash or set(reply.get('scope',[]))!=set(scope):raise ValueError('reply is stale or partially scoped')
        evidence=checked_file(root,reply['source'])
        if not evidence.read_text().strip():raise ValueError('response source is empty')
        message = tone.evidence.response_message(root, reply['source'], reply.get('response_id'))
        if reply.get('quote') != message:raise ValueError('reply quote must equal the complete response message')
        if reply.get('display_sha256') != req['display_sha256']:raise ValueError('reply is bound to another display')
        if reply.get('message_sha256') != tone.evidence.digest(message):raise ValueError('reply message changed')
        if (Path(registry_root or root)/'management/runtime/tasks.sqlite3').is_file() and current!='P-1':
            receipt=reply.get('review_receipt') or state.get('review_receipt')
            binding=tone.evidence.verify_human_receipt(registry_root or root,receipt,artifacts=state['artifacts'])
            if binding['display']['sha256']!=req['display_sha256'] or binding['quote']!=message:raise ValueError('stage confirmation differs from its actual PM attention')
            if task_context and binding.get('task_id') and binding['task_id']!=task_context['task_id']:raise ValueError('stage confirmation was displayed for a different task')
    need=upstream_check(root, role, current, state, registry_root)
    profession, requirements = framework(registry_root or root, role, current)
    triggered = tone.check_stage(root, state, state['artifacts'], requirements, registry_root=registry_root or root, seal=seal, task_context=task_context, historical=historical)
    increment_review=bool(task_context and task_context.get('increment_review'))
    if increment_review:
        additional=tone.check_increment(root,state,state['artifacts'],registry_root=registry_root or root,seal=seal,task_context=task_context,historical=historical)
        triggered += [row for row in additional if row not in triggered]
    result={'allowed':True,'role':role,'from':current,'to':following,'scope':scope,'artifact_sha256':content_hash,'limitation':'Validates records and files, not human identity or professional quality.'}
    if increment_review:result['increment_review']=True
    if triggered:
        result['framework'] = {'profession': profession, 'triggered': triggered, 'tone_contract': state['tone_contract']}
    result.update(delegated)
    if current in REVIEW[role] and person:result['confirmed_by']=person
    if need:result['upstream']=state['upstream']
    if task_context:
        controls={state.get(key) for key in ('request','response','conversation_check','tone_fit_review','practice_completion') if state.get(key)}
        for value in tone.evidence.references(state.get('practice_evidence',{})):
            controls.add(value['path'])
            record=json.loads(tone.verify_ref(root,value).read_text())
            for key in ('screenshot','manual_review','run_evidence','timing_evidence','playtest_evidence'):
                if isinstance(record.get(key),dict):controls.add(record[key]['path'])
            if isinstance(record.get('capture_binding'),dict) and record['capture_binding'].get('receipt'):controls.add(record['capture_binding']['receipt']['path'])
        controls.update(task_context.get('review_files',{}))
        if isinstance(state.get('implementation_handoff'),dict):controls.add(state['implementation_handoff']['path'])
        actual={value['path']:value['sha256'] for value in state['artifacts']}
        handed=task_context.get('handed_files',{})
        required=(task_context.get('review_subjects') if role=='design' and current=='D-6' and task_context.get('implementation')
                  else {name:sha for name,sha in handed.items() if name not in controls})
        if not required or any(actual.get(name)!=sha for name,sha in required.items()):raise ValueError('stage artifacts do not cover the actual task and child handover')
    return result


def check(root,state,conversation=True,registry_root=None,seal=True,task_context=None):
    root=Path(root).resolve();authority=Path(registry_root or root).resolve()
    if seal and root!=authority:raise ValueError('cross-root stage sealing is not supported; use seal=False for an isolated evidence view')
    historical=False
    checked_at=datetime.now(timezone.utc).isoformat() if state.get('delegated_decision') else None
    candidate=root.parent/'manifest.json'
    if root!=authority and candidate.is_file():
        manifest=json.loads(candidate.read_text())
        context=manifest.get('context',{})
        if all(context.get(key) for key in ('role','stage','state_path')):
            reference=tone.evidence.ref(authority,candidate.relative_to(authority).as_posix())
            _,manifest=tone.evidence.stage_receipt(authority,reference)
            task_context=manifest['context'].get('task_context')
            checked_at=manifest['context'].get('checked_at')
            if not checked_at and state.get('delegated_decision'):
                raise ValueError('historical delegated stage lacks its trusted close time')
            historical=True
    with tone.evidence.track_reads() as reads:
        result=_check(root,state,conversation,authority,seal,task_context,historical,checked_at)
        if not seal:return result
        token=tone.evidence.digest(state)
        state_path='management/stage-reviews/'+token+'/state.json'
        body=json.dumps(state,ensure_ascii=False,sort_keys=True,indent=2)+'\n'
        published=tone.evidence.publish_immutable(root,state_path,body)
        refs={state_path:published['sha256']}
        # Mutable project inputs must be sealed. Content-addressed authority is already
        # immutable and verified at its original root; recursively copying its views
        # would embed every earlier snapshot again without adding any evidence.
        authority_dirs = ('management/evidence/', 'management/stage-receipts/', 'management/review-sources/')
        for path,sha in reads.items():
            if path.is_relative_to(root):
                name = path.relative_to(root).as_posix()
                if not name.startswith(authority_dirs):refs[name]=sha
        context={'role':state['role'],'stage':state['current'],'scope':state['scope'],
                 'tone_contract':state.get('tone_contract'),'state_path':state_path,'task_context':task_context,
                 'checked_at':checked_at}
        bundle=tone.evidence.seal_bundle(root,[dict(path=name,sha256=sha) for name,sha in refs.items()],context,follow_refs=False)
        view,_=tone.evidence.verify_bundle(root,bundle)
        saved=json.loads(tone.evidence.file(view,state_path).read_text())
        # Replay first. No successful receipt is published for a snapshot that cannot
        # independently read the exact evidence the live check consumed.
        _check(view,saved,conversation,authority,False,task_context,True,checked_at)
        tone.evidence.register_stage_receipt(authority,bundle)
        result.update(review_bundle=bundle,upstream_state=state_path,practice_evidence=state.get('practice_evidence',{}))
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
