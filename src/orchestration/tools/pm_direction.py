"""Direction sample and the recorded cost of requesting human attention."""

from datetime import datetime
import re


READ_OPS = {'human_attention_status'}
WRITE_OPS = {'direction_sample', 'human_attention'}
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
        inputs = cmd.get('inputs', [])
        pm.require(pm.strings(inputs), 'attention inputs must be project files')
        refs = [evidence.ref(root, source), *[evidence.ref(root, name) for name in inputs]]
        context = dict(task_id=task_id, scope=cmd.get('scope'), request_id=cmd['id'])
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
        elapsed = (datetime.fromisoformat(at) - datetime.fromisoformat(rec['opened_at'])).total_seconds()
        message = evidence.response_message(root, cmd['response'], cmd.get('response_id'))
        pm.require(message, 'complete response message is empty')
        identity = {'response_id':cmd.get('response_id'), 'message_sha256':evidence.digest(message)}
        def reused(other):
            old=other.get('response_identity') or {}
            return (old.get('response_id') == identity['response_id'] if identity['response_id'] is not None
                    else old.get('response_id') is None and old.get('message_sha256') == identity['message_sha256'])
        pm.require(not any(reused(other) and other['id'] != rec['id'] for other in records.values()),
                   'this response message is already bound to another displayed request; use its actual stable message id for a distinct reply')
        source_ref = evidence.ref(root, cmd['response'])
        rec.update(response=cmd['response'], response_id=cmd.get('response_id'), response_identity=identity,
                   response_message=message, response_bundle=evidence.seal_bundle(root, [source_ref], identity),
                   response_ref=source_ref, answered_at=at, seconds=max(0, int(elapsed)))
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
    assigned.setdefault('task_checker',cfg['pm_actor'])
    if not assigned.get('fit_checker'):missing_roles.append('fit_checker')
    assigned.setdefault('fit_checker',None)
    pm.require(not producers & {assigned['fit_checker'],assigned['task_checker']} and assigned['fit_checker'] != assigned['task_checker'],
               'direction and task checkers must be independent of the producers and each other')
    pm.require(not assigned['fit_checker'] or instances.get(assigned['fit_checker'], {}).get('active'), 'active direction fit checker required')
    pm.require(assigned['task_checker'] == cfg['pm_actor'] or instances.get(assigned['task_checker'], {}).get('active'),
               'active task checker or PM required')
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
               brief=brief_path, outputs=output_by_id, practice_profile=PROFILE_OUTPUT, preview=PREVIEW_OUTPUT,
               reserved_roles=['art-production'], fit_checker=assigned['fit_checker'],
               producer=assigned.get('product'), masters={role: assigned[role] for role in PRODUCERS if assigned.get(role)},
               missing_roles=missing_roles, pending_contributions=[suffix for suffix in output_by_id if suffix not in available])
    pm.integrity.save(pm, db, 'direction_sample', rec)
    # Register works first, then create their parent milestone and bind each row to it
    # in the same transaction. A failed child rolls back the whole operation.
    for suffix, role, title, deps, output in TASKS:
        if suffix not in available:continue
        task = dict(id=key+'-'+suffix, title=title, owner=assigned[role], executor=assigned[role],
                    checker=assigned['task_checker'], goal=title, next_action=title,
                    inputs=[output_by_id[d] for d in deps] or [brief_path], outputs=[output],
                    criteria=['按方向样张确认范围交回并提供证据'], dependencies=[key+'-'+d for d in deps])
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
                     next_action='向决定人合并展示做法档、样张与 P-1 结论', inputs=[brief_path]+([PROFILE_OUTPUT,output_by_id['fit']] if 'fit' in available else []),
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


def confirm_milestone(pm, root, db, task):
    rec = pm.integrity.records(db, 'direction_sample').get(task['id'])
    if not rec:
        return
    pm.require(not rec.get('missing_roles') and not rec.get('pending_contributions'),
               'direction still needs the missing professional conclusions; resolve the recorded expertise gaps')
    tone = pm.admission.load_gate().tone
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
    if not rec or cmd['outcome'] != 'approved':
        return
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
                         human_review_receipt=receipt)
    checker = cmd.get('person') if fit['mode'] == 'human' else rec['fit_checker']
    pm.require(fit['checker'] == checker and fit['producer'] == rec['producer'],
               'direction fit review must use the assigned checker or the person who viewed the rendered scene')
    old = rec.get('confirmation_receipt')
    pm.require(not old or old == receipt, 'a response cannot be rebound to a new direction')
    rec.update(reviewed_direction=binding, confirmation_receipt=receipt, closed=False)
    pm.integrity.save(pm, db, 'direction_sample', rec)
    return receipt


def bind_attention(pm, root, db, attention_id, *, person, quote, scope, expected):
    attention = pm.integrity.records(db, 'human_attention').get(attention_id)
    pm.require(attention and attention.get('seconds') is not None and attention.get('scope') == scope,
               'approval requires the answered displayed request and scope')
    pm.require(attention.get('response_message') == quote.strip() and all(attention['context'].get(k) == v for k,v in expected.items()),
               'approval differs from the complete response or displayed content version')
    evidence = pm.admission.load_gate().tone.evidence
    display_root, _ = evidence.verify_bundle(root, attention['display_bundle'])
    response_root, _ = evidence.verify_bundle(root, attention['response_bundle'])
    binding = dict(attention['context'], format='matrix-review-binding/1',
        display=evidence.ref(display_root, attention['display']),
        response=dict(evidence.ref(response_root, attention['response']), response_id=attention.get('response_id'),
                      message_sha256=evidence.digest(quote.strip())),
        person=person, quote=quote.strip(), outcome='approved', actor='user')
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
    return receipt
