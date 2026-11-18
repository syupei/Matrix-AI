#!/usr/bin/env python3
"""Run fixed multi-turn skill probes with an actual local agent CLI (Codex or Claude Code).
Results are ungraded raw evidence; no canned response is treated as model behavior.
"""
import argparse,hashlib,json,os,re,shutil,subprocess,tempfile,time,importlib.util
from contextlib import ExitStack
from pathlib import Path
from read_records import extract
from visual_evidence import capture
from operation_evidence import DIRECTION_CASES, TONE_TOOL, check as check_operation, check_direction, snapshot
from capture_broker import CaptureBroker, preflight as capture_preflight

def fingerprint(root):
 return hashlib.sha256(json.dumps({str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(root.rglob('*')) if p.is_file() and '__pycache__' not in p.parts and p.name!='MANIFEST.json'},sort_keys=True).encode()).hexdigest()

def main():
 p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--case');p.add_argument('--runner',choices=['codex','claude'],default='codex');p.add_argument('--model');p.add_argument('--effort')
 # Resume (Codex only): later turns continue the first turn's session instead of a new session with the earlier turns
 # pasted in. Turns are then not isolated from each other; the record says which way a run was made.
 p.add_argument('--resume',action='store_true')
 p.add_argument('--record-native',action='store_true',help='retain the fresh Codex native session locally for accounting')
 p.add_argument('--author-capture',action='store_true',help='provide the same capture-only author command and capability preflight')
 args=p.parse_args()
 args.source=args.source.resolve();args.output=args.output.resolve()
 if args.resume and args.runner!='codex':raise SystemExit('--resume is implemented for the codex runner only')
 if args.record_native and args.runner!='codex':raise SystemExit('--record-native is implemented for the codex runner only')
 if args.author_capture and args.runner!='codex':raise SystemExit('--author-capture currently has a Codex-native permission preflight only')
 suite_path=Path(__file__).parent/'cases/suite.json';suite=json.loads(suite_path.read_text());args.output.mkdir(parents=True,exist_ok=True)
 source=args.source.resolve();meta={'source_hash':fingerprint(source),'suite_hash':hashlib.sha256(suite_path.read_bytes()).hexdigest(),'runner':{'codex':'codex exec','claude':'claude -p'}[args.runner],'cli_version':subprocess.check_output([args.runner,'--version'],text=True).strip(),'model':args.model,'effort':args.effort,'turns':'resume' if args.resume else 'fresh','operation_evidence_schema':1,'cases':[]}
 if args.record_native:meta['record_native']=True
 meta['author_capture_revision']='author-request-capture/1' if args.author_capture else None
 for case in suite['cases']:
  if args.case and case['id']!=args.case:continue
  with tempfile.TemporaryDirectory(prefix='matrix-behavior-') as d, ExitStack() as services:
   work=Path(d).resolve();shutil.copytree(source,work/'kit',ignore=shutil.ignore_patterns('__pycache__'))
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
   if args.author_capture:
    services.enter_context(CaptureBroker(work,args.output/'author-capture-events.jsonl'))
    record['author_capture_capability']=capture_preflight(work,args.output/'author-capture-preflight')
   operation_kind = ('direction' if case['id'] in DIRECTION_CASES else
                     {'scope': 'draft', 'batch': 'feedback'}.get(case['id']))
   tone_tool = work / TONE_TOOL
   direction_receipt_supported = (operation_kind == 'direction' and tone_tool.is_file()
                                  and b'direction-delivery/1' in tone_tool.read_bytes())
   session=None
   for n,user in enumerate(case['turns']):
    start=f'kit/{entry}' if entry else f'kit/.agents/skills/{role}/SKILL.md'
    prompt=f"在此临时项目中使用 {start} 处理用户请求。读取所需本地规则。仅在此目录写本轮必要成果，不访问外部业务项目、不联网、不启动其他Agent。这里没有可用原生提问控件，使用技能允许的回退方式。只处理当前用户输入，等真实下一条消息，不替用户回答。\n"
    if case.get('visual_preview'):
     prompt+='评测宿主会在本情境结束后自动捕获本地渲染稿，请把 visual-evidence/ 留给评测宿主。\n'
    if args.author_capture:
     prompt+='本轮有本地截图命令：python3 _evaluation/capture_preview.py --preview <本项目HTML相对路径> --output design/author-preview.png --state "当前代表状态"。可重复添加 --artifact <需绑定的本轮文件路径>；未指定时绑定预览文件。命令请求本地隔离浏览器真实采集1280×800图像，并返回实际路径、来源摘要与采集状态。仅可用于本轮项目素材。需要作者截图时请在答复前亲自执行、查看PNG并自行填成果引用。评测宿主后拍图不能追认你早先已截图。\n'
    if history and not session:prompt+='此前真实对话：\n'+json.dumps(history,ensure_ascii=False)+'\n'
    prompt+='用户：'+user
    if session:prompt='用户：'+user
    last=args.output/(case['id']+f'-{n}.md');events=args.output/(case['id']+f'-{n}.jsonl');err=args.output/(case['id']+f'-{n}.stderr')
    if args.runner=='codex' and session:
     cmd=['codex','exec','resume',session,'--skip-git-repo-check','--json','-o',str(last.resolve()),'-c','sandbox_mode="workspace-write"']
     cmd+=(['-m',args.model] if args.model else [])+(['-c','model_reasoning_effort="'+args.effort+'"'] if args.effort else [])+['-']
    elif args.runner=='codex':
     cmd=['codex','exec','--skip-git-repo-check']+([] if args.resume or args.record_native else ['--ephemeral'])+['--sandbox','workspace-write','--json','-C',str(work),'-o',str(last.resolve())]
     cmd+=(['-m',args.model] if args.model else [])+(['-c','model_reasoning_effort="'+args.effort+'"'] if args.effort else [])+['-']
    else:
     cmd=['claude','-p','--output-format','stream-json','--verbose','--permission-mode','acceptEdits']
     cmd+=(['--model',args.model] if args.model else [])+(['--effort',args.effort] if args.effort else [])
    before = snapshot(work, operation_kind) if operation_kind else None
    started=time.time()
    with events.open('w') as stdout,err.open('w') as stderr:
     result=subprocess.run(cmd,input=prompt,text=True,stdout=stdout,stderr=stderr,timeout=480,cwd=str(work))
    if args.runner=='claude' and not result.returncode:
     final=[e for e in (json.loads(l) for l in events.read_text().splitlines() if l.strip()) if e.get('type')=='result']
     if final and not final[-1].get('is_error'):last.write_text(final[-1].get('result',''))
    if result.returncode or not last.exists():raise RuntimeError(f'Actual model run failed: {case["id"]}; see {err}')
    if args.resume and not session:
     started_event=next((json.loads(l) for l in events.read_text().splitlines() if l.strip().startswith('{"type":"thread.started"')),None)
     if not started_event:raise RuntimeError(f'no session to resume: {case["id"]}')
     session=started_event['thread_id']
    reply=last.read_text();history.extend([{'role':'user','text':user},{'role':'assistant','text':reply}])
    record['turns'].append({'user':user,'reply':last.name,'events':events.name,'project_root':str(work),'seconds':round(time.time()-started,2),'sha256':hashlib.sha256(last.read_bytes()).hexdigest()})
    if operation_kind:
     recorded_events = [json.loads(line) for line in events.read_text().splitlines() if line.strip()]
     after = snapshot(work, operation_kind)
     if operation_kind == 'direction':
      audit = check_direction(work, reply, recorded_events, before, after, case['visual_preview'], direction_receipt_supported)
     else:
      audit = check_operation(work, operation_kind, reply, recorded_events, before, after)
     observation = dict(audit, before=before, after=after)
     record['turns'][-1]['operation_evidence'] = observation
     (args.output/last.with_suffix('.operation.json').name).write_text(json.dumps(observation, ensure_ascii=False, indent=2)+'\n')
    print(case['id'],n,'completed',flush=True)
   if case.get('visual_preview'):
    record['visual_evidence'] = capture(work, case['visual_preview'])
    visual = work/'visual-evidence'
    visual.mkdir(exist_ok=True)
    with (visual/'capture.json').open('x', encoding='utf-8') as stream:
     json.dump(record['visual_evidence'], stream, ensure_ascii=False, indent=2)
   # The kit files this case read, from its traces: its reply may be carried over later only while they are unchanged.
   # Resolve relative paths against this isolated evaluated project.
   kit_files=json.loads((source/'MANIFEST.json').read_text())['files']
   events_all=[json.loads(line) for t in record['turns'] for line in (args.output/t['events']).read_text().splitlines() if line.strip()]
   record['read_set']=extract(events_all,meta['runner'],kit_files,entry or '.agents/skills/'+role+'/SKILL.md',str(work))
   record['read_files']=record['read_set']['files'] if record['read_set']['complete'] else None
   artifacts=args.output/(case['id']+'-artifacts');artifacts.mkdir(exist_ok=True)
   for item in work.iterdir():
    if item.name=='kit':continue
    if item.is_dir():shutil.copytree(item,artifacts/item.name,dirs_exist_ok=True)
    elif item.is_file():shutil.copy2(item,artifacts/item.name)
   record['artifacts']={str(p.relative_to(args.output)):hashlib.sha256(p.read_bytes()).hexdigest() for p in artifacts.rglob('*') if p.is_file()}
   meta['cases'].append(record)
   (args.output/'run.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2)+'\n')
if __name__=='__main__':main()
