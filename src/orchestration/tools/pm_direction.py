"""Direction sample and the recorded cost of requesting human attention."""

from datetime import datetime
import json
import re


READ_OPS = {'human_attention_status'}
WRITE_OPS = {'direction_sample', 'direction_resolve_gap', 'human_attention', 'stage_confirmation'}
TASKS = (
    ('brief', 'product', '活动范围与参照简报', (), 'product/specs/方向简报.md'),
    ('scene', 'experience-design', '渲染核心场景', ('brief',), 'design/核心场景样张.md'),
    ('samples', 'content-design', '关键情境样句', ('brief',), 'content/方向样句.md'),
    ('feasibility', 'code-engineering', '核对运行条件', ('brief',), 'engineering/方向可达性.md'),
    ('acceptance', 'quality-engineering', '拟定体验检验方式', ('brief',), 'engineering/qa/方向检验.md'),
    ('compose', 'product', '合成项目做法档与方向样张', ('scene', 'samples', 'feasibility', 'acceptance'), 'product/specs/方向样张草稿.md'),
    ('fit', 'fit_checker', '检查做法档与方向样张贴合', ('compose',), 'product/reviews/方向贴合.json'),
)
PROFILE_OUTPUT = 'product/specs/项目做法档.json'
PREVIEW_OUTPUT = 'design/preview.html'
PRODUCERS = ('product', 'experience-design', 'content-design', 'code-engineering', 'quality-engineering')


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
    pm.require(pm.nonempty(cmd.get('id')) and re.fullmatch(pm.SAFE_ID,cmd['id']), 'simple attention id required')
    at = pm.now()
    tone = pm.admission.load_gate().tone
    evidence = tone.evidence
    if rec is None:
        kind = cmd.get('kind')
        pm.require(kind in {'confirmation','clarification','correction'}, 'invalid request type')
        source = cmd.get('display')
        pm.require(pm.nonempty(source), 'displayed material reference required')
        body = pm.local(root, source).read_text(encoding='utf-8')
        pm.require(bool(body.strip()), 'displayed material is empty')
        rec = dict(id=cmd['id'], kind=kind, display=source, characters=len(body),
                   displayed_sha256=pm.integrity.file_hash(pm, root, source), opened_at=at, seconds=None)
        task_id = cmd.get('task_id')
        direction = pm.integrity.records(db, 'direction_sample').get(task_id)
        task = pm.task_map(db).get(task_id, {})
        stage = task.get('practice_stage') or {}
        purpose=cmd.get('review_purpose')
        pm.require(purpose in {None,'asset_anchors','stage_review'}, 'review_purpose must be asset_anchors or stage_review')
        if purpose:
            pm.require(kind=='confirmation' and task, 'a professional review request needs confirmation kind and task_id')
            check_asset_attention(pm,root,task,source,cmd.get('stage_state'),allow_unmet=True)
        rec.update(review_purpose=purpose,stage_state=cmd.get('stage_state'))
        inputs = cmd.get('inputs', [])
        pm.require(pm.strings(inputs), 'attention inputs must be project files')
        refs = [evidence.ref(root, source), *[evidence.ref(root, name) for name in inputs]]
        context = dict(task_id=task_id, scope=cmd.get('scope'), request_id=cmd['id'],
                       artifacts=[evidence.ref(root, name) for name in inputs])
        if cmd.get('intake_id'):
            incoming = pm.integrity.records(db, 'input_admission').get(cmd['intake_id'])
            pm.require(incoming and (incoming.get('review') or {}).get('outcome') == 'approved', 'display a professionally reviewed intake version')
            context.update(input={key:incoming[key] for key in ('id','source_id','version','path','sha256')},
                           master_review_sha256=tone.practice.digest(incoming['review']))
            refs.append(evidence.ref(root, incoming['path']))
        if direction:
            pm.require(pm.nonempty(cmd.get('scope')), 'direction display needs its explicit review scope')
            draft_path = direction['outputs']['compose']
            draft = tone.validate(root, draft_path, confirmed=False, _pending_human=True)
            context.update(direction_sha256=tone.direction_binding(tone.DEFAULT_PATH, draft)['direction_sha256'], draft=draft_path,
                           scope=[row['id'] for row in tone.profile(root,draft)['scopes']],artifacts=list(draft['parts'].values()))
            refs.extend([evidence.ref(root, draft_path), *draft['parts'].values()])
        rec.update(task_id=task_id, scope=cmd.get('scope'), display_bundle=evidence.seal_bundle(root, refs, context,follow_refs=bool(direction)), context=context)
    else:
        pm.require(rec['seconds'] is None and pm.nonempty(cmd.get('response')), 'actual response or already answered')
        response = pm.local(root, cmd['response']).read_text(encoding='utf-8')
        pm.require(bool(response.strip()), 'actual response is empty')
        elapsed = (datetime.fromisoformat(at.replace('Z','+00:00')) - datetime.fromisoformat(rec['opened_at'].replace('Z','+00:00'))).total_seconds()
        message = evidence.response_message(root, cmd['response'], cmd.get('response_id'))
        pm.require(message, 'complete response message is empty')
        identity = evidence.response_identity(root,{'path':cmd['response'],'response_id':cmd.get('response_id')})
        def reused(other):
            old=other.get('response_identity') or {}
            if not old.get('source') and other.get('response'):
                old={'source':other['response'],'response_id':other.get('response_id')}
            return old == identity
        pm.require(not any(reused(other) and other['id'] != rec['id'] for other in records.values()),
                   'this response source is already bound to another displayed request; save each actual new reply in its own source file')
        source_ref = evidence.ref(root, cmd['response'])
        rec.update(response=cmd['response'], response_id=cmd.get('response_id'), response_identity=identity,
                   response_message=message, response_bundle=evidence.seal_bundle(root, [source_ref], identity),
                   response_ref=source_ref, answered_at=at, seconds=max(0, int(elapsed)))
    pm.integrity.save(pm, db, 'human_attention', rec)
    return {'attention':rec}


def execute(pm, root, db, cmd):
    cfg = pm.config(db)
    if cmd['op'] == 'stage_confirmation':
        return stage_confirmation(pm, root, db, cfg, cmd)
    if cmd['op'] == 'direction_resolve_gap':
        return resolve_gap(pm, root, db, cfg, cmd)
    if cmd['op'] != 'direction_sample':
        return attention(pm, root, db, cfg, cmd)
    pm.require(cmd['actor'] == cfg['pm_actor'], 'only PM registers a project direction sample')
    key = cmd.get('id')
    brief_path = cmd.get('brief')
    pm.require(pm.nonempty(key) and pm.nonempty(brief_path), 'direction sample id and clarified brief required')
    pm.integrity.file_hash(pm, root, brief_path)
    pm.require(pm.nonempty(cmd.get('profile')), 'record a display label for the project practice profile')
    tone = pm.admission.load_gate().tone
    example = cmd.get('example')
    if example is not None:
        pm.require(example == tone.practice.load_example()['id'], 'unknown practice profile example')
    pm.require(pm.nonempty(cmd.get('combined_review_authorization')), 'record agreement to merge direction and P-1 review')
    pm.require(pm.nonempty(cmd.get('person')), 'record the deciding person for the combined P-1 review')
    roster = pm.roster(root)
    if roster:
        person = roster['people'].get(cmd['person'], {})
        pm.require(set(person.get('decides', ())) & {'product','project'}, 'product or project decision authority required')
    assigned = cmd.get('assigned', {})
    expected = set(PRODUCERS) | {'fit_checker', 'task_checker'}
    pm.require(isinstance(assigned, dict) and assigned.keys() <= expected and all(value is None or pm.nonempty(value) for value in assigned.values()),
               'name the professional masters and the independent checkers')
    instances = pm.integrity.records(db, 'instance')
    missing_roles = [role for role in PRODUCERS if not assigned.get(role)]
    for role in PRODUCERS:
        if not assigned.get(role):continue
        entry = instances.get(assigned[role], {})
        pm.require(entry.get('active') and entry.get('master') and entry.get('profession') == role,
                   'PM: route the missing ' + role + ' master through expertise-gap handling')
        pm.team.experts.entry(pm, root, entry)
    producers = {assigned[role] for role in PRODUCERS if assigned.get(role)}
    pm.require(assigned.get('task_checker') and assigned['task_checker'] != cfg['pm_actor'],
               'name a registered independent task_checker; PM adopts the result but cannot check tasks it creates')
    if not assigned.get('fit_checker'):missing_roles.append('fit_checker')
    assigned.setdefault('fit_checker',None)
    pm.require(not producers & {assigned['fit_checker'],assigned['task_checker']} and assigned['fit_checker'] != assigned['task_checker'],
               'direction and task checkers must be independent of the producers and each other')
    pm.require(not assigned['fit_checker'] or (assigned['fit_checker'] in instances
               and instances[assigned['fit_checker']].get('active', True)), 'active direction fit checker required')
    pm.require(assigned['task_checker'] in instances and instances[assigned['task_checker']].get('active', True),
               'active independent task checker required')
    admitted_inputs=cmd.get('admitted_inputs',[])
    pm.require(pm.strings(admitted_inputs) and admitted_inputs and len(admitted_inputs)==len(set(admitted_inputs)),
               'direction_sample requires the admitted versions of the real brief and its source materials')
    admitted=pm.integrity.records(db,'input_admission')
    pm.require(all(key in admitted for key in admitted_inputs),'direction brief admission id missing')
    brief_inputs=list(dict.fromkeys([brief_path,*[admitted[key]['path'] for key in admitted_inputs]]))
    pm.require(any(admitted[key]['path']==brief_path for key in admitted_inputs),'bind the admitted actual brief version')
    downstream = cmd.get('downstream', [])
    pm.require(pm.strings(downstream), 'downstream task ids must be a list')
    before = pm.task_map(db)
    pm.require(all(tid in before and before[tid]['state']=='planned' and before[tid]['manager']==cfg['pm_actor']
                   for tid in downstream), 'downstream tasks must be planned and managed by the PM')
    result = []
    output_by_id = {suffix:out for suffix,_,_,_,out in TASKS}
    available = set()
    for suffix,role,_,deps,_ in TASKS:
        if assigned.get(role) and set(deps) <= available:available.add(suffix)
    rec = dict(id=key, tasks=[key + '-' + suffix for suffix in output_by_id if suffix in available], milestone=key,
               downstream=downstream, profile=cmd['profile'], example=example,
               brief=brief_path, admitted_inputs=admitted_inputs, outputs=output_by_id, practice_profile=PROFILE_OUTPUT, preview=PREVIEW_OUTPUT,
               reserved_roles=['art-production'], fit_checker=assigned['fit_checker'],
               producer=assigned.get('product'), masters={role: assigned[role] for role in PRODUCERS if assigned.get(role)},
               assigned=dict(assigned), task_checker=assigned['task_checker'],
               missing_roles=missing_roles, pending_contributions=[suffix for suffix in output_by_id if suffix not in available])
    pm.integrity.save(pm, db, 'direction_sample', rec)
    # Register works first, then create their parent milestone and bind each row to it
    # in the same transaction. A failed child rolls back the whole operation.
    for suffix, role, title, deps, output in TASKS:
        if suffix not in available:continue
        task = dict(id=key+'-'+suffix, title=title, owner=assigned[role], executor=assigned[role],
                    checker=assigned['task_checker'], goal=title, next_action=title,
                    inputs=[output_by_id[d] for d in deps] or brief_inputs, outputs=[output],
                    criteria=['按方向样张确认范围交回并提供证据'], dependencies=[key+'-'+d for d in deps])
        if suffix == 'brief':task['admitted_inputs']=admitted_inputs
        if suffix == 'scene':
            task['outputs'].append(PREVIEW_OUTPUT)
        if suffix == 'compose':
            task['inputs'].append(PREVIEW_OUTPUT)
            task['outputs'].append(PROFILE_OUTPUT)
        if suffix == 'fit':
            task['inputs'].append(PROFILE_OUTPUT)
        if suffix == 'fit':
            task['project_level'] = False  # independent execution is not profession direction ownership
        created = pm.execute(root, dict(op='create', actor=cmd['actor'], event_id=cmd['event_id']+':'+suffix, task=task), _db=db)
        result.append(created['task']['id'])
    milestone = dict(id=key, kind='stage', title='方向样张与 P-1 合并审阅', owner=assigned.get('product') or cfg['pm_actor'],
                     checker=assigned['task_checker'], goal='采用方向样张与 P-1 澄清结论',
                     next_action='向决定人合并展示做法档、样张与 P-1 结论', admitted_inputs=admitted_inputs, inputs=brief_inputs+([PROFILE_OUTPUT,output_by_id['fit']] if 'fit' in available else []),
                     outputs=[tone.DEFAULT_PATH], criteria=['保留已确认调性契约与人审依据'],
                     dependencies=[key+'-fit'] if 'fit' in available else [key+'-'+suffix for suffix in output_by_id if suffix in available], human_required=True, slots=0,
                     people={'decide':[cmd['person']]}, source=cmd['combined_review_authorization'])
    pm.execute(root, dict(op='create', actor=cmd['actor'], event_id=cmd['event_id']+':milestone', task=milestone), _db=db)
    for tid in result + downstream:
        task = pm.task_map(db)[tid]
        changes = {'stage':key} if tid in result else {'dependencies':list(dict.fromkeys([*task['dependencies'],key]))}
        # Commercial scope only changes for downstream tasks already held by the PM.
        actor = cfg['pm_actor']
        pm.execute(root, dict(op='update', actor=actor, event_id=cmd['event_id']+':bind:'+tid, task_id=tid,
                              expected_revision=task['revision'], changes=changes, reason='方向样张任务链'), _db=db)
    return {'direction_sample':rec}


def resolve_gap(pm, root, db, cfg, cmd):
    """Adopt a real gap delivery and schedule only the contributions it unblocks."""
    pm.require(cmd['actor'] == cfg['pm_actor'], 'only PM adopts direction gap deliveries')
    rec = pm.integrity.records(db, 'direction_sample').get(cmd.get('id'))
    pm.require(rec and not rec.get('closed'), 'use an open direction milestone')
    role = cmd.get('role')
    pm.require(role in rec.get('missing_roles', []) or role in rec.get('gap_resolutions', {}),
               'role is not a recorded direction gap')
    gap = pm.integrity.records(db, 'gap').get(cmd.get('gap'))
    pm.require(gap and gap.get('decision') and gap['status'] in {'self', 'closed'},
               'record the person’s gap choice and complete its delivery first')
    pm.require(gap.get('profession') == role or (role == 'fit_checker' and gap.get('domain') == '方向贴合检验'),
               'gap must name this missing profession or direction fit review')
    tone = pm.admission.load_gate().tone
    tasks = pm.task_map(db)
    suffixes = [suffix for suffix, profession, _, _, _ in TASKS
                if profession == role and suffix != 'compose']
    required = [rec['outputs'][suffix] for suffix in suffixes]
    if role == 'experience-design':
        required.append(rec.get('preview', PREVIEW_OUTPUT))
    delivery = tasks.get(cmd.get('task_id'))
    adopted = cmd.get('admitted_inputs', [])
    pm.require(pm.strings(adopted), 'admitted_inputs must list adopted contribution versions')
    if delivery:
        pm.require(delivery['state'] == 'done' and delivery.get('gap') == gap['id'],
                   'use a checked and closed task linked to this gap')
        handed = delivery.get('handed_output_sha256') or {}
        pm.require(all(handed.get(path) == pm.integrity.file_hash(pm, root, path) for path in required),
                   'gap delivery must contain the current assigned contribution files')
        if gap['status'] == 'self':
            pm.require(any(pm.gap_label(gap) in item for item in delivery.get('evidence', [])),
                       'retain the non-specialist qualification in the self-delivery evidence')
    else:
        pm.require(gap['status'] == 'closed' and adopted,
                   'external or human gap delivery needs closed gap evidence and admitted contribution versions')
        if gap['decision']['choice'] in {'human','expert'}:
            pm.require((gap.get('result') or {}).get('by') in {cfg['pm_actor'],cfg.get('frontdesk_actor')} - {None},
                       gap['decision']['choice'] + ' direction delivery must have been recorded by PM or front desk')
        admissions = pm.integrity.records(db, 'input_admission')
        latest = pm.admission.ref_latest(admissions)
        covered = set()
        for aid in adopted:
            item = admissions.get(aid)
            pm.require(item and item['state'] == 'admitted' and latest[item['source_id']]['id'] == aid
                       and pm.integrity.file_hash(pm, root, item['path']) == item['sha256'],
                       'adopt the current reviewed gap result, not an old or unreviewed source')
            covered.add(item['path'])
        pm.require(set(required) <= covered and set(required) <= set((gap.get('result') or {}).get('evidence', [])),
                   'closed gap and admitted versions must cover the assigned contribution files')
    refs = [tone.evidence.ref(root, path) for path in required]
    assigned = rec.setdefault('assigned', dict(rec.get('masters', {}), fit_checker=rec.get('fit_checker'),
                                               task_checker=rec.get('task_checker')))
    assignee = cmd.get('assignee') or (delivery or {}).get('executor') or (delivery or {}).get('owner')
    if assignee:
        instance = pm.integrity.records(db, 'instance').get(assignee, {})
        pm.require(instance and instance.get('active', True), 'fallback assignee must be a registered active instance')
        pm.require(assignee not in {assigned.get('fit_checker'), assigned.get('task_checker')},
                   'gap delivery cannot make a producer its own checker')
        assigned[role] = assignee
        if role == 'product':
            rec['producer'] = assignee
    if role == 'product':
        pm.require(assigned.get('product'), 'name the registered assignee who will compose the product fallback')
    resolution = dict(gap=gap['id'], gap_revision=gap['revision'], decision=gap['decision'],
                      task_id=(delivery or {}).get('id'), artifacts=refs, admitted_inputs=adopted, adopted_at=pm.now())
    prior = rec.setdefault('gap_resolutions', {}).get(role)
    if prior:
        rec.setdefault('gap_resolution_history', []).append(dict(role=role, resolution=prior))
    rec['gap_resolutions'][role] = resolution
    if role in rec['missing_roles']:
        rec['missing_roles'].remove(role)
    rec['pending_contributions'] = [s for s in rec['pending_contributions'] if s not in suffixes]
    rec['admitted_inputs'] = list(dict.fromkeys(rec.get('admitted_inputs', []) + adopted))
    if delivery and delivery['id'] not in rec['tasks']:
        rec['tasks'].append(delivery['id'])
    pm.integrity.save(pm, db, 'direction_sample', rec)
    available = {suffix for suffix, _, _, _, _ in TASKS
                 if suffix not in rec['pending_contributions'] or rec['id'] + '-' + suffix in tasks}
    for suffix, profession, title, deps, output in TASKS:
        if suffix not in rec['pending_contributions'] or not assigned.get(profession) or not set(deps) <= available:
            continue
        dependencies = []
        for dep in deps:
            tid = rec['id'] + '-' + dep
            if tid in tasks:
                dependencies.append(tid)
            else:
                dep_role = next(r for s, r, _, _, _ in TASKS if s == dep)
                tid = rec.get('gap_resolutions', {}).get(dep_role, {}).get('task_id')
                if tid:
                    dependencies.append(tid)
        task = dict(id=rec['id']+'-'+suffix, title=title, owner=assigned[profession], executor=assigned[profession],
                    checker=assigned['task_checker'], goal=title, next_action=title,
                    inputs=[rec['outputs'][dep] for dep in deps], outputs=[output],
                    admitted_inputs=rec['admitted_inputs'], criteria=['按原方向范围交回并提供证据'], dependencies=dependencies,
                    stage=rec['id'])
        if suffix == 'compose':
            task['inputs'].append(rec.get('preview', PREVIEW_OUTPUT))
            task['outputs'].append(PROFILE_OUTPUT)
        if suffix == 'fit':
            task['inputs'].append(PROFILE_OUTPUT)
            task['project_level'] = False
        admissions = pm.integrity.records(db, 'input_admission')
        task['admitted_inputs'] = [aid for aid in rec['admitted_inputs']
                                   if admissions.get(aid, {}).get('path') in task['inputs']]
        rec['tasks'].append(task['id'])
        pm.integrity.save(pm, db, 'direction_sample', rec)
        pm.execute(root, dict(op='create', actor=cfg['pm_actor'], event_id=cmd['event_id']+':'+suffix, task=task), _db=db)
        rec['pending_contributions'].remove(suffix)
        tasks = pm.task_map(db)
        available.add(suffix)
    pm.integrity.save(pm, db, 'direction_sample', rec)
    milestone = pm.task_map(db)[rec['id']]
    dependencies = [rec['id']+'-fit'] if rec['id']+'-fit' in tasks else list(rec['tasks'])
    pm.execute(root, dict(op='update', actor=cfg['pm_actor'], event_id=cmd['event_id']+':dependencies',
               task_id=rec['id'], expected_revision=milestone['revision'], changes={'dependencies':dependencies},
               reason='采用已决定且交回的专业缺口成果'), _db=db)
    return {'direction_sample':rec}


def confirm_milestone(pm, root, db, task):
    rec = pm.integrity.records(db, 'direction_sample').get(task['id'])
    if not rec:
        return
    pm.require(not rec.get('missing_roles') and not rec.get('pending_contributions'),
               'direction still needs the missing professional conclusions; resolve the recorded expertise gaps')
    tone = pm.admission.load_gate().tone
    for resolution in rec.get('gap_resolutions', {}).values():
        gap = pm.integrity.records(db, 'gap').get(resolution['gap'])
        pm.require(gap and gap['revision'] == resolution['gap_revision']
                   and gap.get('decision') == resolution['decision'] and gap['status'] in {'self', 'closed'},
                   'direction gap choice changed; review and adopt the current contribution again')
        for artifact in resolution['artifacts']:
            tone.evidence.verify_ref(root, artifact)
    current = tone.validate(root, tone.DEFAULT_PATH, require_closed=False)
    pm.require(current['profile'] == rec['profile'] and current['parts']['practice_profile']['path'] == rec['practice_profile'],
               'the direction contract must include the registered project practice profile')
    pm.require(current['parts']['preview']['path'] == rec.get('preview', PREVIEW_OUTPUT),
               'the direction contract must include the assigned preview')
    for part in ('brief', 'scene', 'samples', 'feasibility', 'acceptance'):
        pm.require(current['parts'].get(part, {}).get('path') == rec['outputs'][part],
                   'include the assigned professional direction contribution: ' + part)
    current_profile = tone.profile(root, current)
    if rec.get('example') is not None:
        pm.require(any((row.get('example') or {}).get('id') == rec['example'] for row in current_profile['scopes']),
                   'retain the adopted example and explain changes in the project profile')
    for role, iid in rec['masters'].items():
        pm.admission.master(pm, root, db, iid, role)
    pm.require(rec.get('reviewed_direction') == tone.direction_binding(tone.DEFAULT_PATH, current),
               'confirmed direction differs from the reviewed draft')
    fit = tone.direction_review(root, current, rec['outputs']['fit'])
    approved = task.get('human_review') or {}
    expected_checker = approved.get('person') if fit['mode']=='human' else rec['fit_checker']
    pm.require(fit['checker'] == expected_checker and fit['producer'] == rec['producer'],
               'use the assigned fit checker or the documented human viewport review')
    pm.require(approved.get('person') == current['confirmation']['person']
               and approved.get('quote') == current['confirmation']['quote']
               and approved.get('source') == current['confirmation']['source'],
               'direction contract confirmation must match the combined human review')
    pm.require(current['confirmation'].get('review_receipt') == rec.get('confirmation_receipt'), 'direction confirmation must cite its trusted displayed-request receipt')
    rec.update(closed=True, closed_at=pm.now())
    pm.integrity.save(pm, db, 'direction_sample', rec)


def record_confirmation(pm, root, db, task, cmd):
    rec = pm.integrity.records(db, 'direction_sample').get(task['id'])
    if cmd['outcome'] != 'approved':
        return
    if not rec:
        if not cmd.get('attention_id'):
            return
        attention = pm.integrity.records(db, 'human_attention').get(cmd['attention_id'])
        pm.require(attention and attention.get('task_id') == task['id'],
                   'human review requires the displayed request for this task')
        pm.require(attention.get('kind')=='confirmation', 'approval requires a confirmation request; clarification or correction is not approval')
        pm.require(cmd['presented_ref'] == attention['display'] and cmd['source'] == attention.get('response'),
                   'human review must consume the same displayed material and response source')
        checked=check_asset_attention(pm,root,task,attention['display'],attention.get('stage_state'),allow_unmet=False)
        pm.require(not checked or attention.get('review_purpose')=='stage_review', 'D-4 stage approval must consume an explicit stage_review request')
        return bind_attention(pm, root, db, cmd['attention_id'], person=cmd.get('person'),
                              quote=cmd['quote'], scope=cmd['scope'], expected={'task_id': task['id']})
    tone = pm.admission.load_gate().tone
    draft = tone.validate(root, rec['outputs']['compose'], confirmed=False, _pending_human=True)
    binding = tone.direction_binding(tone.DEFAULT_PATH, draft)
    pm.require(draft['parts']['preview']['path'] == rec.get('preview', PREVIEW_OUTPUT),
               'the direction draft must include the assigned preview')
    attention_id = cmd.get('attention_id')
    attention = pm.integrity.records(db, 'human_attention').get(attention_id)
    pm.require(attention and attention.get('task_id') == task['id'] and attention.get('seconds') is not None,
               'direction confirmation requires the answered displayed request for this milestone')
    pm.require(attention['context'].get('direction_sha256') == binding['direction_sha256'],
               'direction changed after its display; show the new draft before approval')
    pm.require(cmd['presented_ref'] == attention['display'] and cmd['scope'] == attention.get('scope')
               and cmd['source'] == attention['response'] and cmd['quote'].strip() == attention['response_message'],
               'human review must consume the same full display, scope and complete response')
    receipt = bind_attention(pm, root, db, attention_id, person=cmd.get('person'), quote=cmd['quote'],
                             scope=cmd['scope'], expected={'direction_sha256':binding['direction_sha256'], 'task_id':task['id']})
    required = [draft['parts'][key] for key in ('scene', 'preview', 'samples', 'practice_profile')]
    fit = tone.check_fit(root, rec['outputs']['fit'], required, binding, pre_confirmation=True,
                         human_review_receipt=receipt, authority_db=db)
    checker = cmd.get('person') if fit['mode'] == 'human' else rec['fit_checker']
    pm.require(fit['checker'] == checker and fit['producer'] == rec['producer'],
               'direction fit review must use the assigned checker or the person who viewed the rendered scene')
    old = rec.get('confirmation_receipt')
    if old and old != receipt:
        pm.require(task['state'] != 'done', 'reopen the milestone before a new direction review')
        previous_attention = rec.get('confirmation_attention_id')
        pm.require(attention_id != previous_attention, 'a changed direction needs a newly displayed request and new response')
        rec.setdefault('confirmation_history', []).append(dict(receipt=old,
            direction=rec.get('reviewed_direction'), attention_id=previous_attention, replaced_at=pm.now()))
    rec.update(reviewed_direction=binding, confirmation_receipt=receipt,
               confirmation_attention_id=attention_id, closed=False)
    pm.integrity.save(pm, db, 'direction_sample', rec)
    return receipt


def stage_confirmation(pm, root, db, cfg, cmd):
    """Bind an answered stage request through the public PM API, without a new review."""
    pm.require(cmd['actor'] in {cfg['pm_actor'], cfg.get('frontdesk_actor')} - {None},
               'PM or front desk binds the actual stage confirmation')
    gate = pm.admission.load_gate()
    pm.require(pm.nonempty(cmd.get('state')) and pm.local(root,cmd['state']).is_file(), 'stage_confirmation needs state: the existing stage-state JSON path')
    state = json.loads(pm.local(root, cmd['state']).read_text(encoding='utf-8'))
    request = json.loads(gate.checked_file(root, state['request']).read_text())
    reply = json.loads(gate.checked_file(root, state['response']).read_text())
    pm.require(state.get('current') in gate.REVIEW.get(state.get('role'), set()), 'use a registered human-review stage')
    digest = gate.artifact_digest(root, state['artifacts'])
    pm.require(request.get('role') == state['role'] and request.get('stage') == state['current']
               and request.get('scope') == state['scope'] and request.get('artifact_sha256') == digest,
               'stage request does not cover the current artifacts and scope')
    pm.require(reply.get('actor') in {'user', 'person'} and reply.get('choice') == 'confirm'
               and reply.get('request_id') == request.get('request_id') and reply.get('scope') == state['scope']
               and reply.get('artifact_sha256') == digest, 'stage reply does not confirm the displayed scope')
    attention = pm.integrity.records(db, 'human_attention').get(cmd.get('attention_id'))
    pm.require(attention and attention.get('display') == request.get('display_evidence')
               and attention.get('displayed_sha256') == request.get('display_sha256')
               and reply.get('display_sha256') == request.get('display_sha256')
               and attention.get('response') == reply.get('source'), 'use the actual answered stage display and response')
    person = gate.deciding_person(root, state['role'], reply) or cmd.get('person') or 'user'
    if state.get('role')=='design' and state.get('current')=='D-4':
        task=pm.task_map(db).get(attention.get('task_id'))
        pm.require(task, 'D-4 stage approval needs the assigned task_id on human_attention')
        checked=check_asset_attention(pm,root,task,attention['display'],cmd['state'],allow_unmet=False)
        pm.require(not checked or attention.get('review_purpose')=='stage_review', 'D-4 stage approval must consume an explicit stage_review request')
    receipt = bind_attention(pm, root, db, cmd['attention_id'], person=person,
                             quote=reply['quote'], scope=state['scope'],
                             expected={'artifacts': state['artifacts']})
    return {'review_receipt': receipt, 'state': cmd['state'], 'role': state['role'], 'stage': state['current']}


def check_asset_attention(pm,root,task,display,state_path=None,*,allow_unmet=False):
    stage=task.get('practice_stage') or {}
    explicit_state=state_path is not None
    state_path=state_path or task.get('practice_completion')
    state=None
    if state_path:
        if not explicit_state and not (stage.get('role')=='design' and stage.get('current')=='D-4') and not pm.local(root,state_path).is_file():return
        pm.require(pm.nonempty(state_path) and pm.local(root,state_path).is_file(),
                   'asset review requires stage_state: an existing D-4 JSON with practice_evidence and asset_comparison_receipts')
        try:state=json.loads(pm.local(root,state_path).read_text())
        except (ValueError,OSError) as error:
            raise pm.TaskError('asset review stage_state must be a readable JSON object: '+str(state_path)) from error
        pm.require(isinstance(state,dict),'asset review stage_state must be a JSON object')
    if not any(row.get('role')=='design' and row.get('current')=='D-4' for row in (state or {},stage)):return
    pm.require(stage.get('role')=='design' and stage.get('current')=='D-4',
               'D-4 stage approval needs the assigned D-4 task, not another or unregistered stage')
    pm.require(not stage.get('practice_scope') or set(stage['practice_scope'])==set(stage.get('scope',[])),
               'D-4 practice_scope must match the assigned scope')
    if state is not None:
        pm.require(all(state.get(key)==stage.get(key) for key in ('role','current','scope','tone_contract')),
                   'asset review state differs from the assigned D-4 scope')
    tone=pm.admission.load_gate().tone
    data=tone.confirmed_contract(root,stage.get('tone_contract'),registry_root=root)
    if not any('asset_anchors' in row for row in tone.practice.active(tone.profile(root,data),['asset_anchors'],stage.get('practice_scope') or stage.get('scope')).values()):return
    pm.require(state is not None,
               'asset review requires stage_state: an existing D-4 JSON with practice_evidence and asset_comparison_receipts')
    tone.check_asset_submission(root,state,display,allow_unmet=allow_unmet)
    return True


def bind_attention(pm, root, db, attention_id, *, person, quote, scope, expected):
    attention = pm.integrity.records(db, 'human_attention').get(attention_id)
    pm.require(attention, 'approval requires an existing answered human_attention; record the actual display and reply first')
    pm.require(attention.get('kind') == 'confirmation',
               'approval requires a confirmation request; clarification or correction is not approval')
    pm.require(attention and attention.get('seconds') is not None and attention.get('scope') == scope,
               'approval requires the answered displayed request and scope')
    def same(key,value):
        actual=attention['context'].get(key)
        if key=='artifacts' and isinstance(actual,list) and isinstance(value,list):
            return sorted(actual,key=lambda row:(row['path'],row['sha256']))==sorted(value,key=lambda row:(row['path'],row['sha256']))
        return actual==value
    pm.require(attention.get('response_message') == quote.strip() and all(same(k,v) for k,v in expected.items()),
               'approval differs from the complete response or displayed content version')
    evidence = pm.admission.load_gate().tone.evidence
    display_root, _ = evidence.verify_bundle(root, attention['display_bundle'])
    response_root, _ = evidence.verify_bundle(root, attention['response_bundle'])
    binding = dict(attention['context'], format='matrix-review-binding/1',
        display=evidence.ref(display_root, attention['display']),
        response=dict(evidence.ref(response_root, attention['response']), response_id=attention.get('response_id'),
                      message_sha256=evidence.digest(quote.strip())),
        person=person or 'user', quote=quote.strip(), outcome='approved', actor='user')
    evidence.check_review_binding(binding)
    staging = 'management/review-sources/' + attention_id
    for snapshot, source in ((display_root, attention['display']), (response_root, attention['response'])):
        target = pm.local(root, staging + '/' + source)
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = evidence.file(snapshot, source).read_bytes()
        pm.require(not target.exists() or target.read_bytes() == payload, 'review receipt sources are immutable')
        target.write_bytes(payload)
    receipt = evidence.review_receipt(pm.local(root, staging), binding)
    receipt['path'] = staging + '/' + receipt['path']
    receipts = attention.setdefault('review_receipts', [])
    if receipt not in receipts:
        receipts.append(receipt)
        pm.integrity.save(pm, db, 'human_attention', attention)
    return receipt
