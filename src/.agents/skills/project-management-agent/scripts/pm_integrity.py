"""Optional delivery/change records in the existing task database. No transport.

Actors and evidence are cooperative records, not authenticated identities.
Legacy tasks acquire no inferred requirements or retroactive approvals.
"""
import hashlib
import json
from pathlib import Path

WRITE_OPS = {'register_instance', 'register_scope', 'bind_delivery', 'record_change',
             'assess_change', 'apply_change_plan', 'close_change', 'pause_task', 'resume_task'}
READ_OPS = {'query', 'audit', 'changes'}


def records(db, kind):
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='pm_records'").fetchone():
        return {}
    return {r['id']: json.loads(r['data']) for r in db.execute(
        'SELECT id,data FROM pm_records WHERE kind=? ORDER BY id', (kind,))}


def save(pm, db, kind, value):
    db.execute('INSERT OR REPLACE INTO pm_records VALUES(?,?,?)',
               (kind, value['id'], pm.canon(value)))


def file_hash(pm, root, ref):
    path = pm.local(root, ref)
    pm.require(path.is_file(), 'missing evidence file: ' + ref)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def observe(pm, root, task):
    hashes = task.get('artifact_digests', {})
    actual = {}
    for ref in hashes:
        try:
            actual[ref] = file_hash(pm, root, ref)
        except (ValueError, OSError):
            actual[ref] = None
    if hashes:
        task['_observed_artifacts'] = actual
    else:
        task.pop('_observed_artifacts', None)
    return task


def project_level(task, cfg):
    return task.get('kind', 'work') == 'work' and task.get(
        'project_level', task['parent'] is None and task['manager'] == cfg['pm_actor'])


def related(tasks, roots):
    found = set(roots)
    while True:
        more = {t['id'] for t in tasks.values() if t.get('parent') in found or
                set(t['dependencies'] + t.get('completion_requires', [])) & found}
        if more <= found:
            return found
        found |= more


def issue(code, task, action, **fields):
    return dict(code=code, task_id=task, action=action, **fields)


def scope_issues(pm, root, scope, tasks):
    problems = []
    tid = scope['root_task']
    try:
        current = file_hash(pm, root, scope['source']['path'])
    except (ValueError, OSError):
        current = None
    if current != scope['source_sha256']:
        problems.append(issue('scope_source_changed', tid, 'reconcile the collection through a recorded change', scope_id=scope['id']))
    if not scope['known_complete']:
        problems.append(issue('scope_unknown', tid, 'resolve or explicitly bound the remaining scope', scope_id=scope['id']))
    for member in scope['members']:
        for exit_name in scope['required_exits']:
            bound = scope['bindings'].get(member, {}).get(exit_name)
            code = None
            if not bound or bound['task_id'] not in tasks:
                code = 'delivery_unmapped'
            else:
                t = tasks[bound['task_id']]
                if t['work_revision'] != bound['work_revision'] or not pm.effective_done(t, tasks):
                    code = 'delivery_not_current'
                elif exit_name == 'qa' and t['checker'] == t['owner']:
                    code = 'independent_check_missing'
                elif exit_name == 'human' and not t['human_required']:
                    code = 'human_gate_missing'
                elif exit_name == 'adoption':
                    try:
                        valid = file_hash(pm, root, bound['adoption_source']) == bound['adoption_sha256']
                    except (KeyError, ValueError, OSError):
                        valid = False
                    if not valid:
                        code = 'adoption_evidence_missing'
            if code:
                problems.append(issue(code, tid, 'link or complete the current scoped delivery evidence',
                                      scope_id=scope['id'], member_id=member, exit=exit_name))
    return problems


def blockers(pm, root, db, tasks, tid, closing=False, applying=None):
    result = []
    for change in records(db, 'change').values():
        if change['id'] == applying or change['state'] in {'closed', 'superseded'}:
            continue
        roots = list(change['affected_tasks'])
        roots += [s['root_task'] for sid, s in records(db, 'scope').items() if sid in change['scope_ids']]
        affected = related(tasks, roots)
        closing_affected = set(affected)
        if closing:
            for scope in records(db, 'scope').values():
                bound_ids = {b['task_id'] for row in scope['bindings'].values() for b in row.values()}
                if bound_ids & affected:
                    closing_affected.add(scope['root_task'])
            for child in list(closing_affected):
                parent = tasks.get(child, {}).get('parent')
                while parent:
                    closing_affected.add(parent)
                    parent = tasks[parent]['parent']
        if tid not in (closing_affected if closing else affected):
            continue
        if change['state'] != 'planned':
            result.append(issue('change_plan_pending', tid, 'complete impact assessments and apply the plan', change_id=change['id']))
        try:
            unchanged = file_hash(pm, root, change['source']) == change['source_sha256']
        except (ValueError, OSError):
            unchanged = False
        if not unchanged:
            result.append(issue('change_source_changed', tid, 'record the new input as a new change', change_id=change['id']))
    task = tasks[tid]
    if task.get('artifact_digests') and task.get('_observed_artifacts') != task['artifact_digests']:
        result.append(issue('artifact_changed', tid, 're-read the changed artifacts and update their registered digests'))
    if not closing and task['state'] not in pm.TERMINAL and task.get('executor'):
        instances = records(db, 'instance')
        mine = instances.get(task['executor'])
        if mine:
            for other in tasks.values():
                if other['id'] == tid or other['state'] != 'running':
                    continue
                theirs = instances.get(other.get('executor'))
                if not theirs:
                    continue
                overlap = any(a == b or a in b.parents or b in a.parents
                              for a in [pm.local(root, p) for p in mine.get('write_roots', [])]
                              for b in [pm.local(root, p) for p in theirs.get('write_roots', [])])
                if mine['endpoint'] == theirs['endpoint'] or overlap:
                    result.append(issue('instance_or_write_busy', tid, 'wait for the recorded executor to stop or partition write ownership', other_task=other['id']))
    if closing:
        for scope in records(db, 'scope').values():
            if scope['root_task'] == tid:
                result += scope_issues(pm, root, scope, tasks)
    return result


def audit(pm, root, db, tasks, cmd):
    selected = cmd.get('task_ids', list(tasks))
    pm.require(pm.strings(selected) and all(t in tasks for t in selected), 'unknown audit task ids')
    problems = []
    for tid in selected:
        problems += blockers(pm, root, db, tasks, tid, closing=True)
    pauses = []
    for p in records(db, 'pause').values():
        if p['state'] != 'paused' or p['task_id'] not in selected:
            continue
        after = tasks.get(p['resume_after'])
        pauses.append(dict(task_id=p['task_id'], checkpoint=p['checkpoint'], remaining=p['remaining'],
                           resume_when=p['resume_when'], ready_to_review=bool(after and pm.effective_done(after, tasks)),
                           version_changed=tasks[p['task_id']]['work_revision'] != p['work_revision']))
    return dict(issues=problems, resume_candidates=pauses, checked_tasks=len(selected),
                limitation='Checks registered relationships and evidence, not unrecorded intent or professional quality.')


def query(pm, root, db, tasks, cfg, cmd):
    instances = records(db, 'instance')
    level = cmd.get('level', 'project')
    pm.require(level in {'project', 'children', 'all'}, 'invalid query level')
    if level == 'children':
        pm.require(cmd.get('parent') in tasks, 'query parent missing')
    selected = []
    for t in tasks.values():
        if level == 'project' and not project_level(t, cfg):
            continue
        if level == 'children' and t['parent'] != cmd['parent']:
            continue
        role = instances.get(t['owner'], {}).get('role', t.get('role') or t['owner'])
        if cmd.get('role') and role != cmd['role']:
            continue
        if cmd.get('instance') and cmd['instance'] not in {t['owner'], t.get('executor')}:
            continue
        closing_issues = blockers(pm, root, db, tasks, t['id'], closing=True)
        selected.append(dict(t, role=role, state_label=pm.STATE_NAMES[t['state']], integrity_issues=closing_issues,
                             _current_gate=bool(closing_issues), current_complete=pm.effective_done(t, tasks) and not closing_issues))
    return dict(level=level, registered_scope_only=True, counts=pm.counts(selected, tasks), tasks=selected,
                instances=instances, unmapped_owners=sorted({t['owner'] for t in tasks.values() if t['owner'] not in instances and not t.get('role')}), revision=db.execute('SELECT COALESCE(MAX(seq),0) FROM events').fetchone()[0],
                observed_at=pm.now(), limitation='An observation time is not the last execution time; endpoints are not liveness proofs.')


def change_ledger(pm, db, tasks, cmd):
    rows = []
    for change in records(db, 'change').values():
        if cmd.get('id') and cmd['id'] not in {change['id'], change.get('change_no')}:
            continue
        if cmd.get('state') and cmd['state'] != change['state']:
            continue
        ids = set(change['affected_tasks']) | {d['task_id'] for d in change.get('dispositions', [])}
        linked = [dict(id=tid, title=tasks[tid]['title'], state=tasks[tid]['state'],
                       state_label=pm.STATE_NAMES[tasks[tid]['state']],
                       remark=tasks[tid].get('deprecation', {}).get('remark', ''))
                  for tid in sorted(ids) if tid in tasks]
        rows.append(dict(change, change_no=change.get('change_no', change['id']), tasks=linked))
    rows.sort(key=lambda c: (c.get('sequence', 0), c['id']))
    return dict(changes=rows, total=len(rows), observed_at=pm.now(),
                revision=db.execute('SELECT COALESCE(MAX(seq),0) FROM events').fetchone()[0])


def deprecation(pm, db, tid, change_id, applying=None):
    change = records(db, 'change').get(change_id)
    pm.require(change and (change['state'] == 'planned' or change['id'] == applying),
               'deprecation requires an assessed change plan')
    dispositions = change.get('dispositions', []) if change['state'] == 'planned' else [
        d for a in change['assessments'].values() for d in a.get('dispositions', [])]
    pm.require(any(d['task_id'] == tid and d['action'] == 'cancel' for d in dispositions),
               'deprecation requires an assessed change cancellation')
    number = change.get('change_no', change['id'])
    title = change.get('title') or change['quote']
    return dict(change_id=change['id'], change_no=number, requirement=title,
                remark='受 （' + number + '） ' + title + ' 需求调整变更', at=pm.now())


def execute(pm, root, db, cmd):
    op, actor = cmd['op'], cmd.get('actor')
    cfg, tasks = pm.config(db), pm.task_map(db)
    scopes, changes = records(db, 'scope'), records(db, 'change')
    if op == 'audit':
        return audit(pm, root, db, tasks, cmd)
    if op == 'query':
        return query(pm, root, db, tasks, cfg, cmd)
    if op == 'changes':
        return change_ledger(pm, db, tasks, cmd)
    kind = {'register_instance': 'instance', 'register_scope': 'scope', 'bind_delivery': 'scope',
            'record_change': 'change', 'assess_change': 'change', 'apply_change_plan': 'change',
            'close_change': 'change', 'pause_task': 'pause', 'resume_task': 'pause'}[op]
    table = records(db, kind)
    if op == 'record_change':
        sequence = max([c.get('sequence', 0) for c in changes.values()] or [0]) + 1
        reserved = {c.get('change_no', c['id']) for c in changes.values()} | set(changes)
        while 'CHG-' + str(sequence).zfill(6) in reserved:
            sequence += 1
        change_no = 'CHG-' + str(sequence).zfill(6)
        rid = cmd.get('id', change_no)
    else:
        rid = cmd['id']
    pm.require(pm.nonempty(rid), 'record id required')
    before = table.get(rid)
    if before:
        pm.require(cmd.get('expected_revision') == before['revision'], 'stale record revision')
    else:
        pm.require(cmd.get('expected_revision') in {None, 0}, 'record missing')
    value = json.loads(pm.canon(before)) if before else {'id': rid, 'revision': 0}
    if op == 'register_instance':
        pm.require(actor == cfg['pm_actor'], 'only PM registers instances')
        spec = cmd['instance']
        pm.require(set(spec) <= {'role','endpoint','write_roots','batch_limit'}, 'unknown instance fields')
        pm.require(type(spec.get('batch_limit', 1000)) is int and 1 <= spec.get('batch_limit', 1000) <= 1000, 'invalid batch_limit')
        pm.require(all(pm.nonempty(spec.get(k)) for k in ['role', 'endpoint']), 'role and real endpoint required')
        pm.require(pm.strings(spec.get('write_roots', [])), 'write_roots must be paths')
        for ref in spec.get('write_roots', []):
            pm.require(pm.local(root, ref) != root, 'instance cannot own the whole project')
        if before and any(t['state'] == 'running' and rid in {t['owner'], t.get('executor')} for t in tasks.values()):
            pm.require(all(before.get(k) == v for k, v in spec.items()), 'stop active instance before changing its route')
        value.update(spec)
    elif op == 'register_scope':
        tid = cmd.get('root_task', value.get('root_task'))
        pm.require(tid in tasks and actor in {tasks[tid]['owner'], tasks[tid]['manager']}, 'scope owner/manager required')
        source = cmd['source']
        path = pm.local(root, source['path'])
        raw = json.loads(path.read_text(encoding='utf-8'))
        for key in source.get('keys', []):
            raw = raw[key]
        pm.require(isinstance(raw, list), 'scope source must select a JSON list')
        members = [v[source['id_key']] if isinstance(v, dict) else v for v in raw]
        pm.require(pm.strings(members) and len(members) == len(set(members)), 'unique stable member ids required')
        exits = cmd['required_exits']
        pm.require(bool(exits) and set(exits) <= {'production', 'qa', 'human', 'adoption'}, 'invalid delivery exits')
        pm.require(type(cmd['known_complete']) is bool, 'known_complete must be boolean')
        digest = file_hash(pm, root, source['path'])
        if before and (members != before['members'] or exits != before['required_exits'] or digest != before['source_sha256'] or cmd['known_complete'] != before['known_complete'] or tid != before['root_task']):
            change = changes.get(cmd.get('change_id'))
            pm.require(change and rid in change['scope_ids'] and change['state'] != 'closed', 'scope amendment needs a recorded change')
            pm.require(pm.nonempty(cmd.get('scope_authorization')), 'scope amendment authorization required')
        value.update(root_task=tid, source=source, source_sha256=digest, members=members,
                     known_complete=cmd['known_complete'], required_exits=exits, bindings=value.get('bindings', {}))
    elif op == 'bind_delivery':
        pm.require(before is not None, 'scope missing')
        pm.require(actor in {tasks[value['root_task']]['owner'], tasks[value['root_task']]['manager']}, 'scope owner/manager required')
        member, exit_name = cmd['member_id'], cmd['exit']
        pm.require(member in value['members'] and exit_name in value['required_exits'], 'unknown member or exit')
        tid = cmd['task_id']
        pm.require(tid in tasks and cmd['work_revision'] == tasks[tid]['work_revision'], 'bind the current task version')
        pm.require(tid != value['root_task'], 'delivery evidence must not be the collection parent itself')
        bound = dict(task_id=tid, work_revision=cmd['work_revision'])
        if exit_name == 'adoption':
            bound.update(adoption_source=cmd['adoption_source'], adoption_sha256=file_hash(pm, root, cmd['adoption_source']))
        value['bindings'].setdefault(member, {})[exit_name] = bound
    elif op == 'record_change':
        pm.require(before is None, 'new input requires a new change id')
        affected = cmd.get('affected_tasks', [])
        pm.require(pm.strings(affected) and all(t in tasks for t in affected), 'unknown affected tasks')
        allowed = {cfg['pm_actor'], cfg.get('frontdesk_actor')} | {tasks[t]['owner'] for t in affected}
        pm.require(actor in allowed, 'change receiver must be a coordinator or affected owner')
        pm.require(cmd.get('analysis_task') in tasks, 'register an impact-analysis task first')
        parties = cmd['participants']
        pm.require(pm.strings(parties) and parties and len(set(parties)) == len(parties), 'unique impact participants required')
        pm.require(set(cmd.get('scope_ids', [])) <= set(scopes), 'unknown affected scopes')
        pm.require(cmd['type'] in {'add', 'modify', 'remove', 'mixed'} and pm.nonempty(cmd.get('quote')), 'change type and original quote required')
        inherited_tasks, inherited_scopes = set(affected), set(cmd.get('scope_ids', []))
        prior = changes.get(cmd.get('supersedes'))
        if cmd.get('supersedes'):
            pm.require(actor == cfg['pm_actor'] and prior and prior['state'] not in {'closed','superseded'}, 'PM may supersede an open change')
            pm.require(pm.nonempty(cmd.get('supersession_authorization')), 'explicit replacement basis required')
            inherited_tasks.update(prior['affected_tasks'])
            inherited_scopes.update(prior['scope_ids'])
            parties = list(dict.fromkeys(prior['participants'] + parties))
            prior.update(state='superseded', superseded_by=rid, revision=prior['revision']+1, updated_at=pm.now())
            save(pm, db, 'change', prior)
            value['supersedes'] = prior['id']
        pm.require('id' not in cmd or not (rid.startswith('CHG-') and rid[4:].isdigit()) or rid == change_no,
                   'CHG numbers are allocated by the ledger; omit id or use a non-numbered alias')
        pm.require(pm.nonempty(cmd.get('title', cmd['quote'])), 'requirement title required')
        value.update(change_no=change_no, sequence=sequence, created_at=pm.now(), title=cmd.get('title', cmd['quote']),
                     type=cmd['type'], source=cmd['source'], source_sha256=file_hash(pm, root, cmd['source']),
                     quote=cmd['quote'], affected_tasks=sorted(inherited_tasks), scope_ids=sorted(inherited_scopes),
                     analysis_task=cmd['analysis_task'], participants=parties, assessments={}, state='assessing')
    elif op == 'assess_change':
        pm.require(before and value['state'] == 'assessing' and actor in value['participants'], 'assigned impact participant required')
        a = cmd['assessment']
        pm.require(a.get('decision') in {'impacted', 'no_impact', 'pending'} and pm.nonempty(a.get('reason')), 'assessment decision and basis required')
        pm.require(isinstance(a.get('dispositions', []), list), 'dispositions must be a list')
        for d in a.get('dispositions', []):
            pm.require(d.get('action') in {'new', 'update', 'rework', 'keep', 'cancel', 'replace', 'defer'} and pm.nonempty(d.get('task_id')), 'task disposition required')
            if d['task_id'] in tasks:
                pm.require(actor == tasks[d['task_id']]['owner'], 'only the affected owner assesses a task disposition')
            if d['action'] in {'rework', 'replace'}:
                pm.require(d.get('replaces') in tasks, 'successor must name the historical task it replaces')
                pm.require(tasks[d['replaces']]['owner'] == actor, 'only the original owner may propose replacing a task')
            if d['action'] == 'defer':
                pm.require(pm.nonempty(d.get('trigger')), 'deferral needs a concrete trigger')
        for c in a.get('commands', []):
            pm.require(c.get('op') in {'create', 'update', 'transition'} and c.get('actor') == actor, 'participants prepare only their own task commands')
        if a['decision'] == 'no_impact':
            pm.require(not a.get('commands') and not a.get('dispositions'), 'no-impact assessment cannot mutate tasks')
        value['assessments'][actor] = a
        value['affected_tasks'] = sorted(set(value['affected_tasks']) | {d['task_id'] for d in a.get('dispositions', []) if d['task_id'] in tasks}
                                         | {d['replaces'] for d in a.get('dispositions', []) if d.get('replaces')})
    elif op == 'apply_change_plan':
        pm.require(actor == cfg['pm_actor'] and before and value['state'] == 'assessing', 'PM applies an assessed plan')
        pm.require(all(p in value['assessments'] and value['assessments'][p]['decision'] != 'pending' for p in value['participants']), 'impact assessment incomplete')
        pm.require(file_hash(pm, root, value['source']) == value['source_sha256'], 'input changed; record a new change')
        commands = list(cmd.get('pm_commands', []))
        pm.require(all(c.get('actor') == actor and c.get('op') in {'create', 'update', 'transition'} for c in commands), 'PM cannot impersonate a professional owner')
        dispositions = [d for a in value['assessments'].values() for d in a.get('dispositions', [])]
        covered = {d['task_id'] for d in dispositions}
        pm.require(set(value['affected_tasks']) <= covered, 'known affected task lacks a disposition')
        for p in value['participants']:
            prepared = value['assessments'][p].get('commands', [])
            limit = records(db, 'instance').get(p, {}).get('batch_limit', 1000)
            pm.require(len(prepared) <= limit, 'instance batch limit exceeded: '+p)
            commands += prepared
        for c in commands:
            target = c.get('task', {}).get('id') if c['op'] == 'create' else c.get('task_id')
            pm.require(target in covered, 'plan command has no assessed disposition: '+str(target))
        previous = {k: v['revision'] for k, v in tasks.items()}
        for n, c in enumerate(commands):
            child = dict(c, event_id=cmd['event_id'] + ':' + str(n))
            if c['op'] == 'transition' and c.get('state') in {'cancelled', 'deprecated'}:
                pm.require(any(d['task_id'] == c['task_id'] and d['action'] == 'cancel' for d in dispositions),
                           'retirement requires a cancellation disposition')
                pm.require(c.get('change_id', rid) == rid, 'deprecation linked to a different change')
                child.update(state='deprecated', change_id=rid)
            pm.execute(root, child, _db=db, _applying=rid)
        current = pm.task_map(db)
        for party, assessment in value['assessments'].items():
            for d in assessment.get('dispositions', []):
                pm.require(current.get(d['task_id'], {}).get('owner') == party, 'disposition does not belong to the assessing owner')
        for d in dispositions:
            tid = d['task_id']
            pm.require(tid in current, 'disposition task missing: ' + tid)
            action = d['action']
            if action in {'new', 'rework', 'replace'}:
                pm.require(tid not in previous, 'new/rework/replace must link a new successor task')
            elif action == 'update':
                pm.require(current[tid]['revision'] != previous.get(tid), 'task update was not applied')
            elif action == 'cancel':
                pm.require(current[tid]['state'] == 'deprecated' and current[tid].get('deprecation', {}).get('change_id') == rid,
                           'change cancellation must be recorded as deprecated with its change reference')
            elif action == 'defer':
                pm.require(current[tid]['state'] in {'planned', 'blocked'}, 'deferred task still active')
        value.update(state='planned', dispositions=dispositions, plan_event=cmd['event_id'],
                     affected_tasks=sorted(set(value['affected_tasks']) | covered),
                     plan_versions={d['task_id']: current[d['task_id']]['work_revision'] for d in dispositions})
    elif op == 'close_change':
        pm.require(actor == cfg['pm_actor'] and before and value['state'] == 'planned', 'PM closes a synchronized change')
        pm.require(pm.effective_done(tasks[value['analysis_task']], tasks), 'impact analysis task is not complete')
        for d in value['dispositions']:
            if d['action'] == 'cancel':
                retired = tasks[d['task_id']]
                pm.require(retired['state'] == 'deprecated' and retired.get('deprecation', {}).get('change_id') == rid,
                           'task retirement changed; reconcile before closing this change')
            if d['action'] not in {'keep', 'cancel'}:
                pm.require(tasks[d['task_id']]['work_revision'] == value['plan_versions'][d['task_id']], 'plan version changed; reconcile through a new change')
                pm.require(pm.effective_done(tasks[d['task_id']], tasks), 'changed delivery incomplete: ' + d['task_id'])
        for sid in value['scope_ids']:
            pm.require(not scope_issues(pm, root, scopes[sid], tasks), 'changed collection incomplete: ' + sid)
        pm.require(file_hash(pm, root, value['source']) == value['source_sha256'], 'change source changed')
        value['state'] = 'closed'
    elif op == 'pause_task':
        tid = cmd['task_id']
        pm.require(tid in tasks and actor == tasks[tid]['owner'], 'task owner pauses work')
        pm.require(not before or before['state'] != 'paused', 'pause already active')
        pm.require(cmd['resume_after'] in tasks and cmd['resume_after'] != tid, 'resume prerequisite missing/self')
        pm.require(all(pm.nonempty(cmd.get(k)) for k in ['checkpoint', 'resume_when', 'reason']) and pm.strings(cmd.get('remaining')) and cmd['remaining'], 'checkpoint, remaining work and resume condition required')
        graph = {p['task_id']: p['resume_after'] for p in records(db, 'pause').values() if p['state'] == 'paused'}
        graph[tid] = cmd['resume_after']
        seen, cursor = set(), tid
        while cursor in graph:
            pm.require(cursor not in seen, 'resume cycle')
            seen.add(cursor)
            cursor = graph[cursor]
        pm.require(tasks[tid]['state'] not in pm.TERMINAL, 'closed work cannot be paused')
        if tasks[tid]['state'] != 'blocked':
            pm.execute(root, dict(op='transition', actor=actor, task_id=tid,
                       expected_revision=cmd['task_revision'], state='blocked', reason=cmd['reason'],
                       stop_evidence=cmd.get('stop_evidence'), event_id=cmd['event_id']+':pause'), _db=db)
        else:
            pm.require(cmd['task_revision'] == tasks[tid]['revision'], 'stale task revision')
        value.update(task_id=tid, work_revision=tasks[tid]['work_revision'], checkpoint=cmd['checkpoint'],
                     remaining=cmd['remaining'], resume_after=cmd['resume_after'], resume_when=cmd['resume_when'], state='paused')
    elif op == 'resume_task':
        pm.require(before and value['state'] == 'paused', 'pause missing')
        tid = value['task_id']
        pm.require(actor == tasks[tid]['owner'], 'task owner resumes work')
        pm.require(pm.effective_done(tasks[value['resume_after']], tasks), 'interruption task not complete')
        pm.require(tasks[tid]['work_revision'] == value['work_revision'] or pm.nonempty(cmd.get('rebase_evidence')), 'changed checkpoint needs revalidation evidence')
        pm.require(not blockers(pm, root, db, tasks, tid), 'resume blocked by pending change/evidence')
        pm.execute(root, dict(op='transition', actor=actor, task_id=tid, expected_revision=cmd['task_revision'],
                   state='planned', reason=cmd['reason'], event_id=cmd['event_id']+':resume'), _db=db)
        value['state'] = 'resumed'
    value.update(revision=value['revision']+1, updated_at=pm.now())
    save(pm, db, kind, value)
    return dict(record=value, previous=before)
