"""Versioned input intake and production checks in the task transaction."""

from functools import lru_cache
import importlib.util
import json
from pathlib import Path
import re


READ_OPS = {'intake_status'}
WRITE_OPS = {'intake_register', 'intake_submit', 'intake_review', 'intake_admit', 'production_feedback'}
FIELDS = {'admitted_inputs', 'stage_transition', 'intake_review_id'}


@lru_cache(maxsize=1)
def load_gate():
    path = Path(__file__).resolve().parents[2] / 'base/tools/stage_gate.py'
    spec = importlib.util.spec_from_file_location('production_stage_gate', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def ref_latest(records):
    return {r['path']: r for r in sorted(records.values(), key=lambda r: r['sequence'])}


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
        pm.require(all(pm.nonempty(v) for v in (path, version, source, profession)), 'path, version, source and profession required')
        path = Path(path).as_posix()
        pm.require(profession in pm.team.registries(pm, root), 'intake requires a registered profession')
        pm.require(not any(r['path'] == path and r['version'] == version for r in records.values()), 'input path/version already registered')
        rec = dict(id=key, state='registered', sequence=max((r['sequence'] for r in records.values()), default=0)+1,
                   path=path, version=version, source=source, profession=profession,
                   sha256=pm.integrity.file_hash(pm, root, path))
    else:
        pm.require(rec and ref_latest(records)[rec['path']]['id'] == key, 'PM: input is missing or superseded')
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
                rec['confirmation'] = dict(person=cmd['person'], quote=cmd['quote'])
            rec.update(state='admitted', admitted_by=actor)
    rec['updated_at'] = pm.now()
    pm.integrity.save(pm, db, 'input_admission', rec)
    return {'input': rec}


def production_issues(pm, root, db, task, tasks=None):
    registered = pm.integrity.records(db, 'input_admission')
    latest = ref_latest(registered)
    ids = task.get('admitted_inputs', [])
    inputs = task.get('inputs', [])
    origin = task.get('origin') or {}
    tasks = tasks or {}
    parent = tasks.get(task.get('parent'), {})
    # Explicit external paths and a parent's admitted versions cannot be bypassed
    # by dropping admissions from a newly derived task.
    paths = {Path(path).as_posix():path for path in inputs}
    requires = {path for path in paths if path in latest or path.startswith(('external/', 'sources/')) or Path(path).stem.casefold() == 'prd'}
    upstream = [parent, *(tasks.get(tid, {}) for tid in task.get('dependencies', []))]
    requires.update(registered[i]['path'] for upstream_task in upstream for i in upstream_task.get('admitted_inputs', [])
                    if i in registered)
    role = task.get('role') or ''
    if 'code-engineering' in role:
        requires.update(path for path in paths if path.startswith('product/'))
    review_id = task.get('intake_review_id')
    if review_id:
        review = registered.get(review_id, {})
        outputs = task.get('outputs', [])
        try:
            pm.require(review.get('state') in {'reviewing','admitted'} and latest[review['path']]['id']==review_id,
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
            pm.require(r and r['state'] == 'admitted' and latest[r['path']]['id']==key,
                       'PM and professional master: input is not admitted or has been superseded: '+key)
            pm.require(pm.integrity.file_hash(pm, root, r['path'])==r['sha256'], 'PM: register/review changed input '+r['path'])
            pm.require(r['path'] in paths, 'PM: include admitted path in task inputs: '+r['path'])
            bound[r['path']] = r['sha256']
        pm.require(requires <= set(bound), 'PM: review and bind inputs: '+', '.join(sorted(requires-set(bound))))
        pm.require(pm.nonempty(gate_ref), 'PM: attach the upstream role stage transition and confirmation')
        gate = load_gate()
        state = json.loads(pm.local(root, gate_ref).read_text(encoding='utf-8'))
        pm.require(state.get('current') in gate.REVIEW.get(state.get('role'), set()), 'PM: attach an upstream human-review stage')
        pm.require(not state.get('delegated_decision'), 'PM: effective upstream human confirmation required')
        if 'code-engineering' in role and any(registered[i]['profession']=='product' for i in ids):
            pm.require(state.get('role') == 'product' and state.get('next') == 'complete',
                       'product master: complete and confirm the product flow before engineering')
        gate.check(root, state)
        artifacts = {a['path']:a['sha256'] for a in state['artifacts']}
        pm.require(all(artifacts.get(k)==v for k,v in bound.items()), 'PM: stage confirmation does not cover the admitted versions')
    except (ValueError, KeyError, OSError, TypeError, AttributeError) as error:
        return [pm.integrity.issue('production_admission', task['id'], str(error), responsible=pm.config(db)['pm_actor'])]
    return []


def submission(pm, root, task, paths):
    if not (task.get('admitted_inputs') or task.get('intake_review_id')):
        return
    outputs = task.get('outputs', [])
    for path in paths:
        target = pm.local(root, path)
        pm.require(target.is_file() and any(path == out or (out.endswith('/') and path.startswith(out))
                                           for out in outputs), 'submission outside admitted task outputs: ' + path)
