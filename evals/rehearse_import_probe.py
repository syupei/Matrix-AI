#!/usr/bin/env python3
"""Zero-model script rehearsal of the real isolated import controller.

The deterministic workers do not establish professional quality. Their actual
kernel processes, browser captures, intake, handbacks, independent check and
synthetic display use the same APIs as the paid probe. Only validated is allowed.
"""
import argparse
import json
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import uuid

import imported_framework_probe as p


def worker(project, public, phase):
    gate=p.load('rehearsal_gate',project/'matrix/base/tools/stage_gate.py');tone=gate.tone
    def put(name,value):
        target=public/name;target.parent.mkdir(parents=True,exist_ok=True)
        target.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n' if isinstance(value,dict) else value)
        return dict(tone.evidence.ref(public,name),version='1')
    if phase=='author':
        p.seed.copy_inputs(project/'synthetic-input',public)
        put('product/specs/方向简报.md',(project/'synthetic-input/genre-dice.md').read_text()+'\nSYNTHETIC scripted mechanical rehearsal, no professional-quality finding.\n')
        profile=json.loads((p.late_game.INPUTS/'practice-profile.json').read_text())
        profile['scopes'][0]['id']='race';put(p.PROFILE,profile)
        put('content/场内样句.md',p.late_game.sample_lines())
        # Separate derived author output: fixed reference remains byte-for-byte unchanged.
        html=(project/'synthetic-input'/p.seed.SCENE).read_text()
        html=html.replace('</body>','<button id="sim-turn">SYNTHETIC next turn</button><output id="sim-state">0</output><script>document.querySelector("#sim-turn").onclick=()=>{document.querySelector("#sim-state").textContent=Number(document.querySelector("#sim-state").textContent)+1}</script></body>')
        put(p.SCENE,html)
        def capture(output,artifacts):
            argv=[sys.executable,str(public/'_evaluation/capture_preview.py'),'--preview',p.SCENE,'--output',output,'--state','SYNTHETIC deterministic representative fork']
            for name in artifacts:argv+=['--artifact',name]
            result=subprocess.run(argv,cwd=public,capture_output=True,text=True,check=True)
            print(json.dumps(dict(kind='actual_capture_command',argv=argv,stdout=result.stdout)),flush=True)
            return json.loads(result.stdout)['capture_binding']
        binding=capture(p.PREVIEW_SCREENSHOT,[p.SCENE])
        paths=dict(brief='product/specs/方向简报.md',scene=p.SCENE,preview=p.SCENE,samples='content/场内样句.md',screenshot=p.PREVIEW_SCREENSHOT,practice_profile=p.PROFILE)
        draft=dict(version='1',genre='Route-racing game',profile='SYNTHETIC desktop race',tone='Short rule consequences',core_loop='Choose route, roll, move, settle',viewport='1280x800',capture_binding=binding,
            parts={key:dict(tone.evidence.ref(public,name),version='1') for key,name in paths.items()},
            references=[dict(name=row['name'],source=row['source'],borrows='SYNTHETIC route and turn feedback',observed='Listed source only; not visited by this deterministic worker') for row in p.REFERENCES],
            avoid=['Detached configuration form'],samples=[dict(moment=m,text=t,consequence=c) for m,t,c in p.late_game.SAMPLES])
        contract=put(p.CONTRACT,'# SYNTHETIC scripted direction\n\n```tone-contract\n'+json.dumps(draft,ensure_ascii=False,indent=2)+'\n```\n')
        capture(p.FIT_SCREENSHOT,[p.SCENE,'content/场内样句.md',p.PROFILE])
        put(p.AUTHOR_SELF,dict(status='scripted_mechanism_only',pending=['actual independent check and synthetic display'],professional_quality='not assessed'))
        put('product/reviews/conversation.md','P-1 -> P-2; SYNTHETIC no production completion')
        put('product/reviews/截图回读.md','SYNTHETIC scripted capture; no actual professional visual judgment asserted.')
        put(p.STAGE_STATE,dict(role='product',current='P-1',next='P-2',scope=['race'],blockers=[],artifacts=[contract,tone.evidence.ref(public,p.SCENE)],tone_contract=contract,
            conversation_check='product/reviews/conversation.md',request='pending-request.json',response='pending-response.json',tone_fit_review='pending-fit.json'))
        command=[sys.executable,'-B',str(project/p.TONE_TOOL),'--project',str(public),'--contract',p.CONTRACT,'--draft']
        result=subprocess.run(command,capture_output=True,text=True)
        if result.returncode:raise ValueError('actual draft checker failed: '+result.stdout+result.stderr)
        # This is a typed record of an actual subprocess, explicitly not a model trace.
        print(json.dumps(dict(type='item.completed',item=dict(type='command_execution',command=shlex.join(command),exit_code=result.returncode,aggregated_output=result.stdout),synthetic_script=True)),flush=True)
        check=[sys.executable,str(project/'synthetic-input/import_preflight.py'),'--project',str(project),'--author-public',str(public)]
        subprocess.run(check,check=True)
        p.seed.check_inputs(project/'synthetic-input',public)
    else:
        pm=p.installed(project.parent)[1]
        with pm.connect(project,readonly=True) as db:
            runs=pm.integrity.records(db,'launch');author=next(row for row in runs.values() if row.get('purpose')=='start' and row.get('admission_expert'))
            check=next(row for row in runs.values() if row.get('purpose')=='check' and row.get('state')=='running')
        source=project/'management/instances'/p.AUTHOR/'workspace/public';draft=tone.read(source,p.CONTRACT)
        binding=json.loads((source/p.FIT_CAPTURE).read_text());binding.pop('screenshot_sha256')
        binding['receipt']=tone.evidence.ref(source,p.FIT_CAPTURE)
        fit=dict(tone_contract=tone.direction_binding(p.CONTRACT,draft),artifacts=[draft['parts'][key] for key in ('scene','preview','samples','practice_profile')],
            screenshot=tone.evidence.ref(source,p.FIT_SCREENSHOT),capture_binding=binding,viewport='1280x800',capture='SYNTHETIC deterministic actual broker evidence',
            genre_fit='SYNTHETIC fixture supplied route board',application_drift='SYNTHETIC no professional verdict',copy_fit='SYNTHETIC six moment/consequence entries',outcome='passed',
            producer=p.AUTHOR,checker=p.REVIEWER,mode='independent',review_task=author['task_id'],binding_mode='pre_confirmation_direction')
        fit_ref=put(p.FIT,fit)
        precheck=[sys.executable,'-B',str(project/'synthetic-input/import_preflight.py'),'--project',str(project),'--checker-public',str(public)]
        raw=(public/p.FIT).read_bytes();missing=dict(fit);missing.pop('viewport');put(p.FIT,missing)
        before={path.relative_to(public).as_posix():p.sha(path) for path in public.rglob('*') if path.is_file()}
        negative=subprocess.run(precheck,capture_output=True,text=True)
        after={path.relative_to(public).as_posix():p.sha(path) for path in public.rglob('*') if path.is_file()}
        p.require(negative.returncode==1 and 'viewport' in negative.stdout and before==after,'missing viewport must fail without editing checker outputs')
        print(json.dumps(dict(kind='actual_readonly_preflight_negative',case='missing_viewport',exit_code=negative.returncode,stdout=negative.stdout,public_unchanged=before==after)),flush=True)
        (public/p.FIT).write_bytes(raw)
        positive=subprocess.run(precheck,capture_output=True,text=True,check=True)
        print(json.dumps(dict(kind='actual_readonly_preflight_positive',stdout=positive.stdout)),flush=True)
        identity=p.IDENTITY;expert=pm.team.experts;binding=expert.admission_binding(pm.api(),project,identity);contract=expert.framework_contract(pm.api(),project,'product')
        requirements=[dict(stage=row['stage'],requirement=row['requirement']) for row in contract['requirements']]
        report=dict(passed=True,runner='SYNTHETIC-python',run_id=author['id'],review_run_id=check['id'],model='SYNTHETIC-python',methods_sha256=binding['methods_sha256'],
            checks={key:dict(passed=True,evidence='SYNTHETIC deterministic API rehearsal only') for key in p.CHECKS},
            framework_scenario=dict(stage_state=p.STAGE_STATE,reviewer=p.REVIEWER,readback='SYNTHETIC scripted mechanism only; professional quality not assessed',
                author_stage=dict(path=(source/p.STAGE_STATE).relative_to(project).as_posix(),sha256=p.sha(source/p.STAGE_STATE)),
                fit=dict(path=(public/p.FIT).relative_to(project).as_posix(),sha256=fit_ref['sha256']),contract_sha256=binding['contract_sha256'],mapping_sha256=binding['mapping_sha256']),
            tested_requirements=[r for r in requirements if r['stage']=='P-1'],untested_requirements=[r for r in requirements if r['stage']!='P-1'])
        put(p.REVIEW_REPORT,report)


def rehearse(kit,out):
    prepared=p.prepare(kit,out);project,pm,api,boundary=p.installed(out)
    script=project/'synthetic-input/rehearse_import_probe.py';shutil.copyfile(__file__,script)
    # Workers need only this repository's read-only deterministic modules.
    runner=dict(adapter='kernel',argv=[sys.executable,str(script),'--worker','{project}','{workspace}/public','PHASE'],cwd='{workspace}',unset_env=[])
    # Imports are read-only; writes are still enforced by the ordinary kernel runner.
    env_path=str(Path(__file__).parent)
    runner['argv']=[sys.executable,'-B','-c','import sys,runpy;sys.path.insert(0,'+repr(env_path)+');sys.argv='+repr([str(script),'--worker'])+"+[sys.argv[1],sys.argv[2],sys.argv[3]];runpy.run_path("+repr(str(script))+",run_name='__main__')",'{project}','{workspace}/public','PHASE']
    runs={}
    for phase,iid,purpose in [('author',p.AUTHOR,'start'),('checker',p.REVIEWER,'check')]:
        rid='SYNTHETIC-'+phase+'-'+uuid.uuid4().hex;template=dict(runner,argv=[phase if x=='PHASE' else x for x in runner['argv']])
        command=boundary.command_template(project,boundary.safe_workspace(project,iid),[],template,'SYNTHETIC-python','none')[0]
        fields=dict(id=rid,task_id=p.TASK_ID,purpose=purpose,instance=iid,model='SYNTHETIC-python',session=rid,command=command)
        if purpose=='start':fields.update(admission_expert=p.IDENTITY,admission_runner='SYNTHETIC-python')
        p.pm_call(pm,project,out,'launch_start',**fields)
        def started(pid):p.pm_call(pm,project,out,'launch_started',id=rid,pid=pid)
        public=project/'management/instances'/iid/'workspace/public'
        with p.CaptureBroker(public,out/(phase+'-capture-events.jsonl')) if phase=='author' else __import__('contextlib').nullcontext():
            result=boundary.run(project,iid,[],'SYNTHETIC deterministic worker. No model.',timeout=180,template=template,adapter='kernel',model='SYNTHETIC-python',effort='none',started=started)
        p.write_json(out/(phase+'-script-process.json'),result)
        p.require(result['exit_code']==0,'script worker failed: '+result.get('stderr',''))
        if phase=='author':
            events=[]
            for line in result['stdout'].splitlines():
                try:event=json.loads(line)
                except ValueError:continue
                if isinstance(event,dict) and event.get('type')=='item.completed':events.append(event)
            p.author_handover(pm,project,out,public,rid,p.author_delivery(events,project,public))
        else:
            with pm.connect(project,readonly=True) as db:task=pm.task_map(db)[p.TASK_ID]
            p.pm_call(pm,project,out,'review',actor=iid,task_id=p.TASK_ID,expected_revision=task['revision'],outcome='passed',criteria_checked=task['criteria'],
                evidence=[(public/name).relative_to(project).as_posix() for name in (p.FIT,p.REVIEW_REPORT)])
        p.pm_call(pm,project,out,'launch_exit',actor='launcher',id=rid,exit_code=0)
        runs[phase]=pm.team.experts.validation_run(pm.api(),project,rid)
    view=p.assemble_scenario(pm,project,out,runs['author'],runs['checker'],project/'management/instances'/p.REVIEWER/'workspace/public'/p.REVIEW_REPORT)
    result=p.platform_call(api,project,out,'expert.validate',dict(p.IDENTITY,evidence=dict(runner='SYNTHETIC-python',report='management/instances/'+p.REVIEWER+'/workspace/public/'+p.REVIEW_REPORT,source_sha256=prepared['binding']['methods_sha256'],scenario_view=view)))
    p.require(result['state']=='validated','rehearsal must stop at validated')
    p.write_json(out/'rehearsal.json',dict(model_calls=0,state='validated',runs={k:v['id'] for k,v in runs.items()},validation=result,
        professional_quality='not assessed',limit='Scripted isolated mechanical rehearsal only; not enabled, bound, published, or a completed PM milestone.'))
    return result


if __name__=='__main__':
    if len(sys.argv)>1 and sys.argv[1]=='--worker':worker(Path(sys.argv[2]),Path(sys.argv[3]),sys.argv[4])
    else:
        parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--kit',type=Path,required=True);parser.add_argument('--out',type=Path,required=True)
        args=parser.parse_args();print(json.dumps(rehearse(args.kit.resolve(),args.out.resolve()),ensure_ascii=False,indent=2))
