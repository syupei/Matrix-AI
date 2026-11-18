#!/usr/bin/env python3
"""Reobserve retained operation evidence offline in a new directory; never score or run models."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

import operation_evidence as observer


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def kit_hash(kit):
    manifest=json.loads((kit/'MANIFEST.json').read_text())
    for name, expected in manifest['files'].items():
        if sha(kit/name)!=expected:
            raise ValueError('frozen kit member changed: '+name)
    return hashlib.sha256(json.dumps(manifest['files'],sort_keys=True).encode()).hexdigest()


def reobserve(evidence, output, kits):
    evidence,output=Path(evidence).resolve(),Path(output).resolve()
    if output.exists():
        raise ValueError('new correction directory required; preserve earlier evidence')
    if not (evidence/'main-ten').is_dir():
        raise ValueError('retained main-ten evidence directory required')
    available={kit_hash(Path(kit).resolve()):Path(kit).resolve() for kit in kits}
    output.mkdir(parents=True)
    records=[]
    raw={str(path.relative_to(evidence)):sha(path) for path in evidence.rglob('*') if path.is_file()}
    for batch in ('main-ten','d4-round2','d4-round3','guards-seven'):
        for metadata in sorted((evidence/batch).glob('*/*/run.json')):
            meta=json.loads(metadata.read_text());raw[str(metadata.relative_to(evidence))]=sha(metadata)
            for case in meta['cases']:
                for turn in case['turns']:
                    old=turn.get('operation_evidence')
                    if not old:
                        continue
                    tag=metadata.parent.relative_to(evidence)/Path(turn['events']).stem
                    artifact=metadata.parent/(case['id']+'-artifacts')
                    source=available.get(meta['source_hash'])
                    if source is None:
                        raise ValueError('matching frozen kit required: '+meta['source_hash'])
                    work=output/'projects'/tag;work.parent.mkdir(parents=True,exist_ok=True)
                    shutil.copytree(artifact,work);shutil.copytree(source,work/'kit')
                    for name,expected in old['after'].items():
                        if sha(work/name)!=expected:
                            raise ValueError('retained final bytes do not match original pre-final snapshot: '+name)
                    trace=metadata.parent/turn['events'];reply_file=metadata.parent/turn['reply']
                    raw[str(trace.relative_to(evidence))]=sha(trace);raw[str(reply_file.relative_to(evidence))]=sha(reply_file)
                    events=[json.loads(line) for line in trace.read_text().splitlines() if line.strip()]
                    original_root=turn['project_root']
                    # Explicit path rebasing in memory only. Raw traces/replies are never rewritten.
                    mapped=json.loads(json.dumps(events,ensure_ascii=False).replace(original_root,str(work)))
                    reply=reply_file.read_text().replace(original_root,str(work))
                    if old.get('kind')=='direction':
                        tool=work/observer.TONE_TOOL
                        expects=tool.is_file() and b'direction-delivery/1' in tool.read_bytes()
                        new=observer.check_direction(work,reply,mapped,old['before'],old['after'],old['preview'],expects)
                    else:
                        new=observer.check(work,old.get('kind','draft'),reply,mapped,old['before'],old['after'])
                    result=dict(case=case['id'],batch=batch,side=metadata.parent.parent.name,trace=str(trace),
                        path_rebase=dict(original=original_root,offline_view=str(work)),source_hash=meta['source_hash'],
                        original=old,corrected=new,mechanical_result_changed=bool(old['errors'])!=bool(new['errors']),
                        limitation='Offline mechanism observation only; no professional score or old report is changed.')
                    target=output/'observations'/tag.with_suffix('.json');target.parent.mkdir(parents=True,exist_ok=True)
                    target.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');records.append(result)
    if not records:raise ValueError('no retained operation observations found')
    for name,expected in raw.items():
        if sha(evidence/name)!=expected:raise ValueError('original evidence changed: '+name)
    summary=dict(observer_sha256=sha(Path(observer.__file__)),model_calls=0,observations=len(records),
        changed=[dict(case=row['case'],batch=row['batch'],side=row['side'],old_errors=row['original']['errors'],new_errors=row['corrected']['errors'])
                 for row in records if row['mechanical_result_changed']],
        raw_unchanged=raw,limitation='Does not change scores, criteria, source traces, historical observations or reports.')
    (output/'correction.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    return summary


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence',type=Path,required=True);parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--kit',type=Path,action='append',required=True)
    args=parser.parse_args();print(json.dumps(reobserve(args.evidence,args.out,args.kit),ensure_ascii=False,indent=2))
