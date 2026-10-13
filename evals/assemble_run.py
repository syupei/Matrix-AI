#!/usr/bin/env python3
"""Assemble run.json for behavior runs executed by an orchestrating agent session.

Use when the model CLI cannot be launched (for example inside another agent session).
Each turn's reply must already be saved verbatim as <case>-<n>.md in --output; this
script records one completion event per turn, labeled with the runner, and hashes.
It does not create or alter replies.

--reuse-from/--reuse carry cases over verbatim from the previous release's run: replies,
traces and artifacts are copied and the record keeps `reused_from` with that run's source
hash. tools/production.py accepts this only when the case's role files are unchanged."""
import argparse, hashlib, json, shutil
from pathlib import Path
import importlib.util
spec = importlib.util.spec_from_file_location('run', Path(__file__).with_name('run.py'))
run = importlib.util.module_from_spec(spec); spec.loader.exec_module(run)

p = argparse.ArgumentParser()
p.add_argument('--source', type=Path, required=True)
p.add_argument('--output', type=Path, required=True)
p.add_argument('--runner', default='claude subagent')
p.add_argument('--note', required=True, help='how the turns were executed and recorded')
p.add_argument('--reuse-from', type=Path, help="previous release's run directory")
p.add_argument('--reuse', default='', help='comma-separated case ids carried over verbatim from --reuse-from')
a = p.parse_args()
suite_path = Path(__file__).parent / 'cases/suite.json'; suite = json.loads(suite_path.read_text())
reuse = [x for x in a.reuse.split(',') if x]
if reuse and not a.reuse_from:
    raise SystemExit('--reuse needs --reuse-from')
previous = json.loads((a.reuse_from / 'run.json').read_text()) if reuse else None
meta = {'source_hash': run.fingerprint(a.source.resolve()), 'suite_hash': hashlib.sha256(suite_path.read_bytes()).hexdigest(),
        'runner': a.runner, 'cli_version': a.note, 'cases': []}
for case in suite['cases']:
    roles = case['role'] if isinstance(case['role'], list) else [case['role']]
    role = next((r for r in roles if (a.source / '.agents/skills' / r / 'SKILL.md').is_file()), roles[-1])
    if case['id'] in reuse:
        old = next((r for r in previous['cases'] if r['id'] == case['id']), None)
        if not old or old.get('role') != role or [t['user'] for t in old['turns']] != case['turns']:
            raise SystemExit(f"cannot reuse {case['id']}: missing, different role or different turns")
        for t in old['turns']:
            for name in (t['reply'], t['events']):
                shutil.copy2(a.reuse_from / name, a.output / name)
        art = a.reuse_from / f"{case['id']}-artifacts"
        if art.is_dir():
            dest = a.output / art.name
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(art, dest)
        meta['cases'].append(dict(old, reused_from={'run': f'{a.reuse_from.name}/run.json', 'source_hash': previous['source_hash']}))
        continue
    record = {'id': case['id'], 'role': role, 'turns': []}
    for n, user in enumerate(case['turns']):
        reply = a.output / f"{case['id']}-{n}.md"
        if not reply.is_file():
            raise SystemExit(f'missing recorded reply: {reply}')
        events = a.output / f"{case['id']}-{n}.jsonl"
        events.write_text(json.dumps({'type': 'result', 'runner': a.runner, 'recorded_by': 'orchestrator', 'note': a.note}, ensure_ascii=False) + '\n')
        record['turns'].append({'user': user, 'reply': reply.name, 'events': events.name, 'sha256': hashlib.sha256(reply.read_bytes()).hexdigest()})
    meta['cases'].append(record)
(a.output / 'run.json').write_text(json.dumps(meta, ensure_ascii=False, indent=2) + '\n')
print(json.dumps({'source_hash': meta['source_hash'], 'cases': len(meta['cases']), 'reused': len(reuse)}))
