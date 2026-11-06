"""Instance configuration, derivation, levels, reassignment, conflicts and check independence.
Mechanism tests only: every person, model name, endpoint and check is SIMULATED."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest

from kit import KIT
SOURCE = KIT
spec = importlib.util.spec_from_file_location('pm_instances_under_test', SOURCE / 'matrix/orchestration/tools/pm_tasks.py')
pm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pm)
REGISTRIES = {r['id']: r for r in (json.loads(p.read_text(encoding='utf-8')) for p in (SOURCE / 'matrix/professions').glob('*/profession.json'))}
ALL_CAPABILITIES = sorted({c for r in REGISTRIES.values() for c in r.get('model_capabilities', [])})
MODELS = {'models': [
    {'model': 'SIM-big', 'levels': {p: r['levels']['range'][1] for p, r in REGISTRIES.items()}, 'capabilities': ALL_CAPABILITIES, 'filled_by': 'SIMULATED person'},
    {'model': 'SIM-small', 'levels': {'code-engineering': 'T5', 'quality-engineering': 'T5'}, 'capabilities': ALL_CAPABILITIES, 'filled_by': 'SIMULATED tool'},
    {'model': 'SIM-blind', 'levels': {'experience-design': 'T8'}, 'capabilities': [c for c in ALL_CAPABILITIES if c != '能看图'], 'filled_by': 'SIMULATED person'},
    {'model': 'SIM-nocaps', 'levels': {'code-engineering': 'T9'}, 'filled_by': 'SIMULATED person'}]}
TEAM = {'entries': [
    {'id': 'E-T9', 'profession': 'code-engineering', 'level': 'T9', 'model': 'SIM-big', 'count': 1, 'master': True},
    {'id': 'E-T4', 'profession': 'code-engineering', 'level': 'T4', 'model': 'SIM-small', 'count': 2},
    {'id': 'Q-T7', 'profession': 'quality-engineering', 'level': 'T7', 'model': 'SIM-big', 'count': 1, 'master': True},
    {'id': 'Q-T5', 'profession': 'quality-engineering', 'level': 'T5', 'model': 'SIM-small', 'count': 1},
    {'id': 'P-T7', 'profession': 'product', 'level': 'T7', 'model': 'SIM-big', 'count': 1, 'master': True}]}


class Fixture:
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix='pm-instances-simulation-')
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        (self.root / 'management').mkdir(parents=True, exist_ok=True)
        self.n = 0
        self.call('init', 'PM', config=dict(project='SIMULATED', pm_actor='PM', authorization='SIMULATED only',
                                             frontdoor_id='SIMULATED', max_slots=8))
        self.write('model-fit.json', MODELS)

    def write(self, name, data):
        (self.root / 'management' / name).write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')

    def call(self, op, actor='PM', **kw):
        self.n += 1
        return pm.execute(self.root, dict(op=op, actor=actor, event_id='SIM-' + str(self.n), **kw))

    def team(self):
        return pm.execute(self.root, {'op': 'team'})

    def confirm(self, choices=None, actor='PM', **kw):
        rec = self.team()['instance_config']['confirmed']
        fields = dict(person='SIM-owner', quote='SIMULATED: 就按这个配置', presented_ref='SIM shown configuration', choices=choices or {})
        fields.update(kw)
        return self.call('confirm_config', actor, expected_revision=rec['revision'] if rec else None, **fields)

    def derive(self, entry, **kw):
        self.n += 1
        return self.call('derive', entry=entry, endpoint='SIM-host-handle-' + str(self.n), **kw)['record']['id']

    def staff(self, config=TEAM):
        self.write('instance-config.json', config)
        self.confirm()
        return [self.derive(e['id']) for e in config['entries'] for _ in range(e['count'])]

    def t(self, tid):
        return next(t for t in pm.execute(self.root, {'op': 'status'})['tasks'] if t['id'] == tid)

    def instance(self, iid):
        return pm.execute(self.root, {'op': 'status'})['integrity']['instance'][iid]

    def create(self, tid, parent=None, actor=None, **kw):
        data = dict(id=tid, parent=parent, title='SIM ' + tid, owner='code-engineering-001', checker='quality-engineering-001',
                    goal='SIMULATED delivery', inputs=['SIM v1'], outputs=['SIM output'], criteria=['SIM correct'], next_action='SIM next')
        data.update(kw)
        data.setdefault('executor', data['owner'])
        return self.call('create', actor or ('PM' if parent is None else self.t(parent)['owner']), task=data)

    def mutate(self, op, tid, actor=None, **kw):
        t = self.t(tid)
        return self.call(op, actor or t['owner'], task_id=tid, expected_revision=t['revision'], **kw)

    def check(self, tid, checker=None, outcome='passed', **kw):
        t = self.t(tid)
        if not t['evidence']:
            self.mutate('update', tid, changes={'evidence': ['SIMULATED work ' + tid]}, reason='SIM work')
        return self.mutate('review', tid, checker or self.t(tid)['checker'], outcome=outcome, criteria_checked=t['criteria'],
                           evidence=['SIMULATED check; no real verification'], **kw)

    def close(self, tid):
        return self.mutate('transition', tid, self.t(tid)['manager'], state='done', reason='SIM accepted')


class Configuration(Fixture, unittest.TestCase):
    def test_entries_are_validated_against_the_registries(self):
        bad = [({'id': 'A', 'profession': 'astrology', 'level': 'T4', 'model': 'M', 'count': 1}, 'registry id'),
               ({'id': 'A', 'profession': 'code-engineering', 'level': 'T1', 'model': 'M', 'count': 1}, 'level outside'),
               ({'id': 'A', 'profession': 'code-engineering', 'level': 'T4', 'model': 'M', 'count': -1}, 'count'),
               ({'id': 'A', 'profession': 'code-engineering', 'level': 'T4', 'model': 'M', 'count': True}, 'count'),
               ({'id': 'A', 'profession': 'code-engineering', 'level': 'T7', 'model': 'M', 'count': 2, 'master': True}, 'count 1'),
               ({'id': 'A', 'profession': 'code-engineering', 'level': 'T6', 'model': 'M', 'count': 1, 'master': True}, 'at least T7'),
               ({'id': 'A', 'profession': 'code-engineering', 'level': 'T4', 'model': '', 'count': 1}, 'model name'),
               ({'id': 'A', 'profession': 'code-engineering', 'level': 'T4', 'model': 'M', 'count': 1, 'note': 'x'}, 'entry fields')]
        for entry, message in bad:
            self.write('instance-config.json', {'entries': [entry]})
            with self.assertRaisesRegex(pm.TaskError, message):
                self.confirm()
        twice = dict(id='A', profession='product', level='T7', model='SIM-big', count=1, master=True)
        self.write('instance-config.json', {'entries': [twice, dict(twice, id='B')]})
        with self.assertRaisesRegex(pm.TaskError, 'at most one master'):
            self.confirm()
        self.write('instance-config.json', {'entries': [twice, dict(twice, master=False)]})
        with self.assertRaisesRegex(pm.TaskError, 'unique'):
            self.confirm()
        self.write('instance-config.json', {'entries': []})  # no entries: single conversation
        self.assertEqual([], self.confirm()['record']['entries'])

    def test_three_fit_results_and_the_confirmation_refusals(self):
        self.write('instance-config.json', {'entries': [
            {'id': 'OK', 'profession': 'code-engineering', 'level': 'T4', 'model': 'SIM-small', 'count': 1},
            {'id': 'LOW', 'profession': 'code-engineering', 'level': 'T9', 'model': 'SIM-small', 'count': 1, 'master': True},
            {'id': 'BLIND', 'profession': 'experience-design', 'level': 'T5', 'model': 'SIM-blind', 'count': 1},
            {'id': 'NEW', 'profession': 'product', 'level': 'T5', 'model': 'SIM-unlisted', 'count': 1},
            {'id': 'NOCAPS', 'profession': 'code-engineering', 'level': 'T5', 'model': 'SIM-nocaps', 'count': 1}]})
        preview = {e['id']: e['fit'] for e in self.team()['instance_config']['entries']}
        self.assertEqual({'OK': 'fit', 'LOW': 'unfit', 'BLIND': 'unfit', 'NEW': 'unregistered', 'NOCAPS': 'unregistered'}, preview)
        with self.assertRaises(pm.TaskError) as refused:
            self.confirm()
        message = str(refused.exception)
        self.assertIn('LOW: model SIM-small fits code-engineering up to T5, below the configured T9', message)
        self.assertIn('BLIND: model SIM-blind fits experience-design up to T8; lacks 能看图', message)
        self.assertEqual(2, message.count('change the model, lower the level, or insist'))
        self.assertIn('NEW: model SIM-unlisted is not registered', message)
        self.assertIn('NOCAPS', message)
        choices = {'LOW': 'insist', 'BLIND': 'insist', 'NEW': 'acknowledge_unregistered', 'NOCAPS': 'acknowledge_unregistered'}
        with self.assertRaisesRegex(pm.TaskError, 'LOW'):
            self.confirm(dict(choices, LOW='acknowledge_unregistered'))
        with self.assertRaisesRegex(pm.TaskError, 'no choice applies'):
            self.confirm(dict(choices, OK='insist'))
        record = self.confirm(choices)['record']
        flags = {e['id']: (e['fit'], e['insisted']) for e in record['entries']}
        self.assertEqual(('unfit', True), flags['LOW'])
        self.assertEqual(('unregistered', False), flags['NEW'])
        self.assertEqual(('fit', False), flags['OK'])
        derived = {e: self.instance(self.derive(e))['fit'] for e in ['OK', 'LOW', 'NEW']}
        self.assertEqual({'OK': 'fit', 'LOW': 'unfit_insisted', 'NEW': 'unregistered'}, derived)

    def test_confirmation_is_current_only_while_the_file_is_unchanged(self):
        self.write('instance-config.json', TEAM)
        record = self.confirm()['record']
        self.assertTrue(self.team()['instance_config']['current'])
        self.assertEqual('SIM-owner', record['person'])
        self.assertEqual(64, len(record['sha256']))
        self.write('instance-config.json', dict(TEAM, entries=TEAM['entries'][:1]))
        self.assertFalse(self.team()['instance_config']['current'])
        with self.assertRaisesRegex(pm.TaskError, 'no current confirmed'):
            self.derive('E-T9')
        with self.assertRaisesRegex(pm.TaskError, 'stale confirmation'):
            self.call('confirm_config', person='SIM-owner', quote='SIM', presented_ref='SIM', choices={})
        self.confirm()
        self.assertEqual('code-engineering-001', self.derive('E-T9'))

    def test_confirming_person_needs_project_authority_and_a_front_desk_or_pm_recorder(self):
        self.write('instance-config.json', TEAM)
        (self.root / 'management/people.json').write_text(json.dumps({'people': [
            {'id': 'boss', 'name': 'BOSS', 'decides': ['project']}, {'id': 'dev', 'name': '工程师', 'decides': ['build']}]}))
        with self.assertRaisesRegex(pm.TaskError, 'no decision authority'):
            self.confirm(person='dev')
        with self.assertRaisesRegex(pm.TaskError, 'listed person'):
            self.confirm(person='nobody')
        with self.assertRaisesRegex(pm.TaskError, 'PM or front desk'):
            self.confirm(person='boss', actor='SIM-DESK')
        self.call('configure', frontdesk_actor='SIM-DESK')
        self.assertEqual('boss', self.confirm(person='boss', actor='SIM-DESK')['record']['person'])
        with self.assertRaisesRegex(pm.TaskError, 'quote'):
            self.confirm(person='boss', quote='')


class Derivation(Fixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.write('instance-config.json', TEAM)
        self.confirm()

    def test_derive_only_inside_the_configuration_and_its_count(self):
        with self.assertRaisesRegex(pm.TaskError, 'not in the confirmed configuration'):
            self.derive('D-T5')
        with self.assertRaisesRegex(pm.TaskError, 'PM derives'):
            self.call('derive', 'SIM-DESK', entry='E-T4', endpoint='SIM-x')
        with self.assertRaisesRegex(pm.TaskError, 'real handle'):
            self.call('derive', entry='E-T4', endpoint='')
        ids = [self.derive('E-T9'), self.derive('E-T4'), self.derive('P-T7'), self.derive('E-T4')]
        self.assertEqual(['code-engineering-001', 'code-engineering-002', 'product-001', 'code-engineering-003'], ids)
        with self.assertRaisesRegex(pm.TaskError, 'count reached'):
            self.derive('E-T4')
        with self.assertRaisesRegex(pm.TaskError, 'endpoint already registered'):
            self.call('derive', entry='Q-T5', endpoint=self.instance('product-001')['endpoint'])
        inst = self.instance('code-engineering-002')
        for key, value in dict(role='code-engineering', profession='code-engineering', level='T4', model='SIM-small', config_entry='E-T4',
                               fit='fit', master=False, derived_by='PM', active=True).items():
            self.assertEqual(value, inst[key])
        self.assertIn('management/instances/code-engineering-002/workspace', inst['write_roots'])

    def test_profile_is_generated_from_registry_and_configuration_without_endpoint(self):
        iid = self.derive('E-T9')
        text = (self.root / 'management/instances' / iid / 'profile.md').read_text(encoding='utf-8')
        row = next(line for line in (SOURCE / 'matrix/professions/code-engineering/levels.md').read_text(encoding='utf-8').splitlines() if line.startswith('| T9 |'))
        can, judge, cannot = [c.strip() for c in row.strip('|').split('|')][1:4]
        for expected in ['编号：code-engineering-001', '专业：代码工程', '职级：T9', '身份：master', '模型名称：SIM-big', '配置项：E-T9',
                         '派生人与时间：PM', '配置的确认人与原话：SIM-owner：「SIMULATED: 就按这个配置」', '适用性：适用',
                         '能做：' + can, '能判断：' + judge, '不能做（越权）：' + cannot]:
            self.assertIn(expected, text)
        self.assertNotIn(self.instance(iid)['endpoint'], text)

    def test_plain_registration_is_refused_once_a_configuration_is_confirmed(self):
        with self.assertRaisesRegex(pm.TaskError, 'derive from the confirmed instance configuration'):
            self.call('register_instance', id='LEGACY', instance=dict(role='matrix-code-engineering-build', endpoint='SIM-legacy'))

    def test_retire_and_relevel_follow_a_new_confirmation(self):
        workers = [self.derive('E-T4'), self.derive('E-T4')]
        revision = lambda iid: self.instance(iid)['revision']
        with self.assertRaisesRegex(pm.TaskError, 'still includes'):
            self.call('retire_instance', id=workers[1], expected_revision=revision(workers[1]), reason='SIM')
        lowered = [dict(e, count=1, level='T5') if e['id'] == 'E-T4' else e for e in TEAM['entries']]
        self.write('instance-config.json', {'entries': lowered})
        self.confirm()
        with self.assertRaisesRegex(pm.TaskError, 'reason'):
            self.call('retire_instance', id=workers[1], expected_revision=revision(workers[1]), reason='')
        retired = self.call('retire_instance', id=workers[1], expected_revision=revision(workers[1]), reason='SIM count lowered by the person')['record']
        self.assertFalse(retired['active'])
        with self.assertRaisesRegex(pm.TaskError, 'count reached'):
            self.derive('E-T4')  # the lowered count is filled by the remaining worker
        relevelled = self.call('relevel_instance', id=workers[0], expected_revision=revision(workers[0]), reason='SIM level raised by the person')['record']
        self.assertEqual(('T4', 'T5'), (relevelled['previous_level'], relevelled['level']))
        profile = (self.root / 'management/instances' / workers[0] / 'profile.md').read_text(encoding='utf-8')
        self.assertIn('职级：T5', profile)
        self.assertIn('## 本职级（T5）', profile)
        with self.assertRaisesRegex(pm.TaskError, 'does not change'):
            self.call('relevel_instance', id=workers[0], expected_revision=revision(workers[0]), reason='SIM again')

    def test_ids_are_never_reused_after_retirement(self):
        first = self.derive('E-T4')
        self.write('instance-config.json', {'entries': [e for e in TEAM['entries'] if e['id'] != 'E-T4']})
        self.confirm()
        self.call('retire_instance', id=first, expected_revision=1, reason='SIM entry removed')
        self.write('instance-config.json', TEAM)
        self.confirm()
        self.assertEqual('code-engineering-002', self.derive('E-T4'))
        self.assertEqual('code-engineering-003', self.derive('E-T4'))

    def test_running_work_blocks_retirement(self):
        self.derive('E-T9')
        worker = self.derive('E-T4')
        self.create('P', owner='code-engineering-001')
        self.create('W', 'P', owner=worker, checker='code-engineering-001')
        self.mutate('transition', 'W', state='running', reason='SIM', execution_receipt='SIM started')
        self.write('instance-config.json', {'entries': [e for e in TEAM['entries'] if e['id'] != 'E-T4']})
        self.confirm()
        with self.assertRaisesRegex(pm.TaskError, 'stop running work'):
            self.call('retire_instance', id=worker, expected_revision=1, reason='SIM entry removed')

    def test_workflow_pm_may_be_a_derived_project_management_instance(self):
        entries = TEAM['entries'] + [{'id': 'PM-T5', 'profession': 'project-management', 'level': 'T5', 'model': 'SIM-big', 'count': 1}]
        self.write('instance-config.json', {'entries': entries})
        self.confirm()
        iid = self.derive('PM-T5')
        (self.root / 'authority.md').write_text('SIMULATED designation of a workflow PM')
        self.create('FLOW', owner='SIM-OWNER')
        self.call('appoint', id=iid, appointment=dict(mode='workflow_pm', role='project-management', root_tasks=['FLOW'], delegates=[], source='authority.md'))
        self.assertEqual('workflow_pm', next(a for a in self.team()['appointments'] if a['id'] == iid)['mode'])


class Levels(Fixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.staff()  # code 001 (T9 master), 002/003 (T4); quality 001 (T7 master), 002 (T5); product 001 (T7 master)

    def test_level_must_cover_the_difficulty_at_create_update_and_start(self):
        self.create('P', owner='code-engineering-001', difficulty='T6', risk='F2', risk_reason='SIM main module')
        with self.assertRaisesRegex(pm.TaskError, 'split the task or assign a higher level; do not relabel'):
            self.create('HARD', 'P', owner='code-engineering-002', difficulty='T5', checker='code-engineering-001')
        self.create('W', 'P', owner='code-engineering-002', difficulty='T4', checker='code-engineering-001')
        with self.assertRaisesRegex(pm.TaskError, 'below difficulty'):
            self.mutate('update', 'W', changes={'difficulty': 'T6'}, reason='SIM harder', scope_authorization='SIM master decision')
        with self.assertRaisesRegex(pm.TaskError, 'manager authorization'):
            self.mutate('update', 'W', changes={'difficulty': 'T3'}, reason='SIM relabel')
        self.mutate('update', 'W', 'code-engineering-002', changes={'difficulty': 'T3'}, reason='SIM split: interface part moved out', scope_authorization='SIM master split')
        lowering = [e for e in pm.execute(self.root, {'op': 'events', 'limit': 1000})['events'] if e['command'].get('changes', {}).get('difficulty') == 'T3']
        self.assertEqual('SIM split: interface part moved out', lowering[0]['command']['reason'])
        with self.assertRaisesRegex(pm.TaskError, 'difficulty must be'):
            self.create('BAD', 'P', owner='code-engineering-002', difficulty='T10', checker='code-engineering-001')
        with self.assertRaisesRegex(pm.TaskError, 'risk must be'):
            self.create('BAD', 'P', owner='code-engineering-002', risk='F9', checker='code-engineering-001')

    def test_a_relevelled_instance_cannot_start_work_above_its_new_level(self):
        self.create('P', owner='code-engineering-001')
        self.create('W', 'P', owner='code-engineering-002', difficulty='T4', checker='code-engineering-001')
        lowered = [dict(e, level='T3') if e['id'] == 'E-T4' else e for e in TEAM['entries']]
        self.write('instance-config.json', {'entries': lowered})
        self.confirm()
        self.call('relevel_instance', id='code-engineering-002', expected_revision=1, reason='SIM person lowered the level')
        self.assertIn('instance_level', self.t('W')['readiness_issues'])
        with self.assertRaisesRegex(pm.TaskError, 'instance_level'):
            self.mutate('transition', 'W', state='running', reason='SIM', execution_receipt='SIM started')

    def test_instance_without_level_cannot_take_a_task_with_difficulty(self):
        with tempfile.TemporaryDirectory(prefix='pm-legacy-simulation-') as d:
            root = Path(d).resolve()
            pm.execute(root, dict(op='init', actor='PM', event_id='L1', config=dict(project='SIM', pm_actor='PM', authorization='SIM', frontdoor_id='SIM', max_slots=2)))
            pm.execute(root, dict(op='register_instance', actor='PM', event_id='L2', id='OLD', instance=dict(role='matrix-code-engineering-build', endpoint='SIM-old')))
            task = dict(id='X', parent=None, title='SIM', owner='OLD', checker='C', goal='g', inputs=['i'], outputs=['o'], criteria=['c'], next_action='n')
            with self.assertRaisesRegex(pm.TaskError, 'has no level'):
                pm.execute(root, dict(op='create', actor='PM', event_id='L3', task=dict(task, difficulty='T3')))
            pm.execute(root, dict(op='create', actor='PM', event_id='L4', task=task))

    def test_project_tasks_from_the_pm_go_to_the_master(self):
        with self.assertRaisesRegex(pm.TaskError, 'project-level tasks go to the master'):
            self.create('T-1', owner='code-engineering-002')
        self.create('T-1', owner='code-engineering-001')
        self.create('T-2', owner='SIM-unregistered-owner')  # owners that are not instances keep the old rule
        self.create('T-1.a', 'T-1', owner='code-engineering-002', checker='code-engineering-001')  # inside the profession anyone may take it
        with self.assertRaisesRegex(pm.TaskError, 'master'):
            self.mutate('handoff', 'T-2', 'PM', new_owner='code-engineering-003', acceptance_receipt='SIM', reason='SIM')

    def test_lowering_f0_f1_risk_needs_an_authorized_person(self):
        self.create('T-1', owner='code-engineering-001', risk='F1', risk_reason='SIM billing')
        changes = dict(changes={'risk': 'F3'}, reason='SIM relabel', scope_authorization='SIM PM decision')
        with self.assertRaisesRegex(pm.TaskError, 'person and exact quote'):
            self.mutate('update', 'T-1', **changes)
        (self.root / 'management/people.json').write_text(json.dumps({'people': [
            {'id': 'boss', 'name': 'BOSS', 'decides': ['project']}, {'id': 'dev', 'name': '工程师'}]}))
        with self.assertRaisesRegex(pm.TaskError, 'no decision authority'):
            self.mutate('update', 'T-1', person='dev', quote='SIMULATED ok', **changes)
        self.mutate('update', 'T-1', person='boss', quote='SIMULATED: 这个只是展示，降到 F3', **changes)
        self.assertEqual('F3', self.t('T-1')['risk'])
        self.mutate('update', 'T-1', changes={'risk': 'F4'}, reason='SIM minor', scope_authorization='SIM PM decision')  # below F1 needs no person

    def test_dispatcher_is_the_manager_and_cannot_be_changed(self):
        self.create('T-1', owner='code-engineering-001')
        self.create('T-1.a', 'T-1', owner='code-engineering-002', checker='code-engineering-001')
        self.assertEqual(('PM', 'code-engineering-001'), (self.t('T-1')['dispatcher'], self.t('T-1.a')['dispatcher']))
        self.assertEqual('code-engineering-001', next(t for t in pm.execute(self.root, {'op': 'query', 'level': 'all'})['tasks'] if t['id'] == 'T-1.a')['dispatcher'])
        with self.assertRaisesRegex(pm.TaskError, 'immutable'):
            self.mutate('update', 'T-1.a', changes={'manager': 'PM'}, reason='SIM')

    def test_origin_records_the_request_it_came_from(self):
        self.create('T-1', owner='code-engineering-001')
        with self.assertRaisesRegex(pm.TaskError, 'origin'):
            self.create('T-1.a', 'T-1', owner='code-engineering-002', checker='code-engineering-001', origin={'kind': 'chat', 'id': 'R', 'from': 'x'})
        self.create('T-1.a', 'T-1', owner='code-engineering-002', checker='code-engineering-001', origin={'kind': 'request', 'id': 'REQ-7', 'from': 'product-001'})
        listed = pm.execute(self.root, {'op': 'tasks_for', 'as': 'code-engineering-002'})
        self.assertIn('SIM T-1.a（来自 产品-001 的请求）', listed['rows'][0][1])
        self.assertIn('通知 产品-001', listed['rows'][0][6])


class Reassignment(Fixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.staff()
        self.create('P', owner='code-engineering-001')
        self.create('W', 'P', owner='code-engineering-002', difficulty='T4', checker='code-engineering-001')

    def reassign(self, to, actor='code-engineering-001', **kw):
        fields = dict(to=to, reason_kind='executor_unable', note='SIM: 边界拿不准')
        fields.update(kw)
        return self.mutate('reassign', 'W', actor, **fields)

    def test_dispatcher_reassigns_within_the_profession_with_a_reason(self):
        with self.assertRaisesRegex(pm.TaskError, 'dispatcher'):
            self.reassign('code-engineering-003', actor='PM')
        with self.assertRaisesRegex(pm.TaskError, 'reason_kind'):
            self.reassign('code-engineering-003', reason_kind='bored')
        with self.assertRaisesRegex(pm.TaskError, 'same profession'):
            self.reassign('quality-engineering-002')
        with self.assertRaisesRegex(pm.TaskError, 'active registered instance'):
            self.reassign('code-engineering-404')
        self.mutate('transition', 'W', state='running', reason='SIM', execution_receipt='SIM started')
        with self.assertRaisesRegex(pm.TaskError, 'stop or progress evidence'):
            self.reassign('code-engineering-003')
        self.reassign('code-engineering-003', stop_evidence='SIM progress checkpoint saved')
        moved = self.t('W')
        self.assertEqual(('code-engineering-003', 'code-engineering-003', 'planned'), (moved['owner'], moved['executor'], moved['state']))
        event = [e for e in pm.execute(self.root, {'op': 'events', 'limit': 1000})['events'] if e['command']['op'] == 'reassign'][-1]
        self.assertEqual(('code-engineering-002', 'executor_unable'), (event['before_data']['executor'], event['command']['reason_kind']))

    def test_target_needs_the_level_and_must_not_be_busy(self):
        self.create('OTHER', 'P', owner='code-engineering-003', checker='code-engineering-001')
        self.mutate('transition', 'OTHER', state='running', reason='SIM', execution_receipt='SIM started')
        with self.assertRaisesRegex(pm.TaskError, 'busy'):
            self.reassign('code-engineering-003')
        self.create('HARD', 'P', owner='code-engineering-001', difficulty='T7', checker='quality-engineering-001')
        with self.assertRaisesRegex(pm.TaskError, 'below difficulty'):
            self.mutate('reassign', 'HARD', 'code-engineering-001', to='code-engineering-002', reason_kind='other', note='SIM')


class Conflicts(Fixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.staff()
        self.create('P', owner='code-engineering-001')
        self.create('A', 'P', owner='code-engineering-002', checker='code-engineering-001')
        self.create('B', 'P', owner='code-engineering-003', checker='code-engineering-001')

    def ruling(self, actor, level, rid='K1', **kw):
        fields = dict(id=rid, task_ids=['A', 'B'], parties=['code-engineering-002', 'code-engineering-003'], issue='SIM 接口理解不同',
                      basis='SIM 接口契约 v2', resolution='SIM 按 B 的理解', decided_by=actor, level=level, overturned=['A'])
        fields.update(kw)
        return self.call('conflict', actor, **fields)

    def test_actor_must_fit_the_level_and_overturned_work_gets_an_event(self):
        with self.assertRaisesRegex(pm.TaskError, 'does not fit'):
            self.ruling('quality-engineering-001', 'master')  # a master of another profession
        with self.assertRaisesRegex(pm.TaskError, 'does not fit'):
            self.ruling('code-engineering-002', 'pm')
        with self.assertRaisesRegex(pm.TaskError, 'no majority'):
            self.ruling('code-engineering-001', 'master', decided_by='code-engineering-002')
        with self.assertRaisesRegex(pm.TaskError, 'among the conflict tasks'):
            self.ruling('code-engineering-001', 'master', overturned=['P'])
        record = self.ruling('code-engineering-001', 'master')['record']
        self.assertEqual(['A'], record['overturned'])
        self.assertEqual('planned', self.t('A')['state'])  # record only: rework stays with the manager
        with self.assertRaisesRegex(pm.TaskError, 'new simple conflict id'):
            self.ruling('code-engineering-001', 'master')
        marks = [e for e in pm.execute(self.root, {'op': 'events', 'limit': 1000})['events'] if e['command']['op'] == 'overturned']
        self.assertEqual([('A', 'K1')], [(e['task_id'], e['command']['conflict']) for e in marks])
        self.ruling('code-engineering-002', 'owner', rid='K2', overturned=[])
        self.ruling('PM', 'pm', rid='K3', overturned=[])
        self.ruling('code-engineering-003', 'tool', rid='K4', decided_by='write-range check', overturned=[])
        with self.assertRaisesRegex(pm.TaskError, 'person'):
            self.ruling('PM', 'human', rid='K5', decided_by='boss', overturned=[])
        self.ruling('PM', 'human', rid='K5', decided_by='boss', person='boss', quote='SIMULATED: 按 B', overturned=[])
        pm.render(self.root)
        self.assertIn('overturned', (self.root / 'management/views/tasks/A.md').read_text(encoding='utf-8'))


class Independence(Fixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.staff()
        self.create('P', owner='code-engineering-001')

    def work(self, tid, **kw):
        fields = dict(owner='code-engineering-002', checker='code-engineering-003', difficulty='T4')
        fields.update(kw)
        self.create(tid, 'P', **fields)

    def independence(self, tid):
        return self.t(tid)['review']['independence']

    def platform_run(self, tid, model):
        """A SIMULATED platform run of the executor that hands the task over."""
        rid = 'RUN-' + tid + '-' + str(self.n)
        self.call('launch_start', id=rid, purpose='start', task_id=tid, instance=self.t(tid)['executor'], model=model, session='SIM-' + rid, command=['SIM-cli'])
        self.call('launch_started', id=rid, pid=4242)
        self.mutate('transition', tid, state='waiting_review', reason='SIM handed over', stop_evidence='SIM stopped', evidence=['SIMULATED work ' + tid])
        self.call('launch_exit', 'launcher', id=rid, exit_code=0)

    def checking(self, tid, model):
        """A SIMULATED platform run of the checker, still running while it records the review."""
        rid = 'CHECK-' + tid + '-' + str(self.n)
        self.call('launch_start', id=rid, purpose='check', task_id=tid, instance=self.t(tid)['checker'], model=model, session='SIM-' + rid, command=['SIM-cli'])

    def test_same_model_check_is_not_independent_for_f1_and_blocks_closing(self):
        self.work('F1', risk='F1', risk_reason='SIM 扣费')
        self.platform_run('F1', 'SIM-small')
        self.check('F1')
        self.assertEqual('not_independent', self.independence('F1'))
        with self.assertRaisesRegex(pm.TaskError, r'F1 work needs an independent check \(recorded: not_independent\): assign another checker'):
            self.close('F1')  # quality-engineering-001 runs another model
        self.mutate('update', 'F1', changes={'checker': 'quality-engineering-001'}, reason='SIM other model', scope_authorization='SIM master')
        self.check('F1')
        self.assertEqual('not_independent', self.independence('F1'))  # configured for another model, but no recorded run shows it
        self.checking('F1', 'SIM-big')
        self.check('F1')
        self.assertEqual('independent', self.independence('F1'))
        self.close('F1')

    def test_f2_needs_another_instance_but_not_another_model(self):
        self.work('F2', risk='F2', risk_reason='SIM module')
        self.check('F2')
        self.assertEqual('independent', self.independence('F2'))
        self.close('F2')

    def test_checker_level_and_master_level_difficulty(self):
        self.work('LOW', owner='code-engineering-001', checker='quality-engineering-002', difficulty='T6', risk='F2', risk_reason='SIM')
        self.check('LOW')
        self.assertEqual('not_independent', self.independence('LOW'))  # T5 checker on a T6 task
        self.work('MASTERY', owner='code-engineering-001', checker='quality-engineering-001', difficulty='T7', risk='F2', risk_reason='SIM')
        self.check('MASTERY')
        self.assertEqual('not_independent', self.independence('MASTERY'))  # master-level task, same model

    def test_same_instance_check_closes_only_when_no_other_instance_has_the_level(self):
        self.work('SELF', checker='code-engineering-002', risk='F2', risk_reason='SIM')
        self.check('SELF')
        self.assertEqual('same_instance', self.independence('SELF'))
        with self.assertRaisesRegex(pm.TaskError, 'recorded: same_instance.*assign another checker'):
            self.close('SELF')  # code-engineering-003 could check it
        self.work('TOP', owner='code-engineering-001', checker='code-engineering-001', difficulty='T7', risk='F1', risk_reason='SIM 核心逻辑')
        self.check('TOP')
        with self.assertRaisesRegex(pm.TaskError, 'derive a different-model instance per the instance configuration, or ask a person to change the configuration'):
            self.close('TOP')  # T7 instances exist, but all run the producer's model
        self.mutate('update', 'TOP', 'code-engineering-001', changes={'checker': 'quality-engineering-001'}, reason='SIM', scope_authorization='SIM')
        self.check('TOP')
        self.assertEqual('not_independent', self.independence('TOP'))  # another instance, the same model
        with self.assertRaisesRegex(pm.TaskError, 'derive a different-model instance'):
            self.close('TOP')
        self.work('SOLO', owner='code-engineering-001', checker='code-engineering-001', difficulty='T8', risk='F1', risk_reason='SIM 关键选型方案')
        self.check('SOLO')
        self.close('SOLO')  # no other instance reaches T8: 同一实例检验
        self.assertEqual('same_instance', self.independence('SOLO'))

    def test_tasks_without_labels_keep_the_previous_rule(self):
        self.work('PLAIN', checker='code-engineering-002', difficulty=None)
        self.check('PLAIN')
        self.close('PLAIN')

    def test_unfit_insisted_producer_counts_as_f1(self):
        entries = TEAM['entries'] + [{'id': 'E-T7', 'profession': 'code-engineering', 'level': 'T7', 'model': 'SIM-small', 'count': 1}]
        self.write('instance-config.json', {'entries': entries})
        self.confirm({'E-T7': 'insist'})
        insisted = self.derive('E-T7')
        self.assertEqual('unfit_insisted', self.instance(insisted)['fit'])
        self.work('INSISTED', owner=insisted, checker='code-engineering-003', difficulty='T4', risk='F3', risk_reason='SIM tool script')
        self.check('INSISTED')
        self.assertEqual('not_independent', self.independence('INSISTED'))
        with self.assertRaisesRegex(pm.TaskError, 'F1 work needs an independent check'):
            self.close('INSISTED')


if __name__ == '__main__':
    unittest.main()
