"""Copy verified cases without relabeling their source/suite metadata."""
import json,shutil,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import production as gate
from read_records import record_reads,intersects,changes

def carry(previous,output,source,ids):
    previous=previous.resolve();output=output.resolve()
    if output.exists():raise ValueError('scope output must be new')
    old=json.loads(previous.read_text());old_files=old.get('candidate_files')
    if not isinstance(old_files,dict):raise ValueError('previous comparison needs candidate_files')
    ref=old.get('suite_snapshot',{});suite=(previous.parent/ref.get('path','')).resolve()
    if not suite.is_relative_to(previous.parent) or not suite.is_file() or gate.sha(suite)!=ref.get('sha256'):raise ValueError('previous suite snapshot missing')
    gate.check_evidence(previous,old_files,_suite=suite)
    files=json.loads((source/'MANIFEST.json').read_text())['files']
    specs={c['id']:c for c in json.loads((gate.ROOT/'evals/cases/suite.json').read_text())['cases']}
    old_specs={c['id']:c for c in json.loads(suite.read_text())['cases']}
    changed=changes(old_files,files)
    for cid in ids:
        if cid not in old_specs or old_specs[cid]!=specs.get(cid):raise ValueError('new/changed case must rerun: '+cid)
        case=old['cases'][cid];rp=previous.parent/case['candidate_run'];run=json.loads(rp.read_text());record=next(r for r in run['cases'] if r['id']==cid)
        reads=record_reads(rp,record,old_files)
        if not reads['complete'] or not reads['files'] or record.get('read_set')!=reads or intersects(reads,changed):raise ValueError('case needs fresh execution: '+cid)
    # Copy the immutable report dependency bundle, not just replies or a retagged run.json.
    seen=set()
    def copy_ref(path):
        path=path.resolve()
        if not path.is_relative_to(previous.parent):raise ValueError('history leaves report bundle')
        if path in seen:return
        seen.add(path);target=output/'history'/path.relative_to(previous.parent);target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,target)
    def bundle(report):
        if report.resolve() in seen:return
        copy_ref(report);d=json.loads(report.read_text())
        if d.get('suite_snapshot'):copy_ref(report.parent/d['suite_snapshot']['path'])
        for c in d['cases'].values():
            for side in ['baseline','candidate']:
                for e in c[side+'_evidence']:copy_ref(report.parent/e['path'])
            if c.get('carried_from'):bundle(report.parent/c['carried_from']['path'])
        if d.get('previous'):bundle(report.parent/d['previous']['path'])
    bundle(previous)
    result={}
    for cid in ids:
        c=json.loads(json.dumps(old['cases'][cid]));replies={}
        for side in ['baseline','candidate']:
            rp=previous.parent/c[side+'_run'];r=json.loads(rp.read_text());record=next(x for x in r['cases'] if x['id']==cid)
            replies[side]=[t['sha256'] for t in record['turns']]
            c[side+'_run']='history/'+c[side+'_run']
            for e in c[side+'_evidence']:e['path']='history/'+e['path']
        c['carried_from']={'path':'history/'+previous.name,'sha256':gate.sha(previous),'replies':replies};result[cid]=c
    (output/'carried-cases.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    return {'cases':list(result),'previous':{'path':'history/'+previous.name,'sha256':gate.sha(previous)},'note':'Merge carried-cases with fresh final-source cases in a scoped comparison; gate verifies again.'}
