#!/usr/bin/env python3
"""Preserving installer for Matrix-AI.

Installs the skills into the host's skills directory and the rules and tools
into matrix/, adds or updates one managed entry block in the project's
instruction file(s), and never touches project data or business outputs. Each
release is for new projects only: a project that has any other release
installed is refused, not upgraded or migrated. Run without --apply first to
preview.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent
PKG_SKILLS = '.agents/skills/'
PKG_RULES = 'matrix/'
BEGIN = '<!-- matrix-ai:begin -->'
END = '<!-- matrix-ai:end -->'
# A project with any other release installed is refused (each release is for new projects only).
KIT_VERSION = re.compile(r'(?:professional-agents-kit|matrix-ai)/(\d+)\.(\d+)')
# Entry text and rule files written by earlier kits, including the professional-agents line before Matrix-AI.
LEGACY_MARKERS = ['<!-- professional-agents:begin -->', '<!-- pm-agent-test:begin -->', '# 产品与设计联合试验入口',
                  '# 产品 Agent 试验项目', '<!-- professional-agent-collaboration:begin -->']
LEGACY_FILES = ['collaboration/CORE.md', 'collaboration/MATRIX.md', 'shared/stage_gate.py']
ROLES = ['matrix-front-desk', 'matrix-project-management', 'matrix-product', 'matrix-experience-design',
         'matrix-code-engineering-intake', 'matrix-code-engineering-solution', 'matrix-code-engineering-build', 'matrix-quality-engineering',
         'matrix-collaboration', 'matrix-content-design', 'matrix-profession-builder']
# Shared rules that every role depends on: a custom copy must be merged by hand first.
CRITICAL_COMMON = ['matrix/base/CORE.md', 'matrix/base/USER-INTERACTION.md',
                   'matrix/orchestration/PM-REPORTING.md', 'matrix/base/COPY-QUALITY.md',
                   'matrix/professions/product/STRUCTURED-HANDOFF.md', 'matrix/orchestration/TEAM.md']
BLOCK_TEMPLATE = BEGIN + '''
## 专业 Agent（{package}）

按任务选一个角色，读它的 SKILL.md，不同时加载所有角色；专业目录、选专业与单对话用法见 [总入口](matrix/base/MATRIX.md)。

| 任务 | 角色 |
| --- | --- |
| 主对话：问询、转交、启动引导 | [matrix-front-desk]({skills}/matrix-front-desk/SKILL.md) |
| 项目统筹与调度 | [matrix-project-management]({skills}/matrix-project-management/SKILL.md) |
| 产品 | [matrix-product]({skills}/matrix-product/SKILL.md) |
| 用户看到的文字 | [matrix-content-design]({skills}/matrix-content-design/SKILL.md) |
| 交互与视觉设计 | [matrix-experience-design]({skills}/matrix-experience-design/SKILL.md) |
| 代码工程 E-1：承接与建模 | [matrix-code-engineering-intake]({skills}/matrix-code-engineering-intake/SKILL.md) |
| 代码工程 E-2：方案与骨架 | [matrix-code-engineering-solution]({skills}/matrix-code-engineering-solution/SKILL.md) |
| 代码工程 E-3–4：构建与发布 | [matrix-code-engineering-build]({skills}/matrix-code-engineering-build/SKILL.md) |
| 质量工程 | [matrix-quality-engineering]({skills}/matrix-quality-engineering/SKILL.md) |
| 新建或修改专业 | [matrix-profession-builder]({skills}/matrix-profession-builder/SKILL.md) |

跨专业的请求与接续、能力标准原文由各角色按需调用。安装本包不代表任何 Agent 已在运行。
''' + END + '\n'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def block(package, skills_dir):
    return BLOCK_TEMPLATE.format(package=package, skills=skills_dir)


def check_skills_dir(value):
    parts = Path(value).parts
    if Path(value).is_absolute() or len(parts) != 2 or any(p in ('.', '..') for p in parts):
        raise ValueError('skills dir must be a relative path of exactly two levels, e.g. .agents/skills or .claude/skills')
    return '/'.join(parts)


def check_entry(value):
    p = Path(value)
    if p.is_absolute() or len(p.parts) != 1 or p.suffix.lower() != '.md':
        raise ValueError('entry must be a Markdown file in the project root, e.g. AGENTS.md or CLAUDE.md')
    return value


def safe(root, rel):
    p = root / rel
    if Path(rel).is_absolute() or '..' in Path(rel).parts or not p.resolve().is_relative_to(root):
        raise ValueError('unsafe destination: ' + str(rel))
    for node in [p, *p.parents]:
        if node == root:
            break
        if node.is_symlink():
            raise ValueError('symlink destination: ' + str(rel))
        if node != p and node.exists() and not node.is_dir():
            raise ValueError('parent is not a directory: ' + str(node))
    if p.exists() and not p.is_file():
        raise ValueError('destination is not file: ' + str(rel))
    return p


def atomic(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.pa-install-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(data)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def managed(rel):
    return rel.startswith(PKG_SKILLS) or rel.startswith(PKG_RULES)


def target_path(rel, skills_dir):
    return skills_dir + '/' + rel[len(PKG_SKILLS):] if rel.startswith(PKG_SKILLS) else rel


def update_entry(content, new_block):
    """Replace the managed block or prepend a new one."""
    if BEGIN in content or END in content:
        if content.count(BEGIN) != 1 or content.count(END) != 1 or content.index(BEGIN) > content.index(END):
            raise ValueError('malformed managed block')
        return content[:content.index(BEGIN)] + new_block.rstrip('\n') + content[content.index(END) + len(END):]
    return new_block + '\n' + content


def other_release(root, package):
    """What shows that a release other than this one, or an earlier kit, is installed."""
    found = []
    receipt = root / 'management/install-receipt.json'
    if receipt.is_file() and not receipt.is_symlink():
        installed = str(json.loads(receipt.read_text()).get('package', ''))
        if installed != package:
            found.append('management/install-receipt.json: ' + (installed or 'unknown package'))
    for entry in sorted(root.glob('*.md')):
        if not entry.is_file() or entry.is_symlink():
            continue
        text = entry.read_text(errors='replace')
        if BEGIN in text and END in text and text.index(BEGIN) < text.index(END):
            for m in KIT_VERSION.finditer(text[text.index(BEGIN):text.index(END)]):
                if m[0] != package:
                    found.append(f'{entry.name}: {m[0]}')
        found += [f'{entry.name}: {marker}' for marker in LEGACY_MARKERS if marker in text]
    found += [rel for rel in LEGACY_FILES if (root / rel).exists()]
    return found


def install(target, apply=False, skills_dir='.agents/skills', entries=('AGENTS.md',)):
    root = Path(target).resolve()
    if not root.is_dir():
        raise ValueError('target project must exist')
    skills_dir = check_skills_dir(skills_dir)
    entries = [check_entry(e) for e in (entries or ['AGENTS.md'])]
    manifest = json.loads((ROOT / 'MANIFEST.json').read_text())
    other = other_release(root, manifest['package'])
    if other:
        raise ValueError('another release is installed (' + '; '.join(other) + '); this release is for new projects '
                         'only and does not upgrade or migrate them')
    guidance_keys = {PKG_SKILLS + r + '/GUIDANCE-INDEX.md' for r in ROLES} | {'matrix/base/GUIDANCE-INDEX.md'}
    plans, preserved, guidance = [], [], []

    for rel, expected in sorted(manifest['files'].items()):
        if not managed(rel):
            continue
        data = (ROOT / rel).read_bytes()
        if sha(data) != expected:
            raise ValueError('package hash mismatch: ' + rel)
        dest_rel = target_path(rel, skills_dir)
        dest = safe(root, dest_rel)
        before = dest.read_bytes() if dest.exists() else None
        if before == data:
            continue
        if before is not None:
            if rel in guidance_keys:
                guidance.append(dest_rel)
                continue
            if rel.startswith(PKG_RULES) and rel not in CRITICAL_COMMON:
                preserved.append(dest_rel)
                continue
            raise ValueError('custom/unknown existing file requires merge before install: ' + dest_rel)
        plans.append((dest_rel, before, data))

    package = manifest['package']
    new_block = block(package, skills_dir)
    for entry in entries:
        dest = safe(root, entry)
        before = dest.read_bytes() if dest.exists() else None
        content = (before or b'').decode()
        updated = update_entry(content, new_block)
        if updated.encode() != before:
            plans.append((entry, before, updated.encode()))

    # Validate every destination before any mutation.
    for rel, before, _ in plans:
        if before is not None:
            backup = safe(root, 'management/install-backups/' + sha(before) + '/' + rel)
            if backup.exists() and backup.read_bytes() != before:
                raise ValueError('backup conflict: ' + rel)
    safe(root, 'management/install-receipt.json')
    report = {'package': package, 'target': str(root), 'skills_dir': skills_dir, 'entries': entries,
              'preserved_custom_common': preserved, 'preserved_custom_guidance': guidance,
              'guidance_review_required': guidance}
    if not apply:
        return {'dry_run': True, 'changes': [x[0] for x in plans], **report}

    written = []
    for rel, before, data in plans:
        dest = safe(root, rel)
        current = dest.read_bytes() if dest.exists() else None
        if current != before:
            raise ValueError('concurrent edit; earlier writes kept, rerun preflight: ' + rel)
        if before is not None:
            backup = safe(root, 'management/install-backups/' + sha(before) + '/' + rel)
            if not backup.exists():
                atomic(backup, before)
        atomic(dest, data)
        written.append({'path': rel, 'before': sha(before) if before is not None else None, 'after': sha(data)})
    result = {'installed': True, 'at': datetime.now(timezone.utc).isoformat(), 'written': written,
              **report, 'runtime_initialized': False,
              'professional_business_sources_modified': False,
              'note': 'Per-file atomic and rerunnable; not a project-wide transaction. Runtime and adoption are verified separately.'}
    receipt = safe(root, 'management/install-receipt.json')
    if written or not receipt.exists():
        atomic(receipt, json.dumps(result, ensure_ascii=False, indent=2).encode())
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--target', required=True, help='project root')
    p.add_argument('--apply', action='store_true', help='write changes (default: preview only)')
    p.add_argument('--skills-dir', default='.agents/skills',
                   help='where the host discovers project skills, e.g. .agents/skills or .claude/skills')
    p.add_argument('--entry', action='append',
                   help='instruction file that receives the managed entry block; repeatable (default AGENTS.md)')
    args = p.parse_args()
    try:
        print(json.dumps(install(args.target, args.apply, args.skills_dir, args.entry or ['AGENTS.md']),
                         ensure_ascii=False, indent=2))
    except (ValueError, OSError, KeyError) as e:
        print(json.dumps({'error': str(e)}, ensure_ascii=False))
        raise SystemExit(1)
