"""Completion prerequisites in the PM task tool: work may start early but closes only after them. Every fact is SIMULATED."""
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest

SCRIPT = Path(os.environ.get('MATRIX_TEST_KIT', str(Path(__file__).resolve().parents[1] / 'src'))) / '.agents/skills/project-management-agent/scripts/pm_tasks.py'
spec = importlib.util.spec_from_file_location('pm_completion_under_test', SCRIPT)
pm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pm)


class CompletionPrerequisiteTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix='pm-completion-simulation-')
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.n = 0
        self.call('init', 'SIM-PM', config={'project': 'SIMULATED', 'pm_actor': 'SIM-PM',
                  'authorization': 'SIMULATED only', 'frontdoor_thread': 'SIMULATED', 'max_slots': 4})

    def call(self, op, actor='SIM-OWNER', **fields):
        self.n += 1
        return pm.execute(self.root, dict(op=op, actor=actor, event_id='SIM-' + str(self.n), **fields))

    def task(self, tid):
        return next(t for t in pm.execute(self.root, {'op': 'status'})['tasks'] if t['id'] == tid)

    def create(self, tid, **fields):
        data = dict(id=tid, parent=None, title='SIM ' + tid, owner='SIM-OWNER', checker='SIM-CHECKER',
                    goal='simulated', inputs=['in'], outputs=['out'], criteria=['ok'], next_action='next',
                    executor='SIMULATED executor; no agent started')
        data.update(fields)
        return self.call('create', 'SIM-PM', task=data)

    def mutate(self, op, tid, actor='SIM-OWNER', **fields):
        return self.call(op, actor, task_id=tid, expected_revision=self.task(tid)['revision'], **fields)

    def finish_work(self, tid):
        self.mutate('update', tid, changes={'evidence': ['SIMULATED evidence ' + tid]}, reason='SIMULATED work')
        self.mutate('review', tid, 'SIM-CHECKER', outcome='passed', criteria_checked=['ok'],
                    evidence=['SIMULATED check; no real verification'])

    def human(self, tid, outcome='approved'):
        self.mutate('human_review', tid, 'SIM-PM', outcome=outcome, presented_ref='shown.md', source='reply.md',
                    quote='SIMULATED reply, not a human decision', scope='SIMULATED scope')

    def close(self, tid):
        return self.mutate('transition', tid, 'SIM-PM', state='done', reason='SIMULATED close')

    def build(self):
        # Style anchors wait for a human; purchase logic does not depend on the style, but its
        # acceptance must use the confirmed style.
        self.create('D-1', title='风格锚点', human_required=True,
                    awaiting=[{'person': 'SIM-ART', 'action': 'decide', 'item': '确认风格锚点'}])
        self.finish_work('D-1')
        self.mutate('transition', 'D-1', state='waiting_review', reason='SIMULATED shown for review')
        self.create('E-1', title='商店购买逻辑', completion_requires=['D-1'])

    def test_work_starts_before_prerequisite_and_closes_only_after_it(self):
        self.build()
        self.assertTrue(self.task('E-1')['ready'])
        self.mutate('transition', 'E-1', state='running', reason='SIMULATED start', execution_receipt='SIMULATED receipt')
        self.mutate('transition', 'E-1', state='waiting_review', reason='SIMULATED returned', stop_evidence='SIMULATED stop')
        self.finish_work('E-1')
        self.assertEqual(['D-1'], self.task('E-1')['completion_pending'])
        with self.assertRaisesRegex(pm.TaskError, 'completion prerequisites not complete'):
            self.close('E-1')
        self.human('D-1')
        self.close('D-1')
        self.assertEqual([], self.task('E-1')['completion_pending'])
        # The prerequisite was accepted unchanged, so the earlier check is still current.
        self.assertTrue(self.task('E-1')['review_current'])
        self.close('E-1')
        self.assertFalse(self.task('E-1')['needs_recheck'])

    def test_prerequisite_rework_invalidates_checks_bound_to_it(self):
        self.build()
        self.finish_work('E-1')
        self.assertTrue(self.task('E-1')['review_current'])
        self.human('D-1', 'changes_requested')
        self.mutate('update', 'D-1', changes={'evidence': ['SIMULATED revised anchors']}, reason='SIMULATED rework')
        self.assertFalse(self.task('E-1')['review_current'])

    def test_reopened_prerequisite_marks_completed_work_for_recheck(self):
        self.build()
        self.human('D-1')
        self.close('D-1')
        self.finish_work('E-1')
        self.close('E-1')
        self.mutate('transition', 'D-1', 'SIM-PM', state='planned', reason='SIMULATED reopen')
        self.assertTrue(self.task('E-1')['needs_recheck'])

    def test_prerequisites_are_validated_and_mutual_waits_rejected(self):
        self.create('A')
        with self.assertRaisesRegex(pm.TaskError, 'also listed as dependency'):
            self.create('B', dependencies=['A'], completion_requires=['A'])
        with self.assertRaisesRegex(pm.TaskError, 'unknown or self completion prerequisite'):
            self.create('B', completion_requires=['missing'])
        with self.assertRaisesRegex(pm.TaskError, 'unknown or self completion prerequisite'):
            self.create('B', completion_requires=['B'])
        self.create('B', completion_requires=['A'])
        for field in ['completion_requires', 'dependencies']:
            with self.assertRaisesRegex(pm.TaskError, 'cycle'):
                self.mutate('update', 'A', changes={field: ['B']}, reason='SIMULATED mutual wait',
                            scope_authorization='SIMULATED decision')
        with self.assertRaisesRegex(pm.TaskError, 'authorization'):
            self.mutate('update', 'B', changes={'completion_requires': []}, reason='SIMULATED silent change')

    def test_tasks_without_prerequisites_keep_their_verification_basis(self):
        self.create('A')
        current = self.task('A')
        legacy = {k: v for k, v in current.items() if k != 'completion_requires'}
        self.assertEqual(pm.basis(current, {'A': current}), pm.basis(legacy, {'A': legacy}))

    def test_views_show_what_completion_waits_for(self):
        self.build()
        pm.render(self.root)
        views = self.root / 'management/views'
        self.assertIn('完成前置', (views / 'tasks/E-1.md').read_text(encoding='utf-8'))
        self.assertIn('影响完成：商店购买逻辑', (views / 'plan.md').read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
