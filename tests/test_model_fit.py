"""SIMULATED assessments and runtime records; no model capability certification."""
import copy
import unittest
from test_pm_instances import Fixture, MODELS, TEAM, pm


class DynamicFit(Fixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.models = copy.deepcopy(MODELS)
        for row in self.models['models']:
            row.update(basis='human', evidence=['SIM assessment'], evaluated_at='2026-01-01T00:00:00+00:00',
                       model_version=row['model'], review_after='2099-01-01T00:00:00+00:00',
                       review_conditions={'review_failed': 0})
        self.write('model-fit.json', self.models)
        self.write('instance-config.json', TEAM)

    def entries(self):
        return {e['id']: e for e in self.team()['instance_config']['entries']}

    def test_expired_assessment_is_unregistered(self):
        self.models['models'][0]['review_after'] = '2026-01-02T00:00:00+00:00'
        self.write('model-fit.json', self.models)
        self.assertEqual('unregistered', self.entries()['E-T9']['fit'])

    def test_missing_evidence_is_unregistered(self):
        del self.models['models'][0]['evidence']
        self.write('model-fit.json', self.models)
        self.assertEqual('unregistered', self.entries()['E-T9']['fit'])

    def test_actual_version_change_is_unregistered(self):
        self.staff()
        with pm.connect(self.root) as db:
            pm.integrity.save(pm.api(), db, 'launch', dict(id='SIM-run', instance='code-engineering-001',
                model='SIM-big', reported_model='SIM-big-v2', state='exited', purpose='start', running_at=pm.now(), started_at=pm.now()))
        self.assertEqual('unregistered', self.entries()['E-T9']['fit'])
        self.assertFalse(self.team()['instance_config']['current'])

    def test_performance_triggers_reconfirmation_without_demotion(self):
        self.staff()
        self.create('A', difficulty='T7')
        self.check('A', outcome='failed', cause='execution')
        self.assertEqual('unregistered', self.entries()['E-T9']['fit'])
        self.assertEqual('T9', self.instance('code-engineering-001')['level'])
        self.assertFalse(self.team()['instance_config']['current'])
        with self.assertRaisesRegex(pm.TaskError, 'confirmed'):
            self.derive('E-T9')

    def test_one_expired_model_does_not_block_other_entries(self):
        self.staff()
        self.models['models'][1]['review_after'] = '2026-01-02T00:00:00+00:00'
        self.write('model-fit.json', self.models)
        self.create('HEALTHY', difficulty='T4')
        self.create('EXPIRED', parent='HEALTHY', owner='code-engineering-002', executor='code-engineering-002', difficulty='T4')
        self.assertTrue(self.t('HEALTHY')['ready'])
        self.assertFalse(self.t('EXPIRED')['ready'])
        self.mutate('transition', 'HEALTHY', state='running', reason='SIM', execution_receipt='SIM')
        with self.assertRaisesRegex(pm.TaskError, 'model fit'):
            self.mutate('transition', 'EXPIRED', state='running', reason='SIM', execution_receipt='SIM')

    def test_unrelated_expiry_preserves_derivation_planning(self):
        config = copy.deepcopy(TEAM)
        config['entries'][0].update(count=2, master=False)
        self.write('instance-config.json', config)
        self.confirm()
        iid = self.derive('E-T9')
        self.models['models'][1]['review_after'] = '2026-01-02T00:00:00+00:00'
        self.write('model-fit.json', self.models)
        with pm.connect(self.root) as db:
            ctx = {'instances': pm.integrity.records(db, 'instance')}
            entry = pm.platform.room(pm.api(), self.root, db, ctx, {'owner':iid})
        self.assertEqual('E-T9', entry)
        self.assertEqual('code-engineering-002', self.derive(entry))

    def test_assessment_edits_invalidate_only_selected_model_entries(self):
        self.staff()
        self.models['models'][1]['evidence'].append('SIM additional evidence')
        self.write('model-fit.json', self.models)
        entries = self.entries()
        self.assertTrue(entries['E-T9']['current'])
        self.assertTrue(entries['P-T7']['current'])
        self.assertFalse(entries['E-T4']['current'])
        with self.assertRaisesRegex(pm.TaskError, 'configured count reached'):
            self.derive('E-T9')  # confirmation is still valid
        with self.assertRaisesRegex(pm.TaskError, 'confirmed'):
            self.derive('E-T4')

    def test_no_host_report_does_not_claim_actual_version(self):
        self.staff()
        self.create('A', difficulty='T7')
        self.call('launch_start', id='R', purpose='start', task_id='A', instance='code-engineering-001',
                  model='SIM-selection-alias', session='SIM-session', command=['SIM-cli'])
        self.call('launch_started', id='R', pid=4242)
        self.call('launch_exit', 'launcher', id='R', exit_code=1)
        self.assertEqual('fit', self.entries()['E-T9']['fit'])
        rows = pm.execute(self.root, {'op':'model_performance'})['rows']
        self.assertEqual('launch_selection', rows[0]['signals'][0]['version_source'])

    def test_query_is_read_only_and_groups_task_level(self):
        self.staff()
        self.create('A', difficulty='T7')
        self.check('A', outcome='failed', cause='execution')
        before = pm.execute(self.root, {'op':'events', 'limit':1000})
        result = pm.execute(self.root, {'op':'model_performance'})
        row = next(r for r in result['rows'] if r['model'] == 'SIM-big')
        self.assertEqual(('T7', 1), (row['level'], row['review_failed']))
        self.assertEqual(before, pm.execute(self.root, {'op':'events', 'limit':1000}))

    def test_invalid_dates_and_conditions_do_not_certify(self):
        original = copy.deepcopy(self.models)
        for patch in ({'evaluated_at':'2098-01-01T00:00:00Z'}, {'review_after':'not-a-date'},
                      {'review_conditions':{'rework':True}}, {'review_conditions':{'unknown':1}},
                      {'evaluated_at':'2026-01-01T00:00:00'}):
            self.models = copy.deepcopy(original)
            self.models['models'][0].update(patch)
            self.write('model-fit.json', self.models)
            self.assertEqual('unregistered', self.entries()['E-T9']['fit'])

    def test_matching_version_and_failed_start_do_not_invalidate(self):
        self.staff()
        with pm.connect(self.root) as db:
            for rid, version, state in [('same','SIM-big','exited'),('failed','SIM-big-v2','not_started')]:
                row=dict(id=rid, instance='code-engineering-001', model='SIM-big', reported_model=version, state=state, started_at=pm.now())
                if state == 'exited': row['running_at']=pm.now()
                pm.integrity.save(pm.api(), db, 'launch', row)
        self.assertEqual('fit', self.entries()['E-T9']['fit'])
        self.assertTrue(self.team()['instance_config']['current'])

    def test_expiry_invalidates_existing_confirmation(self):
        from unittest.mock import patch
        self.staff()
        with patch.object(pm, 'now', return_value='2100-01-01T00:00:00Z'):
            self.assertFalse(self.team()['instance_config']['current'])
            self.create('A')
            with self.assertRaisesRegex(pm.TaskError, 'model fit'):
                self.mutate('transition', 'A', state='running', reason='SIM', execution_receipt='SIM')
            with self.assertRaisesRegex(pm.TaskError, 'model fit'):
                self.call('launch_start', id='R', purpose='start', task_id='A', instance='code-engineering-001',
                          model='SIM-big', session='SIM-session', command=['SIM-cli'])

    def test_reconfirmation_is_bounded_and_does_not_regrade(self):
        self.staff()
        self.create('A', difficulty='T7')
        self.check('A', outcome='failed', cause='execution')
        self.confirm({key:'acknowledge_unregistered' for key in ['E-T9','Q-T7','P-T7']})
        self.assertTrue(self.team()['instance_config']['current'])
        self.check('A', outcome='failed', cause='execution')
        self.assertFalse(self.team()['instance_config']['current'])
        self.assertEqual('T9', self.instance('code-engineering-001')['level'])

    def test_capability_floor_only_applies_to_high_levels(self):
        self.models['models'][0]['capabilities'].remove('complex_dispatch')
        self.write('model-fit.json', self.models)
        self.assertEqual('unfit', self.entries()['E-T9']['fit'])
        self.assertEqual('fit', self.entries()['E-T4']['fit'])

    def test_all_performance_metrics_and_actual_version(self):
        self.models['models'][0]['review_conditions'] = {}
        self.write('model-fit.json', self.models)
        self.staff()
        self.create('A', difficulty='T7')
        self.call('launch_start', id='R', purpose='start', task_id='A', instance='code-engineering-001',
                  model='SIM-big', session='SIM-session', command=['SIM-cli'])
        self.call('launch_started', id='R', pid=4242, model='SIM-big')
        self.call('launch_exit', 'launcher', id='R', exit_code=1)
        self.call('launch_exit', 'launcher', id='R', exit_code=1)  # duplicate receipt is not another failure
        self.check('A', outcome='failed', cause='execution')
        self.mutate('transition', 'A', state='running', reason='SIM retry', note='SIM fix', execution_receipt='SIM run')
        self.mutate('report', 'A', summary='SIM needs help', next_action='SIM wait', impact='SIM delay', delivery='prepared')
        self.mutate('report', 'A', summary='SIM needs help', next_action='SIM wait', impact='SIM delay', delivery='sent', receipt='SIM delivery')
        rows=pm.execute(self.root, {'op':'model_performance'})['rows']
        row=next(r for r in rows if r['model_version']=='SIM-big')
        self.assertEqual([1,1,1,1], [row[k] for k in pm.team.model_fit.METRICS])
        self.assertEqual('T7', row['level'])
        self.assertTrue(all(s['version_source']=='host_report' for s in row['signals']))
        self.assertEqual([], pm.execute(self.root, {'op':'model_performance','since':'2099-01-01T00:00:00Z'})['rows'])
        with self.assertRaisesRegex(pm.TaskError,'timestamp'):
            pm.execute(self.root, {'op':'model_performance','since':'invalid'})

    def test_confirmed_fit_change_requires_profile_update_not_automatic_demotion(self):
        self.staff()
        self.models['models'][0]['capabilities'].remove('complex_dispatch')
        self.write('model-fit.json', self.models)
        self.confirm({key:'insist' for key in ['E-T9','Q-T7','P-T7']})
        self.create('A', difficulty='T4')
        with self.assertRaisesRegex(pm.TaskError, 'relevel_instance'):
            self.mutate('transition', 'A', state='running', reason='SIM', execution_receipt='SIM')
        row=self.call('relevel_instance', id='code-engineering-001', expected_revision=1,
                      reason='SIM apply confirmed fit flag only')['record']
        self.assertEqual(('T9','unfit_insisted'), (row['level'],row['fit']))
        self.mutate('transition', 'A', state='running', reason='SIM', execution_receipt='SIM')


from test_expert_packages import PlatformFixture


class ModelFitPlatformQuery(PlatformFixture, unittest.TestCase):
    def test_host_version_is_separate_from_claimed_selection(self):
        rec = self.claim()
        result = self.invoke('runs.event', run_id=rec['id'], expected_revision=rec['revision'],
                             kind='started', pid=4242, model=rec['model'], reported_model='SIM-host-version-2',
                             receipt='SIM host init metadata')['record']
        self.assertEqual(rec['model'], result['model'])
        self.assertEqual('SIM-host-version-2', result['reported_model'])
        entries = self.team()['instance_config']['entries']
        affected = next(e for e in entries if e['id']=='E-T9')
        self.assertTrue(any(r.startswith('model_version_changed:') for r in affected['review_reasons']))

    def test_query_through_authenticated_platform(self):
        response = self.run_api(self.req('tasks.query', op='model_performance', since='2020-01-01T00:00:00Z'))
        self.assertTrue(response['ok'], response)
        self.assertEqual([], response['result']['rows'])
