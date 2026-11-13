#!/usr/bin/env python3
"""Resume preserved synthetic acceptance after a fixture/runner fix; never rerun completed model work."""
import argparse,importlib.util,json,shutil,uuid,hashlib
from pathlib import Path


def load(name,path):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m


def main():
 p=argparse.ArgumentParser();p.add_argument('--previous',type=Path,required=True);p.add_argument('--kit',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
 previous,kit,out=a.previous.resolve(),a.kit.resolve(),a.out.resolve()
 if out.exists():raise ValueError('new evidence directory required')
 out.mkdir(parents=True);root=out/'project';shutil.copytree(previous/'project',root)
 # Persist the original before applying the new kit in the new test directory.
 shutil.rmtree(root/'matrix');shutil.copytree(kit/'matrix',root/'matrix')
 tools=root/'matrix/orchestration/tools';pm=load('resume_pm',tools/'pm_tasks.py');worker=load('resume_worker',tools/'reference_worker.py')
 def call(op,actor='PM',**params):return pm.execute(root,dict(op=op,actor=actor,event_id='RESUME-'+uuid.uuid4().hex,**params))
 def task(tid):return next((t for t in pm.execute(root,{'op':'status'})['tasks'] if t['id']==tid),None)
 if task('P')['state']!='done':
  if task('P')['state']=='planned':
   result=worker.execute(root,'controller',timeout=240);(out/'product-result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
   if not result.get('handed'):raise ValueError('product did not hand over')
  t=task('P');text='\n'.join((root/r).read_text() for r in t['evidence'])
  if not all(k in text for k in ['SYNTHETIC-REQ-17','message','created_at','费用']):raise ValueError('product candidate does not retain supplied facts')
  call('review','SIM-checker',task_id='P',expected_revision=t['revision'],outcome='passed',criteria_checked=t['criteria'],evidence=['Program checked exact synthetic input facts in actual artifacts; no professional quality certification'])
  call('transition',task_id='P',expected_revision=task('P')['revision'],state='done',reason='Synthetic fixture acceptance of preserved input facts only')
 t=task('E')
 if t is None:
  call('create',task=dict(id='E',title='SYNTHETIC downstream',owner='code-engineering-001',executor='code-engineering-001',checker='SIM-checker',goal='只核对产品候选，写 handoff-check.md：SYNTHETIC-REQ-17、message、created_at、费用待定；不开发、不改变产品决定。',inputs=task('P')['evidence'],dependencies=['P'],outputs=['本实例公有候选'],criteria=['保留已给输入和未决项'],next_action='核对当前产品交接版本'))
 elif not t['dependencies']:
  call('update',t['owner'],task_id='E',expected_revision=t['revision'],changes={'dependencies':['P']},reason='Synthetic downstream version check',scope_authorization='SIM fixture definition: downstream E consumes accepted P')
 if task('E')['state']=='planned':
  result=worker.execute(root,'controller',timeout=240);(out/'downstream-result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
  if not result.get('handed'):raise ValueError('downstream did not hand over')
 t=task('E');text='\n'.join((root/r).read_text() for r in t['evidence'])
 if not all(k in text for k in ['SYNTHETIC-REQ-17','message','created_at','费用']):raise ValueError('downstream lost product facts')
 (out/'status.json').write_text(json.dumps(pm.execute(root,{'op':'status'}),ensure_ascii=False,indent=2))
 (out/'summary.json').write_text(json.dumps(dict(passed=True,previous=str(previous),kit_sha256=hashlib.sha256((kit/'MANIFEST.json').read_bytes()).hexdigest(),reused='prior completed admission and product runs only; original evidence preserved',limitation='synthetic integration, no business approval or professional certification'),ensure_ascii=False,indent=2))
 print(json.dumps({'passed':True,'out':str(out)}))
if __name__=='__main__':main()
