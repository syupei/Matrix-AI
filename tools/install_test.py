#!/usr/bin/env python3
"""Verify a built Matrix-AI kit in isolated new and previously installed projects."""

import argparse
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile


BEGIN = '<!-- matrix-ai:begin -->'
END = '<!-- matrix-ai:end -->'
HOSTS = (('.agents/skills', 'AGENTS.md'), ('.claude/skills', 'CLAUDE.md'))


def install(kit, target, *options):
    result = subprocess.run(
        [sys.executable, '-B', str(kit / 'install.py'), '--target', str(target), *options],
        capture_output=True, text=True, check=False,
    )
    output = json.loads(result.stdout) if result.stdout.strip().startswith('{') else {'raw': result.stdout + result.stderr}
    return result.returncode, output


def snapshot(root):
    return {path.relative_to(root): path.read_bytes() for path in root.rglob('*') if path.is_file()}


def expected_stages(kit):
    """Read the shipped professional declarations independently of the stage gate."""
    stages = {}
    for registry in sorted((kit / 'matrix/professions').glob('*/profession.json')):
        declarations = json.loads(registry.read_text(encoding='utf-8')).get('stage_flows', [])
        for flow in declarations:
            key = flow['key']
            if key in stages:
                raise ValueError(f'duplicate stage flow: {key}')
            stages[key] = [*flow['stages'], 'complete']
    if not stages:
        raise ValueError('the kit contains no declared stage flows')
    return stages


def installed_stages(target):
    path = target / 'matrix/base/tools/stage_gate.py'
    spec = importlib.util.spec_from_file_location('installed_stage_gate', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.STAGES


def fresh_install(kit, manifest, stages, skills_dir, entry):
    skills = sorted({path.split('/')[2] for path in manifest['files'] if path.startswith('.agents/skills/')})
    body = '业务成果，不应被改动\n'
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        entry_path = root / entry
        entry_path.write_text('# 我的项目\n\n项目自己的说明。\n', encoding='utf-8')
        business = root / 'product/00-工作状态.md'
        business.parent.mkdir()
        business.write_text(body, encoding='utf-8')
        options = ('--skills-dir', skills_dir, '--entry', entry)
        before = snapshot(root)
        preview_code, preview = install(kit, root, *options)
        preview_unchanged = snapshot(root) == before
        apply_code, applied = install(kit, root, *options, '--apply')
        installed = snapshot(root)
        repeat_code, repeated = install(kit, root, *options, '--apply')
        repeat_unchanged = snapshot(root) == installed

        text = entry_path.read_text(encoding='utf-8')
        start, end = text.find(BEGIN), text.find(END)
        block = text[start:end + len(END)] if 0 <= start < end else ''
        profession_script = root / skills_dir / 'matrix-profession-builder/scripts/profession_check.py'
        checked = subprocess.run([sys.executable, '-B', str(profession_script)], capture_output=True, check=False)
        receipt_path = root / 'management/install-receipt.json'
        receipt = json.loads(receipt_path.read_text(encoding='utf-8')) if receipt_path.is_file() else {}
        gate_path = root / 'matrix/base/tools/stage_gate.py'
        return {
            'preview changes nothing': preview_code == 0 and preview.get('dry_run') is True and preview_unchanged,
            'install succeeds': apply_code == 0 and applied.get('installed') is True,
            'all skills installed': bool(skills) and all((root / skills_dir / name / 'SKILL.md').is_file() for name in skills),
            'total entry and registries installed': (root / 'matrix/base/MATRIX.md').is_file()
                and len(list((root / 'matrix/professions').glob('*/profession.json'))) >= 7,
            'rules only under matrix/, no project data there': not (root / 'collaboration').exists()
                and not any((root / 'matrix' / name).exists() for name in ('shared', 'management', 'exchange')),
            'skill names follow matrix-<profession>': all(name.startswith('matrix-') for name in skills),
            'entry block written once, within 1,200 characters': text.count(BEGIN) == text.count(END) == 1 and 0 < len(block) <= 1200,
            'entry links use the skills dir': f'({skills_dir}/matrix-profession-builder/SKILL.md)' in block,
            'project text kept': '项目自己的说明。' in text,
            'business file untouched': business.is_file() and business.read_text(encoding='utf-8') == body,
            'profession check passes in the project': checked.returncode == 0,
            'stage gate reads registries': gate_path.is_file() and installed_stages(root) == stages,
            'repeat is no-op': repeat_code == 0 and repeated.get('written') == [] and repeat_unchanged,
            'receipt names the package': receipt.get('package') == manifest['package'],
        }


def refused_upgrade(kit, earlier):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / 'AGENTS.md').write_text('# 我的项目\n', encoding='utf-8')
        old_code, _ = install(earlier, root, '--apply')
        before = snapshot(root)
        preview_code, preview = install(kit, root)
        apply_code, applied = install(kit, root, '--apply')
        return {
            'installed for the test': old_code == 0,
            'refused in preview': preview_code != 0,
            'refused in apply': apply_code != 0,
            'refusal names another release': all(
                'another release' in result.get('error', '') and 'new projects only' in result.get('error', '')
                for result in (preview, applied)),
            'refused project unchanged': snapshot(root) == before,
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('new_kit', type=Path)
    parser.add_argument('earlier_kit', type=Path, nargs='*')
    args = parser.parse_args()
    kit = args.new_kit.resolve()
    manifest = json.loads((kit / 'MANIFEST.json').read_text(encoding='utf-8'))
    stages = expected_stages(kit)
    results = [(directory, fresh_install(kit, manifest, stages, directory, entry)) for directory, entry in HOSTS]
    results.extend((earlier.name, refused_upgrade(kit, earlier.resolve())) for earlier in args.earlier_kit)
    for label, checks in results:
        for name, passed in checks.items():
            print(f'{"PASS" if passed else "FAIL"} {label}: {name}')
    return 0 if all(passed for _, checks in results for passed in checks.values()) else 1


if __name__ == '__main__':
    raise SystemExit(main())
