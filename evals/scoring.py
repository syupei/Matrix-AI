#!/usr/bin/env python3
"""Blind scoring and second-scorer re-checks for a behavior comparison.

  blind    --baseline DIR --candidate DIR --cases a,b|all --workspace WS --labels FILE [--seed N]
           Copy each case's replies and project files into WS/<case>/X and WS/<case>/Y, the two sides in random
           order. The labels file (kept outside WS) records which letter is which version; scorers never see it.
  merge    --labels FILE --scores FILE [FILE ...] --out FILE [--partial]
           Turn scorer output {case: {X, Y, observations, flags}} into {case: {baseline, candidate, observations, flags}};
           --partial accepts a second scorer's subset of criteria.
  recheck  --scores FILE [FILE ...] --out FILE
           List the criteria a second scorer must score again: candidate 0, candidate below baseline, baseline 0 with
           candidate 1 (a new mechanism), and every criterion the first scorer flagged as a borderline judgment.
  carry    --previous COMPARISON --baseline DIR --candidate DIR --out FILE
           Cases whose replies on both sides are byte-identical to a previous comparison keep that comparison's scores,
           re-checks and decisions (carried_from names it); prints the cases that still go to the scorers.
  combine  --first FILE [FILE ...] --second FILE [FILE ...] --recheck FILE --out FILE
           Compare the two scorers on the listed criteria. Agreements stand; disagreements go to a person, whose
           decision is recorded as a rescoring with the person's words. Prints the agreement counts.
"""
import argparse, hashlib, json, random, re, shutil
from pathlib import Path
from read_records import claude_tools, project_directory

SUITE = Path(__file__).resolve().parent / 'cases/suite.json'


def criteria():
    return {c['id']: c['criteria'] for c in json.loads(SUITE.read_text(encoding='utf-8'))['cases']}


def load(files):
    merged = {}
    for f in files:
        for cid, v in json.loads(Path(f).read_text(encoding='utf-8')).items():
            if cid in merged:
                raise SystemExit(cid + ' scored twice')
            merged[cid] = v
    return merged


def claude_audit(events):
    """Pair each tool call with the actual result envelope, keeping call order."""
    calls, results = {}, {}
    for number, event in enumerate(events, 1):
        content = event.get('message', {}).get('content', [])
        blocks = content if isinstance(content, list) else []
        if event.get('type') in {'tool_use', 'tool_result'}:
            blocks = [event]
        for block in blocks:
            if isinstance(block, dict) and block.get('type') == 'tool_result':
                results[block.get('tool_use_id')] = block
        for call in claude_tools([event]):
            if call.get('id') and call['name'] not in {'SubagentHandback'}:
                calls.setdefault(call['id'], (number, call))
    root = project_directory(events, [c for _, c in calls.values()], None)
    for identity, (line, call) in calls.items():
        name, args = call['name'], call.get('input', {})
        result = results.get(identity)
        output = result.get('content') if result is not None else None
        record = {'line': line, 'id': identity, 'type': 'tool_call', 'tool': name,
                  'status': 'unobserved' if result is None else ('error' if result.get('is_error') else 'returned')}
        for key in ('file_path', 'path', 'pattern', 'command', 'offset', 'limit'):
            if key in args:
                record[key] = args[key]
        # Never attribute a numeric exit code to a result that did not provide one.
        yield record, output, root


def audit_records(events):
    if any(e.get('type') == 'item.completed' for e in events):
        for line, event in enumerate(events, 1):
            item = event.get('item', {})
            if event.get('type') != 'item.completed':
                continue
            kind = item.get('type')
            if kind == 'command_execution':
                keys = ('id', 'type', 'command', 'exit_code')
                yield dict(line=line, **{k: item.get(k) for k in keys}), item.get('aggregated_output'), None
            elif kind in {'file_change', 'mcp_tool_call'}:
                record = {k: v for k, v in item.items() if k not in {'result','error'}}
                record['error'] = bool(item.get('error') or (isinstance(item.get('result'), dict) and item['result'].get('isError')))
                yield dict(line=line, **record), item.get('result'), None
    else:
        yield from claude_audit(events)


def blinded_value(value, root):
    if isinstance(value, str):
        if root and root != '/__matrix_project__':
            value = value.replace(root, '<project>')
            # The orchestration workspace can contain separate input/reply directories.
            if '/work/' in root:
                value = value.replace(root.rsplit('/work/', 1)[0], '<evaluation>')
        value = re.sub(r'/(?:private/)?var/folders/[^\s"\']+?/matrix-behavior-[^/\s"\']+', '<project>', value)
        return re.sub(r'(?i)matrix-ai[ /-]v?0\.\d+(?:\.\d+)?', 'Matrix-AI <version>', value)
    if isinstance(value, list):
        return [blinded_value(item, root) for item in value]
    if isinstance(value, dict):
        return {k: blinded_value(item, root) for k, item in value.items()}
    return value


def write_tool_audit(trace, target):
    """Build audit and return files from raw traces of either runner."""
    raw = trace.read_bytes()
    events = [json.loads(line) for line in raw.splitlines() if line.strip()]
    summary, outputs = [], []
    for record, output, root in audit_records(events):
        view = blinded_value(record, root)
        view['output_chars'] = len(output) if isinstance(output, str) else None
        summary.append(view)
        if output is not None:
            outputs.append({'line': record['line'], 'id': record.get('id'), 'output': blinded_value(output, root)})
    output_path = target.with_name(target.stem.replace('-tools', '-tool-outputs') + '.json')
    output_path.write_text(json.dumps(outputs, ensure_ascii=False) + '\n', encoding='utf-8')
    audit = dict(raw_sha256=hashlib.sha256(raw).hexdigest(), events=summary, outputs_file=output_path.name,
                 trace_status='available' if summary else 'no_observed_tool_events',
                 limitation='Audit of recorded operations. Paths and kit-version strings are masked. Missing tool results are unobserved. Verify persisted state in artifacts and readback.')
    target.write_text(json.dumps(audit, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')


def blind(a):
    cases = criteria()
    ids = list(cases) if a.cases == 'all' else a.cases.split(',')
    rng = random.Random(a.seed)
    labels = {}
    for cid in ids:
        sides = ['baseline', 'candidate']
        rng.shuffle(sides)
        labels[cid] = {'X': sides[0], 'Y': sides[1]}
        for letter, side in labels[cid].items():
            source = Path(a.baseline if side == 'baseline' else a.candidate)
            target = Path(a.workspace) / cid / letter
            target.mkdir(parents=True, exist_ok=True)
            for reply in sorted(source.glob(cid + '-[0-9]*.md')):
                shutil.copy2(reply, target / reply.name)
            for trace in sorted(source.glob(cid + '-[0-9]*.jsonl')):
                write_tool_audit(trace, target / (trace.stem + '-tools.json'))
            if (source / (cid + '-artifacts')).is_dir():
                shutil.copytree(source / (cid + '-artifacts'), target / (cid + '-artifacts'), dirs_exist_ok=True)
    Path(a.labels).write_text(json.dumps(labels, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    print(len(labels), 'cases blinded')


def merge(a):
    labels = json.loads(Path(a.labels).read_text(encoding='utf-8'))
    cases, out = criteria(), {}
    for cid, v in load(a.scores).items():
        side = labels[cid]
        entry = {side['X']: v['X'], side['Y']: v['Y'], 'observations': v.get('observations', ''), 'flags': v.get('flags', [])}
        for s in ('baseline', 'candidate'):
            if (not set(entry[s]) <= set(cases[cid])) if a.partial else set(entry[s]) != set(cases[cid]):
                raise SystemExit(f'{cid}: criteria of {s} differ from the suite')
        out[cid] = entry
    Path(a.out).write_text(json.dumps(out, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    print(len(out), 'cases merged')


def needs_recheck(case):
    """The criteria a second scorer must score: the ones that decide the gate or a new mechanism, and flagged ones."""
    b, c = case['baseline'], case['candidate']
    return sorted({k for k in c if c[k] == 0 or c[k] < b[k] or (b[k] == 0 and c[k] == 1)} | set(case.get('flags', [])))


def recheck(a):
    out = {cid: needs_recheck(v) for cid, v in load(a.scores).items()}
    out = {cid: ks for cid, ks in out.items() if ks}
    Path(a.out).write_text(json.dumps(out, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    print(sum(len(v) for v in out.values()), 'criteria in', len(out), 'cases to re-check')


def replies(cid, items):
    """Reply hashes of one side in turn order, from files on disk or from comparison evidence entries."""
    turn = lambda name: int(re.fullmatch(re.escape(cid) + r'-(\d+)\.md', name).group(1))
    if isinstance(items, (str, Path)):
        files = [p for p in Path(items).glob(cid + '-*.md') if re.fullmatch(re.escape(cid) + r'-\d+\.md', p.name)]
        return [hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(files, key=lambda p: turn(p.name))]
    found = [i for i in items if re.fullmatch(re.escape(cid) + r'-\d+\.md', Path(i['path']).name)]
    return [i['sha256'] for i in sorted(found, key=lambda i: turn(Path(i['path']).name))]


def carry(a):
    previous = json.loads(Path(a.previous).read_text(encoding='utf-8'))
    digest = hashlib.sha256(Path(a.previous).read_bytes()).hexdigest()
    out, todo = {}, []
    for cid in criteria():
        case = previous['cases'].get(cid)
        same = case and all(replies(cid, d) and replies(cid, d) == replies(cid, case[s + '_evidence'])
                            for s, d in (('baseline', a.baseline), ('candidate', a.candidate)))
        if same:
            out[cid] = {k: case[k] for k in ('baseline', 'candidate', 'observations', 'flags', 'rechecked', 'rescored') if k in case}
            out[cid]['carried_from'] = {'path': str(a.previous), 'sha256': digest,
                                        'replies': {s: replies(cid, case[s + '_evidence']) for s in ('baseline', 'candidate')}}
        else:
            todo.append(cid)
    Path(a.out).write_text(json.dumps(out, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    print(json.dumps({'carried': len(out), 'to_score': todo}, ensure_ascii=False))


def combine(a):
    first, second = load(a.first), load(a.second)
    listed = json.loads(Path(a.recheck).read_text(encoding='utf-8'))
    out, agreed, total = {}, 0, 0
    for cid, keys in listed.items():
        rows = {}
        for k in keys:
            one = {s: first[cid][s][k] for s in ('baseline', 'candidate')}
            two = {s: second[cid][s][k] for s in ('baseline', 'candidate')}
            rows[k] = {'first': one, 'second': two, 'agree': one == two}
            total += 1
            agreed += one == two
        out[cid] = rows
    summary = {'rechecked': total, 'agreed': agreed, 'to_person': total - agreed}
    Path(a.out).write_text(json.dumps({'summary': summary, 'cases': out}, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    print(json.dumps(summary))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest='command', required=True)
    b = sub.add_parser('blind'); b.add_argument('--baseline', required=True); b.add_argument('--candidate', required=True)
    b.add_argument('--cases', required=True); b.add_argument('--workspace', required=True); b.add_argument('--labels', required=True)
    b.add_argument('--seed', type=int)
    m = sub.add_parser('merge'); m.add_argument('--labels', required=True); m.add_argument('--scores', nargs='+', required=True)
    m.add_argument('--out', required=True); m.add_argument('--partial', action='store_true')
    r = sub.add_parser('recheck'); r.add_argument('--scores', nargs='+', required=True); r.add_argument('--out', required=True)
    k = sub.add_parser('carry'); k.add_argument('--previous', required=True); k.add_argument('--baseline', required=True)
    k.add_argument('--candidate', required=True); k.add_argument('--out', required=True)
    c = sub.add_parser('combine'); c.add_argument('--first', nargs='+', required=True); c.add_argument('--second', nargs='+', required=True)
    c.add_argument('--recheck', required=True); c.add_argument('--out', required=True)
    args = p.parse_args()
    {'blind': blind, 'merge': merge, 'recheck': recheck, 'carry': carry, 'combine': combine}[args.command](args)
