#!/usr/bin/env python3
"""One-time 0.31 restructure: move the source into layers, rename skills, and rewrite references.

The mapping it applies is written to tools/layout-0.31.json, the record of this restructure.
Usage: restructure_031.py [--apply]   (without --apply: print the plan and the problems only)
"""
import json, os, posixpath, re, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'src'
ROOT_FILES = {'START.md', 'BEHAVIOR-CHECKS.md', 'install.py'}
DROP = {'upgrade-bases.json'}

RULES = {
    'base': ['CORE', 'USER-INTERACTION', 'GUIDANCE-INDEX', 'GUIDANCE-RESOLUTION', 'LEVELS', 'RISK-DEFECT-LEVELS', 'CONTRACT',
             'REQUEST-RESPONSE-TEMPLATE', 'TOPICS', 'FEEDBACK-PROTOCOL', 'TASK-PACKET', 'STAGE-GATES', 'PROFESSIONAL-REVIEW',
             'DELEGATED-REVIEW', 'PROFESSION-SPEC', 'MATRIX', 'COPY-QUALITY'],
    'orchestration': ['PM-REPORTING', 'PM-INTEGRITY', 'PM-INTEGRITY-TOOLS', 'INSTANCES', 'TEAM', 'TEAM-EXECUTION', 'TEAM-LEAD',
                      'TEAM-WORKER', 'TEAM-RUNTIME', 'RUNTIME', 'TOOL-ACCESS', 'ROLE-CONFIG-TEMPLATE'],
    'professions/code-engineering': ['ENGINEERING-FLOW', 'SECURITY', 'PERFORMANCE', 'OPERATIONS'],
    'professions/product': ['PRODUCT-EXPERIENCE', 'CONTENT-READINESS', 'STRUCTURED-HANDOFF'],
}
TOOLS = {'stage_gate.py': 'base', 'delegation_gate.py': 'base', 'review.html': 'base',
         'task_dispatch.py': 'orchestration', 'tool_gateway.py': 'orchestration'}
# old skill -> (layer folder in src, new name)
SKILLS = {
    'project-front-desk-agent': ('orchestration', 'matrix-front-desk'),
    'project-management-agent': ('orchestration', 'matrix-project-management'),
    'professional-agent-collaboration': ('orchestration', 'matrix-collaboration'),
    'product-agent': ('professions/product', 'matrix-product'),
    'content-design-review': ('professions/content-design', 'matrix-content-design'),
    'experience-design-agent': ('professions/experience-design', 'matrix-experience-design'),
    'engineering-intake-agent': ('professions/code-engineering', 'matrix-code-engineering-intake'),
    'engineering-solution-agent': ('professions/code-engineering', 'matrix-code-engineering-solution'),
    'engineering-build-agent': ('professions/code-engineering', 'matrix-code-engineering-build'),
    'quality-verification-agent': ('professions/quality-engineering', 'matrix-quality-engineering'),
    'profession-builder': ('base', 'matrix-profession-builder'),
    'product-capability-model': ('knowledge', 'matrix-product-capability-model'),
}
# Files that leave their skill: the shared task library and coordination ledger belong to orchestration.
LEAVE_SKILL = {
    'project-management-agent/scripts/pm_tasks.py': 'orchestration/tools/pm_tasks.py',
    'project-management-agent/scripts/pm_views.py': 'orchestration/tools/pm_views.py',
    'project-management-agent/scripts/pm_team.py': 'orchestration/tools/pm_team.py',
    'project-management-agent/scripts/pm_integrity.py': 'orchestration/tools/pm_integrity.py',
    'project-management-agent/references/task-runtime.md': 'orchestration/TASK-TOOL.md',
    'professional-agent-collaboration/scripts/coordination.py': 'orchestration/tools/coordination.py',
}
# Project data moves out of the rule directory (project-root paths, longest first when applied).
DATA = {
    'collaboration/runtime/state.sqlite3': 'management/runtime/coordination.sqlite3',
    'collaboration/runtime/host.md': 'management/runtime/host.md',
    'collaboration/instance-config.json': 'management/instance-config.json',
    'collaboration/model-fit.json': 'management/model-fit.json',
    'collaboration/delegations.json': 'management/delegations.json',
    'collaboration/people.json': 'management/people.json',
    'collaboration/feedback.md': 'shared/feedback.md',
    'collaboration/constraints.md': 'shared/constraints.md',
    'collaboration/requests': 'exchange/requests',
    'collaboration/runtime': 'management/runtime',
    '.agent-runtime/instances': 'management/instances',
}
DIRS = {'collaboration/professions': 'matrix/professions'}
ROLE_EXAMPLES = {'engineering-build': 'matrix-code-engineering-build', 'engineering-intake': 'matrix-code-engineering-intake'}


def new_src(old):
    if old in ROOT_FILES:
        return old
    if old in DROP:
        return None
    parts = old.split('/')
    if parts[0] == 'collaboration':
        if len(parts) == 2:
            stem = parts[1][:-3]
            for layer, names in RULES.items():
                if stem in names:
                    return layer + '/' + parts[1]
        if parts[1] == 'professions' and len(parts) == 3:
            pid, ext = parts[2].rsplit('.', 1)
            return f'professions/{pid}/' + ('profession.json' if ext == 'json' else 'levels.md')
        if parts[1] == 'tools' and len(parts) == 3:
            return TOOLS[parts[2]] + '/tools/' + parts[2]
    if parts[:2] == ['.agents', 'skills']:
        skill, rest = parts[2], '/'.join(parts[3:])
        key = skill + '/' + rest
        if key in LEAVE_SKILL:
            return LEAVE_SKILL[key]
        layer, name = SKILLS[skill]
        return f'{layer}/skills/{name}/{rest}'
    raise ValueError('no rule for ' + old)


def package(src):
    """Where a source file lands in the package, which is also where it lands in a project."""
    if src in ROOT_FILES:
        return src
    parts = src.split('/')
    if parts[0] in ('base', 'orchestration', 'knowledge') and len(parts) > 2 and parts[1] == 'skills':
        return '.agents/skills/' + '/'.join(parts[2:])
    if parts[0] == 'professions' and len(parts) > 3 and parts[2] == 'skills':
        return '.agents/skills/' + '/'.join(parts[3:])
    return 'matrix/' + src


def plan():
    old_files = subprocess.run(['git', 'ls-files', 'src'], cwd=ROOT, capture_output=True, text=True, check=True).stdout.split()
    files = {}
    for f in old_files:
        rel = f[len('src/'):]
        files[rel] = new_src(rel)
    return files


LINK = re.compile(r'(\]\()([^)\s]+)(\))')


def rewrite_links(text, old_pkg, new_pkg, old2new_pkg, old_dirs, problems, where):
    def fix(m):
        href = m.group(2)
        if '://' in href or href.startswith(('#', 'mailto:')):
            return m.group(0)
        path, _, frag = href.partition('#')
        if not path:
            return m.group(0)
        target = posixpath.normpath(posixpath.join(posixpath.dirname(old_pkg), path))
        is_dir = path.endswith('/')
        if target in old2new_pkg:
            dest = old2new_pkg[target]
        elif target in old_dirs:
            dest, is_dir = old_dirs[target], True
        else:
            problems.append(f'unresolved link in {where}: {href}')
            return m.group(0)
        rel = posixpath.relpath(dest, posixpath.dirname(new_pkg)) + ('/' if is_dir else '')
        return m.group(1) + rel + ('#' + frag if frag else '') + m.group(3)
    return LINK.sub(fix, text)


def replacements(old2new_pkg):
    pairs = []
    for old, new in old2new_pkg.items():
        if old != new:
            pairs.append((old, new))
    pairs += list(DATA.items()) + list(DIRS.items())
    pairs.sort(key=lambda p: -len(p[0]))
    rules = [(re.compile(r'(?<![\w.-])' + re.escape(o) + r'(?![\w-])'), n) for o, n in pairs]
    rules += [(re.compile(r'(?<![\w-])' + re.escape(o) + r'(?![\w-])'), n) for o, (_, n) in sorted(SKILLS.items(), key=lambda p: -len(p[0]))]
    rules += [(re.compile(r'(?<=[\'"`])' + re.escape(o) + r'(?=[\'"`])'), n) for o, n in ROLE_EXAMPLES.items()]
    rules.append((re.compile(r'(版本：[0-9.]+。)角色标识：[a-z-]+。'), r'\1'))
    return rules


TEXT = {'.md', '.py', '.json', '.html', '.yaml', '.txt'}
FACTORY = ['tests', 'evals/run.py', 'evals/assemble_run.py', 'evals/fixtures', 'tools/production.py', 'tools/release.py', 'docs']


def main(apply):
    files = plan()
    old2new_src = {o: n for o, n in files.items() if n}
    old2new_pkg = {o: package(n) for o, n in old2new_src.items()}
    old_dirs = {}
    for o, n in old2new_pkg.items():
        op, np_ = o.split('/'), n.split('/')
        while len(op) > 1 and len(np_) > 1 and op[-1] == np_[-1]:
            op, np_ = op[:-1], np_[:-1]
            od, nd = '/'.join(op), '/'.join(np_)
            if od in old_dirs and old_dirs[od] != nd:
                old_dirs[od] = None
            elif od not in old_dirs:
                old_dirs[od] = nd
    old_dirs = {k: v for k, v in old_dirs.items() if v} | DIRS
    record = {'note': 'Restructure applied for 0.31: source path -> new source path (null: removed); package paths follow tools/production.py',
              'files': files, 'skills': {o: n for o, (_, n) in SKILLS.items()}, 'data': DATA, 'dirs': DIRS}
    problems = []
    new_texts = {}
    for old, new in old2new_src.items():
        p = SRC / old
        if p.suffix in ('.md', '.html'):
            text = p.read_text(encoding='utf-8')
            text = rewrite_links(text, old, old2new_pkg[old], old2new_pkg, old_dirs, problems, old)
            new_texts[old] = text
    print(json.dumps({'files': len(files), 'moved': sum(1 for o, n in files.items() if n and n != o), 'dropped': [o for o, n in files.items() if not n],
                      'problems': problems[:40], 'problem_count': len(problems)}, ensure_ascii=False, indent=1))
    if not apply:
        return
    (ROOT / 'tools/layout-0.31.json').write_text(json.dumps(record, ensure_ascii=False, indent=1) + '\n')
    for old, new in files.items():
        if new is None:
            subprocess.run(['git', 'rm', '-q', 'src/' + old], cwd=ROOT, check=True)
            continue
        if new != old:
            (SRC / new).parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(['git', 'mv', 'src/' + old, 'src/' + new], cwd=ROOT, check=True)
        if old in new_texts:
            (SRC / new).write_text(new_texts[old], encoding='utf-8')
    rules = replacements(old2new_pkg)
    targets = [p for p in SRC.rglob('*') if p.is_file() and p.suffix in TEXT]
    for f in FACTORY:
        q = ROOT / f
        targets += [p for p in q.rglob('*') if p.is_file() and p.suffix in TEXT] if q.is_dir() else [q]
    changed = 0
    for p in targets:
        text = p.read_text(encoding='utf-8')
        out = text
        for rx, new in rules:
            out = rx.sub(new, out)
        if out != text:
            p.write_text(out, encoding='utf-8')
            changed += 1
    for d in sorted((p for p in SRC.rglob('*') if p.is_dir()), key=lambda p: -len(p.parts)):
        if not any(d.iterdir()):
            d.rmdir()
    print('text files changed:', changed)


if __name__ == '__main__':
    main('--apply' in sys.argv)
