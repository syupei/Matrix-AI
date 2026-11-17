"""Synthetic records generated from exact fixture bytes."""
import base64
import json


PIXEL = base64.b64decode(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+j/DcAAAAASUVORK5CYII='
)


def put(root, name, value, version='1'):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(value, dict):
        value = json.dumps(value, ensure_ascii=False)
    data = value.encode() if isinstance(value, str) else value
    path.write_bytes(data)
    return {'path': name, 'version': version, 'sha256': __import__('hashlib').sha256(data).hexdigest()}


def scope(tone, sid='workspace', **values):
    return {
        'id': sid, 'description': 'Synthetic activity ' + sid,
        'features': {key: {'value': values.get(key, 'no'), 'basis': 'Synthetic scope grounds ' + key}
                     for key in tone.practice.FEATURES},
        'practices': {key: {'approach': 'Walk the synthetic activity', 'pitfall': 'Skip a case',
                            'check': 'Exercise the declared activity'} for key in tone.practice.PROFESSIONS},
    }


def direction(root, tone, rows=None, *, label='Synthetic operations'):
    profile = {'schema': tone.practice.SCHEMA, 'version': '1', 'scopes': rows or [scope(tone)]}
    parts = {
        'practice_profile': put(root, 'practice.json', profile),
        'brief': put(root, 'direction-brief.md', 'Synthetic requirement'),
        'scene': put(root, 'direction-scene.html', '<body>Synthetic scene</body>'),
        'samples': put(root, 'direction-copy.md', 'Synthetic copy samples'),
        'screenshot': put(root, 'direction.png', PIXEL),
    }
    parts['preview'] = parts['scene']
    data = {
        'version': '1', 'genre': 'Synthetic project', 'profile': label, 'tone': 'Synthetic direction', 'core_loop': 'Enter and finish',
        'references': [{'name': f'Synthetic reference {i}', 'source': f'Synthetic source {i}',
                        'borrows': 'Readable flow', 'observed': 'Fixture only'} for i in (1, 2)],
        'avoid': ['Omit the main operation'], 'parts': parts,
        'samples': [{'moment': f'Moment {i % 4}', 'text': f'Line {i}', 'consequence': 'Continue the synthetic task'}
                    for i in range(6)],
        'confirmation': {'person': 'fixture-person', 'quote': 'Synthetic approval', 'source': 'synthetic-human.md'},
    }
    put(root, 'synthetic-human.md', 'Synthetic approval')
    return put(root, tone.DEFAULT_PATH, '# Direction\n\n```tone-contract\n' + json.dumps(data) + '\n```\n'), data


def practice_record(root, tone, contract, key, observed, sid='workspace', **extra):
    record = {field: 'Synthetic specific ' + field for field in tone.practice.REQUIREMENTS[key]['fields']}
    record.update(tone_contract=contract, scope=sid, artifacts=observed, **extra)
    return put(root, f'{key}-{sid}.json', record)


def fit_record(root, contract, reviewed, *, record_path='fit.json', **extra):
    fit = dict(tone_contract=contract, outcome='passed', mode='independent', checker='fit', producer='maker',
               artifacts=reviewed, screenshot=put(root, 'fit.png', PIXEL),
               viewport='1280x800', capture='fixture', genre_fit='turn remains clear',
               application_drift='none in the fixture', copy_fit='text matched its moment')
    fit.update(extra)
    if fit['mode'] == 'human':
        fit.pop('screenshot')
    return put(root, record_path, fit)
