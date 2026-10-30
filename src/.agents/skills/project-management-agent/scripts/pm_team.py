"""Project appointments and specialist obligations in the existing task database.

Records are cooperative facts. Authentication belongs to the host, not actor strings.
"""
import re

READ_OPS = {'team'}
WRITE_OPS = {'appoint', 'revoke_appointment', 'register_participation', 'participation_event', 'bind_participation'}


def within(tid, roots, tasks):
    seen = set()
    while tid and tid not in seen:
        if tid in roots:
            return True
        seen.add(tid)
        tid = tasks.get(tid, {}).get('parent')
    return False


def current(pm, root, appointment):
    if not appointment or not appointment.get('active'):
        return False
    try:
        return pm.integrity.file_hash(pm, root, appointment['source']) == appointment['source_sha256']
    except (ValueError, OSError):
        return False


def workspace(pm, root, iid):
    pm.require(re.fullmatch(pm.SAFE_ID, iid) is not None, 'simple instance id required')
    ref = '.agent-runtime/instances/' + iid
    # Check existing parents too; directory creation is left to the trusted runtime.
    pm.local(root, ref + '/workspace')
    return ref


def workflow_manager(pm, root, db, actor, parent, tasks):
    a = pm.integrity.records(db, 'appointment').get(actor)
    return bool(current(pm, root, a) and a['mode'] == 'workflow_pm' and
                within(parent, a['root_tasks'], tasks))


def authorize(pm, root, db, cmd, tasks):
    """Narrow delegated task writes without granting global PM privileges."""
    actor = cmd['actor']
    if actor == pm.config(db)['pm_actor']:
        return
    appointments = pm.integrity.records(db, 'appointment')
    a = appointments.get(actor)
    if not a:
        return  # Existing projects are not silently enrolled.
    op = cmd['op']
    t = cmd.get('task') if op == 'create' else tasks.get(cmd.get('task_id'))
    if not t:
        return
    tid = t.get('parent') if op == 'create' else t['id']
    # A revoked in-flight worker must still be able to yield and release resources.
    yielding = op == 'transition' and t['state'] == 'running' and cmd.get('state') == 'blocked' and cmd.get('stop_evidence')
    pm.require((current(pm, root, a) or yielding) and within(tid, a['root_tasks'], tasks), 'appointment inactive, stale or outside task scope')
    if op == 'create':
        pm.require(a['mode'] in {'lead', 'workflow_pm'}, 'executor cannot delegate without a lead appointment')
        pm.require(t.get('owner') in [actor, *a['delegates']], 'owner is outside allocated team')
        if t.get('project_level'):
            pm.require(a['mode'] == 'workflow_pm', 'only scoped workflow PM may create project-level work')
    target = (cmd.get('changes') or {}).get('executor') if op == 'update' else t.get('executor') if op == 'create' else cmd.get('new_owner') if op == 'handoff' else None
    if target:
        pm.require(target in [actor, *a['delegates']], 'execution instance is outside allocated team')


def blockers(pm, root, db, tasks, tid, closing=False):
    out = []
    t = tasks[tid]
    appointments = pm.integrity.records(db, 'appointment')
    relevant = any(within(tid, a['root_tasks'], tasks) for a in appointments.values())
    if relevant:
        for iid in {t['owner'], t.get('executor')} - {None}:
            a = appointments.get(iid)
            if not current(pm, root, a) or not within(tid, a['root_tasks'], tasks):
                out.append({'code': 'appointment_required', 'task': tid, 'instance': iid,
                            'action': 'appoint an authorized instance for this scope'})
    targets = {tid} if closing else set(t['dependencies'])
    pending = list(targets)
    while pending:
        k = pending.pop()
        upstream = tasks[k]['dependencies'] + tasks[k].get('completion_requires', []) + [x['id'] for x in tasks.values() if x['parent'] == k]
        for dep in upstream:
            if dep not in targets:
                targets.add(dep)
                pending.append(dep)
    if targets:
        for ob in pm.integrity.records(db, 'participation_obligation').values():
            if ob.get('superseded_by') or ob['mode'] != 'required_review' or not targets.intersection(ob['affected_tasks']):
                continue
            bound = tasks.get(ob.get('review_task'))
            try:
                source_current = pm.integrity.file_hash(pm, root, ob['source']) == ob['source_sha256']
            except (ValueError, OSError):
                source_current = False
            if not source_current or not bound or bound['work_revision'] != ob.get('work_revision') or not pm.effective_done(bound, tasks):
                out.append({'code': 'specialist_review_pending', 'task': tid, 'obligation': ob['id'],
                            'action': 'bind and complete the assigned specialist review on this baseline'})
    return out


def execute(pm, root, db, cmd):
    cfg, tasks = pm.config(db), pm.task_map(db)
    op, actor = cmd['op'], cmd.get('actor')
    if op == 'team':
        appointments = pm.integrity.records(db, 'appointment')
        return {'appointments': [dict(a, current=current(pm, root, a)) for a in appointments.values()],
                'participation': pm.integrity.records(db, 'participation_rule'),
                'obligations': pm.integrity.records(db, 'participation_obligation'),
                'limitation': 'Records do not authenticate people or start processes.'}
    rid = cmd.get('id')
    pm.require(pm.nonempty(rid), 'record id required')
    kind = 'appointment' if op in {'appoint', 'revoke_appointment'} else 'participation_rule' if op == 'register_participation' else 'participation_obligation'
    before = pm.integrity.records(db, kind).get(rid)
    if before:
        pm.require(cmd.get('expected_revision') == before['revision'], 'stale team record')
    else:
        pm.require(cmd.get('expected_revision') in {None, 0}, 'team record missing')
    if op == 'appoint':
        pm.require(actor == cfg['pm_actor'], 'project PM records appointments from actual designation evidence')
        spec = cmd['appointment']
        pm.require(set(spec) == {'mode', 'role', 'root_tasks', 'delegates', 'source'}, 'appointment fields: mode, role, root_tasks, delegates, source')
        pm.require(spec['mode'] in {'lead', 'executor', 'workflow_pm', 'auxiliary'}, 'unknown appointment mode')
        pm.require(spec['mode'] != 'workflow_pm' or spec['role'] == 'project-management-agent', 'workflow PM needs project management capability')
        instances = pm.integrity.records(db, 'instance')
        pm.require(rid in instances and instances[rid]['role'] == spec['role'], 'register matching actual instance first')
        pm.require(pm.strings(spec['root_tasks']) and spec['root_tasks'] and set(spec['root_tasks']) <= set(tasks), 'existing task roots required')
        pm.require(pm.strings(spec['delegates']) and rid not in spec['delegates'] and set(spec['delegates']) <= set(instances), 'allocated instances must be registered and distinct')
        pm.require(spec['mode'] in {'lead', 'workflow_pm'} or not spec['delegates'], 'execution/auxiliary mode has no team allocation')
        pm.require(not any(t['state'] == 'running' and rid in {t['owner'], t.get('executor')} for t in tasks.values()), 'stop active work before changing appointment')
        value = dict(spec, id=rid, active=True, workspace=workspace(pm, root, rid),
                     source_sha256=pm.integrity.file_hash(pm, root, spec['source']))
    elif op == 'revoke_appointment':
        pm.require(actor == cfg['pm_actor'] and before and pm.nonempty(cmd.get('reason')), 'PM revokes existing appointment with reason')
        value = dict(before, active=False, reason=cmd['reason'])
    elif op == 'register_participation':
        pm.require(actor == cfg['pm_actor'], 'PM registers project participation rules')
        spec = cmd['rule']
        pm.require(set(spec) == {'role', 'trigger', 'root_tasks', 'mode', 'source'}, 'explicit participation rule fields required')
        pm.require(pm.nonempty(spec['role']) and pm.nonempty(spec['trigger']), 'professional capability and trigger required')
        pm.require(spec['mode'] in {'consultation', 'required_review'}, 'unknown participation mode')
        pm.require(pm.strings(spec['root_tasks']) and spec['root_tasks'] and set(spec['root_tasks']) <= set(tasks), 'existing rule roots required')
        value = dict(spec, id=rid, source_sha256=pm.integrity.file_hash(pm, root, spec['source']))
    elif op == 'participation_event':
        pm.require(actor == cfg['pm_actor'] and before is None, 'PM records a new participation obligation')
        rule = pm.integrity.records(db, 'participation_rule').get(cmd['rule_id'])
        pm.require(rule and rule['revision'] == cmd['rule_revision'], 'current participation rule required')
        pm.require(pm.integrity.file_hash(pm, root, rule['source']) == rule['source_sha256'], 'participation authority changed')
        pm.require(cmd['trigger'] == rule['trigger'], 'trigger does not match rule')
        affected = cmd['affected_tasks']
        pm.require(pm.strings(affected) and affected and all(t in tasks and within(t, rule['root_tasks'], tasks) for t in affected), 'affected tasks outside participation scope')
        sha = pm.integrity.file_hash(pm, root, cmd['source'])
        key = [cmd['rule_id'], rule['revision'], cmd['trigger_id'], sha]
        pm.require(pm.nonempty(cmd['trigger_id']), 'stable trigger id required')
        for existing in pm.integrity.records(db, kind).values():
            if existing.get('key') == key:
                pm.require(existing['affected_tasks'] == affected, 'duplicate trigger has conflicting scope')
                return {'record': existing, 'duplicate': True}
        value = dict(id=rid, key=key, role=rule['role'], mode=rule['mode'], affected_tasks=affected,
                     source=cmd['source'], source_sha256=sha, state='awaiting_assignment')
        if cmd.get('supersedes'):
            old = pm.integrity.records(db, kind).get(cmd['supersedes'])
            pm.require(old and old['revision'] == cmd.get('supersedes_revision') and not old.get('superseded_by'), 'current prior obligation required')
            pm.require(old['key'][0] == cmd['rule_id'] and set(old['affected_tasks']) <= set(affected), 'replacement must preserve previous affected scope')
            old.update(superseded_by=rid, revision=old['revision']+1, updated_at=pm.now())
            pm.integrity.save(pm, db, kind, old)
            value['supersedes'] = old['id']
    else:
        pm.require(op == 'bind_participation' and actor == cfg['pm_actor'] and before, 'PM binds an existing specialist obligation')
        review = tasks.get(cmd['review_task'])
        pm.require(review and review.get('role') == before['role'], 'review task requires matching professional role')
        pm.require(review['id'] not in before['affected_tasks'] and not any(within(x, [review['id']], tasks) for x in before['affected_tasks']), 'review cannot close itself or its descendants')
        pm.require(not any(within(review['id'], [x], tasks) for x in before['affected_tasks']), 'review must not be a child of the gated work')
        pending = list(review['dependencies'] + review.get('completion_requires', [])); seen = set()
        while pending:
            k = pending.pop()
            if k in seen:
                continue
            seen.add(k)
            pm.require(k not in before['affected_tasks'], 'specialist review creates a completion wait cycle')
            pending.extend(tasks[k]['dependencies'] + tasks[k].get('completion_requires', []))
        value = dict(before, review_task=review['id'], work_revision=review['work_revision'], state='assigned')
    value.update(revision=(before or {}).get('revision', 0) + 1, updated_at=pm.now())
    pm.integrity.save(pm, db, kind, value)
    return {'record': value}
