#!/usr/bin/env python3
"""A full behavior comparison run and scored on the Codex command line, case by case in parallel and resumable.

  codex_comparison.py run      --side baseline|candidate --kit KIT --out OUT [--jobs 4] [--model M] [--effort E] [--cases a,b]
  codex_comparison.py score    --out OUT --work WORK [--batch 7] [--jobs 3] [--model M]
  codex_comparison.py assemble --out OUT --work WORK --candidate-kit KIT --baseline-ref REF --reviewer TEXT

run      one run.py process per case into OUT/<side>/<case>/; cases already complete are skipped, failures are listed.
score    blind copies (scoring.py blind), first scorers by batch, re-check list, second scorers, combine; scorers are
         Codex sessions following evals/scoring-brief.md and write only their output file.
assemble the comparison JSON for tools/production.py: scores, re-checks, flags, observations, evidence with hashes.
Disagreements between scorers are listed and stop here: a person decides them (rescored), as the gate requires.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

EVALS = Path(__file__).resolve().parent
SUITE = EVALS / 'cases/suite.json'


def cases():
    return json.loads(SUITE.read_text(encoding='utf-8'))['cases']


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def complete(folder, case):
    run = Path(folder) / 'run.json'
    if not run.is_file():
        return False
    rec = next((r for r in json.loads(run.read_text())['cases'] if r['id'] == case['id']), None)
    return bool(rec and len(rec['turns']) == len(case['turns']))


def pool(commands, jobs, label):
    """Run (name, argv, log) items with at most jobs at once; returns {name: exit code}."""
    waiting, running, done = list(commands), {}, {}
    while waiting or running:
        while waiting and len(running) < jobs:
            name, argv, log = waiting.pop(0)
            log.parent.mkdir(parents=True, exist_ok=True)
            running[name] = (subprocess.Popen(argv, stdout=open(log, 'w'), stderr=subprocess.STDOUT), time.time())
        for name, (proc, started) in list(running.items()):
            if proc.poll() is not None:
                done[name] = proc.returncode
                print(label, name, 'exit', proc.returncode, round(time.time() - started), 's', flush=True)
                running.pop(name)
        time.sleep(2)
    return done


def run(a):
    out = Path(a.out) / a.side
    wanted = set(a.cases.split(',')) if a.cases else None
    todo = []
    for case in cases():
        if wanted and case['id'] not in wanted:
            continue
        folder = out / case['id']
        if complete(folder, case):
            continue
        shutil.rmtree(folder, ignore_errors=True)
        argv = [sys.executable, '-B', str(EVALS / 'run.py'), '--source', str(Path(a.kit).resolve()), '--output', str(folder), '--case', case['id'],
                '--runner', 'codex'] + (['--model', a.model] if a.model else []) + (['--effort', a.effort] if a.effort else [])
        todo.append((case['id'], argv, out / '_logs' / (case['id'] + '.log')))
    print(a.side, len(todo), 'cases to run', flush=True)
    result = pool(todo, a.jobs, a.side)
    failed = sorted(k for k, v in result.items() if v)
    print(json.dumps({'side': a.side, 'ran': len(result), 'failed': failed}, ensure_ascii=False), flush=True)


def flat(out, side, work):
    """One folder per side with <case>-<n>.md and <case>-artifacts, as scoring.py blind reads them."""
    target = work / 'flat' / side
    shutil.rmtree(target, ignore_errors=True)
    target.mkdir(parents=True)
    for case in cases():
        folder = out / side / case['id']
        for f in folder.glob(case['id'] + '-*'):
            if f.is_dir():
                shutil.copytree(f, target / f.name)
            elif f.suffix == '.md':
                shutil.copy2(f, target / f.name)
    return target


def scorer(work, name, prompt, model, output):
    folder = work / 'scorers' / name
    folder.mkdir(parents=True, exist_ok=True)
    (folder / 'prompt.md').write_text(prompt, encoding='utf-8')
    argv = ['codex', 'exec', '--skip-git-repo-check', '--sandbox', 'workspace-write', '--json', '-C', str(folder), '-o', str(folder / 'last.md')]
    argv += (['-m', model] if model else []) + ['-c', 'model_reasoning_effort="medium"', '-']
    return name, ['sh', '-c', ' '.join("'" + x.replace("'", "'\\''") + "'" for x in argv) + ' < ' + str(folder / 'prompt.md')], folder / 'run.log'


def collect(folder, output):
    """The scorer's JSON: its output file, or the block it returned between the markers."""
    if output.is_file():
        return json.loads(output.read_text(encoding='utf-8'))
    text = (folder / 'last.md').read_text(encoding='utf-8') if (folder / 'last.md').is_file() else ''
    m = re.search(r'=== JSON START ===\s*(.*?)\s*=== JSON END ===', text, re.S)
    if not m:
        raise SystemExit('no scores from ' + folder.name)
    data = json.loads(m.group(1))
    output.write_text(json.dumps(data, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    return data


def brief(work, ids, recheck=None):
    text = (EVALS / 'scoring-brief.md').read_text(encoding='utf-8')
    for k, v in {'suite': SUITE, 'readme': EVALS / 'README.md', 'fixtures': EVALS / 'fixtures', 'workspace': work / 'ws',
                 'output': 'scores.json'}.items():
        text = text.replace('{' + k + '}', str(v))
    if recheck:
        return text + '\n\n## 本批要复评的判据（你是第二位评分员）\n\n' + json.dumps(recheck, ensure_ascii=False) + '\n'
    return text + '\n\n## 本批情境\n\n' + '、'.join(ids) + '\n'


def score(a):
    out, work = Path(a.out), Path(a.work)
    work.mkdir(parents=True, exist_ok=True)
    tool = [sys.executable, '-B', str(EVALS / 'scoring.py')]
    if not (work / 'labels.json').is_file():
        subprocess.run(tool + ['blind', '--baseline', str(flat(out, 'baseline', work)), '--candidate', str(flat(out, 'candidate', work)),
                               '--cases', 'all', '--workspace', str(work / 'ws'), '--labels', str(work / 'labels.json'), '--seed', '31'], check=True)
    ids = [c['id'] for c in cases()]
    batches = [ids[i:i + a.batch] for i in range(0, len(ids), a.batch)]
    first = []
    jobs = [scorer(work, 'first-' + str(n), brief(work, b), a.model, None) for n, b in enumerate(batches)
            if not (work / 'scorers' / ('first-' + str(n)) / 'scores.json').is_file()]
    pool(jobs, a.jobs, 'scoring')
    for n in range(len(batches)):
        folder = work / 'scorers' / ('first-' + str(n))
        collect(folder, folder / 'scores.json')
        first.append(str(folder / 'scores.json'))
    subprocess.run(tool + ['merge', '--labels', str(work / 'labels.json'), '--scores', *first, '--out', str(work / 'merged.json')], check=True)
    subprocess.run(tool + ['recheck', '--scores', str(work / 'merged.json'), '--out', str(work / 'recheck.json')], check=True)
    listed = json.loads((work / 'recheck.json').read_text())
    keys = sorted(listed)
    groups = [keys[i:i + a.batch * 2] for i in range(0, len(keys), a.batch * 2)]
    jobs = [scorer(work, 'second-' + str(n), brief(work, g, {k: listed[k] for k in g}), a.model, None) for n, g in enumerate(groups)
            if not (work / 'scorers' / ('second-' + str(n)) / 'scores.json').is_file()]
    pool(jobs, a.jobs, 'rechecking')
    second = []
    for n in range(len(groups)):
        folder = work / 'scorers' / ('second-' + str(n))
        collect(folder, folder / 'scores.json')
        second.append(str(folder / 'scores.json'))
    if second:
        subprocess.run(tool + ['merge', '--labels', str(work / 'labels.json'), '--scores', *second, '--out', str(work / 'second.json'), '--partial'], check=True)
        subprocess.run(tool + ['combine', '--first', str(work / 'merged.json'), '--second', str(work / 'second.json'),
                               '--recheck', str(work / 'recheck.json'), '--out', str(work / 'combined.json')], check=True)
    else:
        (work / 'combined.json').write_text(json.dumps({'summary': {'rechecked': 0, 'agreed': 0, 'to_person': 0}, 'cases': {}}) + '\n')


def assemble(a):
    out, work = Path(a.out), Path(a.work)
    merged = json.loads((work / 'merged.json').read_text())
    combined = json.loads((work / 'combined.json').read_text())
    to_person = {cid: {k: r for k, r in rows.items() if not r['agree']} for cid, rows in combined['cases'].items()}
    to_person = {k: v for k, v in to_person.items() if v}
    if to_person:
        (work / 'to_person.json').write_text(json.dumps(to_person, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
        raise SystemExit('scorers disagree on ' + str(sum(len(v) for v in to_person.values())) + ' scores; a person decides them (see to_person.json)')
    kit = Path(a.candidate_kit).resolve()
    files = json.loads((kit / 'MANIFEST.json').read_text())['files']
    report = out / 'comparison.json'
    data = {'candidate_hash': hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest(), 'baseline_ref': a.baseline_ref,
            'suite_hash': sha(SUITE), 'reviewer': a.reviewer, 'cases': {},
            'limitations': ['Both versions ran and were scored on the Codex command line (one sample per case); scorers were blind Codex sessions, '
                            'a second scorer re-checked the scores that decide the gate.', 'Synthetic projects and scripted user turns; no real person or project.'],
            'rechecking': combined['summary']}
    prior = Path(__file__).resolve().parents[1] / 'release-manifests' / (a.baseline_ref + '.json')
    data['baseline_hash'] = hashlib.sha256(json.dumps(json.loads(prior.read_text())['files'], sort_keys=True).encode()).hexdigest()
    for case in cases():
        cid, m = case['id'], merged[case['id']]
        entry = {'baseline': m['baseline'], 'candidate': m['candidate'], 'observations': m.get('observations', ''), 'flags': m.get('flags', [])}
        if cid in combined['cases']:
            entry['rechecked'] = combined['cases'][cid]
        for side in ('baseline', 'candidate'):
            folder = out / side / cid
            entry[side + '_run'] = str((folder / 'run.json').relative_to(out))
            entry[side + '_evidence'] = [{'path': str(p.relative_to(out)), 'sha256': sha(p)} for p in sorted(folder.rglob('*')) if p.is_file()]
        data['cases'][cid] = entry
    report.write_text(json.dumps(data, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    print(json.dumps({'report': str(report), 'cases': len(data['cases']), 'rechecking': combined['summary']}, ensure_ascii=False))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='command', required=True)
    r = sub.add_parser('run'); r.add_argument('--side', choices=['baseline', 'candidate'], required=True); r.add_argument('--kit', required=True)
    r.add_argument('--out', required=True); r.add_argument('--jobs', type=int, default=4); r.add_argument('--model'); r.add_argument('--effort'); r.add_argument('--cases')
    s = sub.add_parser('score'); s.add_argument('--out', required=True); s.add_argument('--work', required=True)
    s.add_argument('--batch', type=int, default=7); s.add_argument('--jobs', type=int, default=3); s.add_argument('--model')
    m = sub.add_parser('assemble'); m.add_argument('--out', required=True); m.add_argument('--work', required=True)
    m.add_argument('--candidate-kit', required=True); m.add_argument('--baseline-ref', required=True); m.add_argument('--reviewer', required=True)
    a = ap.parse_args()
    {'run': run, 'score': score, 'assemble': assemble}[a.command](a)


if __name__ == '__main__':
    main()
