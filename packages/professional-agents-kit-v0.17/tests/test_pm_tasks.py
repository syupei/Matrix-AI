"""Isolated behavioral tests. Every actor/receipt/human reply is SIMULATED.

No real agent is started, no human review occurs, and no message is delivered.
Run: python3 -m unittest discover -s tests -v (from the kit root).
"""
import copy
from concurrent.futures import ThreadPoolExecutor
import importlib.util
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / '.agents/skills/project-management-agent/scripts/pm_tasks.py'
spec = importlib.util.spec_from_file_location('pm_tasks_under_test', SCRIPT)
pm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pm)


class TaskRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='pm-isolated-simulation-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.serial = 0
        self.call('init', 'SIM-PM', config={
            'project': 'SIMULATED TEST ONLY', 'pm_actor': 'SIM-PM',
            'authorization': 'SIMULATED test authorization; no external action',
            'frontdoor_thread': 'SIMULATED-NOT-A-REAL-THREAD', 'max_slots': 2})

    def call(self, op, actor='SIM-OWNER', **fields):
        self.serial += 1
        return pm.execute(self.root, dict(op=op, actor=actor,
            event_id='SIM-EVENT-' + str(self.serial), **fields))

    def status(self):
        return pm.execute(self.root, {'op': 'status'})

    def task(self, tid):
        return next(t for t in self.status()['tasks'] if t['id'] == tid)

    def create(self, tid='T-1', parent=None, actor=None, **fields):
        manager = 'SIM-PM' if parent is None else self.task(parent)['owner']
        data = dict(id=tid, parent=parent, title='SIMULATED ' + tid,
            owner='SIM-OWNER', checker='SIM-CHECKER', goal='deliver test fixture',
            inputs=['SIMULATED input v1'], outputs=['evidence/' + tid + '.txt'],
            criteria=['fixture passes'], next_action='produce simulated fixture',
            executor='SIMULATED executor; no agent started')
        data.update(fields)
        return self.call('create', actor or manager, task=data)

    def mutate(self, op, tid='T-1', actor=None, **fields):
        task = self.task(tid)
        return self.call(op, actor or task['owner'], task_id=tid,
            expected_revision=task['revision'], **fields)

    def update(self, tid='T-1', **changes):
        return self.mutate('update', tid, changes=changes,
            reason='SIMULATED local fixture change')

    def transition(self, state, tid='T-1', actor=None, **fields):
        return self.mutate('transition', tid, actor, state=state,
            reason='SIMULATED state change', **fields)

    def review(self, tid='T-1', outcome='passed'):
        return self.mutate('review', tid, self.task(tid)['checker'],
            outcome=outcome, criteria_checked=self.task(tid)['criteria'],
            evidence=['SIMULATED checker evidence; no real verification'])

    def human(self, tid='T-1', outcome='approved'):
        return self.mutate('human_review', tid, 'SIM-PM', outcome=outcome,
            presented_ref='SIMULATED presentation', source='SIMULATED reply fixture',
            quote='SIMULATED approval, not a human decision', scope='SIMULATED fixture v1')

    def complete(self, tid='T-1'):
        self.update(tid, evidence=['SIMULATED work evidence ' + tid])
        self.review(tid)
        if self.task(tid)['human_required']:
            self.human(tid)
        return self.transition('done', tid, self.task(tid)['manager'])

    def events(self, **fields):
        return pm.execute(self.root, dict(op='events', **fields))['events']

    def assert_rejected_unchanged(self, action):
        before = self.status()
        logs = self.events()
        with self.assertRaises(pm.TaskError):
            action()
        after = self.status()
        self.assertEqual(before['tasks'], after['tasks'])
        self.assertEqual(before['revision'], after['revision'])
        self.assertEqual(logs, self.events())

    def test_each_level_has_its_own_manager_and_stable_id(self):
        self.create(owner='SIM-ENGINEER')
        self.create('T-1.a', 'T-1', owner='SIM-SPECIALIST')
        self.create('T-1.a.i', 'T-1.a')
        self.assertEqual('SIM-PM', self.task('T-1')['manager'])
        self.assertEqual('SIM-ENGINEER', self.task('T-1.a')['manager'])
        self.assertEqual('SIM-SPECIALIST', self.task('T-1.a.i')['manager'])
        self.assert_rejected_unchanged(lambda: self.create('T-1.bad', 'T-1', actor='SIM-PM'))
        self.assert_rejected_unchanged(lambda: self.mutate('update', 'T-1.a', 'SIM-PM',
            changes={'next_action': 'override'}, reason='SIMULATED improper override'))
        self.assert_rejected_unchanged(lambda: self.update('T-1', id='new-id'))

    def test_required_plan_precedes_execution(self):
        self.assert_rejected_unchanged(lambda: self.create(inputs=[]))
        self.assert_rejected_unchanged(lambda: self.create(criteria=[]))
        self.create(executor=None)
        self.assertFalse(self.task('T-1')['ready'])
        self.assert_rejected_unchanged(lambda: self.transition('running',
            execution_receipt='SIMULATED start'))
        self.update(executor='SIMULATED executor')
        self.assertTrue(self.task('T-1')['ready'])
        self.assert_rejected_unchanged(lambda: self.transition('running'))
        self.transition('running', execution_receipt='SIMULATED start receipt')

    def test_dependency_gates_readiness_until_verified_completion(self):
        self.create()
        self.create('T-2', dependencies=['T-1'])
        self.assertFalse(self.task('T-2')['ready'])
        self.assert_rejected_unchanged(lambda: self.transition('running', 'T-2',
            execution_receipt='SIMULATED start'))
        self.complete()
        self.assertTrue(self.task('T-2')['ready'])
        self.transition('running', 'T-2', execution_receipt='SIMULATED start')

    def test_dependency_and_containment_cycles_are_rejected(self):
        self.create()
        self.assert_rejected_unchanged(lambda: self.create('T-1.a', 'T-1', dependencies=['T-1']))
        self.create('T-2', dependencies=['T-1'])
        self.assert_rejected_unchanged(lambda: self.mutate('update', changes={'dependencies':['T-2']},
            reason='SIMULATED cycle', scope_authorization='SIMULATED manager authorization'))
        self.assert_rejected_unchanged(lambda: self.create('T-3', dependencies=['MISSING']))

    def test_global_capacity_counts_running_tasks_across_levels(self):
        self.create()
        self.create('T-1.a', 'T-1')
        self.create('T-2')
        self.transition('running', execution_receipt='SIMULATED parent start')
        self.transition('running', 'T-1.a', execution_receipt='SIMULATED child start')
        self.assertFalse(self.task('T-2')['ready'])
        self.assert_rejected_unchanged(lambda: self.transition('running', 'T-2',
            execution_receipt='SIMULATED blocked start'))
        self.assert_rejected_unchanged(lambda: self.transition('blocked', 'T-1.a'))
        self.transition('blocked', 'T-1.a', stop_evidence='SIMULATED actual yield receipt')
        self.assertTrue(self.task('T-2')['ready'])
        self.assertEqual('running', self.task('T-1')['state'])

    def test_exclusive_resource_conflict_and_release(self):
        self.create(resources=['shared-output'])
        self.create('T-2', resources=['shared-output'])
        self.transition('running', execution_receipt='SIMULATED start')
        self.assert_rejected_unchanged(lambda: self.transition('running', 'T-2',
            execution_receipt='SIMULATED competing start'))
        self.transition('blocked', stop_evidence='SIMULATED yielded')
        self.transition('running', 'T-2', execution_receipt='SIMULATED start')

    def test_racing_starts_cannot_overbook_capacity(self):
        self.create(slots=2)
        self.create('T-2', slots=2)
        def attempt(tid):
            try:
                return pm.execute(self.root, dict(op='transition', actor='SIM-OWNER',
                    event_id='SIM-RACE-' + tid, task_id=tid, expected_revision=1,
                    state='running', reason='SIMULATED simultaneous start',
                    execution_receipt='SIMULATED start, no real executor'))
            except pm.TaskError:
                return None
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(attempt, ['T-1', 'T-2']))
        self.assertEqual(1, sum(r is not None for r in results))
        self.assertEqual(1, sum(t['state'] == 'running' for t in self.status()['tasks']))

    def test_only_designated_checker_and_manager_can_close(self):
        self.create()
        self.assert_rejected_unchanged(lambda: self.transition('done', actor='SIM-PM'))
        self.update(evidence=['SIMULATED artifact'])
        self.assert_rejected_unchanged(lambda: self.mutate('review', actor='SIM-OWNER', outcome='passed',
            criteria_checked=['fixture passes'], evidence=['SIMULATED checker evidence']))
        self.assert_rejected_unchanged(lambda: self.mutate('review', actor='SIM-CHECKER', outcome='passed',
            criteria_checked=[], evidence=['SIMULATED checker evidence']))
        self.review(outcome='failed')
        self.assert_rejected_unchanged(lambda: self.transition('done', actor='SIM-PM'))
        self.review()
        self.assert_rejected_unchanged(lambda: self.transition('done'))
        self.transition('done', actor='SIM-PM')

    def test_human_gate_requires_recorded_explicit_decision_and_current_work(self):
        self.create(human_required=True)
        self.update(evidence=['SIMULATED work v1'])
        self.review()
        self.assert_rejected_unchanged(lambda: self.transition('done', actor='SIM-PM'))
        self.assert_rejected_unchanged(lambda: self.mutate('human_review', actor='SIM-PM', outcome='approved'))
        self.human(outcome='deferred')
        self.assert_rejected_unchanged(lambda: self.transition('done', actor='SIM-PM'))
        self.human()
        self.update(evidence=['SIMULATED work v2'])
        self.assertIsNone(self.task('T-1')['human_review'])
        self.review()
        self.assert_rejected_unchanged(lambda: self.transition('done', actor='SIM-PM'))
        self.human()
        self.transition('done', actor='SIM-PM')

    def test_owner_cannot_remove_human_gate_or_change_scope_silently(self):
        self.create(human_required=True)
        self.assert_rejected_unchanged(lambda: self.update(human_required=False))
        self.assert_rejected_unchanged(lambda: self.update(criteria=['different contract']))
        self.mutate('update', changes={'criteria':['different contract']},
            reason='SIMULATED approved scope change', scope_authorization='SIMULATED manager reference')

    def test_child_completion_does_not_complete_parent_or_replace_parent_review(self):
        self.create()
        self.create('T-1.a', 'T-1')
        self.complete('T-1.a')
        self.assertEqual('planned', self.task('T-1')['state'])
        self.assertEqual(0, self.status()['top_level']['done'])
        self.assert_rejected_unchanged(lambda: self.transition('done', actor='SIM-PM'))
        self.complete()
        self.assertEqual(1, self.status()['top_level']['done'])

    def test_descendant_work_invalidates_ancestor_review(self):
        self.create()
        self.create('T-1.a', 'T-1')
        self.create('T-1.a.i', 'T-1.a')
        self.update(evidence=['SIMULATED combined artifact'])
        self.review()
        self.assertTrue(self.task('T-1')['review_current'])
        self.update('T-1.a.i', evidence=['SIMULATED new descendant output'])
        self.assertFalse(self.task('T-1')['review_current'])

    def test_counts_are_per_layer_and_cancelled_is_not_done(self):
        self.create()
        self.create('T-2')
        self.create('T-1.a', 'T-1')
        self.create('T-1.b', 'T-1')
        self.complete('T-1.a')
        self.transition('cancelled', 'T-1.b', 'SIM-OWNER')
        self.assertEqual(2, self.status()['top_level']['total'])
        local = self.task('T-1')['child_counts']
        self.assertEqual((1,1,0,1), tuple(local[k] for k in ['total','done','remaining','cancelled']))
        self.create('T-1.c', 'T-1')
        self.assertEqual(2, self.status()['top_level']['total'])
        self.assertEqual(2, self.task('T-1')['child_counts']['total'])
        self.transition('planned', 'T-1.a', 'SIM-OWNER')
        self.assertEqual(0, self.task('T-1')['child_counts']['done'])

    def test_closed_tree_must_reopen_from_ancestors_before_new_work(self):
        self.create()
        self.create('T-1.a', 'T-1')
        self.complete('T-1.a')
        self.complete()
        self.assert_rejected_unchanged(lambda: self.create('T-1.b', 'T-1'))
        self.assert_rejected_unchanged(lambda: self.transition('planned', 'T-1.a', 'SIM-OWNER'))
        self.transition('planned', actor='SIM-PM')
        self.transition('planned', 'T-1.a', 'SIM-OWNER')
        self.assertFalse(self.task('T-1')['review_current'])

    def test_event_retry_is_idempotent_even_after_later_work(self):
        self.create()
        command = dict(op='update', actor='SIM-OWNER', event_id='SIM-RETRY', task_id='T-1',
            expected_revision=1, changes={'next_action':'SIMULATED next'}, reason='SIMULATED update')
        first = pm.execute(self.root, command)
        self.update(next_action='SIMULATED later action')
        before = self.status()
        self.assertEqual(first, pm.execute(self.root, command))
        self.assertEqual(before['tasks'], self.status()['tasks'])
        changed = copy.deepcopy(command)
        changed['changes']['next_action'] = 'conflicting retry'
        self.assert_rejected_unchanged(lambda: pm.execute(self.root, changed))
        self.assertEqual(1, sum(e['event_id']=='SIM-RETRY' for e in self.events()))

    def test_late_stale_revision_cannot_roll_back_source(self):
        self.create()
        self.update(next_action='SIMULATED latest')
        self.assert_rejected_unchanged(lambda: self.call('update', task_id='T-1', expected_revision=1,
            changes={'next_action':'SIMULATED obsolete'}, reason='SIMULATED late command',
            occurred_at='2000-01-01T00:00:00Z'))
        self.mutate('update', changes={'next_action':'SIMULATED current revision, old clock'},
            reason='SIMULATED clock skew', occurred_at='2000-01-01T00:00:00Z')
        self.assertEqual(3, self.task('T-1')['revision'])
        self.assertEqual('2000-01-01T00:00:00Z', self.events()[-1]['occurred_at'])

    def test_event_pagination_is_complete_and_ordered(self):
        self.create()
        self.update(next_action='SIMULATED next')
        first = self.events(limit=2)
        second = self.events(after=first[-1]['seq'], limit=2)
        self.assertEqual(self.events(), first + second)
        self.assertTrue(all(e['recorded_at'] and e['occurred_at'] for e in self.events()))
        self.assertEqual('planned', self.events()[-1]['before_data']['state'])

    def test_event_insert_failure_rolls_back_task_mutation(self):
        self.create()
        before = self.task('T-1')
        dbfile = self.root / 'management/runtime/tasks.sqlite3'
        with sqlite3.connect(dbfile) as db:
            db.execute("CREATE TRIGGER simulated_crash BEFORE INSERT ON events BEGIN SELECT RAISE(ABORT, 'SIMULATED event write failure'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            self.update(next_action='must never be committed')
        self.assertEqual(before, self.task('T-1'))
        with sqlite3.connect(dbfile) as db:
            db.execute('DROP TRIGGER simulated_crash')
        self.update(next_action='SIMULATED recovered')
        self.assertEqual(2, self.task('T-1')['revision'])

    def test_reports_distinguish_prepared_from_actual_delivery_receipts(self):
        self.create()
        payload = dict(summary='SIMULATED report', next_action='SIMULATED next', impact='none')
        self.mutate('report', delivery='prepared', **payload)
        self.assertEqual('prepared', self.task('T-1')['last_report']['delivery'])
        self.assert_rejected_unchanged(lambda: self.mutate('report', delivery='sent', **payload))
        self.mutate('report', delivery='received', receipt='SIMULATED ONLY, no real delivery',
            request_id='SIMULATED request', **payload)
        self.assertEqual('received', self.task('T-1')['last_report']['delivery'])
        self.assertEqual('planned', self.task('T-1')['state'])

    def test_handoff_preserves_history_and_requires_stopped_leaf(self):
        self.create()
        self.transition('running', execution_receipt='SIMULATED start')
        data = dict(new_owner='SIM-NEW-OWNER', acceptance_receipt='SIMULATED acceptance', reason='SIMULATED handoff')
        self.assert_rejected_unchanged(lambda: self.mutate('handoff', actor='SIM-PM', **data))
        self.transition('blocked', stop_evidence='SIMULATED stop')
        self.mutate('handoff', actor='SIM-PM', **data)
        self.assertEqual('SIM-NEW-OWNER', self.task('T-1')['owner'])
        self.assertIsNone(self.task('T-1')['executor'])
        self.assertEqual(4, len([e for e in self.events() if e['task_id']=='T-1']))
        self.create('T-1.a', 'T-1')
        self.assert_rejected_unchanged(lambda: self.mutate('handoff', actor='SIM-PM', **data))

    def test_render_is_rebuildable_and_does_not_change_task_source(self):
        self.create(human_required=True)
        self.create('T-1.a', 'T-1')
        self.transition('waiting_review')
        before = self.status()
        logs = self.events()
        rendered = pm.render(self.root)
        index = Path(rendered['view'])
        self.assertIn('tasks/T-1.md', index.read_text())
        detail = self.root / 'management/views/tasks/T-1.md'
        self.assertIn('T-1.a.md', detail.read_text())
        self.assertIn('尚未声明完整展开', detail.read_text())
        index.write_text('SIMULATED accidental view edit')
        pm.render(self.root)
        self.assertNotIn('SIMULATED accidental view edit', index.read_text())
        self.assertEqual(before['tasks'], self.status()['tasks'])
        self.assertEqual(logs, self.events())

    def test_cli_restart_recovers_persisted_source_and_history(self):
        self.create()
        self.update(next_action='SIMULATED resume point')
        proc = subprocess.run([sys.executable, str(SCRIPT), '--project', str(self.root)],
            input=json.dumps({'op':'status'}), text=True, capture_output=True, check=True)
        recovered = json.loads(proc.stdout)
        self.assertEqual(self.status()['tasks'], recovered['tasks'])
        self.assertEqual(self.status()['revision'], recovered['revision'])

    def test_paths_cannot_escape_project_via_id_or_symlink(self):
        self.assert_rejected_unchanged(lambda: self.create('../escape'))
        self.create()
        outside = self.root / 'outside-fixture'
        outside.mkdir()
        views = self.root / 'management/views'
        views.symlink_to(outside, target_is_directory=True)
        with self.assertRaises(pm.TaskError):
            pm.render(self.root)
        self.assertEqual([], list(outside.iterdir()))

    def test_completed_task_cannot_silently_acquire_failed_review(self):
        self.create()
        self.complete()
        try:
            self.review(outcome='failed')
        except pm.TaskError:
            pass  # Rejecting terminal reviews until explicit reopen is valid.
        current = self.task('T-1')
        self.assertFalse(current['state']=='done' and current['review']['outcome']=='failed',
            'Failed verification must not leave an actively counted completed task')

    def test_running_review_wait_requires_yield_evidence_before_freeing_capacity(self):
        self.create(slots=2)
        self.create('T-2', slots=2)
        self.transition('running', execution_receipt='SIMULATED start')
        self.assert_rejected_unchanged(lambda: self.transition('waiting_review'))
        self.transition('waiting_review', stop_evidence='SIMULATED execution yielded')
        self.assertTrue(self.task('T-2')['ready'])


    def test_dependency_rework_invalidates_downstream_review_without_rewriting_history(self):
        self.create()
        self.complete()
        self.create('T-2', dependencies=['T-1'])
        self.complete('T-2')
        recorded_done = [e for e in self.events() if e['task_id']=='T-2'][-1]
        self.assertTrue(self.task('T-2')['review_current'])
        self.transition('planned', actor='SIM-PM')
        self.assertFalse(self.task('T-2')['review_current'])
        self.assertTrue(any('T-1' in issue for issue in self.task('T-2')['readiness_issues']))
        self.assertEqual(0, self.status()['top_level']['done'])
        self.create('T-3', dependencies=['T-2'])
        self.assertFalse(self.task('T-3')['ready'])
        self.assert_rejected_unchanged(lambda: self.transition('running', 'T-3',
            execution_receipt='SIMULATED stale dependency attempt'))
        self.assertEqual(recorded_done, [e for e in self.events() if e['task_id']=='T-2'][-1])
        self.transition('planned', 'T-2', 'SIM-PM')
        self.complete()
        self.assert_rejected_unchanged(lambda: self.transition('done', 'T-2', 'SIM-PM'))
        self.review('T-2')
        self.transition('done', 'T-2', 'SIM-PM')

    def test_parent_review_before_child_finishes_cannot_close_parent_later(self):
        self.create()
        self.create('T-1.a', 'T-1')
        self.update(evidence=['SIMULATED parent artifact'])
        self.review()
        self.complete('T-1.a')
        self.assertFalse(self.task('T-1')['review_current'])
        self.assert_rejected_unchanged(lambda: self.transition('done', actor='SIM-PM'))
        self.review()
        self.transition('done', actor='SIM-PM')

    def test_live_resource_expansion_is_checked_against_global_capacity(self):
        self.create()
        self.create('T-2')
        self.transition('running', execution_receipt='SIMULATED first start')
        self.transition('running', 'T-2', execution_receipt='SIMULATED second start')
        self.assert_rejected_unchanged(lambda: self.update(slots=2))
        self.assert_rejected_unchanged(lambda: self.update(executor=None))

    def test_report_or_next_action_does_not_invalidate_verified_work(self):
        self.create()
        self.update(evidence=['SIMULATED artifact'])
        self.review()
        basis = self.task('T-1')['review']['basis']
        self.mutate('report', delivery='prepared', summary='SIMULATED checkpoint',
            next_action='SIMULATED request closure', impact='none')
        self.assertEqual(basis, self.task('T-1')['review']['basis'])
        self.assertTrue(self.task('T-1')['review_current'])
        self.transition('done', actor='SIM-PM')

    def test_review_and_human_evidence_are_findable_from_task_detail(self):
        self.create(human_required=True)
        evidence_dir = self.root / 'evidence'
        evidence_dir.mkdir()
        for name in ['work.txt', 'check.txt', 'presentation.txt', 'reply.txt']:
            (evidence_dir / name).write_text('SIMULATED fixture, not real evidence')
        self.update(evidence=['evidence/work.txt'])
        self.mutate('review', actor='SIM-CHECKER', outcome='passed',
            criteria_checked=['fixture passes'], evidence=['evidence/check.txt'])
        self.mutate('human_review', actor='SIM-PM', outcome='approved',
            presented_ref='evidence/presentation.txt', source='evidence/reply.txt',
            quote='SIMULATED decision; no actual human review', scope='SIMULATED fixture')
        pm.render(self.root)
        detail = (self.root / 'management/views/tasks/T-1.md').read_text()
        for name in ['work.txt', 'check.txt', 'presentation.txt', 'reply.txt']:
            self.assertIn('evidence/' + name, detail)


if __name__ == '__main__':
    unittest.main()
