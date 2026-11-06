"""Read-only lists and views from the task database: task lists by asker, the instance ledger,
human review points and delivery sets. Computed at read time; nothing here is stored or edited by hand.
"""
import html
import json
import re
from datetime import datetime
from types import SimpleNamespace

READ_OPS = {'tasks_for'}
CLOSED = {'done': '已完成', 'cancelled': '已取消', 'deprecated': '已弃用'}
ORDER = ['受阻', '等人审', '人工待办', '等检验', '返工中', '进行中', '未开始', '已完成', '已取消', '已弃用']
CAUSES = {'execution': '执行问题', 'requirement_clarification': '需求澄清', 'basis_changed': '依据变化', 'other': '其他'}
BORNE = {'requirement_clarification', 'basis_changed'}  # counted for the party that caused them, not the producer
CHECKS = {'independent': '独立检验', 'not_independent': '非独立检验', 'same_instance': '同一实例检验'}
FIT = {'fit': '适用', 'unregistered': '未登记', 'unfit_insisted': '模型不适用（坚持）'}
EXITS = {'production': '制作', 'qa': '检验', 'human': '人审', 'adoption': '采用'}
GAPS = {'delivery_unmapped': '未绑定', 'delivery_not_current': '未完成', 'independent_check_missing': '缺独立检验',
        'human_gate_missing': '缺人审', 'adoption_evidence_missing': '缺采用记录'}
REASSIGN = {'failed_check': '检验没过', 'executor_unable': '实例说做不了', 'other': '其他'}


def esc(s):
    return html.escape(str(s)).replace('|', '\\|').replace('\n', ' ')


def md(columns, rows):
    """A Markdown table of already escaped cells."""
    return '| ' + ' | '.join(columns) + ' |\n|' + '---|' * len(columns) + '\n' + ''.join('| ' + ' | '.join(r) + ' |\n' for r in rows)


def stamp(value):
    try:
        return datetime.fromisoformat(value).astimezone().strftime('%m-%d %H:%M')
    except (TypeError, ValueError):
        return str(value or '—')


def when(value):
    try:
        return datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    except ValueError:
        return None


def context(pm, root, db):
    data, people = pm.snapshot(db), pm.roster(root)
    return SimpleNamespace(pm=pm, root=root, db=db, data=data, cfg=data['config'], tasks={t['id']: t for t in data['tasks']},
                           records=data['integrity'], instances=data['integrity']['instance'], regs=pm.team.registries(pm, root), gaps=data['gaps'],
                           people=(people or {}).get('people', {}), names={pid: p['name'] for pid, p in (people or {}).get('people', {}).items()}, blocked={})


def name(c, iid):
    return c.pm.team.display(c.regs, iid)


def kids(c, t):
    return [x for x in c.tasks.values() if x['parent'] == t['id'] and x['state'] not in c.pm.RETIRED]


def done(c, tid):
    return c.pm.effective_done(c.tasks[tid], c.tasks)


def handed(t):
    """Handed over and waiting for its check; a task sent back after a failed check is not."""
    return t['state'] == 'waiting_review' and not t.get('sent_back')


def exit_label(c, e):
    return c.regs.get(e[11:], {}).get('name', e[11:]) if e.startswith('production:') else EXITS.get(e, e)


def deciders(c, t):
    ids = t.get('people', {}).get('decide') or [a['person'] for a in t.get('awaiting', []) if a['action'] == 'decide']
    ids = ids or [pid for pid, p in c.people.items() if 'project' in p.get('decides', [])]
    return '、'.join(c.names.get(p, p) for p in ids) or '人'


def waits(c, t):
    """What t waits on to finish: open children and unfinished completion prerequisites."""
    return sorted((k for k in kids(c, t) + [c.tasks[d] for d in t.get('completion_requires', []) if not done(c, d)] if k['state'] not in CLOSED), key=lambda k: k['id'])


def unresolved(c, t):
    """The expertise gap t waits on: no choice yet, or the expert's or person's result not in."""
    g = c.gaps.get(t.get('gap'))
    return g if g and g['status'] in {'open', 'expert', 'human'} and t['state'] not in CLOSED else None


def blocked(c, t):
    if t['id'] not in c.blocked:
        c.blocked[t['id']] = t['state'] == 'blocked' or bool(unresolved(c, t)) or any(blocked(c, k) for k in waits(c, t))
    return c.blocked[t['id']]


def blocker(c, t):
    """The nearest task t waits on that is itself blocked; its own status leads on to the root cause."""
    ref = (t.get('blocked_by') or {}).get('task_id')
    if t['state'] == 'blocked' and ref in c.tasks and c.tasks[ref]['state'] not in CLOSED:
        return c.tasks[ref]
    return next((k for k in waits(c, t) if blocked(c, k)), None)


def status(c, t):
    """The status column. A linked expertise gap still waiting replaces it; after the person chose self, it is appended."""
    g = c.gaps.get(t.get('gap'))
    if unresolved(c, t):
        if g['status'] == 'open':
            return '受阻：缺 ' + g['domain'] + ' 专家，等人选择'
        return '受阻：等 ' + g['decision']['expert'] + ' 的结论' if g['status'] == 'expert' else '人工待办：' + g['qualification']
    return progress(c, t) + ('｜缺 ' + g['domain'] + ' 专家，人已知风险，由当前实例完成' if g and g['status'] == 'self' else '')


def progress(c, t):
    if t['state'] in CLOSED:
        return CLOSED[t['state']] + ('（待复核）' if t['needs_recheck'] else '')
    hit = blocker(c, t)
    if hit:
        return '受阻：等 ' + name(c, hit['owner']) + ' 的 ' + hit['id']
    if t['state'] == 'blocked':
        return '受阻：' + (t.get('reason') or '未写原因')
    back, again = t.get('sent_back'), t.get('rework') or {}
    if back or (again and t['state'] in {'planned', 'running'}):
        return '返工中（第 ' + str(1 + again.get('count', 0) + bool(back)) + ' 版）：' + CAUSES[back['cause'] if back else again['reason']]
    if t['state'] == 'waiting_review':
        b = c.pm.basis(t, c.tasks)
        checked = bool(t.get('review') and t['review']['basis'] == b and t['review']['outcome'] == 'passed')
        approved = bool(t.get('human_review') and t['human_review']['basis'] == b and t['human_review']['outcome'] == 'approved')
        if t['human_required'] and checked and not approved:
            return '等人审：' + deciders(c, t)
        return '等检验：' + name(c, t['manager'] if checked else t['checker'])
    if t['state'] == 'running':
        k = kids(c, t)
        return '进行中' + ('（下游 ' + str(sum(handed(x) or x['state'] == 'done' for x in k)) + '/' + str(len(k)) + ' 已交出）' if k else '')
    unmet = [c.tasks[d] for d in t['dependencies'] if not done(c, d)]
    return '未开始：' + ('等 ' + '、'.join(name(c, d['owner']) + ' 的 ' + d['id'] for d in unmet) if unmet else '就绪')


def next_step(c, t, s, pm_list):
    """Computed actions for the asker; the recorded next_action otherwise."""
    # An instance checks and integrates what its children hand over; the PM, what its own tasks hand over to it.
    steps = [] if pm_list else ['检验并整合 ' + name(c, k['owner']) + ' 的 ' + k['id'] for k in sorted(kids(c, t), key=lambda k: k['id']) if handed(k)]
    if pm_list and s.split('｜')[0] == '等检验：' + name(c, c.cfg['pm_actor']):
        steps.append('检验并整合 ' + name(c, t['owner']) + ' 的 ' + t['id'])
    if pm_list and t['state'] == 'planned' and t['dependencies'] and all(done(c, d) for d in t['dependencies']) and not unresolved(c, t):
        steps.append('派出给 ' + name(c, t['owner']))
    for scope in c.records['scope'].values() if pm_list and t['state'] not in CLOSED else []:
        if scope['root_task'] == t['id']:
            open_ = {i.get('member_id') for i in c.pm.integrity.scope_issues(c.pm, c.root, scope, c.tasks)}
            steps += ['关闭 ' + '、'.join(m for m in scope['members'] if m not in open_)] if set(scope['members']) - open_ else []
    return '；'.join(steps) or t['next_action']


def after_done(c, t, pm_list):
    """Who gets it, what it releases, which delivery exit it records and whom to notify."""
    parts = [] if pm_list else ['交 ' + name(c, t['manager'])]
    waiting = sorted(x['id'] for x in c.tasks.values() if x['state'] not in CLOSED and t['id'] in x['dependencies'] + x.get('completion_requires', []))
    parts += ['解除 ' + '、'.join(waiting)] if waiting else []
    for s in sorted(c.records['scope'].values(), key=lambda s: s['id']):
        parts += ['记 ' + m + ' 的 ' + exit_label(c, e) + ' 出口' for m, row in sorted(s['bindings'].items()) for e, b in sorted(row.items()) if b['task_id'] == t['id']]
    parts += ['通知 ' + name(c, t['origin']['from'])] if t.get('origin') else []
    return '；'.join(parts) or '—'


def task_list(c, asker, include_closed=False, link=None):
    """The PM's list holds tasks it dispatched; an instance's list holds tasks it received, never those it dispatched."""
    pm_list = asker == c.cfg['pm_actor']
    mine = sorted((t for t in c.tasks.values() if (t['manager'] == asker if pm_list else asker in {t['owner'], t.get('executor')})), key=lambda t: t['id'])
    counts, rows = {}, []
    for t in mine:
        s = status(c, t)
        kind = re.split('[：（｜]', s)[0]
        counts[kind] = counts.get(kind, 0) + 1
        if include_closed or t['state'] not in CLOSED or t['needs_recheck']:
            rows.append((0 if kind == '受阻' else 1 if kind in {'等人审', '人工待办'} else 2, t, s))
    rows.sort(key=lambda r: (r[0], r[1]['id']))
    columns = ['编号', '任务', '受领者' if pm_list else '上游', '难度 / 风险', '状态', '下一步', '完成后', '更新']
    cells = [[t['id'], t['title'] + ('（来自 ' + name(c, t['origin']['from']) + ' 的请求）' if t.get('origin') else ''),
              name(c, t['owner']) + ('（master）' if c.instances.get(t['owner'], {}).get('master') else '') if pm_list
              else name(c, t['manager']) + ' 派发' if t['manager'] == c.cfg['pm_actor'] else str(t['parent']) + ' · ' + name(c, t['manager']),
              (t.get('difficulty') or '—') + ' / ' + (t.get('risk') or '—'), s, next_step(c, t, s, pm_list), after_done(c, t, pm_list), stamp(t['updated_at'])]
             for _, t, s in rows]
    inst = c.instances.get(asker, {})
    head = (c.cfg['project'] + '：PM（' + name(c, asker) + '）派发的任务 ' if pm_list else
            name(c, asker) + ('（' + inst['level'] + '，' + ('master' if inst.get('master') else '执行者') + '）' if inst.get('level') else ' ') + '受领的任务 ')
    head += str(len(mine)) + ' 项' + ('：' + '、'.join(k + ' ' + str(counts[k]) for k in ORDER if counts.get(k)) if counts else '')
    body = md(columns, [[link(r[0]) if link else esc(r[0])] + [esc(x) for x in r[1:]] for r in cells]) if cells else '（没有要列出的任务）\n'
    return dict(asker=asker, header=head, columns=columns, rows=cells, counts=counts, text=esc(head) + '\n\n' + body,
                revision=c.data['revision'], observed_at=c.data['observed_at'])


def execute(pm, root, db, cmd):
    asker, closed = cmd.get('as'), cmd.get('include_closed', False)
    pm.require(pm.nonempty(asker) and type(closed) is bool, 'as (the PM actor or an instance id) and boolean include_closed required')
    return task_list(context(pm, root, db), asker, closed)


def totals(usages):
    out = {}
    for u in usages:
        if 'cost' in u:
            out[u.get('currency', '')] = out.get(u.get('currency', ''), 0) + u['cost']
    return out


def money(usages, divisor=1):
    return '；'.join((str(round(v / divisor, 4)) + ' ' + k).strip() for k, v in sorted(totals(usages).items()))


def rate(part, whole):
    return str(round(100 * part / whole)) + '%（' + str(part) + '/' + str(whole) + '）' if whole else '—'


def ledger(c):
    """Per task, per configuration change and per instance, from events only."""
    events = [{k: json.loads(r[k]) if k in {'command', 'before_data', 'after_data', 'result'} and r[k] else r[k] for k in r.keys()}
              for r in c.db.execute('SELECT * FROM events ORDER BY seq')]
    who = lambda d: d and (d.get('executor') or d.get('owner'))
    tasks, insts, changes, last, open_, starts = {}, {}, [], {}, {}, {}
    def inst(iid):
        return insts.setdefault(iid, dict(held=set(), first={}, against=set(), caused=0, moved=0, overturned=set(), accepted=set(),
                                          usage=[], attempts=0, unpriced=False, times={}))
    for e in events:
        cmd, before, after, tid = e['command'], e['before_data'], e['after_data'], e['task_id']
        op = cmd.get('op')
        if op in {'confirm_config', 'derive', 'relevel_instance', 'retire_instance'}:
            changes.append((e, op, e['result']['record']))
            continue
        if tid not in c.tasks:
            continue
        row = tasks.setdefault(tid, dict(starts=0, reviews=[], reworks=[], overturned=0, moves=[], usage=[]))
        if op == 'overturned':
            row['overturned'] += 1
            inst(last.get(tid))['overturned'].add(tid)
            continue
        if not after:
            continue
        p0, p1 = who(before), who(after)
        last[tid] = p1
        for p in {p0, p1} - {None}:
            inst(p)['held'].add(tid)
        if cmd.get('usage'):
            row['usage'].append(cmd['usage'])
            inst(p0 or p1)['usage'].append(cmd['usage'])
            if 'cost' in cmd['usage'] and tid in open_:
                open_[tid][1] = True
        if after['state'] == 'running' and (before or {}).get('state') != 'running':
            row['starts'] += 1
            open_[tid] = [p1, False]
            starts.setdefault((tid, p1), e['occurred_at'])
        if (before or {}).get('state') == 'running' and after['state'] != 'running':  # a stop, a reassignment included
            p, priced = open_.pop(tid, [p0, False])
            inst(p)['attempts'] += 1
            inst(p)['unpriced'] |= not priced
        if op == 'review':
            rv = after['review']
            row['reviews'].append(rv)
            if not (rv['outcome'] == 'failed' and rv.get('cause') in BORNE):  # a clarification does not use up the first pass
                inst(p1)['first'].setdefault(tid, rv)
        if (after.get('rework') or {}).get('count', 0) > ((before or {}).get('rework') or {}).get('count', 0):
            rw = after['rework']
            row['reworks'].append(rw)
            if rw['reason'] in BORNE:
                inst(rw['attributed_to'])['caused'] += 1
            else:
                inst(rw['attributed_to'])['against'].add(tid)
        if op == 'reassign':
            row['moves'].append((p0, p1, cmd['reason_kind'], cmd['note']))
            inst(p0)['moved'] += 1
        if op == 'transition' and after['state'] == 'done' and (before or {}).get('state') != 'done':
            inst(p1)['accepted'].add(tid)
            start, end = when(starts.get((tid, p1))), when(e['occurred_at'])
            if start and end:
                inst(p1)['times'].setdefault(after.get('difficulty') or '—', []).append((end - start).total_seconds())
    text = (f"# 实例台账\n\n只读派生视图，由任务库的事件生成；读取时间：{c.data['observed_at']}，事件修订：{c.data['revision']}。"
            "需求澄清与依据变化引起的返工不计入制作方的一次通过率，记到给出需求或改了依据的一方。费用拿不到时写\"未接入\"，只记用时和次数。\n\n## 配置与实例变更\n\n")
    rows = []
    for e, op, r in changes:
        if op == 'confirm_config':
            odd = '、'.join(x['id'] + ' ' + ('模型不适用（坚持）' if x['insisted'] else '未登记') for x in r['entries'] if x['fit'] != 'fit')
            what = '确认配置', c.names.get(r['person'], r['person']) + '：「' + r['quote'] + '」；' + str(len(r['entries'])) + ' 项' + ('；' + odd if odd else '')
        elif op == 'derive':
            what = '派生', name(c, r['id']) + '（' + r['level'] + '，' + ('master' if r['master'] else '执行者') + '，配置项 ' + r['config_entry'] + '，' + FIT[r['fit']] + '）'
        elif op == 'relevel_instance':
            what = '调级', name(c, r['id']) + ' ' + r['previous_level'] + ' → ' + r['level'] + '：' + r['reason']
        else:
            what = '停用', name(c, r['id']) + '：' + r['reason']
        rows.append([stamp(e['recorded_at']), what[0], what[1], e['actor']])
    text += (md(['时间', '事项', '内容', '由谁'], [[esc(x) for x in r] for r in rows]) if rows else '- 无\n') + '\n## 任务\n\n'
    rows = []
    for tid, row in sorted(tasks.items()):
        p = who(c.tasks[tid])
        i = c.instances.get(p, {})
        checks = '；'.join(('通过' if rv['outcome'] == 'passed' else '未通过（' + CAUSES.get(rv.get('cause'), '未写原因') + '）') + '·' + name(c, rv['checker'])
                          + '·' + CHECKS.get(rv.get('independence'), '未核对') for rv in row['reviews']) or '—'
        reworks = str(len(row['reworks'])) + ('（' + '、'.join(CAUSES[r['reason']] + '→' + name(c, r['attributed_to']) for r in row['reworks']) + '）' if row['reworks'] else '')
        moves = '；'.join(name(c, a) + ' → ' + name(c, b) + '（' + REASSIGN[k] + '：' + n + '）' for a, b, k, n in row['moves']) or '—'
        spent = '；'.join(x for x in [money(row['usage']), (str(sum(u.get('tokens', 0) for u in row['usage'])) + ' tokens') if any('tokens' in u for u in row['usage']) else '',
                                     (str(sum(u.get('seconds', 0) for u in row['usage'])) + ' 秒') if any('seconds' in u for u in row['usage']) else ''] if x) or '未接入'
        rows.append([tid, name(c, p), i.get('model', '—'), i.get('level', '—'), FIT.get(i.get('fit'), '—'), str(row['starts']), checks, reworks, str(row['overturned']), moves, spent])
    text += (md(['任务', '实例', '模型', '职级', '适用性', '尝试', '检验（结果·检验者·独立性）', '返工', '被推翻', '改派', '用量与费用'], [[esc(x) for x in r] for r in rows]) if rows else '- 无\n') + '\n## 实例\n\n'
    rows = []
    for iid, s in sorted((k, v) for k, v in insts.items() if k in c.instances):
        i = c.instances[iid]
        counted = set(s['first'])
        first = {t for t in counted if s['first'][t]['outcome'] == 'passed' and t not in s['against']}
        times = '；'.join(d + ' ' + str(round(sum(v) / len(v) / 60, 1)) + ' 分钟（' + str(len(v)) + ' 项）' for d, v in sorted(s['times'].items())) or '—'
        accepted = {t for t in s['accepted'] if c.tasks[t]['state'] == 'done'}
        # Effective cost: everything spent, rework and reassignment included, per accepted result.
        if s['unpriced'] or not s['attempts'] or not totals(s['usage']):
            cost = '未接入'
        else:
            cost = money(s['usage'], len(accepted)) if accepted else '—（没有通过检验并被采用的成果）'
        held = len(s['held'])
        rows.append([name(c, iid), i.get('model', '—'), i.get('level', '—'), FIT.get(i.get('fit'), '—'), str(held), rate(len(first), len(counted)),
                     rate(len(s['against'] & s['held']), held), rate(len(s['overturned'] & s['held']), held), rate(s['moved'], held),
                     times, cost, str(s['caused'])])
    text += md(['实例', '模型', '职级', '适用性', '承担', '一次通过率', '返工率', '被推翻率', '被改派率', '各级任务的平均用时', '有效成本', '引起他人返工'],
               [[esc(x) for x in r] for r in rows]) if rows else '- 无\n'
    return text


def reserved(c):
    """Decisions reserved for people: the list in section 3 of the levels file."""
    path = c.pm.local(c.root, 'matrix/base/LEVELS.md')
    path = path if path.is_file() else c.pm.team.KIT / 'matrix/base/LEVELS.md'
    items, inside = [], False
    for line in path.read_text(encoding='utf-8').splitlines():
        if line.startswith('## '):
            inside = line.startswith('## 3.')
        elif inside and line.startswith('- '):
            items.append(line[2:].rstrip('；;。'))
    return items


def human_points(c):
    conf = c.records['instance_config'].get('confirmed') or {}
    used = {e['profession'] for e in conf.get('entries', [])} | {c.instances.get(t['owner'], {}).get('profession') or t.get('role') for t in c.tasks.values()}
    project = [p['name'] for p in c.people.values() if 'project' in p.get('decides', [])]
    rows = []
    for pid in sorted(p for p in used if p in c.regs):
        reg = c.regs[pid]
        for flow in reg.get('stage_flows', []):
            who = '、'.join(dict.fromkeys([p['name'] for p in c.people.values() if flow['key'] in p.get('decides', [])] + project)) or '人'
            rows += [[reg['name'] + ' ' + stage + ' 审阅', '专业登记（' + flow['key'] + '）', who, '—'] for stage in flow.get('review', [])]
    for t in sorted(c.tasks.values(), key=lambda t: t['id']):
        if t['state'] in c.pm.RETIRED:
            continue
        if t.get('risk') == 'F0':
            rows.append([t['id'] + ' ' + t['title'] + '（F0，由人判定后生效）', '任务风险 F0', deciders(c, t), status(c, t)])
        if t['human_required']:
            rows.append([t['id'] + ' ' + t['title'], '任务人审', deciders(c, t), status(c, t)])
    gaps = sorted(c.gaps.values(), key=lambda g: g['id'])
    rows += [[g['id'] + ' 缺 ' + g['domain'] + ' 专家（需要：' + g['qualification'] + '）：' + g['why'] + '；选择：指定专家、由当前实例完成或列为人工待办',
              '专业缺口（' + c.pm.GAP_KINDS[g['kind']] + '，' + g['risk'] + '）', gap_deciders(c, g), '等人选择'] for g in gaps if g['status'] == 'open']
    rows += [[item, '保留给人的决定（C21 §3）', '、'.join(project) or '人', '常设'] for item in reserved(c)]
    text = ('# 人审点汇总\n\n只读派生视图：已确认配置与已登记任务涉及的专业的人审点（读登记）、F0 事项、要人审的任务，以及保留给人的决定。\n\n'
            + md(['事项', '来源', '由谁决定', '状态'], [[esc(x) for x in r] for r in rows]))
    if gaps:
        rows = [[g['id'], g['domain'], c.pm.GAP_KINDS[g['kind']], g['risk'], g['qualification'], gap_state(c, g), gap_decision(c, g),
                 '、'.join(t + '（' + status(c, c.tasks[t]) + '）' for t in g['task_ids']) or '—'] for g in gaps]
        text += '\n## 专业缺口\n\n' + md(['缺口', '领域', '类型', '风险', '资质', '状态', '决定人与原话', '关联任务'], [[esc(x) for x in r] for r in rows])
    return text


def gap_state(c, g):
    d, label = g['decision'] or {}, c.pm.GAP_STATES[g['status']]
    if g['status'] == 'expert':
        return label + '：' + d['expert'] + '，等结论'
    if g['status'] == 'self':
        return label + '，人已知风险'
    if g['status'] == 'closed':
        return label + '（' + c.pm.GAP_STATES[d['choice']] + ('：' + d['expert'] if d.get('expert') else '') + '）；成果：' + g['result']['source']
    return label


def gap_decision(c, g):
    d = g['decision']
    if not d:
        return '—'
    quote = d['quote'] if len(d['quote']) <= 40 else d['quote'][:40] + '…'
    return (c.names.get(d['person'], d['person']) + '：「' + quote + '」；' + ('常设选择' if d['standing'] else '只这一次')
            + ('，沿用 ' + d['standing_from'] if d.get('standing_from') else ''))


def gap_deciders(c, g):
    """People who may make the choice for a gap: deciders of every linked task, else of the project."""
    if not c.people:
        return '人'
    allowed = None
    for tid in g['task_ids'] or [None]:
        ranks = set(c.pm.deciders(tid, c.tasks, {'people': c.people}))
        allowed = ranks if allowed is None else allowed & ranks
    return '、'.join(c.names.get(p, p) for p in sorted(allowed)) or '人'


def provenance(c, s, m, e):
    declared = s.get('exit_sources', {}).get(e)
    if declared:
        d = next((x for x in declared['declared_by'] if x['item'] == m), declared['declared_by'][0])
        return '来自 ' + d['item'] + (' ' + str(d['version']) if d.get('version') else '') + ' 的出口声明'
    added = s.get('member_exits', {}).get(m, {}).get(e)
    return '由 ' + name(c, added['added_by']) + ' 追加：' + added['reason'] if added else '登记范围时要求'


def scopes(c):
    text = '# 交付集合\n\n只读派生视图。每个出口写明来源：需求条目声明的出口（条目与版本）、master 追加的出口（理由），或登记范围时要求的出口。\n'
    for s in sorted(c.records['scope'].values(), key=lambda s: s['id']):
        gaps = {(i.get('member_id'), i.get('exit')): i['code'] for i in c.pm.integrity.scope_issues(c.pm, c.root, s, c.tasks)}
        rows = [[m, exit_label(c, e), provenance(c, s, m, e), (s['bindings'].get(m, {}).get(e) or {}).get('task_id', '—'), GAPS.get(gaps.get((m, e)), '完成')]
                for m in s['members'] for e in c.pm.integrity.required(s, m)]
        text += ('\n## ' + esc(s['id']) + '：' + esc(s['root_task']) + ' ' + esc(c.tasks.get(s['root_task'], {}).get('title', '')) + '\n\n成员来源：'
                 + esc(s['source']['path']) + ('' if s['known_complete'] else '；范围未完整') + '\n\n'
                 + (md(['成员', '出口', '来源', '任务', '状态'], [[esc(x) for x in r] for r in rows]) if rows else '- 无成员\n'))
    return text


def pages(pm, root, db):
    """Views rendered with the others: the PM list for the index, one list per active instance, ledger, human points, delivery sets."""
    c = context(pm, root, db)
    out = {'index-list': task_list(c, c.cfg['pm_actor'], link=lambda tid: '[' + esc(tid) + '](tasks/' + tid + '.md)')['text']}
    for iid, i in sorted(c.instances.items()):
        if i.get('active', True) and re.fullmatch(pm.SAFE_ID, iid):
            out['instances/' + iid + '.md'] = ('# ' + esc(name(c, iid)) + ' 的任务\n\n只读派生视图；只列它受领的任务，派给下游的不列。\n\n'
                                              + task_list(c, iid, link=lambda tid: '[' + esc(tid) + '](../tasks/' + tid + '.md)')['text'])
    out.update({'ledger.md': ledger(c), 'human-points.md': human_points(c), 'scopes.md': scopes(c)})
    return out
