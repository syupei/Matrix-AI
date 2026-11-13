#!/usr/bin/env python3
"""Staged real same-profession / different-package / different-model acceptance.
All appointments and task premises are synthetic; real runs and outputs are kept.
"""
import argparse,hashlib,importlib.util,json,shutil,uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


def load(name,path):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m


def main():
 p=argparse.ArgumentParser();p.add_argument('--phase',choices=['prepare','admit','run'],required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--kit',type=Path);a=p.parse_args()
 out=a.out.resolve();root=out/'project'
 if a.phase=='prepare':
  if out.exists():raise ValueError('new evidence directory required')
  out.mkdir(parents=True);root.mkdir();shutil.copytree(a.kit/'matrix',root/'matrix');shutil.copytree(a.kit/'.agents',root/'.agents')
 tools=root/'matrix/orchestration/tools';pm=load('parallel_pm',tools/'pm_tasks.py');api=load('parallel_api',tools/'platform_api.py');boundary=load('parallel_boundary',tools/'isolated_runner.py');worker=load('parallel_worker',tools/'reference_worker.py')
 def call(op,actor='PM',**kw):return pm.execute(root,dict(op=op,actor=actor,event_id='SIM-'+uuid.uuid4().hex,**kw))
 def write(ref,data):
  dest=root/ref;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
 def facade(op,**params):
  uid=uuid.uuid4().hex;r=api.handle(root,dict(protocol=api.SPEC,request_id=uid,event_id=uid,project_id='SIM-V033-PARALLEL',op=op,params=params),'controller')
  with (out/'events.jsonl').open('a') as f:f.write(json.dumps({'op':op,'response':r},ensure_ascii=False)+'\n')
  if not r['ok']:raise ValueError(r)
  return r['result']
 identity=dict(id='imported-code',version='1');base=root/'experts/imported-code/1'
 if a.phase=='prepare':
  call('init',config=dict(project='SIM-V033-PARALLEL',pm_actor='PM',authorization='user-authorized synthetic compatibility test only',frontdoor_id='SIM',max_slots=3))
  write('management/expert-professions.json',dict(schema='matrix-expert-professions/1',professions=['code-engineering'],configured_by='SIM-fixture',authorization='SIMULATED preset for test'))
  caps={k:dict(state='supported',evidence='actual native workspace-write boundary and CLI probe retained by test operator') for k in ['launch','write_isolation','model_selection','cancel']}
  write(api.CONFIG,dict(schema=api.SPEC,project_id='SIM-V033-PARALLEL',principals={'controller':dict(active=True,actor='PM',operations=sorted(api.OPERATIONS),task_ops=[])},runners={'default':dict(adapter='codex-native',version='0.167.0',models={'gpt-6-luna':'gpt-6-luna','gpt-6.1-sol':'gpt-6.1-sol'},capabilities=caps)}))
  facade('expert.prepare',**identity,profession='code-engineering',url='https://github.com/syupei/Matrix-AI.git',commit='bd65c5ff854c1f272b18e21e86abcba769d0dfdf',subdir='src/professions/code-engineering/skills/matrix-code-engineering-build')
  methods='''# 代码工程子任务专家（限定适配）
读取项目的 matrix/base/CORE.md 与 matrix/professions/code-engineering/profession.json。
只实现任务包明确给定的函数和输入输出契约；不替产品作规则决定，不接管整体工程，不安装依赖、不联网。
按原专家的增量构建方法：核对当前输入和范围，写最小模块，再做真实边界自测，交回代码、测试和残余限制；没有代码或环境则明示缺口，不编造通过。
自测不是独立验收，候选不是已采用；关键技术、费用、发布仍按 Matrix 的真实决定流程处理。
代码与测试候选只写本实例 workspace/public/，草稿只写 workspace/private/，任务状态交可信控制器。
本适配只支持独立函数子任务；原包完整集成、走查、灰度发布及运维主流程未纳入，不宣称全角色等价。
输出代码文件顶部注明来源追踪标识 SOURCE-IMPORTED-CODE，作为本次双来源隔离检查；不将它写入其他实例的成果。
'''
  facade('expert.adapt',**identity,methods=methods,review=dict(reviewer='acceptance operator',source_entry='SKILL.md',license='owned public Matrix-AI source, local authorized compatibility test only',preserved_methods='bounded incremental implementation, real tests, independent acceptance boundary and no invented product decisions; full-role orchestration excluded',directory_changes='instance private/public only',dependencies='installed Matrix shared CORE and profession contract, standard library only'))
  (out/'metadata.json').write_text(json.dumps(dict(kit=str(a.kit.resolve()),kit_sha256=hashlib.sha256((a.kit/'MANIFEST.json').read_bytes()).hexdigest(),models=['gpt-6-luna','gpt-6.1-sol'],effort='medium'),indent=2))
 elif a.phase=='admit':
  target=root/'management/instances/ADMISSION/workspace/public/admission.md'
  prompt='合成专家准入。读取 '+str(base/'ENTRY.md')+' 与 '+str(base/'METHODS.md')+'。概述本专家会怎样处理“仅实现一个已给定函数”的任务，明确未知产品规则、真实测试、独立验收与写盘位置的边界。只写 '+str(target)+'；不要实现或启动其它任务。'
  result=boundary.run(root,'ADMISSION',[],prompt,180,adapter='codex-native',model='gpt-6.1-sol')
  (out/'admission.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
  (out/'admission-pending.json').write_text(json.dumps(dict(artifact=str(target.relative_to(root)),methods_sha256=hashlib.sha256((base/'METHODS.md').read_bytes()).hexdigest(),exit_code=result['exit_code'],review='pending actual artifact read'),indent=2))
 elif a.phase=='run':
  # The operator's real review must already have enabled this package.
  pm.team.experts.binding(pm.api(),root,'code-engineering',identity)
  entries=[dict(id='builtin',profession='code-engineering',level='T7',model='gpt-6-luna',count=1,master=True,aliases=['小 M.ai']),dict(id='imported',profession='code-engineering',level='T4',model='gpt-6.1-sol',count=1,expert=identity,aliases=['小王.ai'])]
  write('management/instance-config.json',{'entries':entries});call('confirm_config',person='SIM-person',quote='SIMULATED test fixture approval only',presented_ref='SIM fixture',choices={e['id']:'acknowledge_unregistered' for e in entries})
  ids=[call('derive',entry=e['id'],endpoint='platform')['record']['id'] for e in entries]
  for tid,iid,fn,parity in [('A',ids[0],'sum_odd','奇数'),('B',ids[1],'sum_even','偶数')]:
   call('create',task=dict(id=tid,title='SIM independent '+fn,owner=ids[0],executor=iid,checker='SIM-checker',goal='只实现 Python 函数 '+fn+'(values)：输入已限定为整数列表，返回其中'+parity+'的总和，空列表返回0。代码放 candidate.py，真实自测后写 test-results.md，再通过规定 outbox 交回。不要安装依赖，不增加其它产品决定。',inputs=['SIM all function semantics explicitly provided; no product unknowns to decide'],outputs=['本实例 candidate.py 与 test-results.md'],criteria=['给定函数计算正确、实际自测、独立候选路径'],next_action='实现并真实自测指定函数'))
  facade('runtime.configure',mode='local',expected_generation=0)
  plan=facade('actions.plan');actions=plan['actions']
  if len(actions)!=2:raise ValueError('expected two independently ready actions')
  def run(action):
   for attempt in range(3):
    try:return worker.execute(root,'controller',action['action_id'],timeout=240)
    except ValueError as error:
     if 'STALE_REVISION' not in str(error) or attempt==2:raise
  with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(run,actions))
  (out/'parallel-results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2))
  (out/'status.json').write_text(json.dumps(pm.execute(root,{'op':'status'}),ensure_ascii=False,indent=2))
  if not all(r.get('handed') for r in results):raise ValueError('a parallel instance did not hand over')
  print(json.dumps({'handed':True,'results':results}))
 print(json.dumps({'phase':a.phase,'out':str(out)}))
if __name__=='__main__':main()
