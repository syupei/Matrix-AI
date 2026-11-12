"""Synthetic project/resource/closure invariants; no human or professional outcome is certified."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from kit import KIT

s = importlib.util.spec_from_file_location('project_test_pm', KIT/'matrix/orchestration/tools/pm_tasks.py')
pm = importlib.util.module_from_spec(s); s.loader.exec_module(pm)


class ProjectTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name); self.n = 0
        self.call('init', config=dict(project='SIM', pm_actor='PM', authorization='SIM', frontdoor_id='SIM', max_slots=3))
        (self.root/'result.txt').write_text('SIM result')

    def call(self, op, actor='PM', **kw):
        self.n += 1
        return pm.execute(self.root, dict(op=op, actor=actor, event_id=f'SIM-{self.n}', **kw))

    def config(self, **changes):
        return self.call('project_config', expected_revision=self.call('project')['revision'], source='SIM source', changes=changes)

    def task(self, tid, **kw):
        self.call('create', task=dict(id=tid,title=tid,parent=None,owner='PM',executor='PM',checker='QA',goal='SIM',
                 inputs=['SIM input'],outputs=['result.txt'],criteria=['SIM checked'],next_action='SIM next', **kw))

    def tasks(self):
        return {t['id']:t for t in self.call('status')['tasks']}

    def accept(self, tid):
        self.call('update',task_id=tid,expected_revision=self.tasks()[tid]['revision'],changes={'evidence':['result.txt']},reason='SIM delivered')
        self.call('review','QA',task_id=tid,expected_revision=self.tasks()[tid]['revision'],outcome='passed',criteria_checked=['SIM checked'],evidence=['SIM check'])
        self.call('transition',task_id=tid,expected_revision=self.tasks()[tid]['revision'],state='done',reason='SIM accepted')

    def resource(self, status='available', exclusive=True):
        return dict(kind='device',status=status,exclusive=exclusive,evidence=['SIM fact'] if status=='available' else [])

    def goal(self):
        return dict(id='adoption',target='20 people',owner='Lin',state='pending',evidence=[])

    def test_resource_reference_does_not_hide_missing_fact_record(self):
        self.task('A', resources=['device'])
        self.task('B', resources=['device'])
        self.assertEqual(self.call('project')['resource_recording_gaps'], ['device'])
        self.config(resources={'device':self.resource()})
        self.assertEqual(self.call('project')['resource_recording_gaps'], [])
        self.assertEqual(self.tasks()['A']['resources'], ['device'])

    def test_project_type_preserved_and_gap_explicit(self):
        d=self.config(project_type='event')
        self.assertEqual(d['project_type'],'event');self.assertTrue(d['route_gap'])
        self.assertEqual(self.call('status')['tasks'],[])

    def test_exclusive_planned_tasks_are_not_both_ready(self):
        self.task('A',resources=['device']);self.task('B',resources=['device'])
        self.assertEqual({k:t['ready'] for k,t in self.tasks().items()},{'A':True,'B':False})
        with self.assertRaises(pm.TaskError):
            self.call('transition',task_id='B',expected_revision=1,state='running',reason='SIM',execution_receipt='SIM')

    def test_shared_resource_and_unknown_are_distinguished(self):
        self.task('A',resources=['device']);self.task('B',resources=['device'])
        self.config(resources={'device':self.resource(exclusive=False)})
        self.assertTrue(all(t['ready'] for t in self.tasks().values()))
        self.config(resources={})
        self.assertFalse(any(t['ready'] for t in self.tasks().values()))
        self.assertTrue(any(a.get('code')=='resource' for a in self.call('continue')['actions']))

    def test_pending_availability_is_not_invented(self):
        self.task('A',resources=['purchase'])
        self.config(resources={'purchase':dict(kind='procurement',status='pending',exclusive=True,evidence=[])})
        self.assertFalse(self.tasks()['A']['ready'])
        with self.assertRaises(pm.TaskError):
            self.config(resources={'purchase':dict(kind='procurement',status='available',exclusive=True,evidence=[])})

    def test_blocked_task_does_not_reserve_resource(self):
        self.task('A',resources=['device']);self.task('B',resources=['device'])
        self.call('transition',task_id='A',expected_revision=1,state='blocked',reason='SIM missing input')
        self.assertTrue(self.tasks()['B']['ready'])

    def test_priority_and_release_recompute_queue(self):
        self.task('A',resources=['device'],order=2);self.task('B',resources=['device'],order=1)
        self.assertTrue(self.tasks()['B']['ready']);self.assertFalse(self.tasks()['A']['ready'])
        self.accept('B');self.assertTrue(self.tasks()['A']['ready'])

    def test_running_occupancy_has_priority(self):
        self.task('A',resources=['device'])
        self.call('transition',task_id='A',expected_revision=1,state='running',reason='SIM',execution_receipt='SIM started')
        self.task('B',resources=['device'],order=0)
        self.assertFalse(self.tasks()['B']['ready'])

    def test_blocked_multi_resource_task_does_not_hold_unrelated_resource(self):
        self.task('A',resources=['r1']);self.task('B',resources=['r1','r2']);self.task('C',resources=['r2'])
        self.assertEqual({k:t['ready'] for k,t in self.tasks().items()},{'A':True,'B':False,'C':True})

    def test_stale_project_write_rejected(self):
        self.config(project_type='event')
        with self.assertRaises(pm.TaskError):
            self.call('project_config',expected_revision=0,source='SIM',changes={'project_type':'product_development'})

    def test_completion_is_not_business_success(self):
        self.task('A');self.accept('A')
        self.config(project_type='product_development',goals=[self.goal()])
        d=self.call('project')
        self.assertEqual(d['task_progress']['done'],1)
        self.assertTrue(d['delivery_acceptance']['A']['current'])
        self.assertEqual(d['business_results'][0]['state'],'pending')
        pm.render(self.root)
        self.assertIn('待证据',(self.root/'management/views/project.md').read_text())

    def test_measured_result_requires_evidence_and_measurement(self):
        goal=self.goal();goal['state']='met'
        with self.assertRaises(pm.TaskError):self.config(goals=[goal])
        goal.update(evidence=['SIM measurement'],measurement='21 people')
        self.assertEqual(self.config(goals=[goal])['business_results'][0]['state'],'met')

    def closure(self, pending=None):
        return dict(accepted=['A'],handoffs=[dict(task_id='A',receiver='Lin',next_action='Receive prototype',evidence=['SIM acceptance receipt'])],pending=pending or [])

    def test_closure_requires_scope_receivers_and_business_status(self):
        self.task('A');self.accept('A');self.task('CLEANUP')
        self.config(project_type='product_development',goals=[self.goal()],closure=self.closure())
        self.assertFalse(self.call('closure_check')['ready'])
        c=self.closure([dict(task_id='CLEANUP',receiver='Lin',next_action='Clean before use',evidence=['SIM accepted responsibility'])])
        self.config(closure=c)
        self.assertTrue(self.call('closure_check')['ready'])
        self.assertEqual(self.call('closure_check')['business_pending'],['adoption'])

    def test_closing_milestone_enforces_gate_and_reopen(self):
        self.task('A');self.accept('A');self.task('CLOSE',kind='stage',closure=True)
        with self.assertRaises(pm.TaskError):self.accept('CLOSE')
        self.config(project_type='product_development',goals=[self.goal()],closure=self.closure())
        self.call('transition',task_id='CLOSE',expected_revision=self.tasks()['CLOSE']['revision'],state='done',reason='SIM close')
        with self.assertRaises(pm.TaskError):self.config(project_type='event')

    def test_lessons_require_observation_conditions_and_evidence(self):
        c=self.closure();c['lessons']=[dict(observation='guess',conditions='all',evidence=[])]
        with self.assertRaises(pm.TaskError):self.config(closure=c)

    def test_unverified_done_is_not_accepted_scope(self):
        self.task('A');self.accept('A')
        self.config(project_type='product_development',goals=[self.goal()],closure=self.closure())
        self.call('transition',task_id='A',expected_revision=self.tasks()['A']['revision'],state='planned',reason='SIM reopen',rework_reason='execution',note='SIM acceptance needs correction')
        self.assertFalse(self.call('closure_check')['ready'])

    def test_current_gate_is_shared_by_project_and_status(self):
        from unittest.mock import patch
        self.task('A');self.accept('A')
        self.config(project_type='product_development',goals=[self.goal()],closure=self.closure())
        def blocked(*args, **kwargs):
            return [{'code':'pending_participation'}] if args[-1] == 'A' and kwargs.get('closing') else []
        with patch.object(pm.team, 'blockers', side_effect=blocked):
            self.assertTrue(self.tasks()['A']['needs_recheck'])
            self.assertFalse(self.call('project')['delivery_acceptance']['A']['current'])
            self.assertFalse(self.call('closure_check')['ready'])
