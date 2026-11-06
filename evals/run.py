#!/usr/bin/env python3
"""Run fixed multi-turn skill probes with an actual local agent CLI (Codex or Claude Code).
Results are ungraded raw evidence; no canned response is treated as model behavior.
"""
import argparse,hashlib,json,os,re,shutil,subprocess,tempfile,time,importlib.util
from pathlib import Path

def fingerprint(root):
 return hashlib.sha256(json.dumps({str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(root.rglob('*')) if p.is_file() and '__pycache__' not in p.parts and p.name!='MANIFEST.json'},sort_keys=True).encode()).hexdigest()

def main():
 p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--case');p.add_argument('--runner',choices=['codex','claude'],default='codex');p.add_argument('--model');p.add_argument('--effort');args=p.parse_args()
 suite_path=Path(__file__).parent/'cases/suite.json';suite=json.loads(suite_path.read_text());args.output.mkdir(parents=True,exist_ok=True)
 source=args.source.resolve();meta={'source_hash':fingerprint(source),'suite_hash':hashlib.sha256(suite_path.read_bytes()).hexdigest(),'runner':{'codex':'codex exec','claude':'claude -p'}[args.runner],'cli_version':subprocess.check_output([args.runner,'--version'],text=True).strip(),'model':args.model,'effort':args.effort,'cases':[]}
 for case in suite['cases']:
  if args.case and case['id']!=args.case:continue
  with tempfile.TemporaryDirectory(prefix='matrix-behavior-') as d:
   work=Path(d);shutil.copytree(source,work/'kit',ignore=shutil.ignore_patterns('__pycache__'))
   # Keep the same conditions and user turns for both revisions; history is actual output.
   roles=case['role'] if isinstance(case['role'],list) else [case['role']]
   role=next((r for r in roles if (source/'.agents/skills'/r/'SKILL.md').is_file()),roles[-1])
   # A case may start from a kit entry file instead of one skill: the first entry present in the tested kit is used.
   entry=next((e for e in case.get('entry',[]) if (source/e).is_file()),None)
   history=[];record={'id':case['id'],'role':role,'turns':[]}|({'entry':entry} if entry else {})
   if case.get('fixture'):
    fixture=Path(__file__).parent/'fixtures'/(case['fixture']+'.py')
    if fixture.parent.resolve()!=(Path(__file__).parent/'fixtures').resolve():raise ValueError('invalid fixture')
    digest=hashlib.sha256(fixture.read_bytes()).hexdigest()
    if case.get('fixture_sha256')!=digest:raise ValueError('fixture changed; update suite')
    fspec=importlib.util.spec_from_file_location('fixed_fixture',fixture);fmod=importlib.util.module_from_spec(fspec);fspec.loader.exec_module(fmod)
    fmod.populate(work.resolve(),case['id']);record['fixture_sha256']=digest
   for n,user in enumerate(case['turns']):
    start=f'kit/{entry}' if entry else f'kit/.agents/skills/{role}/SKILL.md'
    prompt=f"在此临时项目中使用 {start} 处理用户请求。读取所需本地规则。仅在此目录写本轮必要成果，不访问外部业务项目、不联网、不启动其他Agent。这里没有可用原生提问控件，使用技能允许的回退方式。只处理当前用户输入，等真实下一条消息，不替用户回答。\n"
    if history:prompt+='此前真实对话：\n'+json.dumps(history,ensure_ascii=False)+'\n'
    prompt+='用户：'+user
    last=args.output/(case['id']+f'-{n}.md');events=args.output/(case['id']+f'-{n}.jsonl');err=args.output/(case['id']+f'-{n}.stderr')
    if args.runner=='codex':
     cmd=['codex','exec','--skip-git-repo-check','--ephemeral','--sandbox','workspace-write','--json','-C',str(work),'-o',str(last.resolve())]
     cmd+=(['-m',args.model] if args.model else [])+(['-c','model_reasoning_effort="'+args.effort+'"'] if args.effort else [])+['-']
    else:
     cmd=['claude','-p','--output-format','stream-json','--verbose','--permission-mode','acceptEdits']
    started=time.time()
    with events.open('w') as stdout,err.open('w') as stderr:
     result=subprocess.run(cmd,input=prompt,text=True,stdout=stdout,stderr=stderr,timeout=480,cwd=str(work))
    if args.runner=='claude' and not result.returncode:
     final=[e for e in (json.loads(l) for l in events.read_text().splitlines() if l.strip()) if e.get('type')=='result']
     if final and not final[-1].get('is_error'):last.write_text(final[-1].get('result',''))
    if result.returncode or not last.exists():raise RuntimeError(f'Actual model run failed: {case["id"]}; see {err}')
    reply=last.read_text();history.extend([{'role':'user','text':user},{'role':'assistant','text':reply}])
    record['turns'].append({'user':user,'reply':last.name,'events':events.name,'seconds':round(time.time()-started,2),'sha256':hashlib.sha256(last.read_bytes()).hexdigest()})
    print(case['id'],n,'completed',flush=True)
   # The kit files this case read, from its traces: its reply may be carried over later only while they are unchanged.
   # A trace that changes into the kit folder reads by relative paths that cannot be told apart, so it records none.
   traces=''.join((args.output/t['events']).read_text(errors='ignore') for t in record['turns'])
   kit_files=json.loads((source/'MANIFEST.json').read_text())['files']
   record['read_files']=None if re.search(r'cd\s+["\']?(\./)?kit\b',traces) else sorted(f for f in kit_files if 'kit/'+f in traces)
   artifacts=args.output/(case['id']+'-artifacts');artifacts.mkdir(exist_ok=True)
   for item in work.iterdir():
    if item.name=='kit':continue
    if item.is_dir():shutil.copytree(item,artifacts/item.name,dirs_exist_ok=True)
    elif item.is_file():shutil.copy2(item,artifacts/item.name)
   record['artifacts']={str(p.relative_to(args.output)):hashlib.sha256(p.read_bytes()).hexdigest() for p in artifacts.rglob('*') if p.is_file()}
   meta['cases'].append(record)
   (args.output/'run.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2)+'\n')
if __name__=='__main__':main()
