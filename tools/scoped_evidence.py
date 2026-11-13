"""Validate scope selection against recursively verified immutable comparison evidence."""
import json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'evals'))
from read_records import record_reads,intersects

def reference(gate, report, ref):
    path=(report.parent/ref.get('path','')).resolve()
    if not path.is_relative_to(report.parent.resolve()) or not path.is_file() or gate.sha(path)!=ref.get('sha256'):
        raise ValueError('missing/modified scoped reference')
    return path

def prepare(gate,report,data,files,specs,chain):
    mode=data.get('mode','full')
    if mode not in {'full','scoped'}:raise ValueError('unknown comparison mode')
    if data.get('candidate_files',files)!=files:raise ValueError('candidate manifest mismatch')
    if mode=='full':return {},0
    previous=reference(gate,report,data.get('previous',{}))
    if previous in chain or len(chain)>20:raise ValueError('cyclic comparison history')
    old=json.loads(previous.read_text());old_files=old.get('candidate_files')
    if not isinstance(old_files,dict) or gate.fingerprint(old_files)!=old.get('candidate_hash'):raise ValueError('previous candidate manifest missing/mismatched')
    suite=reference(gate,previous,old.get('suite_snapshot',{}))
    if gate.sha(suite)!=old.get('suite_hash'):raise ValueError('previous suite snapshot mismatch')
    if any(old.get(k)!=data.get(k) for k in ['baseline_ref','baseline_hash']):raise ValueError('scoped comparison must keep its baseline')
    verified=gate.check_evidence(previous,old_files,_suite=suite,_chain=(*chain,report))
    depth=verified.get('_verified_scoped_depth',0)+1
    if depth>2:raise ValueError('third consecutive scoped comparison requires a full run')
    old_specs={c['id']:c for c in json.loads(suite.read_text())['cases']}
    if not set(old_specs)<=set(specs):raise ValueError('scoped suite cannot remove cases')
    changed={p for p in set(files)|set(old_files) if files.get(p)!=old_files.get(p)}
    carried={}
    for cid,case in data['cases'].items():
        ref=case.get('carried_from')
        if not ref:continue  # fresh records must match final hash in the main gate
        if reference(gate,report,ref)!=previous:raise ValueError('carry must cite immediately previous comparison')
        if cid not in old_specs or old_specs[cid]!=specs[cid]:raise ValueError('new/changed case must rerun: '+cid)
        prior=old['cases'][cid]
        runpath=(previous.parent/prior['candidate_run']).resolve()
        run=json.loads(runpath.read_text());record=next(r for r in run['cases'] if r['id']==cid)
        reads=record_reads(runpath,record,old_files)
        if record.get('read_set')!=reads or not reads['complete'] or not reads['files']:raise ValueError('no verifiable read record: '+cid)
        if intersects(reads,changed):raise ValueError('changed file intersects reads: '+cid)
        suites={}
        for side in ['baseline','candidate']:
            original=(previous.parent/prior[side+'_run']).resolve()
            new=(report.parent/case[side+'_run']).resolve()
            if gate.sha(original)!=gate.sha(new):raise ValueError('carried run metadata changed: '+cid)
            suites[side]=json.loads(original.read_text())['suite_hash']
        carried[cid]={'candidate_hash':run['source_hash'],'suite_hash':run['suite_hash'],'side_suites':suites}
    return carried,depth
