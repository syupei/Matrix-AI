"""Real admission APIs for isolated PM mechanism fixtures; every person and host is SIMULATED.
Generic registered mechanism roles are not claims of built-in professional production.
"""
import json
from practice_fixture import put, review_state
from test_pm_instances import MODELS


def business_source(fixture, pm, *, pm_actor='PM', actors=(), person=None):
    fixture.root=fixture.root.resolve()
    def call(op,actor=None,**fields):return fixture.call(op,actor or pm_actor,**fields)
    with pm.connect(fixture.root,readonly=True) as db:
        instances=pm.integrity.records(db,'instance');configured=pm.integrity.records(db,'instance_config')
    for actor in actors:
        iid,role=actor[:2]
        if iid not in instances:
            call('register_instance',id=iid,instance=dict(role=role,endpoint='SIM-host-'+iid,**(actor[2] if len(actor)>2 else {})))
    with pm.connect(fixture.root,readonly=True) as db:instances=pm.integrity.records(db,'instance')
    masters=[row for row in instances.values() if row.get('active') and row.get('master')]
    roster=pm.roster(fixture.root)
    person=person or next((iid for iid,row in (roster or {}).get('people',{}).items() if 'project' in row.get('decides',[])),'SIM-owner')
    if not masters:
        assert not configured,'Fixture must explicitly derive its actual professional source master'
        put(fixture.root,'management/model-fit.json',MODELS)
        put(fixture.root,'management/instance-config.json',dict(entries=[dict(id='SIM-source-product',profession='product',level='T7',model='SIM-big',count=1,master=True)]))
        call('confirm_config',person=person,quote='SIM approves the explicit source-review configuration',presented_ref='SIM configuration displayed',choices={})
        master=call('derive',entry='SIM-source-product',endpoint='SIM-source-master-host')['record']
    else:master=next((row for row in masters if row.get('profession')=='product'),masters[0])
    path='external/SIM-business-input.md';key='SIM-business-input'
    put(fixture.root,path,'SIM bounded task-mechanism source: preserve original task scope, declared outputs and acceptance. This is synthetic test material, not an actual professional deliverable.\n')
    with pm.connect(fixture.root,readonly=True) as db:records=pm.integrity.records(db,'input_admission')
    peers=[row['id'] for row in pm.admission.ref_latest(records).values() if row['state']=='admitted' and row['profession']==master['profession']]
    call('intake_register',id=key,source_id=key,path=path,version='1',source='SIM complete original mechanism request',profession=master['profession'],new_family_reason='Independent bounded mechanism fixture')
    call('intake_submit',id=key,master=master['id'])
    call('intake_review',master['id'],id=key,outcome='approved',conclusion='SIM actual source version reviewed for this task mechanism',resolved_risks=[],resolved_conflicts=[],open_items=[],human_required=False,coexists_with=peers,conflicts_with=[])
    call('intake_admit',id=key)
    gate=pm.admission.load_gate();prefix='SIM-input-confirm'
    state=review_state(fixture.root,gate,[path],person=person,prefix=prefix)
    request=json.loads((fixture.root/state['request']).read_text());reply=json.loads((fixture.root/state['response']).read_text())
    call('human_attention',id=prefix,kind='confirmation',display=request['display_evidence'],scope=state['scope'],inputs=[path])
    call('human_attention',id=prefix,response=reply['source'],**({'response_id':reply['response_id']} if reply.get('response_id') else {}))
    with pm.connect(fixture.root) as db:reply['review_receipt']=pm.direction.bind_attention(pm.api(),fixture.root,db,prefix,person=person,quote=reply['quote'],scope=state['scope'],expected={})
    put(fixture.root,state['response'],reply)
    return dict(inputs=[path],admitted_inputs=[key],stage_transition=put(fixture.root,'SIM-input-stage.json',state)['path'])


def actual_output(fixture, task, name=None):
    name=name or next((value for value in task['outputs'] if not value.endswith('/')),task['outputs'][0]+'SIM-'+task['id']+'-result.txt')
    put(fixture.root,name,'SIM actual declared result '+task['id']);return name


def confirmed_direction(fixture, pm, basis, *, checker='code-engineering-001', fit_checker='quality-engineering-001', person='boss'):
    """Synthetic P-1 materials, actual tasks/handoffs/independent fit and one answered attention."""
    from practice_fixture import direction,fit_record
    tone=pm.admission.load_gate().tone
    _,data=direction(fixture.root,tone);data.pop('confirmation')
    data['parts']['feasibility']=put(fixture.root,'SIM-direction-feasibility.md','SIM actual feasibility record')
    data['parts']['acceptance']=put(fixture.root,'SIM-direction-acceptance.md','SIM actual acceptance record')
    def call(op,actor='PM',**fields):return fixture.call(op,actor,**fields)
    def task(tid):return next(t for t in pm.execute(fixture.root,{'op':'status'})['tasks'] if t['id']==tid)
    def mutate(op,tid,actor,**kw):return call(op,actor,task_id=tid,expected_revision=task(tid)['revision'],**kw)
    material=list(dict.fromkeys(ref['path'] for ref in data['parts'].values()))
    for tid,owner,outputs,deps,kind in [('SIM-COMPOSE','product-001',material,[],'work'),('SIM-FIT',fit_checker,['SIM-direction-fit.json'],['SIM-COMPOSE'],'work'),('SIM-DIRECTION','PM',[tone.DEFAULT_PATH],['SIM-FIT'],'stage')]:
        value=dict(id=tid,parent=None,title=tid,owner=owner,executor=owner if kind=='work' else None,checker=checker,goal='SIM complete scoped direction',next_action='SIM inspect current materials',inputs=basis['inputs'],admitted_inputs=basis['admitted_inputs'],stage_transition=basis['stage_transition'],outputs=outputs,criteria=['SIM exact current materials'],dependencies=deps,kind=kind,human_required=kind=='stage',slots=1 if kind=='work' else 0)
        call('create',task=value)
    rec=dict(id='SIM-DIRECTION',tasks=['SIM-COMPOSE','SIM-FIT'],outputs={key:data['parts'][key]['path'] for key in ('brief','scene','samples','feasibility','acceptance')},profile=data['profile'],practice_profile=data['parts']['practice_profile']['path'],preview=data['parts']['preview']['path'],producer='product-001',fit_checker=fit_checker,masters={role:role+'-001' for role in ('product','code-engineering','quality-engineering')})
    rec['outputs'].update(compose='SIM-direction-draft.md',fit='SIM-direction-fit.json')
    with pm.connect(fixture.root) as db:pm.integrity.save(pm.api(),db,'direction_sample',rec)
    def write():
        body='```tone-contract\n'+json.dumps(data)+'\n```\n';put(fixture.root,'SIM-direction-draft.md',body);put(fixture.root,tone.DEFAULT_PATH,body)
    def finish(tid,paths):
        owner=task(tid)['owner'];mutate('transition',tid,owner,state='running',reason='SIM actual local production',execution_receipt='SIM tool execution')
        mutate('transition',tid,owner,state='waiting_review',reason='SIM actual handoff',stop_evidence='SIM returned',evidence=paths)
        mutate('review',tid,checker,outcome='passed',criteria_checked=task(tid)['criteria'],evidence=['SIM checked current scope'])
        mutate('transition',tid,'PM',state='done',reason='SIM independent checked result adopted')
    write();finish('SIM-COMPOSE',material)
    reviewed=[data['parts'][key] for key in ('scene','preview','samples','practice_profile')]
    fit_record(fixture.root,tone.direction_binding(tone.DEFAULT_PATH,data),reviewed,record_path='SIM-direction-fit.json',mode='independent',producer='product-001',checker=fit_checker,review_task='SIM-FIT',binding_mode='pre_confirmation_direction')
    finish('SIM-FIT',['SIM-direction-fit.json'])
    mutate('update','SIM-DIRECTION','PM',changes={'evidence':[tone.DEFAULT_PATH]},reason='SIM draft handed to the milestone')
    mutate('review','SIM-DIRECTION',checker,outcome='passed',criteria_checked=task('SIM-DIRECTION')['criteria'],evidence=['SIM complete scope inspected'])
    put(fixture.root,'SIM-direction-display.md','SIM actually displayed the complete direction with all material references')
    quote='SIM approves this whole displayed fixture direction once';put(fixture.root,'SIM-direction-reply.md',quote)
    call('human_attention',id='SIM-P1',kind='confirmation',task_id='SIM-DIRECTION',scope='SIM whole direction',display='SIM-direction-display.md')
    call('human_attention',id='SIM-P1',response='SIM-direction-reply.md')
    approved=mutate('human_review','SIM-DIRECTION','PM',outcome='approved',person=person,presented_ref='SIM-direction-display.md',source='SIM-direction-reply.md',quote=quote,scope='SIM whole direction',attention_id='SIM-P1')
    data['confirmation']=dict(person=person,quote=quote,source='SIM-direction-reply.md',direction_sha256=tone.direction_binding(tone.DEFAULT_PATH,data)['direction_sha256'],review_receipt=approved['task']['human_review']['review_receipt'])
    write();mutate('transition','SIM-DIRECTION','PM',state='done',reason='SIM actual P1 adopted')
    return dict(tone.evidence.ref(fixture.root,tone.DEFAULT_PATH),version=data['version'])


def bound_review_state(fixture,pm,paths,*,role='product',stage='P-7',following='complete',scope_ids=None,prefix='SIM-stage',person='boss'):
    gate=pm.admission.load_gate();state=review_state(fixture.root,gate,paths,role=role,stage=stage,following=following,scope_ids=scope_ids,person=person,prefix=prefix)
    request=json.loads((fixture.root/state['request']).read_text());reply=json.loads((fixture.root/state['response']).read_text())
    quote='SIM approves the complete displayed scope '+prefix
    put(fixture.root,reply['source'],dict(messages=[dict(id=prefix+'-reply',text=quote)]))
    reply.update(quote=quote,response_id=prefix+'-reply',message_sha256=gate.tone.evidence.digest(quote))
    fixture.call('human_attention','PM',id=prefix,kind='confirmation',display=request['display_evidence'],scope=state['scope'],inputs=paths)
    fixture.call('human_attention','PM',id=prefix,response=reply['source'],**({'response_id':reply['response_id']} if reply.get('response_id') else {}))
    with pm.connect(fixture.root) as db:reply['review_receipt']=pm.direction.bind_attention(pm.api(),fixture.root,db,prefix,person=person,quote=reply['quote'],scope=state['scope'],expected={})
    put(fixture.root,state['response'],reply);return state
