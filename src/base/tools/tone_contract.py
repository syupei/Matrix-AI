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


def check_confirmation(root, data, *, require_closed=True, registry_root=None):
    approval = data.get('confirmation', {})
    require(isinstance(approval, dict) and all(text(approval.get(k)) for k in ('person', 'quote', 'source')),
            'record confirmer, exact quote and response source')
    expected = direction_binding(DEFAULT_PATH, data)['direction_sha256']
    require(approval.get('direction_sha256') == expected, 'confirmation direction_sha256 is missing or changed; return to P-1')
    authority_root = Path(registry_root or root).resolve()
    view, manifest = evidence.verify_bundle(authority_root, approval.get('review_receipt'))
    binding = evidence.check_review_binding(manifest['context'], direction_sha256=expected,
                                             person=approval['person'], quote=approval['quote'])
    people = authority_root / 'management/people.json'
    if people.is_file():
        roster = {row['id']:row for row in json.loads(people.read_text(encoding='utf-8')).get('people', [])}
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
        with sqlite3.connect(database.as_uri() + '?mode=ro', uri=True) as db:
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


def check_capture(root, record, unavailable, *, viewport_value=None, capture_binding=None, artifacts=None, registry_root=None, human_review_receipt=None, pending_human=False):
    if 'screenshot' in record:
        path = verify_ref(root, record['screenshot'])
        require(picture(path), 'actual rendered screenshot required (decodable PNG)')
        dimensions = evidence.png_dimensions(path)
        binding = capture_binding or record.get('capture_binding')
        require(isinstance(binding, dict), 'actual screenshot needs a capture binding to its current preview/artifacts')
        css = viewport(viewport_value or record.get('viewport'))
        scale = binding.get('scale', 1)
        require(isinstance(scale, (int, float)) and not isinstance(scale, bool) and scale > 0
                and dimensions == tuple(round(size * scale) for size in css), 'screenshot pixel dimensions differ from viewport and scale')
        require(binding.get('pixel_size') == list(dimensions) and viewport(binding.get('viewport')) == css
                and all(text(binding.get(key)) for key in ('method', 'state', 'source')), 'record capture pixel size, viewport, method, state and source')
        expected = {(row['path'], row['sha256']) for row in (artifacts or record.get('artifacts', []))}
        actual = {(row.get('path'), row.get('sha256')) for row in binding.get('artifacts', []) if isinstance(row, dict)}
        require(expected and actual == expected, 'screenshot capture does not bind the current artifacts')
        provenance = json.loads(verify_ref(root, binding.get('receipt')).read_text(encoding='utf-8'))
        require(provenance == {**{key:value for key,value in binding.items() if key != 'receipt'},
                               'screenshot_sha256':record['screenshot']['sha256']},
                'screenshot differs from its actual capture receipt or captured source closure')
        for item in binding['artifacts']:
            verify_ref(root, item)
    else:
        require(text(unavailable), 'actual screenshot or recorded human viewport review with capture limitation required')
        observed = verify_ref(root, record.get('manual_review'))
        require(text(observed.read_text(encoding='utf-8')), 'record the actually displayed viewport before asking for review')
        if pending_human and human_review_receipt is None and record.get('human_review_receipt') is None:
            return  # Display registration only; no passed delivery or human inspection is claimed.
        check_human_review(root,record,artifacts or record.get('artifacts',[]),
                           human_review_receipt or record.get('human_review_receipt'),registry_root)


def check_human_review(root, record, artifacts, receipt, registry_root=None):
    require(isinstance(receipt,dict), 'human viewport inspection requires the actual human response receipt')
    authority = Path(registry_root or root).resolve()
    view, manifest = evidence.verify_bundle(authority, receipt)
    binding = evidence.check_review_binding(manifest['context'],person=record.get('checker'))
    people = authority / 'management/people.json'
    if people.is_file():
        roster = {row['id']: row for row in json.loads(people.read_text()).get('people', [])}
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


def check_fit(root, record, artifacts, contract=None, *, pre_confirmation=False, registry_root=None, human_review_receipt=None):
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
        with sqlite3.connect(database.as_uri() + '?mode=ro', uri=True) as db:
            instances = {row['id']: row for row in (json.loads(value[0]) for value in db.execute("SELECT data FROM pm_records WHERE kind='instance'")) if row.get('active', True)}
    if mode == 'same_instance':
        require(not database.is_file() and not (authority / 'management/instance-config.json').is_file()
                and not (authority / 'management/people.json').is_file(), 'same-instance fit is only available in an actual single-conversation project')
    if mode == 'independent' and database.is_file():
        require({data['producer'], data['checker']} <= instances.keys(), 'fit producer/checker must be actual active project instances')
        review_task = data.get('review_task')
        with sqlite3.connect(database.as_uri() + '?mode=ro', uri=True) as db:
            row = db.execute('SELECT data FROM tasks WHERE id=?', (review_task,)).fetchone()
        task = json.loads(row[0]) if row else {}
        require(task.get('owner') == data['checker'] or task.get('checker') == data['checker'], 'fit checker must have an assigned project review task')
        review = task.get('review') or {}
        handed = task.get('handed_output_sha256', {}) if task.get('owner') == data['checker'] else {}
        reviewed = review.get('artifact_sha256', {}) if review.get('checker') == data['checker'] and review.get('outcome') == 'passed' else {}
        require(sha(file(root,record).read_bytes()) in {*handed.values(), *reviewed.values()},
                'independent fit bytes must match the actual checker handover or trusted review submission')
    require(mode == 'human' or 'screenshot' in data, 'actual rendered screenshot required for passed fit review')
    check_capture(root, data, data.get('capture_unavailable'), artifacts=observed, registry_root=registry_root,
                  human_review_receipt=human_review_receipt)
    if mode == 'human' and 'screenshot' in data:
        check_human_review(root,data,[*observed,data['screenshot']],human_review_receipt or data.get('human_review_receipt'),registry_root)
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
            and ref.get('path') == DEFAULT_PATH, 'reference the current tone contract and its version')
    verify_ref(root, ref)
    result = validate(root, ref['path'], require_closed=require_closed, registry_root=registry_root)
    require(result['version'] == ref.get('version'), 'tone contract version changed')
    return result


def direction_review(root, data, record, *, registry_root=None):
    binding = direction_binding(DEFAULT_PATH, data)
    reviewed = [data['parts'][key] for key in ('scene', 'preview', 'samples', 'practice_profile')]
    fit = check_fit(root, record, reviewed, binding, pre_confirmation=True, registry_root=registry_root,
                    human_review_receipt=data.get('confirmation',{}).get('review_receipt'))
    if fit['mode'] == 'human':
        require(fit['checker'] == data['confirmation']['person'], 'human viewport reviewer must match the P-1 confirmer')
    return fit


def check_record(root, key, scope, ref, contract, *, registry_root=None):
    path = verify_ref(root, ref)
    data = json.loads(path.read_text(encoding='utf-8'))
    require(isinstance(data, dict) and data.get('scope') == scope and data.get('tone_contract') == contract,
            scope + ': ' + key + ' scope or tone contract is stale')
    fields = practice.REQUIREMENTS[key]['fields']
    require(all(text(data.get(name)) for name in fields), scope + ': ' + key + ' needs ' + ', '.join(fields))
    observed = data.get('artifacts')
    require(isinstance(observed, list) and observed, scope + ': ' + key + ' needs actual artifacts')
    for item in observed:
        verify_ref(root, item)
    if key in {'appearance_proof', 'core_scene_skeleton'}:
        check_capture(root, data, data.get('capture_unavailable'), artifacts=observed, registry_root=registry_root)
    if key == 'asset_anchors':
        anchors = data.get('anchors')
        require(isinstance(anchors, list) and 3 <= len(anchors) <= 5, 'record three to five representative assets')
        paths = {verify_ref(root, item) for item in anchors}
        require(len(paths) == len(anchors), 'representative assets must be distinct')
    if key == 'playable_prototype':
        require(data.get('status') == 'completed', 'actual playable prototype must be completed; plans remain pending')
        for name in fields:
            require(not re.fullmatch(r'(?:pending|todo|tbd|待定|待补|未做|稍后)[.。 ]*', data[name].strip(), re.I), 'actual playable prototype cannot use placeholder: ' + name)
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
    return observed


def evidence_ref(state, key, sid):
    evidence = state.get('practice_evidence', {})
    require(isinstance(evidence, dict), 'practice_evidence must map records to activity scopes')
    scoped = evidence.get(key, {})
    require(isinstance(scoped, dict) and sid in scoped, sid + ': missing practice evidence: ' + key)
    return scoped[sid]


def check_stage(root, state, artifacts, requirements=None, *, phase='complete', registry_root=None, seal=True):
    root = Path(root).resolve()
    stage = state['current']
    if requirements is None:
        # Direct callers use the same registry as the stage CLI.
        stages = Path(__file__).resolve().parents[2] / 'professions'
        requirements = next((rules[stage] for path in sorted(stages.glob('*/profession.json'))
                             if stage in (rules := practice.stage_requirements(json.loads(path.read_text(encoding='utf-8'))))), {})
    entry = requirements.get('entry', [])
    whole_stage = list(dict.fromkeys([*entry, *requirements.get('complete', [])]))
    keys = whole_stage if phase == 'complete' else entry
    if not keys:
        return []
    ref = state.get('tone_contract')
    data = confirmed_contract(root, ref, require_closed=stage != 'P-1', registry_root=registry_root)
    declared_label = state.get('practice_profile')
    require(not declared_label or declared_label == data['profile'], 'practice profile differs from project contract')
    if 'direction_fit' in keys:
        require(any(item['path'] == ref['path'] and item['sha256'] == ref['sha256'] for item in artifacts),
                'P-1 confirmation must cover the direction contract and practice profile')
        request = json.loads(file(root,state.get('request')).read_text(encoding='utf-8'))
        _, approval_manifest = evidence.verify_bundle(Path(registry_root or root),data['confirmation']['review_receipt'])
        bound = approval_manifest['context']
        require(bound['request_id'] == request.get('request_id') and bound['scope'] == request.get('scope')
                and bound['display']['path'] == request.get('display_evidence')
                and bound['display']['sha256'] == request.get('display_sha256'),
                'P-1 confirmation must consume the same displayed request and complete scope')
        fit_path = state.get('tone_fit_review')
        direction_review(root, data, fit_path, registry_root=registry_root or root)
        response = json.loads(file(root, state.get('response')).read_text(encoding='utf-8'))
        approval = data['confirmation']
        require(approval['source'] == response.get('source'), 'direction confirmation must cite the P-1 response')
        if response.get('person_id'):
            require(approval['person'] == response['person_id'], 'direction confirmer differs from P-1 confirmation')
        if response.get('quote'):
            require(approval['quote'] == response['quote'], 'direction quote differs from P-1 confirmation')
    selected = state.get('practice_scope')
    current = profile(root, data)
    if selected is not None:
        practice.select_scopes(current, selected)
        require(isinstance(state.get('scope'), list) and set(selected) == set(state['scope']),
                'practice coverage must match the worked activity scope')
    require('direction_fit' not in keys or selected is None, 'P-1 confirms the profile across all activity scopes')
    if stage == 'D-6' and state.get('implementation_handoff'):
        handoff_ref = state['implementation_handoff']
        handoff = json.loads(verify_ref(root, handoff_ref).read_text(encoding='utf-8'))
        require(handoff.get('delivery_kind') in {'design_only', 'implemented'} and text(handoff.get('basis')),
                'D-6 implementation applicability needs an actual scoped handoff')
        require({(item.get('path'),item.get('sha256')) for item in handoff.get('artifacts',[]) if isinstance(item,dict)}
                == {(item['path'],item['sha256']) for item in artifacts}, 'D-6 handoff must cover this actual stage delivery')
        if handoff['delivery_kind'] == 'design_only':
            keys = [key for key in keys if key not in {'implementation_walkthrough','increment_fit'}]
    enabled = practice.active(current, whole_stage, selected)
    triggered = []
    seals = []
    for sid, rows in enabled.items():
        checked = {}
        fit_paths = set()
        for key in rows:
            if key not in keys:
                continue
            definition = practice.REQUIREMENTS[key]
            historical = key in entry and key not in requirements.get('complete', [])
            if key in {'tone_contract', 'direction_profile', 'direction_fit'}:
                continue
            if definition['record'] == 'tone_fit_review':
                record_ref = evidence_ref(state, key, sid)
                record_root = root
                if historical:
                    record_root, sealed = evidence.verify_bundle(Path(registry_root or root), record_ref.get('bundle'))
                    require(sealed['context'].get('tone_contract') == ref and sealed['context'].get('scope') == sid
                            and sealed['context'].get('requirement') == key, 'historical evidence bundle contract/scope changed')
                if key == 'skeleton_fit':
                    target = checked.get('core_scene_skeleton', artifacts)
                else:
                    target = next((checked[name] for name in
                                   ('implementation_walkthrough', 'asset_anchors', 'scene_structure', 'appearance_target')
                                   if name in checked), artifacts)
                path = verify_ref(record_root, record_ref).relative_to(record_root).as_posix()
                require(path not in fit_paths, 'skeleton and increment require separate fit review records')
                fit_paths.add(path)
                if historical:
                    target = json.loads(file(record_root, path).read_text())['artifacts']
                else:
                    target = list({item['path']: item for item in [*target, *artifacts]}.values())
                fit = check_fit(record_root, path, target, ref, registry_root=registry_root or root)
                if 'comparison' in definition:
                    check_fit_comparison(record_root, fit, data, definition['comparison'])
            else:
                record_ref = evidence_ref(state, key, sid)
                record_root = root
                if historical:
                    record_root, sealed = evidence.verify_bundle(Path(registry_root or root), record_ref.get('bundle'))
                    require(sealed['context'].get('tone_contract') == ref and sealed['context'].get('scope') == sid
                            and sealed['context'].get('requirement') == key, 'historical evidence bundle contract/scope changed')
                checked[key] = check_record(record_root, key, sid, record_ref, ref, registry_root=registry_root or root)
                if not historical and key == 'implementation_walkthrough' and stage in definition.get('design_review_stages', ()):
                    record = json.loads(verify_ref(root, record_ref).read_text(encoding='utf-8'))
                    design_review = record.get('design_review', {})
                    design_root, manifest = evidence.verify_bundle(Path(registry_root or root), design_review.get('bundle'))
                    state_path = design_review.get('state_path')
                    require(manifest['context'].get('state_path') == state_path and manifest['context'].get('stage') == 'D-6'
                            and manifest['context'].get('tone_contract') == ref, 'implementation needs the actual D-6 design review snapshot')
                    design_state = json.loads(file(design_root, state_path).read_text(encoding='utf-8'))
                    require(design_state.get('role') == 'design' and design_state.get('current') == 'D-6', 'implementation design review must be D-6')
                    gate_spec=importlib.util.spec_from_file_location('walkthrough_stage_gate',Path(__file__).with_name('stage_gate.py'))
                    gate=importlib.util.module_from_spec(gate_spec);gate_spec.loader.exec_module(gate)
                    gate.check(design_root,design_state,registry_root=registry_root or root,seal=False)
                    design_artifacts={item['path']:item['sha256'] for item in design_state['artifacts']}
                    require(all(design_artifacts.get(item['path']) == item['sha256'] for item in artifacts),
                            'D-6 review snapshot does not cover current implementation')
                if not historical and key in {'core_scene_skeleton','implementation_walkthrough','playable_prototype'}:
                    observed = {item['path']:item['sha256'] for item in checked[key]}
                    require(all(observed.get(item['path']) == item['sha256'] for item in artifacts),
                            key + ' does not cover current stage artifacts')
            if not historical:
                seals.append((record_ref, {'role': state.get('role'), 'stage': stage, 'scope': sid, 'requirement': key, 'tone_contract': ref}))
        triggered.extend({'scope': sid, 'requirement': key} for key in rows if key in keys)
    if seal:
        for record_ref, context in seals:
            record_ref['bundle'] = evidence.seal_bundle(root, [record_ref], context)
    return triggered


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, required=True)
    parser.add_argument('--contract', default=DEFAULT_PATH)
    parser.add_argument('--draft', action='store_true', help='print the binding for review before P-1 confirmation')
    args = parser.parse_args()
    try:
        record = validate(args.project, args.contract, confirmed=not args.draft)
    except (ValueError, OSError, KeyError, TypeError, AttributeError) as error:
        print(json.dumps({'allowed':False,'error':str(error)}, ensure_ascii=False))
        return 1
    result = {'allowed': True, 'version': record['version']}
    if args.draft:
        result['direction_reference'] = direction_binding(DEFAULT_PATH, record)
        result['delivery'] = direction_delivery(record)
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
