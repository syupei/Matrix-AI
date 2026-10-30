#!/usr/bin/env python3
"""Synthetic local CLI transport probe: actual workers -> actual lead.
No external project, human approvals, SaaS tools or OS isolation are claimed.
"""
import argparse
from contextlib import ExitStack
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import uuid


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--source',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
    source=a.source.resolve();output=a.output.resolve();output.mkdir(parents=True,exist_ok=False)
    with tempfile.TemporaryDirectory(prefix='matrix-live-team-') as temporary, ExitStack() as cleanup:
        work=Path(temporary);shutil.copytree(source,work/'kit',ignore=shutil.ignore_patterns('__pycache__'))
        bridge=load('live_bridge',source/'collaboration/tools/task_dispatch.py')
        pm=load('live_pm',source/'.agents/skills/project-management-agent/scripts/pm_tasks.py')
        coord=load('live_coord',source/'.agents/skills/professional-agent-collaboration/scripts/coordination.py')
        n=0
        def cmd(op,actor='PM',**kw):
            nonlocal n
            n+=1;return pm.execute(work,dict(op=op,actor=actor,event_id='LIVE-SETUP-'+str(n),**kw))
        (work/'AUTHORITY.md').write_text('合成试跑授权：P1 为产品负责人，P2/P3 为执行者；只处理未支付订单可取消的已确定范围。已支付后取消与退款时效待真人决定。允许在此隔离项目中实际调用本机模型进程制作候选，禁止外部业务操作。没有任何人工批准或专业通过记录。')
        (work/'BASELINE.md').write_text('已确定：未支付订单可以取消。已支付后能否取消、退款时效仍待决定。P2 准备状态表，P3 准备取消流程和异常场景；P1 整合，不填补未定规则。')
        cmd('init',config=dict(project='SYNTHETIC-LIVE',pm_actor='PM',authorization='AUTHORITY.md',frontdoor_thread='LOCAL-TEST',max_slots=3))
        def task(tid,owner,goal,parent=None,actor='PM',slots=1):
            return cmd('create',actor,task=dict(id=tid,parent=parent,title=goal,owner=owner,executor=owner,checker='UNASSIGNED-CHECKER',
                goal=goal,inputs=['BASELINE.md'],outputs=['candidate.md'],criteria=['保留已确定规则和未决范围'],next_action='prepare candidate',slots=slots))
        task('PRODUCT','P1','整合订单产品候选',slots=0)
        sessions={iid:uuid.uuid4().hex for iid in ['P1','P2','P3']}
        # Endpoints identify actual host-managed CLI sessions, allocated after local readiness checks.
        for iid in sessions:
            root='.agent-runtime/instances/'+iid+'/workspace';(work/root).mkdir(parents=True)
            cmd('register_instance',id=iid,instance=dict(role='product-agent',endpoint='local-cli:'+sessions[iid],write_roots=[root]))
        cmd('appoint',id='P1',appointment=dict(mode='lead',role='product-agent',root_tasks=['PRODUCT'],delegates=['P2','P3'],source='AUTHORITY.md'))
        task('STATES','P2','仅制作未支付订单取消相关的状态表候选，保存 candidate.md','PRODUCT','P1')
        task('FLOW','P3','仅制作未支付订单取消流程、异常与验收情境候选，保存 candidate.md','PRODUCT','P1')
        for iid,tid in [('P2','STATES'),('P3','FLOW')]:
            cmd('appoint',id=iid,appointment=dict(mode='executor',role='product-agent',root_tasks=[tid],delegates=[],source='AUTHORITY.md'))
        coord.execute(work,dict(op='init',actor='coordinator',config=dict(protocol='professional-collaboration/0.1',authorization='AUTHORITY.md',frontdoor={'thread_id':'LOCAL-TEST'})))
        for iid,session in sessions.items():
            coord.execute(work,dict(op='register',actor='coordinator',role=dict(id=iid,skill='kit/.agents/skills/product-agent/SKILL.md',write_roots=['.agent-runtime/instances/'+iid+'/workspace'],endpoint=dict(kind='subagent',id='local-cli:'+session,session=session))))
        processes={};notifications={};raw=[]
        # Preserve partial evidence and stop only the probe's own children on failure.
        cleanup.callback(lambda: shutil.copytree(work, output/'project', dirs_exist_ok=True, ignore=shutil.ignore_patterns('kit','__pycache__')))
        def stop(proc):
            if proc.poll() is None:
                proc.terminate()
                try: proc.wait(timeout=5)
                except subprocess.TimeoutExpired: proc.kill();proc.wait()
        def start(iid,prompt,label):
            reply=output/(label+'.md');events=output/(label+'.jsonl');errors=output/(label+'.stderr')
            out=events.open('w');err=errors.open('w')
            proc=subprocess.Popen(['codex','exec','--skip-git-repo-check','--ephemeral','--sandbox','workspace-write','--json','-C',str(work),'-o',str(reply),'-'],stdin=subprocess.PIPE,stdout=out,stderr=err,text=True)
            cleanup.callback(out.close);cleanup.callback(err.close);cleanup.callback(stop,proc)
            proc.stdin.write(prompt);proc.stdin.close()
            row=dict(instance=iid,pid=proc.pid,session=sessions[iid],label=label,started_at=time.time())
            raw.append(row)
            return proc,out,err,reply,row
        def send(endpoint,packet):
            iid=packet['target_role']['id'];binding=packet['request']['payload']['task_binding']
            prompt='这是隔离合成项目的实际执行试跑。读取 kit/.agents/skills/product-agent/SKILL.md、AUTHORITY.md、BASELINE.md 和本任务包。不要联网、创建其他 Agent 或修改任务库/共享基线/任职。只在自己工作区制作实际候选并最终返回摘要、产物引用、未知和自检范围；不宣称已验收或人已确认。回交通道由宿主处理，你不自行调用 respond。\n'+json.dumps(packet,ensure_ascii=False)
            p=start(iid,prompt,iid);processes[iid]=(p,packet)
            return dict(outcome='sent',evidence='local CLI stdin accepted; pid '+str(p[0].pid),started=True,start_evidence='actual subprocess '+str(p[0].pid)+' started for '+binding['task_id'])
        def wake(endpoint,note):
            notifications.setdefault(note['event_id'],note)
            # Host coalesces current return notifications, then invokes the lead once below.
            return dict(outcome='queued',evidence='local host wake queue '+note['event_id'])
        dispatcher=bridge.Dispatcher(work,work/'kit/.agents/skills',send,wake)
        for tid in ['STATES','FLOW']:dispatcher.dispatch(tid,'LIVE-'+tid,['BASELINE.md','AUTHORITY.md'],'AUTHORITY.md')
        for iid,(p,packet) in processes.items():
            proc,out,err,reply,row=p;code=proc.wait(timeout=480);out.close();err.close();row.update(exit=code,finished_at=time.time())
            if code or not reply.is_file():raise RuntimeError('actual worker failed: '+iid)
            req=packet['request']
            refs=[str(x.relative_to(work)) for x in (work/'.agent-runtime/instances'/iid/'workspace').rglob('*') if x.is_file()]
            if not refs:raise RuntimeError('worker produced no candidate: '+iid)
            coord.execute(work,dict(op='respond',actor=iid,id=req['id'],attempt=req['attempt'],response=dict(kind='explanation',summary=reply.read_text(),evidence=refs)))
            dispatcher.collect(req['id'])
        leadprompt='这是隔离合成项目。使用 kit/.agents/skills/product-agent/SKILL.md。你是已有任职的 P1，请读 AUTHORITY.md、BASELINE.md、任务库和 .agent-runtime/instances/P2/workspace/、P3/workspace/ 的实际成果。两个执行者已回交，通知如下。请核对两个候选的一致性并在 .agent-runtime/instances/P1/workspace/integrated.md 整合，指出矛盾和未决事实。不得改任务库、源授权或原候选，不伪造独立验收/人工批准，不联网或启动其他 Agent。最后给真人产品一条答复。\n'+json.dumps(list(notifications.values()),ensure_ascii=False)
        proc,out,err,reply,row=start('P1',leadprompt,'P1-returned');code=proc.wait(timeout=480);out.close();err.close();row.update(exit=code,finished_at=time.time())
        if code or not reply.is_file() or not (work/'.agent-runtime/instances/P1/workspace/integrated.md').is_file():raise RuntimeError('lead integration missing')
        shutil.copytree(work,output/'project',ignore=shutil.ignore_patterns('kit','__pycache__'))
        source_hash=load('live_runner_hash',Path(__file__).with_name('run.py')).fingerprint(source)
        receipt=dict(source_hash=source_hash,runner='codex exec',cli_version=subprocess.check_output(['codex','--version'],text=True).strip(),processes=raw,notifications=list(notifications.values()),
            tasks=pm.execute(work,{'op':'status'}),limitations=['Synthetic project and preassigned work packages; no real human approval.', 'Host callback records actual CLI outputs; sessions share a filesystem and do not prove OS/tool isolation.', 'No external tool, autonomous daemon, professional acceptance or real user trial.'])
        receipt['evidence']={str(p.relative_to(output)):hashlib.sha256(p.read_bytes()).hexdigest() for p in output.rglob('*') if p.is_file()}
        (output/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
        print(json.dumps(dict(actual_processes=len(raw),candidate_files=len(list((output/'project/.agent-runtime').rglob('*.md'))),output=str(output))),flush=True)
if __name__=='__main__':main()
