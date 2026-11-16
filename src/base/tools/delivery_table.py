"""Validate a single-chat handoff and render its user-facing Markdown table."""

import argparse
import json
from pathlib import Path, PurePosixPath
from urllib.parse import quote


def render(project, rows, required, professions):
    if not isinstance(rows, list) or not rows:
        raise ValueError('交付清单需要至少一行')
    lines = ['| 专业全名 | 实际采用的要求 | 成果链接 |', '| --- | --- | --- |']
    seen = set()
    for index, row in enumerate(rows, 1):
        if not isinstance(row, dict):
            raise ValueError(f'第 {index} 行应为对象')
        role, requirement, file = (row.get(k) for k in ('profession', 'requirement', 'file'))
        if not isinstance(role, str) or role not in professions:
            raise ValueError(f'第 {index} 行 profession 必须是登记的专业 ID')
        if not isinstance(requirement, str) or not requirement.strip():
            raise ValueError(f'第 {index} 行须写明实际采用的要求')
        if not isinstance(file, str) or not file.strip():
            raise ValueError(f'第 {index} 行须给出成果文件')
        relative = PurePosixPath(file)
        actual = (project / file).resolve()
        if (relative.is_absolute() or '..' in relative.parts or '\\' in file
                or not actual.is_relative_to(project) or not actual.is_file()):
            raise ValueError(f'第 {index} 行成果须为项目内已存在的相对文件：{file}')
        requirement = ' '.join(requirement.split()).replace('|', r'\|')
        label = relative.name.replace('[', r'\[').replace(']', r'\]').replace('|', r'\|')
        lines.append(f'| {professions[role]} | {requirement} | [{label}]({quote(file)}) |')
        seen.add(role)
    if missing := set(required) - seen:
        raise ValueError('缺少已交付的专业行：' + '、'.join(sorted(missing)))
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest', type=Path)
    parser.add_argument('--project', type=Path, default=Path.cwd())
    parser.add_argument('--require', action='append', default=[])
    args = parser.parse_args()
    try:
        registry = Path(__file__).resolve().parents[2] / 'professions'
        professions = {}
        for path in registry.glob('*/profession.json'):
            record = json.loads(path.read_text(encoding='utf-8'))
            professions[record['id']] = record['name']
        print(render(args.project.resolve(), json.loads(args.manifest.read_text(encoding='utf-8')),
                     args.require, professions))
    except (ValueError, OSError, KeyError) as error:
        parser.exit(1, f'{error}\n')


if __name__ == '__main__':
    main()
