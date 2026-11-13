#!/usr/bin/env python3
"""Report installed Markdown character budgets and direct local links; not token billing."""
import argparse,json,re,posixpath
from pathlib import Path
from production import guidance_budget

def report(kit):
 rows=[]
 for p in sorted(kit.rglob('*.md')):
  rel=p.relative_to(kit).as_posix();limit=guidance_budget(rel)
  if limit is None:continue
  text=p.read_text();routes=[]
  for link in re.findall(r'\]\(([^)]+)\)',text):
   path=link.split('#')[0]
   if path and '://' not in path and not path.startswith('mailto:'):
    dest=posixpath.normpath(posixpath.join(posixpath.dirname(rel),path))
    if dest.endswith('.md') and (kit/dest).is_file():routes.append(dest)
  rows.append(dict(path=rel,characters=len(text),budget=limit,over_budget=len(text)>limit,direct_routes=sorted(set(routes))))
 return dict(metric='Unicode characters, not tokens or fees',files=rows,total_characters=sum(r['characters'] for r in rows),over_budget=sum(r['over_budget'] for r in rows))
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--kit',type=Path,required=True);a=p.parse_args();print(json.dumps(report(a.kit.resolve()),ensure_ascii=False,indent=2))
