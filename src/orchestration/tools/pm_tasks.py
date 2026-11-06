#!/usr/bin/env python3
"""Local, cooperative task ownership + atomic events. No transport or daemon."""
import argparse
import importlib.util
from types import SimpleNamespace
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

_spec = importlib.util.spec_from_file_location('pm_integrity', Path(__file__).with_name('pm_integrity.py'))
integrity = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(integrity)
_team_spec = importlib.util.spec_from_file_location('pm_team', Path(__file__).with_name('pm_team.py'))
team = importlib.util.module_from_spec(_team_spec)
_team_spec.loader.exec_module(team)
_views_spec = importlib.util.spec_from_file_location('pm_views', Path(__file__).with_name('pm_views.py'))
views = importlib.util.module_from_spec(_views_spec)
_views_spec.loader.exec_module(views)
_platform_spec = importlib.util.spec_from_file_location('pm_platform', Path(__file__).with_name('pm_platform.py'))
platform = importlib.util.module_from_spec(_platform_spec)
_platform_spec.loader.exec_module(platform)


def api():
    return SimpleNamespace(**globals())


SCHEMA = 'pm-tasks/0.1'
STATES = {'planned', 'running', 'waiting_review', 'blocked', 'done', 'cancelled', 'deprecated'}
TERMINAL = {'done', 'cancelled', 'deprecated'}
RETIRED = {'cancelled', 'deprecated'}
RELATIONS = ('decide', 'clarify', 'designate', 'execute', 'inform')
STATE_NAMES = {'planned': '未开始', 'running': '进行中', 'waiting_review': '待审', 'blocked': '受阻', 'done': '完成', 'cancelled': '已取消', 'deprecated': '已弃用'}
RELATION_NAMES = {'decide': '决定', 'clarify': '澄清', 'designate': '指定', 'execute': '执行或试用', 'inform': '知悉'}
ACTIONS = {'decide', 'clarify', 'designate', 'execute'}
KINDS = {'work', 'stage'}
ROSTER = 'management/people.json'
# Coordination facts: who is involved, what is awaited (an expertise gap included), where a task sits in the plan.
# Changing them does not invalidate professional verification of the work itself.
COORDINATION = {'awaiting', 'people', 'direction', 'stage', 'derived_from', 'gap', 'order', 'timeout_minutes'}
SAFE_ID = r'[A-Za-z0-9][A-Za-z0-9_.-]{0,63}'
# Rework causes, written by the checker of a failed review or by the manager who reopens finished work.
REWORK = {'execution', 'requirement_clarification', 'basis_changed', 'other'}
NOTICES = {'F1_output': 'F1 成果', 'Q0': 'Q0', 'Q1': 'Q1', 'Q2': 'Q2'}
CONFLICT_LEVELS = {'tool', 'master', 'owner', 'pm', 'human'}
# Expertise gaps: work needing a profession the project has not set up waits for the person's choice.
GAP_OPS = {'gap_open', 'gap_decide', 'gap_close'}
GAP_KINDS = {'not_in_kit': '本包没有', 'not_set_up': '项目未设立'}
GAP_CHOICES = {'expert': '指定专家', 'self': '由当前实例完成', 'human': '列为人工待办'}
GAP_STATES = dict(GAP_CHOICES, open='等人选择', closed='已关闭')
ROOT_MARK = '\x00root/'  # resolved to the relative path from each view file to the project root


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


def authorized(person, tids, tasks, people):
    """The person-authority check of human_review, for decisions recorded by other operations."""
    require(nonempty(person), 'deciding person required')
    if people:
        require(person in people['people'], 'team project: record which listed person decided')
        require(any(person in deciders(t, tasks, people) for t in tids), 'person has no decision authority for this task or its upstream')


def check_usage(usage):
    if usage is not None:
        require(isinstance(usage, dict) and usage and set(usage) <= {'cost', 'currency', 'tokens', 'seconds'}, 'usage fields: cost, currency, tokens, seconds')
        require(all(type(v) in (int, float) and v >= 0 for k, v in usage.items() if k != 'currency') and nonempty(usage.get('currency', 'x')), 'usage values must be non-negative numbers; currency text')


def rework(cmd, before, sent_back):
    """A rework of the same task: cause, note and who it is counted for (the producer for execution)."""
    reason = cmd.get('rework_reason') or (sent_back or {}).get('cause')
    require(reason in REWORK and nonempty(cmd.get('note')), 'rework needs rework_reason (execution/requirement_clarification/basis_changed/other) and note')
    require(not sent_back or reason == sent_back['cause'], 'the checker wrote the rework cause; dispute it through conflict')
    producer = (sent_back or {}).get('producer') or before.get('executor') or before['owner']  # who made the work sent back
    who = cmd.get('attributed_to') or (producer if reason == 'execution' else None)
    require(nonempty(who), 'attributed_to (an instance id) required unless the cause is execution')
    return dict(count=(before.get('rework') or {}).get('count', 0) + 1, reason=reason, note=cmd['note'], attributed_to=who, at=now())


def check_people(t, people):
    if not people:
        return
    known = people['people']
    named = [p for v in t.get('people', {}).values() for p in v] + [a['person'] for a in t.get('awaiting', [])]
    unknown = sorted(set(p for p in named if p not in known))
    require(not unknown, 'unknown person ids (not in people.json): ' + ','.join(unknown))


def connect(root, readonly=False):
    path = local(root, 'management/runtime/tasks.sqlite3')
    if readonly:
        require(path.is_file(), 'task database missing; initialize explicitly')
        db = sqlite3.connect(path.as_uri()+'?mode=ro', uri=True, timeout=20, isolation_level=None)
        db.row_factory = sqlite3.Row
        return db
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=20, isolation_level=None)
    db.row_factory = sqlite3.Row
    db.executescript('''
      CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS tasks (id TEXT PRIMARY KEY, data TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS pm_records (kind TEXT NOT NULL, id TEXT NOT NULL, data TEXT NOT NULL, PRIMARY KEY(kind,id));
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
    root = Path(db.execute('PRAGMA database_list').fetchone()[2]).parent.parent.parent
    tasks = {r['id']: integrity.observe(api(), root, json.loads(r['data'])) for r in db.execute('SELECT * FROM tasks ORDER BY id')}
    for c in integrity.records(db, 'change').values():
        if c['state'] not in {'planned', 'closed'}:
            continue
        for d in c.get('dispositions', []):
            if d.get('replaces') in tasks:
                tasks[d['replaces']]['_superseded_by'] = d['task_id']
    for scope in integrity.records(db, 'scope').values():
        if scope['root_task'] in tasks and integrity.scope_issues(api(), root, scope, tasks):
            tasks[scope['root_task']]['_scope_incomplete'] = True
    return tasks


def config(db):
    row = db.execute("SELECT value FROM meta WHERE key='config'").fetchone()
    require(row is not None, 'initialize project first')
    return json.loads(row[0])


def children(tasks, parent):
    return [t for t in tasks.values() if t['parent'] == parent]


def effective_done(t, tasks):
    if t.get('_superseded_by') or t.get('_scope_incomplete') or t.get('_current_gate'):
        return False
    if t.get('artifact_digests') and t.get('_observed_artifacts') != t['artifact_digests']:
        return False
    if t['state'] != 'done' or not t.get('review'):
        return False
    b = basis(t, tasks)
    if t['review']['outcome'] != 'passed' or t['review']['basis'] != b:
        return False
    if t['human_required'] and not (t.get('human_review') and t['human_review']['outcome'] == 'approved' and t['human_review']['basis'] == b):
        return False
    return all(effective_done(tasks[d], tasks) for d in t['dependencies'] + t.get('completion_requires', [])) and all(x['state'] in RETIRED or effective_done(x,tasks) for x in children(tasks,t['id']))


def counts(items, tasks):
    active = [t for t in items if t['state'] not in RETIRED]
    done = sum(effective_done(t, tasks) for t in active)
    return {'total': len(active), 'done': done, 'remaining': len(active) - done,
            'cancelled': sum(t['state'] == 'cancelled' for t in items),
            'deprecated': sum(t['state'] == 'deprecated' for t in items),
            'needs_recheck': sum(t['state'] == 'done' and not effective_done(t,tasks) for t in active),
            'states': {s: sum(t['state'] == s for t in active) for s in sorted(STATES - RETIRED)}}


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
    require('project_level' not in t or type(t['project_level']) is bool, 'project_level must be boolean')
    require(t.get('difficulty') is None or team.level(t['difficulty']) is not None, 'difficulty must be T1–T9')
    require(t.get('risk') is None or team.risk(t['risk']) is not None, 'risk must be F0–F5')
    require(t.get('risk_reason') is None or nonempty(t['risk_reason']), 'risk_reason must be text')
    origin = t.get('origin')
    require(origin is None or (isinstance(origin, dict) and set(origin) == {'kind', 'id', 'from'} and origin['kind'] == 'request'
            and nonempty(origin['id']) and nonempty(origin['from'])), 'origin needs kind "request", id and from')
    hashes = t.get('artifact_digests', {})
    require(isinstance(hashes, dict) and all(nonempty(k) and re.fullmatch(r'[a-f0-9]{64}', str(v)) for k,v in hashes.items()), 'artifact_digests must map paths to sha256')
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
    require(t.get('gap') is None or (isinstance(t['gap'], str) and re.fullmatch(r'G-\d{3,}', t['gap']) is not None), 'gap must be a gap id such as G-001')
    require(t.get('order') is None or (type(t['order']) is int and t['order'] >= 0), 'order must be a non-negative integer')
    require(t.get('timeout_minutes') is None or (type(t['timeout_minutes']) is int and 1 <= t['timeout_minutes'] <= 10000), 'timeout_minutes must be 1..10000')
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
    if t.get('artifact_digests'):
        data['artifact_digests'] = t['artifact_digests']
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


def brief(row):
    """One event as what happened: the operation, who, the state change and the new reason; not the whole records."""
    before = json.loads(row['before_data']) if row['before_data'] else {}
    after = json.loads(row['after_data']) if row['after_data'] else {}
    out = {'seq': row['seq'], 'op': json.loads(row['command']).get('op'), 'task_id': row['task_id'], 'actor': row['actor'], 'at': row['recorded_at']}
    if after.get('state') != before.get('state'):
        out['state'] = [before.get('state'), after.get('state')]
    if after.get('reason') and after.get('reason') != before.get('reason'):
        out['reason'] = after['reason']
    return out


def snapshot(db):
    cfg, tasks = config(db), task_map(db)
    seq = db.execute('SELECT COALESCE(MAX(seq),0) FROM events').fetchone()[0]
    root = Path(db.execute('PRAGMA database_list').fetchone()[2]).parent.parent.parent
    gates = {tid: integrity.blockers(api(), root, db, tasks, tid) + team.blockers(api(), root, db, tasks, tid) for tid in tasks}
    for tid, t in tasks.items():
        t['_current_gate'] = bool(integrity.blockers(api(), root, db, tasks, tid, closing=True) + team.blockers(api(), root, db, tasks, tid, closing=True))
    gaps = integrity.records(db, 'gap')
    held = {tid: [x for x in [gap_issue(t, gaps, 'running')] if x] for tid, t in tasks.items()}  # an expertise gap that stops the start
    return {'schema': SCHEMA, 'config': cfg, 'revision': seq, 'observed_at': now(),
            'integrity': {k: integrity.records(db,k) for k in ['instance','scope','change','pause','appointment','participation_rule','participation_obligation','instance_config','conflict','notice',
                                                               'launch','inbox','project_pause','pm_session']},
            'gaps': {gid: gap_view(g, tasks) for gid, g in gaps.items()},
            'top_level': counts(children(tasks, None), tasks),
            'tasks': [dict(t, state_label=STATE_NAMES[t['state']], dispatcher=t['manager'], child_counts=counts(children(tasks, t['id']), tasks),
                           needs_recheck=t['state'] == 'done' and not effective_done(t,tasks),
                           ready=t['state'] == 'planned' and not reasons(t, tasks, cfg) and not gates[t['id']] and not held[t['id']],
                           integrity_issues=gates[t['id']],
                           readiness_issues=reasons(t, tasks, cfg)+[x['code'] for x in gates[t['id']]]+held[t['id']],
                           completion_pending=[d for d in t.get('completion_requires', []) if not effective_done(tasks[d], tasks)],
                           review_current=bool(t.get('review') and t['review']['basis'] == basis(t, tasks)))
                      for t in tasks.values()]}


def record(root, db, cmd):
    """Conflict rulings and notices: recorded facts; tasks keep their state (rework stays with the manager)."""
    cfg, tasks, people, actor, op = config(db), task_map(db), roster(root), cmd['actor'], cmd['op']
    rid = cmd.get('id')
    require(nonempty(rid) and re.fullmatch(SAFE_ID, rid) and rid not in integrity.records(db, op), 'new simple ' + op + ' id required')
    if op == 'notice':
        require(actor in {cfg['pm_actor'], cfg.get('frontdesk_actor')} - {None}, 'PM or front desk records notices')
        who = cmd.get('people', [])
        require(cmd.get('kind') in NOTICES and nonempty(cmd.get('ref')) and nonempty(cmd.get('summary')), 'notice needs kind (F1_output/Q0/Q1/Q2), ref and summary')
        require(strings(who) and (who or cmd['kind'] in {'Q0', 'Q2'}), 'F1 and Q1 notices name the people to inform')
        require(not people or set(who) <= set(people['people']), 'unknown person ids (not in people.json): ' + ','.join(sorted(set(who) - set((people or {}).get('people', {})))))
        value = dict(id=rid, kind=cmd['kind'], ref=cmd['ref'], summary=cmd['summary'], people=who)
    else:
        ids, parties, gone, level = cmd.get('task_ids'), cmd.get('parties'), cmd.get('overturned', []), cmd.get('level')
        require(strings(ids) and ids and all(t in tasks for t in ids), 'conflict names registered tasks')
        require(strings(parties) and parties and all(nonempty(cmd.get(k)) for k in ['issue', 'basis', 'resolution', 'decided_by']), 'parties, issue, basis, resolution and decided_by required')
        require(level in CONFLICT_LEVELS and strings(gone) and set(gone) <= set(ids), 'level tool/master/owner/pm/human; overturned tasks are among the conflict tasks')
        instances = integrity.records(db, 'instance')
        involved = {instances.get(i, {}).get('profession') for t in ids for i in (tasks[t]['owner'], tasks[t].get('executor'))} - {None}
        me = instances.get(actor, {})
        fits = {'tool': actor in set(parties) | {cfg['pm_actor']},
                'master': bool(me.get('master') and me.get('active') and me.get('profession') in involved),
                'owner': actor in {tasks[t]['owner'] for t in ids}, 'pm': actor == cfg['pm_actor'],
                'human': actor in {cfg['pm_actor'], cfg.get('frontdesk_actor')} - {None}}[level]
        require(fits, 'the recording actor does not fit decision level ' + level)
        if level == 'human':
            require(nonempty(cmd.get('quote')) and cmd['decided_by'] == cmd.get('person'), 'a human ruling records the person as decided_by and the exact quote')
            authorized(cmd['person'], ids, tasks, people)
        elif level != 'tool':
            require(cmd['decided_by'] == actor, 'decided_by is the recording decider; no majority of instances')
        value = {k: cmd[k] for k in ['task_ids', 'parties', 'issue', 'basis', 'resolution', 'decided_by', 'level'] + [k for k in ['person', 'quote'] if k in cmd]}
        value.update(id=rid, overturned=gone)
    value.update(recorded_by=actor, at=now(), revision=1)
    integrity.save(api(), db, op, value)
    return {'record': value}


def may_decide(person, tids, tasks, people):
    """Whether the person may decide for every listed task (with none listed: for the project)."""
    try:
        for tid in tids or [None]:
            authorized(person, [tid], tasks, people)
        return True
    except TaskError:
        return False


def gap_label(g):
    return '非' + g['domain'] + '专家产出，未经具备资质的人审定'


def gap_of(t, gaps):
    return gaps.get(t['gap']) if isinstance(t.get('gap'), str) else None


def gap_view(g, tasks):
    return dict(g, task_ids=sorted(tid for tid, t in tasks.items() if t.get('gap') == g['id']))


def gap_items(t, gaps):
    """t's awaiting items with the human to-do of its gap in place (tasks not closed); to-dos of other or resolved gaps removed."""
    g, items = gap_of(t, gaps), t.get('awaiting', [])
    want = None
    if g and g['status'] == 'human' and t['state'] not in TERMINAL:
        want = {'person': g['decision']['person'], 'action': 'execute', 'ref': g['id'],
                'item': '需要具备' + g['qualification'] + '的人处理：' + g['why'] + '（缺口 ' + g['id'] + '）'}
    if not isinstance(items, list):
        return items
    keep = [a for a in items if a == want or not (isinstance(a, dict) and isinstance(a.get('ref'), str) and a['ref'] in gaps
                                                  and str(a.get('item')).endswith('（缺口 ' + a['ref'] + '）'))]
    return keep + ([want] if want and want not in keep else [])


def gap_issue(t, gaps, state):
    """Why a task linked to an expertise gap may not move to state, or None."""
    g = gap_of(t, gaps)
    if not g or state not in {'running', 'waiting_review', 'done'}:
        return None
    tail = '（缺口 ' + g['id'] + '）'
    if g['status'] == 'open':
        return '缺 ' + g['domain'] + ' 专家，等人选择' + tail
    if g['status'] == 'expert':
        return '等 ' + g['decision']['expert'] + ' 的结论' + tail
    if g['status'] == 'human':
        return '人工待办：需要具备' + g['qualification'] + '的人处理：' + g['why'] + tail
    if g['status'] == 'self' and state != 'running' and not any(gap_label(g) in e for e in t['evidence']):
        return '交出与完成时，成果证据须有一条标明「' + gap_label(g) + '」' + tail
    return None


def gap_link(db, before, after, cmd, tasks, people):
    """A task's link to a gap (create, update) and its gap's human to-do (every task write)."""
    gaps = integrity.records(db, 'gap')
    if 'gap' in after and after['gap'] is None:
        after.pop('gap')  # stored only on tasks that have one
    old, new = (before or {}).get('gap'), after.get('gap')
    if new != old and isinstance(new, str) and re.fullmatch(r'G-\d{3,}', new):  # other values fail validation
        g = gaps.get(new)
        require(g is not None, 'unknown gap: ' + new)
        require(g['status'] != 'closed', 'gap ' + new + ' is closed; register new work with gap_open, which follows its standing choice')
        require(not g['decision'] or may_decide(g['decision']['person'], [after['id']], tasks, people),
                'gap ' + new + ' was decided by a person without authority for ' + after['id'] + '; open a gap for it with gap_open')
    if new != old and old in gaps and gaps[old]['status'] != 'closed':
        require(nonempty(cmd.get('quote')), 'leaving gap ' + old + ' before it is closed needs the deciding person and exact quote')
        authorized(cmd.get('person'), [after['id']], tasks, people)
    items = gap_items(after, gaps)
    if items != after.get('awaiting', []):
        after['awaiting'] = items


def gap_op(root, db, cmd):
    """Open, decide and close expertise gaps. Linked tasks change only in coordination facts: gap and awaiting."""
    cfg, tasks, people, actor, op = config(db), task_map(db), roster(root), cmd['actor'], cmd['op']
    gaps, desks, rule, touched = integrity.records(db, 'gap'), {cfg['pm_actor'], cfg.get('frontdesk_actor')} - {None}, None, []

    def handles(ids):
        return actor in desks or (bool(ids) and all(actor in {tasks[t]['owner'], tasks[t]['manager']} for t in ids))

    def put(tid, gid=None):
        before = {k: v for k, v in tasks[tid].items() if not k.startswith('_')}
        after = json.loads(canon(before))
        if gid:
            after['gap'] = gid
        items = gap_items(after, gaps)
        if items != after.get('awaiting', []):
            after['awaiting'] = items
        if after != before:
            after.update(revision=before['revision'] + 1, updated_at=now())
            tasks[tid] = after
            validation(after, tasks)
            check_people(after, people)
            db.execute('INSERT OR REPLACE INTO tasks VALUES (?,?)', (tid, canon(after)))
            touched.append((tid, before, after))

    if op == 'gap_open':
        ids = cmd.get('task_ids', [])
        require(strings(ids) and len(ids) == len(set(ids)) and all(t in tasks for t in ids), 'task_ids must list registered tasks once each')
        require(handles(ids), 'PM, front desk, or the owner or manager of every listed task opens a gap')
        require(all(nonempty(cmd.get(k)) for k in ['domain', 'why', 'qualification']) and cmd.get('kind') in GAP_KINDS and team.risk(cmd.get('risk')) is not None,
                'gap needs domain, kind (not_in_kit/not_set_up), why, qualification and risk (F0–F5)')
        domain, regs = cmd['domain'].strip(), team.registries(api(), root)
        profession = domain if domain in regs else next((p for p, r in regs.items() if r['name'] == domain), None)
        if cmd['kind'] == 'not_in_kit':
            require(profession is None, domain + ' is a profession of this kit; open it as not_set_up')
        else:
            require(profession is not None, 'not_set_up names a profession of this kit by registry id or name')
            live = sorted(i['id'] for i in integrity.records(db, 'instance').values() if i.get('profession') == profession and i.get('active'))
            require(not live, profession + ' is set up (' + ','.join(live) + '); dispatch the work to it instead of opening a gap')
            conf = team.confirmed(api(), root, db)
            configured = [e['id'] for e in (conf or {}).get('entries', []) if e['profession'] == profession and e['count'] > 0]
            require(not configured, profession + ' is in the confirmed instance configuration (' + ','.join(configured) + '); derive an instance when its work is ready instead of opening a gap')
            domain = regs[profession]['name']
        # The person's latest standing choice for this domain, among those they may make for these tasks.
        prior = [g for g in gaps.values() if g['domain'] == domain and (g['decision'] or {}).get('standing') and may_decide(g['decision']['person'], ids, tasks, people)]
        rule = max(prior, key=lambda g: (g['decision']['at'], g['id']), default=None)
        if rule and rule['decision']['choice'] == 'self' and team.risk(cmd['risk']) < team.risk(rule['risk']):
            rule = None  # the risk the person accepted was lower; ask again
        if rule and rule['decision']['choice'] == 'self':
            gid = rule['id']
        else:
            gid = 'G-' + str(1 + max([int(k[2:]) for k in gaps if re.fullmatch(r'G-\d{3,}', k)] or [0])).zfill(3)
        for tid in ids:
            held = gap_of(tasks[tid], gaps)
            require(tasks[tid]['state'] not in TERMINAL, tid + ' is closed; reopen it or register the follow-up work first')
            require(not held or held['id'] == gid or held['status'] == 'closed', tid + ' already waits on gap ' + str(tasks[tid].get('gap')) + '; split the work by missing profession')
        if gid not in gaps:
            value = dict(id=gid, domain=domain, kind=cmd['kind'], why=cmd['why'], qualification=cmd['qualification'], risk=cmd['risk'],
                         opened_by=actor, opened_at=now(), status='open', decision=None, result=None, revision=1, updated_at=now())
            if profession:
                value['profession'] = profession
            if rule:  # expert or human: this work gets its own handover and result under the standing choice
                value.update(status=rule['decision']['choice'], decision=dict(rule['decision'], standing_from=rule['id']))
            integrity.save(api(), db, 'gap', value)
            gaps[gid] = value
        for tid in ids:
            put(tid, gid)
    else:
        g = gaps.get(cmd.get('gap'))
        require(g is not None, 'unknown gap')
        require(cmd.get('expected_revision') == g['revision'], 'stale gap revision; reload status')
        gid, linked = g['id'], sorted(tid for tid, t in tasks.items() if t.get('gap') == g['id'])
        if op == 'gap_decide':
            require(actor in desks, "PM or front desk records the person's choice")
            require(g['status'] != 'closed', 'gap ' + gid + ' is closed; a new need is opened as a new gap')
            choice, standing = cmd.get('choice'), cmd.get('standing', True)
            require(choice in GAP_CHOICES and type(standing) is bool, 'choice must be expert, self or human; standing boolean')
            require(nonempty(cmd.get('quote')), "the person's exact quote is required")
            require(nonempty(cmd.get('expert')) if choice == 'expert' else cmd.get('expert') is None,
                    'expert names the designated expert agent or qualified person, for choice expert only')
            for tid in linked or [None]:
                authorized(cmd.get('person'), [tid], tasks, people)
            decision = dict(choice=choice, person=cmd['person'], quote=cmd['quote'], standing=standing, at=now())
            if choice == 'expert':
                decision['expert'] = cmd['expert']
            value = dict(g, status=choice, decision=decision)
        else:
            require(g['status'] in {'expert', 'human'}, 'only a gap given to an expert or a person closes, with their result')
            require(handles(linked), 'PM, front desk, or the owner or manager of every linked task records the result')
            require(nonempty(cmd.get('source')) and strings(cmd.get('evidence')) and cmd['evidence'], 'source of the received result and evidence (non-empty list) required')
            value = dict(g, status='closed', result=dict(source=cmd['source'], evidence=cmd['evidence'], by=actor, at=now()))
        value.update(revision=g['revision'] + 1, updated_at=now())
        integrity.save(api(), db, 'gap', value)
        gaps[gid] = value
        for tid in linked:
            put(tid)
    result = {'record': gap_view(gaps[gid], tasks)}
    if rule:
        result.update(existing=rule['id'], choice=rule['decision']['choice'])
    return result, touched


def execute(project, cmd, _db=None, _applying=None):
    root = Path(project).resolve()
    require(root.is_dir(), 'project directory missing')
    owns_db = _db is None
    reads = {'status', 'events'} | integrity.READ_OPS | team.READ_OPS | views.READ_OPS | platform.READ_OPS
    db = connect(root, readonly=cmd.get('op') in reads) if owns_db else _db
    try:
        op = cmd.get('op')
        if op in reads:
            if owns_db:
                db.execute('BEGIN')
            if op in views.READ_OPS:
                result = views.execute(api(), root, db, cmd)
            elif op in platform.READ_OPS:
                result = platform.execute(api(), root, db, cmd)
            elif op in team.READ_OPS:
                result = team.execute(api(), root, db, cmd)
            elif op in integrity.READ_OPS:
                result = integrity.execute(api(), root, db, cmd)
            elif op == 'status':
                result = snapshot(db)
            else:
                config(db)
                after = cmd.get('after', 0)
                limit = cmd.get('limit', 100)
                require(type(after) is int and after >= 0 and type(limit) is int and 1 <= limit <= 1000, 'invalid cursor/limit')
                if cmd.get('task_id'):
                    rows = db.execute('SELECT * FROM events WHERE seq > ? AND task_id = ? ORDER BY seq LIMIT ?', (after, cmd['task_id'], limit)).fetchall()
                else:
                    rows = db.execute('SELECT * FROM events WHERE seq > ? ORDER BY seq LIMIT ?', (after, limit)).fetchall()
                if cmd.get('full') is True:
                    result = {'events': [{k: json.loads(r[k]) if k in {'command', 'before_data', 'after_data', 'result'} and r[k] else r[k] for k in r.keys()} for r in rows]}
                else:
                    result = {'events': [brief(r) for r in rows], 'note': 'summaries; add "full": true for the recorded before and after'}
            if owns_db:
                db.commit()
            return result
        require(op in {'init', 'configure', 'create', 'update', 'transition', 'review', 'human_review', 'report', 'handoff', 'reassign', 'conflict', 'notice'} | GAP_OPS | integrity.WRITE_OPS | team.WRITE_OPS | platform.WRITE_OPS, 'unknown operation')
        require(nonempty(cmd.get('event_id')) and nonempty(cmd.get('actor')), 'event_id and actor required')
        if owns_db:
            db.execute('BEGIN IMMEDIATE')
        old = db.execute('SELECT command,result FROM events WHERE event_id=?', (cmd['event_id'],)).fetchone()
        if old:
            require(old['command'] == canon(cmd), 'event id reused with different content')
            if owns_db:
                db.commit()
            return json.loads(old['result'])
        before, after, overturned, touched = None, None, [], []
        if op == 'init':
            require(db.execute('SELECT COUNT(*) FROM meta').fetchone()[0] == 0, 'already initialized')
            cfg = cmd['config']
            require(nonempty(cfg.get('project')) and nonempty(cfg.get('pm_actor')) and nonempty(cfg.get('authorization')), 'project/PM/authorization required')
            require(nonempty(cfg.get('frontdoor_id')), 'real frontdoor task id required (frontdoor_id)')
            require(type(cfg.get('max_slots')) is int and 1 <= cfg['max_slots'] <= 64, 'max_slots must be 1..64')
            require(cmd['actor'] == cfg['pm_actor'], 'init actor must be PM')
            db.execute('INSERT INTO meta VALUES (?,?)', ('config', canon(cfg)))
            result = {'initialized': True, 'schema': SCHEMA}
        elif op in team.WRITE_OPS:
            result = team.execute(api(), root, db, cmd)
        elif op in integrity.WRITE_OPS:
            result = integrity.execute(api(), root, db, cmd)
        elif op in platform.WRITE_OPS:
            result = platform.execute(api(), root, db, cmd)
        elif op == 'configure':
            # The front desk faces people; PM may let it record their real decisions.
            cfg = config(db)
            require(cmd['actor'] == cfg['pm_actor'], 'only PM configures the coordination entry')
            require({'frontdesk_actor', 'max_slots', 'limits'} & set(cmd), 'configure frontdesk_actor, max_slots or limits')
            if 'frontdesk_actor' in cmd:
                desk = cmd['frontdesk_actor']
                require(desk is None or (nonempty(desk) and desk != cfg['pm_actor']), 'frontdesk_actor must be a distinct actor or null')
                cfg['frontdesk_actor'] = desk
            if {'max_slots', 'limits'} & set(cmd):
                # How many run at once and the unattended limits are the person's decision.
                require(nonempty(cmd.get('quote')), 'max_slots and limits need the deciding person and exact quote')
                authorized(cmd.get('person'), [None], task_map(db), roster(root))
                if 'max_slots' in cmd:
                    require(type(cmd['max_slots']) is int and 1 <= cmd['max_slots'] <= 64, 'max_slots must be 1..64')
                    cfg['max_slots'] = cmd['max_slots']
                if 'limits' in cmd:
                    platform.check_limits(api(), cmd['limits'])
                    cfg['limits'] = dict(cfg.get('limits', {}), **cmd['limits'])
            db.execute("UPDATE meta SET value=? WHERE key='config'", (canon(cfg),))
            result = {'configured': True, 'frontdesk_actor': cfg.get('frontdesk_actor'), 'max_slots': cfg['max_slots'], 'limits': platform.limits(cfg)}
        elif op in {'conflict', 'notice'}:
            result = record(root, db, cmd)
            overturned = result['record'].get('overturned', [])
        elif op in GAP_OPS:
            result, touched = gap_op(root, db, cmd)
        else:
            cfg, tasks = config(db), task_map(db)
            people = roster(root)
            actor = cmd['actor']
            team.authorize(api(), root, db, cmd, tasks)
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
                if data.get('project_level'):
                    manager = actor if team.workflow_manager(api(), root, db, actor, parent, tasks) else cfg['pm_actor']
                require(actor == manager, 'only responsible manager may create this level')
                allowed = {'id','parent','title','owner','checker','goal','inputs','outputs','criteria','dependencies','completion_requires','resources','slots','executor','human_required','expanded','next_action','source',
                           'kind','stage','direction','people','derived_from','awaiting','project_level','role','artifact_digests',
                           'difficulty','risk','risk_reason','origin','gap','order','timeout_minutes'}
                require(set(data) <= allowed, 'unknown create fields')
                after = dict(data, parent=parent, manager=manager, state='planned', revision=1,
                             work_revision=1, evidence=[], review=None, human_review=None,
                             created_at=now(), updated_at=now(), last_report=None,
                             reason='registered before execution')
                for key, default in [('dependencies',[]),('completion_requires',[]),('resources',[]),('slots',1),('executor',None),('human_required',False),('expanded',False),('source',''),
                                     ('kind','work'),('stage',None),('direction',''),('people',{}),('derived_from',[]),('awaiting',[])]:
                    after.setdefault(key, default)
                instance = integrity.records(db, 'instance').get(after['owner'])
                if instance:
                    require(not after.get('role') or after['role'] == instance['role'], 'instance role mismatch')
                    after['role'] = instance['role']
                integrity.observe(api(), root, after)
                tasks[tid] = after
                gap_link(db, None, after, cmd, tasks, people)
                validation(after, tasks)
                check_people(after, people)
                problem = team.level_issue(api(), db, after) or team.master_issue(api(), db, cfg, after)
                require(not problem, problem)
            else:
                tid = cmd['task_id']
                require(tid in tasks, 'task missing')
                before = tasks[tid]
                require(cmd.get('expected_revision') == before['revision'], 'stale revision; reload task before editing (current revision ' + str(before['revision']) + ')')
                after = json.loads(canon(before))
                if op in {'update', 'transition', 'report'}:
                    # The dispatcher may also record coordination facts, such as which person the task now waits for.
                    coordinating = op == 'update' and actor == after['manager'] and set(cmd.get('changes') or {}) <= COORDINATION | {'next_action'}
                    require(actor == after['owner'] or coordinating or (op == 'transition' and (actor == after['manager'] or platform.launch_bound(api(), db, cfg, cmd, before))),
                            'task state belongs to its owner')
                if op == 'update':
                    require(after['state'] not in TERMINAL, 'reopen before editing terminal task')
                    changes = cmd['changes']
                    allowed = {'next_action','evidence','executor','expanded','source','reason','title','goal','inputs','outputs','criteria','dependencies','completion_requires','resources','slots','human_required','checker','artifact_digests',
                               'difficulty','risk','risk_reason'} | COORDINATION
                    require(set(changes) <= allowed, 'immutable/unknown field')
                    require(nonempty(cmd.get('reason')), 'change reason required')
                    # Difficulty and risk are labels of the dispatcher; lowering one needs this reason, F0/F1 also a person.
                    if set(changes) & {'goal','inputs','outputs','criteria','dependencies','completion_requires','human_required','checker','people','derived_from','difficulty','risk','risk_reason'}:
                        require(actor == after['manager'] or nonempty(cmd.get('scope_authorization')), 'scope/interface change needs manager authorization reference')
                    old_risk, new_risk = team.risk(before.get('risk')), team.risk(changes.get('risk', before.get('risk')))
                    if old_risk is not None and old_risk <= 1 and (new_risk is None or new_risk > old_risk):
                        require(nonempty(cmd.get('quote')), 'lowering an F0/F1 risk needs the deciding person and exact quote')
                        authorized(cmd.get('person'), [tid], tasks, people)
                    if before['state'] == 'running' and changes.get('executor', before.get('executor')) != before.get('executor'):
                        require(False, 'stop current executor before reassignment')
                    after.update(changes)
                    integrity.observe(api(), root, after)
                    require(not before['human_required'] or after['human_required'] or nonempty(cmd.get('scope_authorization')), 'cannot silently remove human review')
                    if set(changes) & {'executor', 'difficulty'}:
                        problem = team.level_issue(api(), db, after)
                        require(not problem, problem)
                    if set(changes) - {'next_action','executor','source','reason'} - COORDINATION:
                        after['work_revision'] += 1
                        after['review'] = after['human_review'] = None
                    after['reason'] = cmd['reason']
                elif op == 'transition':
                    state = cmd['state']
                    change_id = cmd.get('change_id') or _applying
                    if state in RETIRED and not change_id:
                        linked = [c['id'] for c in integrity.records(db, 'change').values()
                                  if c['state'] not in {'closed', 'superseded'} and tid in c['affected_tasks']]
                        require(len(linked) <= 1, 'multiple changes affect this task; explicit change_id required')
                        change_id = linked[0] if linked else None
                    if state == 'cancelled' and change_id:
                        state = 'deprecated'
                    require(state in STATES and state != after['state'], 'invalid/no-op transition')
                    retirement = integrity.deprecation(api(), db, tid, change_id, _applying) if state == 'deprecated' else None
                    require(retirement or nonempty(cmd.get('reason')), 'transition reason required')
                    if state == 'running':
                        require(not reasons(after, tasks, cfg), '; '.join(reasons(after, tasks, cfg)))
                        require(nonempty(cmd.get('execution_receipt')), 'actual execution/start receipt required')
                    if before['state'] == 'running' and state != 'running':
                        require(nonempty(cmd.get('stop_evidence')), 'actual stop/yield evidence required before releasing resources')
                    check_usage(cmd.get('usage'))
                    if before['state'] == 'running' and state == 'waiting_review':
                        # Handing over to the dispatcher: the result and evidence paths go with it.
                        handed = cmd.get('evidence')
                        require(handed is None or (strings(handed) and handed), 'evidence must be a non-empty path list')
                        if handed and handed != after['evidence']:
                            after.update(evidence=handed, work_revision=after['work_revision'] + 1, review=None, human_review=None)
                        require(after['evidence'], 'hand over with the result and evidence paths (evidence)')
                    problem = gap_issue(after, integrity.records(db, 'gap'), state)
                    require(not problem, problem)
                    after.pop('blocked_by', None)
                    if state == 'blocked' and cmd.get('blocked_by') is not None:
                        ref = cmd['blocked_by']
                        require(isinstance(ref, dict) and set(ref) == {'task_id'} and ref['task_id'] in tasks and ref['task_id'] != tid, 'blocked_by must be {task_id} of another registered task')
                        after['blocked_by'] = ref
                    if state == 'running' and before.get('sent_back'):
                        # Same task, next version: earlier checks and decisions no longer apply.
                        after['rework'] = rework(cmd, before, before['sent_back'])
                        escalated = platform.check_escalation(api(), root, cfg, cmd, before, tasks, 'rework', after['rework']['count'])
                        if escalated:
                            after['rework']['escalation'] = escalated
                        after.pop('sent_back')
                        after.update(work_revision=after['work_revision'] + 1, review=None, human_review=None)
                    if before['state'] in TERMINAL and state != 'deprecated':
                        require(state in {'planned','blocked'} and actor == after['manager'], 'only manager may reopen closed task')
                        # Reopen from ancestors downwards; cannot hide new work under done.
                        parent = after['parent']
                        while parent:
                            require(tasks[parent]['state'] not in TERMINAL, 'reopen closed ancestors first')
                            parent = tasks[parent]['parent']
                        if before['state'] == 'done':
                            # Work not yet used downstream is reworked in place; used work is replaced by a successor.
                            users = sorted(x['id'] for x in tasks.values() if tid in x['dependencies'] + x.get('completion_requires', []) and x['state'] in {'running', 'waiting_review', 'done'})
                            require(not users, 'output already used by ' + ','.join(users) + '; replace it through a successor in a change plan instead of reopening')
                            after['rework'] = rework(cmd, before, None)
                            escalated = platform.check_escalation(api(), root, cfg, cmd, before, tasks, 'rework', after['rework']['count'])
                            if escalated:
                                after['rework']['escalation'] = escalated
                        after['work_revision'] += 1
                        after['review'] = after['human_review'] = None
                        after.pop('deprecation', None)
                    if state in TERMINAL:
                        require(actor == after['manager'], 'responsible manager closes task after owner reports')
                        require(all(x['state'] in TERMINAL for x in children(tasks, tid)), 'open children remain')
                    if state == 'done':
                        require(after['evidence'], 'deliverable evidence missing')
                        require(all(effective_done(tasks[d],tasks) for d in after['dependencies']), 'dependencies not complete/current')
                        pending = [d for d in after.get('completion_requires', []) if not effective_done(tasks[d], tasks)]
                        require(not pending, 'completion prerequisites not complete/current: ' + ','.join(pending))
                        require(all(x['state'] in RETIRED or effective_done(x,tasks) for x in children(tasks,tid)), 'child verification stale')
                        b = basis(after, tasks)
                        require(after['review'] and after['review']['basis'] == b and after['review']['outcome'] == 'passed', 'current professional verification required')
                        if after['human_required']:
                            require(after['human_review'] and after['human_review']['basis'] == b and after['human_review']['outcome'] == 'approved', 'current explicit human review required')
                        problem = team.verification_issue(api(), root, db, after)
                        require(not problem, problem)
                    if before['state'] == 'done' and state != 'done':
                        # Downstream completed work is kept as historical fact;
                        # record stale dependency visibility rather than rewriting it.
                        after['reason'] = cmd.get('reason', '')
                    after['state'], after['reason'] = state, cmd.get('reason', '')
                    if retirement:
                        after['deprecation'] = retirement
                        after['reason'] = retirement['remark']
                elif op == 'review':
                    require(after['state'] not in TERMINAL, 'reopen closed task before new verification')
                    require(actor == after['checker'], 'designated checker only')
                    if any(team.within(tid, a['root_tasks'], tasks) for a in integrity.records(db, 'appointment').values()):
                        require(actor not in {after['owner'], after.get('executor')}, 'team delivery requires an independent checker')
                    require(cmd.get('outcome') in {'passed','failed'}, 'invalid verification outcome')
                    require(strings(cmd.get('evidence')) and cmd['evidence'], 'verification evidence required')
                    require(cmd.get('criteria_checked') == after['criteria'], 'must explicitly check all listed criteria')
                    require(after['evidence'], 'work evidence required before review')
                    require(cmd['outcome'] == 'passed' or cmd.get('cause') in REWORK, 'a failed check records its cause: execution, requirement_clarification, basis_changed or other')
                    after['review'] = {'basis':basis(after,tasks),'checker':actor,'outcome':cmd['outcome'],'evidence':cmd['evidence'],'at':now(),
                                       'independence':team.independence(api(), root, db, after, actor)}
                    after.pop('sent_back', None)
                    if cmd['outcome'] == 'failed':
                        # Sent back: the next start of this task is its rework, with this cause.
                        after['review']['cause'] = cmd['cause']
                        after['sent_back'] = {'cause': cmd['cause'], 'checker': actor, 'producer': after.get('executor') or after['owner'], 'at': now()}
                elif op == 'human_review':
                    require(after['state'] not in TERMINAL, 'reopen closed task before new human decision')
                    require(actor in {cfg['pm_actor'], cfg.get('frontdesk_actor')} - {None}, 'unified frontdoor records human decisions')
                    require(cmd.get('outcome') in {'approved','changes_requested','deferred'}, 'invalid human decision')
                    require(all(nonempty(cmd.get(k)) for k in ['presented_ref','source','quote','scope']), 'actual presentation, reply source, exact quote and scope required')
                    person = cmd.get('person')
                    if people:
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
                    check_usage(cmd.get('usage'))
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
                    problem = team.level_issue(api(), db, after) or team.master_issue(api(), db, cfg, after)
                    require(not problem, problem)
                elif op == 'reassign':
                    # Within the profession, by the dispatcher, with the reason; the new executor continues from progress.
                    require(actor == after['manager'], 'the dispatcher (task manager) reassigns')
                    require(after['state'] not in TERMINAL, 'closed task cannot be reassigned')
                    require(cmd.get('reason_kind') in {'failed_check', 'executor_unable', 'other'} and nonempty(cmd.get('note')), 'reason_kind (failed_check/executor_unable/other) and note required')
                    instances = integrity.records(db, 'instance')
                    target, previous = instances.get(cmd.get('to')), before.get('executor') or before['owner']
                    require(target and target.get('active', True) and cmd['to'] != previous, 'target must be another active registered instance')
                    known = instances.get(previous, {}).get('profession')
                    require(not known or not target.get('profession') or target['profession'] == known, 'reassign within the same profession')
                    if before['state'] == 'running':
                        require(nonempty(cmd.get('stop_evidence')), 'actual stop or progress evidence of the current executor required')
                        after['state'] = 'planned'
                    if before['owner'] == before.get('executor'):
                        require(not children(tasks, tid), 'transfer leaf responsibility only; resolve child managers explicitly')
                        after['owner'] = cmd['to']
                    after['executor'], after['reason'] = cmd['to'], cmd['note']
                    after['reassigned'] = before.get('reassigned', 0) + 1
                    escalated = platform.check_escalation(api(), root, cfg, cmd, before, tasks, 'reassign', after['reassigned'])
                    if escalated:
                        after['reassign_escalation'] = escalated
                    tasks[tid] = after
                    problem = team.level_issue(api(), db, after) or team.master_issue(api(), db, cfg, after)
                    require(not problem, problem)
                    busy = [x['other_task'] for x in integrity.blockers(api(), root, db, tasks, tid) if x['code'] == 'instance_or_write_busy']
                    require(not busy, 'target instance is busy with ' + ','.join(busy))
                after['revision'] += 1
                after['updated_at'] = now()
                tasks[tid] = after
                gap_link(db, before, after, cmd, tasks, people)
                validation(after, tasks)
                check_people(after, people)
                if after['state'] == 'running':
                    require(not reasons(after,tasks,cfg), '; '.join(reasons(after,tasks,cfg)))
            if op == 'transition' and after['state'] in {'running', 'done'}:
                problems = integrity.blockers(api(), root, db, tasks, tid, closing=after['state']=='done', applying=_applying)
                problems += team.blockers(api(), root, db, tasks, tid, closing=after['state']=='done')
                require(not problems, 'integrity gate: ' + canon(problems))
            for key in list(after):
                if key.startswith('_'):
                    after.pop(key)
            db.execute('INSERT OR REPLACE INTO tasks VALUES (?,?)', (tid,canon(after)))
            result = {'task': after}
        occurred = cmd.get('occurred_at', now())
        cur = db.execute('INSERT INTO events(event_id,command,task_id,actor,occurred_at,recorded_at,before_data,after_data,result) VALUES (?,?,?,?,?,?,?,?,?)',
                         (cmd['event_id'],canon(cmd),after['id'] if after else None,cmd['actor'],occurred,now(),canon(before) if before else None,canon(after) if after else None,canon(result)))
        result['event_seq'] = cur.lastrowid
        db.execute('UPDATE events SET result=? WHERE seq=?',(canon(result),cur.lastrowid))
        for tid in overturned:
            # One event per overturned task, so its timeline and the ledger show the ruling.
            note = {'op': 'overturned', 'conflict': result['record']['id'], 'task_id': tid, 'reason': result['record']['resolution']}
            db.execute('INSERT INTO events(event_id,command,task_id,actor,occurred_at,recorded_at,before_data,after_data,result) VALUES (?,?,?,?,?,?,?,?,?)',
                       (cmd['event_id']+':overturned:'+tid, canon(note), tid, cmd['actor'], occurred, now(), None, None, canon({'conflict': note['conflict']})))
        for tid, old_task, new_task in touched:
            # One event per task a gap operation linked or whose human to-do it changed, so its timeline shows the gap.
            gap = result['record']
            note = {'op': op, 'gap': gap['id'], 'task_id': tid, 'reason': '缺口 ' + gap['id'] + '：' + GAP_STATES[gap['status']]}
            db.execute('INSERT INTO events(event_id,command,task_id,actor,occurred_at,recorded_at,before_data,after_data,result) VALUES (?,?,?,?,?,?,?,?,?)',
                       (cmd['event_id']+':gap:'+tid, canon(note), tid, cmd['actor'], occurred, now(), canon(old_task), canon(new_task), canon({'gap': gap['id']})))
        if owns_db:
            db.commit()
        return result
    except Exception:
        if owns_db:
            db.rollback()
        raise
    finally:
        if owns_db:
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


def read_db(root, fn):
    db = connect(root, readonly=True)
    try:
        db.execute('BEGIN')
        return fn(db)
    finally:
        db.close()


def render(project):
    root = Path(project).resolve()
    data = execute(root,{'op':'status'})
    pages = read_db(root, lambda db: views.pages(api(), root, db))
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
            return '['+esc(ref)+'](<'+ROOT_MARK+plain+('#'+ref.split('#',1)[1] if '#' in ref else '')+'>)'
        return esc(ref)
    def save(rel, text):
        # Links in a view are relative to the view file, so the project can move and the views can be shared.
        atomic(local(root, rel), text.replace(ROOT_MARK, os.path.relpath(root, (root / rel).parent) + '/'))
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
    def choice_line(g):
        held = [tasks[x] for x in g['task_ids'] if tasks[x]['state'] not in TERMINAL]
        return (f"- 缺口 {g['id']}：缺 {esc(g['domain'])} 专家（需要：{esc(g['qualification'])}），等人选择：指定专家、由当前实例完成或列为人工待办"
                + ('；挡住：' + '、'.join(tlink(x) for x in held) if held else '') + '\n')
    # Expertise gaps still waiting for the person's choice come first among the items waiting for people.
    choosing = ''.join(choice_line(g) for g in sorted(data['gaps'].values(), key=lambda g: g['id']) if g['status'] == 'open')
    summary = data['top_level']
    notices = sorted(data['integrity']['notice'].values(), key=lambda n: (n['at'], n['id']))
    def notice_line(n):
        return f"- {esc(n['summary'])}（{NOTICES[n['kind']]}）；查看：{link(n['ref'])}" + ('；告知：' + '、'.join(who(p) for p in n['people']) if n['people'] else '') + '\n'
    urgent = ''.join(notice_line(n) for n in notices if n['kind'] == 'Q0')
    urgent = '## 立即（Q0）\n\n' + urgent + '\n' if urgent else ''
    head = f"# 项目任务总览\n\n只读派生视图。任务事实由 `management/runtime/tasks.sqlite3` 维护；专业内容仍在原源。\n\n项目：{esc(data['config']['project'])}。读取时间：{data['observed_at']}。事件修订：{data['revision']}。\n\n顶层完成 {summary['done']}/{summary['total']}，剩余 {summary['remaining']}；已弃用 {summary['deprecated']}，已取消 {summary['cancelled']}。仅统计已登记范围，未登记远期不计入。\n\n另见：[全程计划表](plan.md)｜[项目总入口](project.md)｜[群摘要](digest.md)｜[需求变更流水](changes.md)｜[交付集合](scopes.md)｜[人审点](human-points.md)｜[实例台账](ledger.md)\n\n"
    head += pages.pop('index-list')
    head += '\n待人核验（各项独立决定；不跨越前置审阅）：\n\n'
    for t in tasks.values():
        b_current = t.get('human_review') and t['human_review']['basis'] == basis(t,tasks) and t['human_review']['outcome']=='approved'
        if t['human_required'] and t['state'] == 'waiting_review' and not b_current:
            head+=f"- [{t['id']} {esc(t['title'])}](tasks/{t['id']}.md)\n"
    # One snapshot for state, paged read of immutable events up to its revision.
    events=[]
    cursor=0
    while True:
        batch=execute(root,{'op':'events','after':cursor,'limit':1000,'full':True})['events']
        events.extend(e for e in batch if e['seq']<=data['revision'])
        if not batch or batch[-1]['seq']>=data['revision']:
            break
        cursor=batch[-1]['seq']
    for t in tasks.values():
        c=t['child_counts']
        body=f"# {t['id']} {esc(t['title'])}\n\n[项目总览](../index.md) | [完整事件](../events.md)\n\n只读；快照修订 {data['revision']}，任务修订 {t['revision']}，源更新时间 {t['updated_at']}。\n\n"
        for label,key in [('责任','owner'),('执行实例','executor'),('检验责任','checker'),('状态','state'),('目标','goal'),('下一步','next_action'),('原因','reason')]:
            body+=f"- {label}：{state_of(t) if key == 'state' else esc(t.get(key))}\n"
        if t.get('deprecation'):
            body+='- 变更编号：'+esc(t['deprecation']['change_no'])+'（[需求变更流水](../changes.md)）\n'
            body+='- 备注：'+esc(t['deprecation']['remark'])+'\n'
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
            body+=f"- [{child['id']} {esc(child['title'])}]({child['id']}.md)：{state_of(child)}；下一步：{esc(child['next_action'])}\n"
        body+='\n本任务时间线：\n\n'
        for e in events:
            if e['task_id']==t['id']:
                body+=f"- #{e['seq']} {e['recorded_at']}｜{esc(e['actor'])}｜{e['command']['op']}｜{esc(e['command'].get('reason',e['command'].get('summary','')))}\n"
        save('management/views/tasks/'+t['id']+'.md',body)
    event_text='# 任务事件时间线\n\n只读；发生/接收时间和完整变更见任务账本 events 查询。\n\n'
    for e in events:
        event_text+=f"- #{e['seq']} {e['recorded_at']}｜{esc(e['task_id'])}｜{esc(e['actor'])}｜{e['command']['op']}｜{esc(e['command'].get('reason',e['command'].get('summary','')))}\n"
    save('management/views/events.md',event_text)
    save('management/views/index.md',head)
    ledger = data['integrity']['change']
    change_text = '# 需求变更流水\n\n只读派生视图；编号在本项目内唯一，完整修订见[事件时间线](events.md)。\n\n'
    change_text += '| 变更编号 | 需求 | 类型 | 状态 | 登记时间 | 来源 | 关联任务 |\n|---|---|---|---|---|---|---|\n'
    for change in sorted(ledger.values(), key=lambda c: (c.get('sequence', 0), c['id'])):
        ids = set(change['affected_tasks']) | {d['task_id'] for d in change.get('dispositions', [])}
        refs = '；'.join(tlink(tasks[tid])+'（'+state_of(tasks[tid])+'）' for tid in sorted(ids) if tid in tasks)
        change_text += '| '+ ' | '.join([esc(change.get('change_no', change['id'])), esc(change.get('title', change['quote'])),
                      esc(change['type']), esc(change['state']), esc(change.get('created_at', '历史记录未登记')),
                      link(change['source']), refs or '待分析'])+' |\n'
    save('management/views/changes.md', change_text)
    written = ['index.md', 'events.md', 'changes.md']

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
    plan += '## 现在等人处理\n\n' + (choosing + ''.join(awaiting_line(t, a) for t, a in awaiting) or '- 无\n')
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
    save('management/views/plan.md',plan)
    written.append('plan.md')

    # Project front page: one row per sub-direction with outputs, progress and who is awaited.
    directions = {}
    for t in children(tasks, None):
        if t.get('kind') != 'stage':
            directions.setdefault(t.get('direction') or '未分类', []).append(t)
    proj = f"# 项目总入口\n\n只读派生视图，读取时间：{data['observed_at']}。每个子方向一行；成果与状态取自任务源，按维度的详细进度在各角色的专业源。\n\n{urgent}| 子方向 | 负责的人 | 进行中 | 最新完成与证据 | 在等谁 | 详细进度 |\n|---|---|---|---|---|---|\n"
    for name in sorted(directions):
        items = directions[name]
        owners = sorted(set(p for x in items for r in ('decide', 'execute') for p in x.get('people', {}).get(r, [])))
        active = [x for x in items if x['state'] in {'running', 'waiting_review', 'blocked'}]
        finished = sorted([x for x in items if done(x)], key=lambda x: x['updated_at'], reverse=True)
        latest = '；'.join(esc(x['title']) + (' ' + link(x['evidence'][0]) if x['evidence'] else '') for x in finished[:2]) or '—'
        waiting = sorted(set(a['person'] for x in items for a in x.get('awaiting', []) if x['state'] not in TERMINAL))
        sources = sorted(set(x['source'] for x in items if x.get('source')))
        proj += f"| {esc(name)} | {'、'.join(who(p) for p in owners) or '—'} | {'；'.join(tlink(x) + '（' + state_of(x) + '；执行：' + esc(x.get('executor') or '未登记') + '）' for x in active[:3]) or '—'} | {latest} | {'、'.join(who(p) for p in waiting) or '—'} | {'、'.join(link(s) for s in sources) or '—'} |\n"
    save('management/views/project.md',proj)
    written.append('project.md')

    # Group digest: stage progress, items blocking others first, recent decisions with the deciding person.
    dig = f"# 群摘要\n\n只读派生视图，读取时间：{data['observed_at']}。只在群里 @ 需要行动的人；本摘要供所有人了解进展。\n\n{urgent}"
    others = ''.join(notice_line(n) for n in notices if n['kind'] != 'Q0')
    dig += ('## 告知（F1 成果、Q1、Q2）\n\n' + others + '\n' if others else '') + '## 阶段进展\n\n'
    dig += ''.join(f"- {esc(s['title'])}：{state_of(s)}\n" for s in stages) or '- 尚未登记阶段\n'
    dig += '\n## 在等的人（阻塞他人的在前）\n\n' + (choosing + ''.join(awaiting_line(t, a) for t, a in awaiting) or '- 无\n')
    decided = sorted([t for t in tasks.values() if t.get('human_review')], key=lambda t: t['human_review'].get('at', ''), reverse=True)
    dig += '\n## 最近的人工决定\n\n' + (''.join(f"- {tlink(t)}：{esc(t['human_review']['outcome'])}；范围：{esc(t['human_review']['scope'])}" + (f"；决定人：{who(t['human_review']['person'])}" if t['human_review'].get('person') else '') + '\n' for t in decided[:10]) or '- 无\n')
    save('management/views/digest.md',dig)
    written.append('digest.md')

    # Personal and group views exist only when two or more people take part.
    def scoped_view(title, members, intro, prefix='../tasks/'):
        mine = [t for t in tasks.values() if t['state'] not in RETIRED and any(set(rels(m, t)) - {'inform'} for m in members)]
        ids = {t['id'] for t in mine}
        waiting = [(t, a) for t, a in awaiting if a['person'] in members]
        counts_by = {s: sum(t['state'] == s for t in mine) for s in ['done', 'running', 'waiting_review', 'blocked', 'planned']}
        text = f"# {title}\n\n{intro}\n\n与此相关 {len(mine)} 项：完成 {counts_by['done']}｜进行中 {counts_by['running']}｜待审 {counts_by['waiting_review']}｜受阻 {counts_by['blocked']}｜未开始 {counts_by['planned']}\n\n"
        mentioned = ''.join(notice_line(n) for n in notices if n['kind'] in {'Q0', 'F1_output', 'Q1'} and set(n['people']) & set(members))
        text += ('## 告知你\n\n' + mentioned + '\n' if mentioned else '') + '## 现在等你\n\n' + (''.join(awaiting_line(t, a, prefix) for t, a in waiting) or '- 无\n')
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
    for sub in ['people', 'groups', 'instances']:
        folder = local(root, 'management/views/' + sub)
        if folder.is_dir():
            for old in folder.glob('*.md'):
                local(root, 'management/views/' + sub + '/' + old.name).unlink()
    if team_mode(people):
        for pid, p in sorted(people['people'].items()):
            save(f'management/views/people/{pid}.md', scoped_view(esc(p['name']) + '的视图', [pid], '只读派生视图。只列与你有关系（决定、澄清、指定、执行或试用）的事项，以及与它们直接相连的上层任务；AI 内部子任务不在此列。'))
            written.append(f'people/{pid}.md')
        group_ids = sorted(set(g for p in people['people'].values() for g in p.get('groups', [])))
        for gid in group_ids:
            members = [pid for pid, p in people['people'].items() if gid in p.get('groups', [])]
            label = esc(people['groups'].get(gid, gid))
            save(f'management/views/groups/{gid}.md', scoped_view(label + '的视图', members, '只读派生视图。成员：' + '、'.join(who(m) for m in members) + '。列出与本组成员有关的事项与跨组依赖。'))
            written.append(f'groups/{gid}.md')
    for rel, text in pages.items():  # instance lists, ledger, human review points, delivery sets
        save('management/views/' + rel, text)
        written.append(rel)
    return {'view':str(root/'management/views/index.md'),'revision':data['revision'],'task_count':len(tasks),'views':written}


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project',required=True)
    mode=parser.add_mutually_exclusive_group()
    mode.add_argument('--command',help='JSON file; omit to read stdin')
    mode.add_argument('--render',action='store_true',help='render existing state only; run mutations separately')
    args=parser.parse_args()
    try:
        if args.render:
            require(sys.stdin.isatty() or not sys.stdin.read().strip(), 'render does not execute commands; execute the JSON command first, then render separately')
            command=None
        else:
            command=json.loads(Path(args.command).read_text() if args.command else sys.stdin.read())
        if isinstance(command,list):
            # Several commands in one call, in order; each returns its own result or error.
            results=[]
            for item in command:
                try:
                    results.append(execute(args.project,item))
                except (ValueError,OSError,KeyError,TypeError,sqlite3.Error) as exc:
                    results.append({'error':str(exc)})
            print(json.dumps({'results':results},ensure_ascii=False,indent=2))
            sys.exit(1 if any('error' in r for r in results) else 0)
        print(json.dumps(render(args.project) if args.render else execute(args.project,command),ensure_ascii=False,indent=2))
    except (ValueError,OSError,KeyError,TypeError,sqlite3.Error) as exc:
        print(json.dumps({'error':str(exc)},ensure_ascii=False))
        sys.exit(1)
