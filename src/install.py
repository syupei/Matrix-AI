#!/usr/bin/env python3
"""Preserving installer for the professional-agents kit.

Installs the skills and shared collaboration rules into a project, adds or
updates one managed entry block in the project's instruction file(s), retires
unmodified files from earlier releases, and never touches business outputs.
Run without --apply first to preview.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import tempfile
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent
PKG_SKILLS = '.agents/skills/'
BEGIN = '<!-- professional-agents:begin -->'
END = '<!-- professional-agents:end -->'
LEGACY_MARKERS = [('<!-- pm-agent-test:begin -->', '<!-- pm-agent-test:end -->')]
# Entry text written by earlier standalone kits; reported for manual review, never removed.
LEGACY_HEADINGS = ['# 产品与设计联合试验入口', '# 产品 Agent 试验项目', '<!-- professional-agent-collaboration:begin -->']
ROLES = ['project-management-agent', 'product-agent', 'experience-design-agent',
         'engineering-intake-agent', 'professional-agent-collaboration', 'content-design-review']
# Shared rules that every role depends on: a custom copy must be merged by hand first.
CRITICAL_COMMON = ['collaboration/CORE.md', 'collaboration/USER-INTERACTION.md',
                   'collaboration/PM-REPORTING.md', 'collaboration/COPY-QUALITY.md',
                   'collaboration/STRUCTURED-HANDOFF.md']
BLOCK_TEMPLATE = BEGIN + '''
## 专业 Agent（{package}）

按当前任务选择一个角色并读取它的 skill，不要同时加载所有角色。每个角色启动时先读 [collaboration/CORE.md](collaboration/CORE.md)。

| 任务 | 角色 |
| --- | --- |
| 项目统筹、进度、调度、全流程续做 | [project-management-agent]({skills}/project-management-agent/SKILL.md) |
| 新产品需求；产品阶段续做；产品事实、规则、范围问题 | [product-agent]({skills}/product-agent/SKILL.md) |
| 承接产品基线做空间、交互、视觉设计；设计续做与设计问题 | [experience-design-agent]({skills}/experience-design-agent/SKILL.md) |
| 研发第一阶段：需求承接、澄清与逻辑工程建模 | [engineering-intake-agent]({skills}/engineering-intake-agent/SKILL.md) |
| 跨角色问询、唤醒与接续 | [professional-agent-collaboration]({skills}/professional-agent-collaboration/SKILL.md) |

产品与设计撰写或审读文案时使用 [content-design-review]({skills}/content-design-review/SKILL.md)；需要能力模型原文时查 [product-capability-model]({skills}/product-capability-model/SKILL.md)。安装本包不代表任何 Agent 已在运行；用户当前的明确要求优先于这里的默认安排。
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
    """Replace the managed block (current or legacy markers) or prepend a new one."""
    for begin, end in [(BEGIN, END), *LEGACY_MARKERS]:
        if begin in content or end in content:
            if content.count(begin) != 1 or content.count(end) != 1 or content.index(begin) > content.index(end):
                raise ValueError('malformed managed block')
            return content[:content.index(begin)] + new_block.rstrip('\n') + content[content.index(end) + len(end):]
    return new_block + '\n' + content


def install(target, apply=False, skills_dir='.agents/skills', entries=('AGENTS.md',)):
    root = Path(target).resolve()
    if not root.is_dir():
        raise ValueError('target project must exist')
    skills_dir = check_skills_dir(skills_dir)
    entries = [check_entry(e) for e in (entries or ['AGENTS.md'])]
    bases = json.loads((ROOT / 'upgrade-bases.json').read_text())
    manifest = json.loads((ROOT / 'MANIFEST.json').read_text())
    guidance_keys = {PKG_SKILLS + r + '/GUIDANCE-INDEX.md' for r in ROLES}
    plans, preserved, guidance, retire, retired_kept, legacy = [], [], [], [], [], []

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
        outside = updated.replace(new_block.rstrip('\n'), '')
        legacy += [f'{entry}: {h}' for h in LEGACY_HEADINGS if h in outside]
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
              'guidance_review_required': guidance, 'retired_modified_kept': retired_kept,
              'legacy_entry_review': legacy}
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
