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
  combine  --first FILE [FILE ...] --second FILE [FILE ...] --recheck FILE --out FILE
           Compare the two scorers on the listed criteria. Agreements stand; disagreements go to a person, whose
           decision is recorded as a rescoring with the person's words. Prints the agreement counts.
"""
import argparse, json, random, shutil
from pathlib import Path

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
    c = sub.add_parser('combine'); c.add_argument('--first', nargs='+', required=True); c.add_argument('--second', nargs='+', required=True)
    c.add_argument('--recheck', required=True); c.add_argument('--out', required=True)
    args = p.parse_args()
    {'blind': blind, 'merge': merge, 'recheck': recheck, 'combine': combine}[args.command](args)
