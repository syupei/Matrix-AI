#!/usr/bin/env python3
"""Read-only stage transition validation against actual artifacts and review records."""
import argparse
import hashlib
import json
from pathlib import Path

STAGES={'product':['S1','S2','S3','S4','S5','S6','S7','complete'], 'design':['D1','D2','D3','D4','D5','D6','D7','complete'], 'engineering':['E1.1','E1.2','E1.3','E1.4','complete']}
REVIEW={'product':{'S1','S2','S3','S4','S5','S6','S7'},'design':{'D1','D2','D4','D6'},'engineering':{'E1.4'}}

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

def check(root,state):
    root=Path(root).resolve();role=state['role'];stages=STAGES[role]
    current=state['current'];following=state['next']
    if current not in stages[:-1] or stages[stages.index(current)+1]!=following:raise ValueError('invalid or skipped stage transition')
    scope=state['scope']
    if not isinstance(scope,list) or not scope or not all(isinstance(s,str) and s.strip() for s in scope) or len(set(scope))!=len(scope):raise ValueError('explicit unique scope required')
    if state.get('blockers')!=[]:raise ValueError('unresolved or unspecified blockers')
    content_hash=artifact_digest(root,state['artifacts'])
    # Review/evidence files are projections of existing sources, not a new authority.
    if current in REVIEW[role]:
        req=json.loads(checked_file(root,state['request']).read_text())
        reply=json.loads(checked_file(root,state['response']).read_text())
        if not req.get('request_id') or req.get('stage')!=current or req.get('role')!=role:raise ValueError('request does not match stage')
        if req.get('artifact_sha256')!=content_hash or set(req.get('scope',[]))!=set(scope):raise ValueError('request content or scope is stale')
        shown=checked_file(root,req['display_evidence'])
        if not shown.read_text().strip():raise ValueError('missing displayed review evidence')
        if reply.get('actor')!='user' or reply.get('choice')!='confirm':raise ValueError('explicit human confirmation required')
        if reply.get('request_id')!=req['request_id'] or reply.get('artifact_sha256')!=content_hash or set(reply.get('scope',[]))!=set(scope):raise ValueError('reply is stale or partially scoped')
        evidence=checked_file(root,reply['source'])
        if not evidence.read_text().strip():raise ValueError('response source is empty')
    return {'allowed':True,'role':role,'from':current,'to':following,'scope':scope,'artifact_sha256':content_hash,'limitation':'Validates records and files, not human identity or professional quality.'}

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
    except (ValueError,KeyError,TypeError,OSError) as e:print(json.dumps({'allowed':False,'error':str(e)},ensure_ascii=False));return 1
    print(json.dumps(result,ensure_ascii=False,indent=2));return 0
if __name__=='__main__':raise SystemExit(main())
