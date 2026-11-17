"""Summarize paired observations from a strict subset of the suite for human review."""

import hashlib
import json
from pathlib import Path

from run import fingerprint
from scoring import needs_recheck
from visual_evidence import IMAGE_MAGIC


SIDES = ('baseline', 'candidate')
COMPLETION = {'codex exec': 'turn.completed', 'claude -p': 'result'}
ENVIRONMENT = ('runner', 'cli_version', 'model', 'effort', 'turns')
INPUTS = 'scoring-inputs.json'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def write(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def select(suite, names):
    ids = names.split(',')
    known = {case['id'] for case in suite}
    require(len(ids) == len(set(ids)) and set(ids) <= known, 'unknown, empty or duplicate case ids')
    return [case for case in suite if case['id'] in ids]


def evidence(root, folder):
    require(folder.resolve().is_relative_to(root.resolve()), 'evidence is outside the report bundle')
    result = {}
    for path in sorted(folder.rglob('*')):
        require(not path.is_symlink(), 'symlink in evidence bundle: ' + str(path))
        if path.is_file():
            result[path.relative_to(root).as_posix()] = sha(path)
    return result


def run_record(out, side, case, suite_hash, expected=None):
    cid = case['id']
    prefix = f'{side}/{cid}'
    folder = out / prefix
    files = evidence(out, folder)
    run_path = prefix + '/run.json'
    require(run_path in files, 'missing case run: ' + prefix)
    run = read(out / run_path)
    require(run.get('suite_hash') == suite_hash, 'run suite mismatch: ' + prefix)
    require(run.get('source_hash') and (expected is None or run['source_hash'] == expected),
            'run source mismatch: ' + prefix)
    runner = run.get('runner')
    require(runner in COMPLETION and all(run.get(key) for key in ENVIRONMENT), 'run environment missing: ' + prefix)
    records = run.get('cases')
    require(isinstance(records, list) and len(records) == 1 and records[0].get('id') == cid,
            'wrong case in run: ' + prefix)
    record = records[0]
    require(not any(record.get(key) for key in ('fixture_equivalent', 'carried_from', 'reused_from')),
            'limited summary requires fresh runs: ' + prefix)
    require(record.get('fixture_sha256') == case.get('fixture_sha256'), 'run fixture mismatch: ' + prefix)
    turns = record.get('turns', [])
    require([turn.get('user') for turn in turns] == case['turns'], 'run turns mismatch: ' + prefix)
    for index, turn in enumerate(turns):
        reply, trace = f'{cid}-{index}.md', f'{cid}-{index}.jsonl'
        require(turn.get('reply') == reply and turn.get('events') == trace and
                files.get(prefix + '/' + reply) == turn.get('sha256') and prefix + '/' + reply in files and
                prefix + '/' + trace in files, 'missing or modified turn output: ' + prefix)
        entries = [json.loads(line) for line in (folder / trace).read_text(encoding='utf-8').splitlines() if line.strip()]
        require(any(row.get('type') == COMPLETION[runner] and not row.get('is_error') for row in entries),
                'model turn did not complete: ' + prefix)
    artifacts = f'{prefix}/{cid}-artifacts/'
    actual = {path.removeprefix(prefix + '/'): digest for path, digest in files.items() if path.startswith(artifacts)}
    require(record.get('artifacts') == actual, 'missing or modified run artifacts: ' + prefix)
    if case.get('visual_preview'):
        receipt = artifacts + 'visual-evidence/capture.json'
        require(receipt in files and read(out / receipt) == record.get('visual_evidence'),
                'missing or modified visual capture receipt: ' + prefix)
        visual = record['visual_evidence']
        if visual.get('status') == 'captured':
            screenshot = artifacts + 'visual-evidence/preview.png'
            require(visual.get('screenshot') == 'visual-evidence/preview.png' and screenshot in files and
                    visual.get('sha256') == files[screenshot] and (out / screenshot).read_bytes().startswith(IMAGE_MAGIC),
                    'captured screenshot missing or modified: ' + prefix)
        else:
            require(visual.get('status') in ('browser_unavailable', 'preview_missing', 'capture_failed'),
                    'unknown visual capture outcome: ' + prefix)
    return run, {'run': run_path, 'evidence': files}


def paired(out, cases, suite_hash, sources=None):
    environments, by_side, runs = set(), {}, {}
    for side in SIDES:
        by_side[side] = set()
        for case in cases:
            run, saved = run_record(out, side, case, suite_hash, sources[side] if sources else None)
            environments.add(tuple(run[key] for key in ENVIRONMENT))
            by_side[side].add(run['source_hash'])
            runs.setdefault(case['id'], {})[side] = saved
    require(len(environments) == 1, 'paired runs must match runner, CLI version, model, effort and turn mode')
    require(all(len(by_side[side]) == 1 for side in SIDES), 'multiple source hashes on one side')
    return {'suite_hash': suite_hash, 'sources': {side: next(iter(by_side[side])) for side in SIDES},
            'environment': dict(zip(ENVIRONMENT, next(iter(environments)))), 'runs': runs}


def bind_scoring(out, work, cases, suite_hash, runner, model, batch):
    inputs = paired(out, cases, suite_hash)
    expected_runner = {'codex': 'codex exec', 'claude': 'claude -p'}[runner]
    require(inputs['environment']['runner'] == expected_runner and inputs['environment']['model'] == model,
            'limited scoring must use the paired runner and model')
    inputs['batch_size'] = batch
    context = work / INPUTS
    if context.exists():
        require(read(context) == inputs, 'paired input or scoring batch changed; use a fresh scoring directory')
    else:
        require(not (work / 'labels.json').exists() and not (work / 'scorers').exists(),
                'unbound scores present; use a fresh scoring directory')
        write(context, inputs)


def score_row(row, keys, label):
    for side in SIDES:
        values = row.get(side, {})
        require(set(values) == keys and all(type(value) is int and value in (0, 1) for value in values.values()),
                'incomplete or invalid scores: ' + label + '/' + side)
    flags = row.get('flags', [])
    require(isinstance(flags, list) and set(flags) <= keys, 'invalid score flags: ' + label)


def summarize_scores(work, cases):
    first = read(work / 'merged.json')
    require(set(first) == {case['id'] for case in cases}, 'scored case subset differs from selected runs')
    to_check = {}
    for case in cases:
        cid = case['id']
        score_row(first[cid], set(case['criteria']), cid)
        keys = needs_recheck(first[cid])
        if keys:
            to_check[cid] = keys
    require(read(work / 'recheck.json') == to_check, 'required recheck list differs from the first scores')
    second = read(work / 'second.json') if (work / 'second.json').is_file() else {}
    require(set(second) == set(to_check), 'second scores do not cover the required rechecks')
    rows, disagreements, regressions, failures = {}, [], [], []
    summary = {'rechecked': 0, 'agreed': 0, 'to_person': 0}
    for cid, result in first.items():
        row = dict(result)
        keys = to_check.get(cid, [])
        if keys:
            score_row(second[cid], set(keys), cid + '/recheck')
            row['second_observations'] = second[cid].get('observations', '')
        rechecked = {}
        for criterion, candidate in result['candidate'].items():
            pair = {'baseline': result['baseline'][criterion], 'candidate': candidate}
            item = {'case': cid, 'criterion': criterion}
            if criterion in keys:
                another = {side: second[cid][side][criterion] for side in SIDES}
                agree = pair == another
                rechecked[criterion] = {'first': pair, 'second': another, 'agree': agree}
                summary['rechecked'] += 1
                summary['agreed' if agree else 'to_person'] += 1
                if not agree:
                    disagreements.append(item | rechecked[criterion])
                    continue
            if candidate == 0:
                failures.append(item)
                if pair['baseline'] == 1:
                    regressions.append(item)
        if rechecked:
            row['rechecked'] = rechecked
        rows[cid] = row
    require(read(work / 'combined.json') == {'summary': summary, 'cases': {
        cid: row['rechecked'] for cid, row in rows.items() if 'rechecked' in row}},
        'combined scores differ from the actual first and second scores')
    return {'cases': rows, 'rechecking': summary, 'unresolved_disagreements': disagreements,
            'observed_regressions': regressions, 'observed_candidate_failures': failures}


def summarize(args, suite_path, release_manifests):
    out, work = Path(args.out).resolve(), Path(args.work).resolve()
    require(work.is_relative_to(out) and work != out, 'keep scoring work inside the evidence bundle')
    require(args.reviewer.strip(), 'review attribution is required')
    suite_bytes = suite_path.read_bytes()
    suite_hash = hashlib.sha256(suite_bytes).hexdigest()
    suite = json.loads(suite_bytes)['cases']
    cases = select(suite, args.cases)
    require(len(cases) < len(suite), 'limited summary requires a strict subset of the suite')
    require(Path(args.baseline_ref).name == args.baseline_ref, 'baseline ref must be a release name')
    kit = Path(args.candidate_kit).resolve()
    files = read(kit / 'MANIFEST.json')['files']
    prior = read(release_manifests / (args.baseline_ref + '.json'))['files']
    source_hash = lambda file_map: hashlib.sha256(json.dumps(file_map, sort_keys=True).encode()).hexdigest()
    sources = {'baseline': source_hash(prior), 'candidate': source_hash(files)}
    require(fingerprint(kit) == sources['candidate'], 'candidate files differ from the manifest')
    inputs = paired(out, cases, suite_hash, sources)
    recorded = read(work / INPUTS)
    require(inputs == {key: recorded.get(key) for key in inputs}, 'scores are bound to different paired inputs')
    scores = summarize_scores(work, cases)
    for cid, by_side in inputs['runs'].items():
        for side, saved in by_side.items():
            scores['cases'][cid].update({side + '_run': saved['run'], side + '_evidence': [
                {'path': path, 'sha256': digest} for path, digest in saved['evidence'].items()]})
    ids = [case['id'] for case in cases]
    omitted = [case['id'] for case in suite if case['id'] not in ids]
    scoring_files = [work / name for name in (INPUTS, 'labels.json', 'merged.json', 'recheck.json', 'second.json', 'combined.json')]
    scorer_dir = work / 'scorers'
    raw_scores = evidence(out, scorer_dir)
    saved_scores = {path.relative_to(out).as_posix(): sha(path) for path in scoring_files if path.is_file()}
    snapshot = out / 'suite.snapshot.json'
    report = out / 'comparison-limited.json'
    snapshot.write_bytes(suite_bytes)
    write(report, {'mode': 'limited', 'full_suite_pass': False, 'eligible_as_full_baseline': False,
                   'review_status': 'needs_human_decision' if scores['unresolved_disagreements'] else 'recorded',
                   'baseline_ref': args.baseline_ref, 'baseline_hash': sources['baseline'],
                   'candidate_hash': sources['candidate'], 'candidate_files': files, 'suite_hash': suite_hash,
                   'suite_snapshot': {'path': snapshot.name, 'sha256': suite_hash}, 'reviewer': args.reviewer,
                   'environment': inputs['environment'], 'selected_cases': ids, 'not_run_cases': omitted,
                   'coverage': {'suite_cases': len(suite), 'paired_cases': len(ids), 'not_run': len(omitted)},
                   'scoring_files': saved_scores | raw_scores,
                   'limitations': ['Only the listed subset was executed, once per case and side.',
                                   'Fixtures and their confirmations are synthetic. Visual and playtest claims are limited to observed evidence.',
                                   'For human review of a limited comparison only. No release decision or full-baseline eligibility.'],
                   **scores})
    return report, len(ids), len(omitted), scores['rechecking']
