#!/usr/bin/env python3
"""Generate the profession directory in matrix/base/MATRIX.md from the registries.

Run after adding or changing a profession. --check only reports whether the directory
matches the registries (exit 1 when it does not)."""
import argparse
import json
from pathlib import Path

BEGIN, END = '<!-- professions:begin -->', '<!-- professions:end -->'
CLASSES = ['调度', '定义', '制作', '保障与审查']
# scripts/ -> matrix-profession-builder/ -> skills dir -> host dir -> project root
ROOT = Path(__file__).resolve().parents[4]


def directory(professions):
    registries = [json.loads(p.read_text(encoding='utf-8')) for p in sorted(Path(professions).glob('*/profession.json'))]
    for r in registries:
        if r.get('class') not in CLASSES:
            raise ValueError('unknown class in registry: ' + str(r.get('id')))
    registries.sort(key=lambda r: (CLASSES.index(r['class']), r['id']))
    rows = ['| 专业 | 类别 | 处理什么 | 何时参与 | 技能 |', '| --- | --- | --- | --- | --- |']
    for r in registries:
        cells = [f"[{r['name']}](../professions/{r['id']}/{r['levels']['doc']})", r['class'], '；'.join(r['handles']),
                 r['participation'], '、'.join(f'`{s}`' for s in r['skills'])]
        rows.append('| ' + ' | '.join(c.replace('|', '\\|') for c in cells) + ' |')
    return '\n'.join(rows)


def render(text, table):
    if text.count(BEGIN) != 1 or text.count(END) != 1 or text.index(BEGIN) > text.index(END):
        raise ValueError('MATRIX.md needs exactly one professions block')
    return text[:text.index(BEGIN) + len(BEGIN)] + '\n' + table + '\n' + text[text.index(END):]


def build(root=ROOT):
    """Return (current text, regenerated text) of the total entry."""
    matrix = Path(root) / 'matrix/base/MATRIX.md'
    text = matrix.read_text(encoding='utf-8')
    return text, render(text, directory(Path(root) / 'matrix/professions'))


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--root', type=Path, default=ROOT, help='project root that holds matrix/')
    p.add_argument('--check', action='store_true', help='report only; do not write')
    a = p.parse_args()
    text, new = build(a.root)
    if a.check:
        print('MATRIX.md is up to date' if new == text else 'MATRIX.md is out of date; run build_entry.py')
        return 0 if new == text else 1
    if new != text:
        (a.root / 'matrix/base/MATRIX.md').write_text(new, encoding='utf-8')
    print('MATRIX.md updated' if new != text else 'MATRIX.md already up to date')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
