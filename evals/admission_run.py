"""Run a synthetic admission task through existing launch lifecycle records.

The expert is still unenabled. A trusted controller runs only its bounded admission
probe, binds exact candidate content before starting, and records actual receipts.
"""
import hashlib
import json
from pathlib import Path
import uuid


def admitted_sources(pm, project, manifest, identity, model, prompt, token, call):
    """Prepare explicit synthetic input versions through the kit's real intake API.

    This is an evaluation controller, never a production-user approval recorder.
    It keeps business sources as sources; it does not relabel them as installed rules.
    """
    with pm.connect(project,readonly=True) as db:
        instances=pm.integrity.records(db,'instance')
        masters=[row for row in instances.values() if row.get('active') and row.get('master')
                 and row.get('profession')==manifest['profession'] and row.get('expert',{}).get('id','builtin')=='builtin']
    if masters:
        master=masters[0]['id']
    else:
        config=project/'management/instance-config.json'
        if config.exists():
            raise ValueError('synthetic admission requires an appointed built-in source master; preserve the existing configuration')
        data={'entries':[dict(id='synthetic-admission-source-master',profession=manifest['profession'],level='T7',model=model,count=1,master=True)]}
        pm.atomic(config,json.dumps(data,ensure_ascii=False,indent=2)+'\n')
        call('confirm_config',person='SIM-fixture-person',quote='SYNTHETIC evaluation controller fixture appointment only; not production authorization',
             presented_ref='management/instance-config.json',choices={'synthetic-admission-source-master':'acknowledge_unregistered'})
        master=call('derive',entry='synthetic-admission-source-master',endpoint='SIM-controller-source-review')['record']['id']
    brief='management/admission-inputs/'+token+'/source.md'
    pm.atomic(project/brief,'# SYNTHETIC bounded admission source\n\n'+prompt+'\n\nThis fixture authorizes only the bounded candidate exercise. No production expert activation or product decision.\n')
    methods='experts/'+identity['id']+'/'+identity['version']+'/METHODS.md'
    input_paths=[brief,methods]
    ids=[]
    with pm.connect(project,readonly=True) as db:
        records=pm.integrity.records(db,'input_admission')
    for number,path in enumerate(input_paths):
        sha=hashlib.sha256((project/path).read_bytes()).hexdigest()
        reusable=next((row for row in records.values() if row.get('path')==path and row.get('sha256')==sha and row.get('state')=='admitted'),None)
        if reusable:
            ids.append(reusable['id']);continue
        key='admission-input-'+token+'-'+str(number)
        call('intake_register',id=key,path=path,version=token,source='SYNTHETIC admission controller supplied file',
             source_id='synthetic-admission-'+token+'-'+str(number),profession=manifest['profession'],
             new_family_reason='SYNTHETIC distinct brief/method source; coexistence reviewed for the bounded exercise')
        call('intake_submit',id=key,master=master)
        # Exact fixed fixture facts are read by the trusted controller; no model or
        # professional-quality review is claimed by this deterministic admission.
        actual=(project/path).read_text(encoding='utf-8')
        if not actual.strip():raise ValueError('synthetic admission source must contain the actual bounded instructions')
        with pm.connect(project,readonly=True) as db:
            peers=[row['id'] for row in pm.integrity.records(db,'input_admission').values() if row.get('state')=='admitted' and row.get('profession')==manifest['profession']]
        call('intake_review',by=master,id=key,outcome='approved',
             conclusion='SYNTHETIC source readback: '+path+' sha256='+sha+'; preserve the supplied facts and limits; no production approval',
             resolved_risks=[],resolved_conflicts=[],open_items=[],human_required=False,coexists_with=peers,conflicts_with=[])
        call('intake_admit',id=key)
        ids.append(key)
    gate=pm.admission.load_gate()
    registry=pm.team.registries(pm.api(),project)[manifest['profession']]
    options=[]
    for flow in registry.get('stage_flows',[]):
        options=[(flow['key'],stage) for stage in flow.get('review',[])
                 if not registry.get('framework_requirements',{}).get(stage) and not gate.UPSTREAM.get((flow['key'],stage))]
        if options:break
    if not options:
        raise ValueError('prepare the profession upstream review explicitly; no applicable bounded source-confirmation stage')
    role,current=options[-1];following=gate.STAGES[role][gate.STAGES[role].index(current)+1]
    def put(name,value):
        path=project/name
        pm.atomic(path,json.dumps(value,ensure_ascii=False,indent=2)+'\n' if isinstance(value,dict) else value)
        return name
    prefix='management/admission-inputs/'+token+'/'
    artifacts=[dict(path=path,sha256=hashlib.sha256((project/path).read_bytes()).hexdigest()) for path in input_paths]
    content=gate.artifact_digest(project,artifacts);scope=['synthetic-admission-source'];request_id='SYNTHETIC-'+token
    shown=put(prefix+'display.md','SYNTHETIC source confirmation only\n'+''.join(row['path']+' '+row['sha256']+'\n' for row in artifacts))
    quote='SYNTHETIC fixture confirms only these exact source versions and their stated bounds; no production-user approval.'
    source=put(prefix+'response-source.md',quote)
    display_sha=hashlib.sha256((project/shown).read_bytes()).hexdigest()
    request=put(prefix+'request.json',dict(request_id=request_id,role=role,stage=current,scope=scope,artifact_sha256=content,display_evidence=shown,display_sha256=display_sha))
    response=put(prefix+'response.json',dict(request_id=request_id,actor='user',choice='confirm',scope=scope,artifact_sha256=content,
        source=source,quote=quote,display_sha256=display_sha,message_sha256=gate.tone.evidence.digest(quote) if hasattr(gate,'tone') and hasattr(gate.tone,'evidence') else hashlib.sha256(json.dumps(quote,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()))
    conversation=put(prefix+'conversation.md',current+' -> '+following)
    if hasattr(pm.direction,'bind_attention') and 'human_attention' in getattr(pm.direction,'WRITE_OPS',set()):
        attention='source-confirmation-'+token
        call('human_attention',id=attention,kind='confirmation',display=shown,scope=scope,inputs=input_paths)
        call('human_attention',id=attention,response=source)
        with pm.connect(project) as db:
            receipt=pm.direction.bind_attention(pm.api(),project,db,attention,person='SIM-fixture-person',quote=quote,scope=scope,expected={})
        reply=json.loads((project/response).read_text());reply['review_receipt']=receipt;put(response,reply)
    state=put(prefix+'stage.json',dict(role=role,current=current,next=following,scope=scope,blockers=[],artifacts=artifacts,
        request=request,response=response,conversation_check=conversation))
    gate.check(project,json.loads((project/state).read_text(encoding='utf-8')))
    return dict(inputs=input_paths,admitted_inputs=ids,stage_transition=state),master


def run(pm, boundary, project, identity, runner_name, runner, model, effort, prompt, timeout=180, *, synthetic=False, source_context=None):
    db=pm.connect(project,readonly=True)
    try:actor=pm.config(db)['pm_actor']
    finally:db.close()
    def call(op, by=None, **fields):
        return pm.execute(project,dict(op=op,actor=by or actor,event_id='admission-'+uuid.uuid4().hex,**fields))
    project=Path(project).resolve()
    token=uuid.uuid4().hex[:12]
    iid='ADMISSION';tid='ADMISSION-'+token;rid='admission-'+uuid.uuid4().hex
    _,manifest=pm.team.experts.read(pm.api(),project,identity)
    intake=bool(getattr(pm,'admission',None) and 'intake_register' in getattr(pm.admission,'WRITE_OPS',set()))
    if intake and source_context is None and not synthetic:
        raise ValueError('provide current admitted source_context or explicitly select an isolated synthetic fixture; no automatic appointments or approvals')
    with pm.connect(project,readonly=True) as db:instances=pm.integrity.records(db,'instance')
    if intake and not synthetic:
        if not all(instances.get(key,{}).get('active') for key in (iid,'SIM-admission-reviewer')):
            raise ValueError('appoint the author and independent reviewer explicitly before running against an existing project')
    elif iid not in instances:
        call('register_instance',id=iid,instance=dict(role=manifest['profession'],endpoint='SIM-local-admission',write_roots=['management/instances/ADMISSION/workspace']))
    source=dict(inputs=['experts/'+identity['id']+'/'+identity['version']+'/METHODS.md'])
    if intake:
        if synthetic and 'SIM-admission-reviewer' not in instances:
            call('register_instance',id='SIM-admission-reviewer',instance=dict(role=manifest['profession'],endpoint='SIM-independent-controller-review',write_roots=['management/instances/SIM-admission-reviewer/workspace']))
        if source_context is not None:
            if not isinstance(source_context,dict) or set(source_context) != {'inputs','admitted_inputs','stage_transition'}:
                raise ValueError('source_context must bind inputs, admitted_inputs and the actual upstream stage_transition')
            source=source_context
        else:
            source,_=admitted_sources(pm,project,manifest,identity,model,prompt,token,call)
    call('create',task=dict(id=tid,title='SYNTHETIC expert admission only',owner=iid,executor=iid,checker='SIM-admission-reviewer',
                           goal='Run bounded candidate admission; no production expert activation',**source,
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
