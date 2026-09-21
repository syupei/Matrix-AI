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
    return all(effective_done(tasks[d], tasks) for d in t['dependencies']) and all(x['state'] == 'cancelled' or effective_done(x,tasks) for x in children(tasks,t['id']))


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
    # A parent completes after children. Include those edges to detect indirect
    # deadlocks (child depends on its parent / an ancestor waits for itself).
    graph = {k: list(v['dependencies']) + [x['id'] for x in children(tasks, k)] for k, v in tasks.items()}
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
        require(op in {'init', 'create', 'update', 'transition', 'review', 'human_review', 'report', 'handoff'}, 'unknown operation')
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
        else:
            cfg, tasks = config(db), task_map(db)
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
                allowed = {'id','parent','title','owner','checker','goal','inputs','outputs','criteria','dependencies','resources','slots','executor','human_required','expanded','next_action','source'}
                require(set(data) <= allowed, 'unknown create fields')
                after = dict(data, parent=parent, manager=manager, state='planned', revision=1,
                             work_revision=1, evidence=[], review=None, human_review=None,
                             created_at=now(), updated_at=now(), last_report=None,
                             reason='registered before execution')
                for key, default in [('dependencies',[]),('resources',[]),('slots',1),('executor',None),('human_required',False),('expanded',False),('source','')]:
                    after.setdefault(key, default)
                tasks[tid] = after
                validation(after, tasks)
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
                    allowed = {'next_action','evidence','executor','expanded','source','reason','title','goal','inputs','outputs','criteria','dependencies','resources','slots','human_required','checker'}
                    require(set(changes) <= allowed, 'immutable/unknown field')
                    require(nonempty(cmd.get('reason')), 'change reason required')
                    if set(changes) & {'goal','inputs','outputs','criteria','dependencies','human_required','checker'}:
                        require(actor == after['manager'] or nonempty(cmd.get('scope_authorization')), 'scope/interface change needs manager authorization reference')
                    after.update(changes)
                    require(not before['human_required'] or after['human_required'] or nonempty(cmd.get('scope_authorization')), 'cannot silently remove human review')
                    if set(changes) - {'next_action','executor','source','reason'}:
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
                    require(actor == cfg['pm_actor'], 'unified frontdoor records human decisions')
                    require(cmd.get('outcome') in {'approved','changes_requested','deferred'}, 'invalid human decision')
                    require(all(nonempty(cmd.get(k)) for k in ['presented_ref','source','quote','scope']), 'actual presentation, reply source, exact quote and scope required')
                    after['human_review'] = {k:cmd[k] for k in ['outcome','presented_ref','source','quote','scope']}
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
    summary = data['top_level']
    head = f"# 项目任务总览\n\n只读派生视图。任务事实由 `management/runtime/tasks.sqlite3` 维护；专业内容仍在原源。\n\n项目：{esc(data['config']['project'])}。读取时间：{data['observed_at']}。事件修订：{data['revision']}。\n\n顶层完成 {summary['done']}/{summary['total']}，剩余 {summary['remaining']}；仅统计已登记范围，未登记远期不计入。\n\n"
    head += '| 编号 | 任务 | 责任方 | 状态 | 本层子项 | 下一步 | 详情 |\n|---|---|---|---|---|---|---|\n'
    for t in children(tasks,None):
        c=t['child_counts']
        state = '待复核（历史完成）' if t['needs_recheck'] else t['state']
        head += f"| {t['id']} | {esc(t['title'])} | {esc(t['owner'])} | {state} | {c['done']}/{c['total']}，剩余{c['remaining']} | {esc(t['next_action'])} | [展开](tasks/{t['id']}.md) |\n"
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
        body+=f"- 直接子项：完成 {c['done']}/{c['total']}，剩余 {c['remaining']}；{'本轮已展开' if t['expanded'] else '尚未声明完整展开'}。\n"
        for key,label in [('inputs','输入'),('outputs','关键交付物'),('criteria','完成条件'),('dependencies','依赖'),('evidence','成果证据')]:
            body+=f'\n{label}：\n\n'+''.join('- '+link(x)+'\n' for x in t[key])
        if t.get('last_report'):
            body+='\n最后上报：\n\n'+esc(canon(t['last_report']))+'\n'
        if t['needs_recheck']:
            body+='\n当前判定：历史完成依据已变化，待责任方复核；暂不计入当前完成数。\n'
        if t.get('review'):
            body+='\n专业检验：'+esc(t['review']['outcome'])+'；'+('当前有效' if t['review_current'] else '需复核')+'。\n\n'
            body+=''.join('- '+link(x)+'\n' for x in t['review']['evidence'])
        if t.get('human_review'):
            h=t['human_review']
            body+='\n人工决定：'+esc(h['outcome'])+'；范围：'+esc(h['scope'])+'。\n\n'
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
    return {'view':str(root/'management/views/index.md'),'revision':data['revision'],'task_count':len(tasks)}


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
