"""Synthetic records generated from exact fixture bytes."""
import base64
import json


def png(width=1280, height=800, color=(24, 72, 112)):
    import struct
    import zlib
    def chunk(kind, payload):
        return struct.pack('>I', len(payload)) + kind + payload + struct.pack('>I', zlib.crc32(kind + payload) & 0xffffffff)
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress((b'\0' + bytes(color) * width) * height)) + chunk(b'IEND', b''))


PIXEL = png()


def capture_binding(observed, *, state='Synthetic current screen', viewport='1280x800', root=None, screenshot=None):
    binding=dict(artifacts=observed, pixel_size=[int(x) for x in viewport.split('x')], viewport=viewport,
                 scale=1, state=state, method='synthetic PNG fixture', source='Synthetic deterministic renderer')
    if root is not None and screenshot is not None:
        name=screenshot['path']+'.'+__import__('hashlib').sha256(json.dumps(binding,sort_keys=True).encode()).hexdigest()[:12]+'.capture.json'
        binding['receipt']=put(root,name,dict(binding,screenshot_sha256=screenshot['sha256']))
    return binding


def human_receipt(root, tone, artifacts, *, person='fixture-person', source='synthetic-viewport-response.md'):
    quote='I viewed the actual displayed viewport and approve the recorded observation'
    reply=put(root, source, quote)
    shown=put(root, source+'-display.md', 'Displayed the rendered current view')
    return tone.evidence.review_receipt(root, dict(format='matrix-review-binding/1',request_id=source,
        scope='workspace', actor='user', display=shown, response=dict(reply,message_sha256=tone.evidence.digest(quote)),
        person=person,quote=quote,outcome='approved',artifacts=artifacts))


def approve(root, tone, data, *, person=None, source=None, quote=None):
    approval = data.setdefault('confirmation', {})
    approval.update(person=person or approval.get('person', 'fixture-person'),
                    source=source or approval.get('source', 'synthetic-human.md'),
                    quote=quote or approval.get('quote', 'Synthetic approval'))
    human = put(root, approval['source'], approval['quote'])
    display = put(root, 'synthetic-display.md', 'Synthetic direction shown for review')
    binding = dict(format='matrix-review-binding/1', request_id='synthetic-direction', scope=['workspace'], actor='user',
                   direction_sha256=tone.direction_binding(tone.DEFAULT_PATH, data)['direction_sha256'],
                   display=display, response=dict(human, message_sha256=tone.evidence.digest(approval['quote'])),
                   person=approval['person'], quote=approval['quote'], outcome='approved', artifacts=list(data['parts'].values()))
    approval['direction_sha256'] = binding['direction_sha256']
    approval['review_receipt'] = tone.evidence.review_receipt(root, binding)
    return approval


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
        'viewport':'1280x800', 'capture_binding':capture_binding([parts['preview']],root=root,screenshot=parts['screenshot']),
        'version': '1', 'genre': 'Synthetic project', 'profile': label, 'tone': 'Synthetic direction', 'core_loop': 'Enter and finish',
        'references': [{'name': f'Synthetic reference {i}', 'source': f'Synthetic source {i}',
                        'borrows': 'Readable flow', 'observed': 'Fixture only'} for i in (1, 2)],
        'avoid': ['Omit the main operation'], 'parts': parts,
        'samples': [{'moment': f'Moment {i % 4}', 'text': f'Line {i}', 'consequence': 'Continue the synthetic task'}
                    for i in range(6)],
        'confirmation': {'person': 'fixture-person', 'quote': 'Synthetic approval', 'source': 'synthetic-human.md'},
    }
    approve(root, tone, data)
    return put(root, tone.DEFAULT_PATH, '# Direction\n\n```tone-contract\n' + json.dumps(data) + '\n```\n'), data


def practice_record(root, tone, contract, key, observed, sid='workspace', **extra):
    record = {field: 'Synthetic specific ' + field for field in tone.practice.REQUIREMENTS[key]['fields']}
    record.update(tone_contract=contract, scope=sid, artifacts=observed, **extra)
    if 'screenshot' in record:
        record.setdefault('viewport','1280x800')
        record.setdefault('capture_binding',capture_binding(observed,root=root,screenshot=record['screenshot']))
    if 'manual_review' in record and 'screenshot' not in record:
        record.setdefault('human_review_receipt',human_receipt(root,tone,observed))
    if key == 'playable_prototype':
        record.update(status='completed',environment='Synthetic desktop simulation',
                      run_evidence=put(root,'run-log-'+sid+'.json',dict(status='observed',environment='Synthetic desktop simulation',events=[dict(action='Select start',result='Turn begins',at_ms=0)])),
                      timing_evidence=put(root,'timing-'+sid+'.json',dict(status='observed',environment='Synthetic desktop simulation',measurements=[dict(event='Start feedback',result='Turn appears',started_ms=0,observed_ms=12)])))
    result = put(root, f'{key}-{sid}.json', record)
    result['bundle'] = tone.evidence.seal_bundle(root, [result], {'scope':sid,'requirement':key,'tone_contract':contract})
    return result


def fit_record(root, contract, reviewed, *, record_path='fit.json', **extra):
    fit = dict(tone_contract=contract, outcome='passed', mode='independent', checker='fit', producer='maker',
               artifacts=reviewed, screenshot=put(root, 'fit.png', PIXEL),
               viewport='1280x800', capture_binding=capture_binding(reviewed), capture='fixture', genre_fit='turn remains clear',
               application_drift='none in the fixture', copy_fit='text matched its moment')
    fit.update(extra)
    if 'screenshot' in fit:
        fit['capture_binding']=capture_binding(fit['artifacts'],root=root,screenshot=fit['screenshot'])
    if fit['mode'] == 'human':
        fit.pop('screenshot')
    result = put(root, record_path, fit)
    import importlib.util
    from kit import KIT
    spec=importlib.util.spec_from_file_location('fixture_evidence', KIT/'matrix/base/tools/review_evidence.py')
    evidence=importlib.util.module_from_spec(spec); spec.loader.exec_module(evidence)
    if fit['mode']=='human':
        from types import SimpleNamespace
        fit.setdefault('human_review_receipt',human_receipt(root,SimpleNamespace(evidence=evidence),reviewed,person=fit['checker']))
        result=put(root,record_path,fit)
    # A fit fixture can stand for either historical skeleton or current increment; callers set its role.
    result['bundle'] = evidence.seal_bundle(root, [result], {'scope':'workspace','requirement':'skeleton_fit','tone_contract':contract})
    return result


def review_state(root, gate, paths, *, role='product', stage='P-7', following='complete', scope_ids=None, person=None, prefix='synthetic-stage'):
    scope_ids=scope_ids or ['release']
    refs=gate.digests(root,paths)
    display=put(root,prefix+'-display.md','Displayed all current artifacts: '+', '.join(paths))
    human=put(root,prefix+'-human.md','Confirmed the complete displayed scope')
    request=dict(request_id=prefix,stage=stage,role=role,artifact_sha256=refs['artifact_sha256'],scope=scope_ids,
                 display_evidence=display['path'],display_sha256=display['sha256'])
    response=dict(request_id=prefix,artifact_sha256=refs['artifact_sha256'],scope=scope_ids,actor='user',choice='confirm',
                  source=human['path'],quote='Confirmed the complete displayed scope',
                  display_sha256=display['sha256'],message_sha256=gate.tone.evidence.digest('Confirmed the complete displayed scope'))
    if person:response['person_id']=person
    return dict(role=role,current=stage,next=following,scope=scope_ids,blockers=[],artifacts=refs['artifacts'],
                request=put(root,prefix+'-request.json',request)['path'],response=put(root,prefix+'-response.json',response)['path'],
                conversation_check=put(root,prefix+'-conversation.md',stage+' → '+following)['path'])


def pm_closed_fixture(root, tone, data, *, receipt_root=None, identity='synthetic-approved-direction'):
    """Controller-only synthetic trusted PM record, never a consumer shortcut."""
    import sqlite3
    authority=receipt_root or root
    approval=data['confirmation']
    with sqlite3.connect(authority/'management/runtime/tasks.sqlite3') as db:
        record=dict(id=identity,tasks=[],closed=True,reviewed_direction=tone.direction_binding(tone.DEFAULT_PATH,data),
                    confirmation_receipt=approval['review_receipt'])
        db.execute('INSERT OR REPLACE INTO pm_records VALUES(?,?,?)',('direction_sample',identity,json.dumps(record)))


def design_walkthrough(root, gate, contract, artifacts):
    """Actual synthetic D-6 gate receipt for the current implementation fixture."""
    tone=gate.tone
    walk=practice_record(root,tone,contract,'implementation_walkthrough',artifacts)
    direction=tone.read(root,tone.DEFAULT_PATH)
    fit=fit_record(root,contract,artifacts,record_path='design-walk-fit.json',
                   reference_screenshot=direction['parts']['screenshot'],reference_viewport=direction['viewport'],
                   comparison_state='Synthetic current implementation state')
    state=review_state(root,gate,[item['path'] for item in artifacts],role='design',stage='D-6',following='D-7',
                       scope_ids=['workspace'],prefix='design-walk-review')
    state.update(tone_contract=contract,practice_evidence={'implementation_walkthrough':{'workspace':walk},'increment_fit':{'workspace':fit}})
    result=gate.check(root,state)
    data=json.loads((root/walk['path']).read_text())
    data['design_review']={'bundle':result['review_bundle'],'state_path':result['upstream_state']}
    return put(root,'build-implementation-walkthrough.json',data)


def installed_rule_input(root, kit):
    """A real frozen package instruction for mechanism tests without business requirements."""
    name='matrix/base/MATRIX.md'
    target=root/name
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_bytes((kit/name).read_bytes())
    return name
