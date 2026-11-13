"""Run a synthetic admission task through existing launch lifecycle records.

The expert is still unenabled. A trusted controller runs only its bounded admission
probe, binds exact candidate content before starting, and records actual receipts.
"""
import uuid


def run(pm, boundary, project, identity, runner_name, runner, model, effort, prompt, timeout=180):
    db=pm.connect(project,readonly=True)
    try:actor=pm.config(db)['pm_actor']
    finally:db.close()
    def call(op, by=None, **fields):
        return pm.execute(project,dict(op=op,actor=by or actor,event_id='admission-'+uuid.uuid4().hex,**fields))
    iid='ADMISSION';tid='ADMISSION-'+uuid.uuid4().hex[:12];rid='admission-'+uuid.uuid4().hex
    _,manifest=pm.team.experts.read(pm.api(),project,identity)
    call('register_instance',id=iid,instance=dict(role=manifest['profession'],endpoint='SIM-local-admission',write_roots=['management/instances/ADMISSION/workspace']))
    call('create',task=dict(id=tid,title='SYNTHETIC expert admission only',owner=iid,executor=iid,checker='SIM-admission-reviewer',
                           goal='Run bounded candidate admission; no production expert activation',inputs=['experts/'+identity['id']+'/'+identity['version']+'/METHODS.md'],
                           outputs=['management/instances/ADMISSION/workspace/public/admission.md'],criteria=['Preserve supplied facts and boundaries'],next_action='Run isolated admission'))
    workspace=boundary.safe_workspace(project,iid)
    command=boundary.command_template(project,workspace,[],runner,model,effort)[0]
    call('launch_start',id=rid,task_id=tid,purpose='start',instance=iid,model=model,session=rid,command=command,
         admission_expert=identity,admission_runner=runner_name)
    started=False
    def start(pid):
        nonlocal started
        call('launch_started',id=rid,pid=pid)
        started=True
    try:
        result=boundary.run(project,iid,[],prompt,timeout,adapter=runner.get('adapter','kernel'),model=model,effort=effort,template=runner,started=start)
    except Exception as error:
        if started:call('launch_lost',by='scheduler',id=rid,evidence='admission runner stopped after '+type(error).__name__)
        else:call('launch_failed',id=rid,error=type(error).__name__)
        raise
    artifact=workspace/'public/admission.md'
    if result['exit_code']==0 and artifact.is_file():
        call('hand_over',by=iid,run=rid,evidence=[str(artifact.relative_to(project))],summary='Synthetic admission candidate; review still pending')
    call('launch_exit',by='launcher',id=rid,exit_code=result['exit_code'])
    return dict(result,run_id=rid,model=model,runner=runner_name,task_id=tid)
