#!/usr/bin/env python3
"""Validate a direction sample, its approved tone contract and review evidence."""

import argparse
import hashlib
import json
from pathlib import Path
import re

DEFAULT_PATH = 'product/specs/00-方向样张.md'
PROFILES = {'工具与业务', '游戏与玩乐'}
DESIGN_REVIEWS = {'D-1', 'D-2', 'D-4', 'D-6'}
ENTRY_STAGES = {'P-2', 'D-1', 'CD-1'}


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
    path = file(root, ref.get('path'))
    require(ref.get('sha256') == sha(path.read_bytes()), 'stale artifact: ' + ref['path'])
    return path


def picture(path):
    with path.open('rb') as handle:
        magic = handle.read(12)
    return (magic.startswith((b'\x89PNG\r\n\x1a\n', b'\xff\xd8\xff')) or
            (magic.startswith(b'RIFF') and magic[8:] == b'WEBP'))


def read(root, ref):
    source = file(root, ref).read_text(encoding='utf-8')
    parts = re.findall(r'^\x60\x60\x60tone-contract\s*\n(.*?)^\x60\x60\x60\s*$', source, flags=re.M | re.S)
    require(len(parts) == 1, 'one tone-contract JSON block required')
    data = json.loads(parts[0])
    require(isinstance(data, dict), 'tone contract must be an object')
    return data


def validate(root, ref):
    root = Path(root).resolve()
    data = read(root, ref)
    require(all(text(data.get(k)) for k in ('version', 'genre', 'profile', 'tone', 'core_loop')), 'version, genre, profile, tone and core_loop required')
    require(data['profile'] in PROFILES, 'unknown practice profile')
    examples = data.get('references', [])
    require(isinstance(examples, list) and len(examples) >= 2 and all(
        isinstance(x, dict) and all(text(x.get(k)) for k in ('name', 'borrows', 'observed')) for x in examples),
        'at least two references with borrowed detail and observation status required')
    require(len({x['name'].strip().casefold() for x in examples})==len(examples), 'reference names must be distinct')
    avoid = data.get('avoid', [])
    require(isinstance(avoid, list) and avoid and all(text(x) for x in avoid), 'at least one direction to avoid required')
    parts = data.get('parts', {})
    require(isinstance(parts, dict) and {'brief','scene','samples'} <= set(parts), 'brief, scene and samples required')
    require(set(parts) & {'screenshot','manual_review'}, 'actual screenshot or recorded human viewport review required')
    for part in parts.values():
        require(text(part.get('version')), 'each part requires a version')
        verify_ref(root, part)
    if 'screenshot' in parts:
        require(picture(verify_ref(root, parts['screenshot'])), 'screenshot must be a rendered image')
    else:
        require(text(data.get('capture_unavailable')), 'state why host screenshot is unavailable')
    if data['profile'] == '游戏与玩乐':
        samples = data.get('samples', [])
        require(isinstance(samples, list) and all(isinstance(x, dict) and text(x.get('moment')) and text(x.get('text')) for x in samples),
                'samples must name a moment and text')
        require(len({x['text'].strip() for x in samples}) >= 6 and len({x['moment'].strip() for x in samples}) >= 4,
                'game profile requires six distinct samples across four moments')
    confirmation = data.get('confirmation', {})
    require(all(text(confirmation.get(k)) for k in ('person','quote','source')), 'record confirmer, exact quote and response source')
    require(confirmation['quote'] in file(root, confirmation['source']).read_text(encoding='utf-8'), 'confirmation quote missing from response source')
    return data


def check_fit(root, record, artifacts):
    data = json.loads(file(root, record).read_text(encoding='utf-8'))
    require(data.get('outcome') == 'passed' and text(data.get('checker')) and text(data.get('producer')),
            'a passing fit review with named participants is required')
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
        require(text(data.get('capture_unavailable')), 'record the capture limitation for human viewport inspection')
        source = verify_ref(root, data['manual_review'])
        require(text(source.read_text(encoding='utf-8')), 'human viewport inspection evidence required')
    else:
        screenshot = verify_ref(root, data['screenshot'])
        require(picture(screenshot), 'actual rendered screenshot required for passed fit review')
    require(text(data.get('viewport')) and text(data.get('capture')), 'record viewport and capture method')
    require(all(text(data.get(k)) for k in ('genre_fit','application_drift','copy_fit')),
            'record genre fit, application-like details, and copy fit')
    current={x['path']:x['sha256'] for x in artifacts}
    reviewed = {x['path']:x['sha256'] for x in observed}
    require(current and all(reviewed.get(k)==v for k,v in current.items()),
            'fit review does not cover current artifacts')
    return data


def check_stage(root, state, artifacts):
    ref = state.get('tone_contract')
    profile = state.get('practice_profile')
    current, following = state['current'], state['next']
    relevant = current in ENTRY_STAGES | DESIGN_REVIEWS or following in ENTRY_STAGES
    if not relevant:
        return
    existing = root / DEFAULT_PATH
    if existing.is_file():
        data = read(root, DEFAULT_PATH)
        declared = data.get('profile')
        require(not profile or declared == profile, 'practice profile differs from project contract')
        profile = declared
    if not (ref or profile and profile != '工具与业务'):
        return
    require(isinstance(ref, dict) and ref.get('path') == DEFAULT_PATH, 'reference the current tone contract and its version')
    verify_ref(root, ref)
    data = validate(root, DEFAULT_PATH)
    require(data['version']==ref.get('version') and (not profile or data['profile']==profile), 'tone contract version or profile changed')
    if data['profile'] != '工具与业务':
        if current == 'P-1':
            reviewed = [data['parts'][key] for key in ('scene','samples')]
            check_fit(root, state.get('tone_fit_review'), reviewed)
            response = json.loads(file(root, state.get('response')).read_text(encoding='utf-8'))
            confirmation = data['confirmation']
            require(confirmation['source'] == response.get('source'), 'direction confirmation must cite the P-1 response')
            if response.get('person_id'):
                require(confirmation['person'] == response['person_id'], 'direction confirmer differs from P-1 confirmation')
        elif current in DESIGN_REVIEWS:
            check_fit(root, state.get('tone_fit_review'), artifacts)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, required=True)
    parser.add_argument('--contract', default=DEFAULT_PATH)
    args = parser.parse_args()
    try:
        record = validate(args.project, args.contract)
    except (ValueError, OSError, KeyError, TypeError, AttributeError) as error:
        print(json.dumps({'allowed':False,'error':str(error)}, ensure_ascii=False))
        return 1
    print(json.dumps({'allowed':True, 'version':record['version']}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
