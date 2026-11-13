"""Mechanism scenarios, synthetic people and receipts; no model behavior claimed."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from kit import KIT

spec = importlib.util.spec_from_file_location('pm_governance_test', KIT / 'matrix/orchestration/tools/pm_tasks.py')
pm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pm)


class CollaborationTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.n = 0
        self.call('init', config=dict(project='SIM', pm_actor='PM', authorization='SIM', frontdoor_id='SIM', max_slots=3))
        self.people = [{'id': 'lead', 'name': 'Lead', 'decides': ['project']},
                       {'id': 'product', 'name': 'Product', 'masters': ['product']},
                       {'id': 'engineer', 'name': 'Engineer', 'masters': ['code-engineering']},
                       {'id': 'delegate', 'name': 'Delegate'}]
        self.roster()

    def roster(self):
        (self.root / 'management/people.json').write_text(json.dumps({'people': self.people}))

    def call(self, op, **kw):
        self.n += 1
        return pm.execute(self.root, dict(op=op, actor='PM', event_id=f'test-{self.n}', **kw))

    def configure(self, person='lead', **changes):
        revision = self.call('collaboration')['revision']
        return self.call('collaboration_config', expected_revision=revision, person=person, quote='SIM explicit choice', changes=changes)

    def delegation(self, **kw):
        return dict(id='export', profession='product', scope='export', person='delegate', grantor='lead',
                    quote='SIM delegate export product only', decisions=['professional'], **kw)

    def test_profiles_are_separate_and_unselected_pending(self):
        data = self.configure(default='regular', profiles={'product': 'deep', 'code-engineering': 'quick'})
        self.assertEqual(data['profiles']['product']['mode'], 'deep')
        self.assertEqual(data['profiles']['code-engineering']['mode'], 'quick')
        self.assertFalse(data['profiles']['experience-design']['confirmed'])
        self.assertEqual(data['engineering']['state'], 'pending')

    def test_master_changes_only_own_profile_and_history_survives(self):
        self.configure(profiles={'product': 'deep'})
        self.configure('product', profiles={'product': 'quick'})
        with self.assertRaises(pm.TaskError):
            self.configure('product', profiles={'code-engineering': 'deep'})
        events = self.call('events', full=True)['events']
        choices = [e['command']['changes']['profiles']['product'] for e in events
                   if e['command']['op'] == 'collaboration_config']
        self.assertEqual(choices, ['deep', 'quick'])

    def test_duplicate_master_is_rejected(self):
        self.people[-1]['masters'] = ['product']
        self.roster()
        with self.assertRaises(pm.TaskError):
            self.call('collaboration')

    def test_scope_priority_and_release_budget_fallback(self):
        self.configure(delegations=[self.delegation()])
        for scope, kind, expected in [('export', 'professional', 'delegate'), ('other', 'professional', 'product'),
                                      ('export', 'release', 'lead'), ('export', 'budget', 'lead')]:
            self.assertEqual(self.call('decision_route', profession='product', scope=scope, kind=kind)['person'], expected)

    def test_explicit_release_delegation_and_revocation(self):
        d = self.delegation(); d['decisions'] = ['release']
        self.configure(delegations=[d])
        self.assertEqual(self.call('decision_route', profession='product', scope='export', kind='release')['person'], 'delegate')
        d['active'] = False
        self.configure(delegations=[d])
        self.assertEqual(self.call('decision_route', profession='product', scope='export', kind='release')['person'], 'lead')

    def test_master_cannot_delegate_budget(self):
        d = self.delegation(); d.update(grantor='product', decisions=['budget'])
        with self.assertRaises(pm.TaskError):
            self.configure('product', delegations=[d])

    def test_ambiguous_delegation_does_not_choose_silently(self):
        d = self.delegation(); d['id'] = 'another'
        self.configure(delegations=[self.delegation(), d])
        with self.assertRaises(pm.TaskError):
            self.call('decision_route', profession='product', scope='export')

    def test_single_person_fallback(self):
        self.people = [self.people[0]]; self.roster()
        self.configure(profiles={'product': 'deep'})
        self.assertEqual(self.call('decision_route', profession='product')['person'], 'lead')

    def test_pending_question_is_not_confirmation_and_not_repeated(self):
        self.configure(default='quick')
        with self.assertRaises(pm.TaskError):
            self.call('collaboration_asked', expected_revision=1, professions=['product'])
        data = self.call('collaboration_asked', expected_revision=1, professions=['product'],
                         question='SIM: choose the default profile?', presented_ref='SIM displayed question')
        self.assertNotIn('product', data['ask_once'])
        self.assertFalse(data['profiles']['product']['confirmed'])
        self.assertIn('code-engineering', data['ask_once'])

    def test_stale_revision_and_unknown_fields_rejected(self):
        self.configure(default='regular')
        with self.assertRaises(pm.TaskError):
            self.call('collaboration_config', expected_revision=0, person='lead', quote='SIM', changes={'default': 'quick'})
        with self.assertRaises(pm.TaskError):
            self.configure(bogus=True)

    def test_engineering_requires_master_and_facts(self):
        self.configure(profiles={'code-engineering': 'quick'})
        with self.assertRaises(pm.TaskError):
            self.configure(engineering={'tier': 'medium', 'basis': 'SIM payroll data', 'stage': 'E-1'})
        data = self.configure('engineer', engineering={'tier': 'medium', 'basis': 'SIM payroll data', 'stage': 'E-1'})
        self.assertEqual(data['engineering']['tier'], 'medium')
        self.assertEqual(data['profiles']['code-engineering']['mode'], 'quick')

    def test_critical_risk_also_informs_leader(self):
        self.configure(default='quick')
        route = self.call('decision_route', profession='product', risk='F0')
        self.assertEqual(route['person'], 'product')
        self.assertTrue(route['separate_review'])
        self.assertEqual(route['inform'], ['lead'])

    def task(self, tid, **kw):
        return self.call('create', task=dict(id=tid, title=tid, parent=None, owner='PM', executor='PM', checker='QA',
                                            goal='SIM', inputs=['SIM'], outputs=['SIM'], criteria=['SIM'], next_action='SIM next', **kw))

    def test_actual_human_review_uses_same_route(self):
        self.configure(delegations=[self.delegation()])
        self.task('EXPORT', profession='product', decision_scope='export', human_required=True)
        args = dict(task_id='EXPORT', expected_revision=1, outcome='approved', presented_ref='SIM review',
                    source='SIM reply', quote='SIM approved', scope='export')
        with self.assertRaises(pm.TaskError):
            self.call('human_review', person='product', **args)
        self.call('human_review', person='delegate', **args)
        self.assertEqual(self.call('status')['tasks'][0]['human_review']['person'], 'delegate')

    def test_view_uses_current_recipient_and_profile(self):
        self.configure(profiles={'product': 'deep'}, delegations=[self.delegation()])
        self.task('EXPORT', profession='product', decision_scope='export', human_required=True)
        pm.render(self.root)
        self.assertIn('EXPORT', (self.root / 'management/views/people/delegate.md').read_text())
        self.assertIn('精细共创', (self.root / 'management/views/collaboration.md').read_text())

    def test_stage_line_in_continuation_and_views(self):
        self.task('P', kind='stage')
        self.task('D', kind='stage', dependencies=['P'])
        data = self.call('continue')
        self.assertEqual(data['project_stages']['total'], 2)
        self.assertEqual(data['project_stages']['current'], ['P'])
        pm.render(self.root)
        self.assertTrue((self.root / 'management/views/project.md').read_text().startswith(data['stage_line']))

    def test_no_stage_does_not_invent_progress(self):
        self.task('WORK')
        data = self.call('continue')
        self.assertNotIn('project_stages', data)
        self.assertIn('阶段尚未登记', data['stage_line'])
        self.assertNotIn('共', data['stage_line'])
        pm.render(self.root)
        self.assertTrue((self.root / 'management/views/project.md').read_text().startswith(data['stage_line']))

    def test_registry_stage_total(self):
        data = self.call('stage_flow', profession='product', flow='product')
        self.assertEqual(data['total'], len(data['stages']))
        self.assertEqual(data['total'], 7)
        for profession, flow in [('content-design','copy'),('quality-engineering','quality')]:
            self.assertEqual(self.call('stage_flow', profession=profession, flow=flow)['total'],4)
        with self.assertRaises(pm.TaskError):
            self.call('stage_flow', profession='product', flow='invented')

    def test_content_flow_exposes_canonical_labels_without_changing_count(self):
        data = self.call('stage_flow', profession='content-design', flow='copy')
        self.assertEqual(data['names'], {'CD-1':'定判据','CD-2':'成稿','CD-3':'审读','CD-4':'记录与交接'})
        self.assertEqual(data['total'], 4)
        self.assertEqual(list(data['names']), data['stages'])

    def test_closed_stage_without_current_evidence_is_not_complete(self):
        self.task('P', kind='stage')
        tasks = {t['id']: t for t in self.call('status')['tasks']}
        tasks['P']['state'] = 'done'
        data = pm.governance.stage_projection(pm.api(), tasks, [])
        self.assertIn('待复核', data['line'])
        self.assertNotIn('全部完成', data['line'])

    def test_parallel_rework_completion_projection(self):
        for tid in ['P', 'D', 'E']:
            self.task(tid, kind='stage', dependencies=[] if tid == 'P' else ['P'])
        tasks = {t['id']: t for t in self.call('status')['tasks']}
        # Pure projection input: explicit synthetic closure, not a claim of real approval.
        def completed(t):
            return t['state'] == 'done'
        from types import SimpleNamespace
        api = pm.api(); api.effective_done = lambda t, _: completed(t)
        tasks['P']['state'] = 'done'; tasks['D']['state'] = tasks['E']['state'] = 'running'
        p = pm.governance.stage_projection(api, tasks, [])
        self.assertEqual(set(p['current']), {'D', 'E'})
        tasks['P'].update(state='planned', rework={'count': 1})
        self.assertIn('返工中', pm.governance.stage_projection(api, tasks, [])['line'])
        for t in tasks.values(): t['state'] = 'done'
        self.assertIn('全部完成', pm.governance.stage_projection(api, tasks, [])['line'])

    def test_runtime_pause_does_not_turn_planned_stage_into_human_review(self):
        self.task('P', kind='stage')
        self.call('pause_project', person='lead', quote='SIM stop', reason='SIM pause')
        data = self.call('continue')
        self.assertTrue(data['runtime_state']['resume_required'])
        self.assertEqual(data['project_stages']['stages'][0]['state'], 'planned')
        self.assertNotIn('待审', data['stage_line'])
