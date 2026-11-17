"""Direction sample and the recorded cost of requesting human attention."""

from datetime import datetime


READ_OPS = {'human_attention_status'}
WRITE_OPS = {'direction_sample', 'human_attention'}
TASKS = (
    ('brief', 'product', '品类与参照简报', (), 'product/specs/方向简报.md'),
    ('scene', 'experience-design', '渲染核心场景', ('brief',), 'design/核心场景样张.md'),
    ('samples', 'content-design', '关键时刻样句', ('brief',), 'content/玩法样句.md'),
    ('compose', 'product', '合成方向样张', ('scene', 'samples'), 'product/specs/00-方向样张.md'),
    ('fit', 'fit_checker', '检查品类贴合', ('compose',), 'product/reviews/品类贴合.json'),
)


def attention(pm, root, db, cfg, cmd):
    records = pm.integrity.records(db, 'human_attention')
    if cmd['op'] == 'human_attention_status':
        return {'items': list(records.values()), 'count':len(records),
                'characters':sum(r['characters'] for r in records.values()),
                'answered':sum(r['seconds'] is not None for r in records.values()),
                'seconds':sum(r['seconds'] or 0 for r in records.values())}
    actor = cmd['actor']
    pm.require(actor in {cfg['pm_actor'], cfg.get('frontdesk_actor')} - {None},
               'PM or front desk records displayed requests and responses')
    rec = records.get(cmd.get('id'))
    pm.require(pm.nonempty(cmd.get('id')), 'attention id required')
    at = pm.now()
    if rec is None:
        kind = cmd.get('kind')
        pm.require(kind in {'confirmation','clarification','correction'}, 'invalid request type')
        source = cmd.get('display')
        pm.require(pm.nonempty(source), 'displayed material reference required')
        body = pm.local(root, source).read_text(encoding='utf-8')
        pm.require(bool(body.strip()), 'displayed material is empty')
        rec = dict(id=cmd['id'], kind=kind, display=source, characters=len(body),
                   displayed_sha256=pm.integrity.file_hash(pm, root, source), opened_at=at, seconds=None)
    else:
        pm.require(rec['seconds'] is None and pm.nonempty(cmd.get('response')), 'actual response or already answered')
        response = pm.local(root, cmd['response']).read_text(encoding='utf-8')
        pm.require(bool(response.strip()), 'actual response is empty')
        elapsed = (datetime.fromisoformat(at) - datetime.fromisoformat(rec['opened_at'])).total_seconds()
        rec.update(response=cmd['response'], answered_at=at, seconds=max(0, int(elapsed)))
    pm.integrity.save(pm, db, 'human_attention', rec)
    return {'attention':rec}


def execute(pm, root, db, cmd):
    cfg = pm.config(db)
    if cmd['op'] != 'direction_sample':
        return attention(pm, root, db, cfg, cmd)
    pm.require(cmd['actor'] == cfg['pm_actor'], 'only PM registers a project direction sample')
    key = cmd.get('id')
    brief_path = cmd.get('brief')
    pm.require(pm.nonempty(key) and pm.nonempty(brief_path), 'direction sample id and clarified brief required')
    pm.integrity.file_hash(pm, root, brief_path)
    pm.require(cmd.get('profile') == '游戏与玩乐', 'direction sample template is for the game practice profile')
    pm.require(pm.nonempty(cmd.get('combined_review_authorization')), 'record agreement to merge direction and P-1 review')
    pm.require(pm.nonempty(cmd.get('person')), 'record the deciding person for the combined P-1 review')
    roster = pm.roster(root)
    if roster:
        person = roster['people'].get(cmd['person'], {})
        pm.require(set(person.get('decides', ())) & {'product','project'}, 'product or project decision authority required')
    assigned = cmd.get('assigned', {})
    expected = {'product','experience-design','content-design','fit_checker','task_checker'}
    pm.require(isinstance(assigned, dict) and set(assigned) == expected and all(pm.nonempty(x) for x in assigned.values()), 'named product, design, content and independent checkers required')
    instances = pm.integrity.records(db, 'instance')
    for role in ('product','experience-design','content-design'):
        entry = instances.get(assigned[role], {})
        pm.require(entry.get('active') and entry.get('master') and entry.get('profession') == role,
                   'PM: route the missing ' + role + ' master through expertise-gap handling')
    producers = {assigned[role] for role in ('product','experience-design','content-design')}
    pm.require(not producers & {assigned['fit_checker'],assigned['task_checker']} and assigned['fit_checker'] != assigned['task_checker'],
               'direction and task checkers must be independent of the producers and each other')
    pm.require(instances.get(assigned['fit_checker'], {}).get('active'), 'active direction fit checker required')
    pm.require(assigned['task_checker'] == cfg['pm_actor'] or instances.get(assigned['task_checker'], {}).get('active'),
               'active task checker or PM required')
    downstream = cmd.get('downstream', [])
    pm.require(pm.strings(downstream), 'downstream task ids must be a list')
    before = pm.task_map(db)
    pm.require(all(tid in before and before[tid]['state']=='planned' and before[tid]['manager']==cfg['pm_actor']
                   for tid in downstream), 'downstream tasks must be planned and managed by the PM')
    result = []
    output_by_id = {suffix:out for suffix,_,_,_,out in TASKS}
    # Register works first, then create their parent milestone and bind each row to it
    # in the same transaction. A failed child rolls back the whole operation.
    for suffix, role, title, deps, output in TASKS:
        task = dict(id=key+'-'+suffix, title=title, owner=assigned[role], executor=assigned[role],
                    checker=assigned['task_checker'], goal=title, next_action=title,
                    inputs=[output_by_id[d] for d in deps] or [brief_path], outputs=[output],
                    criteria=['按方向样张确认范围交回并提供证据'], dependencies=[key+'-'+d for d in deps])
        if suffix == 'fit':
            task['project_level'] = False  # independent execution is not profession direction ownership
        created = pm.execute(root, dict(op='create', actor=cmd['actor'], event_id=cmd['event_id']+':'+suffix, task=task), _db=db)
        result.append(created['task']['id'])
    milestone = dict(id=key, kind='stage', title='方向样张与 P-1 合并审阅', owner=assigned['product'],
                     checker=assigned['task_checker'], goal='采用方向样张与 P-1 澄清结论',
                     next_action='向决定人合并展示样张与 P-1 结论', inputs=[brief_path, output_by_id['fit']],
                     outputs=[output_by_id['compose']], criteria=['保留已确认调性契约与人审依据'],
                     dependencies=[key+'-fit'], human_required=True, slots=0,
                     people={'decide':[cmd['person']]}, source=cmd['combined_review_authorization'])
    pm.execute(root, dict(op='create', actor=cmd['actor'], event_id=cmd['event_id']+':milestone', task=milestone), _db=db)
    for tid in result + downstream:
        task = pm.task_map(db)[tid]
        changes = {'stage':key} if tid in result else {'dependencies':list(dict.fromkeys([*task['dependencies'],key]))}
        # Commercial scope only changes for downstream tasks already held by the PM.
        actor = task['owner'] if tid in result else cfg['pm_actor']
        pm.execute(root, dict(op='update', actor=actor, event_id=cmd['event_id']+':bind:'+tid, task_id=tid,
                              expected_revision=task['revision'], changes=changes, reason='方向样张任务链'), _db=db)
    rec = dict(id=key, tasks=result, milestone=key, downstream=downstream, profile=cmd['profile'],
               reserved_roles=['art-production'], fit_checker=assigned['fit_checker'], producer=assigned['product'])
    pm.integrity.save(pm, db, 'direction_sample', rec)
    return {'direction_sample':rec}


def confirm_milestone(pm, root, db, task):
    rec = pm.integrity.records(db, 'direction_sample').get(task['id'])
    if not rec:
        return
    tone = pm.admission.load_gate().tone
    current = tone.validate(root, tone.DEFAULT_PATH)
    fit_ref = 'product/reviews/品类贴合.json'
    reviewed = [current['parts'][key] for key in ('scene','samples')]
    fit = tone.check_fit(root, fit_ref, reviewed)
    approved = task.get('human_review') or {}
    expected_checker = approved.get('person') if fit['mode']=='human' else rec['fit_checker']
    pm.require(fit['checker'] == expected_checker and fit['producer'] == rec['producer'],
               'use the assigned fit checker or the documented human viewport review')
    pm.require(approved.get('person') == current['confirmation']['person']
               and approved.get('quote') == current['confirmation']['quote'],
               'direction contract confirmation must match the combined human review')
