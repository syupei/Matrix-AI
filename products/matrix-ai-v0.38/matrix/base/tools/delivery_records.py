"""Validate professional delivery records, independently of practice profiles.

This binds declared results and candidate bytes. It does not grade professional
quality, discover omitted decisions, or authenticate human answers.
"""
import importlib.util
import json
import contextvars
import sqlite3
import re
from pathlib import Path

_spec=importlib.util.spec_from_file_location('delivery_evidence',Path(__file__).with_name('review_evidence.py'))
evidence=importlib.util.module_from_spec(_spec);_spec.loader.exec_module(evidence)
_authority=contextvars.ContextVar("delivery_authority",default=None)
require=evidence.require
IMPACTS=('channels','interaction','data','capacity_deployment','maintenance_cost','exit_migration')
LEVELS={'measured','prototype','estimate','experience','pending','not_applicable'}
KINDS=('product_impact','impact_review','acceptance_package','release_acceptance')
DEFINITIONS={f'delivery.{name}/1':{'record':f'delivery_records.{name}','version':1,
    'template':'matrix/base/delivery-records-template.json','trigger':'professional stage completion'} for name in KINDS}


# This professional handoff declaration is part of the imported-expert contract.
QA_HANDOFF_SUBMISSION={
    'version':1,'when':'before Q-4 handoff to release preparation',
    'completion':{'role':'quality','stage':'Q-4','receipt':'practice_receipt'},
    'consumer':{'role':'release','stage':'E-4.1'},
    'record':'delivery_records.acceptance_package',
    'checks':['current QA task completion','actual QA producer handover','immutable Q-4 receipt',
              'matching package digest','current candidate bytes'],
    'rule':'matrix/orchestration/PRODUCTION-ADMISSION.md#qa验收包交给发布准备'}


def framework_definition(key,stage):
    definition=dict(DEFINITIONS[key])
    if key=='delivery.acceptance_package/1' and stage=='Q-4':
        definition.update(version=2,submission=QA_HANDOFF_SUBMISSION)
    return definition


def text(value,label):
    require(isinstance(value,str) and bool(value.strip()),label+' must be nonempty text')


def fields(row,names,label):
    require(isinstance(row,dict),label+' must be an object')
    for key in names:text(row.get(key),label+'.'+key)


def rows(value,label,*,empty=False):
    require(isinstance(value,list) and (empty or value),label+' must be a '+('' if empty else 'nonempty ')+'list')
    return value



def artifact(root,ref):
    """Read content-addressed evidence at the authority, without copying old views."""
    name=ref.get('path','') if isinstance(ref,dict) else ''
    match=re.fullmatch(r'management/evidence/([0-9a-f]{64})/files/(.+)',name)
    if match:
        authority=_authority.get() or Path(root)
        manifest='management/evidence/'+match[1]+'/manifest.json'
        view,_=evidence.verify_bundle(authority,evidence.ref(authority,manifest))
        return evidence.verify_ref(view,dict(ref,path=match[2]))
    return evidence.verify_ref(root,ref)


def load(root,ref):
    path=artifact(root,ref)
    try:value=json.loads(path.read_text(encoding='utf-8'))
    except (ValueError,UnicodeError) as error:raise ValueError('invalid delivery JSON: '+ref['path']) from error
    require(isinstance(value,dict),'delivery JSON must be an object: '+ref['path'])
    return value


def declaration(registry):
    declared=registry.get('delivery_requirements',{})
    stages={stage for flow in registry.get('stage_flows',[]) for stage in flow['stages']}
    require(isinstance(declared,dict) and declared.keys()<=stages,'delivery requirements must use registered stages')
    for stage,value in declared.items():
        require(isinstance(value,dict) and set(value)=={'complete'},'delivery records are checked at completion: '+stage)
        keys=rows(value['complete'],'delivery requirements '+stage)
        require(len(keys)==len(set(keys)) and all(key in DEFINITIONS for key in keys),'unknown or duplicate delivery requirement: '+stage)
    return declared


def candidate(root,ref,kind):
    data=load(root,ref)
    require(ref.get('kind',data.get('kind'))==kind,'candidate must identify '+kind+' bytes')
    files=data.get('files')
    require(isinstance(files,dict) and files,'candidate manifest must contain a nonempty files mapping')
    for path,sha in files.items():artifact(root,dict(path=path,sha256=sha))
    return ref['sha256']


def same_candidate(left,right,label):
    require(isinstance(left,dict) and isinstance(right,dict) and left.get('sha256') and
            left.get('sha256')==right.get('sha256'),label+' belongs to another candidate')


def require_artifact(ref,artifacts):
    require(any(item.get('path')==ref.get('path') and item.get('sha256')==ref.get('sha256') for item in artifacts),
            'delivery business record must be included in stage artifacts: '+str(ref.get('path')))


def checked_record(root,ref,name,artifacts=None):
    value=load(root,ref)
    require(value.get('schema')==name+'/1','expected '+name+'/1: '+ref['path'])
    rows(value.get('scope'),'delivery scope')
    require(all(isinstance(s,str) and s.strip() for s in value['scope']),'delivery scope needs nonempty IDs')
    if artifacts is not None:require_artifact(ref,artifacts)
    return value


def impacts(root,data):
    candidate(root,data.get('candidate'),'plan')
    decisions=rows(data.get('decisions'),'product impact decisions',empty=True)
    seen=set();pending=[];excluded=[]
    for decision in decisions:
        fields(decision,('id','selection'),'decision')
        require(decision['id'] not in seen,'duplicate decision ID');seen.add(decision['id'])
        artifact(root,decision.get('source'))
        require(type(decision.get('screened_critical')) is bool,'decision screened_critical must be boolean')
        applicable=decision.get('product_effects')
        require(isinstance(applicable,list) and len(set(applicable))==len(applicable) and set(applicable)<=set(IMPACTS),
                'decision product_effects must name impact categories')
        required=decision['screened_critical'] or applicable
        card=decision.get('card')
        if not required:
            text(decision.get('no_card_reason'),'decision no_card_reason');excluded.append(decision['id'])
            if card is None:continue
        require(isinstance(card,dict),'missing product impact card: '+decision['id'])
        fields(card,('verification','limitations','reopen_when'),'impact card')
        require(type(card.get('default_choice')) is bool,'impact card default_choice must be boolean')
        effects=card.get('effects')
        require(isinstance(effects,dict) and set(effects)==set(IMPACTS),'impact card must address all six categories')
        for key,row in effects.items():
            fields(row,('conclusion','basis'),'impact '+key)
            level=row.get('level');require(level in LEVELS,'unknown impact evidence level: '+key)
            refs=rows(row.get('evidence',[]),'impact evidence',empty=True)
            for ref in refs:artifact(root,ref)
            require(level not in {'measured','prototype'} or refs,'measured/prototype impact needs actual evidence: '+key)
            if level in {'estimate','experience','pending'}:pending.append(decision['id']+':'+key)
    return {'decision_ids':sorted(seen),'excluded':sorted(excluded),'unverified_impacts':sorted(pending)}


def impact_review(root,data,artifacts):
    impact=checked_record(root,data.get('product_impact'),'product_impact',artifacts)
    same_candidate(data.get('candidate',{}),impact['candidate'],'impact review')
    result=impacts(root,impact)
    summary=rows(data.get('summary'),'impact summary',empty=True)
    ids=[]
    choices={row['id']:row['selection'] for row in impact['decisions']}
    for row in summary:
        fields(row,('decision_id','selection','main_impact','verification_state'),'impact summary')
        ids.append(row['decision_id'])
        require(row['selection']==choices.get(row['decision_id']),'impact summary selection differs from its decision')
    require(sorted(ids)==result['decision_ids'],'impact summary must list each decision exactly once')
    excluded=rows(data.get('excluded_decisions'),'excluded decisions',empty=True)
    for row in excluded:fields(row,('decision_id','reason'),'excluded decision')
    require(sorted(row['decision_id'] for row in excluded)==result['excluded'],'show all decisions without required cards and their reasons')
    return result


def acceptance(root,data):
    identity=candidate(root,data.get('candidate'),'implementation')
    require(data.get('stage') in {'Q-3','Q-4'},'acceptance package must identify Q-3 or Q-4')
    artifact(root,data.get('coverage'))
    entries=rows(data.get('entries'),'acceptance entries');seen=set();results={};open_defects=set()
    for row in entries:
        fields(row,('id','section'),'acceptance index')
        require(not set(row)&{'outcome','result','status','passed'},'acceptance index must reference results, not duplicate them')
        require(row['id'] not in seen,'duplicate acceptance item');seen.add(row['id'])
        artifact(root,row.get('source'))
        ref=row.get('inspection')
        if not ref:
            results[row['id']]='tool_unverified';continue
        proof=load(root,ref)
        require(proof.get('item_id')==row['id'],'inspection must bind the indexed item')
        outcome=proof.get('outcome')
        require(outcome in {'passed','failed','untested','blocked','not_applicable'},'invalid inspection outcome')
        fields(proof,('conclusion','owner'),'inspection')
        raw=rows(proof.get('evidence',[]),'inspection evidence',empty=True)
        for value in raw:artifact(root,value)
        if outcome=='passed':require(raw,'passed inspection requires evidence')
        else:fields(proof,('reason','next_action'),'incomplete inspection')
        # Old results remain visible without being relabelled as verified for this build.
        results[row['id']]=outcome if proof.get('candidate_sha256')==identity else 'evidence_unbound'
        for defect in rows(proof.get('defects',[]),'inspection defects',empty=True):
            fields(defect,('id','severity'),'defect');artifact(root,defect.get('source'))
            require(defect['severity'] in {'Q0','Q1','Q2','Q3','Q4','Q5'},'invalid defect severity')
            if defect.get('fixed'):
                retest=load(root,defect.get('retest'))
                require(retest.get('defect_id')==defect['id'] and retest.get('candidate_sha256')==identity,
                        'defect retest must link the defect and this candidate')
                require(retest.get('outcome')=='passed','a fixed defect requires a passed retest')
                for ref in rows(retest.get('evidence'),'defect retest evidence'):artifact(root,ref)
            else:open_defects.add('defect:'+defect['id'])
    text(data.get('implementer'),'acceptance implementer')
    trial=data.get('trial')
    fields(trial,('author','entry','environment','reset','limitations'),'human trial')
    require(trial['author']!=data.get('implementer'),'human trial must be authored independently of implementer')
    for step in rows(trial.get('steps'),'human trial steps'):
        fields(step,('action','expected','unacceptable'),'human trial step')
    slices=rows(data.get('core_tasks'),'core task evidence chain')
    for task in slices:
        fields(task,('id',),'core task')
        for key in ('entry','main_action','state_persistence','failure_recovery','observation'):
            value=task.get(key);require(isinstance(value,dict),'core task missing '+key)
            if value.get('not_applicable'):text(value.get('reason'),'core task '+key+' reason')
            else:
                text(value.get('item_id'),'core task '+key+' item')
                require(value['item_id'] in seen,'core task references unknown acceptance item')
    return {'results':results,'unresolved_items':sorted({key for key,value in results.items() if value not in {'passed','not_applicable'}}|open_defects)}


def qa_gap(root,authority,ref):
    value=load(root,ref)
    fields(value,('choice','qualification','person','quote'),'QA gap')
    require(value['choice'] in {'self','expert','human'},'use the existing QA gap choices')
    source=artifact(root,value.get('source')).read_text(encoding='utf-8')
    require(value['quote'] in source,'QA gap must preserve its actual decision source')
    database=Path(authority)/'management/runtime/tasks.sqlite3'
    if database.is_file():
        with evidence.authority_connection(authority) as db:
            row=db.execute("SELECT data FROM pm_records WHERE kind='gap' AND id=?",(value.get('gap_id'),)).fetchone()
            record=json.loads(row[0]) if row else {}
            active=[json.loads(row[0]) for row in db.execute("SELECT data FROM pm_records WHERE kind='instance'")]
        require(not any(row.get('active',True) and row.get('profession')=='quality-engineering' for row in active),
                'registered QA must provide its acceptance package')
        require(record.get('profession')=='quality-engineering' and record.get('decision',{}).get('choice')==value['choice']
                and record['decision'].get('quote')==value['quote'] and record['decision'].get('person')==value['person'],
                'QA gap must match the current recorded PM choice')
    text(value.get('non_specialist_label'),'QA gap qualification disclosure')
    return value



_companions={}
def companion(relative):
    path=Path(__file__).parents[2]/relative
    if relative not in _companions:
        spec=importlib.util.spec_from_file_location('delivery_'+path.stem,path)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        _companions[relative]=module
    return _companions[relative]


def qa_completion(root,data,package,authority):
    completion=data.get('qa_completion')
    require(isinstance(completion,dict) and completion.get('bundle') and completion.get('state_path'),
            'release needs the actual Q-4 completion receipt')
    view,manifest=evidence.stage_receipt(authority,completion['bundle'])
    context=manifest['context']
    require(context.get('role')=='quality' and context.get('stage')=='Q-4'
            and context.get('state_path')==completion['state_path'],'Q-4 completion must be a real quality Q-4 stage')
    state=load(view,dict(path=completion['state_path'],sha256=evidence.ref(view,completion['state_path'])['sha256']))
    ref=state.get('delivery_records',{}).get('acceptance_package',{})
    expected=data['acceptance_package']
    require(all(ref.get(key)==expected.get(key) for key in ('path','sha256')),
            'Q-4 completion must bind this exact acceptance package')
    gate=companion('base/tools/stage_gate.py')
    gate.check(view,state,conversation=True,registry_root=authority,seal=False)
    if (Path(authority)/'management/runtime/tasks.sqlite3').is_file():
        trusted=context.get('task_context') or {}
        pm=companion('orchestration/tools/pm_tasks.py')
        with evidence.authority_connection(authority) as db:
            db.row_factory=sqlite3.Row
            # Recheck the referenced QA gate, not every later release gate in the project.
            tasks=pm.task_map(db,gate_ids={trusted.get('task_id')});task=tasks.get(trusted.get('task_id'))
            instances=pm.integrity.records(db,'instance')
        producer=trusted.get('producers',{}).get(ref['path'])
        require(task and pm.effective_done(task,tasks) and task.get('practice_receipt',{}).get('bundle')==completion['bundle']
                and task['practice_receipt'].get('state_path')==completion['state_path'],
                'Q-4 completion must belong to a currently completed QA task')
        require(instances.get(producer,{}).get('profession')=='quality-engineering'
                and producer==package['trial']['author'] and trusted.get('handed_files',{}).get(ref['path'])==ref['sha256'],
                'Q-4 completion package must be the actual QA producer handover')
    return completion


def release(root,data,artifacts,authority):
    candidate(root,data.get('candidate'),'implementation')
    acceptance_ref=data.get('acceptance_package');unresolved=[]
    if acceptance_ref:
        package=checked_record(root,acceptance_ref,'acceptance_package')
        require(package.get('stage')=='Q-4','release needs the Q-4 acceptance package')
        same_candidate(data['candidate'],package['candidate'],'release acceptance')
        unresolved=acceptance(root,package)['unresolved_items']
        qa_completion(root,data,package,authority)
    else:
        qa_gap(root,authority,data.get('qa_gap'))
        for ref in rows(data.get('available_evidence'),'available acceptance evidence'):artifact(root,ref)
        unresolved=['qa_gap']
    impact_ref=data.get('product_impact')
    impact=checked_record(root,impact_ref,'product_impact')
    try:impact_result=impacts(root,impact)
    except ValueError as error:raise ValueError('impact cards must follow current decisions: '+str(error)) from error
    packet=load(root,data.get('decision_packet'))
    require(packet.get('schema')=='decision_packet/1','release needs decision_packet/1')
    same_candidate(data['candidate'],packet.get('candidate',{}),'release decision packet')
    require(packet.get('product_impact',{}).get('sha256')==impact_ref['sha256'],'release decision packet must reference current impact cards')
    if acceptance_ref:require(packet.get('acceptance_package',{}).get('sha256')==acceptance_ref['sha256'],'release decision packet must reference current acceptance package')
    else:require(packet.get('qa_gap',{}).get('sha256')==data['qa_gap']['sha256'],'release decision packet must disclose the QA gap')
    require(sorted(packet.get('unresolved_items',[]))==unresolved,'release decision packet must list every untested, blocked or unbound item')
    require(sorted(packet.get('unverified_impacts',[]))==impact_result['unverified_impacts'],
            'release decision packet must list estimated or pending product impacts')
    require_artifact(data['decision_packet'],artifacts)
    return dict(unresolved_items=unresolved,unverified_impacts=impact_result['unverified_impacts'])


def _check(root,state,registry,*,authority=None,task_context=None):
    declared=declaration(registry).get(state['current'],{}).get('complete',[])
    if not declared:return []
    root=Path(root);authority=Path(authority or root);artifacts=state['artifacts'];completed=[]
    for requirement in declared:
        name=requirement.split('.')[1].split('/')[0]
        ref=state.get('delivery_records',{}).get(name)
        require(ref,'missing delivery record: '+name)
        value=checked_record(root,ref,name,artifacts)
        if task_context:
            require(task_context.get('handed_files',{}).get(ref['path'])==ref['sha256'],
                    'delivery record must be an actual handover of this task: '+ref['path'])
        require(set(value['scope'])==set(state['scope']),'delivery record must cover the stage scope: '+name)
        if name=='product_impact':result=impacts(root,value)
        elif name=='impact_review':result=impact_review(root,value,artifacts)
        elif name=='acceptance_package':
            require(value.get('stage')==state['current'],'acceptance package stage mismatch')
            result=acceptance(root,value)
            if task_context:
                require(task_context.get('producers',{}).get(ref['path'])==value['trial']['author'],
                        'trial author must match the actual QA delivery producer')
        else:result=release(root,value,artifacts,authority)
        completed.append(dict(requirement=requirement,scope=state['scope'],record=ref,result=result))
    return completed


def check(root,state,registry,*,authority=None,task_context=None):
    token=_authority.set(Path(authority or root))
    try:return _check(root,state,registry,authority=authority,task_context=task_context)
    finally:_authority.reset(token)


def business_records(root,state,completed):
    """Validated review documents, not the scene/prototype being visually checked."""
    refs=[]
    for row in completed:
        ref=row['record'];refs.append(ref)
        value=load(root,ref)
        key={'impact_review':'product_impact','release_acceptance':'decision_packet'}.get(value['schema'].split('/')[0])
        if key:refs.append(value[key])
    return {row['path']:row['sha256'] for row in refs}


def main():
    import argparse
    parser=argparse.ArgumentParser(description='Print one professional delivery record template; validate records through stage_gate.')
    parser.add_argument('--template',required=True,choices=[*KINDS,'candidate','inspection','decision_packet','qa_gap'])
    args=parser.parse_args()
    templates=json.loads(Path(__file__).parents[1].joinpath('delivery-records-template.json').read_text(encoding='utf-8'))
    print(json.dumps(templates[args.template],ensure_ascii=False,indent=2))


if __name__=='__main__':main()
