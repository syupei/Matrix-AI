#!/usr/bin/env python3
"""Retest the unchanged failed admission prompt after restoring a source constraint.

Leaves the new package awaiting validation; an actual artifact review must produce
the three-part validation report before expert.validate / enable are called.
"""
import argparse,importlib.util,json,shutil,uuid,hashlib
from pathlib import Path


def load(name,path):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m


def main():
 p=argparse.ArgumentParser();p.add_argument('--previous',type=Path,required=True);p.add_argument('--kit',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
 old,kit,out=a.previous.resolve(),a.kit.resolve(),a.out.resolve()
 if out.exists():raise ValueError('preserve old evidence; use new output')
 out.mkdir(parents=True);root=out/'project';shutil.copytree(old/'project',root);shutil.rmtree(root/'matrix');shutil.copytree(kit/'matrix',root/'matrix')
 tools=root/'matrix/orchestration/tools';api=load('repair_api',tools/'platform_api.py');boundary=load('repair_boundary',tools/'isolated_runner.py')
 def call(op,**params):
  u=uuid.uuid4().hex;r=api.handle(root,dict(protocol=api.SPEC,request_id=u,event_id=u,project_id='SIM-V033',op=op,params=params),'controller')
  with (out/'events.jsonl').open('a') as f:f.write(json.dumps({'op':op,'result':r},ensure_ascii=False)+'\n')
  if not r['ok']:raise ValueError(r)
  return r['result']
 # The earlier controller scope predates the explicit disable operation. This is a
 # synthetic fixture configuration update, not production authorization.
 cfg=json.loads((root/api.CONFIG).read_text());cfg['principals']['controller']['operations']=sorted(api.OPERATIONS)
 (root/api.CONFIG).write_text(json.dumps(cfg,ensure_ascii=False,indent=2)+'\n')
 call('expert.disable',id='imported-product',version='1',reason='Actual admission output expanded anonymous into unapproved login/account/data-collection decisions; preserve failed package')
 identity={'id':'imported-product','version':'2'}
 call('expert.prepare',**identity,profession='product',url='https://github.com/syupei/Matrix-AI.git',commit='bd65c5ff854c1f272b18e21e86abcba769d0dfdf',subdir='src/professions/product/skills/matrix-product')
 prior=root/'experts/imported-product/1';base=root/'experts/imported-product/2'
 source=(base/'source/SKILL.md').read_text()
 constraint=next(line for line in source.splitlines() if line.startswith('1. 一句话需求'))
 methods=(prior/'METHODS.md').read_text()+'\n## 保留原专家的确认边界\n\n'+constraint+'\n仅把原话明确给出的信息列为已定。推断、建议与未知项分别标注；不得把推断变成人的决定。\n'
 review=json.loads((prior/'REVIEW.json').read_text());review.pop('unresolved',None);review['preserved_methods']+='；补回原SKILL硬关卡1，旧失败与差异保留'
 call('expert.adapt',**identity,methods=methods,review=review)
 target=root/'management/instances/ADMISSION-V2/workspace/public/admission.md'
 prompt='这是合成准入测试。请读取 '+str(base/'ENTRY.md')+' 和 '+str(base/'METHODS.md')+'。按该专业方法为已明确要求的留言板写一段候选说明：匿名留言、费用未定。保留费用未定，不开发。只写 '+str(target)+'，完成即退出。'
 runner=cfg['runners']['default'];model=next(iter(runner['models'].values()));argv=[x.replace('{model}',model) for x in runner.get('argv',[])]
 result=boundary.run(root,'ADMISSION-V2',argv,prompt,180,adapter=runner.get('adapter','kernel'),model=model)
 (out/'admission.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
 (out/'review-pending.json').write_text(json.dumps(dict(package=identity,model=model,kit_sha256=hashlib.sha256((kit/'MANIFEST.json').read_bytes()).hexdigest(),methods_sha256=hashlib.sha256((base/'METHODS.md').read_bytes()).hexdigest(),artifact=str(target.relative_to(root)),exit_code=result['exit_code'],professional_review='pending actual read',previous=str(old)),ensure_ascii=False,indent=2))
 print(json.dumps({'exit_code':result['exit_code'],'artifact_exists':target.is_file(),'review':'pending'}))
if __name__=='__main__':main()
