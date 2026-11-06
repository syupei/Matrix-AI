#!/usr/bin/env python3
"""Check profession registries against the profession spec (matrix/base/PROFESSION-SPEC.md §4).

Checks every registry in matrix/professions/, prints one line per problem and exits 1
when any is found. --suite also checks that the evaluation cases named in the registries exist.
Passing means the files are complete and consistent, not that the profession works well:
its evaluations still have to pass."""
import argparse
import json
import re
from pathlib import Path
import importlib.util

HERE = Path(__file__).resolve().parent
SKILLS = HERE.parents[1]
ROOT = HERE.parents[3]
CLASSES = ['调度', '定义', '制作', '保障与审查']
TEXT = ['id', 'name', 'class', 'version', 'kit', 'participation', 'verification', 'reporting']
LISTS = ['skills', 'handles', 'not_handles', 'standards', 'tools', 'model_capabilities']
LEVEL = re.compile(r'^T([1-9])$')
ABBR = re.compile(r'^[A-Z]{1,3}$')
ROW = re.compile(r'^\|\s*T(\d+)\s*\|(.*)\|\s*$')
BUDGET = {'SKILL.md': 3500, 'GUIDANCE-INDEX.md': 1500, 'level doc': 3000, 'shared index': 2500}

spec = importlib.util.spec_from_file_location('build_entry', HERE / 'build_entry.py')
entry = importlib.util.module_from_spec(spec)
spec.loader.exec_module(entry)


def links(path, problems, name):
    for href in re.findall(r'\]\(([^)]+)\)', path.read_text(encoding='utf-8')):
        target = href.split('#')[0]
        if target and '://' not in target and not (path.parent / target).exists():
            problems.append(f'{name}: broken link {href}')


def level_doc(doc, low, high, problems, name):
    text = doc.read_text(encoding='utf-8')
    if len(text) > BUDGET['level doc']:
        problems.append(f'{name}: {doc.name} exceeds {BUDGET["level doc"]} characters')
    rows = {}
    for line in text.splitlines():
        m = ROW.match(line.strip())
        if m:
            cells = [c.strip() for c in m.group(2).split('|')]
            rows.setdefault(int(m.group(1)), []).append(cells)
    for n in range(low, high + 1):
        found = rows.get(n, [])
        if len(found) != 1 or len(found[0]) != 3 or not all(found[0]):
            problems.append(f'{name}: level table needs one row for T{n} with 能做, 能判断 and 不能做')
    for n in rows:
        if not low <= n <= high:
            problems.append(f'{name}: level table has T{n} outside the declared range')
    for title, prefix in [('**风险对照**', 'F'), ('**缺陷对照**', 'Q')]:
        if title not in text:
            problems.append(f'{name}: missing section {title}')
            continue
        section = text.split(title, 1)[1].split('**缺陷对照**', 1)[0]
        missing = [f'{prefix}{n}' for n in range(6) if f'{prefix}{n}' not in section]
        if missing:
            problems.append(f'{name}: {title} does not cover {", ".join(missing)}')
    links(doc, problems, name)


def registry(path, problems, owners, flows, abbrs):
    name = path.parent.name + '/' + path.name
    try:
        r = json.loads(path.read_text(encoding='utf-8'))
    except ValueError as e:
        problems.append(f'{name}: not valid JSON ({e})')
        return None
    if r.get('schema') != 'profession/1':
        problems.append(f'{name}: schema must be profession/1')
    for key in TEXT:
        if not isinstance(r.get(key), str) or not r[key].strip():
            problems.append(f'{name}: {key} must be non-empty text')
    for key in LISTS:
        if not isinstance(r.get(key), list) or not r[key] or not all(isinstance(x, str) and x.strip() for x in r[key]):
            problems.append(f'{name}: {key} must be a non-empty list of text')
    if r.get('id') != path.parent.name:
        problems.append(f'{name}: id must match the file name')
    if r.get('class') not in CLASSES:
        problems.append(f'{name}: class must be one of {"、".join(CLASSES)}')
    if not re.fullmatch(r'matrix-ai/\d+\.\d+', str(r.get('kit'))):
        problems.append(f'{name}: kit must name the required kit version')
    for key, fields in [('owns', ['deliverable', 'source']), ('interfaces', ['with', 'needs', 'gives'])]:
        items = r.get(key)
        if not isinstance(items, list) or not items or not all(isinstance(i, dict) and all(i.get(f) for f in fields) for i in items):
            problems.append(f'{name}: {key} must list items with {", ".join(fields)}')
    d = r.get('decisions')
    if not isinstance(d, dict) or not d.get('own') or not d.get('escalate') or not isinstance(d.get('binding'), list):
        problems.append(f'{name}: decisions needs own, escalate and binding')
    reuse = r.get('reuse')
    if not isinstance(reuse, list) or not all(isinstance(x, str) and x.strip() for x in reuse) \
            or (r.get('class') in ['定义', '制作'] and not reuse):
        problems.append(f'{name}: reuse must list the reuse units (required for 定义 and 制作)')
    if not isinstance(r.get('inputs', []), list):
        problems.append(f'{name}: inputs must be a list')
    items = r.get('item_inputs') or {}
    if items.get('default', 'by_risk') != 'by_risk' or not all(
            isinstance(s, dict) and s.get('item') and s.get('state') == 'confirmed' for s in items.get('stricter', [])):
        problems.append(f'{name}: item_inputs may only make the risk default stricter (state confirmed)')
    evals = r.get('evals')
    cases = evals if isinstance(evals, list) else [c for v in (evals or {}).values() for c in v] if isinstance(evals, dict) else []
    if not cases or not all(isinstance(c, str) and c for c in cases):
        problems.append(f'{name}: evals must name the evaluation cases')
    if not isinstance(r.get('stage_flows'), list):
        problems.append(f'{name}: stage_flows must be a list (empty when the profession has no stage gate)')
    abbr = r.get('abbr')
    if abbr is not None:
        if not isinstance(abbr, str) or not ABBR.match(abbr):
            problems.append(f'{name}: abbr must be one to three capital letters')
        elif abbr in abbrs:
            problems.append(f'{name}: abbr {abbr} already used by {abbrs[abbr]}')
        else:
            abbrs[abbr] = name
    elif r.get('stage_flows'):
        problems.append(f'{name}: abbr is required when the profession has stages')
    code = re.compile('^' + re.escape(str(abbr)) + r'-[1-9][0-9]*(?:\.[1-9][0-9]*)?$')
    for flow in r.get('stage_flows') or []:
        key, stages = flow.get('key'), flow.get('stages')
        if not key or key in flows:
            problems.append(f'{name}: stage flow key missing or duplicated: {key}')
            continue
        if not isinstance(stages, list) or not stages or len(set(stages)) != len(stages):
            problems.append(f'{name}: stage flow {key} needs distinct stages')
            continue
        if not all(isinstance(s, str) and code.match(s) for s in stages):
            problems.append(f'{name}: stage codes in {key} must look like {abbr}-1 or {abbr}-1.1')
        if not set(flow.get('review', [])) <= set(stages):
            problems.append(f'{name}: stage flow {key} reviews a stage it does not have')
        flows[key] = (name, flow)

    for skill in r.get('skills') or []:
        if skill in owners:
            problems.append(f'{name}: skill {skill} already belongs to {owners[skill]}')
        owners[skill] = name
        folder = SKILLS / skill
        for file in ['SKILL.md', 'GUIDANCE-INDEX.md']:
            p = folder / file
            if not p.is_file():
                problems.append(f'{name}: {skill}/{file} not found')
            elif len(p.read_text(encoding='utf-8')) > BUDGET[file]:
                problems.append(f'{name}: {skill}/{file} exceeds {BUDGET[file]} characters')
        index = folder / 'GUIDANCE-INDEX.md'
        if index.is_file() and f'professions/{path.parent.name}/levels.md' not in index.read_text(encoding='utf-8'):
            problems.append(f'{name}: {skill}/GUIDANCE-INDEX.md must link the level table professions/{path.parent.name}/levels.md')

    levels = r.get('levels') or {}
    rng = levels.get('range')
    if not isinstance(rng, list) or len(rng) != 2 or not all(LEVEL.match(str(x)) for x in rng) or int(rng[0][1]) > int(rng[1][1]):
        problems.append(f'{name}: levels.range must be two levels within T1–T9, low to high')
        return r
    low, high = int(rng[0][1]), int(rng[1][1])
    master = levels.get('master_min')
    if master is not None and (not LEVEL.match(str(master)) or not low <= int(master[1]) <= high):
        problems.append(f'{name}: levels.master_min must be null or inside the range')
    doc = path.parent / str(levels.get('doc'))
    anchors = r.get('anchors') or {}
    if not levels.get('doc') or not doc.is_file():
        problems.append(f'{name}: levels.doc not found')
    else:
        level_doc(doc, low, high, problems, name)
    for key in ['risk', 'defect']:
        if not anchors.get(key) or not (path.parent / anchors[key]).is_file():
            problems.append(f'{name}: anchors.{key} not found')
    return r


def check(root=ROOT, suite=None):
    root = Path(root)
    professions = root / 'matrix/professions'
    problems, owners, flows, abbrs, found = [], {}, {}, {}, []
    for path in sorted(professions.glob('*/profession.json')):
        r = registry(path, problems, owners, flows, abbrs)
        if r:
            found.append(r)
    if not found:
        problems.append('no registries found in matrix/professions/')
    for key, (name, flow) in flows.items():
        for stage, target in (flow.get('upstream') or {}).items():
            if stage not in flow['stages'] or not isinstance(target, list) or len(target) != 2 \
                    or target[0] not in flows or target[1] not in flows[target[0]][1]['stages']:
                problems.append(f'{name}: stage flow {key} has an invalid upstream for {stage}')
    stages = {r['id']: {s for f in r.get('stage_flows') or [] for s in f.get('stages') or []} for r in found}
    for r in found:
        own = stages[r['id']] | {o.get('deliverable') for o in r.get('owns') or [] if isinstance(o, dict)}
        for i in r.get('inputs') or []:
            prof, _, stage = str(i.get('needs', '')).partition(':') if isinstance(i, dict) else ('', '', '')
            if not isinstance(i, dict) or i.get('for') not in own or stage not in stages.get(prof, set()) \
                    or i.get('state') not in ('confirmed', 'complete') or i.get('kind', 'start') not in ('start', 'complete'):
                problems.append(f'{r["id"]}/profession.json: invalid input {i}')
    ranks = [f['authority_rank'] for _, f in flows.values() if 'authority_rank' in f]
    if len(ranks) != len(set(ranks)):
        problems.append('authority_rank values must be distinct')
    if suite:
        ids = {c['id'] for c in json.loads(Path(suite).read_text(encoding='utf-8'))['cases']}
        for r in found:
            evals = r.get('evals')
            for case in (evals if isinstance(evals, list) else [c for v in evals.values() for c in v]):
                if case not in ids:
                    problems.append(f'{r["id"]}/profession.json: evaluation case {case} not in the suite')
    shared = root / 'matrix/base/GUIDANCE-INDEX.md'
    if shared.is_file() and len(shared.read_text(encoding='utf-8')) > BUDGET['shared index']:
        problems.append(f'matrix/base/GUIDANCE-INDEX.md exceeds {BUDGET["shared index"]} characters')
    try:
        text, new = entry.build(root)
        if text != new:
            problems.append('matrix/base/MATRIX.md is out of date; run build_entry.py')
    except (OSError, ValueError, KeyError) as e:
        problems.append(f'matrix/base/MATRIX.md: {e}')
    return problems


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--root', type=Path, default=ROOT, help='project root that holds matrix/')
    p.add_argument('--suite', type=Path, help='evaluation suite JSON with a "cases" list')
    a = p.parse_args()
    problems = check(a.root, a.suite)
    print('\n'.join(problems) if problems else 'all registries pass')
    return 1 if problems else 0


if __name__ == '__main__':
    raise SystemExit(main())
