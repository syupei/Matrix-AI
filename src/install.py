#!/usr/bin/env python3
"""Preserving installer for the professional-agents kit.

Installs the skills and shared collaboration rules into a project, adds or
updates one managed entry block in the project's instruction file(s), retires
unmodified files from earlier releases of the same line, and never touches
business outputs. Each release is for new projects only: a project that has an
earlier release installed is refused, not upgraded or migrated. Run without
--apply first to preview.
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
BEGIN = '<!-- professional-agents:begin -->'
END = '<!-- professional-agents:end -->'
# Projects with a release before this one installed are refused (each release is for new projects only).
FIRST_RELEASE = (0, 30)
KIT_VERSION = re.compile(r'professional-agents-kit/(\d+)\.(\d+)')
# Entry text written by earlier standalone kits.
LEGACY_MARKERS = ['<!-- pm-agent-test:begin -->', '# 产品与设计联合试验入口', '# 产品 Agent 试验项目',
                  '<!-- professional-agent-collaboration:begin -->']
ROLES = ['project-front-desk-agent', 'project-management-agent', 'product-agent', 'experience-design-agent',
         'engineering-intake-agent', 'engineering-solution-agent', 'engineering-build-agent', 'quality-verification-agent',
         'professional-agent-collaboration', 'content-design-review', 'profession-builder']
# Shared rules that every role depends on: a custom copy must be merged by hand first.
CRITICAL_COMMON = ['collaboration/CORE.md', 'collaboration/USER-INTERACTION.md',
                   'collaboration/PM-REPORTING.md', 'collaboration/COPY-QUALITY.md',
                   'collaboration/STRUCTURED-HANDOFF.md', 'collaboration/TEAM.md']
BLOCK_TEMPLATE = BEGIN + '''
## 专业 Agent（{package}）

按任务选一个角色，读它的 SKILL.md，不同时加载所有角色；专业目录、选专业与单对话用法见 [总入口](collaboration/MATRIX.md)。

| 任务 | 角色 |
| --- | --- |
| 主对话：问询、转交、启动引导 | [project-front-desk-agent]({skills}/project-front-desk-agent/SKILL.md) |
| 项目统筹与调度 | [project-management-agent]({skills}/project-management-agent/SKILL.md) |
| 产品 | [product-agent]({skills}/product-agent/SKILL.md) |
| 用户看到的文字 | [content-design-review]({skills}/content-design-review/SKILL.md) |
| 交互与视觉设计 | [experience-design-agent]({skills}/experience-design-agent/SKILL.md) |
| 代码工程 E-1：承接与建模 | [engineering-intake-agent]({skills}/engineering-intake-agent/SKILL.md) |
| 代码工程 E-2：方案与骨架 | [engineering-solution-agent]({skills}/engineering-solution-agent/SKILL.md) |
| 代码工程 E-3–4：构建与发布 | [engineering-build-agent]({skills}/engineering-build-agent/SKILL.md) |
| 质量工程 | [quality-verification-agent]({skills}/quality-verification-agent/SKILL.md) |
| 新建或修改专业 | [profession-builder]({skills}/profession-builder/SKILL.md) |

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
    return rel.startswith(PKG_SKILLS) or rel.startswith('collaboration/')


def retirable(rel):
    # shared/ was installed by an earlier release line; only removal applies to it.
    return managed(rel) or rel.startswith('shared/')


def target_path(rel, skills_dir):
    return skills_dir + '/' + rel[len(PKG_SKILLS):] if rel.startswith(PKG_SKILLS) else rel


def update_entry(content, new_block):
    """Replace the managed block or prepend a new one."""
    if BEGIN in content or END in content:
        if content.count(BEGIN) != 1 or content.count(END) != 1 or content.index(BEGIN) > content.index(END):
            raise ValueError('malformed managed block')
        return content[:content.index(BEGIN)] + new_block.rstrip('\n') + content[content.index(END) + len(END):]
    return new_block + '\n' + content


def earlier_release(root):
    """What shows that a release before FIRST_RELEASE, or an earlier standalone kit, is installed."""
    found = []
    receipt = root / 'management/install-receipt.json'
    if receipt.is_file() and not receipt.is_symlink():
        package = str(json.loads(receipt.read_text()).get('package', ''))
        m = KIT_VERSION.fullmatch(package)
        if not m or (int(m[1]), int(m[2])) < FIRST_RELEASE:
            found.append('management/install-receipt.json: ' + (package or 'unknown package'))
    for entry in sorted(root.glob('*.md')):
        if not entry.is_file() or entry.is_symlink():
            continue
        text = entry.read_text(errors='replace')
        if BEGIN in text and END in text and text.index(BEGIN) < text.index(END):
            for m in KIT_VERSION.finditer(text[text.index(BEGIN):text.index(END)]):
                if (int(m[1]), int(m[2])) < FIRST_RELEASE:
                    found.append(f'{entry.name}: {m[0]}')
        found += [f'{entry.name}: {marker}' for marker in LEGACY_MARKERS if marker in text]
    return found


def install(target, apply=False, skills_dir='.agents/skills', entries=('AGENTS.md',)):
    root = Path(target).resolve()
    if not root.is_dir():
        raise ValueError('target project must exist')
    skills_dir = check_skills_dir(skills_dir)
    entries = [check_entry(e) for e in (entries or ['AGENTS.md'])]
    earlier = earlier_release(root)
    if earlier:
        raise ValueError('an earlier release is installed (' + '; '.join(earlier) + '); this release is for new projects '
                         'only and does not upgrade or migrate them')
    bases = json.loads((ROOT / 'upgrade-bases.json').read_text())
    manifest = json.loads((ROOT / 'MANIFEST.json').read_text())
    guidance_keys = {PKG_SKILLS + r + '/GUIDANCE-INDEX.md' for r in ROLES} | {'collaboration/GUIDANCE-INDEX.md'}
    plans, preserved, guidance, retire, retired_kept = [], [], [], [], []

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
        if before is not None and sha(before) not in bases.get(rel, []):
            if rel in guidance_keys:
                guidance.append(dest_rel)
                continue
            if rel.startswith('collaboration/') and rel not in CRITICAL_COMMON:
                preserved.append(dest_rel)
                continue
            raise ValueError('custom/unknown existing file requires merge before install: ' + dest_rel)
        plans.append((dest_rel, before, data))

    # Files shipped by earlier releases but no longer part of this one.
    for rel in sorted(k for k in bases if retirable(k) and k not in manifest['files']):
        dest_rel = target_path(rel, skills_dir)
        dest = safe(root, dest_rel)
        if not dest.exists():
            continue
        before = dest.read_bytes()
        if sha(before) in bases[rel]:
            retire.append((dest_rel, before))
        else:
            retired_kept.append(dest_rel)

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
    for rel, before, _ in plans + [(r, b, None) for r, b in retire]:
        if before is not None:
            backup = safe(root, 'management/install-backups/' + sha(before) + '/' + rel)
            if backup.exists() and backup.read_bytes() != before:
                raise ValueError('backup conflict: ' + rel)
    safe(root, 'management/install-receipt.json')
    report = {'package': package, 'target': str(root), 'skills_dir': skills_dir, 'entries': entries,
              'preserved_custom_common': preserved, 'preserved_custom_guidance': guidance,
              'guidance_review_required': guidance, 'retired_modified_kept': retired_kept}
    if not apply:
        return {'dry_run': True, 'changes': [x[0] for x in plans], 'retire': [x[0] for x in retire], **report}

    written, removed = [], []
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
    for rel, before in retire:
        dest = safe(root, rel)
        if dest.read_bytes() != before:
            raise ValueError('concurrent edit; earlier writes kept, rerun preflight: ' + rel)
        backup = safe(root, 'management/install-backups/' + sha(before) + '/' + rel)
        if not backup.exists():
            atomic(backup, before)
        dest.unlink()
        removed.append({'path': rel, 'before': sha(before)})
        parent = dest.parent
        while parent != root and parent.is_dir() and not any(parent.iterdir()):
            parent.rmdir()
            parent = parent.parent
    result = {'installed': True, 'at': datetime.now(timezone.utc).isoformat(), 'written': written,
              'retired': removed, **report, 'runtime_initialized': False,
              'professional_business_sources_modified': False,
              'note': 'Per-file atomic and rerunnable; not a project-wide transaction. Runtime and adoption are verified separately.'}
    receipt = safe(root, 'management/install-receipt.json')
    if written or removed or not receipt.exists():
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
