"""Project facts, resource eligibility, and closure checks; task and evidence records remain authoritative."""
import html
import json

READ_OPS = {'project', 'closure_check'}
WRITE_OPS = {'project_config'}
RESOURCE_KINDS = {'person', 'device', 'supplier', 'budget', 'procurement'}


def resource_issues(t, cfg):
    catalog = cfg.get('project_meta', {}).get('resources')
    if catalog is None:
        return []  # Existing string resources retain their exclusive-lock meaning.
    return ['resource pending: ' + rid if rid not in catalog or catalog[rid]['status'] == 'pending'
            else 'resource unavailable: ' + rid for rid in t['resources']
            if rid not in catalog or catalog[rid]['status'] != 'available']


def exclusive(t, cfg):
    catalog = cfg.get('project_meta', {}).get('resources', {})
    return {r for r in t['resources'] if catalog.get(r, {}).get('exclusive', True)}


def reservations(pm, tasks, cfg, gates, held):
    """Greedy deterministic reservation among eligible planned tasks; never reserves for a blocked task."""
    reserved, blocked = {}, {}
    for t in sorted(tasks.values(), key=lambda t: (t.get('order', 10**6), t['created_at'], t['id'])):
        if t['state'] != 'planned' or t.get('awaiting') or gates.get(t['id']) or held.get(t['id']) or pm.reasons(t, tasks, cfg):
            continue
        need = exclusive(t, cfg)
        owners = sorted({reserved[r] for r in need if r in reserved})
        if owners:
            blocked[t['id']] = ['resource queued behind: ' + ','.join(owners)]
        else:
            reserved.update({r: t['id'] for r in need})
    return blocked


def validate(pm, value):
    pm.require(isinstance(value, dict) and set(value) <= {'revision', 'project_type', 'goals', 'resources', 'closure', 'source', 'recorded_by'}, 'unknown project fields')
    if 'project_type' in value:
        pm.require(pm.nonempty(value['project_type']), 'project_type required')
    goals = value.get('goals', [])
    pm.require(isinstance(goals, list), 'goals must be a list')
    ids = set()
    for g in goals:
        pm.require(isinstance(g, dict) and set(g) <= {'id', 'target', 'owner', 'state', 'evidence', 'measurement'}, 'unknown goal fields')
        pm.require(all(pm.nonempty(g.get(k)) for k in ['id','target','owner']), 'goal ID, target and evidence owner required')
        pm.require(g['id'] not in ids, 'duplicate goal ID'); ids.add(g['id'])
        pm.require(g.get('state') in {'pending','met','not_met'} and pm.strings(g.get('evidence')), 'goal state/evidence required')
        pm.require(g['state'] == 'pending' or (g['evidence'] and pm.nonempty(g.get('measurement'))), 'measured outcome needs evidence and observation')
    if 'resources' in value:
        pm.require(isinstance(value['resources'], dict), 'resources must map IDs to facts')
        for rid, r in value['resources'].items():
            pm.require(pm.nonempty(rid) and isinstance(r, dict) and set(r) <= {'kind','exclusive','status','owner','evidence','note'}, 'unknown resource fields')
            pm.require(r.get('kind') in RESOURCE_KINDS and type(r.get('exclusive')) is bool, 'resource kind and exclusive boolean required')
            pm.require(r.get('status') in {'available','pending','unavailable'} and pm.strings(r.get('evidence')), 'resource status and evidence list required')
            pm.require(r['status'] != 'available' or bool(r['evidence']), 'availability needs recorded facts; unknown stays pending')
    if 'closure' in value:
        c = value['closure']
        pm.require(isinstance(c, dict) and set(c) <= {'accepted', 'handoffs', 'pending', 'lessons'}, 'unknown closure fields')
        pm.require(pm.strings(c.get('accepted')), 'accepted task IDs required')
        for key in ['handoffs','pending','lessons']:
            pm.require(isinstance(c.get(key, []), list), key + ' must be a list')
        for entry in c.get('handoffs', []) + c.get('pending', []):
            pm.require(isinstance(entry, dict) and set(entry) <= {'task_id','receiver','next_action','evidence'}, 'handoff fields: task_id,receiver,next_action,evidence')
            pm.require(all(pm.nonempty(entry.get(k)) for k in ['task_id','receiver','next_action']) and pm.strings(entry.get('evidence')) and entry['evidence'], 'handoff needs recipient, next action and evidence')
        for lesson in c.get('lessons', []):
            pm.require(isinstance(lesson, dict) and set(lesson) == {'observation','conditions','evidence'} and pm.nonempty(lesson['observation'])
                       and pm.nonempty(lesson['conditions']) and pm.strings(lesson['evidence']) and lesson['evidence'], 'lesson needs observed facts, conditions and evidence')


def closure_check(pm, cfg, tasks):
    meta = cfg.get('project_meta', {})
    c = meta.get('closure', {})
    issues = []
    accepted = set(c.get('accepted', []))
    work = {k:t for k,t in tasks.items() if t['parent'] is None and t.get('kind') != 'stage' and t['state'] not in pm.RETIRED}
    finished = {k for k,t in work.items() if pm.effective_done(t, tasks)}
    if not work: issues.append('no registered delivery scope')
    if accepted != finished: issues.append('accepted scope must match current verified completed top-level work')
    if not accepted: issues.append('accepted scope missing')
    for key, expected in [('handoffs', accepted), ('pending', set(work) - finished)]:
        rows = c.get(key, [])
        ids = [r['task_id'] for r in rows]
        if len(ids) != len(set(ids)) or set(ids) != expected:
            issues.append(key + ' must cover exactly the applicable registered tasks')
    if not meta.get('goals'): issues.append('business goals and evidence status not recorded')
    if not meta.get('project_type'): issues.append('project type not recorded')
    return dict(ready=not issues, scope='registered_tasks_only', issues=issues, accepted=sorted(accepted), unfinished=sorted(set(work)-finished),
                business_pending=[g['id'] for g in meta.get('goals', []) if g['state']=='pending'],
                note='仅核对已登记任务；关闭前仍需对照项目简报与未结事项来源补齐遗漏及接手责任。收尾不等于业务目标已达成，也不自动开始持续运营')


def view(pm, cfg, tasks):
    meta = cfg.get('project_meta', {})
    work = [t for t in tasks.values() if t['parent'] is None and t.get('kind') != 'stage']
    return dict(revision=meta.get('revision',0), project_type=meta.get('project_type'),
        route_gap=bool(meta.get('project_type') and meta['project_type'] != 'product_development'),
        route_note='本包仅提供产品研发路线；其他类型登记所需专业与路线缺口，不套用产品基线流程',
        task_progress=pm.counts(work,tasks),
        delivery_acceptance={t['id']:dict(state=t['state'], current=pm.effective_done(t,tasks), evidence=t['evidence']) for t in work if t['state'] not in pm.RETIRED},
        business_results=meta.get('goals', []), resources=meta.get('resources', {}),
        resource_recording_gaps=sorted({rid for t in work for rid in t['resources']} - set(meta.get('resources', {}))),
        closure=closure_check(pm,cfg,tasks))


def execute(pm, root, db, cmd):
    cfg, tasks = pm.config(db), pm.task_map(db)
    pm.current_gates(root, db, tasks)
    if cmd['op'] == 'closure_check': return closure_check(pm,cfg,tasks)
    if cmd['op'] == 'project': return view(pm,cfg,tasks)
    pm.require(cmd['actor'] == cfg['pm_actor'], 'PM records project facts')
    old = cfg.get('project_meta', {})
    pm.require(cmd.get('expected_revision') == old.get('revision',0), 'stale project revision')
    pm.require(pm.nonempty(cmd.get('source')), 'actual source of project facts required')
    changes = cmd.get('changes')
    pm.require(isinstance(changes, dict) and changes and set(changes) <= {'project_type','goals','resources','closure'}, 'unknown project changes')
    pm.require(not any(t.get('closure') and t['state']=='done' for t in tasks.values()), 'reopen closure milestone before changing project facts')
    value = dict(old, **changes, revision=old.get('revision',0)+1, source=cmd['source'], recorded_by=cmd['actor'])
    validate(pm,value)
    cfg['project_meta'] = value
    db.execute("UPDATE meta SET value=? WHERE key='config'",(pm.canon(cfg),))
    return view(pm,cfg,tasks)


def markdown(pm,cfg,tasks):
    data = view(pm,cfg,tasks)
    esc = lambda s: html.escape(str(s)).replace('\n',' ')
    p = data['task_progress']
    text = '\n## 项目结果\n\n项目类型：' + esc(data['project_type'] or '未登记') + '\n'
    if data['route_gap']: text += data['route_note'] + '\n'
    text += f"\n任务进度：顶层工作完成 {p['done']}/{p['total']}；不把完成比例当业务结果。\n\n交付验收：\n"
    for tid,a in data['delivery_acceptance'].items(): text += '- ' + esc(tid) + ('：当前验收有效' if a['current'] else '：尚未验收或需复核') + '\n'
    if data['resource_recording_gaps']:
        text += '\n资源事实待登记：' + esc('、'.join(data['resource_recording_gaps'])) + '。任务引用或排队结果不代表资源状态、来源与采购条件已登记。\n'
    text += '\n业务结果：\n'
    for g in data['business_results']:
        text += '- ' + esc(g['target']) + '：' + {'pending':'待证据','met':'已记录达标证据','not_met':'已记录未达标证据'}[g['state']] + '；证据责任人 ' + esc(g['owner']) + '；' + esc('、'.join(g['evidence'])) + '\n'
    if not data['business_results']: text += '- 未登记目标与证据，不推断成功。\n'
    text += '\n收尾：' + ('已登记任务条件已齐；仍需盘点源中未结事项，并按里程碑检验与人审' if data['closure']['ready'] else esc('；'.join(data['closure']['issues']))) + '\n'
    return text
