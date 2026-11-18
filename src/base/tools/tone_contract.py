#!/usr/bin/env python3
"""Validate a direction sample, its approved tone contract and review evidence."""

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sqlite3

DEFAULT_PATH = 'product/specs/00-方向样张.md'
_spec = importlib.util.spec_from_file_location('practice_profiles', Path(__file__).with_name('practice_profiles.py'))
practice = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(practice)
_spec = importlib.util.spec_from_file_location('review_evidence', Path(__file__).with_name('review_evidence.py'))
evidence = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(evidence)


def require(ok, message):
    if not ok:
        raise ValueError(message)


def text(value):
    return isinstance(value, str) and bool(value.strip())


def file(root, name):
    if name==DEFAULT_PATH and not (Path(root)/name).is_file():
        raise ValueError('confirmed direction is missing; return to P-1 direction sample before this stage')
    return evidence.file(root, name)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def verify_ref(root, ref):
    return evidence.verify_ref(root, ref)


def picture(path):
    try:
        evidence.png_dimensions(path)
        return True
    except (ValueError, OSError):
        return False


def viewport(value):
    match = re.fullmatch(r'([1-9][0-9]*)\s*[x×]\s*([1-9][0-9]*)', str(value).strip(), flags=re.I)
    require(match, 'record a numeric viewport')
    return tuple(int(x) for x in match.groups())


def check_confirmation(root, data, *, require_closed=True, registry_root=None, authority_db=None):
    approval = data.get('confirmation', {})
    require(isinstance(approval, dict) and all(text(approval.get(k)) for k in ('person', 'quote', 'source')),
            'record confirmer, exact quote and response source')
    expected = direction_binding(DEFAULT_PATH, data)['direction_sha256']
    require(approval.get('direction_sha256') == expected, 'confirmation direction_sha256 is missing or changed; return to P-1')
    authority_root = Path(registry_root or root).resolve()
    view, manifest = evidence.verify_bundle(authority_root, approval.get('review_receipt'))
    binding = evidence.check_review_binding(manifest['context'], direction_sha256=expected,
                                             person=approval['person'], quote=approval['quote'])
    check_direction_scope(root, data, binding.get('scope'))
    if (authority_root/'management/runtime/tasks.sqlite3').is_file():
        evidence.verify_human_receipt(authority_root,approval['review_receipt'],direction_sha256=expected,authority_db=authority_db)
    else:
        evidence.verify_response_registration(authority_root,binding)
    people = authority_root / 'management/people.json'
    if people.is_file():
        roster = {row['id']:row for row in json.loads(file(authority_root, 'management/people.json').read_text(encoding='utf-8')).get('people', [])}
        require(binding['person'] in roster and set(roster[binding['person']].get('decides', [])) & {'product','project'},
                'P-1 confirmer must be a listed product/project deciding person')
    else:
        require(binding.get('actor') == 'user', 'single-conversation P-1 requires the actual user response path')
    require(binding['response']['path'] == approval['source'], 'confirmation response source differs from displayed review')
    require(evidence.response_message(view, approval['source'], binding['response'].get('response_id')) == approval['quote'].strip(),
            'confirmation quote missing from complete response message')
    # A PM project must have closed its own milestone; a self-authored contract is insufficient.
    database = authority_root / 'management/runtime/tasks.sqlite3'
    if require_closed and database.is_file():
        with evidence.authority_connection(authority_root,authority_db) as db:
            records = [json.loads(row[0]) for row in db.execute("SELECT data FROM pm_records WHERE kind='direction_sample'")]
            matching = [rec for rec in records if rec.get('reviewed_direction', {}).get('direction_sha256') == expected]
            require(any(rec.get('closed') and rec.get('confirmation_receipt') == approval['review_receipt'] for rec in matching),
                    'P-1 direction milestone is not closed with this confirmation receipt')
    return binding


def read(root, ref):
    source = file(root, ref).read_text(encoding='utf-8')
    parts = re.findall(r'^\x60\x60\x60tone-contract\s*\n(.*?)^\x60\x60\x60\s*$', source, flags=re.M | re.S)
    require(len(parts) == 1, 'one tone-contract JSON block required')
    data = json.loads(parts[0])
    require(isinstance(data, dict), 'tone contract must be an object')
    return data


def profile(root, data):
    ref = data.get('parts', {}).get('practice_profile')
    path = verify_ref(root, ref)
    result = practice.validate(json.loads(path.read_text(encoding='utf-8')), lambda value: verify_ref(root, value))
    require(result['version'] == ref.get('version'), 'practice profile version differs from its contract reference')
    return result


def check_direction_scope(root, data, scope):
    expected = [row['id'] for row in profile(root, data)['scopes']]
    require(isinstance(scope, list) and len(scope) == len(expected)
            and all(isinstance(value, str) for value in scope) and set(scope) == set(expected),
            'P-1 confirmation must cover all activity scopes exactly; correct the binding before retrying')
    return sorted(expected)


def check_preview(root, ref):
    path = verify_ref(root, ref)
    content = path.read_text(encoding='utf-8')
    if path.suffix.lower() == '.svg':
        rendered_source = re.search(r'<svg(?:\s|>)', content, flags=re.I)
    else:
        rendered_source = path.suffix.lower() in {'.html', '.htm'} and re.search(r'<[a-z][\w-]*(?:\s|>)', content, flags=re.I)
    require(rendered_source, 'actual HTML or SVG direction preview required')
    visible = re.sub(r'<(?:script|style)\b[^>]*>.*?</(?:script|style)>', '', content, flags=re.I|re.S)
    visible = re.sub(r'<[^>]*>', '', visible).strip()
    require(not re.fullmatch(r'(?:TODO|TBD|pending|待制作|待补|稍后补充)[.。 ]*',visible,re.I),
            'direction preview is an explicit placeholder, not a rendered direction')


def validate_references(root, rows, parts):
    from urllib.parse import urlparse
    own={Path(value['path']).as_posix() for value in parts.values() if isinstance(value,dict) and text(value.get('path'))}
    own_hashes={evidence.ref(root,name)['sha256'] for name in own if (Path(root)/name).is_file()}
    sources=set()
    for row in rows:
        source=row['source'].strip();parsed=urlparse(source)
        if parsed.scheme in {'http','https'}:
            require(bool(parsed.netloc) and not parsed.username and not parsed.password and parsed.hostname not in {'localhost','127.0.0.1','::1'},'locatable external reference required')
            require(not re.search(r'/(?:matrix|\.agents|\.claude)/|/Matrix-AI/(?:blob|tree)/[^/]+/src/',parsed.path,re.I),'package methods/examples are not external activity references')
        elif parsed.scheme=='system':require(bool(parsed.path.strip('/')),'existing system reference needs a locator')
        else:
            require(not parsed.scheme and Path(source).as_posix() not in own and source!=DEFAULT_PATH
                    and not source.startswith(('matrix/','.agents/','.claude/','product/specs/')),
                    'the current project, user request or package is not an external reference')
            require(evidence.ref(root,source)['sha256'] not in own_hashes,'current project materials cannot be copied into external references')
        identity=(parsed.netloc.lower(),parsed.path.rstrip('/'),parsed.query) if parsed.scheme in {'http','https'} else Path(source).as_posix()
        require(identity not in sources,'use at least two distinct external reference sources');sources.add(identity)


def validate(root, ref, *, confirmed=True, require_closed=True, registry_root=None, _pending_human=False):
    root = Path(root).resolve()
    data = read(root, ref)
    require(all(text(data.get(k)) for k in ('version', 'genre', 'profile', 'tone', 'core_loop')),
            'version, genre, profile, tone and core_loop required')
    examples = data.get('references', [])
    require(isinstance(examples, list) and 2 <= len(examples) <= 3 and all(
        isinstance(x, dict) and all(text(x.get(k)) for k in ('name', 'source', 'borrows', 'observed')) for x in examples),
        'two to three references with source, borrowed detail and observation status required')
    require(len({x['name'].strip().casefold() for x in examples}) == len(examples), 'reference names must be distinct')
    validate_references(root,examples,data.get('parts',{}))
    avoid = data.get('avoid', [])
    require(isinstance(avoid, list) and avoid and all(text(x) for x in avoid), 'at least one direction to avoid required')
    parts = data.get('parts', {})
    require(isinstance(parts, dict) and {'brief', 'scene', 'preview', 'samples', 'practice_profile'} <= parts.keys(),
            'brief, scene, preview, samples and practice_profile parts required')
    for part in parts.values():
        require(isinstance(part, dict) and text(part.get('version')), 'each part requires a version')
        verify_ref(root, part)
    check_preview(root, parts['preview'])
    sample_file = verify_ref(root, parts['samples'])
    require(text(sample_file.read_text(encoding='utf-8')), 'direction samples file is empty')
    viewport(data.get('viewport'))
    check_capture(root, parts, data.get('capture_unavailable'), viewport_value=data['viewport'],
                  capture_binding=data.get('capture_binding'), artifacts=[parts['preview']], registry_root=registry_root,
                  human_review_receipt=data.get('human_review_receipt') or data.get('confirmation',{}).get('review_receipt'),
                  pending_human=_pending_human)
    current = profile(root, data)
    motion = any(row['features'][name]['value'] in {'yes','pending'} for row in current['scopes'] for name in practice.MOTION)
    if motion:
        samples = data.get('samples', [])
        require(isinstance(samples, list) and all(isinstance(x, dict) and all(text(x.get(k)) for k in
                ('moment', 'text', 'consequence')) for x in samples), 'samples must name a moment, text and consequence')
        require(len({x['text'].strip() for x in samples}) >= 6 and len({x['moment'].strip() for x in samples}) >= 4,
                'interactive timing requires six distinct samples across four moments')
    if confirmed:
        check_confirmation(root, data, require_closed=require_closed, registry_root=registry_root)
    return data


def check_capture(root, record, unavailable, *, viewport_value=None, capture_binding=None, artifacts=None, registry_root=None, human_review_receipt=None, pending_human=False, authority_db=None):
    if 'screenshot' in record:
        path = verify_ref(root, record['screenshot'])
        require(picture(path), 'actual rendered screenshot required (decodable PNG)')
        dimensions = evidence.png_dimensions(path)
        binding = capture_binding or record.get('capture_binding')
        require(isinstance(binding, dict), 'actual screenshot needs a capture binding to its current preview/artifacts')
        css = viewport(viewport_value or record.get('viewport'))
        scale = binding.get('scale', 1)
        require(isinstance(scale, (int, float)) and not isinstance(scale, bool) and scale >= 1
                and dimensions == tuple(round(size * scale) for size in css), 'screenshot pixel dimensions differ from viewport and scale')
        require(binding.get('pixel_size') == list(dimensions) and viewport(binding.get('viewport')) == css
                and all(text(binding.get(key)) for key in ('method', 'state', 'source')), 'record capture pixel size, viewport, method, state and source')
        expected = {(row['path'], row['sha256']) for row in (artifacts or record.get('artifacts', []))}
        actual = {(row.get('path'), row.get('sha256')) for row in binding.get('artifacts', []) if isinstance(row, dict)}
        require(expected and actual == expected, 'screenshot capture does not bind the current artifacts')
        provenance = json.loads(verify_ref(root, binding.get('receipt')).read_text(encoding='utf-8'))
        require(provenance == {**{key:value for key,value in binding.items() if key != 'receipt'},
                               'screenshot_sha256':record['screenshot']['sha256']},
                'screenshot differs from its actual capture receipt or captured source closure; differing fields: '+', '.join(sorted(key for key in set(provenance)|set(binding) if key != 'receipt' and provenance.get(key)!=binding.get(key))))
        for item in binding['artifacts']:
            verify_ref(root, item)
    else:
        require(text(unavailable), 'actual screenshot or recorded human viewport review with capture limitation required')
        observed = verify_ref(root, record.get('manual_review'))
        require(text(observed.read_text(encoding='utf-8')), 'record the actually displayed viewport before asking for review')
        if pending_human and human_review_receipt is None and record.get('human_review_receipt') is None:
            return  # Display registration only; no passed delivery or human inspection is claimed.
        check_human_review(root,record,artifacts or record.get('artifacts',[]),
                           human_review_receipt or record.get('human_review_receipt'),registry_root,authority_db=authority_db)


def check_human_review(root, record, artifacts, receipt, registry_root=None, *, authority_db=None):
    require(isinstance(receipt,dict), 'human viewport inspection requires the actual human response receipt')
    authority = Path(registry_root or root).resolve()
    binding = evidence.verify_human_receipt(authority, receipt, artifacts=artifacts, authority_db=authority_db)
    evidence.check_review_binding(binding,person=record.get('checker'))
    people = authority / 'management/people.json'
    if people.is_file():
        roster = {row['id']: row for row in json.loads(file(authority, 'management/people.json').read_text()).get('people', [])}
        require(binding['person'] in roster and roster[binding['person']].get('decides'), 'human viewport reviewer must be a listed deciding person')
    else:
        require(binding.get('actor') == 'user', 'single-conversation human viewport review requires the user response path')
    required = {(row['path'], row['sha256']) for row in artifacts}
    shown = {(row.get('path'), row.get('sha256')) for row in binding.get('artifacts', [])}
    require(required and required <= shown, 'human viewport review does not cover current artifacts')


def direction_binding(ref, data):
    content = {name: value for name, value in data.items() if name != 'confirmation'}
    return {'path': ref, 'version': data['version'], 'direction_sha256': practice.digest(content)}


def direction_delivery(data):
    """Project the validated draft into a receipt for the user-facing handoff."""
    parts = data['parts']
    preview = parts['preview']
    kind = 'screenshot' if 'screenshot' in parts else 'human'
    capture = parts['screenshot' if kind == 'screenshot' else 'manual_review']
    return {
        'format': 'direction-delivery/1',
        'direction_reference': direction_binding(DEFAULT_PATH, data),
        'artifacts': [{'part': name, **{key: ref[key] for key in ('path', 'version', 'sha256')}}
                      for name, ref in sorted(parts.items())],
        'preview': {key: preview[key] for key in ('path', 'sha256')},
        'capture': {'kind': kind, 'path': capture['path'], 'sha256': capture['sha256'],
                    'limitation': data.get('capture_unavailable') if kind == 'human' else None},
        'status': 'draft_pending_confirmation',
    }


def handed_path(root, authority, instance, name, expected):
    """Translate only the real isolated public prefix; never match arbitrary same-byte aliases."""
    root=Path(root).resolve();authority=Path(authority).resolve()
    prefix=Path('management/instances')/instance/'workspace/public'
    if root == (authority/prefix).resolve():return (prefix/name).as_posix()
    manifest=root.parent/'manifest.json'
    if root!=authority and manifest.is_file():
        context=json.loads(evidence.file(root.parent,'manifest.json').read_text()).get('context',{})
        if context.get('format')=='matrix-admission-scenario/1':
            source=(prefix/name).as_posix()
            require(any(row.get('logical_path')==name and row.get('source_path')==source and row.get('sha256')==expected
                        for row in context.get('origins',[])), 'isolated handover path has no exact trusted origin: '+name)
            return source
    return name


def check_fit(root, record, artifacts, contract=None, *, pre_confirmation=False, registry_root=None, human_review_receipt=None, historical=False, task_context=None, authority_db=None):
    data = json.loads(file(root, record).read_text(encoding='utf-8'))
    require(isinstance(data, dict) and data.get('outcome') == 'passed' and text(data.get('checker')) and text(data.get('producer')),
            'a passing fit review with named participants is required')
    if contract is not None:
        require(data.get('tone_contract') == contract, 'fit review uses a stale or missing tone contract')
        if pre_confirmation:
            require(data.get('binding_mode') == 'pre_confirmation_direction', 'bind the fit review to the direction before confirmation')
        else:
            require(data.get('binding_mode') != 'pre_confirmation_direction', 'fit review requires the confirmed tone contract')
    mode = data.get('mode')
    require((mode == 'independent' and data['checker'] != data['producer']) or
            (mode == 'same_instance' and data['checker'] == data['producer']) or
            (mode == 'human' and data['checker'] != data['producer']),
            'label independent or same-instance perspective correctly')
    observed = data.get('artifacts', [])
    require(isinstance(observed, list) and observed, 'reviewed artifacts are required')
    for ref in observed:
        verify_ref(root, ref)
    authority = Path(registry_root or root).resolve()
    database = authority / 'management/runtime/tasks.sqlite3'
    instances = {}
    if database.is_file():
        with evidence.authority_connection(authority,authority_db) as db:
            instances = {row['id']: row for row in (json.loads(value[0]) for value in db.execute("SELECT data FROM pm_records WHERE kind='instance'"))}
    if mode == 'same_instance':
        require(not database.is_file() and not (authority / 'management/instance-config.json').is_file()
                and not (authority / 'management/people.json').is_file(), 'same-instance fit is only available in an actual single-conversation project')
    if mode == 'independent':
        require(database.is_file(), 'independent fit requires a trusted project review run; use same_instance only in an actual single conversation')
        eligible={key for key,value in instances.items() if historical or value.get('active',True)}
        require({data['producer'], data['checker']} <= eligible, 'fit producer/checker must be registered; new reviews require active project instances')
        review_task = data.get('review_task')
        with evidence.authority_connection(authority,authority_db) as db:
            row = db.execute('SELECT data FROM tasks WHERE id=?', (review_task,)).fetchone()
        task = json.loads(row[0]) if row else {}
        require(task.get('owner') == data['checker'] or task.get('checker') == data['checker'], 'fit checker must have an assigned project review task')
        actual_producers=set()
        if task_context:
            for item in observed:
                producer=task_context.get('subject_producers',{}).get(item['path']) or task_context.get('producers',{}).get(item['path'])
                handed=dict(task_context.get('handed_files',{}),**task_context.get('review_subjects',{}))
                require(producer in instances and handed.get(item['path'])==item['sha256'],
                        'each reviewed artifact needs its exact task handover and actual producer: '+item['path'])
                actual_producers.add(producer)
        else:
            with evidence.authority_connection(authority,authority_db) as db:
                tasks=[json.loads(row[0]) for row in db.execute('SELECT data FROM tasks')]
                launches=[json.loads(row[0]) for row in db.execute("SELECT data FROM pm_records WHERE kind='launch'")]
                records={(kind,key):json.loads(raw) for kind,key,raw in db.execute('SELECT kind,id,data FROM pm_records')}
            task_index={item['id']:item for item in tasks}
            sources=[(item.get('executor') or item.get('owner'),item.get('handed_output_sha256',{})) for item in tasks]
            gap_sources={}
            if pre_confirmation:
                for (kind,_), direction in records.items():
                    if kind!='direction_sample' or direction.get('outputs',{}).get('fit')!=record:continue
                    for resolution in direction.get('gap_resolutions',{}).values():
                        gap=records.get(('gap',resolution.get('gap')), {})
                        if (gap.get('status')!='closed' or gap.get('revision')!=resolution.get('gap_revision')
                                or gap.get('decision')!=resolution.get('decision') or resolution.get('task_id')):continue
                        admitted=[records.get(('input_admission',key),{}) for key in resolution.get('admitted_inputs',[])]
                        for item in resolution.get('artifacts',[]):
                            if any(row.get('state')=='admitted' and row.get('path')==item['path']
                                   and row.get('sha256')==item['sha256'] for row in admitted):
                                gap_sources[(item['path'],item['sha256'])]='human-gap:'+gap['id']
            for run in launches:
                source_task=task_index.get(run.get('task_id'),{})
                produced=(run.get('handover') or {}).get('files',{})
                if (run.get('purpose')=='start' and run.get('state')=='exited' and run.get('exit_code')==0
                    and run.get('handed') and isinstance(produced,dict)
                    and run.get('instance') in {source_task.get('executor'),source_task.get('owner')}):
                    sources.append((run['instance'],produced))
            for item in observed:
                matched=set()
                human=gap_sources.get((item['path'],item['sha256']))
                if human:matched.add(human)
                for producer,files in sources:
                    if producer not in instances:continue
                    try:name=handed_path(root,authority,producer,item['path'],item['sha256'])
                    except ValueError:continue
                    if files.get(name)==item['sha256']:matched.add(producer)
                require(matched,'each reviewed artifact must match its exact actual task handover path and hash: '+item['path'])
                actual_producers.update(matched)
        require(actual_producers and data['producer'] in actual_producers and data['checker'] not in actual_producers,
                'fit producer must match actual task handover, and its checker must be independent of all producers')
        review = task.get('review') or {}
        handed = task.get('handed_output_sha256', {}) if task.get('owner') == data['checker'] and task.get('state')=='done' else {}
        reviewed = review.get('artifact_sha256', {}) if review.get('checker') == data['checker'] and review.get('outcome') == 'passed' else {}
        if reviewed:
            with evidence.authority_connection(authority,authority_db) as db:
                row=db.execute("SELECT data FROM pm_records WHERE kind='launch' AND id=?",(review.get('run_id'),)).fetchone()
            run=json.loads(row[0]) if row else {}
            require(run.get('purpose')=='check' and run.get('instance')==data['checker'] and run.get('state')=='exited'
                    and run.get('exit_code')==0,'independent fit needs its real successful checker run')
        fit_sha=sha(file(root,record).read_bytes())
        fit_path=handed_path(root,authority,data['checker'],record,fit_sha)
        require(handed.get(fit_path)==fit_sha or reviewed.get(fit_path)==fit_sha,
                'independent fit path and hash must match the actual checker handover or trusted review submission')
    require(mode == 'human' or 'screenshot' in data, 'actual rendered screenshot required for passed fit review')
    check_capture(root, data, data.get('capture_unavailable'), artifacts=observed, registry_root=registry_root,
                  human_review_receipt=human_review_receipt,authority_db=authority_db)
    if mode == 'human' and 'screenshot' in data:
        check_human_review(root,data,[*observed,data['screenshot']],human_review_receipt or data.get('human_review_receipt'),registry_root,authority_db=authority_db)
    require(text(data.get('viewport')) and text(data.get('capture')), 'record viewport and capture method')
    require(all(text(data.get(k)) for k in ('genre_fit', 'application_drift', 'copy_fit')),
            'record genre fit, application-like details, and copy fit')
    current = {x['path']: x['sha256'] for x in artifacts}
    reviewed = {x['path']: x['sha256'] for x in observed}
    require(current and all(reviewed.get(k) == v for k, v in current.items()),
            'fit review does not cover current artifacts')
    return data


def check_fit_comparison(root, record, direction, schema):
    fields = schema['fields']
    require(all(text(record.get(key)) for key in fields), 'record the reference viewport and representative comparison state')
    current = re.fullmatch(r'([1-9][0-9]*)\s*[x×]\s*([1-9][0-9]*)', record['viewport'].strip(), flags=re.I)
    reference = re.fullmatch(r'([1-9][0-9]*)\s*[x×]\s*([1-9][0-9]*)',
                             record['reference_viewport'].strip(), flags=re.I)
    require(current and reference and current.groups() == reference.groups(),
            'use the same numeric viewport for reviewed and direction views')
    parts = direction['parts']
    if 'screenshot' in parts:
        key = schema['reference'][0]
        part = parts['screenshot']
    else:
        key = schema['reference'][1]
        part = parts['manual_review']
    ref = record.get(key)
    require(isinstance(ref, dict) and all(ref.get(field) == part[field] for field in ('path', 'sha256')),
            'fit comparison must use the current direction reference: ' + key)
    verify_ref(root, ref)
    require(viewport(record['reference_viewport']) == viewport(direction['viewport']), 'reference viewport differs from confirmed direction')


def confirmed_contract(root, ref, *, require_closed=True, registry_root=None):
    require(isinstance(ref, dict) and set(ref) == {'path', 'version', 'sha256'}
            and ref.get('path') == DEFAULT_PATH, 'enter P-1 to confirm the direction sample; reference the current tone contract and its version')
    verify_ref(root, ref)
    result = validate(root, ref['path'], require_closed=require_closed, registry_root=registry_root)
    require(result['version'] == ref.get('version'), 'tone contract version changed')
    return result


def check_contract_scope(old_root, old_ref, current_root, current_ref=None, scope=None, *, registry_root=None):
    """Retain a sealed decision only for activity scopes whose agreed semantics did not change."""
    old=confirmed_contract(old_root,old_ref,require_closed=False,registry_root=registry_root or current_root)
    current_ref=current_ref or dict(evidence.ref(current_root,DEFAULT_PATH),version=read(current_root,DEFAULT_PATH)['version'])
    current=confirmed_contract(current_root,current_ref,registry_root=registry_root or current_root)
    if old_ref==current_ref:return True
    before={row['id']:row for row in profile(old_root,old)['scopes']}
    after={row['id']:row for row in profile(current_root,current)['scopes']}
    selected=scope if scope and all(sid in before for sid in scope) else list(before)
    require(all(sid in before and before[sid]==after.get(sid) for sid in selected), 'confirmed direction changed the reviewed activity scope')
    shared=('tone','core_loop','references','avoid','samples','viewport')
    require(all(old.get(key)==current.get(key) for key in shared), 'shared direction meaning changed; review the affected scopes')
    return True


def compare_capture_source(record, origin):
    if not record.get('screenshot') or not origin.get('screenshot'):return
    if record['screenshot']['sha256']!=origin['screenshot']['sha256']:return
    current=record.get('capture_binding',{});previous=origin.get('capture_binding',{})
    signature=lambda value:({(r['path'],r['sha256']) for r in value.get('artifacts',[])},value.get('state'))
    require(signature(current)==signature(previous), 'reused stage image has a different source or state; capture the actual current artifacts')


def historical_record(authority, record_ref, key, sid, current_root, current_contract):
    record_root,manifest=evidence.verify_bundle(authority,record_ref.get('bundle'))
    context=manifest['context']
    require(context.get('scope')==sid and context.get('requirement')==key and context.get('role') and context.get('stage'),
            'historical evidence needs its producer stage, role and scope')
    _,origin,state=evidence.record_origin(authority,record_ref,key,sid)
    require((origin['context']['role'],origin['context']['stage'])==(context['role'],context['stage']), 'historical record stage differs from its successful origin')
    check_contract_scope(record_root,context['tone_contract'],current_root,current_contract,[sid],registry_root=authority)
    return record_root,context['tone_contract']


def direction_review(root, data, record, *, registry_root=None, historical=False, task_context=None):
    binding = direction_binding(DEFAULT_PATH, data)
    reviewed = [data['parts'][key] for key in ('scene', 'preview', 'samples', 'practice_profile')]
    fit = check_fit(root, record, reviewed, binding, pre_confirmation=True, registry_root=registry_root,
                    human_review_receipt=data.get('confirmation',{}).get('review_receipt'),historical=historical,task_context=task_context)
    require(viewport(fit['viewport'])==viewport(data['viewport']),'direction fit viewport differs from the actual direction')
    if fit['mode'] == 'human':
        require(fit['checker'] == data['confirmation']['person'], 'human viewport reviewer must match the P-1 confirmer')
    return fit


ASSET_PAGE_PLACEHOLDERS = ('待观察', '待判定', '待填写差异和影响', '待填写代表状态', '待填写缺失输入和本轮限制')


def embedded_page(root, page_path, *, recursive=False, visited=None):
    """Read local embedded sources; links and image elements pointing to HTML do not qualify."""
    from html.parser import HTMLParser
    from urllib.parse import urlparse, unquote
    root=Path(root).resolve();page_path=Path(page_path)
    page_path=(root/page_path).resolve() if not page_path.is_absolute() else page_path.resolve()
    visited=set() if visited is None else visited
    if page_path in visited:return set(), ''
    visited.add(page_path)
    class Embedded(HTMLParser):
        def __init__(self):super().__init__();self.paths=set();self.frames=set();self.words=[];self.hidden=0
        def handle_starttag(self,tag,attrs):
            if tag in {'script','style'}:self.hidden+=1
            attrs=dict(attrs)
            name=attrs.get('src') if tag in {'img','iframe','embed'} else attrs.get('data') if tag=='object' else attrs.get('href') or attrs.get('xlink:href') if tag=='image' else None
            if not name:return
            parsed=urlparse(name)
            if parsed.scheme or parsed.netloc:return
            candidate=(page_path.parent/unquote(parsed.path)).resolve()
            if not candidate.is_relative_to(root):return
            if tag in {'img','image'}:
                require(candidate.suffix.lower() in {'.png','.jpg','.jpeg','.svg','.webp','.gif','.avif'},
                        'image element must reference an image file; embed HTML with iframe or object')
            self.paths.add(candidate.relative_to(root).as_posix())
            if tag in {'iframe','object','embed'} and candidate.suffix.lower() in {'.html','.htm'}:self.frames.add(candidate)
        def handle_endtag(self,tag):
            if tag in {'script','style'}:self.hidden=max(0,self.hidden-1)
        def handle_data(self,data):
            if not self.hidden:self.words.append(data)
    parsed=Embedded();parsed.feed(file(root,page_path.relative_to(root).as_posix()).read_text())
    if recursive:
        for frame in parsed.frames:
            paths,_=embedded_page(root,frame,recursive=True,visited=visited);parsed.paths.update(paths)
    return parsed.paths, ' '.join(parsed.words)


def check_asset_comparison(root, record, contract, *, allow_unmet=False):
    """Check the comparison deliverables and versions, not their visual quality."""
    data=record.get('comparison')
    require(isinstance(data,dict),'asset_anchors needs the actual structured direction comparison')
    specific=lambda value: text(value) and value.strip().strip('.。').lower() not in practice.ASSET_PLACEHOLDERS
    features=data.get('confirmed_features')
    require(isinstance(features,list) and features and all(specific(value) for value in features)
            and len(set(features))==len(features),'list the confirmed observable appearance features')
    rows=data.get('rows')
    schema=practice.REQUIREMENTS['asset_anchors']['comparison']
    require(isinstance(rows,list) and len(rows)==len(features) and all(isinstance(row,dict) for row in rows)
            and {row.get('feature') for row in rows}==set(features),'comparison rows must cover every declared confirmed feature')
    sample=data.get('scene_sample');sample_path=verify_ref(root,sample)
    direction=read(root,contract['path'])
    direction_hashes={row['sha256'] for row in direction['parts'].values()}
    require(sample['sha256'] not in direction_hashes and all(row['sha256'] not in direction_hashes for row in record['anchors']),
            'current scene sample and anchors cannot copy the confirmed direction files')
    observed={(row['path'],row['sha256']) for row in record['artifacts']}
    require((sample['path'],sample['sha256']) in observed,'current scene sample must belong to the actual asset artifacts')
    if sample_path.suffix.lower()=='.png':
        require(viewport(data.get('viewport'))==viewport(direction['viewport']), 'asset sample viewport differs from confirmed direction')
        sources=[row for row in record['artifacts'] if row['path'] not in {sample['path'],data.get('review_page',{}).get('path')}]
        require(sources,'PNG scene sample needs the actual source artifacts used to render it')
        check_capture(root,dict(screenshot=sample,capture_binding=data.get('capture_binding'),viewport=data.get('viewport')),None,artifacts=sources)
    else:check_preview(root,sample)
    page=data.get('review_page');page_path=verify_ref(root,page)
    require(page_path.suffix.lower() in {'.html','.htm'},'actual side-by-side HTML review page required')
    embedded,visible=embedded_page(root,page_path)
    require(not any(value in visible for value in ASSET_PAGE_PLACEHOLDERS),
            'review page contains generated placeholders; replace them with actual observations, state and limitations')
    direction=read(root,contract['path'])
    reference={(ref['path'],ref['sha256']) for key,ref in direction['parts'].items() if key in {'preview','screenshot'}}
    anchors={(ref['path'],ref['sha256']) for ref in record['anchors']}|{(sample['path'],sample['sha256'])}
    expected={sample['path']}
    for row in rows:
        require(all(specific(row.get(key)) or key=='difference' and row.get('status')=='achieved'
                    and row.get(key) in {'无','none'} for key in ('feature','reference_observation','anchor_observation','difference')),
                'comparison observations and differences must be actual, not placeholders or future plans')
        require(row.get('status') in schema['statuses'],'comparison status must be achieved, close or unmet')
        before=row.get('reference');after=row.get('anchor');verify_ref(root,before);verify_ref(root,after)
        require((before['path'],before['sha256']) in reference,'comparison must use the current confirmed direction sample')
        require((after['path'],after['sha256']) in anchors,'comparison must use the actual current anchor or scene sample')
        require((before['path'],before['sha256'])!=(sample['path'],sample['sha256']),'current scene sample cannot be the direction itself')
        expected.update((before['path'],after['path']))
        require(allow_unmet or row['status']!='unmet','an unmet appearance feature cannot release the asset family for production')
        label={'achieved':'达到','close':'接近','unmet':'未达到'}[row['status']]
        require(row['feature'] in visible and (row['status'] in visible or label in visible),
                'review page must show every comparison feature and its status: '+row['feature'])
    require(expected<=embedded,'side-by-side review page must embed the actual direction and current scene/anchors: '+', '.join(sorted(expected-embedded)))


def asset_comparison_page(root, record_path, output, contract_path=DEFAULT_PATH):
    """Generate an editable comparison page, never a passed inspection."""
    from html import escape
    import os
    record=json.loads(file(root,record_path).read_text())
    data=validate(root,contract_path)
    comparison=record.get('comparison',{})
    features=comparison.get('confirmed_features',[])
    require(features and all(text(value) for value in features),'provide comparison.confirmed_features before generating the review page')
    target=Path(root)/output
    require(not Path(output).is_absolute() and '..' not in Path(output).parts and target.resolve().is_relative_to(Path(root).resolve()),'review page must be a safe project path')
    require(not target.exists(),'review page already exists; edit it instead of overwriting observations')
    sample=comparison.get('scene_sample');verify_ref(root,sample)
    direction=data['parts'].get('screenshot') or data['parts']['preview'];verify_ref(root,direction)
    values={'SCOPE':record.get('scope',''),'VIEWPORT':data['viewport'],'STATE':comparison.get('state','待填写代表状态'),
            'MISSING_INPUT_LIMITATIONS':'待填写缺失输入和本轮限制'}
    page=(Path(__file__).parent.parent/'asset-comparison-template.html').read_text()
    for key,value in values.items():page=page.replace('{{'+key+'}}',escape(str(value),quote=True))
    def embed(ref,label):
        source=escape(os.path.relpath(Path(root)/ref['path'],target.parent),quote=True)
        if Path(ref['path']).suffix.lower() in {'.html','.htm'}:
            return '<iframe src="'+source+'" title="'+label+'" sandbox="allow-scripts"></iframe>'
        return '<img src="'+source+'" alt="'+label+'">'
    page=page.replace('{{DIRECTION_EMBED}}',embed(direction,'已确认方向样张'))
    page=page.replace('{{SCENE_EMBED}}',embed(sample,'本轮锚点小样'))
    rows=''.join('<tr><td>'+escape(value)+'</td><td>待观察</td><td>待观察</td><td>待判定</td><td>待填写差异和影响</td></tr>' for value in features)
    page=page.replace('{{COMPARISON_ROWS}}',rows)
    target.parent.mkdir(parents=True,exist_ok=True);target.write_text(page)
    return dict(allowed=True,status='draft_only',review_page=evidence.ref(root,output),
                limitation='Generated placeholders are not an inspection or permission to submit review B.')


def asset_comparison_receipt(root, record_path, contract_path=DEFAULT_PATH):
    """Public pre-review check; its receipt binds the materials before asking the person."""
    data=validate(root,contract_path)
    contract=dict(evidence.ref(root,contract_path),version=data['version'])
    record_ref=evidence.ref(root,record_path)
    record=json.loads(file(root,record_path).read_text())
    check_record(root,'asset_anchors',record.get('scope'),record_ref,contract,allow_unmet=True)
    release_ready=all(row['status']!='unmet' for row in record['comparison']['rows'])
    refs={row['path']:row['sha256'] for row in evidence.references(record)}
    refs.update({row['path']:row['sha256'] for row in data['parts'].values()})
    payload=dict(format='asset-comparison-receipt/1',allowed=True,record=record_ref,contract=contract,
                 scope=record['scope'],review_page=record['comparison']['review_page'],release_ready=release_ready,
                 materials=[dict(path=name,sha256=sha) for name,sha in sorted(refs.items())])
    receipt=evidence.publish_immutable(root,'management/asset-comparisons/'+evidence.digest(payload)+'.json',
                                      json.dumps(payload,ensure_ascii=False,sort_keys=True))
    return dict(allowed=True,release_ready=release_ready,asset_comparison_receipt=receipt,review_page=payload['review_page'])


def check_asset_submission(root,state,display=None,*,registry_root=None,historical=False,allow_unmet=False):
    if state.get('role')!='design' or state.get('current')!='D-4':return
    authority=registry_root or root
    contract=state.get('tone_contract')
    data=confirmed_contract(root,contract,require_closed=not historical,registry_root=authority)
    require(not state.get('practice_scope') or set(state['practice_scope'])==set(state.get('scope',[])),
            'asset review practice_scope must match the displayed task scope')
    active=practice.active(profile(root,data),['asset_anchors'],state.get('practice_scope') or state.get('scope'))
    for sid, requirements in active.items():
        if 'asset_anchors' not in requirements:continue
        record_ref=state.get('practice_evidence',{}).get('asset_anchors',{}).get(sid)
        require(record_ref,'missing practice evidence: asset_anchors')
        record=json.loads(verify_ref(root,record_ref).read_text())
        check_asset_comparison(root,record,contract,allow_unmet=allow_unmet)
        receipt_ref=state.get('asset_comparison_receipts',{}).get(sid)
        require(receipt_ref,'before anchor review (and before review B) run tone_contract.py --asset-comparison and bind its receipt')
        receipt=json.loads(verify_ref(root,receipt_ref).read_text())
        require(receipt.get('format')=='asset-comparison-receipt/1' and receipt.get('allowed') is True
                and receipt.get('record')=={key:record_ref[key] for key in ('path','sha256')}
                and receipt.get('contract')==contract and receipt.get('scope')==sid
                and receipt.get('review_page')==record['comparison']['review_page'], 'asset comparison receipt is stale or belongs to other material')
        for ref in receipt['materials']:verify_ref(root,ref)
        if display is not None and display!=receipt['review_page']['path']:
            require((Path(root)/display).is_file(), 'review must show the page bound by each asset comparison receipt, directly or embedded')
            embedded,_=embedded_page(root,display,recursive=True)
            require(receipt['review_page']['path'] in embedded, 'review must show the page bound by each asset comparison receipt, directly or embedded')


def check_record(root, key, scope, ref, contract, *, registry_root=None, stage=None,allow_unmet=False):
    path = verify_ref(root, ref)
    data = json.loads(path.read_text(encoding='utf-8'))
    require(isinstance(data, dict) and data.get('scope') == scope and data.get('tone_contract') == contract,
            scope + ': ' + key + ' scope or tone contract is stale')
    specific=lambda value: text(value) and not re.fullmatch(r'(?:无|不适用|同上|n/?a|none|null|-|pending|todo|tbd|待定|待补|未做|稍后)[.。 ]*',value.strip(),re.I)
    fields = practice.REQUIREMENTS[key]['fields']
    require(all(specific(data.get(name)) for name in fields), scope + ': ' + key + ' needs ' + ', '.join(fields))
    if key=='implementation_walkthrough':
        for name,required in practice.REQUIREMENTS[key]['structured'].items():
            rows=data.get(name)
            require(isinstance(rows,list) and (rows or name in {'preserved_states','corrections'}), 'structured walkthrough rows required: '+name)
            require(all(isinstance(row,dict) and all(specific(row.get(field)) for field in required) for row in rows), 'walkthrough row needs '+', '.join(required))
            if name=='design_recheck_states':
                for row in rows:
                    path=verify_ref(root,row.get('evidence'))
                    if path.suffix.lower()=='.png':check_capture(root,dict(screenshot=row['evidence'],capture_binding=row.get('capture_binding'),viewport=data.get('viewport')),None,artifacts=data.get('artifacts'),registry_root=registry_root)
            if name=='corrections':require(all(row['type'] in {'implementation_deviation','acceptable_difference','design_gap','product_decision'} for row in rows), 'walkthrough correction needs a canonical type')
        if not data['preserved_states']:
            review=data.get('preservation_review',{})
            require(text(review.get('checker')) and specific(review.get('conclusion')) and specific(data.get('preservation_basis')), 'absence of preserved states needs an actual reviewer conclusion')
    observed = data.get('artifacts')
    require(isinstance(observed, list) and observed, scope + ': ' + key + ' needs actual artifacts')
    for item in observed:
        verify_ref(root, item)
    if key in {'appearance_proof', 'core_scene_skeleton'}:
        check_capture(root, data, data.get('capture_unavailable'), artifacts=observed, registry_root=registry_root)
        direction=read(root,contract['path'])
        require(viewport(data.get('viewport'))==viewport(direction['viewport']), 'stage viewport differs from the confirmed direction')
        compare_capture_source(data,dict(screenshot=direction['parts'].get('screenshot'),capture_binding=direction.get('capture_binding')))
    if key == 'asset_anchors':
        anchors = data.get('anchors')
        require(isinstance(anchors, list) and 3 <= len(anchors) <= 5, 'record three to five representative assets')
        paths = {verify_ref(root, item) for item in anchors}
        require(len(paths) == len(anchors), 'representative assets must be distinct')
        check_asset_comparison(root,data,contract,allow_unmet=allow_unmet)
    if key == 'playable_prototype':
        require(data.get('status') == 'completed', 'actual playable prototype must be completed; plans remain pending')
        for name in fields:
            require(not re.fullmatch(r'(?:pending|todo|tbd|待定|待补|未做|稍后)[.。 ]*', data[name].strip(), re.I), 'actual playable prototype cannot use placeholder: ' + name)
        denied=r'not actually run|assumed fine|not played(?: yet)?|not measured|no player (?:has )?(?:tried|played)'
        require(not any(re.search(denied,str(data[name]),re.I) for name in ('environment','play_instructions','timing')), 'completed evidence cannot claim it was not run or measured')
        run = json.loads(verify_ref(root, data.get('run_evidence')).read_text(encoding='utf-8'))
        timing = json.loads(verify_ref(root, data.get('timing_evidence')).read_text(encoding='utf-8'))
        require(run.get('status') == 'observed' and text(run.get('environment')) and isinstance(run.get('events'), list)
                and run['events'] and all(isinstance(event, dict) and all(text(event.get(key)) for key in ('action','result'))
                    and isinstance(event.get('at_ms'), (int,float)) and not isinstance(event['at_ms'], bool) and event['at_ms'] >= 0 for event in run['events']),
                'actual run evidence needs observed operations, results, event times and environment')
        require(timing.get('status') == 'observed' and text(timing.get('environment'))
                and isinstance(timing.get('measurements'), list) and timing['measurements']
                and all(isinstance(row, dict) and text(row.get('event')) and text(row.get('result'))
                    and all(isinstance(row.get(key), (int,float)) and not isinstance(row[key], bool) and row[key] >= 0
                            for key in ('started_ms','observed_ms'))
                    and row['observed_ms'] >= row['started_ms'] for row in timing['measurements']),
                'actual timing evidence needs measured events, results and environment')
        pairs=lambda rows:{(row['path'],row['sha256']) for row in rows}
        for log in (run,timing):
            require(pairs(log.get('artifacts',[]))==pairs(observed),'run and timing evidence must bind the actual current artifacts')
            require(not stage or log.get('stage')==stage,'run or timing evidence is from another stage')
            require(not re.search(denied,json.dumps(log,ensure_ascii=False),re.I),'observed log contradicts actual execution')
        play_status=data.get('playtest_status')
        if stage and stage.startswith('E-2.') and play_status=='pending':
            require(text(data.get('playtest')),'pending playtest needs the existing trial arrangement')
        else:
            require(play_status=='observed','actual acceptance requires an observed existing playtest, not a new approval')
            played=json.loads(verify_ref(root,data.get('playtest_evidence')).read_text())
            require(played.get('status')=='observed' and text(played.get('environment')) and pairs(played.get('artifacts',[]))==pairs(observed),
                    'playtest evidence must bind the tested artifacts and actual environment')
            require(not re.search(denied,str(data.get('playtest'))+' '+json.dumps(played,ensure_ascii=False),re.I),'playtest evidence contradicts actual participation')
            sessions=played.get('sessions')
            require(isinstance(sessions,list) and sessions and all(isinstance(row,dict) and text(row.get('player'))
                    and isinstance(row.get('observations'),list) and row['observations'] and all(specific(value) for value in row['observations']) for row in sessions),
                    'playtest needs an existing participant observation and its source')
            for row in sessions:verify_ref(root,row.get('source'))
        if stage=='Q-2':
            tested=data.get('tested_stage',{})
            view,manifest=evidence.stage_receipt(registry_root or root,tested.get('bundle'))
            require(manifest['context'].get('role')=='build' and manifest['context'].get('stage')=='E-3.3'
                    and manifest['context'].get('state_path')==tested.get('state_path'),'Q-2 needs the actual tested E-3.3 stage version')
            accepted=json.loads(file(view,tested['state_path']).read_text())
            require(pairs(accepted['artifacts'])<=pairs(observed),'Q-2 records must include the E-3.3 tested artifacts')
    return observed


def evidence_ref(state, key, sid):
    evidence = state.get('practice_evidence', {})
    require(isinstance(evidence, dict), 'practice_evidence must map records to activity scopes')
    scoped = evidence.get(key, {})
    require(isinstance(scoped, dict) and sid in scoped, sid + ': missing practice evidence: ' + key)
    return scoped[sid]


def check_stage(root, state, artifacts, requirements=None, *, phase='complete', registry_root=None, seal=True, task_context=None, historical=False, increment_review=False):
    root=Path(root).resolve();authority=Path(registry_root or root).resolve();stage=state['current']
    if requirements is None:
        stages=Path(__file__).resolve().parents[2]/'professions'
        requirements=next((rules[stage] for path in sorted(stages.glob('*/profession.json'))
                           if stage in (rules:=practice.stage_requirements(json.loads(path.read_text(encoding='utf-8'))))),{})
    entry=requirements.get('entry',[])
    whole_stage=list(dict.fromkeys([*entry,*requirements.get('complete',[])]))
    keys=whole_stage if phase=='complete' else entry
    if not keys:return []
    ref=state.get('tone_contract')
    data=confirmed_contract(root,ref,require_closed=stage!='P-1' and not historical,registry_root=authority)
    selected=state.get('practice_scope')
    if historical and (authority/DEFAULT_PATH).is_file():
        check_contract_scope(root,ref,authority,scope=selected or state['scope'],registry_root=authority)
    require(not state.get('practice_profile') or state['practice_profile']==data['profile'],'practice profile differs from project contract')
    if 'direction_fit' in keys:
        require(any(row['path']==ref['path'] and row['sha256']==ref['sha256'] for row in artifacts),'P-1 confirmation must cover the direction contract and practice profile')
        request=json.loads(file(root,state.get('request')).read_text(encoding='utf-8'))
        check_direction_scope(root,data,request.get('scope'))
        _,approved=evidence.verify_bundle(authority,data['confirmation']['review_receipt'])
        bound=approved['context']
        require(bound['request_id']==request.get('request_id') and set(bound['scope'])==set(request['scope'])
                and bound['display']['path']==request.get('display_evidence') and bound['display']['sha256']==request.get('display_sha256'),
                'P-1 confirmation must consume the same displayed request and complete scope')
        direction_review(root,data,state.get('tone_fit_review'),registry_root=authority,historical=historical,task_context=task_context)
        response=json.loads(file(root,state.get('response')).read_text(encoding='utf-8'))
        approval=data['confirmation']
        require(approval['source']==response.get('source'),'direction confirmation must cite the P-1 response')
        require(not response.get('person_id') or approval['person']==response['person_id'],'direction confirmer differs from P-1 confirmation')
        require(not response.get('quote') or approval['quote']==response['quote'],'direction quote differs from P-1 confirmation')
    current=profile(root,data)
    if stage=='D-6' and (task_context or {}).get('implementation'):
        # Human approval covers all stage artifacts. The visual walkthrough and
        # fit cover implementation; the design review document is its own output.
        artifacts=[row for row in artifacts if row['path'] in task_context['review_subjects']]
    if selected is not None:
        practice.select_scopes(current,selected)
        require(isinstance(state.get('scope'),list) and set(selected)==set(state['scope']),'practice coverage must match the worked activity scope')
    require('direction_fit' not in keys or selected is None,'P-1 confirms the profile across all activity scopes')
    if stage=='D-6' and state.get('implementation_handoff'):
        handoff=json.loads(verify_ref(root,state['implementation_handoff']).read_text())
        require(handoff.get('delivery_kind') in {'design_only','implemented'} and text(handoff.get('basis')),'D-6 implementation applicability needs an actual scoped handoff')
        require(isinstance(handoff.get('artifacts'),list) and {(row['path'],row['sha256']) for row in handoff['artifacts']}=={(row['path'],row['sha256']) for row in artifacts},'D-6 handoff must cover this actual stage delivery')
        if handoff['delivery_kind']=='design_only':
            require(not (task_context or {}).get('implementation') and not any(row['path'].startswith(('src/','engineering/')) for row in artifacts),
                    'design_only handoff cannot exempt actual implementation artifacts')
            keys=[key for key in keys if key not in {'implementation_walkthrough','increment_fit'}]
    enabled=practice.active(current,whole_stage,selected);triggered=[];seals=[]
    for sid,rows in enabled.items():
        checked={};prior_fits={};fit_paths=set()
        for key in rows:
            if key not in keys:continue
            definition=practice.REQUIREMENTS[key]
            if key in {'tone_contract','direction_profile','direction_fit'}:continue
            entry_record=key in entry and key not in requirements.get('complete',[])
            record_ref=evidence_ref(state,key,sid);record_root=root;record_contract=ref
            if entry_record:
                if state.get('upstream_bundle'):
                    upstream_root,upstream_manifest=evidence.stage_receipt(authority,state['upstream_bundle'])
                    upstream_state=json.loads(file(upstream_root,upstream_manifest['context']['state_path']).read_text())
                    upstream_evidence=upstream_state.get('practice_evidence',{}).get(key)
                    require(upstream_evidence is None or upstream_evidence.get(sid)==record_ref,
                            'historical evidence differs from the chosen upstream stage: '+key)
                record_root,record_contract=historical_record(authority,record_ref,key,sid,root,ref)
            if definition['record']=='tone_fit_review':
                if key=='skeleton_fit':target=checked.get('core_scene_skeleton',artifacts)
                else:target=next((checked[name] for name in ('implementation_walkthrough','asset_anchors','scene_structure','appearance_target') if name in checked),artifacts)
                path=verify_ref(record_root,record_ref).relative_to(record_root).as_posix()
                require(path not in fit_paths,'skeleton and increment require separate fit review records');fit_paths.add(path)
                if entry_record:target=json.loads(file(record_root,path).read_text())['artifacts']
                else:target=list({row['path']:row for row in [*target,*artifacts]}.values())
                fit=check_fit(record_root,path,target,record_contract,registry_root=authority,historical=historical or entry_record,
                              task_context=task_context if not entry_record else None)
                direction=read(record_root,record_contract['path'])
                require(viewport(fit['viewport'])==viewport(direction['viewport']),'fit viewport differs from the confirmed direction')
                if 'comparison' in definition:check_fit_comparison(record_root,fit,direction,definition['comparison'])
                if not entry_record:
                    compare_capture_source(fit,dict(screenshot=data['parts'].get('screenshot'),capture_binding=data.get('capture_binding')))
                    for previous in prior_fits.values():compare_capture_source(fit,previous)
                    walk=checked.get('implementation_walkthrough')
                    if walk:
                        record=json.loads(verify_ref(root,evidence_ref(state,'implementation_walkthrough',sid)).read_text())
                        if not record['preserved_states']:require(record['preservation_review']['checker']==fit['checker'],'preservation exception must be confirmed by the actual fit checker')
                else:prior_fits[key]=fit
            else:
                record_stage=evidence.verify_bundle(authority,record_ref['bundle'])[1]['context']['stage'] if entry_record else stage
                observed=check_record(record_root,key,sid,record_ref,record_contract,registry_root=authority,stage=record_stage)
                # Historical files are evidence of an earlier state, never targets of a new fit.
                if not entry_record:checked[key]=observed
                if entry_record and key=='core_scene_skeleton' and stage=='E-2.4' and not historical:
                    for item in observed:verify_ref(root,item)
                if not entry_record and key=='implementation_walkthrough' and (increment_review or stage in definition.get('design_review_stages',())):
                    record=json.loads(verify_ref(root,record_ref).read_text());design_review=record.get('design_review',{})
                    design_root,manifest=evidence.stage_receipt(authority,design_review.get('bundle'))
                    state_path=design_review.get('state_path')
                    require(manifest['context'].get('state_path')==state_path and manifest['context'].get('stage')=='D-6','implementation needs the actual D-6 design review snapshot')
                    design_state=json.loads(file(design_root,state_path).read_text())
                    require(design_state.get('role')=='design' and design_state.get('current')=='D-6','implementation design review must be D-6')
                    check_contract_scope(design_root,design_state['tone_contract'],root,ref,[sid],registry_root=authority)
                    database=authority/'management/runtime/tasks.sqlite3'
                    if database.is_file():
                        with evidence.authority_connection(authority) as db:
                            tasks=[json.loads(row[0]) for row in db.execute('SELECT data FROM tasks')]
                            identities={row['id']:row for (raw,) in db.execute("SELECT data FROM pm_records WHERE kind='instance'") for row in [json.loads(raw)]}
                        matches=[task for task in tasks if task.get('state')=='done' and (task.get('practice_receipt') or {}).get('bundle')==design_review['bundle']
                                 and (task.get('practice_stage') or {}).get('role')=='design' and (task.get('practice_stage') or {}).get('current')=='D-6']
                        require(any(identities.get(task.get('executor') or task.get('owner'),{}).get('profession')=='experience-design' for task in matches),
                                'D-6 snapshot must come from a completed actual design task')
                    gate_spec=importlib.util.spec_from_file_location('walkthrough_stage_gate',Path(__file__).with_name('stage_gate.py'))
                    gate=importlib.util.module_from_spec(gate_spec);gate_spec.loader.exec_module(gate)
                    gate.check(design_root,design_state,registry_root=authority,seal=False)
                    expected={row['path']:row['sha256'] for row in design_state['artifacts']}
                    require(all(expected.get(row['path'])==row['sha256'] for row in artifacts),'D-6 review snapshot does not cover current implementation')
                if not entry_record and key in {'core_scene_skeleton','implementation_walkthrough','playable_prototype','asset_anchors'}:
                    expected={row['path']:row['sha256'] for row in observed}
                    require(all(expected.get(row['path'])==row['sha256'] for row in artifacts),key+' does not cover current stage artifacts')
            if not entry_record:seals.append((record_ref,{'role':state.get('role'),'stage':stage,'scope':sid,'requirement':key,'tone_contract':ref}))
        triggered.extend({'scope':sid,'requirement':key} for key in rows if key in keys)
    if seal:
        for record_ref,context in seals:record_ref['bundle']=evidence.seal_bundle(root,[record_ref],context)
    return triggered


def check_increment(root, state, artifacts, *, registry_root=None, task_context=None, seal=True, historical=False):
    """Review the actual first operable increment without changing or closing its stage."""
    require(state.get('role') == 'build' and state.get('current') in {'E-3.1', 'E-3.2'},
            'first increment review must retain its actual registered build stage')
    requirements={'complete':['tone_contract','implementation_walkthrough','increment_fit']}
    return check_stage(root,state,artifacts,requirements,registry_root=registry_root,seal=seal,
                       task_context=task_context,historical=historical,increment_review=True)


def refresh_draft(root, name):
    data=read(root,name)
    require(not data.get('confirmation'),'refresh only an unconfirmed draft; preserve approved versions')
    for key,value in data.get('parts',{}).items():
        require(isinstance(value,dict) and text(value.get('path')),'part path required: '+key)
        value['sha256']=evidence.ref(root,value['path'])['sha256']
        value.setdefault('version',data['version'])
    profile_ref=data.get('parts',{}).get('practice_profile')
    if profile_ref:
        profile_ref['version']=json.loads(verify_ref(root,profile_ref).read_text())['version']
    capture=data.get('capture_binding',{})
    if capture.get('receipt'):
        capture_ref=evidence.ref(root,capture['receipt']['path'])
        actual=json.loads(verify_ref(root,capture_ref).read_text())
        require(actual.get('screenshot_sha256')==data['parts']['screenshot']['sha256'],'capture receipt is not for the current screenshot')
        data['capture_binding']={key:value for key,value in actual.items() if key!='screenshot_sha256'}
        data['capture_binding']['receipt']=capture_ref
    path=file(root,name)
    source=path.read_text(encoding='utf-8')
    payload='```tone-contract\n'+json.dumps(data,ensure_ascii=False,indent=2)+'\n```'
    source=re.sub(r'^```tone-contract\s*\n.*?^```\s*$',lambda _:payload,source,flags=re.M|re.S)
    path.write_text(source,encoding='utf-8')
    return data


def save_delivery(root,name,result,contract_path):
    relative=Path(name);base=Path(root).resolve();path=base/relative
    require(not relative.is_absolute() and '..' not in relative.parts and path.resolve().is_relative_to(base)
            and not any(p.is_symlink() for p in [path,*path.parents] if p!=base and base in p.parents), 'safe project-relative tool receipt required')
    require(name!=contract_path,'tool receipt cannot replace its direction contract')
    if path.exists():
        existing=json.loads(file(base,name).read_text(encoding='utf-8'))
        require(isinstance(existing,dict) and existing.get('format')=='direction-tool-receipt/1','tool receipt cannot overwrite a business artifact')
    path.parent.mkdir(parents=True,exist_ok=True)
    body=dict(result,format='direction-tool-receipt/1',contract=evidence.ref(base,contract_path),
              tool={'path':'matrix/base/tools/tone_contract.py','sha256':sha(Path(__file__).read_bytes())})
    path.write_text(json.dumps(body,ensure_ascii=False,sort_keys=True,indent=2)+'\n',encoding='utf-8')
    return evidence.ref(base,name)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project',type=Path,required=True)
    parser.add_argument('--contract',default=DEFAULT_PATH)
    parser.add_argument('--draft',action='store_true',help='validate and persist the current draft delivery receipt')
    parser.add_argument('--refresh-draft',action='store_true',help='refresh actual part digests in an unconfirmed draft; never fabricate capture evidence')
    parser.add_argument('--receipt',help='project-relative successful tool receipt; defaults to <contract>.delivery.json')
    parser.add_argument('--asset-comparison',help='check before anchor review; review B reuses or refreshes the receipt; unmet is reviewable, not releasable')
    parser.add_argument('--asset-page',help='generate a draft review page from the comparison record')
    parser.add_argument('--page-output',help='new project-relative HTML path for --asset-page')
    args=parser.parse_args()
    try:
        if args.asset_page:
            require(args.page_output and not args.asset_comparison and not args.draft and not args.refresh_draft,'asset page generation needs --page-output and no other mode')
            print(json.dumps(asset_comparison_page(args.project,args.asset_page,args.page_output,args.contract),ensure_ascii=False));return 0
        if args.asset_comparison:
            require(not args.draft and not args.refresh_draft,'asset comparison is a separate pre-review operation')
            print(json.dumps(asset_comparison_receipt(args.project,args.asset_comparison,args.contract),ensure_ascii=False));return 0
        require(not args.refresh_draft or args.draft,'--refresh-draft requires --draft')
        if args.refresh_draft:refresh_draft(args.project,args.contract)
        record=validate(args.project,args.contract,confirmed=not args.draft)
        result={'allowed':True,'version':record['version']}
        if args.draft:
            result.update(direction_reference=direction_binding(DEFAULT_PATH,record),delivery=direction_delivery(record))
            result['draft']=evidence.ref(args.project,args.contract)
            result['tool_receipt']=save_delivery(args.project,args.receipt or args.contract+'.delivery.json',result,args.contract)
    except (ValueError,OSError,KeyError,TypeError,AttributeError) as error:
        result={'allowed':False,'error':str(error)}
        if args.draft:
            try:
                pending=read(args.project,args.contract)
                if text(pending.get('version')):result.update(direction_reference=direction_binding(DEFAULT_PATH,pending),status='draft_incomplete')
            except (ValueError,OSError,KeyError,TypeError,AttributeError):pass
        print(json.dumps(result,ensure_ascii=False));return 1
    print(json.dumps(result,ensure_ascii=False));return 0


if __name__=='__main__':
    raise SystemExit(main())
