#!/usr/bin/env python3
"""Local, cooperative task ownership + atomic events. No transport or daemon."""
import argparse
import hashlib
import html
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
import tempfile
from datetime import datetime, timezone

SCHEMA = 'pm-tasks/0.1'
STATES = {'planned', 'running', 'waiting_review', 'blocked', 'done', 'cancelled'}
TERMINAL = {'done', 'cancelled'}
RELATIONS = ('decide', 'clarify', 'designate', 'execute', 'inform')
STATE_NAMES = {'planned': '未开始', 'running': '进行中', 'waiting_review': '待审', 'blocked': '受阻', 'done': '完成', 'cancelled': '已取消'}
RELATION_NAMES = {'decide': '决定', 'clarify': '澄清', 'designate': '指定', 'execute': '执行或试用', 'inform': '知悉'}
ACTIONS = {'decide', 'clarify', 'designate', 'execute'}
KINDS = {'work', 'stage'}
ROSTER = 'collaboration/people.json'
# Coordination facts: who is involved, what is awaited, where a task sits in the plan.
# Changing them does not invalidate professional verification of the work itself.
COORDINATION = {'awaiting', 'people', 'direction', 'stage', 'derived_from'}
SAFE_ID = r'[A-Za-z0-9][A-Za-z0-9_.-]{0,63}'


class TaskError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise TaskError(message)


def canon(obj):
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def local(root, rel):
    path = root / rel
    require(not Path(rel).is_absolute() and '..' not in Path(rel).parts, 'relative project path required')
    require(not any(p.is_symlink() for p in [path, *path.parents] if p != root and root in p.parents), 'symlink destination rejected')
    require(path.resolve().is_relative_to(root), 'path escapes project')
    return path


def roster(root):
    """People list maintained by the project (or synced from its member system); read only."""
    path = local(root, ROSTER)
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding='utf-8'))
    people = data.get('people')
    require(isinstance(people, list), 'people.json: people list required')
    groups = data.get('groups', [])
    require(isinstance(groups, list) and all(isinstance(g, dict) and re.fullmatch(SAFE_ID, str(g.get('id', ''))) for g in groups), 'people.json: group ids must be simple identifiers')
    ids = [p.get('id') if isinstance(p, dict) else None for p in people]
    require(all(isinstance(i, str) and re.fullmatch(SAFE_ID, i) for i in ids) and len(ids) == len(set(ids)), 'people.json: unique simple person ids required')
    for p in people:
        require(nonempty(p.get('name')), 'people.json: name required for ' + p['id'])
        for key in ['groups', 'decides']:
            require(strings(p.get(key, [])), 'people.json: ' + key + ' must be a string list')
        require(all(re.fullmatch(SAFE_ID, g) for g in p.get('groups', [])), 'people.json: group ids must be simple identifiers')
    return {'people': {p['id']: p for p in people}, 'groups': {g['id']: g.get('name') or g['id'] for g in groups}}


def team_mode(people):
    return bool(people) and len(people['people']) >= 2


def deciders(tid, tasks, people):
    """Who may decide for a task and how far upstream they sit (higher wins conflicts)."""
    ranks, frontier, seen = {}, [(tid, 0)], set()
    while frontier:
        k, depth = frontier.pop(0)
        if k in seen or k not in tasks:
            continue
        seen.add(k)
        for p in tasks[k].get('people', {}).get('decide', []):
            ranks[p] = max(ranks.get(p, -1), depth)
        frontier.extend((up, depth + 1) for up in tasks[k].get('derived_from', []))
    for pid, p in (people or {}).get('people', {}).items():
        if 'project' in p.get('decides', []):
            ranks[pid] = 10 ** 6
    return ranks


def check_people(t, people):
    if not people:
        return
    known = people['people']
    named = [p for v in t.get('people', {}).values() for p in v] + [a['person'] for a in t.get('awaiting', [])]
    unknown = sorted(set(p for p in named if p not in known))
    require(not unknown, 'unknown person ids (not in people.json): ' + ','.join(unknown))


def connect(root):
    path = local(root, 'management/runtime/tasks.sqlite3')
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=20, isolation_level=None)
    db.row_factory = sqlite3.Row
    db.executescript('''
      CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS tasks (id TEXT PRIMARY KEY, data TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS events (
        seq INTEGER PRIMARY KEY AUTOINCREMENT, event_id TEXT UNIQUE NOT NULL,
        command TEXT NOT NULL, task_id TEXT, actor TEXT NOT NULL,
        occurred_at TEXT NOT NULL, recorded_at TEXT NOT NULL,
        before_data TEXT, after_data TEXT, result TEXT NOT NULL);
    ''')
    return db


def nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def strings(value):
    return isinstance(value, list) and all(nonempty(x) for x in value)


def task_map(db):
    return {r['id']: json.loads(r['data']) for r in db.execute('SELECT * FROM tasks ORDER BY id')}


def config(db):
    row = db.execute("SELECT value FROM meta WHERE key='config'").fetchone()
    require(row is not None, 'initialize project first')
    return json.loads(row[0])


def children(tasks, parent):
    return [t for t in tasks.values() if t['parent'] == parent]


def effective_done(t, tasks):
    if t['state'] != 'done' or not t.get('review'):
        return False
    b = basis(t, tasks)
    if t['review']['outcome'] != 'passed' or t['review']['basis'] != b:
        return False
    if t['human_required'] and not (t.get('human_review') and t['human_review']['outcome'] == 'approved' and t['human_review']['basis'] == b):
        return False
    return all(effective_done(tasks[d], tasks) for d in t['dependencies'] + t.get('completion_requires', [])) and all(x['state'] == 'cancelled' or effective_done(x,tasks) for x in children(tasks,t['id']))


def counts(items, tasks):
    active = [t for t in items if t['state'] != 'cancelled']
    done = sum(effective_done(t, tasks) for t in active)
    return {'total': len(active), 'done': done, 'remaining': len(active) - done,
            'cancelled': len(items) - len(active),
            'needs_recheck': sum(t['state'] == 'done' and not effective_done(t,tasks) for t in active),
            'states': {s: sum(t['state'] == s for t in active) for s in sorted(STATES - {'cancelled'})}}


def validation(t, tasks):
    required = ['title', 'owner', 'manager', 'checker', 'goal', 'next_action']
    require(all(nonempty(t.get(x)) for x in required), 'missing task responsibility/goal/next action')
    require(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,95}', t['id']) is not None, 'invalid task id')
    for key in ['inputs', 'outputs', 'criteria', 'evidence', 'dependencies', 'resources']:
        require(strings(t.get(key)), key + ' must be a string list')
    require(t['inputs'] and t['outputs'] and t['criteria'], 'input, deliverable and acceptance criteria required')
    require(len(t['dependencies']) == len(set(t['dependencies'])), 'duplicate dependencies')
    require(t['state'] in STATES, 'invalid state')
    require(type(t['slots']) is int and 0 <= t['slots'] <= 64, 'invalid slots')
    require(type(t['human_required']) is bool, 'human_required must be boolean')
    require(type(t['expanded']) is bool, 'expanded must be boolean')
    for dep in t['dependencies']:
        require(dep in tasks and dep != t['id'], 'unknown or self dependency: ' + dep)
    # Completion prerequisites: work may start before them, but cannot complete until they are done.
    finish = t.get('completion_requires', [])
    require(strings(finish), 'completion_requires must be a task id list')
    require(len(finish) == len(set(finish)) and not set(finish) & set(t['dependencies']), 'duplicate completion prerequisite or also listed as dependency')
    for dep in finish:
        require(dep in tasks and dep != t['id'], 'unknown or self completion prerequisite: ' + dep)
    require(t.get('kind', 'work') in KINDS, 'kind must be work or stage')
    stage = t.get('stage')
    if stage is not None:
        require(t.get('kind', 'work') == 'work', 'a stage milestone cannot belong to another stage')
        require(stage in tasks and stage != t['id'] and tasks[stage].get('kind') == 'stage', 'stage must reference a registered stage milestone')
    require(isinstance(t.get('direction', ''), str), 'direction must be text')
    people = t.get('people', {})
    require(isinstance(people, dict) and set(people) <= set(RELATIONS) and all(strings(v) for v in people.values()),
            'people relations must be decide/clarify/designate/execute/inform person lists')
    require(strings(t.get('derived_from', [])), 'derived_from must be a task id list')
    for up in t.get('derived_from', []):
        require(up in tasks and up != t['id'], 'unknown or self derivation: ' + up)
    awaiting = t.get('awaiting', [])
    require(isinstance(awaiting, list) and all(isinstance(a, dict) and set(a) <= {'person', 'action', 'item', 'ref'}
            and nonempty(a.get('person')) and a.get('action') in ACTIONS and nonempty(a.get('item')) for a in awaiting),
            'awaiting items need person, action (decide/clarify/designate/execute) and item')
    chain, path = {k: v.get('derived_from', []) for k, v in tasks.items()}, set()
    def climb(k):
        require(k not in path, 'derivation cycle')
        path.add(k)
        for up in chain.get(k, []):
            climb(up)
        path.discard(k)
    climb(t['id'])
    # A parent completes after children and a task after its completion prerequisites.
    # Include those edges to detect indirect deadlocks (child depends on its parent /
    # an ancestor waits for itself / two tasks wait for each other to complete).
    graph = {k: list(v['dependencies']) + list(v.get('completion_requires', [])) + [x['id'] for x in children(tasks, k)] for k, v in tasks.items()}
    visiting, visited = set(), set()
    def visit(k):
        require(k not in visiting, 'dependency/containment cycle')
        if k in visited:
            return
        visiting.add(k)
        for d in graph[k]:
            visit(d)
        visiting.remove(k)
        visited.add(k)
    for k in graph:
        visit(k)


def basis(t, tasks):
    # A review is bound to work, direct dependencies and all descendant work.
    def desc(k):
        return [(x['id'], x['work_revision'], x['state'], x['evidence'], desc(x['id'])) for x in children(tasks, k)]
    data = {k: t[k] for k in ['work_revision', 'inputs', 'outputs', 'criteria', 'evidence', 'human_required']}
    data['dependencies'] = [(d, tasks[d]['work_revision'], tasks[d]['state']) for d in t['dependencies']]
    data['children'] = desc(t['id'])
    if t.get('completion_requires'):
        # Bound to the prerequisite's work version: accepted unchanged keeps this check valid,
        # rework invalidates it. Omitted when empty so existing verification stays valid.
        data['completion_requires'] = [(d, tasks[d]['work_revision']) for d in t['completion_requires']]
    return hashlib.sha256(canon(data).encode()).hexdigest()


def reasons(t, tasks, cfg):
    result = []
    for dep in t['dependencies']:
        if not effective_done(tasks[dep], tasks):
            result.append('dependency not complete: ' + dep)
    if not t.get('executor'):
        result.append('actual executor not recorded')
    running = [x for x in tasks.values() if x['state'] == 'running' and x['id'] != t['id']]
    if sum(x['slots'] for x in running) + t['slots'] > cfg['max_slots']:
        result.append('concurrency capacity exhausted')
    for x in running:
        overlap = set(x['resources']) & set(t['resources'])
        if overlap:
            result.append('exclusive resources occupied by ' + x['id'] + ': ' + ','.join(sorted(overlap)))
    return result


def snapshot(db):
    cfg, tasks = config(db), task_map(db)
    seq = db.execute('SELECT COALESCE(MAX(seq),0) FROM events').fetchone()[0]
    return {'schema': SCHEMA, 'config': cfg, 'revision': seq, 'observed_at': now(),
            'top_level': counts(children(tasks, None), tasks),
            'tasks': [dict(t, child_counts=counts(children(tasks, t['id']), tasks),
                           needs_recheck=t['state'] == 'done' and not effective_done(t,tasks),
                           ready=t['state'] == 'planned' and not reasons(t, tasks, cfg),
                           readiness_issues=reasons(t, tasks, cfg),
                           completion_pending=[d for d in t.get('completion_requires', []) if not effective_done(tasks[d], tasks)],
                           review_current=bool(t.get('review') and t['review']['basis'] == basis(t, tasks)))
                      for t in tasks.values()]}


def execute(project, cmd):
    root = Path(project).resolve()
    require(root.is_dir(), 'project directory missing')
    db = connect(root)
    try:
        op = cmd.get('op')
        if op in {'status', 'events'}:
            db.execute('BEGIN')
            if op == 'status':
                result = snapshot(db)
            else:
                config(db)
                after = cmd.get('after', 0)
                limit = cmd.get('limit', 100)
                require(type(after) is int and after >= 0 and type(limit) is int and 1 <= limit <= 1000, 'invalid cursor/limit')
                rows = db.execute('SELECT * FROM events WHERE seq > ? ORDER BY seq LIMIT ?', (after, limit)).fetchall()
                result = {'events': [{k: json.loads(r[k]) if k in {'command', 'before_data', 'after_data', 'result'} and r[k] else r[k] for k in r.keys()} for r in rows]}
            db.commit()
            return result
        require(op in {'init', 'configure', 'create', 'update', 'transition', 'review', 'human_review', 'report', 'handoff'}, 'unknown operation')
        require(nonempty(cmd.get('event_id')) and nonempty(cmd.get('actor')), 'event_id and actor required')
        db.execute('BEGIN IMMEDIATE')
        old = db.execute('SELECT command,result FROM events WHERE event_id=?', (cmd['event_id'],)).fetchone()
        if old:
            require(old['command'] == canon(cmd), 'event id reused with different content')
            db.commit()
            return json.loads(old['result'])
        before, after = None, None
        if op == 'init':
            require(db.execute('SELECT COUNT(*) FROM meta').fetchone()[0] == 0, 'already initialized')
            cfg = cmd['config']
            require(nonempty(cfg.get('project')) and nonempty(cfg.get('pm_actor')) and nonempty(cfg.get('authorization')), 'project/PM/authorization required')
            require(nonempty(cfg.get('frontdoor_thread')), 'real frontdoor task id required')
            require(type(cfg.get('max_slots')) is int and 1 <= cfg['max_slots'] <= 64, 'max_slots must be 1..64')
            require(cmd['actor'] == cfg['pm_actor'], 'init actor must be PM')
            db.execute('INSERT INTO meta VALUES (?,?)', ('config', canon(cfg)))
            result = {'initialized': True, 'schema': SCHEMA}
        elif op == 'configure':
            # The front desk faces people; PM may let it record their real decisions.
            cfg = config(db)
            require(cmd['actor'] == cfg['pm_actor'], 'only PM configures the coordination entry')
            desk = cmd.get('frontdesk_actor')
            require(desk is None or (nonempty(desk) and desk != cfg['pm_actor']), 'frontdesk_actor must be a distinct actor or null')
            cfg['frontdesk_actor'] = desk
            db.execute("UPDATE meta SET value=? WHERE key='config'", (canon(cfg),))
            result = {'configured': True, 'frontdesk_actor': desk}
        else:
            cfg, tasks = config(db), task_map(db)
            people = roster(root)
            actor = cmd['actor']
            if op == 'create':
                data = dict(cmd['task'])
                tid = data['id']
                require(tid not in tasks, 'task already exists')
                parent = data.get('parent')
                if parent is None:
                    manager = cfg['pm_actor']
                else:
                    require(parent in tasks, 'parent missing')
                    require(tasks[parent]['state'] not in TERMINAL, 'closed parent; reopen explicitly first')
                    manager = tasks[parent]['owner']
                require(actor == manager, 'only responsible manager may create this level')
                allowed = {'id','parent','title','owner','checker','goal','inputs','outputs','criteria','dependencies','completion_requires','resources','slots','executor','human_required','expanded','next_action','source',
                           'kind','stage','direction','people','derived_from','awaiting'}
                require(set(data) <= allowed, 'unknown create fields')
                after = dict(data, parent=parent, manager=manager, state='planned', revision=1,
                             work_revision=1, evidence=[], review=None, human_review=None,
                             created_at=now(), updated_at=now(), last_report=None,
                             reason='registered before execution')
                for key, default in [('dependencies',[]),('completion_requires',[]),('resources',[]),('slots',1),('executor',None),('human_required',False),('expanded',False),('source',''),
                                     ('kind','work'),('stage',None),('direction',''),('people',{}),('derived_from',[]),('awaiting',[])]:
                    after.setdefault(key, default)
                tasks[tid] = after
                validation(after, tasks)
                check_people(after, people)
            else:
                tid = cmd['task_id']
                require(tid in tasks, 'task missing')
                before = tasks[tid]
                require(cmd.get('expected_revision') == before['revision'], 'stale revision; reload task before editing')
                after = json.loads(canon(before))
                if op in {'update', 'transition', 'report'}:
                    require(actor == after['owner'] or (op == 'transition' and actor == after['manager']), 'task state belongs to its owner')
                if op == 'update':
                    require(after['state'] not in TERMINAL, 'reopen before editing terminal task')
                    changes = cmd['changes']
                    allowed = {'next_action','evidence','executor','expanded','source','reason','title','goal','inputs','outputs','criteria','dependencies','completion_requires','resources','slots','human_required','checker'} | COORDINATION
                    require(set(changes) <= allowed, 'immutable/unknown field')
                    require(nonempty(cmd.get('reason')), 'change reason required')
                    if set(changes) & {'goal','inputs','outputs','criteria','dependencies','completion_requires','human_required','checker','people','derived_from'}:
                        require(actor == after['manager'] or nonempty(cmd.get('scope_authorization')), 'scope/interface change needs manager authorization reference')
                    after.update(changes)
                    require(not before['human_required'] or after['human_required'] or nonempty(cmd.get('scope_authorization')), 'cannot silently remove human review')
                    if set(changes) - {'next_action','executor','source','reason'} - COORDINATION:
                        after['work_revision'] += 1
                        after['review'] = after['human_review'] = None
                    after['reason'] = cmd['reason']
                elif op == 'transition':
                    state = cmd['state']
                    require(state in STATES and state != after['state'], 'invalid/no-op transition')
                    require(nonempty(cmd.get('reason')), 'transition reason required')
                    if state == 'running':
                        require(not reasons(after, tasks, cfg), '; '.join(reasons(after, tasks, cfg)))
                        require(nonempty(cmd.get('execution_receipt')), 'actual execution/start receipt required')
                    if before['state'] == 'running' and state != 'running':
                        require(nonempty(cmd.get('stop_evidence')), 'actual stop/yield evidence required before releasing resources')
                    if before['state'] in TERMINAL:
                        require(state in {'planned','blocked'} and actor == after['manager'], 'only manager may reopen closed task')
                        # Reopen from ancestors downwards; cannot hide new work under done.
                        parent = after['parent']
                        while parent:
                            require(tasks[parent]['state'] not in TERMINAL, 'reopen closed ancestors first')
                            parent = tasks[parent]['parent']
                        after['work_revision'] += 1
                        after['review'] = after['human_review'] = None
                    if state in TERMINAL:
                        require(actor == after['manager'], 'responsible manager closes task after owner reports')
                        require(all(x['state'] in TERMINAL for x in children(tasks, tid)), 'open children remain')
                    if state == 'done':
                        require(after['evidence'], 'deliverable evidence missing')
                        require(all(effective_done(tasks[d],tasks) for d in after['dependencies']), 'dependencies not complete/current')
                        pending = [d for d in after.get('completion_requires', []) if not effective_done(tasks[d], tasks)]
                        require(not pending, 'completion prerequisites not complete/current: ' + ','.join(pending))
                        require(all(x['state'] == 'cancelled' or effective_done(x,tasks) for x in children(tasks,tid)), 'child verification stale')
                        b = basis(after, tasks)
                        require(after['review'] and after['review']['basis'] == b and after['review']['outcome'] == 'passed', 'current professional verification required')
                        if after['human_required']:
                            require(after['human_review'] and after['human_review']['basis'] == b and after['human_review']['outcome'] == 'approved', 'current explicit human review required')
                    if before['state'] == 'done' and state != 'done':
                        # Downstream completed work is kept as historical fact;
                        # record stale dependency visibility rather than rewriting it.
                        after['reason'] = cmd['reason']
                    after['state'], after['reason'] = state, cmd['reason']
                elif op == 'review':
                    require(after['state'] not in TERMINAL, 'reopen closed task before new verification')
                    require(actor == after['checker'], 'designated checker only')
                    require(cmd.get('outcome') in {'passed','failed'}, 'invalid verification outcome')
                    require(strings(cmd.get('evidence')) and cmd['evidence'], 'verification evidence required')
                    require(cmd.get('criteria_checked') == after['criteria'], 'must explicitly check all listed criteria')
                    require(after['evidence'], 'work evidence required before review')
                    after['review'] = {'basis':basis(after,tasks),'checker':actor,'outcome':cmd['outcome'],'evidence':cmd['evidence'],'at':now()}
                elif op == 'human_review':
                    require(after['state'] not in TERMINAL, 'reopen closed task before new human decision')
                    require(actor in {cfg['pm_actor'], cfg.get('frontdesk_actor')} - {None}, 'unified frontdoor records human decisions')
                    require(cmd.get('outcome') in {'approved','changes_requested','deferred'}, 'invalid human decision')
                    require(all(nonempty(cmd.get(k)) for k in ['presented_ref','source','quote','scope']), 'actual presentation, reply source, exact quote and scope required')
                    person = cmd.get('person')
                    if team_mode(people):
                        require(nonempty(person) and person in people['people'], 'team project: record which listed person decided')
                        ranks = deciders(tid, tasks, people)
                        require(person in ranks, 'person has no decision authority for this task or its upstream')
                        prev = before.get('human_review')
                        if prev and prev.get('person') in ranks and prev['basis'] == basis(after, tasks) and prev['outcome'] != cmd['outcome']:
                            require(ranks[prev['person']] <= ranks[person], 'upstream decision stands; record this view as feedback for the upstream decider')
                    elif person is not None:
                        require(nonempty(person) and (not people or person in people['people']), 'unknown deciding person')
                    after['human_review'] = {k:cmd[k] for k in ['outcome','presented_ref','source','quote','scope']}
                    if person is not None:
                        after['human_review']['person'] = person
                    after['human_review'].update(basis=basis(after,tasks),at=now())
                elif op == 'report':
                    require(all(nonempty(cmd.get(k)) for k in ['summary','next_action','impact']), 'summary/next/impact required')
                    require(cmd.get('delivery') in {'prepared','sent','received'}, 'invalid delivery fact')
                    if cmd['delivery'] != 'prepared':
                        require(nonempty(cmd.get('receipt')), 'actual report delivery receipt required')
                    after['last_report'] = {k:cmd.get(k) for k in ['summary','next_action','impact','delivery','receipt','request_id']}
                    after['last_report'].update(at=now(), source_revision=before['revision'])
                    after['next_action'] = cmd['next_action']
                elif op == 'handoff':
                    require(actor == after['manager'], 'manager transfers responsibility')
                    require(after['state'] != 'running', 'stop old executor before handoff')
                    require(all(nonempty(cmd.get(k)) for k in ['new_owner','acceptance_receipt','reason']), 'actual acceptance required')
                    require(not children(tasks, tid), 'transfer leaf responsibility only; resolve child managers explicitly')
                    after['owner'] = cmd['new_owner']
                    after['executor'] = None
                after['revision'] += 1
                after['updated_at'] = now()
                tasks[tid] = after
                validation(after, tasks)
                check_people(after, people)
                if after['state'] == 'running':
                    require(not reasons(after,tasks,cfg), '; '.join(reasons(after,tasks,cfg)))
            db.execute('INSERT OR REPLACE INTO tasks VALUES (?,?)', (tid,canon(after)))
            result = {'task': after}
        occurred = cmd.get('occurred_at', now())
        cur = db.execute('INSERT INTO events(event_id,command,task_id,actor,occurred_at,recorded_at,before_data,after_data,result) VALUES (?,?,?,?,?,?,?,?,?)',
                         (cmd['event_id'],canon(cmd),after['id'] if after else None,cmd['actor'],occurred,now(),canon(before) if before else None,canon(after) if after else None,canon(result)))
        result['event_seq'] = cur.lastrowid
        db.execute('UPDATE events SET result=? WHERE seq=?',(canon(result),cur.lastrowid))
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def atomic(path, text):
    path.parent.mkdir(parents=True,exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.pm-view-',dir=path.parent)
    try:
        with os.fdopen(fd,'w') as f:
            f.write(text)
        os.replace(name,path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def render(project):
    root = Path(project).resolve()
    data = execute(root,{'op':'status'})
    tasks = {t['id']:t for t in data['tasks']}
    people = roster(root)
    names = {pid: p['name'] for pid, p in (people or {}).get('people', {}).items()}
    def esc(s):
        return html.escape(str(s)).replace('|','\\|').replace('\n',' ')
    def link(ref):
        # Evidence remains a visible, explicit path; no arbitrary executable URLs.
        if re.match(r'^https?://',ref):
            return '['+esc(ref)+'](<'+ref.replace('>','%3E')+'>)'
        plain = ref.split('#',1)[0]
        candidate = root / plain
        if plain and not Path(plain).is_absolute() and '..' not in Path(plain).parts and candidate.is_file():
            return '['+esc(ref)+'](<'+str(candidate)+(' #'+ref.split('#',1)[1] if '#' in ref else '').replace(' #','#')+'>)'
        return esc(ref)
    def who(pid):
        return esc(names.get(pid, pid))
    def state_of(t):
        return '待复核（历史完成）' if t['needs_recheck'] else STATE_NAMES.get(t['state'], t['state'])
    def tlink(t, prefix='tasks/'):
        return f"[{t['id']} {esc(t['title'])}]({prefix}{t['id']}.md)"
    def top(t):
        while t['parent']:
            t = tasks[t['parent']]
        return t
    def rels(pid, t):
        return [r for r in RELATIONS if pid in t.get('people', {}).get(r, [])]
    def involvement(t):
        return '、'.join(f"{who(p)}（{RELATION_NAMES[r]}）" for r in RELATIONS for p in t.get('people', {}).get(r, [])) or '—'
    def done(t):
        return t['state'] == 'done' and not t['needs_recheck']
    def waiters(t):
        # Open tasks that cannot start until this one is done.
        return [x for x in tasks.values() if t['id'] in x['dependencies'] and x['state'] not in TERMINAL]
    def finishers(t):
        # Open tasks that may proceed but cannot complete until this one is done.
        return [x for x in tasks.values() if t['id'] in x.get('completion_requires', []) and x['state'] not in TERMINAL]
    awaiting = [(t, a) for t in tasks.values() if t['state'] not in TERMINAL for a in t.get('awaiting', [])]
    awaiting.sort(key=lambda ta: (-len(waiters(ta[0])) - len(finishers(ta[0])), ta[0]['id']))
    def awaiting_line(t, a, prefix='tasks/'):
        blocked = waiters(t)
        line = f"- {tlink(t, prefix)}：{who(a['person'])}（{RELATION_NAMES[a['action']]}）{esc(a['item'])}"
        if a.get('ref'):
            line += '；查看：' + link(a['ref'])
        finishing = finishers(t)
        line += '；阻塞：' + '、'.join(esc(x['title']) for x in blocked) if blocked else ''
        line += '；影响完成：' + '、'.join(esc(x['title']) for x in finishing) if finishing else ''
        return line + '\n'
    summary = data['top_level']
    head = f"# 项目任务总览\n\n只读派生视图。任务事实由 `management/runtime/tasks.sqlite3` 维护；专业内容仍在原源。\n\n项目：{esc(data['config']['project'])}。读取时间：{data['observed_at']}。事件修订：{data['revision']}。\n\n顶层完成 {summary['done']}/{summary['total']}，剩余 {summary['remaining']}；仅统计已登记范围，未登记远期不计入。\n\n另见：[全程计划表](plan.md)｜[项目总入口](project.md)｜[群摘要](digest.md)\n\n"
    head += '| 编号 | 任务 | 责任方 | 状态 | 本层子项 | 下一步 | 详情 |\n|---|---|---|---|---|---|---|\n'
    for t in children(tasks,None):
        c=t['child_counts']
        head += f"| {t['id']} | {esc(t['title'])} | {esc(t['owner'])} | {state_of(t)} | {c['done']}/{c['total']}，剩余{c['remaining']} | {esc(t['next_action'])} | [展开](tasks/{t['id']}.md) |\n"
    head += '\n待人核验（各项独立决定；不跨越前置审阅）：\n\n'
    for t in tasks.values():
        b_current = t.get('human_review') and t['human_review']['basis'] == basis(t,tasks) and t['human_review']['outcome']=='approved'
        if t['human_required'] and t['state'] == 'waiting_review' and not b_current:
            head+=f"- [{t['id']} {esc(t['title'])}](tasks/{t['id']}.md)\n"
    # One snapshot for state, paged read of immutable events up to its revision.
    events=[]
    cursor=0
    while True:
        batch=execute(root,{'op':'events','after':cursor,'limit':1000})['events']
        events.extend(e for e in batch if e['seq']<=data['revision'])
        if not batch or batch[-1]['seq']>=data['revision']:
            break
        cursor=batch[-1]['seq']
    for t in tasks.values():
        c=t['child_counts']
        body=f"# {t['id']} {esc(t['title'])}\n\n[项目总览](../index.md) | [完整事件](../events.md)\n\n只读；快照修订 {data['revision']}，任务修订 {t['revision']}，源更新时间 {t['updated_at']}。\n\n"
        for label,key in [('责任','owner'),('执行实例','executor'),('检验责任','checker'),('状态','state'),('目标','goal'),('下一步','next_action'),('原因','reason')]:
            body+=f"- {label}：{esc(t.get(key))}\n"
        if t.get('source'):
            body+='- 专业有效源：'+link(t['source'])+'\n'
        if t.get('stage'):
            body+=f"- 所属阶段：[{t['stage']} {esc(tasks[t['stage']]['title'])}]({t['stage']}.md)\n"
        if t.get('direction'):
            body+='- 子方向：'+esc(t['direction'])+'\n'
        if t.get('people'):
            body+='- 相关的人：'+involvement(t)+'\n'
        if t.get('derived_from'):
            body+='- 派生自：'+'、'.join(f"[{d}]({d}.md)" for d in t['derived_from'])+'\n'
        if t.get('awaiting'):
            body+='- 在等：'+'；'.join(f"{who(a['person'])}（{RELATION_NAMES[a['action']]}）{esc(a['item'])}" for a in t['awaiting'])+'\n'
        body+=f"- 直接子项：完成 {c['done']}/{c['total']}，剩余 {c['remaining']}；{'本轮已展开' if t['expanded'] else '尚未声明完整展开'}。\n"
        for key,label in [('inputs','输入'),('outputs','关键交付物'),('criteria','完成条件'),('dependencies','依赖'),('evidence','成果证据')]:
            body+=f'\n{label}：\n\n'+''.join('- '+link(x)+'\n' for x in t[key])
            if key == 'dependencies' and t.get('completion_requires'):
                body+='\n完成前置（可以先开始，完成前须已完成）：\n\n'+''.join(f"- [{d} {esc(tasks[d]['title'])}]({d}.md)：{state_of(tasks[d])}\n" for d in t['completion_requires'])
        if t.get('last_report'):
            body+='\n最后上报：\n\n'+esc(canon(t['last_report']))+'\n'
        if t['needs_recheck']:
            body+='\n当前判定：历史完成依据已变化，待责任方复核；暂不计入当前完成数。\n'
        if t.get('review'):
            body+='\n专业检验：'+esc(t['review']['outcome'])+'；'+('当前有效' if t['review_current'] else '需复核')+'。\n\n'
            body+=''.join('- '+link(x)+'\n' for x in t['review']['evidence'])
        if t.get('human_review'):
            h=t['human_review']
            body+='\n人工决定：'+esc(h['outcome'])+'；范围：'+esc(h['scope'])+('；决定人：'+who(h['person']) if h.get('person') else '')+'。\n\n'
            body+='- 展示：'+link(h['presented_ref'])+'\n- 答复来源：'+link(h['source'])+'\n- 原话：'+esc(h['quote'])+'\n'
        if t['readiness_issues']:
            body+='\n当前前置/资源提示（不等同于已停止）：\n\n'+''.join('- '+esc(x)+'\n' for x in t['readiness_issues'])
        body+='\n子任务：\n\n'
        for child in children(tasks,t['id']):
            body+=f"- [{child['id']} {esc(child['title'])}]({child['id']}.md)：{child['state']}；下一步：{esc(child['next_action'])}\n"
        body+='\n本任务时间线：\n\n'
        for e in events:
            if e['task_id']==t['id']:
                body+=f"- #{e['seq']} {e['recorded_at']}｜{esc(e['actor'])}｜{e['command']['op']}｜{esc(e['command'].get('reason',e['command'].get('summary','')))}\n"
        atomic(local(root,'management/views/tasks/'+t['id']+'.md'),body)
    event_text='# 任务事件时间线\n\n只读；发生/接收时间和完整变更见任务账本 events 查询。\n\n'
    for e in events:
        event_text+=f"- #{e['seq']} {e['recorded_at']}｜{esc(e['task_id'])}｜{esc(e['actor'])}｜{e['command']['op']}｜{esc(e['command'].get('reason',e['command'].get('summary','')))}\n"
    atomic(local(root,'management/views/events.md'),event_text)
    atomic(local(root,'management/views/index.md'),head)
    written = ['index.md', 'events.md']

    # Whole-lifecycle plan: stage milestones in dependency order, near stages expanded.
    stages = [t for t in tasks.values() if t.get('kind') == 'stage']
    depth = {}
    def stage_depth(s):
        if s['id'] not in depth:
            depth[s['id']] = 0
            depth[s['id']] = 1 + max([stage_depth(tasks[d]) for d in s['dependencies'] if tasks[d].get('kind') == 'stage'] or [-1])
        return depth[s['id']]
    stages.sort(key=lambda s: (stage_depth(s), s['id']))
    def staged(s):
        return [t for t in tasks.values() if t.get('stage') == s['id'] and t['parent'] is None]
    plan = f"# 全程计划表\n\n只读派生视图，读取时间：{data['observed_at']}，事件修订：{data['revision']}。阶段由阶段里程碑任务登记，近期展开到任务，远期写\"待展开\"；不估工期，不算总百分比。\n\n"
    plan += '## 现在等人处理\n\n' + (''.join(awaiting_line(t, a) for t, a in awaiting) or '- 无\n')
    plan += '\n## 阶段\n\n| # | 阶段 | 负责 | 相关的人 | 出口条件 | 状态 | 本阶段任务 |\n|---|---|---|---|---|---|---|\n'
    for n, s in enumerate(stages, 1):
        items = staged(s)
        progress = f"{sum(done(x) for x in items)}/{len(items)}" if items else '待展开'
        plan += f"| {n} | {tlink(s)} | {esc(s['owner'])} | {involvement(s)} | {esc('；'.join(s['criteria']))} | {state_of(s)} | {progress} |\n"
    for s in stages:
        items = staged(s)
        if items:
            plan += f"\n### {esc(s['title'])}\n\n| 编号 | 任务 | 子方向 | 相关的人 | 状态 | 下一步 |\n|---|---|---|---|---|---|\n"
            for x in sorted(items, key=lambda x: x['id']):
                plan += f"| {tlink(x)} | {esc(x['title'])} | {esc(x.get('direction') or '—')} | {involvement(x)} | {state_of(x)} | {esc(x['next_action'])} |\n"
    loose = [t for t in children(tasks, None) if t.get('kind') != 'stage' and not t.get('stage')]
    if loose:
        plan += '\n### 未归入阶段的顶层任务\n\n' + ''.join(f"- {tlink(x)}：{state_of(x)}\n" for x in loose)
    atomic(local(root,'management/views/plan.md'),plan)
    written.append('plan.md')

    # Project front page: one row per sub-direction with outputs, progress and who is awaited.
    directions = {}
    for t in children(tasks, None):
        if t.get('kind') != 'stage':
            directions.setdefault(t.get('direction') or '未分类', []).append(t)
    proj = f"# 项目总入口\n\n只读派生视图，读取时间：{data['observed_at']}。每个子方向一行；成果与状态取自任务源，按维度的详细进度在各角色的专业源。\n\n| 子方向 | 负责的人 | 进行中 | 最新完成与证据 | 在等谁 | 详细进度 |\n|---|---|---|---|---|---|\n"
    for name in sorted(directions):
        items = directions[name]
        owners = sorted(set(p for x in items for r in ('decide', 'execute') for p in x.get('people', {}).get(r, [])))
        active = [x for x in items if x['state'] in {'running', 'waiting_review', 'blocked'}]
        finished = sorted([x for x in items if done(x)], key=lambda x: x['updated_at'], reverse=True)
        latest = '；'.join(esc(x['title']) + (' ' + link(x['evidence'][0]) if x['evidence'] else '') for x in finished[:2]) or '—'
        waiting = sorted(set(a['person'] for x in items for a in x.get('awaiting', []) if x['state'] not in TERMINAL))
        sources = sorted(set(x['source'] for x in items if x.get('source')))
        proj += f"| {esc(name)} | {'、'.join(who(p) for p in owners) or '—'} | {'；'.join(tlink(x) + '（' + state_of(x) + '；执行：' + esc(x.get('executor') or '未登记') + '）' for x in active[:3]) or '—'} | {latest} | {'、'.join(who(p) for p in waiting) or '—'} | {'、'.join(link(s) for s in sources) or '—'} |\n"
    atomic(local(root,'management/views/project.md'),proj)
    written.append('project.md')

    # Group digest: stage progress, items blocking others first, recent decisions with the deciding person.
    dig = f"# 群摘要\n\n只读派生视图，读取时间：{data['observed_at']}。只在群里 @ 需要行动的人；本摘要供所有人了解进展。\n\n## 阶段进展\n\n"
    dig += ''.join(f"- {esc(s['title'])}：{state_of(s)}\n" for s in stages) or '- 尚未登记阶段\n'
    dig += '\n## 在等的人（阻塞他人的在前）\n\n' + (''.join(awaiting_line(t, a) for t, a in awaiting) or '- 无\n')
    decided = sorted([t for t in tasks.values() if t.get('human_review')], key=lambda t: t['human_review'].get('at', ''), reverse=True)
    dig += '\n## 最近的人工决定\n\n' + (''.join(f"- {tlink(t)}：{esc(t['human_review']['outcome'])}；范围：{esc(t['human_review']['scope'])}" + (f"；决定人：{who(t['human_review']['person'])}" if t['human_review'].get('person') else '') + '\n' for t in decided[:10]) or '- 无\n')
    atomic(local(root,'management/views/digest.md'),dig)
    written.append('digest.md')

    # Personal and group views exist only when two or more people take part.
    def scoped_view(title, members, intro, prefix='../tasks/'):
        mine = [t for t in tasks.values() if t['state'] != 'cancelled' and any(set(rels(m, t)) - {'inform'} for m in members)]
        ids = {t['id'] for t in mine}
        waiting = [(t, a) for t, a in awaiting if a['person'] in members]
        counts_by = {s: sum(t['state'] == s for t in mine) for s in ['done', 'running', 'waiting_review', 'blocked', 'planned']}
        text = f"# {title}\n\n{intro}\n\n与此相关 {len(mine)} 项：完成 {counts_by['done']}｜进行中 {counts_by['running']}｜待审 {counts_by['waiting_review']}｜受阻 {counts_by['blocked']}｜未开始 {counts_by['planned']}\n\n"
        text += '## 现在等你\n\n' + (''.join(awaiting_line(t, a, prefix) for t, a in waiting) or '- 无\n')
        upcoming = [t for t in mine if t['state'] in {'planned', 'blocked'} and not any(a['person'] in members for a in t.get('awaiting', []))]
        text += '\n## 即将轮到你（按触发条件，不写日期）\n\n'
        for t in sorted(upcoming, key=lambda t: t['id']):
            pending = [tasks[d] for d in t['dependencies'] if not done(tasks[d])]
            text += f"- {tlink(t, prefix)}：" + ('等 ' + '、'.join(esc(d['title']) for d in pending) + ' 完成' if pending else '前置已满足，等待排入') + '\n'
        if not upcoming:
            text += '- 无\n'
        neighbours = {}
        for t in mine:
            for d in t['dependencies']:
                if d not in ids:
                    neighbours.setdefault(top(tasks[d])['id'], set()).add('你的「' + t['title'] + '」依赖它')
            for x in waiters(t):
                if x['id'] not in ids:
                    neighbours.setdefault(top(x)['id'], set()).add('它在等你的「' + t['title'] + '」')
            for d in t.get('completion_requires', []):
                if d not in ids:
                    neighbours.setdefault(top(tasks[d])['id'], set()).add('你的「' + t['title'] + '」完成前需要它')
            for x in finishers(t):
                if x['id'] not in ids:
                    neighbours.setdefault(top(x)['id'], set()).add('它完成前需要你的「' + t['title'] + '」')
        text += '\n## 因依赖显示（只列上层任务）\n\n' + (''.join(f"- {tlink(tasks[k], prefix)}（{state_of(tasks[k])}）：{esc('；'.join(sorted(v)))}\n" for k, v in sorted(neighbours.items()) if k not in ids) or '- 无\n')
        text += '\n## 你负责的环节\n\n' + (''.join(f"- {tlink(t, prefix)}：{'、'.join(RELATION_NAMES[r] for m in members for r in rels(m, t) if r != 'inform')}；{state_of(t)}\n" for t in sorted(mine, key=lambda t: t['id'])) or '- 无\n')
        informed = [t for t in tasks.values() if t['id'] not in ids and any(rels(m, t) == ['inform'] for m in members)]
        if informed:
            text += f"\n另有 {len(informed)} 项只需知悉，见[群摘要](../digest.md)。\n"
        return text
    for sub in ['people', 'groups']:
        folder = local(root, 'management/views/' + sub)
        if folder.is_dir():
            for old in folder.glob('*.md'):
                local(root, 'management/views/' + sub + '/' + old.name).unlink()
    if team_mode(people):
        for pid, p in sorted(people['people'].items()):
            atomic(local(root, f'management/views/people/{pid}.md'), scoped_view(esc(p['name']) + '的视图', [pid], '只读派生视图。只列与你有关系（决定、澄清、指定、执行或试用）的事项，以及与它们直接相连的上层任务；AI 内部子任务不在此列。'))
            written.append(f'people/{pid}.md')
        group_ids = sorted(set(g for p in people['people'].values() for g in p.get('groups', [])))
        for gid in group_ids:
            members = [pid for pid, p in people['people'].items() if gid in p.get('groups', [])]
            label = esc(people['groups'].get(gid, gid))
            atomic(local(root, f'management/views/groups/{gid}.md'), scoped_view(label + '的视图', members, '只读派生视图。成员：' + '、'.join(who(m) for m in members) + '。列出与本组成员有关的事项与跨组依赖。'))
            written.append(f'groups/{gid}.md')
    return {'view':str(root/'management/views/index.md'),'revision':data['revision'],'task_count':len(tasks),'views':written}


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project',required=True)
    parser.add_argument('--command',help='JSON file; omit to read stdin')
    parser.add_argument('--render',action='store_true')
    args=parser.parse_args()
    try:
        command=json.loads(Path(args.command).read_text() if args.command else sys.stdin.read()) if not args.render else None
        print(json.dumps(render(args.project) if args.render else execute(args.project,command),ensure_ascii=False,indent=2))
    except (ValueError,OSError,KeyError,TypeError,sqlite3.Error) as exc:
        print(json.dumps({'error':str(exc)},ensure_ascii=False))
        sys.exit(1)
