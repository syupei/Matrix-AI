"""Project appointments, specialist obligations and configured instances in the existing task database.

Records are cooperative facts. Authentication belongs to the host, not actor strings.
"""
import importlib.util
import hashlib
import json
from pathlib import Path
import re

_spec = importlib.util.spec_from_file_location('matrix_experts', Path(__file__).with_name('expert_packages.py'))
experts = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(experts)

_spec = importlib.util.spec_from_file_location('matrix_model_fit', Path(__file__).with_name('pm_model_fit.py'))
model_fit = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(model_fit)

READ_OPS = {'team', 'resolve_instance', 'model_performance'}
INSTANCE_OPS = {'confirm_config', 'derive', 'retire_instance', 'relevel_instance', 'rename_instance'}
WRITE_OPS = {'appoint', 'revoke_appointment', 'register_participation', 'participation_event', 'bind_participation'} | INSTANCE_OPS
CONFIG, FIT = 'management/instance-config.json', 'management/model-fit.json'
KIT = Path(__file__).resolve().parents[3]  # tools/ -> orchestration/ -> matrix/ -> project root
CHOICE = {'unfit': 'insist', 'unregistered': 'acknowledge_unregistered'}
DERIVED_FIT = {'fit': 'fit', 'unregistered': 'unregistered', 'unfit': 'unfit_insisted'}
FIT_NAMES = {'fit': '适用', 'unregistered': '未登记（人已确认）', 'unfit_insisted': '模型不适用（人坚持使用；成果按 F1 检验）'}
PM_ROLES = {'matrix-project-management', 'project-management'}


def level(value):
    """'T4' -> 4; None when absent or not T1–T9."""
    return int(value[1]) if isinstance(value, str) and re.fullmatch(r'T[1-9]', value) else None


def risk(value):
    """'F1' -> 1 (lower is more severe); None when absent or not F0–F5."""
    return int(value[1]) if isinstance(value, str) and re.fullmatch(r'F[0-5]', value) else None


def professions(pm, root):
    """The project's profession registries, or this kit's when the project has none."""
    folder = pm.local(root, 'matrix/professions')
    return folder if folder.is_dir() else KIT / 'matrix/professions'


def registries(pm, root):
    return {r['id']: r for r in (json.loads(p.read_text(encoding='utf-8')) for p in sorted(professions(pm, root).glob('*/profession.json')))}


def level_row(pm, root, reg, value):
    """能做, 能判断, 不能做 of one row in the profession's level table."""
    for line in (professions(pm, root) / reg['id'] / reg['levels']['doc']).read_text(encoding='utf-8').splitlines():
        cells = [c.strip() for c in line.strip().strip('|').split('|')]
        if len(cells) >= 4 and cells[0] == value:
            return cells[1:4]
    return ['—'] * 3


def read(pm, root, ref):
    path = pm.local(root, ref)
    pm.require(path.is_file(), ref + ' missing')
    raw = path.read_bytes()
    return json.loads(raw.decode('utf-8')), hashlib.sha256(raw).hexdigest()


def fit_entries(pm, root, regs, db=None):
    """Validated configuration entries with their model fit: fit, unregistered or unfit."""
    data, sha = read(pm, root, CONFIG)
    items = data.get('entries') if isinstance(data, dict) else None
    pm.require(isinstance(items, list), 'instance-config.json: entries list required')
    seen, masters, aliases = set(), set(), set()
    for e in items:
        pm.require(isinstance(e, dict) and set(e) <= {'id', 'profession', 'level', 'model', 'count', 'master', 'aliases', 'expert', 'runner', 'effort'}, 'instance-config.json: entry fields are id, profession, level, model, count, master, aliases, expert, runner, effort')
        eid = e.get('id')
        pm.require(isinstance(eid, str) and re.fullmatch(pm.SAFE_ID, eid) is not None and eid not in seen, 'instance-config.json: unique simple entry ids required')
        seen.add(eid)
        reg = regs.get(e['profession']) if isinstance(e.get('profession'), str) else None
        pm.require(reg is not None, eid + ': profession must be a registry id')
        low, high = (level(x) for x in reg['levels']['range'])
        pm.require(level(e.get('level')) is not None and low <= level(e['level']) <= high, eid + ': level outside ' + '–'.join(reg['levels']['range']))
        pm.require(pm.nonempty(e.get('model')), eid + ': model name required')
        pm.require('effort' not in e or (isinstance(e['effort'], str) and re.fullmatch(r'[A-Za-z0-9_-]{1,64}', e['effort'])), eid + ': effort must be a host-supported identifier')
        pm.require(type(e.get('count')) is int and e['count'] >= 0, eid + ': count must be an integer >= 0')
        pm.require(type(e.get('master', False)) is bool, eid + ': master must be boolean')
        pm.require('runner' not in e or (isinstance(e['runner'], str) and re.fullmatch(pm.SAFE_ID, e['runner'])), eid + ': simple runner id required')
        names = e.get('aliases', [])
        pm.require(pm.strings(names) and (not names or len(names) == e['count']), eid + ': aliases must match configured count')
        for name in names:
            k = experts.key(name)
            pm.require(k not in aliases, 'duplicate instance alias')
            aliases.add(k)
        experts.binding(pm, root, e['profession'], e.get('expert'))
        if e.get('master'):
            floor = reg['levels'].get('master_min')
            pm.require(e['count'] == 1, eid + ': a master entry has count 1')
            pm.require(floor is None or level(e['level']) >= level(floor), eid + ': a master needs at least ' + str(floor))
            pm.require(e['profession'] not in masters, e['profession'] + ': at most one master entry')
            masters.add(e['profession'])
    models = {}
    if pm.local(root, FIT).is_file():
        rows = read(pm, root, FIT)[0]
        rows = rows.get('models') if isinstance(rows, dict) else None
        pm.require(isinstance(rows, list), 'model-fit.json: models list required')
        for m in rows:
            pm.require(isinstance(m, dict) and pm.nonempty(m.get('model')) and m['model'] not in models, 'model-fit.json: unique model names required')
            pm.require(isinstance(m.get('levels', {}), dict) and all(p in regs and level(v) for p, v in m.get('levels', {}).items()), 'model-fit.json: levels map registry ids to T1–T9')
            pm.require('capabilities' not in m or pm.strings(m['capabilities']), 'model-fit.json: capabilities must be a string list')
            pm.require(pm.nonempty(m.get('filled_by')), 'model-fit.json: filled_by required for ' + m['model'])
            models[m['model']] = m
    out, freshness = [], {}
    for e in items:
        m, need = models.get(e['model'], {}), model_fit.required(regs[e['profession']], e['level'])
        top, caps = m.get('levels', {}).get(e['profession']), m.get('capabilities')
        missing = [c for c in need if caps is not None and c not in caps]
        if e['model'] not in freshness:
            freshness[e['model']] = model_fit.reasons(pm, db, m)
        stale = freshness[e['model']]
        if stale:
            fit = 'unregistered'
        elif m and ((top and level(top) < level(e['level'])) or missing):
            fit = 'unfit'
        elif top and (caps is not None or not need):
            fit = 'fit'
        else:
            fit = 'unregistered'  # model not listed, no level for this profession, or capabilities not recorded
        out.append(dict(e, fit=fit, max_level=top, missing_capabilities=missing, review_reasons=stale))
    return out, sha


def fit_signatures(pm, root, db, entries=None):
    """Each approval depends only on its entry and its model's assessment/state."""
    entries = entries if entries is not None else fit_entries(pm, root, registries(pm, root), db)[0]
    data = read(pm, root, FIT)[0] if pm.local(root, FIT).is_file() else {}
    models = {m['model']: m for m in data.get('models', [])}
    return {e['id']: hashlib.sha256(json.dumps([models.get(e['model']), e], sort_keys=True).encode()).hexdigest()
            for e in entries}


def configuration(pm, root, db):
    """Configuration-file authorization is separate from per-entry model freshness."""
    rec = pm.integrity.records(db, 'instance_config').get('confirmed')
    try:
        return rec if rec and pm.integrity.file_hash(pm, root, CONFIG) == rec['sha256'] else None
    except (ValueError, OSError):
        return None


def confirmed(pm, root, db, entry_id=None):
    rec = configuration(pm, root, db)
    if not rec:
        return None
    try:
        signatures = fit_signatures(pm, root, db)
        selected = [entry_id] if entry_id is not None else list(signatures)
        return rec if all(k in signatures and rec.get('fit_signatures', {}).get(k) == signatures[k] for k in selected) else None
    except (ValueError, OSError):
        return None


def instance_fit_issue(pm, root, db, inst):
    if not inst or not inst.get('config_entry'):
        return None
    conf = confirmed(pm, root, db, inst['config_entry'])
    if not conf:
        return 'model fit or configuration changed; review and confirm before launching'
    entry = next((e for e in conf['entries'] if e['id'] == inst['config_entry']), None)
    if not entry or any(inst.get(k) != entry.get(k) for k in ('model', 'level', 'effort')) or inst.get('fit') != DERIVED_FIT[entry['fit']]:
        return 'apply the confirmed instance configuration with relevel_instance or retire_instance before launching'
    return None


def config_state(pm, root, db):
    state = {'confirmed': pm.integrity.records(db, 'instance_config').get('confirmed'), 'current': bool(confirmed(pm, root, db))}
    if pm.local(root, CONFIG).is_file():
        try:
            entries = fit_entries(pm, root, registries(pm, root), db)[0]
            signatures = fit_signatures(pm, root, db, entries)
            rec = configuration(pm, root, db)
            state['entries'] = [dict(e, current=bool(rec and rec.get('fit_signatures', {}).get(e['id']) == signatures[e['id']])) for e in entries]
        except (ValueError, OSError) as error:
            state['problem'] = str(error)
    return state


def display(regs, iid):
    """An instance id <profession>-<NNN> reads as <registry name>-<NNN>; other ids as they are."""
    m = re.fullmatch(r'(.+)-(\d{3,})', str(iid))
    return regs[m[1]]['name'] + '-' + m[2] if m and m[1] in regs else str(iid)


def profile(pm, root, inst, conf):
    """Generated profile of a derived instance; never the endpoint or a credential."""
    regs = registries(pm, root)
    reg = regs[inst['profession']]
    can, judge, cannot = level_row(pm, root, reg, inst['level'])
    person = ((pm.roster(root) or {}).get('people', {}).get(conf['person']) or {}).get('name', conf['person'])
    text = (f"# 实例档案：{display(regs, inst['id'])}\n\n由派生工具生成，不手写。\n\n"
            f"- 编号：{inst['id']}\n- 专业：{reg['name']}\n- 职级：{inst['level']}\n- 身份：{'master' if inst['master'] else '执行者'}\n"
            f"- 别名：{inst.get('alias', inst['id'])}\n- 专家：{inst.get('expert', {'id': 'builtin', 'version': 'installed'})}\n- 运行器：{inst.get('runner', 'default')}\n- 模型名称：{inst['model']}\n- 推理强度：{inst.get('effort') or '未指定'}\n- 配置项：{inst['config_entry']}\n- 派生人与时间：{inst['derived_by']}，{inst['derived_at']}\n"
            f"- 配置的确认人与原话：{person}：「{conf['quote']}」\n- 适用性：{FIT_NAMES[inst['fit']]}（派生时记录；当前状态查询 team）\n\n"
            f"## 本职级（{inst['level']}）\n\n- 能做：{can}\n- 能判断：{judge}\n- 不能做（越权）：{cannot}\n")
    pm.atomic(pm.local(root, workspace(pm, root, inst['id']) + '/profile.md'), text)


def assert_alias(pm, instances, alias, iid):
    k = experts.key(alias)
    for other in instances.values():
        if other['id'] != iid:
            reserved = [other['id'], other.get('alias', other['id']), *other.get('alias_history', [])]
            pm.require(all(experts.key(a) != k for a in reserved), 'duplicate or historical instance alias')


def resolve(pm, instances, value):
    k = experts.key(value)
    hits = [i for i in instances.values() if any(experts.key(a) == k for a in [i['id'], i.get('alias', i['id']), *i.get('alias_history', [])])]
    pm.require(len(hits) == 1, 'instance alias is missing or ambiguous')
    return hits[0]


def derived(inst):
    return bool(inst and inst.get('level') and inst.get('model'))


def level_issue(pm, db, task):
    """Why the task's owner or executor may not take it, or None (difficulty above level, retired)."""
    need, instances = level(task.get('difficulty')), pm.integrity.records(db, 'instance')
    for iid in sorted({task.get('owner'), task.get('executor')} - {None}):
        inst = instances.get(iid)
        if inst is None:
            continue
        if inst.get('active') is False:
            return iid + ' is retired; reassign the task'
        if need is not None and level(inst.get('level')) is None:
            return iid + ' has no level and cannot take a task of difficulty ' + task['difficulty']
        if need is not None and level(inst['level']) < need:
            alternatives = [i['id'] + ' (' + i['level'] + ')' for i in instances.values()
                            if i.get('active') is not False and i.get('profession') == inst.get('profession')
                            and level(i.get('level')) is not None and level(i['level']) >= need]
            return (iid + ' (' + inst['level'] + ') is below difficulty ' + task['difficulty']
                    + ': split the task or assign a higher level; do not relabel. Keep this difficulty when reassigning. Same-profession level-qualified instances '
                    + '(check availability and delegation): ' + (', '.join(sorted(alternatives)) or 'none registered')
                    + '. Otherwise split the actual goal/outputs/criteria into smaller tasks. Rewording the same scope '
                    + 'or adding “only follow confirmed rules” does not justify lowering difficulty; do not relabel.')
    return None


def master_issue(pm, db, cfg, task):
    """Project-level work dispatched by the PM goes to the master of the owner's profession."""
    inst = pm.integrity.records(db, 'instance').get(task['owner'])
    if task['manager'] == cfg['pm_actor'] and pm.integrity.project_level(task, cfg) and inst and inst.get('profession') and not inst.get('master'):
        return task['owner'] + ' is not the ' + inst['profession'] + ' master; project-level tasks go to the master'
    return None


def requirement(pm, root, task, instances):
    """Derived producers, effective risk, level floor and whether the checker needs another model."""
    producers = {task['owner'], task.get('executor')} - {None}
    made = [instances[i] for i in sorted(producers) if derived(instances.get(i))]
    insisted = any(p.get('fit') == 'unfit_insisted' for p in made)
    r, need = risk(task.get('risk')), level(task.get('difficulty'))
    if insisted:
        r = 1 if r is None else min(r, 1)  # work of an instance whose model was insisted on counts as at least F1
    regs = registries(pm, root) if need is not None and made else {}
    floors = [level(regs.get(p['profession'], {}).get('levels', {}).get('master_min')) for p in made]
    other_model = insisted or (r is not None and r <= 1) or any(f is not None and need >= f for f in floors)
    return producers, made, r, need, other_model


def independence(pm, root, db, task, checker):
    """independent, not_independent or same_instance, from the checker against the producers."""
    instances = pm.integrity.records(db, 'instance')
    producers, made, r, need, other_model = requirement(pm, root, task, instances)
    if checker in producers:
        return 'same_instance'
    c = instances.get(checker)
    if need is not None and not (derived(c) and level(c['level']) >= need):
        return 'not_independent'
    if other_model and not (derived(c) and len(made) == len(producers) and different_models(pm, db, task, producers, checker)):
        return 'not_independent'
    return 'independent'


def different_models(pm, db, task, producers, checker):
    """Only models the launcher recorded count: the producers' runs of this task and the checker's current run."""
    runs = pm.integrity.records(db, 'launch').values()
    made = {l['model'] for l in runs if l['task_id'] == task['id'] and l['purpose'] == 'start' and l['instance'] in producers and l['state'] != 'not_started'}
    checking = {l['model'] for l in runs if l['instance'] == checker and l['state'] in pm.platform.ACTIVE}
    return bool(made and checking and not made & checking)


def verification_issue(pm, root, db, task):
    """Why the current passed review cannot close an F0–F2 task, or None. Legacy producers keep the old rule."""
    instances = pm.integrity.records(db, 'instance')
    producers, made, r, need, other_model = requirement(pm, root, task, instances)
    if not made or r is None or r > 2 or any(i in instances and not derived(instances[i]) for i in producers):
        return None
    kind = task['review'].get('independence')
    if kind == 'independent':
        return None
    others = [i for i in instances.values() if derived(i) and i.get('active') and i['id'] not in producers and (need is None or level(i['level']) >= need)]
    if kind == 'same_instance' and not others:
        return None  # no other instance at this level in the project: recorded as 同一实例检验
    head = 'F' + str(r) + ' work needs an independent check (recorded: ' + str(kind) + ')'
    if any(not (other_model and i['model'] in {p['model'] for p in made}) for i in others):
        return head + ': assign another checker that meets C24 §6'
    return (head + ' and no instance in the project can give one: ask the PM to derive '
            + ('a different-model instance' if others else 'an instance at this level') + ' per the instance configuration, or ask a person to change the configuration')


def confirm(pm, root, db, cfg, tasks, cmd):
    pm.require(cmd['actor'] in {cfg['pm_actor'], cfg.get('frontdesk_actor')} - {None}, 'PM or front desk records the person\'s confirmation')
    pm.require(all(pm.nonempty(cmd.get(k)) for k in ['quote', 'presented_ref']), 'exact quote and presented reference required')
    pm.authorized(cmd.get('person'), [None], tasks, pm.roster(root))
    items, sha = fit_entries(pm, root, registries(pm, root), db)
    choices = cmd.get('choices', {})
    pm.require(isinstance(choices, dict) and set(choices) <= {e['id'] for e in items}, 'choices must name configuration entries')
    problems = []
    for e in items:
        want, got = CHOICE.get(e['fit']), choices.get(e['id'])
        if got == want:
            continue
        if want == 'insist':
            low = e['max_level'] and level(e['max_level']) < level(e['level'])
            problems.append(e['id'] + ': model ' + e['model'] + ' fits ' + e['profession'] + ' up to ' + (e['max_level'] or 'no listed level')
                            + (', below the configured ' + e['level'] if low else '')
                            + ('; lacks ' + '、'.join(e['missing_capabilities']) if e['missing_capabilities'] else '')
                            + ' - change the model, lower the level, or insist')
        elif want:
            problems.append(e['id'] + ': model ' + e['model'] + ' is not registered for ' + e['profession'] + '; review ' + ', '.join(e['review_reasons']) + '; change model, lower level or explicitly continue as acknowledge_unregistered')
        else:
            problems.append(e['id'] + ': the model fits; no choice applies')
    pm.require(not problems, 'configuration not confirmed: ' + '; '.join(problems))
    before = pm.integrity.records(db, 'instance_config').get('confirmed')
    pm.require(cmd.get('expected_revision') == before['revision'] if before else cmd.get('expected_revision') in {None, 0}, 'stale confirmation; reload the team view')
    signatures = fit_signatures(pm, root, db, items)
    items = [dict(e, expert_binding=experts.binding(pm, root, e['profession'], e.get('expert'))) for e in items]
    value = dict(id='confirmed', config=CONFIG, sha256=sha, entries=[dict(e, insisted=e['fit'] == 'unfit') for e in items],
                 person=cmd['person'], quote=cmd['quote'], presented_ref=cmd['presented_ref'], at=pm.now(),
                 fit_signatures=signatures,
                 revision=(before or {}).get('revision', 0) + 1, updated_at=pm.now())
    pm.integrity.save(pm, db, 'instance_config', value)
    return {'record': value}


def instance_op(pm, root, db, cfg, tasks, cmd):
    """Derive, relevel and retire instances only as the current confirmed configuration says."""
    op, actor = cmd['op'], cmd['actor']
    if op == 'confirm_config':
        return confirm(pm, root, db, cfg, tasks, cmd)
    pm.require(actor == cfg['pm_actor'], 'PM derives and updates instances from the confirmed configuration')
    if op == 'rename_instance':
        instances = pm.integrity.records(db, 'instance')
        inst = instances.get(cmd.get('id'))
        pm.require(inst and cmd.get('expected_revision') == inst['revision'], 'stale or missing instance')
        alias = cmd.get('alias')
        assert_alias(pm, instances, alias, inst['id'])
        value = dict(inst, alias=alias.strip(), alias_history=list(dict.fromkeys(inst.get('alias_history', []) + [inst.get('alias', inst['id'])])), revision=inst['revision'] + 1, updated_at=pm.now())
        pm.integrity.save(pm, db, 'instance', value)
        old_conf = pm.integrity.records(db, 'instance_config').get('confirmed')
        if inst.get('config_entry') and old_conf:
            profile(pm, root, value, old_conf)
        return {'record': value}
    instances = pm.integrity.records(db, 'instance')
    entry_id = cmd.get('entry') if op == 'derive' else instances.get(cmd.get('id'), {}).get('config_entry')
    conf = configuration(pm, root, db)
    pm.require(conf, 'no current confirmed instance configuration; ask the person to confirm the file first')
    if op == 'derive':
        pm.require(any(e['id'] == entry_id for e in conf['entries']), 'entry not in the confirmed configuration; do not derive outside it')
    if op != 'retire_instance':
        pm.require(confirmed(pm, root, db, entry_id), 'no current confirmed instance configuration; ask the person to confirm the entry first')
    if op == 'derive':
        entry = next((e for e in conf['entries'] if e['id'] == cmd.get('entry')), None)
        pm.require(entry, 'entry not in the confirmed configuration; do not derive outside it')
        active = [i for i in instances.values() if i.get('config_entry') == entry['id'] and i.get('active')]
        pm.require(len(active) < entry['count'], 'configured count reached for ' + entry['id'])
        pm.require(pm.nonempty(cmd.get('endpoint')), 'the real handle returned by the host, or platform for runs the launcher starts, is required')
        pm.require(pm.strings(cmd.get('write_roots', [])), 'write_roots must be paths')
        n = 1 + max([int(m[1]) for k in instances for m in [re.fullmatch(re.escape(entry['profession']) + r'-(\d{3,})', k)] if m] or [0])
        iid = entry['profession'] + '-' + str(n).zfill(3)
        chosen = experts.binding(pm, root, entry['profession'], entry.get('expert'))
        pm.require(chosen == entry.get('expert_binding', {'id':'builtin','version':'installed'}), 'expert changed since configuration approval')
        available = [a for a in entry.get('aliases', []) if not any(experts.key(a) == experts.key(i.get('alias', i['id'])) for i in active)]
        alias = available[0] if available else iid
        assert_alias(pm, instances, alias, iid)
        endpoint = 'platform:' + iid if cmd['endpoint'] == 'platform' else cmd['endpoint']
        pm.require(not any(i.get('active', True) and i.get('endpoint') == endpoint for i in instances.values()), 'endpoint already registered')
        roots = list(dict.fromkeys([workspace(pm, root, iid) + '/workspace'] + cmd.get('write_roots', [])))
        pm.require(all(pm.local(root, ref) != root for ref in roots), 'instance cannot own the whole project')
        value = dict(id=iid, role=entry['profession'], profession=entry['profession'], level=entry['level'], model=entry['model'],
                     alias=alias, alias_history=[], expert=chosen, runner=entry.get('runner', 'default'),
                     effort=entry.get('effort'), config_entry=entry['id'], fit=DERIVED_FIT[entry['fit']], master=entry.get('master', False),
                     endpoint=endpoint, write_roots=roots, derived_by=actor, derived_at=pm.now(), active=True, revision=1)
    else:
        inst = instances.get(cmd.get('id'))
        pm.require(inst and inst.get('config_entry') and inst.get('active'), 'active derived instance required')
        pm.require(cmd.get('expected_revision') == inst['revision'], 'stale instance record')
        pm.require(pm.nonempty(cmd.get('reason')), 'reason required')
        pm.require(not any(r['instance'] == inst['id'] for r in pm.platform.active(pm, db)), 'stop running work before changing the instance')
        pm.require(not any(t['state'] == 'running' and inst['id'] in {t['owner'], t.get('executor')} for t in tasks.values()), 'stop running work before changing the instance')
        entry = next((e for e in conf['entries'] if e['id'] == inst['config_entry']), None)
        if op == 'retire_instance':
            active = [i for i in instances.values() if i.get('config_entry') == inst['config_entry'] and i.get('active')]
            pm.require(not entry or len(active) > entry['count'] or entry['model'] != inst['model'] or entry.get('expert_binding', {'id':'builtin','version':'installed'}) != inst.get('expert', {'id':'builtin','version':'installed'}) or entry.get('runner', 'default') != inst.get('runner', 'default'), 'the confirmed configuration still includes this instance')
            value = dict(inst, active=False, retired_by=actor, retired_at=pm.now(), reason=cmd['reason'])
        else:
            pm.require(entry and entry['model'] == inst['model'] and entry.get('expert_binding', {'id':'builtin','version':'installed'}) == inst.get('expert', {'id':'builtin','version':'installed'}) and entry.get('runner', 'default') == inst.get('runner', 'default'), 'entry removed or its model changed; retire the instance instead')
            change = dict(level=entry['level'], effort=entry.get('effort'), master=entry.get('master', False), fit=DERIVED_FIT[entry['fit']])
            pm.require(any(inst.get(k) != v for k, v in change.items()), 'the confirmed configuration does not change this instance')
            value = dict(inst, previous_level=inst['level'], relevelled_by=actor, relevelled_at=pm.now(), reason=cmd['reason'], **change)
        value['revision'] = inst['revision'] + 1
    value['updated_at'] = pm.now()
    pm.integrity.save(pm, db, 'instance', value)
    if op != 'retire_instance':
        profile(pm, root, value, conf)
    return {'record': value}


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
    ref = 'management/instances/' + iid
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
    target = {'update': (cmd.get('changes') or {}).get('executor'), 'create': t.get('executor'), 'handoff': cmd.get('new_owner'), 'reassign': cmd.get('to')}.get(op)
    if target:
        pm.require(target in [actor, *a['delegates']], 'execution instance is outside allocated team')


def blockers(pm, root, db, tasks, tid, closing=False):
    out = []
    t = tasks[tid]
    problem = None if closing or t['state'] in pm.TERMINAL else level_issue(pm, db, t)
    if problem:
        out.append({'code': 'instance_level', 'task': tid, 'action': problem})
    if not closing and t['state'] != 'running':
        inst = pm.integrity.records(db, 'instance').get(t.get('executor') or t['owner'])
        issue = instance_fit_issue(pm, root, db, inst)
        if issue:
            out.append({'code': 'model_fit_review', 'task': tid, 'action': issue})
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
    if op == 'model_performance':
        return model_fit.performance(pm, db, cmd.get('since'))
    if op == 'resolve_instance':
        return {'record': resolve(pm, pm.integrity.records(db, 'instance'), cmd.get('name'))}
    if op == 'team':
        appointments = pm.integrity.records(db, 'appointment')
        return {'appointments': [dict(a, current=current(pm, root, a)) for a in appointments.values()],
                'participation': pm.integrity.records(db, 'participation_rule'),
                'obligations': pm.integrity.records(db, 'participation_obligation'),
                'instance_config': config_state(pm, root, db),
                'limitation': 'Records do not authenticate people or start processes.'}
    if op in INSTANCE_OPS:
        return instance_op(pm, root, db, cfg, tasks, cmd)
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
        pm.require(spec['mode'] != 'workflow_pm' or spec['role'] in PM_ROLES, 'workflow PM needs project management capability')
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
