#!/usr/bin/env python3
"""Compare the product skill's first-round intake form with the guides it duplicates (rule evaluation P6).

The form (assets/initial-intake-form.html) carries its own copy of the I01–I13 items: importance, basis and the
latest stage to resolve each, and the tone and visual-style presets. The guides (references/initial-intake.md,
references/style-options.md) are the formal source. This checks that the two agree on what a program can compare:
  - the same item IDs in the form's fieldsets, the form's data and the guide's coverage table;
  - the importance class (must / conditional / optional) of each item;
  - the capability codes cited as basis;
  - the product stages (P-n) named as the latest point to resolve;
  - the tone and visual-style presets (the form's extra choices such as "AI 帮你选" are allowed).

Usage: check_intake_form.py [<skill folder>]   (default: the publishing source)
Prints one line per difference and exits 1 when there is any."""
import re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / 'src/professions/product/skills/matrix-product'
FORM_ONLY = {'跟随现有品牌', '自定义', 'AI 帮你选', '无偏好', '暂不决定'}


def importance(text):
    """The first importance class a text names: must, conditional or optional. Later words describe exceptions,
    e.g. "可选；有强制术语时转为条件" is optional."""
    hits = [(text.find(word), cls) for word, cls in (('必须', 'must'), ('条件', 'conditional'), ('可选', 'optional')) if word in text]
    return min(hits)[1] if hits else None


def check(skill):
    form = (skill / 'assets/initial-intake-form.html').read_text(encoding='utf-8')
    guide = (skill / 'references/initial-intake.md').read_text(encoding='utf-8')
    styles = (skill / 'references/style-options.md').read_text(encoding='utf-8')
    problems = []

    fieldsets = re.findall(r'<fieldset data-id="(I\d\d)"', form)
    if len(fieldsets) != len(set(fieldsets)):
        problems.append("duplicate form fieldset IDs")
    data = {m.group(1): m.group(2) for m in re.finditer(r"^\s*(I\d\d):\{(.*)\},?$", form, re.M)}
    table = {}
    for line in guide.splitlines():
        m = re.match(r'\|\s*(I\d\d)\s+[^|]*\|([^|]*)\|([^|]*)\|([^|]*)\|', line)
        if m:
            table[m.group(1)] = (m.group(2), m.group(3), m.group(4))
    for name, ids in (('form fieldsets', set(fieldsets)), ('form data', set(data)), ('guide table', set(table))):
        for other, oids in (('guide table', set(table)),):
            if name != other and ids != oids:
                problems.append(f'IDs differ: {name} has {sorted(ids - oids)} extra, {sorted(oids - ids)} missing')

    for iid in sorted(set(data) & set(table)):
        spec, (imp, basis, latest) = data[iid], table[iid]
        level = re.search(r"level:'([^']*)'", spec).group(1)
        if importance(level) != importance(imp):
            problems.append(f'{iid} importance: form "{level}", guide "{imp.strip()[:30]}"')
        fb = set(re.findall(r"'(P\d-\d+)'", spec))
        gb = set(re.findall(r'P\d-\d+', basis))
        if fb != gb:
            problems.append(f'{iid} basis: form {sorted(fb)}, guide {sorted(gb)}')
        fs = set(re.findall(r'P-\d', re.search(r"resolve_by:'([^']*)'", spec).group(1)))
        gs = set(re.findall(r'P-\d', latest))
        if fs != gs:
            problems.append(f'{iid} latest stage: form {sorted(fs)}, guide {sorted(gs)}')

    for group, heading in (('tone', '## 文案语气'), ('style', '## 视觉风格')):
        m = re.search(group + r":\{label:'[^']*',options:\[([^\]]*)\]", form)
        options = set(re.findall(r"'([^']*)'", m.group(1))) if m else set()
        section = styles.split(heading, 1)[1].split('\n## ', 1)[0] if heading in styles else ''
        presets = {row.split('|')[1].strip() for row in section.splitlines()
                   if row.startswith('|') and not row.startswith('| ---') and row.split('|')[1].strip() not in ('预设',)}
        if presets - options:
            problems.append(f'{group} presets missing from the form: {sorted(presets - options)}')
        if options - presets - FORM_ONLY:
            problems.append(f'{group} options in the form but not in the guide: {sorted(options - presets - FORM_ONLY)}')

    return problems


def main():
    problems = check(SKILL)
    for problem in problems:
        print(problem)
    print(f"{len(problems)} difference(s)")
    return 1 if problems else 0


if __name__ == '__main__':
    raise SystemExit(main())
