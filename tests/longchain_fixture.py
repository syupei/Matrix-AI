"""Synthetic public-CLI fixtures for the complete consumer stage chain."""
import copy
import hashlib
import importlib.util
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

sys.dont_write_bytecode = True
from kit import KIT
import subprocess

spec = importlib.util.spec_from_file_location('c_stage_gate', KIT / 'matrix/base/tools/stage_gate.py')
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)
tone = gate.tone
practice = tone.practice
ev = tone.evidence


def png(w=1280, h=800, color=(24, 72, 112)):
    import struct, zlib
    def chunk(kind, payload):
        return struct.pack('>I', len(payload)) + kind + payload + struct.pack('>I', zlib.crc32(kind + payload) & 0xffffffff)
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress((b'\0' + bytes(color) * w) * h)) + chunk(b'IEND', b''))


_colour = [0]


def shotpng():
    """A distinct decodable PNG per call (stage pictures may not reuse bytes across sources)."""
    _colour[0] += 1
    n = _colour[0]
    return png(color=((n * 37) % 256, (n * 91) % 256, (n * 53 + 7) % 256))



def put(root, name, value, version=None):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False)
    data = value.encode() if isinstance(value, str) else value
    path.write_bytes(data)
    result = {'path': name, 'sha256': hashlib.sha256(data).hexdigest()}
    if version is not None:
        result['version'] = version
    return result


def ref(r):
    return {'path': r['path'], 'sha256': r['sha256']}


def capture(root, observed, shot, *, viewport='1280x800', state='representative state', method='headless browser capture'):
    w, h = (int(x) for x in viewport.split('x'))
    binding = dict(artifacts=[ref(x) for x in observed], pixel_size=[w, h], viewport=viewport, scale=1,
                   state=state, method=method, source='local build')
    tag = hashlib.sha256(json.dumps(binding, sort_keys=True).encode()).hexdigest()[:10]
    receipt = put(root, shot['path'] + '.' + tag + '.capture.json', dict(binding, screenshot_sha256=shot['sha256']))
    binding['receipt'] = ref(receipt)
    return binding


def user_receipt(root, rid, artifacts, *, person='owner', reply='I viewed the displayed state and approve it',
                 scope='board', actor='user', extra=None):
    display = put(root, f'management/reviews/{rid}-display.md', 'Displayed: ' + ', '.join(a['path'] for a in artifacts) + ' direction ' + (extra or {}).get('direction_sha256',''))
    answer = put(root, f'management/reviews/{rid}-reply.md', reply)
    binding = dict(format='matrix-review-binding/1', request_id=rid, scope=scope, actor=actor, display=ref(display),
                   response=dict(ref(answer), message_sha256=ev.digest(reply)), person=person, quote=reply,
                   outcome='approved', artifacts=[ref(a) for a in artifacts])
    binding.update(extra or {})
    binding_path = put(root, f'management/reviews/{rid}-binding.json', binding)
    run = subprocess.run([sys.executable, '-B', str(KIT/'matrix/base/tools/review_evidence.py'), '--project', str(root), '--review-binding', binding_path['path']], text=True, capture_output=True)
    if run.returncode: raise ValueError(run.stdout + run.stderr)
    return json.loads(run.stdout)['review_receipt']


def feature_scope(sid='board', **values):
    return {
        'id': sid, 'description': 'Activity ' + sid,
        'features': {k: {'value': values.get(k, 'no'), 'basis': 'Concrete business grounds for ' + k}
                     for k in practice.FEATURES},
        'practices': {k: {'approach': 'Specific approach', 'pitfall': 'Specific pitfall', 'check': 'Specific check'}
                      for k in practice.PROFESSIONS},
    }


def direction(root, rows, *, label='Board race', genre='Board game', person='owner', version='1', reply=None, rid='P1'):
    profile = {'schema': practice.SCHEMA, 'version': version, 'scopes': rows}
    parts = {
        'practice_profile': put(root, 'product/specs/practice-profile.json', profile, version),
        'brief': put(root, 'product/specs/brief.md', 'Brief: race pawns around the board', '1'),
        'scene': put(root, 'design/direction/preview.html', '<main><svg><rect/></svg>Board scene with pawns</main>', '1'),
        'samples': put(root, 'content/direction-samples.md', 'Sample lines', '1'),
        'screenshot': put(root, 'design/direction/preview.png', png(color=(10, 90, 40)), '1'),
    }
    parts['preview'] = parts['scene']
    data = {
        'viewport': '1280x800',
        'capture_binding': capture(root, [parts['preview']], parts['screenshot'], state='turn start'),
        'version': version, 'genre': genre, 'profile': label, 'tone': 'Warm wooden board', 'core_loop': 'Roll, move, capture',
        'references': [{'name': f'Ref {i}', 'source': f'https://example.test/board-game-{i}', 'borrows': 'Board readability',
                        'observed': 'not observed'} for i in (1, 2)],
        'avoid': ['Form-like control panels'], 'parts': parts,
        'samples': [{'moment': f'Moment {i % 4}', 'text': f'Line {i}', 'consequence': 'Next action'} for i in range(6)],
    }
    return confirm_direction(root, data, person=person, reply=reply or ('I approve this complete direction v' + version), rid=rid)


def confirm_direction(root, data, *, person='owner', reply='I approve this complete direction', rid='P1'):
    data = copy.deepcopy(data)
    data.pop('confirmation', None)
    sha = tone.direction_binding(tone.DEFAULT_PATH, data)['direction_sha256']
    rows = json.loads((root / data['parts']['practice_profile']['path']).read_text())['scopes']
    receipt = user_receipt(root, rid, list(data['parts'].values()), person=person, reply=reply,
                           scope=[r['id'] for r in rows], extra={'direction_sha256': sha, 'direction_draft': ref(write_contract(root, data))})
    data['confirmation'] = {'person': person, 'quote': reply, 'source': f'management/reviews/{rid}-reply.md',
                            'direction_sha256': sha, 'review_receipt': receipt}
    return write_contract(root, data), data


def write_contract(root, data):
    r = put(root, tone.DEFAULT_PATH, '# Direction\n\n```tone-contract\n' + json.dumps(data, ensure_ascii=False) + '\n```\n')
    return {'path': r['path'], 'version': data['version'], 'sha256': r['sha256']}


def logs(root, name, observed, stage):
    run_ = ref(put(root, name + '.run.json', dict(status='observed', environment='Desktop Chrome', stage=stage,
                                                 artifacts=[ref(a) for a in observed],
                                                 events=[dict(action='Click die', result='Die rolls', at_ms=0),
                                                         dict(action='Click pawn', result='Pawn moves', at_ms=900)])))
    timing = ref(put(root, name + '.timing.json', dict(status='observed', environment='Desktop Chrome', stage=stage,
                                                      artifacts=[ref(a) for a in observed],
                                                      measurements=[dict(event='Click feedback', result='Highlight', started_ms=0, observed_ms=40)])))
    return run_, timing


def record(root, key, contract, observed, name, *, sid='board', shot=None, fill=None, stage='E-2.2', **extra):
    body = {f: (fill or {}).get(f, 'Specific ' + f) for f in practice.REQUIREMENTS[key].get('fields', ())}
    body.update(tone_contract=contract, scope=sid, artifacts=[ref(a) for a in observed])
    if shot is not None:
        body.update(screenshot=ref(shot), viewport='1280x800', capture_binding=capture(root, observed, shot))
    if key == 'implementation_walkthrough':
        obs = put(root, name + '.observation.json', dict(state='Pawn selected', result='HUD retained'))
        body.update(preserved_states=[dict(state='Current player', layer='HUD', basis='Needed to choose the next move')],
                    design_recheck_states=[dict(state='Pawn selected', method='Read the rendered selection', evidence=ref(obs))],
                    corrections=[])
    if key == 'playable_prototype':
        run_, timing = logs(root, name, observed, stage)
        body.update(status='completed', environment='Desktop Chrome 1280x800', run_evidence=run_, timing_evidence=timing)
        if stage.startswith('E-2.'):
            body.update(playtest_status='pending')
        else:
            src = put(root, name + '.participant.md', 'Participant rolled the die and moved a pawn; the highlight was readable')
            body.update(playtest_status='observed', playtest_evidence=ref(put(root, name + '.playtest.json', dict(
                status='observed', environment='Desktop Chrome', artifacts=[ref(a) for a in observed],
                sessions=[dict(player='Participant A', source=ref(src), observations=['Recognised the pawn that moved'])]))))
    body.update(extra)
    return ref(put(root, name, body))


def fit(root, contract, observed, name, *, shot, direction_data, mode='same_instance', checker='me',
        producer='me', comparison=True, **extra):
    body = dict(tone_contract=contract, outcome='passed', mode=mode, checker=checker, producer=producer,
                artifacts=[ref(a) for a in observed], viewport='1280x800', capture='headless browser',
                genre_fit='Board remains the centre', application_drift='No form controls', copy_fit='Lines match moments')
    if shot is not None:
        body.update(screenshot=ref(shot), capture_binding=capture(root, observed, shot))
    if comparison:
        body.update(reference_screenshot=ref(direction_data['parts']['screenshot']), reference_viewport='1280x800',
                    comparison_state='Turn start, die ready')
    body.update(extra)
    return ref(put(root, name, body))


def conv(root, current, nxt, name='management/conversation.md'):
    put(root, name, f'{current} → {nxt}')
    return name


def stage(root, role, current, nxt, contract, artifacts, evidence=None, scope=('board',), **extra):
    s = dict(role=role, current=current, next=nxt, scope=list(scope), blockers=[],
             artifacts=[ref(a) for a in artifacts], conversation_check=conv(root, current, nxt),
             tone_contract=contract, practice_evidence=copy.deepcopy(evidence or {}))
    s.update(extra)
    return s


def human_stage(root, s, rid, *, reply=None, person=None):
    reply = reply or ('Confirmed the complete displayed scope ' + rid)
    digest = gate.artifact_digest(root, s['artifacts'])
    display = put(root, f'management/reviews/{rid}-stage-display.md', 'Displayed ' + ', '.join(a['path'] for a in s['artifacts']))
    answer = put(root, f'management/reviews/{rid}-stage-reply.md', reply)
    request = dict(request_id=rid, stage=s['current'], role=s['role'], artifact_sha256=digest, scope=s['scope'],
                   display_evidence=display['path'], display_sha256=display['sha256'])
    response = dict(request_id=rid, artifact_sha256=digest, scope=s['scope'], actor='person' if person else 'user',
                    choice='confirm', source=answer['path'], quote=reply, display_sha256=display['sha256'],
                    message_sha256=ev.digest(reply))
    if person:
        response['person_id'] = person
    s['request'] = put(root, f'management/reviews/{rid}-request.json', request)['path']
    s['response'] = put(root, f'management/reviews/{rid}-response.json', response)['path']
    return s


def run(label, fn, *args, **kw):
    try:
        result = fn(*args, **kw)
        brief = result.get('framework', {}).get('triggered', result.get('triggered', '')) if isinstance(result, dict) else result
        print(f'[{label}] ALLOWED', json.dumps(brief, ensure_ascii=False)[:200])
        return result if result is not None else True
    except (ValueError, KeyError, TypeError, OSError, AttributeError) as error:
        print(f'[{label}] BLOCKED {type(error).__name__}: {str(error)[:300]}')
        return None


def frozen(root, result):
    view, _ = ev.stage_receipt(root, result['review_bundle'])
    return view, json.loads(ev.file(view, result['upstream_state']).read_text())
