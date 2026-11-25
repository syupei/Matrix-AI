#!/usr/bin/env python3
"""Check the project's shared knowledge index (shared/index.md) against matrix/base/SHARED-INDEX.md.

Prints one line per problem and exits 1 when there is any; a project without an index passes."""
import argparse, re, sys
from pathlib import Path

COLUMNS = ['编号', '内容', '位置', '负责专业', '版本或摘要', '谁能读', '对外', '含个人数据或凭证']
OUTSIDE = {'不外发', '只给摘录', '可外发'}


def rows(text):
    lines = [l.strip() for l in text.splitlines() if l.strip().startswith('|')]
    cells = [[c.strip() for c in l.strip('|').split('|')] for l in lines]
    return cells[0] if cells else [], [c for c in cells[2:]]


def check(project):
    project = Path(project).resolve()
    index = project / 'shared/index.md'
    if not index.is_file():
        return []
    professions = {p.parent.name for p in (project / 'matrix/professions').glob('*/profession.json')}
    header, body = rows(index.read_text(encoding='utf-8'))
    if header != COLUMNS:
        return ['shared/index.md: columns must be ' + ' | '.join(COLUMNS)]
    problems, seen = [], set()
    for cells in body:
        if len(cells) != len(COLUMNS):
            problems.append('shared/index.md: row with %d cells: %s' % (len(cells), ' | '.join(cells)))
            continue
        kid, _, where, owner, _, readers, outside, personal = cells
        tag = 'shared/index.md ' + kid
        if not re.fullmatch(r'K-\d{3}', kid) or kid in seen:
            problems.append(tag + ': id must be K-nnn and unique')
        seen.add(kid)
        target = (project / where).resolve()
        if not where or not target.is_relative_to(project) or not target.exists():
            problems.append(tag + ': location not found: ' + where)
        if owner not in professions:
            problems.append(tag + ': owner is not a registered profession: ' + owner)
        if readers != '全部':
            unknown = [r for r in re.split(r'[、,，]\s*', readers) if r not in professions]
            if unknown:
                problems.append(tag + ': readers not registered: ' + '、'.join(unknown))
        if outside not in OUTSIDE:
            problems.append(tag + ': 对外 must be one of ' + '、'.join(sorted(OUTSIDE)))
        if personal not in ('是', '否'):
            problems.append(tag + ': 含个人数据或凭证 must be 是 or 否')
        elif personal == '是' and outside != '不外发':
            problems.append(tag + ': items with personal data or credentials must be 不外发')
    return problems


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--project', type=Path, default=Path('.'))
    found = check(p.parse_args().project)
    print('\n'.join(found) if found else 'shared index passes')
    sys.exit(1 if found else 0)
