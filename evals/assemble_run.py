#!/usr/bin/env python3
"""Assemble run.json for behavior runs executed by an orchestrating agent session.

Use when the model CLI cannot be launched (for example inside another agent session).
Each turn's reply must already be saved verbatim as <case>-<n>.md in --output; this
script records one completion event per turn, labeled with the runner, and hashes.
It does not create or alter replies."""
import argparse, hashlib, json
from pathlib import Path
import importlib.util
spec = importlib.util.spec_from_file_location('run', Path(__file__).with_name('run.py'))
run = importlib.util.module_from_spec(spec); spec.loader.exec_module(run)

p = argparse.ArgumentParser()
p.add_argument('--source', type=Path, required=True)
p.add_argument('--output', type=Path, required=True)
p.add_argument('--runner', default='claude subagent')
p.add_argument('--note', required=True, help='how the turns were executed and recorded')
a = p.parse_args()
suite_path = Path(__file__).parent / 'cases/suite.json'; suite = json.loads(suite_path.read_text())
meta = {'source_hash': run.fingerprint(a.source.resolve()), 'suite_hash': hashlib.sha256(suite_path.read_bytes()).hexdigest(),
        'runner': a.runner, 'cli_version': a.note, 'cases': []}
for case in suite['cases']:
    record = {'id': case['id'], 'turns': []}
    for n, user in enumerate(case['turns']):
        reply = a.output / f"{case['id']}-{n}.md"
        if not reply.is_file():
            raise SystemExit(f'missing recorded reply: {reply}')
        events = a.output / f"{case['id']}-{n}.jsonl"
        events.write_text(json.dumps({'type': 'result', 'runner': a.runner, 'recorded_by': 'orchestrator', 'note': a.note}, ensure_ascii=False) + '\n')
        record['turns'].append({'user': user, 'reply': reply.name, 'events': events.name, 'sha256': hashlib.sha256(reply.read_bytes()).hexdigest()})
    meta['cases'].append(record)
(a.output / 'run.json').write_text(json.dumps(meta, ensure_ascii=False, indent=2) + '\n')
print(json.dumps({'source_hash': meta['source_hash'], 'cases': len(meta['cases'])}))
