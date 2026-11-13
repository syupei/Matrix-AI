#!/usr/bin/env python3
"""Synthetic platform acceptance, real CLI models and filesystem, no business deployment.

Run after a canonical build. All people/approvals/task premises are explicitly
SIMULATED; real artifacts, command traces and failures are retained. This is a
platform integration check, not full professional-quality certification.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import time
import uuid

COMMIT='bd65c5ff854c1f272b18e21e86abcba769d0dfdf'


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--kit',type=Path,required=True);ap.add_argument('--out',type=Path,required=True)
    ap.add_argument('--host',choices=['codex','claude'],required=True);ap.add_argument('--model',help='explicit model for the bounded acceptance run')
    ap.add_argument('--phase',choices=['prepare','continue-reviewed'],default='prepare');a=ap.parse_args()
    kit,out=a.kit.resolve(),a.out.resolve()
    project=out/'project'
    if a.phase=='prepare':
        if out.exists():raise ValueError('new evidence directory required; preserve previous runs')
        out.mkdir(parents=True);project.mkdir()
        shutil.copytree(kit/'matrix',project/'matrix');shutil.copytree(kit/'.agents',project/'.agents')
    elif not project.is_dir():raise ValueError('prepare and review the preserved admission first')
    tools=project/'matrix/orchestration/tools';pm=load('v033_pm',tools/'pm_tasks.py');api=load('v033_api',tools/'platform_api.py');worker=load('v033_worker',tools/'reference_worker.py');boundary=load('v033_boundary',tools/'isolated_runner.py')
    sequence=0
    def call(op,actor='PM',**p):
        nonlocal sequence;sequence+=1
        return pm.execute(project,dict(op=op,actor=actor,event_id='SIM-'+uuid.uuid4().hex,**p))
    def write(ref,obj):
        p=project/ref;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n')
    def facade(op,**p):
        nonlocal sequence;sequence+=1
        r=api.handle(project,dict(protocol=api.SPEC,project_id='SIM-V033',request_id='API-'+uuid.uuid4().hex,event_id='API-'+uuid.uuid4().hex,op=op,params=p),'controller')
        with (out/'events.jsonl').open('a') as f:f.write(json.dumps({'op':op,'result':r},ensure_ascii=False)+'\n')
        if not r['ok']:raise ValueError(r)
        return r['result']
    if a.phase=='prepare':
        call('init',config=dict(project='SIM-V033',pm_actor='PM',authorization='User-authorized synthetic acceptance only',frontdoor_id='SIM',max_slots=3))
        professions=['product','code-engineering']
        write('management/expert-professions.json',dict(schema='matrix-expert-professions/1',professions=professions,configured_by='SIM-fixture',authorization='SIMULATED test preset, not a human production decision'))
        models=[a.model,a.model] if a.model else (['gpt-6.1-sol','gpt-6-luna'] if a.host=='codex' else ['claude-sonnet-4-6','claude-sonnet-4-6'])
        caps={k:dict(state='supported',evidence='local write-boundary probe and CLI probe; raw evidence retained by acceptance operator') for k in ['launch','write_isolation','model_selection','cancel']}
        runner=dict(version='acceptance',models={m:m for m in models},capabilities=caps)
        name='codex-0.167.0.json' if a.host=='codex' else 'claude-2.1.72.json'
        runner.update(json.loads((Path(__file__).resolve().parents[1]/'docs/platforms'/name).read_text()))
        runner.update(models={m:m for m in models},capabilities=caps)
        write(api.CONFIG,dict(schema=api.SPEC,project_id='SIM-V033',principals={'controller':dict(active=True,actor='PM',operations=sorted(api.OPERATIONS),task_ops=[])},runners={'default':runner}))
        # Fetch a real pinned Git expert source. Adapt shared paths, retain source for review.
        identity={'id':'imported-product','version':'1'}
        manifest=facade('expert.prepare',**identity,profession='product',url='https://github.com/syupei/Matrix-AI.git',commit=COMMIT,subdir='src/professions/product/skills/matrix-product')
        base=project/'experts/imported-product/1'
        source=(base/'source/SKILL.md').read_text(encoding='utf-8')
        # Preserve all source text as audit data. The active expert is deliberately a
        # task-specific extraction, whose exclusions are explicit, not a full-role replacement.
        methods='''# 产品需求与交接专家（限定适配）
    来源的产品职责：澄清用户、问题、目标、范围、验收、规则及未决项；关键产品判断留给人。
    一句话需求不等于已确认公开、匿名、登录、审核等特征；示例、模板、案例和其他项目的资料都不是本项目事实。明确区分原话已定、推断和待人决定，匿名不能推导为免登录、免审核或不收集身份信息。
    只处理任务包明确授权的产品子任务，不重新启动完整产品主流程。保持输入版本与未决项，不将候选当确认。
    输出到本实例 workspace/public/，草稿到 workspace/private/。正式源采用、人的确认及跨阶段派发由 Matrix 管理。
    读取 matrix/base/CORE.md 和 matrix/professions/product/profession.json；按其中职责、阶段与人审契约工作。
    专业方法：先核对原话与事实，再按字段和状态拆解；标注已定/待定、适用范围和可检查的验收；交接给下游明确输入版本和限制。
    本适配只支持当前产品需求子任务；完整原专家的规划、视觉联动及验收主流程未纳入此包，不声称完整专家等价。
    '''
        facade('expert.adapt',**identity,methods=methods,review=dict(reviewer='acceptance operator',source_entry='SKILL.md',license='Matrix-AI repository source; package is used only for this authorized local compatibility test',preserved_methods='需求事实、范围、验收、未决项与交接；限定子任务抽取，未声称完整角色迁移',directory_changes='仅实例 private/public；公共规则指向安装包',dependencies='Matrix shared CORE and product profession registry; full-role workflows excluded explicitly'))
        sha=hashlib.sha256((base/'METHODS.md').read_bytes()).hexdigest()
        adm_iid='ADMISSION'
        prompt='这是合成准入测试。请读取 '+str(base/'ENTRY.md')+' 和 '+str(base/'METHODS.md')+'。按该专业方法为已明确要求的留言板写一段候选说明：匿名留言、费用未定。保留费用未定，不开发。只写 '+str(project/'management/instances/ADMISSION/workspace/public/admission.md')+'，完成即退出。'
        admission=load('admission_lifecycle',Path(__file__).with_name('admission_run.py'))
        result=admission.run(pm,boundary,project,identity,a.host,runner,models[0],'medium',prompt)
        (out/'admission.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
        artifact=project/'management/instances/ADMISSION/workspace/public/admission.md'
        write('management/admission-pending.json',dict(runner=a.host,run_id=result['run_id'],model=result['model'],methods_sha256=sha,artifact=str(artifact.relative_to(project)),exit_code=result['exit_code'],review='pending actual artifact and trace review; keyword checks are not admission'))
        print(json.dumps({'phase':'awaiting_review','out':str(out),'next':'Read actual artifact/trace; record method_preservation, write_isolation and handoff_contract evidence, validate and enable through trusted facade, then continue-reviewed. No automatic self-certification.'}))
        return
    # The operator must have reviewed actual artifacts and enabled the package.
    identity={'id':'imported-product','version':'1'}
    pm.team.experts.binding(pm.api(),project,'product',identity)
    models=[a.model,a.model] if a.model else (['gpt-6.1-sol','gpt-6-luna'] if a.host=='codex' else ['claude-sonnet-4-6','claude-sonnet-4-6'])
    entries=[dict(id='P',profession='product',level='T7',model=models[0],effort='medium',count=1,master=True,expert=identity,aliases=['小王.ai']),dict(id='E',profession='code-engineering',level='T7',model=models[1],effort='medium',count=1,master=True,aliases=['小 M.ai'])]
    write('management/instance-config.json',{'entries':entries})
    call('confirm_config',person='SIM-person',quote='SIMULATED approval of acceptance fixture only',presented_ref='SIM fixture',choices={e['id']:'acknowledge_unregistered' for e in entries})
    p=call('derive',entry='P',endpoint='platform')['record']['id'];e=call('derive',entry='E',endpoint='platform')['record']['id']
    call('register_instance',id='SIM-checker',instance=dict(role='quality-engineering',endpoint='SIM-check')) if False else None
    def create(tid,owner,inputs,goal):
        return call('create',task=dict(id=tid,title='SYNTHETIC acceptance '+tid,owner=owner,executor=owner,checker='SIM-checker',goal=goal,inputs=inputs,outputs=['本实例公有候选'],criteria=['保留 SYNTHETIC-REQ-17 与费用待定；仅交候选'],next_action='完成本次限定子任务'))
    create('P',p,['SYNTHETIC-REQ-17：匿名留言板，只定义 message 文本与 created_at 时间；费用待定。此处为合成已定输入，不代表真人产品基线。'],'将给定字段、未决费用及编号整理成 candidate.md，不新增产品决定，不写代码。')
    facade('runtime.configure',mode='local',expected_generation=0)
    result=worker.execute(project,'controller',timeout=240);(out/'product-result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    if not result.get('handed'):raise ValueError('product did not hand over')
    task=next(t for t in pm.execute(project,{'op':'status'})['tasks'] if t['id']=='P')
    texts='\n'.join((project/ref).read_text() for ref in task['evidence'])
    if not all(x in texts for x in ['SYNTHETIC-REQ-17','message','created_at','费用']):raise ValueError('missing supplied facts in product candidate')
    # This is an objective fixture check of explicitly provided facts, not a fake person approval.
    call('review','SIM-checker',task_id='P',expected_revision=task['revision'],outcome='passed',criteria_checked=task['criteria'],evidence=['Actual candidate files checked for exact synthetic inputs; no professional quality certification'])
    task=next(t for t in pm.execute(project,{'op':'status'})['tasks'] if t['id']=='P')
    call('transition',task_id='P',expected_revision=task['revision'],state='done',reason='Synthetic fixture accepts only preservation of exact input facts')
    create('E',e,task['evidence'],'只核对产品已交回候选，写 handoff-check.md，列出 SYNTHETIC-REQ-17、message、created_at 与费用待定；不开发、不改变产品决定。')
    task_e=next(t for t in pm.execute(project,{'op':'status'})['tasks'] if t['id']=='E')
    call('update',e,task_id='E',expected_revision=task_e['revision'],changes={'dependencies':['P']},reason='Synthetic downstream version check',scope_authorization='SIM fixture definition: downstream E consumes accepted P')
    result=worker.execute(project,'controller',timeout=240);(out/'downstream-result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    if not result.get('handed'):raise ValueError('downstream did not hand over')
    status=pm.execute(project,{'op':'status'});write('management/acceptance-status.json',status)
    (out/'summary.json').write_text(json.dumps(dict(passed=True,host=a.host,models=models,effort='medium',source_commit=COMMIT,kit_manifest_sha256=hashlib.sha256((kit/'MANIFEST.json').read_bytes()).hexdigest(),limitation='synthetic platform integration; source adapter intentionally task-limited'),ensure_ascii=False,indent=2))
    print(json.dumps({'passed':True,'host':a.host,'out':str(out)},ensure_ascii=False))


if __name__=='__main__':main()
