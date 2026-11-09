#!/usr/bin/env python3
"""A full behavior comparison run and scored on a model command line (Codex by default, or Claude with --runner
claude), case by case in parallel and resumable. Runs and scorers of one comparison use the same runner.

  codex_comparison.py run      --side baseline|candidate --kit KIT --out OUT [--jobs 4] [--model M] [--effort E] [--cases a,b]
  codex_comparison.py score    --out OUT --work WORK [--batch 7] [--jobs 3] [--model M]
  codex_comparison.py assemble --out OUT --work WORK --candidate-kit KIT --baseline-ref REF --reviewer TEXT
  codex_comparison.py focus    --old DIR --new DIR --criteria FILE --work WORK [--batch 7] [--jobs 3] [--model M] [--seed N]

run      one run.py process per case into OUT/<side>/<case>/; cases already complete are skipped, failures are listed.
score    blind copies (scoring.py blind), first scorers by batch, re-check list, second scorers, combine; scorers are
         Codex sessions following evals/scoring-brief.md and write only their output file.
assemble the comparison JSON for tools/production.py: scores, re-checks, flags, observations, evidence with hashes.
Disagreements between scorers are listed and stop here: a person decides them (rescored), as the gate requires.
focus    a pilot after a change, not gate evidence: chosen criteria ({case: [criteria]}) of chosen cases, earlier replies
         (DIR/<case>/, scored as "baseline") against new ones ("candidate"), blind. The first scorer scores only those
         criteria; the second re-scores every new 0, every flag, and every new stage-line 1 the program check does not
         support. The program checks that each reply opens with a stage line carrying a basis, and that in a project with
         no records the first reply's basis says inferred (or a flow started this turn). Writes WORK/focus.json.
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
# Scorers have answered "done" without writing their file: the last step checks it, or returns the scores inline.
CHECK = '\n最后一步：确认当前目录下 scores.json 已写入且是完整的 JSON（可以用 python3 -m json.tool scores.json 检查）；写入失败时，把 JSON 原文放在 "=== JSON START ===" 与 "=== JSON END ===" 两行之间交回。\n'


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
                '--runner', a.runner] + (['--model', a.model] if a.model else []) + (['--effort', a.effort] if a.effort else []) + (['--resume'] if a.resume else [])
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


RUNNER = 'codex'


def scorer(work, name, prompt, model, output):
    folder = work / 'scorers' / name
    folder.mkdir(parents=True, exist_ok=True)
    (folder / 'prompt.md').write_text(prompt, encoding='utf-8')
    quote = lambda x: "'" + x.replace("'", "'\\''") + "'"
    if RUNNER == 'claude':
        # The scorer works in its own folder and may write only there; its final message is read from the trace.
        argv = ['claude', '-p', '--output-format', 'stream-json', '--verbose', '--permission-mode', 'acceptEdits'] + (['--model', model] if model else [])
        return name, ['sh', '-c', 'cd ' + quote(str(folder)) + ' && ' + ' '.join(quote(x) for x in argv) + ' < prompt.md'], folder / 'run.log'
    argv = ['codex', 'exec', '--skip-git-repo-check', '--sandbox', 'workspace-write', '--json', '-C', str(folder), '-o', str(folder / 'last.md')]
    argv += (['-m', model] if model else []) + ['-c', 'model_reasoning_effort="medium"', '-']
    return name, ['sh', '-c', ' '.join(quote(x) for x in argv) + ' < ' + str(folder / 'prompt.md')], folder / 'run.log'


def last_message(folder):
    """The scorer's final message: Codex writes last.md; a Claude trace ends with a result event."""
    if (folder / 'last.md').is_file():
        return (folder / 'last.md').read_text(encoding='utf-8')
    for line in reversed((folder / 'run.log').read_text(encoding='utf-8', errors='ignore').splitlines() if (folder / 'run.log').is_file() else []):
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if event.get('type') == 'result':
            return event.get('result') or ''
    return ''


def collect(folder, output):
    """The scorer's JSON: its output file, or the block it returned between the markers."""
    if output.is_file():
        return json.loads(output.read_text(encoding='utf-8'))
    text = last_message(folder)
    m = re.search(r'=== JSON START ===\s*(.*?)\s*=== JSON END ===', text, re.S)
    if not m:
        raise SystemExit('no scores from ' + folder.name)
    data = json.loads(m.group(1))
    output.write_text(json.dumps(data, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    return data


SECOND = '## 本批要复评的判据（你是第二位评分员）'
FIRST = '## 本批只评下列判据\n\n你是第一位评分员。只评下面列出的判据，其余不评；输出格式同"复评"一节（X、Y 只含列出的判据），flags 照常写。'
STAGE_COUNT = re.compile(r'共\s*\d+\s*步')


def stage_check(text):
    """The program's part of the stage-line check, on one reply: its first line is a stage line with a basis, and the
    basis says inferred or that the flow starts this turn."""
    first = next((line.strip() for line in text.splitlines() if line.strip()), '')
    m = re.search(r'依据[：:]\s*([^｜|]*)', first)
    basis = m.group(1) if m else ''
    return {'stage_line': bool(STAGE_COUNT.search(first) and basis.strip()), 'inferred': '推断' in basis or '本轮开始' in basis,
            'line': first[:240]}


def stage_supported(checks, records):
    """Every reply opens with a stage line; without project records the first one must also be marked inferred."""
    return bool(checks) and all(c['stage_line'] for c in checks) and (records or checks[0]['inferred'])


def brief(work, ids, recheck=None, title=SECOND):
    text = (EVALS / 'scoring-brief.md').read_text(encoding='utf-8')
    for k, v in {'suite': SUITE, 'readme': EVALS / 'README.md', 'fixtures': EVALS / 'fixtures', 'workspace': work / 'ws',
                 'output': 'scores.json'}.items():
        text = text.replace('{' + k + '}', str(v))
    if recheck:
        return text + '\n\n' + title + '\n\n' + json.dumps(recheck, ensure_ascii=False) + '\n' + CHECK
    return text + '\n\n## 本批情境\n\n' + '、'.join(ids) + '\n' + CHECK


def score(a):
    out, work = Path(a.out).resolve(), Path(a.work).resolve()
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
    out, work = Path(a.out).resolve(), Path(a.work).resolve()
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
            'limitations': ['Both versions ran and were scored on the ' + RUNNER.capitalize() + ' command line (one sample per case); scorers were blind ' + RUNNER.capitalize() + ' sessions, '
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


def scorers(work, prefix, groups, listed, title, model, jobs):
    """Run one scorer per group of cases on the listed criteria and return their score files."""
    todo = [scorer(work, prefix + str(n), brief(work, g, {k: listed[k] for k in g}, title), model, None) for n, g in enumerate(groups)
            if not (work / 'scorers' / (prefix + str(n)) / 'scores.json').is_file()]
    pool(todo, jobs, prefix.rstrip('-'))
    files = []
    for n in range(len(groups)):
        folder = work / 'scorers' / (prefix + str(n))
        collect(folder, folder / 'scores.json')
        files.append(str(folder / 'scores.json'))
    return files


def focus(a):
    work = Path(a.work).resolve()
    work.mkdir(parents=True, exist_ok=True)
    listed = json.loads(Path(a.criteria).read_text(encoding='utf-8'))
    ids, suite = sorted(listed), {c['id']: c for c in cases()}
    tool = [sys.executable, '-B', str(EVALS / 'scoring.py')]
    if not (work / 'labels.json').is_file():
        flat_dirs = {}
        for name, folder in (('old', Path(a.old).resolve()), ('new', Path(a.new).resolve())):
            target = flat_dirs[name] = work / 'flat' / name
            shutil.rmtree(target, ignore_errors=True)
            target.mkdir(parents=True)
            for cid in ids:
                for f in (folder / cid).glob(cid + '-*'):
                    if f.is_dir():
                        shutil.copytree(f, target / f.name)
                    elif f.suffix == '.md':
                        shutil.copy2(f, target / f.name)
        subprocess.run(tool + ['blind', '--baseline', str(flat_dirs['old']), '--candidate', str(flat_dirs['new']), '--cases', ','.join(ids),
                               '--workspace', str(work / 'ws'), '--labels', str(work / 'labels.json'), '--seed', str(a.seed)], check=True)
    batches = [ids[i:i + a.batch] for i in range(0, len(ids), a.batch)]
    first = scorers(work, 'first-', batches, listed, FIRST, a.model, a.jobs)
    subprocess.run(tool + ['merge', '--labels', str(work / 'labels.json'), '--scores', *first, '--out', str(work / 'first.json'), '--partial'], check=True)
    scores = json.loads((work / 'first.json').read_text())
    program = {cid: [stage_check(p.read_text(encoding='utf-8')) for p in sorted((Path(a.new).resolve() / cid).glob(cid + '-[0-9]*.md'),
                                                                                    key=lambda p: int(p.stem.rsplit('-', 1)[1]))]
               for cid in ids if 'shows_stage' in listed[cid]}
    supported = {cid: stage_supported(checks, bool(suite[cid].get('fixture'))) for cid, checks in program.items()}
    again = {}
    for cid in ids:
        v = scores[cid]
        keys = {k for k in listed[cid] if v['candidate'][k] == 0 or k in v.get('flags', []) or (k == 'shows_stage' and not supported[cid])}
        if keys:
            again[cid] = sorted(keys)
    (work / 'recheck.json').write_text(json.dumps(again, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    keys = sorted(again)
    second = scorers(work, 'second-', [keys[i:i + a.batch * 2] for i in range(0, len(keys), a.batch * 2)], again, SECOND, a.model, a.jobs)
    if second:
        subprocess.run(tool + ['merge', '--labels', str(work / 'labels.json'), '--scores', *second, '--out', str(work / 'second.json'), '--partial'], check=True)
    rescored = json.loads((work / 'second.json').read_text()) if second else {}
    rows, summary = {}, {}
    for cid in ids:
        for k in listed[cid]:
            one = {s: scores[cid][s][k] for s in ('baseline', 'candidate')}
            two = {s: rescored[cid][s][k] for s in ('baseline', 'candidate')} if k in again.get(cid, []) else None
            new = (one['candidate'] if two is None else (one['candidate'] if one['candidate'] == two['candidate'] else None))
            rows.setdefault(cid, {})[k] = {'old_first': one['baseline'], 'new_first': one['candidate'], 'new_second': two and two['candidate'], 'new': new}
            s = summary.setdefault(k, {'cases': 0, 'new_pass': 0, 'old_pass_first': 0, 'to_person': 0})
            s['cases'] += 1
            s['new_pass'] += new == 1
            s['old_pass_first'] += one['baseline'] == 1
            s['to_person'] += new is None
    out = {'summary': summary, 'program': {cid: {'supported': supported[cid], 'replies': checks} for cid, checks in program.items()},
           'cases': rows, 'observations': {cid: scores[cid].get('observations', '') for cid in ids}}
    (work / 'focus.json').write_text(json.dumps(out, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='command', required=True)
    r = sub.add_parser('run'); r.add_argument('--side', choices=['baseline', 'candidate'], required=True); r.add_argument('--kit', required=True)
    r.add_argument('--out', required=True); r.add_argument('--jobs', type=int, default=4); r.add_argument('--model'); r.add_argument('--effort'); r.add_argument('--cases')
    r.add_argument('--resume', action='store_true', help='later turns resume the first turn\'s session (pilot of E5)')
    s = sub.add_parser('score'); s.add_argument('--out', required=True); s.add_argument('--work', required=True)
    s.add_argument('--batch', type=int, default=7); s.add_argument('--jobs', type=int, default=3); s.add_argument('--model')
    m = sub.add_parser('assemble'); m.add_argument('--out', required=True); m.add_argument('--work', required=True)
    m.add_argument('--candidate-kit', required=True); m.add_argument('--baseline-ref', required=True); m.add_argument('--reviewer', required=True)
    f = sub.add_parser('focus'); f.add_argument('--old', required=True); f.add_argument('--new', required=True); f.add_argument('--criteria', required=True)
    f.add_argument('--work', required=True); f.add_argument('--batch', type=int, default=7); f.add_argument('--jobs', type=int, default=3)
    f.add_argument('--model'); f.add_argument('--seed', type=int, default=32)
    for p in (r, s, f):
        p.add_argument('--runner', choices=['codex', 'claude'], default='codex')
    a = ap.parse_args()
    global RUNNER
    RUNNER = getattr(a, 'runner', 'codex')
    {'run': run, 'score': score, 'assemble': assemble, 'focus': focus}[a.command](a)


if __name__ == '__main__':
    main()
