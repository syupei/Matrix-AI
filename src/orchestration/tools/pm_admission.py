"""Versioned input intake and production checks in the task transaction."""

from functools import lru_cache
import importlib.util
import json
from pathlib import Path
import re


READ_OPS = {'intake_status'}
WRITE_OPS = {'intake_register', 'intake_submit', 'intake_review', 'intake_admit', 'production_feedback'}
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
        rec = dict(id=key, state='registered', sequence=max((r['sequence'] for r in records.values()), default=0)+1,
                   path=path, version=version, source=source, source_id=source_id, supersedes=supersedes, profession=profession,
                   sha256=pm.integrity.file_hash(pm, root, path))
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
            rec['review'] = {k:cmd[k] for k in ('outcome','conclusion','resolved_risks','resolved_conflicts','open_items','human_required')}
        elif op == 'intake_admit':
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
    if task['id'] in direction or task.get('intake_review_id'):
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
            if phase != 'planning' and task.get('kind') == 'work':
                sandbox_run = phase == 'entry' and any(
                    run.get('admission_expert') and run['task_id'] == task['id'] and run['state'] in pm.platform.ACTIVE
                    for run in pm.integrity.records(db, 'launch').values())
                pm.require(sandbox_run or not professions & governed,
                           'record the professional practice stage and current prerequisites')
            return
    pm.require(isinstance(state, dict) and set(state) <= {'role', 'current', 'scope', 'practice_scope', 'tone_contract',
                                                          'practice_evidence', 'upstream', 'upstream_bundle', 'implementation_handoff'},
               'practice_stage must contain the professional stage and its current prerequisite records')
    role, current = state['role'], state['current']
    pm.require(current in gate.STAGES.get(role, [])[:-1], 'practice_stage must name a registered professional stage')
    stage_profession, requirements = gate.framework(root, role, current)
    pm.require(professions & governed <= {stage_profession},
               'practice_stage must match the assigned and executing professions')
    scope = state.get('scope')
    pm.require(pm.strings(scope) and scope and len(scope) == len(set(scope)), 'practice_stage needs a unique workflow scope')
    if phase == 'planning':
        return
    if task['state'] == 'done' and task.get('practice_receipt'):
        receipt = task['practice_receipt']
        snapshot, _ = gate.tone.evidence.verify_bundle(root, receipt['bundle'])
        frozen = json.loads(gate.checked_file(snapshot, receipt['state_path']).read_text())
        gate.check(snapshot, frozen, registry_root=root, seal=False)
        if receipt.get('tone_contract'):
            gate.tone.confirmed_contract(root, receipt['tone_contract'])
        return
    gate.check_entry(root, state)
    if phase != 'complete' or inherited:
        return
    ref = task.get('practice_completion')
    if not ref and not requirements.get('complete') and task.get('kind') != 'stage':
        return     # Finishing a work item does not advance its entire professional stage.
    pm.require(pm.nonempty(ref) and ref in task['evidence'],
               'hand over the current practice stage completion record')
    completed = json.loads(gate.checked_file(root, ref).read_text(encoding='utf-8'))
    pm.require(all(completed.get(key) == state.get(key) for key in ('role', 'current', 'scope', 'practice_scope')),
               'practice stage completion must match the dispatched stage and scope')
    pm.require(not state.get('tone_contract') or completed.get('tone_contract') == state['tone_contract'],
               'practice stage completion must use the dispatched tone contract')
    checked = gate.check(root, completed)
    task['practice_receipt'] = {'bundle':checked['review_bundle'], 'state_path':checked['upstream_state'],
                                'tone_contract':completed.get('tone_contract')}


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


def production_issues(pm, root, db, task, tasks=None, phase='entry'):
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
    paths = {Path(path).as_posix():path for path in inputs}
    requires = {path for path in paths if path in {row['path'] for row in latest.values()}}
    if professional:
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
        for up in upstream:
            declared = any(path == out or out.endswith('/') and path.startswith(out) for out in up.get('outputs', []))
            if not declared:
                continue
            if phase == 'planning':
                trusted = True
            elif pm.effective_done(up, tasks):
                handed = up.get('handed_output_sha256', {})
                trusted = path in handed and pm.integrity.file_hash(pm, root, path) == handed[path]
            if trusted:
                break
        actual = pm.local(root, path)
        if path in frozen_rules and actual.is_file() and pm.integrity.file_hash(pm,root,path) == frozen_rules[path]:
            trusted = True
        if trusted:
            requires.remove(path)
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
        pm.require(pm.strings(ids) and ids and len(ids)==len(set(ids)), 'PM: bind each current admitted input version')
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
        checked = gate.check(root, state)
        if phase == 'complete':
            task['input_receipt']={'bundle':checked['review_bundle'],'state_path':checked['upstream_state']}
        artifacts = {a['path']:a['sha256'] for a in state['artifacts']}
        pm.require(all(artifacts.get(k)==v for k,v in bound.items()), 'PM: stage confirmation does not cover the admitted versions')
    except (ValueError, KeyError, OSError, TypeError, AttributeError) as error:
        return [pm.integrity.issue('production_admission', task['id'], str(error), responsible=pm.config(db)['pm_actor'])]
    return []


def submission(pm, root, task, paths):
    if not (task.get('admitted_inputs') or task.get('intake_review_id') or task.get('practice_completion')):
        return
    outputs = task.get('outputs', [])
    for path in paths:
        target = pm.local(root, path)
        pm.require(target.is_file() and any(path == out or (out.endswith('/') and path.startswith(out))
                                           for out in outputs), 'submission outside admitted task outputs: ' + path)
