"""Project stage projection and recorded human collaboration choices. No model calls."""
import json

READ_OPS = {'collaboration', 'decision_route', 'stage_flow'}
WRITE_OPS = {'collaboration_config', 'collaboration_asked'}
MODES = {'quick': '快速出品', 'regular': '常规协作', 'deep': '精细共创'}
FIELDS = {'profession', 'decision_scope', 'decision_kind'}
KINDS = {'professional', 'release', 'budget', 'project'}


def leaders(people):
    return [pid for pid, p in (people or {}).get('people', {}).items() if 'project' in p.get('decides', [])]


def masters(pm, people):
    out = {}
    for pid, p in (people or {}).get('people', {}).items():
        pm.require(pm.strings(p.get('masters', [])), 'masters must be a profession ID list')
        for profession in p.get('masters', []):
            pm.require(profession not in out, 'each profession has exactly one human master: ' + profession)
            out[profession] = pid
    return out


def route(pm, people, cfg, profession=None, scope=None, kind='professional', task_id=None, risk=None):
    pm.require(kind in KINDS, 'unknown decision kind')
    owners = masters(pm, people)
    lead = leaders(people)
    pm.require(len(lead) == 1, 'record one project leader in people.json')
    settings = cfg.get('collaboration', {})
    matches = [d for d in settings.get('delegations', []) if d.get('active', True)
               and d['profession'] == profession and kind in d['decisions']
               and ((scope and d['scope'] == scope) or (task_id and task_id in d.get('task_ids', [])))]
    pm.require(len(matches) <= 1, 'overlapping delegations: resolve explicitly before routing')
    recipient = matches[0]['person'] if matches else (owners.get(profession, lead[0]) if kind == 'professional' else lead[0])
    pm.require(recipient in (people or {}).get('people', {}), 'decision recipient no longer in roster')
    return {'person': recipient, 'basis': 'delegation:' + matches[0]['id'] if matches else
            'profession_master' if kind == 'professional' and profession in owners else 'project_leader',
            'separate_review': risk in {'F0', 'F1', 'money', 'privacy', 'compliance', 'irreversible'},
            'inform': lead if risk == 'F0' else []}


def view(pm, root, cfg, people):
    settings = cfg.get('collaboration', {})
    owners = masters(pm, people)
    profiles = {}
    for profession in sorted(pm.team.registries(pm, root)):
        selected = settings.get('profiles', {}).get(profession)
        mode = selected['mode'] if selected else settings.get('default', 'regular')
        profiles[profession] = dict(mode=mode, label=MODES[mode], confirmed=bool(selected),
            human_master=owners.get(profession), asked=profession in settings.get('asked', []),
            review='方向范围、可试用版本、发布；细节列入代定清单' if mode == 'quick' else
                   '专业阶段成果与关键取舍' if mode == 'regular' else '规则、边界、文字与验收逐项审阅',
            required=['成果', '证据', '高风险单独审阅'] + (['代定清单', '委托覆盖'] if mode == 'quick' else
                    ['关键取舍'] if mode == 'regular' else ['逐项决定记录']))
    return {'revision': settings.get('revision', 0), 'project_leaders': leaders(people),
            'default': settings.get('default', 'regular'), 'profiles': profiles,
            'ask_once': [p for p, v in profiles.items() if not v['confirmed'] and not v['asked']],
            'delegations': settings.get('delegations', []),
            'engineering': settings.get('engineering', {'state': 'pending', 'confirm_at': 'E-1'})}


def execute(pm, root, db, cmd):
    cfg, people = pm.config(db), pm.roster(root)
    op = cmd['op']
    if op == 'stage_flow':
        reg = pm.team.registries(pm, root).get(cmd.get('profession'), {})
        flow = next((f for f in reg.get('stage_flows', []) if f['key'] == cmd.get('flow')), None)
        pm.require(flow is not None, 'unknown profession stage flow')
        return dict(flow, total=len(flow['stages']), source='profession.json')
    if op == 'decision_route':
        task = pm.task_map(db).get(cmd.get('task_id'), {})
        return route(pm, people, cfg, cmd.get('profession', task.get('profession')),
                     cmd.get('scope', task.get('decision_scope')), cmd.get('kind', task.get('decision_kind', 'professional')),
                     cmd.get('task_id'), cmd.get('risk', task.get('risk')))
    if op == 'collaboration':
        return view(pm, root, cfg, people)
    pm.require(cmd['actor'] == cfg['pm_actor'], 'PM records collaboration choices')
    settings = json.loads(pm.canon(cfg.get('collaboration', {})))
    pm.require(cmd.get('expected_revision') == settings.get('revision', 0), 'stale collaboration revision')
    regs = pm.team.registries(pm, root)
    owners, lead = masters(pm, people), leaders(people)
    pm.require(len(lead) == 1, 'record one project leader in people.json')
    pm.require(set(owners) <= set(regs), 'unknown master profession')
    if op == 'collaboration_asked':
        requested = cmd.get('professions')
        pm.require(pm.strings(requested) and requested and set(requested) <= set(regs), 'registered professions required')
        pm.require(pm.nonempty(cmd.get('question')) and pm.nonempty(cmd.get('presented_ref')),
                   'ask the person first; record actual question text and presentation reference, not a plan to ask')
        settings.setdefault('questions', []).append(dict(professions=requested, question=cmd['question'],
                                                       presented_ref=cmd['presented_ref'], at=pm.now()))
        settings['asked'] = sorted(set(settings.get('asked', [])) | set(requested))
    else:
        person, quote, changes = cmd.get('person'), cmd.get('quote'), cmd.get('changes')
        pm.require(person in (people or {}).get('people', {}) and pm.nonempty(quote), 'listed person and exact quote required')
        pm.require(isinstance(changes, dict) and changes and set(changes) <= {'default', 'profiles', 'delegations', 'engineering'}, 'unknown collaboration fields')
        if 'default' in changes:
            pm.require(person == lead[0] and changes['default'] in MODES, 'project leader sets the default profile')
            settings['default'] = changes['default']
        if 'profiles' in changes:
            pm.require(isinstance(changes['profiles'], dict), 'profiles must be a profession-to-mode map')
            for profession, mode in changes['profiles'].items():
                pm.require(profession in regs and mode in MODES, 'unknown profession/profile')
                pm.require(person in {lead[0], owners.get(profession)}, 'only leader or that human master changes profile')
                settings.setdefault('profiles', {})[profession] = dict(mode=mode, person=person, quote=quote, at=pm.now())
        if 'delegations' in changes:
            pm.require(isinstance(changes['delegations'], list), 'delegations must be a list')
            existing = {d['id']: d for d in settings.get('delegations', [])}
            for d in changes['delegations']:
                pm.require(isinstance(d, dict) and set(d) <= {'id', 'profession', 'scope', 'person', 'grantor', 'quote', 'decisions', 'task_ids', 'active'}, 'unknown delegation fields')
                pm.require(all(pm.nonempty(d.get(k)) for k in ['id', 'profession', 'scope', 'person', 'grantor', 'quote']), 'delegation needs ID, profession, scope, recipient, grantor and exact quote')
                pm.require(d['profession'] in regs and d['person'] in people['people'], 'unknown delegation profession/person')
                pm.require(d['grantor'] == person and person in {lead[0], owners.get(d['profession'])}, 'only leader or that master grants authority')
                pm.require(pm.strings(d.get('decisions')) and d['decisions'] and set(d['decisions']) <= KINDS, 'explicit decision kinds required')
                pm.require(not (set(d['decisions']) - {'professional'}) or person == lead[0], 'release/budget/project delegation requires project leader')
                pm.require(pm.strings(d.get('task_ids', [])), 'task_ids must be a list')
                pm.require(all(t in pm.task_map(db) for t in d.get('task_ids', [])), 'unknown delegated task')
                pm.require(type(d.get('active', True)) is bool, 'active must be boolean')
                old = existing.get(d['id'])
                pm.require(not old or person in {lead[0], old['grantor']}, 'only original grantor or leader changes a delegation')
                existing[d['id']] = dict(d, at=pm.now())
            settings['delegations'] = list(existing.values())
        if 'engineering' in changes:
            e = changes['engineering']
            pm.require(person == owners.get('code-engineering', lead[0]), 'engineering human master confirms rigor')
            pm.require(isinstance(e, dict) and set(e) == {'tier', 'basis', 'stage'} and e['tier'] in {'small', 'medium', 'large'}
                       and pm.nonempty(e['basis']) and e['stage'] == 'E-1', 'engineering tier needs factual basis and E-1 confirmation')
            settings['engineering'] = dict(e, person=person, quote=quote, at=pm.now(), state='confirmed')
    settings['revision'] = settings.get('revision', 0) + 1
    cfg['collaboration'] = settings
    db.execute("UPDATE meta SET value=? WHERE key='config'", (pm.canon(cfg),))
    return view(pm, root, cfg, people)


def markdown(pm, root, cfg, people):
    data = view(pm, root, cfg, people)
    text = '# 协作配置\n\n只读派生视图；事实在任务库，名单在 people.json。\n\n'
    for profession, row in data['profiles'].items():
        text += f"- {profession}：{row['label']}；主责 {row['human_master'] or '项目负责人兜底'}；" + ('已确认' if row['confirmed'] else '待确认')
        text += ('（已问过，不重复问）' if row['asked'] and not row['confirmed'] else '') + f"；审阅：{row['review']}；必需材料：{'、'.join(row['required'])}。\n"
    text += '\n研发严格程度（独立设置）：' + pm.canon(data['engineering']) + '\n'
    for d in data['delegations']:
        text += f"\n- 授权 {d['id']}：{d['scope']} → {d['person']}；授权人 {d['grantor']}；种类 {','.join(d['decisions'])}；有效 {d.get('active', True)}。\n"
    return text


def stage_projection(pm, tasks, actions, pm_actor='PM'):
    stages = {k: t for k, t in tasks.items() if t.get('kind') == 'stage' and t['state'] not in pm.RETIRED}
    if not stages:
        return None
    depth = {}
    def level(k):
        if k not in depth:
            depth[k] = 1 + max([level(d) for d in stages[k]['dependencies'] if d in stages] or [-1])
        return depth[k]
    ordered = sorted(stages, key=lambda k: (level(k), stages[k].get('order', 10**6), k))
    rows = []
    for index, k in enumerate(ordered, 1):
        t = stages[k]
        complete = pm.effective_done(t, tasks)
        state = '待复核' if t.get('needs_recheck') or (t['state'] == 'done' and not complete) else '返工中' if t.get('sent_back') or (t.get('rework') and t['state'] in {'planned', 'running'}) else pm.STATE_NAMES[t['state']]
        rows.append(dict(id=k, position=index, title=t['title'], state=t['state'], label=state,
                         complete=complete, dependencies=t['dependencies']))
    current = [r for r in rows if not r['complete'] and (r['state'] != 'planned' or r['label'] == '返工中')]
    if not current:
        current = [r for r in rows if not r['complete'] and all(pm.effective_done(tasks[d], tasks) for d in r['dependencies'])]
    if not current:
        current = [r for r in rows if not r['complete']]
    first = next(iter(actions), None)
    next_action = ((first.get('why') or first.get('what') or first.get('code') or first['kind']) +
                   '（' + str(first.get('task') or first.get('id') or 'PM') + '）') if first else (
                   stages[current[0]['id']]['next_action'] if current else '无')
    next_actor = pm_actor if first else stages[current[0]['id']]['manager'] if current else None
    if next_actor:
        next_action += '（' + next_actor + '）'
    position = '；'.join(f"第{r['position']}项 {r['id']}「{r['title']}」{r['label']}" for r in current) or '全部完成'
    line = f"项目阶段：已登记共 {len(rows)} 项里程碑｜{position}｜依据：任务库｜下一步：{next_action}"
    return dict(total=len(rows), stages=rows, current=[r['id'] for r in current], next_action=next_action, next_actor=next_actor, line=line)
