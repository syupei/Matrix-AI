"""Versioned input intake and production checks in the task transaction."""

from functools import lru_cache
import importlib.util
import json
from pathlib import Path
import re


READ_OPS = {'intake_status'}
WRITE_OPS = {'intake_register', 'intake_submit', 'intake_review', 'intake_admit', 'production_feedback', 'resolve_production_feedback'}
FIELDS = {'admitted_inputs', 'stage_transition', 'intake_review_id', 'practice_stage', 'practice_completion'}


@lru_cache(maxsize=1)
def load_gate():
    path = Path(__file__).resolve().parents[2] / 'base/tools/stage_gate.py'
    spec = importlib.util.spec_from_file_location('production_stage_gate', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def ref_latest(records):
    return {r.get('source_id', r['path']): r for r in sorted(records.values(), key=lambda r: r['sequence'])}


def master(pm, root, db, instance_id, profession):
    entry = pm.integrity.records(db, 'instance').get(instance_id, {})
    pm.require(entry.get('active') and entry.get('master') and entry.get('profession') == profession,
               'assign an active ' + profession + ' master to review this input')
    saved = entry.get('expert')
    requested = {k: saved[k] for k in ('id','version')} if saved else None
    identity = pm.team.experts.binding(pm, root, profession, requested)
    pm.require(identity == entry.get('expert', identity), 'reviewer expert binding changed; reload the appointment')
    return identity


def execute(pm, root, db, cmd):
    op = cmd['op']
    cfg = pm.config(db)
    records = pm.integrity.records(db, 'input_admission')
    if op == 'intake_status':
        return {'inputs': records, 'feedback': pm.integrity.records(db, 'production_feedback')}
    actor = cmd['actor']
    if op == 'production_feedback':
        task = pm.task_map(db).get(cmd.get('task_id'))
        actors = {task.get(k) for k in ('owner', 'executor', 'manager')} if task else set()
        pm.require(task and actor in actors, 'feedback requires the current task and its assigned actor')
        pm.require(pm.nonempty(cmd.get('instruction')), 'record the actual instruction as feedback')
        rec = dict(id=cmd['event_id'], task=task['id'], actor=actor, recipient=cfg['pm_actor'],
                   instruction=cmd['instruction'], at=pm.now(), status='pending')
        pm.integrity.save(pm, db, 'production_feedback', rec)
        return {'feedback': rec}

    if op == 'resolve_production_feedback':
        pm.require(actor == cfg['pm_actor'], 'PM disposes production feedback')
        rec=pm.integrity.records(db,'production_feedback').get(cmd.get('id'))
        pm.require(rec and rec['status']=='pending','pending production feedback required')
        action=cmd.get('disposition');pm.require(action in {'intake','change','rejected'} and pm.nonempty(cmd.get('reason')),'feedback disposition and reason required')
        target=cmd.get('target_id')
        if action!='rejected':
            kind='input_admission' if action=='intake' else 'change'
            target_record=pm.integrity.records(db,kind).get(target)
            pm.require(target_record,'feedback disposition must name an actual intake/change record')
            path=target_record['path'] if action=='intake' else target_record['source']
            digest=target_record['sha256'] if action=='intake' else target_record['source_sha256']
            pm.require(pm.integrity.file_hash(pm,root,path)==digest and rec['instruction'] in pm.local(root,path).read_text(encoding='utf-8'),
                       'feedback target must preserve the complete recorded instruction and current source bytes')
        rec.update(status='resolved',disposition=action,target_id=target,reason=cmd['reason'],resolved_by=actor,resolved_at=pm.now())
        pm.integrity.save(pm,db,'production_feedback',rec)
        return {'feedback':rec}

    key = cmd.get('id')
    pm.require(pm.nonempty(key) and re.fullmatch(pm.SAFE_ID, key), 'input id required')
    rec = records.get(key)
    if op != 'intake_review':
        pm.require(actor == cfg['pm_actor'], 'PM manages intake registration, routing and admission')
    if op == 'intake_register':
        pm.require(rec is None, 'register a new id for a new input version')
        path, version, source, profession = (cmd.get(k) for k in ('path', 'version', 'source', 'profession'))
        source_id = cmd.get('source_id')
        pm.require(pm.nonempty(source_id), 'stable source_id required for the input document family')
        supersedes = cmd.get('supersedes')
        if supersedes:
            old = records.get(supersedes)
            pm.require(old and old.get('source_id') == source_id and ref_latest(records).get(source_id, {}).get('id') == supersedes,
                       'supersedes must name the latest version of the same source_id')
        pm.require(all(pm.nonempty(v) for v in (path, version, source, profession)), 'path, version, source and profession required')
        path = Path(path).as_posix()
        pm.require(profession in pm.team.registries(pm, root), 'intake requires a registered profession')
        pm.require(not any(r['path'] == path and r['version'] == version for r in records.values()), 'input path/version already registered')
        peers=[r['id'] for r in ref_latest(records).values() if r['state']=='admitted' and r['profession']==profession and r['source_id']!=source_id]
        new_family=source_id not in ref_latest(records)
        pm.require(not (new_family and peers) or pm.nonempty(cmd.get('new_family_reason')),
                   'new source family alongside current admitted inputs needs new_family_reason and master coexistence review')
        rec = dict(id=key, state='registered', sequence=max((r['sequence'] for r in records.values()), default=0)+1,
                   path=path, version=version, source=source, source_id=source_id, supersedes=supersedes, profession=profession,
                   sha256=pm.integrity.file_hash(pm, root, path),new_family_reason=cmd.get('new_family_reason'),family_review_required=bool(new_family and peers))
    else:
        pm.require(rec and ref_latest(records)[rec.get('source_id', rec['path'])]['id'] == key, 'PM: input is missing or superseded')
        pm.require(pm.integrity.file_hash(pm, root, rec['path']) == rec['sha256'], 'PM: input changed; register a new version')
        if op == 'intake_submit':
            pm.require(rec['state'] in {'registered', 'reviewing'}, 'only pending versions can be routed')
            reviewer = cmd.get('master')
            identity = master(pm, root, db, reviewer, rec['profession'])
            rec.update(state='reviewing', master=reviewer, expert=identity, review=None)
        elif op == 'intake_review':
            pm.require(rec['state'] == 'reviewing' and actor == rec['master'], 'the assigned master records the review conclusion')
            pm.require(master(pm, root, db, actor, rec['profession']) == rec['expert'], 'master binding changed; PM must route again')
            for keyname in ('resolved_risks', 'resolved_conflicts'):
                pm.require(pm.strings(cmd.get(keyname)), keyname + ' must be a list (empty when none)')
            pm.require(cmd.get('outcome') in {'approved','changes_requested'} and pm.nonempty(cmd.get('conclusion'))
                       and pm.strings(cmd.get('open_items')), 'review outcome, conclusion and open_items list required')
            pm.require(cmd['outcome'] != 'approved' or not cmd['open_items'], 'resolve open risks and conflicts before approval')
            pm.require(type(cmd.get('human_required')) is bool, 'declare whether human confirmation is required')
            peers={r['id'] for r in ref_latest(records).values() if r['state']=='admitted' and r['profession']==rec['profession'] and r['source_id']!=rec['source_id']}
            coexist,conflict=cmd.get('coexists_with',[]),cmd.get('conflicts_with',[])
            pm.require(pm.strings(coexist) and pm.strings(conflict) and not set(coexist)&set(conflict) and
                       set(coexist)|set(conflict)==peers,'master must classify current same-profession admitted families with coexists_with/conflicts_with')
            rec['review'] = {k:cmd[k] for k in ('outcome','conclusion','resolved_risks','resolved_conflicts','open_items','human_required')}
            rec['review'].update(coexists_with=coexist,conflicts_with=conflict)
        elif op == 'intake_admit':
            peers={r['id'] for r in ref_latest(records).values() if r['state']=='admitted' and r['profession']==rec['profession'] and r['source_id']!=rec['source_id']}
            review=rec.get('review') or {}
            pm.require(set(review.get('coexists_with',[]))|set(review.get('conflicts_with',[]))==peers,
                       'current source families changed after review; master must review their coexistence again')
            pm.require(not peers or rec.get('new_family_reason') or any(r['source_id']==rec['source_id'] and r['id']!=rec['id'] for r in records.values()),
                       'new source family alongside current admitted inputs needs new_family_reason')
            pm.require(rec['state'] == 'reviewing' and (rec.get('review') or {}).get('outcome') == 'approved', 'assigned master approval is missing')
            pm.require(master(pm, root, db, rec['master'], rec['profession']) == rec['expert'], 'master binding changed; route again')
            if rec['review']['human_required']:
                people = pm.roster(root)
                pm.require(pm.nonempty(cmd.get('person')) and pm.nonempty(cmd.get('quote')), 'authorized person and actual confirmation quote required')
                if people:
                    person = people['people'].get(cmd['person'], {})
                    pm.require(set(person.get('decides', ())) & {'project', rec['profession']}, 'confirmation requires the relevant deciding person')
                expected = dict(input={k:rec[k] for k in ('id','source_id','version','path','sha256')},
                                master_review_sha256=load_gate().tone.practice.digest(rec['review']))
                receipt = pm.direction.bind_attention(pm, root, db, cmd.get('attention_id'), person=cmd['person'],
                    quote=cmd['quote'], scope=cmd.get('scope'), expected=expected)
                rec['confirmation'] = dict(person=cmd['person'], quote=cmd['quote'], review_receipt=receipt)
            for old_id in rec['review'].get('conflicts_with',[]):
                old=records[old_id];old.update(state='superseded',superseded_by=rec['id']);pm.integrity.save(pm,db,'input_admission',old)
            rec.update(state='admitted', admitted_by=actor)
    rec['updated_at'] = pm.now()
    pm.integrity.save(pm, db, 'input_admission', rec)
    return {'input': rec}


def task_professions(pm, root, db, task):
    registries=pm.team.registries(pm,root)
    aliases={name:profession for profession,registry in registries.items() for name in [profession,*registry.get('skills',[])]}
    instances=pm.integrity.records(db,'instance')
    names={task.get('role'),task.get('profession')}
    for key in ('owner','executor'):
        instance=instances.get(task.get(key),{})
        names.update((instance.get('profession'),instance.get('role')))
    return {aliases[name] for name in names if name in aliases}


def practice_check(pm, root, db, task, tasks, direction, phase):
    if task['id'] in direction or task.get('intake_review_id') or coordination_only(pm,db,task):
        return
    gate = load_gate()
    state = task.get('practice_stage')
    instances = pm.integrity.records(db, 'instance')
    owner = instances.get(task['owner'], {})
    executor = instances.get(task.get('executor'), {})
    profession = owner.get('profession') or owner.get('role')
    executing = executor.get('profession') or executor.get('role')
    professions = task_professions(pm,root,db,task)
    governed = {reg['id'] for reg in pm.team.registries(pm, root).values()
                if reg.get('framework_requirements')}
    inherited = False
    if state is None:
        parent = tasks.get(task.get('parent'), {})
        if parent.get('practice_stage'):
            state, inherited = parent['practice_stage'], True
        else:
            if phase != 'planning' and task.get('kind') in {'work','stage'}:
                sandbox_run = phase in {'entry','start'} and any(
                    run.get('admission_expert') and run['task_id'] == task['id'] and run['state'] in pm.platform.ACTIVE
                    for run in pm.integrity.records(db, 'launch').values())
                pm.require(sandbox_run or not professions & governed,
                           'record the professional practice stage and current prerequisites')
            return
    pm.require(isinstance(state, dict) and set(state) <= {'role', 'current', 'scope', 'practice_scope', 'tone_contract',
                                                          'practice_evidence', 'upstream', 'upstream_bundle', 'implementation_handoff', 'delivery_kind'},
               'practice_stage must contain the professional stage and its current prerequisite records')
    role, current = state['role'], state['current']
    pm.require(current in gate.STAGES.get(role, [])[:-1], 'practice_stage must name a registered professional stage')
    stage_profession, requirements = gate.framework(root, role, current)
    pm.require(professions & governed <= {stage_profession},
               'practice_stage must match the assigned and executing professions')
    scope = state.get('scope')
    pm.require(pm.strings(scope) and scope and len(scope) == len(set(scope)), 'practice_stage needs a unique workflow scope')
    if role=='design' and current=='D-4':
        pm.require(not state.get('practice_scope') or set(state['practice_scope'])==set(scope),
                   'D-4 practice_scope must match the assigned scope before dispatch')
    if phase == 'planning':
        return
    if task['state'] == 'done' and task.get('practice_receipt'):
        receipt = task['practice_receipt']
        snapshot, _ = gate.tone.evidence.verify_bundle(root, receipt['bundle'])
        frozen = json.loads(gate.checked_file(snapshot, receipt['state_path']).read_text())
        gate.check(snapshot, frozen, registry_root=root, seal=False)
        return
    gate.check_entry(root, state)
    increment = increment_context(pm,root,db,task,tasks,phase)
    if phase != 'complete':
        return
    ref = task.get('practice_completion')
    parent=tasks.get(task.get('parent'),{})
    implementation_child=(parent.get('practice_stage') or {}).get('current')=='E-3.2' and not review_child(pm,task,tasks)
    if implementation_child and not increment and not ref:
        return  # Later implementation items consume the first increment's receipt.
    if not ref and not requirements.get('complete') and task.get('kind') != 'stage' and not increment:
        return     # Finishing a work item does not advance its entire professional stage.
    pm.require(pm.nonempty(ref) and ref in task['evidence'],
               'hand over the current practice stage completion record')
    completed = json.loads(gate.checked_file(root, ref).read_text(encoding='utf-8'))
    pm.require(all(completed.get(key) == state.get(key) for key in ('role', 'current', 'scope', 'practice_scope')),
               'practice stage completion must match the dispatched stage and scope')
    pm.require(not state.get('tone_contract') or completed.get('tone_contract') == state['tone_contract'],
               'practice stage completion must use the dispatched tone contract')
    context=completion_context(pm,root,db,task,tasks,ref)
    if increment:context['increment_review']=True
    checked = gate.check(root, completed, registry_root=root,task_context=context)
    task['practice_receipt'] = {'bundle':checked['review_bundle'], 'state_path':checked['upstream_state'],
                                'tone_contract':completed.get('tone_contract'), 'increment_review':bool(checked.get('increment_review'))}


def installed_rules(pm, root):
    receipt=pm.local(root,'management/install-receipt.json')
    if receipt.is_file():
        data=json.loads(receipt.read_text(encoding='utf-8'))
        skills=data.get('skills_dir','.agents/skills').rstrip('/')+'/'
        return {row['path']:row['after'] for row in data.get('written',[]) if isinstance(row,dict)
                and isinstance(row.get('path'),str) and row['path'].startswith(('matrix/',skills)) and row.get('after')}
    manifest=pm.team.KIT/'MANIFEST.json'
    if manifest.is_file():
        return json.loads(manifest.read_text(encoding='utf-8')).get('files',{})
    return {}


def canonical_input(value):
    path=Path(value).as_posix()
    return path+'/' if value.endswith('/') and path != '.' else path


def within_output(path, outputs):
    return any(path == name or name.endswith('/') and path.startswith(name) for name in outputs)


def coordination_only(pm,db,task):
    return task.get('kind')=='coordination' or (task.get('kind')=='stage' and task['owner']==pm.config(db)['pm_actor'] and
        not task.get('executor') and not task.get('practice_stage') and task.get('outputs') and
        all(name.startswith('management/') for name in task['outputs']))


def governed(pm,root,db,task):
    return bool(task_professions(pm,root,db,task) or any(task.get(key) for key in FIELDS) or task.get('kind','work') in {'work','stage'})


def review_child(pm, task, tasks):
    """A declared independent inspection cannot deliver the parent's implementation."""
    target=task.get('review_for')
    if not target:return False
    parent=tasks.get(task.get('parent'),{})
    pm.require(target==parent.get('id'), 'review_for must name the managed parent')
    producers={parent.get('owner'),parent.get('executor')}-{None}
    pm.require(not producers & {task.get('owner'),task.get('executor')}, 'review child must be independent of the parent producers')
    outputs=task.get('outputs',[])
    ancestors=[];ancestor=parent;seen=set()
    while ancestor and ancestor.get('id') not in seen:
        seen.add(ancestor['id']);ancestors.extend(ancestor.get('outputs',[]))
        ancestor=tasks.get(ancestor.get('parent'),{})
    pm.require(outputs and all(not name.endswith('/') and Path(name).suffix.lower() in {'.json','.md','.txt'} and
               not within_output(name,[*parent.get('inputs',[]),*ancestors]) for name in outputs),
               'review child outputs must be separate inspection records, never ancestor business outputs')
    return True


def increment_context(pm,root,db,task,tasks,phase):
    state=task.get('practice_stage') or tasks.get(task.get('parent'),{}).get('practice_stage') or {}
    explicit=task.get('first_increment',False) or state.get('delivery_kind')=='first_operable_increment'
    parent=tasks.get(task.get('parent'),{})
    impl=(parent.get('practice_stage') or {}).get('current')=='E-3.2' and not review_child(pm,task,tasks)
    if not impl:return bool(explicit)
    siblings=[row for row in tasks.values() if row.get('parent')==parent['id'] and row.get('kind','work')=='work'
              and row.get('state') not in {'cancelled','deprecated'} and not review_child(pm,row,tasks)]
    # A registered child is not an increment until it actually starts or closes.
    active=[row for row in siblings if row.get('state') in {'running','waiting_review','done'} or row.get('input_provenance')]
    first=next((row for row in active if row.get('first_increment')),active[0] if active else task)
    if first['id']!=task['id'] and phase != 'planning':
        receipt=first.get('practice_receipt',{})
        pm.require(pm.effective_done(first,tasks) and receipt.get('increment_review'),
                   'complete the first actual increment and its fit/D6 receipt before subsequent implementation starts')
        gate=load_gate();view,_=gate.tone.evidence.verify_bundle(root,receipt['bundle'])
        frozen=json.loads(gate.checked_file(view,receipt['state_path']).read_text())
        checked=gate.check(view,frozen,registry_root=root,seal=False)
        pm.require(checked.get('increment_review'), 'first increment receipt must retain the increment review')
    return bool(explicit or first['id']==task['id'])


def task_boundary(pm,root,db,task,tasks,creator=None):
    instances=pm.integrity.records(db,'instance');cfg=pm.config(db)
    creator=creator or task.get('created_by')
    inspection=review_child(pm,task,tasks)
    parent=tasks.get(task.get('parent'),{})
    if parent and governed(pm,root,db,parent):
        pm.require(set(parent.get('admitted_inputs',[]))<=set(task.get('admitted_inputs',[])) and
                   set(parent.get('inputs',[]))<=set(task.get('inputs',[])), 'managed children must retain the parent admitted business inputs')
        pm.require(not parent.get('stage_transition') or task.get('stage_transition'), 'managed children retain upstream human confirmation')
        pm.require(inspection or not parent.get('practice_stage') or task.get('practice_stage')==parent['practice_stage'],
                   'managed implementation children must preserve the dispatched parent stage')
    if task.get('kind')=='coordination':
        pm.require(task['owner'] in {cfg['pm_actor'],cfg.get('frontdesk_actor')} and not task.get('executor'),
                   'coordination has a PM/frontdesk owner and no production executor')
        pm.require(all(path.startswith('management/') for path in task.get('outputs',[])), 'coordination writes management records only')
        return
    if task.get('kind')=='stage' and task['owner']==cfg['pm_actor'] and not task.get('executor'):
        return
    pm.require(all(iid in instances and instances[iid].get('active',True) for iid in
                   {task['owner'],task.get('executor')} - {None,cfg['pm_actor']}), 'register the actual owner and executor before production dispatch')
    pm.require(task['owner']!=cfg['pm_actor'] or task.get('executor') in instances,
               'PM production work needs a registered professional executor; use coordination for PM-only records')
    config=pm.team.read(pm,root,pm.team.CONFIG)[0] if pm.local(root,pm.team.CONFIG).is_file() else {}
    confirmed=pm.integrity.records(db,'instance_config')
    active=[row for row in instances.values() if row.get('active',True)]
    single=bool(confirmed and len(active)==1 and sum(row.get('count',0) for row in config.get('entries',[]))==1)
    pm.require(task['checker'] in instances and instances[task['checker']].get('active',True), 'registered active professional checker required')
    pm.require(single or task['checker'] not in {task['owner'],task.get('executor'),creator},
               'managed production requires a checker independent of creator, owner and executor')
    if task.get('kind')=='rule_maintenance':
        rules=installed_rules(pm,root)
        pm.require(task.get('inputs') and set(task['inputs'])<=set(rules) and task.get('outputs') and
                   set(task['outputs'])<=set(rules), 'rule maintenance is limited to existing frozen installed rule files')


def semantic_basis(pm,root,db,before,after,cmd,applying=None):
    changes=cmd.get('changes') or {}
    if not set(changes)&{'title','goal','next_action','inputs','outputs','criteria','source','direction'}:return
    ids=cmd.get('admission_basis',[]) or changes.get('admitted_inputs',[])
    records=pm.integrity.records(db,'input_admission');latest=ref_latest(records)
    if applying:
        change=pm.integrity.records(db,'change').get(applying,{})
        ids=list(dict.fromkeys([*ids,*[r['id'] for r in records.values() if r.get('path')==change.get('source') and r.get('sha256')==change.get('source_sha256')]]))
        needed=task_professions(pm,root,db,before)
        instances=pm.integrity.records(db,'instance')
        reviewed={instances[p].get('profession') for p,a in change.get('assessments',{}).items()
                  if p in instances and instances[p].get('active') and instances[p].get('master') and a.get('decision') in {'impacted','no_impact'}}
        pm.require(needed<=reviewed, 'change plan needs the affected professional masters assessment')
    pm.require(pm.strings(ids) and ids,'semantic production changes require an explicit currently admitted source basis')
    for key in ids:
        rec=records.get(key,{})
        pm.require(rec.get('state')=='admitted' and latest.get(rec.get('source_id'),{}).get('id')==key and
                   pm.integrity.file_hash(pm,root,rec['path'])==rec['sha256'], 'semantic source basis must be current and admitted')
    pm.require(set(ids)<=set(after.get('admitted_inputs',[])) and all(records[key]['path'] in after.get('inputs',[]) for key in ids),
               'bind the admitted change source and its path to the resulting task')


def upstream_confirmation(pm,root,db,task,up,files,phase):
    source=task_professions(pm,root,db,up);target=task_professions(pm,root,db,task)
    if not source or source & target:return None
    if phase=='planning':return None
    direction=pm.integrity.records(db,'direction_sample').get(up.get('id'))
    if direction and direction.get('closed') and 'code-engineering' not in target:
        tone=load_gate().tone
        data=tone.validate(root,tone.DEFAULT_PATH)
        pm.require(direction.get('reviewed_direction')==tone.direction_binding(tone.DEFAULT_PATH,data),
                   'direction milestone does not confirm this version')
        receipt=direction.get('confirmation_receipt')
        tone.evidence.verify_human_receipt(root,receipt,direction_sha256=direction['reviewed_direction']['direction_sha256'],authority_db=db)
        approved={value['path']:value['sha256'] for value in data['parts'].values()}
        approved[tone.DEFAULT_PATH]=pm.integrity.file_hash(pm,root,tone.DEFAULT_PATH)
        pm.require(all(approved.get(name)==sha for name,sha in files.items()), 'direction confirmation must cover the consumed handoff')
        return receipt
    gate=load_gate();receipt=up.get('practice_receipt') or (up.get('input_receipt') if not task.get('stage_transition') else None)
    state_ref=task.get('stage_transition') or up.get('stage_transition')
    if receipt:
        view,_=gate.tone.evidence.verify_bundle(root,receipt['bundle'])
        state=json.loads(gate.checked_file(view,receipt['state_path']).read_text())
    else:
        pm.require(pm.nonempty(state_ref),'cross-profession handoff needs the upstream human-review stage receipt')
        view=root;state=json.loads(gate.checked_file(root,state_ref).read_text())
    pm.require(state.get('current') in gate.REVIEW.get(state.get('role'),set()) and not state.get('delegated_decision'),
               'cross-profession handoff requires effective upstream human confirmation')
    if 'product' in source and 'code-engineering' in target:
        pm.require(state.get('role')=='product' and state.get('next')=='complete','complete and confirm the product flow before engineering')
    checked=gate.check(view,state,registry_root=root,seal=False)
    approved={r['path']:r['sha256'] for r in state['artifacts']}
    pm.require(all(approved.get(name)==digest for name,digest in files.items()), 'upstream human confirmation must cover the consumed handoff versions')
    return checked.get('review_bundle') or (receipt or {}).get('bundle')


def input_snapshot(pm,root,task,tasks=None,phase='entry'):
    saved=task.get('input_provenance')
    if not saved:return None
    gate=load_gate();view,bundle=gate.tone.evidence.verify_bundle(root,saved['bundle'])
    context=bundle['context']
    pm.require(context.get('task_id')==task['id'], 'frozen dispatch inputs belong to another task')
    context=json.loads(json.dumps(context))
    retained={canonical_input(path) for path in task.get('inputs',[])}
    context['sources']={path:source for path,source in context['sources'].items() if path in retained}
    context['inputs']=task.get('inputs',[])
    context['files']={name:sha for source in context['sources'].values() for name,sha in source['files'].items()}
    # An authorized reopen may consume a newly completed upstream revision. Never
    # refresh from live bytes alone, and never change a running task's input contract.
    if tasks and (phase == 'start' or task.get('state') not in {'running','done'} and phase in {'entry','planning'}):
        context=json.loads(json.dumps(context))
        reachable=set();pending=[task.get('parent'),*task.get('dependencies',[])]
        while pending:
            tid=pending.pop()
            if not tid or tid in reachable:continue
            reachable.add(tid);up=tasks.get(tid,{})
            pending.extend([up.get('parent'),*up.get('dependencies',[])])
        for path, source in list(context['sources'].items()):
            origins=source.get('origins', [source])
            if any(origin.get('task_id') not in reachable for origin in origins):
                # A manager may replace an already-consumed upstream task with a
                # successor. Re-resolve that input through normal admission; a
                # retained path alone must not keep the departed source forever.
                own=dict(task.get('handed_output_sha256',{}),**task.get('submitted_output_sha256',{}))
                evolved=[name for name,sha in source['files'].items()
                         if within_output(name,task.get('outputs',[])) and name in own and own[name]!=sha]
                pm.require(not evolved,'evolved input changed upstream; merge the prior work before rebinding: '+', '.join(evolved))
                del context['sources'][path]
                continue
            refreshed=[]
            for origin in origins:
                up=tasks.get(origin.get('task_id'), {})
                if up and pm.effective_done(up,tasks) and up.get('work_revision',0)>origin.get('work_revision',0):
                    files={name:sha for name,sha in up.get('handed_output_sha256',{}).items()
                           if name==path or path.endswith('/') and name.startswith(path)}
                    pm.require(files and all(pm.integrity.file_hash(pm,root,name)==sha for name,sha in files.items()),
                               'reworked input differs from its latest trusted handover: '+path)
                    refreshed.append(dict(task_id=up['id'],work_revision=up['work_revision'],files=files))
                else:refreshed.append(origin)
            source['files']={name:sha for origin in refreshed for name,sha in origin['files'].items()}
            if 'origins' in source:source['origins']=refreshed
            else:source.update(refreshed[0])
        context['files']={name:sha for row in context['sources'].values() for name,sha in row['files'].items()}
    for path,digest in context['files'].items():
        if not within_output(path,task.get('outputs',[])):
            if (phase=='entry' and task.get('state')=='done' and path==gate.tone.DEFAULT_PATH
                    and task.get('practice_receipt') and pm.integrity.file_hash(pm,root,path)!=digest):
                receipt=task['practice_receipt'];old_root,_=gate.tone.evidence.stage_receipt(root,receipt['bundle'])
                state=json.loads(gate.checked_file(old_root,receipt['state_path']).read_text())
                gate.tone.check_contract_scope(old_root,state['tone_contract'],root,scope=state['scope'],registry_root=root)
                source=context['sources'].get(path,{})
                if set(source.get('files',{}))=={path} and source.get('task_id') in task.get('dependencies',[]):
                    task.setdefault('_scope_dependency_revisions',{})[source['task_id']]=source['work_revision']
                continue
            pm.require(pm.integrity.file_hash(pm,root,path)==digest,'read-only dispatched input changed: '+path)
    return context


def freeze_input_sources(pm,root,task,sources):
    gate=load_gate();files={name:digest for row in sources.values() for name,digest in row['files'].items()}
    if not files:return
    previous=task.get('input_provenance');source_roots={}
    if previous:
        old_view, old = gate.tone.evidence.verify_bundle(root, previous['bundle'])
        if old['context'].get('sources') == sources:
            return
        # Preserve already consumed input bytes when a task legitimately edits its
        # own output, while refreshing another input from a new upstream handover.
        for name,digest in files.items():
            if old['context']['files'].get(name)==digest:
                source_roots[name]=old_view
    refs=[dict(path=name,sha256=digest) for name,digest in files.items()]
    context=dict(format='matrix-input-start/1',task_id=task['id'],inputs=task.get('inputs',[]),files=files,sources=sources)
    task['input_provenance']={'bundle':gate.tone.evidence.seal_bundle(root,refs,context,follow_refs=False,source_roots=source_roots)}


def completion_context(pm,root,db,task,tasks,completion):
    selected=[task]
    for row in tasks.values():
        if row['id']!=task['id'] and pm.team.within(row['id'],[task['id']],tasks) and pm.effective_done(row,tasks):selected.append(row)
    files={};producers={};review_files={};control_files=set();inspection_files=set();production_files=set()
    for row in selected:
        if row.get('practice_completion'):control_files.add(row['practice_completion'])
        handed=row.get('handed_output_sha256',{})
        if row['id']==task['id']:
            handed={name:pm.integrity.file_hash(pm,root,name) for name in row.get('evidence',[])
                    if name!=completion and pm.local(root,name).is_file() and within_output(name,row.get('outputs',[]))}
        (inspection_files if row.get('review_for') else production_files).update(handed)
        for name,digest in handed.items():
            if name!=completion:files[name]=digest;producers[name]=row.get('executor') or row['owner']
        review=row.get('review') or {}
        for name,digest in review.get('artifact_sha256',{}).items():
            files[name]=digest;producers[name]=review['checker'];review_files[name]=digest
    control_files.update(inspection_files-production_files)
    context=dict(task_id=task['id'],dispatched=task.get('practice_stage'),handed_files=files,producers=producers,review_files=review_files,control_files=sorted(control_files))
    state=json.loads(pm.local(root,completion).read_text())
    if state.get('current') in {'D-6','E-3.1','E-3.2'}:
        subjects={};subject_producers={}
        for item in state.get('artifacts',[]):
            candidates=[]
            for row in tasks.values():
                if 'code-engineering' not in task_professions(pm,root,db,row) or row.get('state') not in {'waiting_review','done'}:continue
                if not set(state['scope']) & set((row.get('practice_stage') or {}).get('scope',[])):continue
                handed=row.get('handed_output_sha256') if row['state']=='done' else row.get('submitted_output_sha256')
                if (handed or {}).get(item['path'])==item['sha256']:
                    candidates.append(row)
            if candidates:
                source=max(candidates,key=lambda row:row.get('updated_at',''))
                subjects[item['path']]=item['sha256']
                subject_producers[item['path']]=source.get('submitted_by') or source.get('executor') or source['owner']
        if subjects:
            unmatched=[item['path'] for item in state['artifacts'] if item['path'] not in subjects and files.get(item['path'])!=item['sha256']]
            pm.require(not unmatched,
                       'implementation artifacts must match a current trusted engineering handover or this task delivery: '+', '.join(unmatched))
            context.update(review_subjects=subjects,subject_producers=subject_producers,implementation=True)
    return context

def production_issues_impl(pm, root, db, task, tasks=None, phase='entry'):
    tasks = tasks or {}
    direction_samples = pm.integrity.records(db, 'direction_sample')
    direction = {tid: record for record in direction_samples.values() for tid in [record['id'], *record.get('tasks', [])]}
    try:
        historical = phase == 'entry' and task['state'] in pm.TERMINAL
        if not historical or task['state'] == 'done' and task.get('practice_stage'):
            practice_check(pm, root, db, task, tasks, direction, 'complete' if historical else phase)
    except (ValueError, KeyError, OSError, TypeError, AttributeError) as error:
        return [pm.integrity.issue('practice_stage', task['id'], str(error), responsible=pm.config(db)['pm_actor'])]
    if phase == 'entry' and task.get('state') == 'done' and task.get('input_receipt'):
        try:
            receipt=task['input_receipt'];gate=load_gate()
            snapshot,_=gate.tone.evidence.verify_bundle(root,receipt['bundle'])
            frozen=json.loads(gate.checked_file(snapshot,receipt['state_path']).read_text(encoding='utf-8'))
            gate.check(snapshot,frozen,registry_root=root,seal=False)
            return []
        except (ValueError, KeyError, OSError, TypeError, AttributeError) as error:
            return [pm.integrity.issue('production_admission',task['id'],str(error),responsible=pm.config(db)['pm_actor'])]
    registered = pm.integrity.records(db, 'input_admission')
    latest = ref_latest(registered)
    ids = task.get('admitted_inputs', [])
    inputs = task.get('inputs', [])
    origin = task.get('origin') or {}
    parent = tasks.get(task.get('parent'), {})
    instances = pm.integrity.records(db, 'instance')
    professions = task_professions(pm,root,db,task)
    professional = bool(professions & pm.team.registries(pm, root).keys())
    paths = {canonical_input(path):path for path in inputs}
    snapshot=input_snapshot(pm,root,task,tasks,phase) if task.get('input_provenance') else None
    input_sources={}
    requires = {path for path in paths if path in {row['path'] for row in latest.values()}}
    production=not coordination_only(pm,db,task) and task.get('kind')!='rule_maintenance'
    if production or professional and not coordination_only(pm,db,task):
        requires.update(paths)
    upstream = [parent, *(tasks.get(tid, {}) for tid in task.get('dependencies', []))]
    pending = list(upstream); seen_upstream = set()
    while pending:
        source_task = pending.pop()
        if not source_task or source_task.get('id') in seen_upstream:continue
        seen_upstream.add(source_task.get('id'))
        extra = [tasks.get(key, {}) for key in source_task.get('dependencies', [])]
        upstream.extend(extra);pending.extend(extra)
    # Every professional business input needs provenance, regardless of its path or owner label.
    frozen_rules=installed_rules(pm,root)
    for path in list(requires):
        trusted = False
        if snapshot and path in snapshot['sources']:
            trusted=True;input_sources[path]=snapshot['sources'][path]
        for up in sorted(upstream,key=lambda row:row.get('updated_at',''),reverse=True):
            if trusted:break
            declared = any(path == out or out.endswith('/') and path.startswith(out) for out in up.get('outputs', []))
            if not declared or up.get('kind') in {'coordination','rule_maintenance'} or up.get('intake_review_id') or not task_professions(pm,root,db,up):
                continue
            if phase == 'planning':
                trusted = True
            elif pm.effective_done(up, tasks):
                handed = up.get('handed_output_sha256', {})
                consumed={name:digest for name,digest in handed.items() if name==path or path.endswith('/') and name.startswith(path)}
                actual_files={file.relative_to(root).as_posix() for file in pm.local(root,path).rglob('*') if file.is_file()} if path.endswith('/') else {path}
                trusted=bool(consumed) and actual_files<=set(consumed) and all(pm.integrity.file_hash(pm,root,name)==digest for name,digest in consumed.items())
                if trusted:
                    same_direction=task['id'] in direction and up['id'] in direction and direction[task['id']]['id']==direction[up['id']]['id']
                    if not same_direction:upstream_confirmation(pm,root,db,task,up,consumed,phase)
                    input_sources[path]=dict(task_id=up['id'],work_revision=up.get('work_revision'),files=consumed)
            if trusted:
                break
        if not trusted and path.endswith('/') and phase!='planning':
            actual_names={p.relative_to(root).as_posix() for p in pm.local(root,path).rglob('*') if p.is_file()}
            combined={};origins=[]
            for up in upstream:
                if not up or up.get('kind') in {'coordination','rule_maintenance'} or up.get('intake_review_id') or not task_professions(pm,root,db,up) or not pm.effective_done(up,tasks) or not any(path==out or out.endswith('/') and path.startswith(out) for out in up.get('outputs',[])):continue
                consumed={name:digest for name,digest in up.get('handed_output_sha256',{}).items()
                          if name in actual_names and pm.integrity.file_hash(pm,root,name)==digest}
                if not consumed:continue
                same_direction=task['id'] in direction and up['id'] in direction and direction[task['id']]['id']==direction[up['id']]['id']
                if not same_direction:upstream_confirmation(pm,root,db,task,up,consumed,phase)
                combined.update(consumed);origins.append(dict(task_id=up['id'],work_revision=up.get('work_revision'),files=consumed))
            if actual_names and actual_names<=set(combined):
                trusted=True;input_sources[path]=dict(files=combined,origins=origins)
        actual = pm.local(root, path)
        if path in frozen_rules and actual.is_file() and pm.integrity.file_hash(pm,root,path) == frozen_rules[path]:
            trusted = True
        if trusted:
            requires.remove(path)
    if production and not task.get('intake_review_id') and task['id'] not in direction and task.get('kind') not in {'coordination','rule_maintenance'}:
        pm.require(ids or any(source for source in upstream if source.get('kind') not in {'coordination','rule_maintenance'} and not source.get('intake_review_id') and task_professions(pm,root,db,source) and any(within_output(path,source.get('outputs',[])) for path in paths)),
                   'professional production needs an admitted business source or declared upstream handoff; installed rules alone are not business input')
    if phase=='start' and input_sources:freeze_input_sources(pm,root,task,input_sources)
    requires.update(registered[i]['path'] for upstream_task in upstream for i in upstream_task.get('admitted_inputs', [])
                    if i in registered and registered[i]['path'] in paths)
    role = ' '.join(str(value) for value in professions if value)
    review_id = task.get('intake_review_id')
    if review_id:
        review = registered.get(review_id, {})
        outputs = task.get('outputs', [])
        try:
            pm.require(review.get('state') in {'reviewing','admitted'} and latest[review.get('source_id', review['path'])]['id']==review_id,
                       'PM: route the current input to its master before creating review work')
            reviewer_task = (task.get('owner') == review['master'] or parent.get('intake_review_id') == review_id and
                             parent.get('owner') == review['master'])
            pm.require(reviewer_task and inputs == [review['path']] and not ids and not task.get('stage_transition'),
                       'PM: the assigned master owns intake review work and its delegated review scope')
            pm.require(outputs and all(out.startswith('management/intake-reviews/') for out in outputs),
                       'intake review work may only submit review notes')
            pm.require(pm.integrity.file_hash(pm, root, review['path']) == review['sha256'], 'PM: review version changed')
        except (ValueError, KeyError, OSError, TypeError, AttributeError) as error:
            return [pm.integrity.issue('intake_review', task['id'], str(error), responsible=pm.config(db)['pm_actor'])]
        return []
    gate_ref = task.get('stage_transition')
    if not (ids or requires or gate_ref):
        return []
    try:
        pm.require(pm.strings(ids) and (ids or not requires) and len(ids)==len(set(ids)), 'PM: bind each current admitted input version')
        bound = {}
        for key in ids:
            r = registered.get(key)
            pm.require(r and r['state'] == 'admitted' and latest[r.get('source_id', r['path'])]['id']==key,
                       'PM and professional master: input is not admitted or has been superseded: '+key)
            pm.require(pm.integrity.file_hash(pm, root, r['path'])==r['sha256'], 'PM: register/review changed input '+r['path'])
            pm.require(r['path'] in paths, 'PM: include admitted path in task inputs: '+r['path'])
            bound[r['path']] = r['sha256']
        pm.require(requires <= set(bound), 'PM: review and bind inputs: '+', '.join(sorted(requires-set(bound))))
        if task['id'] in direction:
            return []
        pm.require(pm.nonempty(gate_ref), 'PM: attach the upstream role stage transition and confirmation')
        gate = load_gate()
        state = json.loads(pm.local(root, gate_ref).read_text(encoding='utf-8'))
        pm.require(state.get('current') in gate.REVIEW.get(state.get('role'), set()), 'PM: attach an upstream human-review stage')
        pm.require(not state.get('delegated_decision'), 'PM: effective upstream human confirmation required')
        if 'code-engineering' in role and any(registered[i]['profession']=='product' for i in ids):
            pm.require(state.get('role') == 'product' and state.get('next') == 'complete',
                       'product master: complete and confirm the product flow before engineering')
        # Admission queries validate current evidence without publishing a close.
        checked = gate.check(root, state, seal=phase == 'complete')
        if phase == 'complete':
            task['input_receipt']={'bundle':checked['review_bundle'],'state_path':checked['upstream_state']}
        artifacts = {a['path']:a['sha256'] for a in state['artifacts']}
        pm.require(all(artifacts.get(k)==v for k,v in bound.items()), 'PM: stage confirmation does not cover the admitted versions')
    except (ValueError, KeyError, OSError, TypeError, AttributeError) as error:
        return [pm.integrity.issue('production_admission', task['id'], str(error), responsible=pm.config(db)['pm_actor'])]
    return []


def production_issues(pm,root,db,task,tasks=None,phase='entry'):
    try:
        return production_issues_impl(pm,root,db,task,tasks,phase)
    except (ValueError,KeyError,OSError,TypeError,AttributeError) as error:
        return [pm.integrity.issue('production_admission',task['id'],str(error),responsible=pm.config(db)['pm_actor'])]


def submission(pm, root, task, paths):
    if not (task.get('admitted_inputs') or task.get('intake_review_id') or task.get('practice_completion')):
        return
    outputs = task.get('outputs', [])
    for path in paths:
        target = pm.local(root, path)
        pm.require(target.is_file() and any(path == out or (out.endswith('/') and path.startswith(out))
                                           for out in outputs), 'submission outside admitted task outputs: ' + path)
