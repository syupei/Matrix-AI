"""Fixture state follows the kit under test.

Fixtures build project state in the Matrix-AI layout. When the kit under test (root/'kit') is from before
Matrix-AI, adapt() moves that data to the places the earlier kit reads and rewrites the paths in the text files
written (paths and skill names), so every kit sees the same state where it expects it. In the task library the paths
are rewritten in the event log, the instance and configuration records and the tasks' next actions; fields that bind
checks and reviews are left alone."""
import importlib.util
import json
import re
import shutil
import sqlite3
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
# Matrix-AI project path -> path used by kits before Matrix-AI (longest first).
LEGACY = [
    ('management/runtime/coordination.sqlite3', 'collaboration/runtime/state.sqlite3'),
    ('management/runtime/host.md', 'collaboration/runtime/host.md'),
    ('management/instance-config.json', 'collaboration/instance-config.json'),
    ('management/model-fit.json', 'collaboration/model-fit.json'),
    ('management/delegations.json', 'collaboration/delegations.json'),
    ('management/people.json', 'collaboration/people.json'),
    ('management/instances', '.agent-runtime/instances'),
    ('shared/feedback.md', 'collaboration/feedback.md'),
    ('shared/constraints.md', 'collaboration/constraints.md'),
    ('exchange', 'collaboration'),
]
# Skill names before Matrix-AI, for the text a fixture writes (for example who owns a work state).
NAMES = {
    'matrix-code-engineering-solution': 'engineering-solution-agent',
    'matrix-product-capability-model': 'product-capability-model',
    'matrix-code-engineering-intake': 'engineering-intake-agent',
    'matrix-code-engineering-build': 'engineering-build-agent',
    'matrix-quality-engineering': 'quality-verification-agent',
    'matrix-project-management': 'project-management-agent',
    'matrix-profession-builder': 'profession-builder',
    'matrix-experience-design': 'experience-design-agent',
    'matrix-content-design': 'content-design-review',
    'matrix-collaboration': 'professional-agent-collaboration',
    'matrix-front-desk': 'project-front-desk-agent',
    'matrix-product': 'product-agent',
}
_PACKAGE = None


def candidate():
    """The candidate package built from this repository's source (once per process): fixtures use its tools."""
    global _PACKAGE
    if _PACKAGE is None:
        spec = importlib.util.spec_from_file_location('fixture_production', REPO / 'tools/production.py')
        prod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(prod)
        _PACKAGE, _, _ = prod.build(Path(tempfile.mkdtemp(prefix='matrix-fixture-kit-')))
    return _PACKAGE


def tool(name):
    spec = importlib.util.spec_from_file_location('fixture_' + name, candidate() / 'matrix/orchestration/tools' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def legacy(root):
    manifest = Path(root) / 'kit' / 'MANIFEST.json'
    return manifest.is_file() and not json.loads(manifest.read_text(encoding='utf-8'))['package'].startswith('matrix-ai/')


def adapt(root):
    root = Path(root)
    if not legacy(root):
        return
    for new, old in LEGACY:
        source, target = root / new, root / old
        if not source.exists():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.is_dir():
            shutil.copytree(source, target, dirs_exist_ok=True)
            shutil.rmtree(source)
        else:
            shutil.move(str(source), str(target))
    rules = [(re.compile(r'(?<![\w.-])' + re.escape(new) + r'(?![\w-])'), old) for new, old in LEGACY]
    rules += [(re.compile(r'(?<![\w-])' + re.escape(new) + r'(?![\w-])'), old) for new, old in NAMES.items()]
    for path in root.rglob('*'):
        rel = path.relative_to(root)
        if rel.parts[0] == 'kit' or not path.is_file() or path.suffix not in ('.md', '.json', '.txt'):
            continue
        text = path.read_text(encoding='utf-8')
        out = text
        for rx, old in rules:
            out = rx.sub(old, out)
        if out != text:
            path.write_text(out, encoding='utf-8')
    paths = rules[:len(LEGACY)]

    def fix(text):
        for rx, old in paths:
            text = rx.sub(old, text)
        return text
    db = root / 'management/runtime/tasks.sqlite3'
    if db.is_file():
        con = sqlite3.connect(db)
        for table in ('events', 'pm_records'):
            columns = [c[1] for c in con.execute(f'PRAGMA table_info("{table}")') if c[2].upper() == 'TEXT']
            for row in con.execute(f'SELECT rowid, {", ".join(columns)} FROM "{table}"').fetchall():
                values = [fix(v) if isinstance(v, str) else v for v in row[1:]]
                if values != list(row[1:]):
                    con.execute(f'UPDATE "{table}" SET ' + ', '.join(c + ' = ?' for c in columns) + ' WHERE rowid = ?', [*values, row[0]])
        for tid, data in con.execute('SELECT id, data FROM tasks').fetchall():
            task = json.loads(data)
            if isinstance(task.get('next_action'), str) and fix(task['next_action']) != task['next_action']:
                task['next_action'] = fix(task['next_action'])
                con.execute('UPDATE tasks SET data = ? WHERE id = ?', (json.dumps(task, ensure_ascii=False, sort_keys=True, separators=(',', ':')), tid))
        con.commit()
        con.close()
    for d in sorted((p for p in root.rglob('*') if p.is_dir() and 'kit' not in p.relative_to(root).parts[:1]), key=lambda p: -len(p.parts)):
        if not any(d.iterdir()):
            d.rmdir()
