#!/usr/bin/env python3
"""Validate a direction sample, its approved tone contract and review evidence."""

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re

DEFAULT_PATH = 'product/specs/00-方向样张.md'
_spec = importlib.util.spec_from_file_location('practice_profiles', Path(__file__).with_name('practice_profiles.py'))
practice = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(practice)


def require(ok, message):
    if not ok:
        raise ValueError(message)


def text(value):
    return isinstance(value, str) and bool(value.strip())


def file(root, name):
    require(text(name), 'project file path required')
    path = Path(name)
    require(not path.is_absolute() and '..' not in path.parts, 'project-relative path required: ' + name)
    dest = root / path
    require(dest.resolve().is_relative_to(root) and dest.is_file()
            and not any(p.is_symlink() for p in [dest, *dest.parents] if p != root and root in p.parents),
            'missing or unsafe project file: ' + name)
    return dest


def sha(data):
    return hashlib.sha256(data).hexdigest()


def verify_ref(root, ref):
    require(isinstance(ref, dict), 'artifact reference must include path and sha256')
    path = file(root, ref.get('path'))
    require(ref.get('sha256') == sha(path.read_bytes()), 'stale artifact: ' + ref['path'])
    return path


def picture(path):
    with path.open('rb') as handle:
        header = handle.read(33)
        if header.startswith(b'\x89PNG\r\n\x1a\n'):
            if (len(header) != 33 or header[8:16] != b'\x00\x00\x00\x0dIHDR'
                    or not all(int.from_bytes(header[i:i+4], 'big') for i in (16, 20))):
                return False
            handle.seek(-12, 2)
            return handle.read() == b'\x00\x00\x00\x00IEND\xaeB`\x82'
        if header.startswith(b'\xff\xd8\xff') and len(header) == 33:
            handle.seek(-2, 2)
            return handle.read() == b'\xff\xd9'
    return (len(header) == 33 and header[:4] == b'RIFF' and header[8:12] == b'WEBP'
            and header[12:16] in {b'VP8 ', b'VP8L', b'VP8X'}
            and int.from_bytes(header[4:8], 'little') + 8 == path.stat().st_size)


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


def validate(root, ref, *, confirmed=True):
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
    check_capture(root, parts, data.get('capture_unavailable'))
    current = profile(root, data)
    motion = any(row['features'][name]['value'] == 'yes' for row in current['scopes'] for name in practice.MOTION)
    if motion:
        samples = data.get('samples', [])
        require(isinstance(samples, list) and all(isinstance(x, dict) and all(text(x.get(k)) for k in
                ('moment', 'text', 'consequence')) for x in samples), 'samples must name a moment, text and consequence')
        require(len({x['text'].strip() for x in samples}) >= 6 and len({x['moment'].strip() for x in samples}) >= 4,
                'interactive timing requires six distinct samples across four moments')
    if confirmed:
        confirmation = data.get('confirmation', {})
        require(isinstance(confirmation, dict) and all(text(confirmation.get(k)) for k in ('person', 'quote', 'source')),
                'record confirmer, exact quote and response source')
        require(confirmation['quote'] in file(root, confirmation['source']).read_text(encoding='utf-8'),
                'confirmation quote missing from response source')
    return data


def check_capture(root, record, unavailable):
    if 'screenshot' in record:
        require(picture(verify_ref(root, record['screenshot'])), 'actual rendered screenshot required')
    else:
        require(text(unavailable), 'actual screenshot or recorded human viewport review with capture limitation required')
        source = verify_ref(root, record.get('manual_review'))
        require(text(source.read_text(encoding='utf-8')), 'human viewport inspection evidence required')


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


def check_fit(root, record, artifacts, contract=None, *, pre_confirmation=False):
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
    if mode == 'human':
        require('screenshot' not in data, 'human capture fallback uses a viewport inspection record')
        check_capture(root, data, data.get('capture_unavailable'))
    else:
        require('screenshot' in data, 'actual rendered screenshot required for passed fit review')
        check_capture(root, data, None)
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
        require(record['mode'] == 'human', 'direction without capture requires actual human comparison')
        key = schema['reference'][1]
        part = parts['manual_review']
    ref = record.get(key)
    require(isinstance(ref, dict) and all(ref.get(field) == part[field] for field in ('path', 'sha256')),
            'fit comparison must use the current direction reference: ' + key)
    verify_ref(root, ref)


def confirmed_contract(root, ref):
    require(isinstance(ref, dict) and set(ref) == {'path', 'version', 'sha256'}
            and ref.get('path') == DEFAULT_PATH, 'reference the current tone contract and its version')
    verify_ref(root, ref)
    result = validate(root, ref['path'])
    require(result['version'] == ref.get('version'), 'tone contract version changed')
    return result


def direction_review(root, data, record):
    binding = direction_binding(DEFAULT_PATH, data)
    reviewed = [data['parts'][key] for key in ('scene', 'preview', 'samples', 'practice_profile')]
    fit = check_fit(root, record, reviewed, binding, pre_confirmation=True)
    if fit['mode'] == 'human':
        require(fit['checker'] == data['confirmation']['person'], 'human viewport reviewer must match the P-1 confirmer')
    return fit


def check_record(root, key, scope, ref, contract):
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
        check_capture(root, data, data.get('capture_unavailable'))
    if key == 'asset_anchors':
        anchors = data.get('anchors')
        require(isinstance(anchors, list) and 3 <= len(anchors) <= 5, 'record three to five representative assets')
        paths = {verify_ref(root, item) for item in anchors}
        require(len(paths) == len(anchors), 'representative assets must be distinct')
    return observed


def evidence_ref(state, key, sid):
    evidence = state.get('practice_evidence', {})
    require(isinstance(evidence, dict), 'practice_evidence must map records to activity scopes')
    scoped = evidence.get(key, {})
    require(isinstance(scoped, dict) and sid in scoped, sid + ': missing practice evidence: ' + key)
    return scoped[sid]


def check_stage(root, state, artifacts, requirements=None, *, phase='complete'):
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
    data = confirmed_contract(root, ref)
    declared_label = state.get('practice_profile')
    require(not declared_label or declared_label == data['profile'], 'practice profile differs from project contract')
    if 'direction_fit' in keys:
        require(any(item['path'] == ref['path'] and item['sha256'] == ref['sha256'] for item in artifacts),
                'P-1 confirmation must cover the direction contract and practice profile')
        fit_path = state.get('tone_fit_review')
        direction_review(root, data, fit_path)
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
    enabled = practice.active(current, whole_stage, selected)
    triggered = []
    for sid, rows in enabled.items():
        checked = {}
        fit_paths = set()
        for key in rows:
            if key not in keys:
                continue
            definition = practice.REQUIREMENTS[key]
            if key in {'tone_contract', 'direction_profile', 'direction_fit'}:
                continue
            if definition['record'] == 'tone_fit_review':
                entry = evidence_ref(state, key, sid)
                if key == 'skeleton_fit':
                    target = checked['core_scene_skeleton']
                else:
                    target = next((checked[name] for name in
                                   ('implementation_walkthrough', 'asset_anchors', 'scene_structure', 'appearance_target')
                                   if name in checked), artifacts)
                path = verify_ref(root, entry).relative_to(root).as_posix()
                require(path not in fit_paths, 'skeleton and increment require separate fit review records')
                fit_paths.add(path)
                fit = check_fit(root, path, target, ref)
                if 'comparison' in definition:
                    check_fit_comparison(root, fit, data, definition['comparison'])
            else:
                entry = evidence_ref(state, key, sid)
                checked[key] = check_record(root, key, sid, entry, ref)
        triggered.extend({'scope': sid, 'requirement': key} for key in rows if key in keys)
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
