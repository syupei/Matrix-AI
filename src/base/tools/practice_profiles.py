"""Resolve the fixed, content-based obligations shared by professional stages."""

import hashlib
import json
from pathlib import Path
import re


SCHEMA = 'matrix-practice-profile/1'
ASSET_PLACEHOLDERS = {'无', 'none', 'n/a', 'na', '-', '稍后', '待补', '待补充', '待对照', '待比较',
                      'todo', 'tbd', 'to be compared', 'compare later', 'pending', '待定', '不适用', '同上', '以后再看', '稍后对照'}
FEATURES = (
    'scene_centered', 'appearance_target', 'asset_family', 'direct_manipulation',
    'continuous_animation', 'timing_feedback', 'traffic_peak',
)
PROFESSIONS = (
    'product', 'experience-design', 'content-design', 'code-engineering', 'quality-engineering',
)
EXAMPLE = Path(__file__).resolve().parent.parent / 'practice-profile-example-game.json'
MOTION = ('direct_manipulation', 'continuous_animation', 'timing_feedback')
VISUAL = ('appearance_target', *MOTION)
FIT_COMPARISON = {
    'fields': ('reference_viewport', 'comparison_state'),
    'reference': ('reference_screenshot', 'reference_manual_review'),
}

# Conditions are a fixed OR over declared features, never expressions from project data.
# A record with fields is scoped JSON with those observations and actual artifact references.
REQUIREMENTS = {
    'tone_contract': {'features': (), 'record': 'tone_contract', 'template': 'matrix/base/tone-contract-template.md', 'version': 4},
    'direction_profile': {'features': (), 'record': 'practice_profile', 'version': 3},
    'direction_fit': {'features': (), 'record': 'tone_fit_review', 'version': 4},
    'direction_contribution': {'features': (), 'record': 'direction_contribution',
                               'fields': ('contribution', 'profile_check'), 'version': 1},
    'appearance_target': {'features': ('appearance_target',), 'record': 'appearance_target',
                          'fields': ('visual_features', 'anchor', 'comparison'), 'version': 1},
    'scene_structure': {'features': ('scene_centered',), 'record': 'scene_structure',
                        'fields': ('core_activity', 'operation_locations', 'comparison'), 'version': 1},
    'design_fit': {'features': ('scene_centered', 'appearance_target'), 'record': 'tone_fit_review', 'version': 3},
    'asset_anchors': {'features': ('asset_family',), 'record': 'asset_anchors',
                      'fields': ('scene_comparison', 'series_production'),
                      'comparison': {'fields': ('confirmed_features','rows','review_page','scene_sample'),
                                     'row_fields': ('feature','reference','reference_observation','anchor','anchor_observation','status','difference'),
                                     'statuses': ('achieved','close','unmet')},
                      'submission': {'command':'tone_contract.py --asset-comparison',
                                     'receipt':'asset-comparison-receipt/1','before':'anchor review',
                                     'display':'receipt page or embedded receipt pages',
                                     'artifacts':'review pages, scene samples, anchors and declared deliverables; capture receipts remain verified evidence',
                                     'unmet':'reviewable, not releasable'}, 'version': 6},
    'asset_fit': {'features': ('asset_family',), 'record': 'tone_fit_review', 'version': 3},
    'implementation_walkthrough': {'features': VISUAL, 'record': 'implementation_walkthrough',
                                    'fields': ('locations', 'activity_effect', 'preservation_basis', 'recheck_method'),
                                    'structured': {'preserved_states': ('state','layer','basis'),
                                                   'design_recheck_states': ('state','method'),
                                                   'corrections': ('location','type','destination')},
                                    'design_review_stages': ('E-3.2',), 'version': 3},
    'rendering_choice': {'features': VISUAL, 'record': 'rendering_choice',
                         'fields': ('options', 'chosen', 'product_impact'), 'version': 1},
    'appearance_proof': {'features': VISUAL, 'record': 'appearance_proof',
                         'fields': ('candidate_technology', 'core_scene', 'comparison'), 'version': 3},
    'playable_prototype': {'features': MOTION, 'record': 'playable_prototype',
                           'fields': ('play_instructions', 'timing', 'interruption', 'performance_budget', 'playtest', 'environment'), 'version': 3},
    'load_test_plan': {'features': ('traffic_peak',), 'record': 'load_test_plan',
                       'fields': ('target', 'basis', 'scenario'), 'version': 1},
    'core_scene_skeleton': {'features': ('appearance_target',), 'record': 'core_scene_skeleton',
                            'fields': ('core_scene', 'run_instructions'), 'version': 3},
    'skeleton_fit': {'features': ('appearance_target',), 'record': 'tone_fit_review',
                     'comparison': FIT_COMPARISON, 'version': 4},
    'increment_fit': {'features': VISUAL, 'record': 'tone_fit_review',
                      'comparison': FIT_COMPARISON, 'version': 4},
    'direction_acceptance_plan': {'features': ('appearance_target',), 'record': 'direction_acceptance_plan',
                                  'fields': ('direction_comparison', 'screenshot_plan'), 'version': 1},
    'motion_acceptance_plan': {'features': MOTION, 'record': 'motion_acceptance_plan',
                               'fields': ('recording_plan', 'timing', 'playtest_script'), 'version': 1},
    'load_acceptance_plan': {'features': ('traffic_peak',), 'record': 'load_acceptance_plan',
                             'fields': ('target', 'workload', 'pass_criteria'), 'version': 1},
}


def nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def require(condition, message):
    if not condition:
        raise ValueError(message)


def canonical(data):
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()


def digest(data):
    return hashlib.sha256(canonical(data)).hexdigest()


def load_example():
    return json.loads(EXAMPLE.read_text(encoding='utf-8'))


def validate(data, verify_ref):
    require(isinstance(data, dict) and data.get('schema') == SCHEMA and nonempty(data.get('version')),
            'current project practice profile schema and version required')
    rows = data.get('scopes')
    require(isinstance(rows, list) and rows, 'practice profile must name activity scopes')
    seen = set()
    for scope in rows:
        require(isinstance(scope, dict) and nonempty(scope.get('id'))
                and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}', scope['id'])
                and nonempty(scope.get('description')), 'each scope needs an id and business description')
        sid = scope['id']
        require(sid not in seen, 'duplicate activity scope: ' + sid)
        seen.add(sid)
        features = scope.get('features')
        require(isinstance(features, dict) and set(features) == set(FEATURES),
                sid + ': all seven practice features are required; unknown fields are rejected')
        for name, declaration in features.items():
            require(isinstance(declaration, dict) and set(declaration) == {'value', 'basis'}
                    and declaration['value'] in ('yes', 'no', 'pending') and nonempty(declaration['basis']),
                    sid + ': practice feature needs yes/no/pending and business grounds: ' + name)
            require(not re.fullmatch(r'<[^>]+>|TODO|TBD|pending|待定|待填', declaration['basis'].strip(), re.I),
                    sid + ': replace template placeholder with concrete business grounds: ' + name)
        practices = scope.get('practices')
        require(isinstance(practices, dict) and set(practices) == set(PROFESSIONS),
                sid + ': project-specific practice is needed for each participating profession')
        for profession, practice in practices.items():
            require(isinstance(practice, dict) and set(practice) == {'approach', 'pitfall', 'check'}
                    and all(nonempty(value) for value in practice.values()),
                    sid + ': approach, pitfall and check required for ' + profession)
        if 'example' in scope:
            validate_example(scope, verify_ref)
    return data


def validate_example(scope, verify_ref):
    adopted = scope['example']
    example = load_example()
    require(isinstance(adopted, dict) and adopted.get('id') == example['id'],
            'unknown practice profile example')
    deviations = adopted.get('deviations', {})
    expected = example['scopes'][0]['features']
    changed = {key for key in FEATURES if scope['features'][key]['value'] != expected[key]['value']}
    require(isinstance(deviations, dict) and set(deviations) == changed,
            'explain and review every changed feature of the adopted practice example')
    for name, record in deviations.items():
        require(isinstance(record, dict) and set(record) == {'reason', 'master_review'}
                and nonempty(record['reason']), 'example change needs a business reason: ' + name)
        path = verify_ref(record['master_review'])
        require(nonempty(path.read_text(encoding='utf-8')), 'example change needs professional review: ' + name)


def select_scopes(profile, selection=None):
    scopes = {row['id']: row for row in profile['scopes']}
    if selection is None:
        return scopes
    require(isinstance(selection, list) and selection and all(nonempty(x) for x in selection)
            and len(set(selection)) == len(selection) and set(selection) <= set(scopes),
            'practice scopes must be unique activity ids from the current profile')
    return {key: scopes[key] for key in selection}


def active(profile, requirements, selection=None, *, preview=False):
    """Return the requirements active in each selected scope."""
    result = {}
    for sid, scope in select_scopes(profile, selection).items():
        selected = []
        for key in requirements:
            when = REQUIREMENTS[key]['features']
            values = scope['features']
            pending = [name for name in when if values[name]['value'] == 'pending']
            if not preview:
                require(not pending, sid + ': unresolved practice feature(s): ' + ', '.join(pending))
            if not when or any(values[name]['value'] == 'yes' for name in when):
                selected.append(key)
        result[sid] = selected
    return result


def stage_requirements(registry):
    rows = registry.get('framework_requirements', {})
    stages = {stage for flow in registry.get('stage_flows', []) for stage in flow.get('stages', ())}
    require(isinstance(rows, dict) and rows.keys() <= stages, 'framework requirements use registered stages')
    for stage, phases in rows.items():
        require(isinstance(phases, dict) and phases and phases.keys() <= {'entry', 'complete'},
                'framework stage requires entry or complete declarations: ' + stage)
        for keys in phases.values():
            require(isinstance(keys, list) and keys and all(key in REQUIREMENTS for key in keys)
                    and len(keys) == len(set(keys)), 'invalid or duplicate framework requirement: ' + stage)
    return rows


def professional_contract(registry):
    phases = stage_requirements(registry)
    rows = [
        {'stage': stage, 'requirement': key, 'phases': [phase for phase in ('entry', 'complete')
                                                       if key in declared.get(phase, ())],
         'definition': REQUIREMENTS[key]}
        for stage, declared in sorted(phases.items())
        for key in sorted({key for keys in declared.values() for key in keys})
    ]
    flow_fields = ('key', 'stages', 'review', 'authority', 'authority_rank', 'upstream', 'inherit_upstream')
    body = {
        'schema': 'matrix-expert-framework/1', 'profession': registry['id'],
        'stages': [{key: flow[key] for key in flow_fields if key in flow} for flow in registry.get('stage_flows', [])],
        'inputs': registry.get('inputs', []), 'interfaces': registry.get('interfaces', []),
        'requirements': rows,
    }
    if any(row['requirement']=='tone_contract' for row in rows):
        template=Path(__file__).resolve().parents[1]/'tone-contract-template.md'
        body['templates']={'tone_contract':{'path':REQUIREMENTS['tone_contract']['template'],
                                              'sha256':hashlib.sha256(template.read_bytes()).hexdigest()}}
    return dict(body, sha256=digest(body))
