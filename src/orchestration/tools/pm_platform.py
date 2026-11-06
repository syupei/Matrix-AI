"""Platform runs in the task database: launch records, the PM's inbox, project pause, limits, and the continuation
summary (what to do now and why each open task is stopped) that the PM and the timer read.

Records are cooperative facts written by the PM, the launcher and the timer. Nothing here starts a process.
"""
import hashlib
import json
from datetime import datetime, timezone

READ_OPS = {'continue'}
WRITE_OPS = {'launch_start', 'launch_started', 'launch_failed', 'launch_exit', 'launch_lost', 'inbox', 'inbox_done',
             'pause_project', 'resume_project'}
LIMITS = {'unattended_launches': 30, 'run_timeout_minutes': 60, 'rework_cap': 2, 'reassign_cap': 2, 'launch_retries': 3}
PURPOSES = {'start': '执行', 'check': '检验', 'attend': '处理'}
ACTIVE = {'starting', 'running'}
LAUNCHER, TIMER = 'launcher', 'timer'  # actors of the run wrapper and the timer
# Events that carry a person's words; the unattended launch limit counts from the latest one.
HUMAN_OPS = {'human_review', 'confirm_config', 'gap_decide', 'inbox', 'pause_project', 'resume_project', 'configure'}
INBOX_KINDS = {'request': '新需求', 'answer': '答复', 'continue': '继续', 'note': '说明'}
STOPS = {'running': '执行中', 'timeout': '超时待核实', 'ended': '结束未交出', 'children': '等下游', 'review': '等检验',
         'adopt': '等派发者采用', 'human': '等人', 'stale': '依据已变，待核对', 'sent_back': '检验没过，待返工',
         'cap': '超过上限，等上一级决定', 'blocked': '受阻', 'gap': '缺专家', 'deps': '等依赖', 'derive': '待派生',
         'executor': '未指定执行者', 'slots': '空位已满', 'gate': '前置未满足', 'paused': '已暂停', 'budget': '额度用完',
         'launch_failed': '启动失败', 'ready': '就绪', 'busy': '实例在忙'}


def limits(cfg):
    return dict(LIMITS, **cfg.get('limits', {}))


def check_limits(pm, value):
    pm.require(isinstance(value, dict) and set(value) <= set(LIMITS), 'limits fields: ' + ', '.join(sorted(LIMITS)))
    pm.require(all(type(v) is int and 1 <= v <= 1000 for v in value.values()), 'limits must be integers 1..1000')


def launches(pm, db):
    return pm.integrity.records(db, 'launch')


def active(pm, db):
    return [l for l in launches(pm, db).values() if l['state'] in ACTIVE]


def paused(pm, db):
    rec = pm.integrity.records(db, 'project_pause').get('project')
    return rec if rec and rec['state'] == 'paused' else None


def human_since(db):
    """The record (sequence number, time) where a person last spoke, by the events that carry their words."""
    for row in db.execute('SELECT seq, command, recorded_at FROM events ORDER BY seq DESC'):
        cmd = json.loads(row['command'])
        op = cmd.get('op')
        if op in HUMAN_OPS and (op not in {'configure', 'inbox'} or cmd.get('quote')):
            return row['seq'], row['recorded_at']
    return 0, None


def failed(l):
    """A start run that did not start, or ended without the executor handing over or reporting a block."""
    return l['purpose'] == 'start' and (l['state'] == 'not_started' or l.get('ended_without_handover'))


def streak(runs, executor):
    """Failed start runs of the current executor since its last start run that did not fail; another executor starts afresh."""
    count = 0
    for l in reversed([r for r in runs if r['purpose'] == 'start' and r['instance'] == executor]):
        if not failed(l):
            break
        count += 1
    return count


def after(l, seq):
    """The launch was recorded after the event seq (launch records keep the last sequence number before them)."""
    return l.get('after_seq', 0) >= seq


def budget(pm, db, cfg):
    seq, at = human_since(db)
    used = sum(1 for l in launches(pm, db).values() if l['state'] != 'not_started' and after(l, seq))
    limit = limits(cfg)['unattended_launches']
    return {'limit': limit, 'used': used, 'left': max(0, limit - used), 'since_seq': seq, 'since': at}


def binding(pm, root, db, task, tasks):
    """What the run was given: the task definition, the dependencies' versions, the appointment and the input files."""
    appointment = pm.integrity.records(db, 'appointment').get(task.get('executor') or task['owner'])
    files = {}
    for ref in task['inputs']:
        try:
            files[ref] = pm.integrity.file_hash(pm, root, ref)
        except (ValueError, OSError):
            pass  # an input described in words rather than a project file
    data = {k: task.get(k) for k in ['goal', 'inputs', 'outputs', 'criteria', 'dependencies', 'completion_requires', 'executor']}
    data.update(dependency_versions=[(d, tasks[d]['work_revision']) for d in task['dependencies'] if d in tasks],
                appointment=(appointment or {}).get('revision'), files=files)
    return hashlib.sha256(pm.canon(data).encode()).hexdigest()


def launch_bound(pm, db, cfg, cmd, before):
    """The launcher's own transitions of the task it launched: start, revert of a start that failed, end without handover."""
    rec = launches(pm, db).get(cmd.get('launch_id')) if cmd.get('launch_id') else None
    if not rec or rec['task_id'] != before['id'] or rec['purpose'] != 'start':
        return False
    actor, state = cmd['actor'], cmd.get('state')
    if actor in {cfg['pm_actor'], TIMER} and rec['state'] == 'starting':
        return (before['state'] in {'planned', 'waiting_review'} and state == 'running') or (before['state'] == 'running' and state == 'planned')
    return actor in {LAUNCHER, TIMER} and rec['state'] in ACTIVE and before['state'] == 'running' and state == 'blocked'


def minutes_since(stamp):
    try:
        return (datetime.now(timezone.utc) - datetime.fromisoformat(stamp)).total_seconds() / 60
    except (TypeError, ValueError):
        return 0


def execute(pm, root, db, cmd):
    cfg, tasks = pm.config(db), pm.task_map(db)
    op, actor = cmd['op'], cmd.get('actor')
    if op == 'continue':
        return summary(pm, root, db, cfg, tasks)
    if op in {'pause_project', 'resume_project'}:
        pm.require(actor in {cfg['pm_actor'], cfg.get('frontdesk_actor')} - {None}, 'PM or front desk records the person\'s decision')
        pm.require(all(pm.nonempty(cmd.get(k)) for k in ['quote', 'reason']), 'the person\'s exact quote and the reason are required')
        pm.authorized(cmd.get('person'), [None], tasks, pm.roster(root))
        before = pm.integrity.records(db, 'project_pause').get('project')
        pm.require((before or {}).get('state') != 'paused' if op == 'pause_project' else (before or {}).get('state') == 'paused',
                   'project already paused' if op == 'pause_project' else 'project is not paused')
        value = dict(id='project', state='paused' if op == 'pause_project' else 'resumed', person=cmd['person'], quote=cmd['quote'],
                     reason=cmd['reason'], at=pm.now(), revision=(before or {}).get('revision', 0) + 1)
        pm.integrity.save(pm, db, 'project_pause', value)
        return {'record': value}
    rid = cmd.get('id')
    pm.require(pm.nonempty(rid), 'record id required')
    if op in {'inbox', 'inbox_done'}:
        return inbox(pm, root, db, cfg, tasks, cmd)
    records = launches(pm, db)
    if op == 'launch_start':
        return start(pm, root, db, cfg, tasks, cmd, records)
    rec = records.get(rid)
    pm.require(rec, 'launch record missing')
    task = tasks[rec['task_id']]
    if op in {'launch_started', 'launch_failed'}:
        pm.require(actor in {cfg['pm_actor'], TIMER} and rec['state'] == 'starting', 'the PM, or the timer that starts queued runs, records how a start went')
        if op == 'launch_started':
            pm.require(type(cmd.get('pid')) is int and cmd['pid'] > 0, 'process id of the started run required')
            rec.update(state='running', pid=cmd['pid'], running_at=pm.now())
        else:
            pm.require(pm.nonempty(cmd.get('error')), 'why the run did not start')
            if rec['purpose'] == 'start' and task['state'] == 'running':
                pm.execute(root, dict(op='transition', actor=actor, event_id=cmd['event_id'] + ':revert', task_id=task['id'],
                                      expected_revision=task['revision'], state='planned', launch_id=rid, reason='launch did not start: ' + cmd['error'],
                                      stop_evidence='launch ' + rid + ' did not start: ' + cmd['error']), _db=db)
            rec.update(state='not_started', error=cmd['error'], finished_at=pm.now())
    else:
        pm.require(actor == (LAUNCHER if op == 'launch_exit' else TIMER), 'the run wrapper records the exit; the timer a lost run')
        if rec['state'] not in ACTIVE:
            return {'record': rec, 'unchanged': True}
        detail = ('exited with code ' + str(cmd.get('exit_code'))) if op == 'launch_exit' else ('lost: ' + str(cmd.get('evidence')))
        pm.require(op != 'launch_exit' or type(cmd.get('exit_code')) is int, 'exit code required')
        pm.require(op != 'launch_lost' or pm.nonempty(cmd.get('evidence')), 'evidence that the run is gone required')
        if rec['purpose'] == 'start' and task['state'] == 'running':
            open_kids = [x for x in pm.children(tasks, task['id']) if x['state'] not in pm.TERMINAL]
            if open_kids:
                rec['waiting_children'] = True  # a lead's run ends while its team works; the task stays in progress
            else:
                pm.execute(root, dict(op='transition', actor=actor, event_id=cmd['event_id'] + ':ended', task_id=task['id'],
                                      expected_revision=task['revision'], state='blocked', launch_id=rid,
                                      reason='结束未交出：' + ('进程退出，代码 ' + str(cmd['exit_code']) if op == 'launch_exit' else '进程已不在'),
                                      stop_evidence='launch ' + rid + ' ' + detail), _db=db)
                rec['ended_without_handover'] = True
        elif rec['purpose'] == 'start':
            rec['handed'] = True
            current = pm.task_map(db)[task['id']]
            if current['state'] == 'waiting_review' and binding(pm, root, db, current, pm.task_map(db)) != rec['binding']:
                rec['needs_attention'] = 'task, inputs or appointment changed during the run'
        rec.update(state='exited' if op == 'launch_exit' else 'lost', finished_at=pm.now(), exit_code=cmd.get('exit_code'),
                   **({'evidence': cmd['evidence']} if op == 'launch_lost' else {}))
    rec['revision'] = rec.get('revision', 1) + 1
    pm.integrity.save(pm, db, 'launch', rec)
    return {'record': rec}


def start(pm, root, db, cfg, tasks, cmd, records):
    """Record a run before the launcher starts it; a start run moves the task to running in the same transaction."""
    actor, rid = cmd['actor'], cmd['id']
    pm.require(actor == cfg['pm_actor'], 'the PM launches runs')
    pm.require(rid not in records, 'new launch id required')
    pm.require(not paused(pm, db), 'project paused by a person; launch nothing until they resume it')
    left = budget(pm, db, cfg)
    pm.require(left['left'] > 0, 'unattended launch limit reached (' + str(left['limit']) + ' since the person last replied); report and wait')
    purpose, ids = cmd.get('purpose'), cmd.get('task_ids') or [cmd.get('task_id')]
    pm.require(purpose in PURPOSES, 'purpose must be start, check or attend')
    pm.require(pm.strings(ids) and all(t in tasks for t in ids) and len(ids) == len(set(ids)), 'registered task ids required')
    pm.require(purpose != 'start' or len(ids) == 1, 'a start run takes one task')
    inst = pm.integrity.records(db, 'instance').get(cmd.get('instance'))
    pm.require(inst and inst.get('active', True), 'active registered instance required')
    pm.require(not any(l['instance'] == inst['id'] for l in active(pm, db)), inst['id'] + ' is already running; one run per instance at a time')
    pm.require(pm.nonempty(cmd.get('model')) and pm.nonempty(cmd.get('session')) and pm.strings(cmd.get('command')) and cmd['command'], 'model, session and command of the run required')
    task = tasks[ids[0]]
    if purpose == 'start':
        pm.require(inst['id'] == task.get('executor'), 'a start run launches the task\'s recorded executor')
        pm.require(not any(l['task_id'] == task['id'] for l in active(pm, db)), task['id'] + ' already has an active run')
        mine = sorted((l for l in records.values() if l['task_id'] == task['id']), key=lambda l: (l['started_at'], l['id']))
        if streak(mine, inst['id']) >= limits(cfg)['launch_retries']:
            # Past the cap a person decides: try again, or change the executor or its model first.
            e = cmd.get('escalation')
            pm.require(isinstance(e, dict) and pm.nonempty(e.get('quote')) and pm.nonempty(e.get('note')),
                       'launch retries for ' + task['id'] + ' exhausted (did not start or ended without handover); report to the person, '
                       'or pass their decision as escalation {decided_by, note, quote}')
            pm.authorized(e.get('decided_by'), [task['id']], tasks, pm.roster(root))
    for tid in ids:
        t = tasks[tid]
        if purpose == 'check':
            pm.require(t['state'] == 'waiting_review' and t['checker'] == inst['id'], tid + ': a check run launches the checker of a handed-over task')
        if purpose == 'attend':
            pm.require(t['manager'] == inst['id'] and t['state'] not in pm.TERMINAL, tid + ': an attend run launches the task\'s dispatcher')
    value = dict(id=rid, task_id=ids[0], task_ids=ids, purpose=purpose, instance=inst['id'], manager=task['manager'],
                 binding=binding(pm, root, db, task, tasks), work_revision=task['work_revision'], model=cmd['model'],
                 session=cmd['session'], command=cmd['command'], log=cmd.get('log'), state='starting', started_at=pm.now(), revision=1,
                 after_seq=db.execute('SELECT COALESCE(MAX(seq),0) FROM events').fetchone()[0])
    if cmd.get('log') is not None:
        pm.local(root, cmd['log'])
    pm.integrity.save(pm, db, 'launch', value)
    if purpose == 'start':
        extra = {k: cmd[k] for k in ['rework_reason', 'note', 'attributed_to', 'escalation'] if k in cmd}
        pm.execute(root, dict(op='transition', actor=actor, event_id=cmd['event_id'] + ':start', task_id=task['id'],
                              expected_revision=task['revision'], state='running', launch_id=rid, reason='platform run ' + rid,
                              execution_receipt='launch ' + rid + ': run of ' + inst['id'] + ' with model ' + cmd['model'], **extra), _db=db)
    return {'record': value}


def inbox(pm, root, db, cfg, tasks, cmd):
    """What a person says to the PM through the front desk; the PM marks it handled."""
    rid, actor, items = cmd['id'], cmd['actor'], pm.integrity.records(db, 'inbox')
    if cmd['op'] == 'inbox':
        pm.require(actor in {cfg['pm_actor'], cfg.get('frontdesk_actor')} - {None}, 'PM or front desk records what a person said')
        pm.require(rid not in items, 'new inbox id required')
        pm.require(cmd.get('kind') in INBOX_KINDS and pm.nonempty(cmd.get('text')), 'kind (request/answer/continue/note) and text required')
        if cmd.get('person') is not None or cmd.get('quote') is not None:
            pm.require(pm.nonempty(cmd.get('quote')), 'the person\'s exact quote is required')
            pm.authorized(cmd.get('person'), [None], tasks, pm.roster(root))
        value = dict(id=rid, kind=cmd['kind'], text=cmd['text'], person=cmd.get('person'), quote=cmd.get('quote'),
                     ref=cmd.get('ref'), state='open', at=pm.now(), by=actor, revision=1)
    else:
        value = items.get(rid)
        pm.require(value and value['state'] == 'open', 'open inbox item required')
        pm.require(actor == cfg['pm_actor'] and pm.nonempty(cmd.get('note')), 'the PM marks an item handled with a note')
        value = dict(value, state='done', note=cmd['note'], done_at=pm.now(), revision=value['revision'] + 1)
    pm.integrity.save(pm, db, 'inbox', value)
    return {'record': value}


def upper(pm, cfg, task, tasks):
    """Who may decide past a cap: someone above the task's dispatcher (the PM; for the PM's own tasks, a person)."""
    above, parent = set(), tasks.get(task.get('parent'))
    while parent:
        above.add(parent['manager'])
        parent = tasks.get(parent.get('parent'))
    return (above | {cfg['pm_actor']}) - {task['manager']}


def check_escalation(pm, root, cfg, cmd, task, tasks, kind, count):
    """Past the rework or reassignment cap, the next one needs the decision of someone above the dispatcher."""
    cap = limits(cfg)[kind + '_cap']
    if count <= cap:
        return None
    e = cmd.get('escalation')
    pm.require(isinstance(e, dict) and pm.nonempty(e.get('decided_by')) and pm.nonempty(e.get('note')),
               kind + ' ' + str(count) + ' exceeds the cap of ' + str(cap) + ': escalation {decided_by, note} from above the dispatcher required')
    if task['manager'] == cfg['pm_actor']:
        pm.require(pm.nonempty(e.get('quote')), 'past the cap on a PM task a person decides: escalation needs their exact quote')
        pm.authorized(e['decided_by'], [task['id']], tasks, pm.roster(root))
    else:
        pm.require(e['decided_by'] in upper(pm, cfg, task, tasks), 'escalation must come from above the dispatcher ' + task['manager'])
    return dict(e, at=pm.now(), kind=kind, count=count)


def stop_of(pm, root, db, cfg, task, ctx):
    """The one reason an open task is not moving, with who acts next."""
    t, tasks, runs = task, ctx['tasks'], ctx['runs'].get(task['id'], [])
    last = runs[-1] if runs else None
    run = next((l for l in reversed(runs) if l['state'] in ACTIVE and l['purpose'] == 'start'), None)
    kids = [x for x in pm.children(tasks, t['id']) if x['state'] not in pm.TERMINAL]
    gap = pm.gap_of(t, ctx['gaps'])
    if gap and gap['status'] in {'open', 'expert', 'human'}:
        return 'gap', gap['decision']['expert'] if gap['status'] == 'expert' else 'person'
    if t.get('awaiting'):
        return 'human', 'person'
    if t['state'] == 'running':
        if run:
            over = minutes_since(run['started_at']) > t.get('timeout_minutes', ctx['limits']['run_timeout_minutes'])
            return ('timeout', cfg['pm_actor']) if over else ('running', run['instance'])
        return ('children', t['owner']) if kids else ('running', t.get('executor') or t['owner'])
    if t['state'] == 'waiting_review':
        if last and last['purpose'] == 'start' and last.get('needs_attention'):
            return 'stale', t['manager']
        if t.get('sent_back'):
            count = (t.get('rework') or {}).get('count', 0) + 1
            return ('cap', 'above') if count > ctx['limits']['rework_cap'] else ('sent_back', t['manager'])
        b = pm.basis(t, tasks)
        checked = bool(t.get('review') and t['review']['basis'] == b and t['review']['outcome'] == 'passed')
        approved = bool(t.get('human_review') and t['human_review']['basis'] == b and t['human_review']['outcome'] == 'approved')
        if checked and t['human_required'] and not approved:
            return 'human', 'person'
        return ('adopt', t['manager']) if checked else ('review', t['checker'])
    if t['state'] == 'blocked':
        if last and last['purpose'] == 'start' and last.get('ended_without_handover') and t['revision'] == ctx['ended_at'].get(t['id']):
            return 'ended', t['manager']
        if any(p['task_id'] == t['id'] and p['state'] == 'paused' for p in ctx['pauses']):
            return 'paused', t['owner']
        return 'blocked', t['manager']
    # planned
    if ctx['paused']:
        return 'paused', 'person'
    issues = ctx['issues'][t['id']]
    if t.get('sent_back') and (t.get('rework') or {}).get('count', 0) + 1 > ctx['limits']['rework_cap']:
        return 'cap', 'above'
    if any(i.startswith('dependency not complete') for i in issues):
        return 'deps', None
    if t['ready']:
        if ctx['budget']['left'] <= 0:
            return 'budget', 'person'
        if streak(runs, t['executor']) >= ctx['limits']['launch_retries']:
            return 'launch_failed', 'person'
        if any(l['instance'] == t['executor'] for l in ctx['active']):
            return 'busy', t['executor']
        return 'ready', cfg['pm_actor']
    if issues == ['actual executor not recorded']:
        return ('derive', cfg['pm_actor']) if room(pm, root, db, ctx, t) else ('executor', t['manager'])
    if any(i == 'concurrency capacity exhausted' for i in issues):
        return 'slots', None
    return 'gate', t['manager']


def room(pm, root, db, ctx, task):
    """The confirmed configuration still allows another instance of the task's profession."""
    conf = pm.team.confirmed(pm, root, db)
    profession = (ctx['instances'].get(task['owner']) or {}).get('profession') or task.get('role')
    if not conf or not profession:
        return None
    for e in conf['entries']:
        alive = [i for i in ctx['instances'].values() if i.get('config_entry') == e['id'] and i.get('active')]
        if e['profession'] == profession and len(alive) < e['count']:
            return e['id']
    return None


def context(pm, root, db, cfg, tasks):
    snap = pm.snapshot(db)
    runs = {}
    for l in sorted(launches(pm, db).values(), key=lambda l: (l['started_at'], l['id'])):
        for tid in l.get('task_ids') or [l['task_id']]:
            runs.setdefault(tid, []).append(l)
    ended_at = {}
    for row in db.execute("SELECT task_id, after_data FROM events WHERE event_id LIKE '%:ended' ORDER BY seq"):
        if row['after_data']:
            ended_at[row['task_id']] = json.loads(row['after_data'])['revision']
    return dict(tasks=tasks, revision=snap['revision'], snap={t['id']: t for t in snap['tasks']}, issues={t['id']: t['readiness_issues'] for t in snap['tasks']},
                runs=runs, active=active(pm, db), gaps=pm.integrity.records(db, 'gap'), limits=limits(cfg), budget=budget(pm, db, cfg),
                paused=paused(pm, db), pauses=list(pm.integrity.records(db, 'pause').values()),
                instances=pm.integrity.records(db, 'instance'), ended_at=ended_at)


def stops(pm, root, db, cfg, tasks):
    ctx = context(pm, root, db, cfg, tasks)
    out = {}
    for tid, t in tasks.items():
        if t['state'] not in pm.TERMINAL:
            code, who = stop_of(pm, root, db, cfg, dict(t, ready=ctx['snap'][tid]['ready']), ctx)
            out[tid] = {'code': code, 'label': STOPS[code], 'who': who}
    return out, ctx


def summary(pm, root, db, cfg, tasks):
    """Continuation: what the PM does now, the one stop reason of every open task, and whether to stop."""
    reasons, ctx = stops(pm, root, db, cfg, tasks)
    pm_actor, instances = cfg['pm_actor'], ctx['instances']
    busy = {l['instance'] for l in ctx['active']}
    actions = [dict(kind='inbox', id=i['id'], what=INBOX_KINDS[i['kind']], text=i['text'], person=i.get('person'))
               for i in sorted(pm.integrity.records(db, 'inbox').values(), key=lambda i: i['at']) if i['state'] == 'open']
    running_slots = sum(t['slots'] for t in tasks.values() if t['state'] == 'running')
    free, left = cfg['max_slots'] - running_slots, ctx['budget']['left']
    ready = sorted((t for t in tasks.values() if reasons.get(t['id'], {}).get('code') == 'ready'),
                   key=lambda t: (t.get('order', 10 ** 6), t['created_at'], t['id']))
    for t in ready:
        if t['executor'] not in instances or t['executor'] in busy or left <= 0 or (t['slots'] and free < t['slots']):
            continue  # an executor that is not a registered instance starts the work itself
        hint = {'rework': dict(cause=t['sent_back']['cause'], attribution_required=t['sent_back']['cause'] != 'execution')} if t.get('sent_back') else {}
        actions.append(dict(kind='start', task=t['id'], instance=t['executor'], **hint))
        busy.add(t['executor']); free -= t['slots']; left -= 1
    by_instance = {}
    for tid, r in sorted(reasons.items()):
        t = tasks[tid]
        if r['code'] in {'review', 'adopt', 'ended', 'blocked', 'stale', 'sent_back', 'executor', 'gate'}:
            who = r['who']
            if who == pm_actor:
                actions.append(dict(kind='pm', task=tid, why=r['label']))
            elif who in instances and instances[who].get('active', True):
                by_instance.setdefault((who, 'check' if r['code'] == 'review' else 'attend'), []).append(tid)
        elif r['code'] == 'derive':
            actions.append(dict(kind='derive', task=tid, entry=room(pm, root, db, ctx, t)))
        elif r['code'] in {'timeout', 'cap'}:
            actions.append(dict(kind='pm', task=tid, why=r['label']))
    for (who, purpose), tids in sorted(by_instance.items()):
        if who not in busy and left > 0:
            actions.append(dict(kind=purpose, instance=who, tasks=tids))
            busy.add(who); left -= 1
    open_tasks = [tid for tid in reasons]
    human = [dict(task=tid, why=reasons[tid]['label']) for tid in open_tasks if reasons[tid]['code'] in {'human', 'gap', 'budget', 'launch_failed'}]
    if not open_tasks and not actions:
        stop = 'done'
    elif actions:
        stop = None
    elif ctx['paused']:
        stop = 'paused'
    elif human:
        stop = 'needs_human'
    elif any(reasons[t]['code'] in {'running', 'children', 'timeout', 'busy'} for t in open_tasks):
        stop = 'waiting'
    else:
        stop = 'idle'
    return {'revision': ctx['revision'], 'actions': actions, 'stops': reasons, 'stop': stop, 'human_items': human,
            'budget': ctx['budget'], 'slots': {'max': cfg['max_slots'], 'used': running_slots}, 'paused': ctx['paused'],
            'limits': ctx['limits'], 'active_runs': [dict(id=l['id'], instance=l['instance'], tasks=l.get('task_ids'), purpose=l['purpose'],
                                                           minutes=round(minutes_since(l['started_at']))) for l in ctx['active']]}
