"""Synthetic prior direction created and closed only through ordinary PM APIs."""
import json
from practice_fixture import direction,put,capture_binding,fit_record


def close_direction(f,pm,rows=None):
    tone=pm.admission.load_gate().tone
    cache=getattr(f,'closed_expert_directions',{})
    token=__import__('hashlib').sha256(json.dumps(rows,sort_keys=True).encode()).hexdigest()[:8]
    if token in cache:return cache[token]
    context=f.expert_business_context
    with pm.connect(f.root,readonly=True) as db:
        instances=pm.integrity.records(db,'instance')
    master=next(r['id'] for r in instances.values() if r.get('master') and r.get('profession')=='product' and r.get('active'))
    author=getattr(f,'admission_author','SIM-admission-instance');checker='SIM-independent-reviewer'
    key='EXPERT-PRIOR-'+token
    _,data=direction(f.root,tone,rows);data.pop('confirmation')
    sample=f.call('direction_sample',id=key,brief=context['inputs'][0],admitted_inputs=context['admitted_inputs'],profile=data['profile'],person='SYNTHETIC fixture decider',
        combined_review_authorization='SYNTHETIC closed prerequisite for mechanism tests only',assigned=dict(product=master,fit_checker=checker,task_checker=author))['direction_sample']
    # Missing professional contributions are explicitly supplied and admitted human
    # fallback results. No role, task completion or approval is invented in SQL.
    for role,part in [('experience-design','scene'),('content-design','samples'),('code-engineering','feasibility'),('quality-engineering','acceptance')]:
        required=[sample['outputs'][part]]
        if role=='experience-design':required.append(sample['preview'])
        for name in required:put(f.root,name,'<body>SYNTHETIC direction</body>' if name.endswith('.html') else 'SYNTHETIC bounded '+part+' contribution')
        gap=f.call('gap_open',domain=role,kind='not_set_up',why='SYNTHETIC no specialist role in mechanism fixture',qualification='SYNTHETIC fixture supplier',risk='F3')['record']
        gap=f.call('gap_decide',gap=gap['id'],expected_revision=gap['revision'],choice='human',person='SYNTHETIC fixture decider',quote='SYNTHETIC supplied contribution only')['record']
        f.call('gap_close',gap=gap['id'],expected_revision=gap['revision'],source='SYNTHETIC explicit fixture result',evidence=required)
        ids=[]
        for i,path in enumerate(required):
            with pm.connect(f.root,readonly=True) as db:
                reusable=next((r for r in pm.integrity.records(db,'input_admission').values() if r['path']==path and r['sha256']==tone.evidence.ref(f.root,path)['sha256'] and r['state']=='admitted'),None)
            if reusable:ids.append(reusable['id']);continue
            aid=key+'-'+part+'-'+str(i)
            f.call('intake_register',id=aid,path=path,version='1',source='SYNTHETIC actual human fallback file',source_id=aid,profession='product',new_family_reason='SYNTHETIC distinct contribution source')
            f.call('intake_submit',id=aid,master=master)
            with pm.connect(f.root,readonly=True) as db:peers=[r['id'] for r in pm.integrity.records(db,'input_admission').values() if r['state']=='admitted']
            f.call('intake_review',master,id=aid,outcome='approved',conclusion='SYNTHETIC actual contribution readback',resolved_risks=[],resolved_conflicts=[],open_items=[],human_required=False,coexists_with=peers,conflicts_with=[])
            f.call('intake_admit',id=aid);ids.append(aid)
        sample=f.call('direction_resolve_gap',id=key,role=role,gap=gap['id'],admitted_inputs=ids)['direction_sample']
    def finish(tid,evidence):
        f.mutate('transition',tid,state='running',reason='SYNTHETIC deterministic fixture process',execution_receipt='SYNTHETIC actual fixture method')
        f.mutate('transition',tid,state='waiting_review',reason='SYNTHETIC actual handback',stop_evidence='SYNTHETIC yielded',evidence=evidence)
        f.check(tid);f.close(tid)
    data['parts']['brief']=put(f.root,sample['outputs']['brief'],'SYNTHETIC read back original bounded business brief')
    finish(key+'-brief',[sample['outputs']['brief']])
    for part in ('scene','samples','feasibility','acceptance'):data['parts'][part]=dict(tone.evidence.ref(f.root,sample['outputs'][part]),version='1')
    data['parts']['preview']=dict(tone.evidence.ref(f.root,sample['preview']),version='1')
    profile=json.loads((f.root/data['parts']['practice_profile']['path']).read_text())
    data['parts']['practice_profile']=put(f.root,sample['practice_profile'],profile)
    data['capture_binding']=capture_binding([data['parts']['preview']],root=f.root,screenshot=data['parts']['screenshot'])
    def draft():
        text='```tone-contract\n'+json.dumps(data)+'\n```\n';put(f.root,sample['outputs']['compose'],text);return put(f.root,tone.DEFAULT_PATH,text)
    draft()
    compose_outputs=[sample['outputs']['compose'],sample['practice_profile'],*[data['parts'][part]['path'] for part in ('scene','preview','samples')]]
    with pm.connect(f.root,readonly=True) as db:
        records=pm.integrity.records(db,'input_admission');compose_task=pm.task_map(db)[key+'-compose']
    basis=[aid for aid in sample['admitted_inputs'] if records[aid]['path'] in compose_task['inputs']]
    f.mutate('update',key+'-compose','PM',changes={'outputs':compose_outputs},reason='SYNTHETIC composer preserves and hands back the explicitly adopted contribution files',admission_basis=basis)
    finish(key+'-compose',compose_outputs)
    observed=[data['parts'][k] for k in ('scene','preview','samples','practice_profile')]
    fit_record(f.root,tone.direction_binding(tone.DEFAULT_PATH,data),observed,record_path=sample['outputs']['fit'],producer=master,checker=checker,mode='independent',review_task=key+'-fit',binding_mode='pre_confirmation_direction')
    finish(key+'-fit',[sample['outputs']['fit']])
    f.mutate('update',key,changes={'evidence':[tone.DEFAULT_PATH]},reason='SYNTHETIC current direction draft')
    f.check(key)
    put(f.root,key+'-display.md','SYNTHETIC displayed complete prior direction '+tone.direction_binding(tone.DEFAULT_PATH,data)['direction_sha256'])
    quote='SYNTHETIC fixture confirms this complete prior direction only: '+key
    put(f.root,key+'-response.md',quote)
    f.call('human_attention',id=key+'-REVIEW',kind='confirmation',task_id=key,display=key+'-display.md',scope='SYNTHETIC complete prior direction')
    f.call('human_attention',id=key+'-REVIEW',response=key+'-response.md')
    result=f.mutate('human_review',key,'PM',outcome='approved',person='SYNTHETIC fixture decider',presented_ref=key+'-display.md',source=key+'-response.md',quote=quote,scope='SYNTHETIC complete prior direction',attention_id=key+'-REVIEW')
    receipt=result['task']['human_review']['review_receipt']
    data['confirmation']=dict(person='SYNTHETIC fixture decider',quote=quote,source=key+'-response.md',direction_sha256=tone.direction_binding(tone.DEFAULT_PATH,data)['direction_sha256'],review_receipt=receipt)
    ref=draft();f.close(key)
    cache[token]=(ref,data);f.closed_expert_directions=cache
    return ref,data
