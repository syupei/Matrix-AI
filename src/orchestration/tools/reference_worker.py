#!/usr/bin/env python3
"""Trusted local controller: claim -> isolated argv runner -> verified outbox -> events.

The same platform protocol can be transported by a remote shell. This reference
controller implements one execution per invocation, without a model scheduler.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import sys
import uuid

TOOLS=Path(__file__).resolve().parent


def load(name):
    spec=importlib.util.spec_from_file_location('worker_'+name,TOOLS/(name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


api=load('platform_api')
boundary=load('isolated_runner')


def execute(project,principal,action_id=None,timeout=180):
    root=Path(project).resolve()
    cfg,who=api.access(root,principal)
    def call(op,**params):
        uid=uuid.uuid4().hex
        result=api.handle(root,dict(protocol=api.SPEC,project_id=cfg['project_id'],request_id=uid,event_id=uid,op=op,params=params),principal)
        if not result['ok']:
            raise ValueError(json.dumps(result['error'],ensure_ascii=False))
        return result['result']
    plan=call('actions.plan')
    a=next((a for a in plan['actions'] if action_id is None or a['action_id']==action_id),None)
    if a is None:
        return {'started':False,'stop':plan['stop'],'attention':plan['attention']}
    claimed=call('actions.claim',action_id=a['action_id'],expected_revision=plan['revision'])
    rec,inst=claimed['record'],claimed['instance']
    rid=rec['id'];runner=cfg['runners'][rec['runner']]
    def current():
        return call('runs.query',run_id=rid)['runs'][0]
    def event(kind,**params):
        r=current()
        return call('runs.event',run_id=rid,expected_revision=r['revision'],kind=kind,**params)
    workspace=api.pm.local(root,'management/instances/'+inst['id']+'/workspace')
    values={'model':rec['model'],'instance':inst['id'],'workspace':str(workspace),'project':str(root),
            'state':str(workspace/'private/runner-state'),'log':str(workspace/'private/runner-log')}
    argv=[]
    try:
        if runner.get('adapter','kernel') != 'codex-native' and (not isinstance(runner.get('argv'),list) or not runner['argv'] or not all(isinstance(x,str) for x in runner['argv']) or not runner['argv'][0]):
            raise ValueError('registered runner argv required')
        for part in runner.get('argv', []):
            for k,v in values.items():
                part=part.replace('{'+k+'}',v)
            argv.append(part)
        outbox=api.pm.local(root,'management/instances/'+inst['id']+'/workspace/public/'+rid+'-handoff.json')
        if outbox.exists():
            raise ValueError('outbox exists before a new run')
        log=api.pm.local(root,'management/runtime/logs/'+rid)
        log.parent.mkdir(parents=True,exist_ok=True)
        with open(str(log)+'.stdout','w') as stdout,open(str(log)+'.stderr','w') as stderr:
            result=boundary.run(root,inst['id'],argv,claimed['prompt'],timeout,stdout,stderr,
                started=lambda pid:event('started',pid=pid,model=rec['model'],receipt='local sandbox process '+str(pid)),
                cancelled=lambda:bool(current().get('cancel_requested')), adapter=runner.get('adapter','kernel'), model=rec['model'])
        r=current()
        handed=False
        if result['exit_code']==0 and not result['timed_out'] and not r.get('cancel_requested') and outbox.is_file():
            if outbox.stat().st_nlink != 1:
                raise ValueError('outbox hardlink rejected')
            data=json.loads(outbox.read_text(encoding='utf-8'))
            if not isinstance(data,dict) or not set(data)<={'summary','evidence','reason','commands'}:
                raise ValueError('outbox contains invalid fields')
            if 'commands' in data:
                event('commands',commands=data['commands'])
                handed=True
            elif 'reason' in data:
                event('blocked',reason=data['reason'])
            else:
                if not api.pm.strings(data.get('evidence')) or not data['evidence']:
                    raise ValueError('handover evidence required')
                for ref in data['evidence']:
                    file=api.pm.local(root,ref)
                    if not file.is_relative_to(workspace/'public') or not file.is_file() or file.stat().st_nlink!=1:
                        raise ValueError('evidence must be this instance public candidate')
                event('handover',summary=data.get('summary'),evidence=data['evidence'])
                handed=True
        event('stopped' if result['timed_out'] or r.get('cancel_requested') else 'finished',exit_code=result['exit_code'],receipt='local process group stopped; logs '+str(log.relative_to(root)))
        return dict(started=True,run_id=rid,handed=handed,exit_code=result['exit_code'],timed_out=result['timed_out'])
    except Exception as error:
        r=current()
        if r['state']=='starting':
            event('failed',receipt=str(error))
        elif r['state'] in api.pm.platform.ACTIVE:
            # boundary.run cleans up on all exceptions; post-processing exceptions occur after exit.
            event('stopped',exit_code=1,receipt='reference controller stopped process before reporting: '+str(error))
        raise


def main():
    p=argparse.ArgumentParser();p.add_argument('--project',required=True);p.add_argument('--principal',required=True)
    p.add_argument('--action');p.add_argument('--timeout',type=int,default=180);a=p.parse_args()
    try:
        result=execute(a.project,a.principal,a.action,a.timeout);print(json.dumps(result,ensure_ascii=False));return 0
    except (ValueError,OSError) as error:
        print(json.dumps({'error':str(error)},ensure_ascii=False));return 1


if __name__=='__main__':raise SystemExit(main())
