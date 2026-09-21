#!/usr/bin/env python3
"""Isolated ledger tests. User-message evidence here is simulated, never real approval.
Run: python3 -m unittest discover -s <this directory> -v
"""
import concurrent.futures
import hashlib
from pathlib import Path
import tempfile
import unittest

from coordination import CoordinationError, execute


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        for path, text in {'skills/p.md': 'product', 'skills/e.md': 'engineering',
                           'product/base.md': 'Business rule v1',
                           'engineering/base.md': 'Engineering model v1'}.items():
            file = self.root / path
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_text(text)
        self.config = {'protocol': 'professional-collaboration/0.1',
                       'authorization': 'SIMULATED TEST ONLY',
                       'frontdoor': {'thread_id': 'test-v2'}, 'max_rounds': 3}
        execute(self.root, {'op': 'init', 'config': self.config})
        self.register('engineering', 'skills/e.md', ['engineering'], 'test-engineering')
        self.register('product', 'skills/p.md', ['product'], 'test-product')

    def runop(self, op, actor='coordinator', rid='R1', **kwargs):
        return execute(self.root, {'op': op, 'actor': actor, 'id': rid, **kwargs})

    def register(self, role, skill, roots, endpoint):
        return execute(self.root, {'op': 'register', 'actor': 'coordinator', 'role': {
            'id': role, 'skill': skill, 'write_roots': roots,
            'endpoint': {'kind': 'subagent', 'id': endpoint, 'session': 'simulated-session'}}})

    def request(self, rid='R1', **extra):
        payload = {'id': rid, 'source': 'engineering', 'target': 'product',
                   'question': 'What does the rule mean?', 'expected_output': 'Sourced answer',
                   'authorization': 'SIMULATED: explain or clarify existing source within product scope',
                   'write_allowed': ['product'],
                   'sources': ['product/base.md', 'engineering/base.md']}
        payload.update(extra)
        return self.runop('request', 'engineering', rid, request=payload)

    def claimed(self, rid='R1'):
        self.request(rid)
        return self.runop('claim', rid=rid)['attempt']

    def response(self, token, kind='explanation', **extra):
        answer = {'kind': kind, 'summary': 'Existing rule explained',
                  'evidence': ['product/base.md — simulated source']}
        answer.update(extra)
        return self.runop('respond', 'product', attempt=token, response=answer)

    def needs_human(self):
        token = self.claimed()
        req = self.response(token, 'needs_human', question={
            'prompt': 'Choose a retention rule', 'why': 'No rule in source',
            'scope': 'Retention only'})
        return token, req['question_hash']

    def present(self, question_hash):
        return self.runop('presented', question_hash=question_hash,
                          evidence='SIMULATED conversation presentation')

    def human_answer(self, question_hash, **extra):
        command = {'question_hash': question_hash, 'answer': 'Retain for 30 days',
                   'evidence': {'kind': 'user_message', 'thread_id': 'test-v2',
                                'quote': 'SIMULATED: retain for 30 days'}}
        command.update(extra)
        return self.runop('human_answer', **command)

    def test_happy_path_requires_requester_adoption(self):
        token = self.claimed()
        self.runop('receipt', attempt=token, outcome='sent', evidence='simulated host result')
        self.assertEqual(self.response(token)['state'], 'answered')
        with self.assertRaises(CoordinationError):
            self.runop('accept', 'product', result='Do not self-approve')
        self.assertEqual(self.runop('accept', 'engineering', result='Used interpretation')['state'], 'closed')

    def test_request_idempotency_and_payload_conflict(self):
        first = self.request()
        self.assertEqual(first, self.request())
        with self.assertRaises(CoordinationError):
            self.request(question='Different content')

    def test_answer_idempotency_and_conflict(self):
        token = self.claimed()
        first = self.response(token)
        self.assertEqual(first, self.response(token))
        with self.assertRaises(CoordinationError):
            self.response(token, summary='Changed answer')

    def test_claim_rechecks_baseline(self):
        self.request()
        (self.root / 'product/base.md').write_text('Human changed the source')
        self.assertEqual(self.runop('claim')['state'], 'stale')

    def test_response_rechecks_baseline(self):
        token = self.claimed()
        (self.root / 'product/base.md').write_text('Changed source')
        self.assertEqual(self.response(token)['state'], 'stale')

    def test_accept_rechecks_baseline(self):
        token = self.claimed()
        self.response(token)
        (self.root / 'product/base.md').write_text('Changed after response')
        self.assertEqual(self.runop('accept', 'engineering', result='Trying adoption')['state'], 'stale')

    def test_cancel_rejects_late_response(self):
        token = self.claimed()
        self.runop('cancel', 'engineering', reason='Superseded')
        with self.assertRaises(CoordinationError):
            self.response(token)

    def test_claim_is_atomic_under_concurrency(self):
        self.request()
        def attempt(_):
            try:
                return self.runop('claim')['state']
            except CoordinationError:
                return 'rejected'
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            results = list(pool.map(attempt, range(6)))
        self.assertEqual(results.count('dispatching'), 1)
        self.assertEqual(results.count('rejected'), 5)

    def test_same_owner_requests_serialize(self):
        self.claimed()
        self.request('R2')
        with self.assertRaises(CoordinationError):
            self.runop('claim', rid='R2')

    def test_active_role_cannot_be_rebound(self):
        self.claimed()
        with self.assertRaises(CoordinationError):
            self.register('product', 'skills/p.md', ['product'], 'new-agent')

    def test_unknown_actor_cannot_mutate(self):
        self.request()
        with self.assertRaises(CoordinationError):
            self.runop('cancel', 'outsider', reason='Unauthorized')

    def test_path_escape_rejected(self):
        with self.assertRaises(CoordinationError):
            self.request(sources=['../outside.md'])

    def test_symlink_escape_rejected(self):
        with tempfile.TemporaryDirectory() as outside:
            (Path(outside) / 'source.md').write_text('Outside project')
            (self.root / 'outside').symlink_to(outside, target_is_directory=True)
            with self.assertRaises(CoordinationError):
                self.request(sources=['outside/source.md'])

    def test_other_owner_update_rejected(self):
        token = self.claimed()
        path = self.root / 'engineering/base.md'
        path.write_text('Changed')
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
        with self.assertRaises(CoordinationError):
            self.response(token, updated_sources={'engineering/base.md': sha},
                          change_authorization='Claiming unsupported permission')

    def test_no_request_write_permission_rejects_source_update(self):
        self.request(write_allowed=[])
        token = self.runop('claim')['attempt']
        path = self.root / 'product/base.md'
        path.write_text('Unauthorized clarification')
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
        with self.assertRaises(CoordinationError):
            self.response(token, updated_sources={'product/base.md': sha},
                          change_authorization='Role ownership is not request authority')

    def test_owned_update_can_be_adopted(self):
        token = self.claimed()
        path = self.root / 'product/base.md'
        path.write_text('Authorized source clarification')
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
        self.assertEqual(self.response(token, updated_sources={'product/base.md': sha},
                                       change_authorization='SIMULATED delegated clarification')['state'], 'answered')
        self.assertEqual(self.runop('accept', 'engineering', result='Applied current source')['state'], 'closed')

    def test_uncertain_delivery_cannot_retry_or_release_owner(self):
        token = self.claimed()
        self.runop('receipt', attempt=token, outcome='uncertain', evidence='Simulated host timeout')
        with self.assertRaises(CoordinationError):
            self.runop('retry')
        self.request('R2')
        with self.assertRaises(CoordinationError):
            self.runop('claim', rid='R2')

    def test_confirmed_not_sent_retry_changes_token(self):
        token = self.claimed()
        self.runop('receipt', attempt=token, outcome='not_sent', evidence='Simulated rejection before delivery')
        self.runop('retry')
        new = self.runop('claim')['attempt']
        self.assertNotEqual(token, new)
        with self.assertRaises(CoordinationError):
            self.response(token)

    def test_receipt_after_fast_answer_does_not_reopen(self):
        token = self.claimed()
        self.response(token)
        self.assertEqual(self.runop('receipt', attempt=token, outcome='sent',
                                    evidence='Simulated delayed tool return')['state'], 'answered')

    def test_human_answer_requires_presented_current_question(self):
        _, qh = self.needs_human()
        with self.assertRaises(CoordinationError):
            self.human_answer(qh)
        self.present(qh)
        with self.assertRaises(CoordinationError):
            self.human_answer('outdated-hash')

    def test_human_answer_requires_frontdoor_user_message(self):
        _, qh = self.needs_human()
        self.present(qh)
        for evidence in [
            {'kind': 'agent_message', 'thread_id': 'test-v2', 'quote': 'yes'},
            {'kind': 'user_message', 'thread_id': 'other-task', 'quote': 'yes'},
            {'kind': 'user_message', 'thread_id': 'test-v2'},
        ]:
            with self.subTest(evidence=evidence), self.assertRaises(CoordinationError):
                self.human_answer(qh, evidence=evidence)
        with self.assertRaises(CoordinationError):
            self.runop('human_answer', 'product', question_hash=qh, answer='yes',
                       evidence={'kind': 'user_message', 'thread_id': 'test-v2', 'quote': 'SIMULATED'})

    def test_human_answer_rechecks_current_baseline(self):
        _, qh = self.needs_human()
        self.present(qh)
        (self.root / 'product/base.md').write_text('Changed while human considered question')
        req = self.human_answer(qh)
        self.assertEqual(req['state'], 'stale')
        self.assertEqual(req['human_answers'], [])

    def test_human_answer_readies_owner_for_new_wake(self):
        old_token, qh = self.needs_human()
        self.present(qh)
        req = self.human_answer(qh)
        self.assertEqual((req['state'], req['round']), ('ready', 2))
        token = self.runop('claim')['attempt']
        self.assertNotEqual(token, old_token)
        packet = self.runop('packet')
        self.assertEqual(len(packet['request']['human_answers']), 1)
        with self.assertRaises(CoordinationError):
            self.response(old_token)
        self.assertEqual(self.response(token)['state'], 'answered')

    def test_cycle_is_rejected(self):
        self.request()
        payload = {'id': 'R2', 'source': 'product', 'target': 'engineering',
                   'question': 'Reciprocal wait', 'expected_output': 'answer',
                   'authorization': 'test', 'sources': ['product/base.md']}
        with self.assertRaises(CoordinationError):
            self.runop('request', 'product', 'R2', request=payload)

    def test_frontdoor_thread_self_dispatch_rejected(self):
        execute(self.root, {'op': 'register', 'actor': 'coordinator', 'role': {
            'id': 'product', 'skill': 'skills/p.md', 'write_roots': ['product'],
            'endpoint': {'kind': 'thread', 'id': 'test-v2', 'session': 'simulated'}}})
        self.request()
        with self.assertRaises(CoordinationError):
            self.runop('claim')

    def test_rejected_answer_rolls_back_without_partial_record(self):
        token = self.claimed()
        with self.assertRaises(CoordinationError):
            self.response(token, 'needs_human', question={'prompt': 'Incomplete'})
        req = self.runop('show')
        self.assertEqual(req['state'], 'dispatching')
        self.assertEqual(req['responses'], [])

    def test_professional_decision_requires_delegated_authority(self):
        token = self.claimed()
        with self.assertRaises(CoordinationError):
            self.response(token, 'decision')
        self.assertEqual(self.response(token, 'decision',
                                       decision_authorization='SIMULATED scope delegation')['state'], 'answered')

    def test_concurrent_conflicting_answers_only_commit_once(self):
        token = self.claimed()
        def attempt(number):
            try:
                return self.response(token, summary='Concurrent answer ' + str(number))['state']
            except CoordinationError:
                return 'rejected'
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(attempt, range(4)))
        self.assertEqual(results.count('answered'), 1)
        self.assertEqual(len(self.runop('show')['responses']), 1)

    def test_late_old_receipt_cannot_overwrite_next_human_round(self):
        old_token, qh = self.needs_human()
        self.present(qh)
        self.human_answer(qh)
        new_token = self.runop('claim')['attempt']
        with self.assertRaises(CoordinationError):
            self.runop('receipt', attempt=old_token, outcome='sent', evidence='Late first round')
        self.assertEqual(self.runop('show')['attempt'], new_token)

    # Regression expectations below capture safety gaps found during independent review.
    def test_unavailable_response_is_not_not_sent_and_cannot_auto_retry(self):
        token = self.claimed()
        self.response(token, 'unavailable')
        with self.assertRaises(CoordinationError):
            self.runop('retry')

    def test_write_root_cannot_normalize_to_entire_project(self):
        with self.assertRaises(CoordinationError):
            self.register('unsafe', 'skills/p.md', ['product/..'], 'unsafe-agent')

    def test_distinct_roles_cannot_dispatch_to_same_live_endpoint(self):
        self.register('product', 'skills/p.md', ['product'], 'test-engineering')
        self.request()
        with self.assertRaises(CoordinationError):
            self.runop('claim')

    def test_overlapping_write_owners_cannot_run_concurrently(self):
        self.register('product-helper', 'skills/p.md', ['product'], 'helper-agent')
        self.claimed()
        self.request('R2', target='product-helper')
        with self.assertRaises(CoordinationError):
            self.runop('claim', rid='R2')

    def test_cancelled_running_worker_does_not_silently_release_write_owner(self):
        self.claimed()
        self.runop('cancel', 'engineering', reason='Changed request; worker has not stopped')
        self.request('R2')
        with self.assertRaises(CoordinationError):
            self.runop('claim', rid='R2')

    def test_cancel_settled_by_host_completion_releases_owner(self):
        token = self.claimed()
        self.runop('receipt', attempt=token, outcome='sent', evidence='SIMULATED accepted send')
        self.runop('cancel', 'engineering', reason='SIMULATED replacement')
        req = self.runop('settle_cancel', attempt=token, outcome='completed',
                         evidence='SIMULATED host status: previous worker completed')
        self.assertFalse(req['lease_active'])
        self.request('R2')
        self.assertEqual(self.runop('claim', rid='R2')['state'], 'dispatching')

    def test_cancel_settlement_requires_current_attempt_and_host_evidence(self):
        token = self.claimed()
        self.runop('cancel', 'engineering', reason='SIMULATED cancel')
        for extra in [dict(attempt='old-token', evidence='SIMULATED stopped'),
                      dict(attempt=token, evidence='')]:
            with self.subTest(extra=extra), self.assertRaises(CoordinationError):
                self.runop('settle_cancel', outcome='stopped', **extra)
        self.assertTrue(self.runop('show')['lease_active'])

    def test_cancel_unsettled_worker_prevents_role_rebind(self):
        token = self.claimed()
        self.runop('cancel', 'engineering', reason='SIMULATED cancel')
        with self.assertRaises(CoordinationError):
            self.register('product', 'skills/p.md', ['product'], 'replacement-agent')
        self.runop('settle_cancel', attempt=token, outcome='stopped',
                   evidence='SIMULATED host interrupt acknowledged')
        self.assertEqual(self.register('product', 'skills/p.md', ['product'],
                                       'replacement-agent')['endpoint']['id'], 'replacement-agent')

    def test_cancel_of_never_dispatched_request_does_not_hold_owner(self):
        self.request()
        self.runop('cancel', 'engineering', reason='SIMULATED discard before send')
        self.assertFalse(self.runop('show')['lease_active'])
        self.request('R2')
        self.assertEqual(self.runop('claim', rid='R2')['state'], 'dispatching')

    def test_database_symlink_outside_project_is_rejected_without_touching_target(self):
        with tempfile.TemporaryDirectory() as outside, tempfile.TemporaryDirectory() as project:
            external = Path(outside) / 'sentinel.db'
            external.write_bytes(b'outside sentinel must remain unchanged')
            runtime = Path(project) / 'collaboration/runtime'
            runtime.mkdir(parents=True)
            (runtime / 'state.sqlite3').symlink_to(external)
            with self.assertRaises(CoordinationError):
                execute(project, {'op': 'init', 'config': self.config})
            self.assertEqual(external.read_bytes(), b'outside sentinel must remain unchanged')

    def test_active_same_endpoint_with_disjoint_roots_cannot_run_parallel(self):
        self.register('helper', 'skills/p.md', ['helper-output'], 'test-product')
        self.claimed()
        self.request('R2', target='helper', write_allowed=[])
        with self.assertRaises(CoordinationError):
            self.runop('claim', rid='R2')

    def test_parent_child_write_roots_cannot_run_parallel(self):
        self.register('helper', 'skills/p.md', ['product/nested'], 'helper-agent')
        self.claimed()
        self.request('R2', target='helper', write_allowed=['product/nested'])
        with self.assertRaises(CoordinationError):
            self.runop('claim', rid='R2')

    def test_independent_owners_and_endpoints_can_run_parallel(self):
        self.register('helper', 'skills/p.md', ['helper-output'], 'helper-agent')
        self.claimed()
        self.request('R2', target='helper', write_allowed=['helper-output'])
        self.assertEqual(self.runop('claim', rid='R2')['state'], 'dispatching')

    def test_same_real_thread_id_with_different_session_labels_is_self_call(self):
        for role, skill, roots, session in [
            ('engineering', 'skills/e.md', ['engineering'], 'session-a'),
            ('product', 'skills/p.md', ['product'], 'session-b')]:
            execute(self.root, {'op': 'register', 'actor': 'coordinator', 'role': {
                'id': role, 'skill': skill, 'write_roots': roots,
                'endpoint': {'kind': 'thread', 'id': 'same-real-task', 'session': session}}})
        self.request()
        with self.assertRaises(CoordinationError):
            self.runop('claim')

    def test_confirmed_sent_cancel_cannot_be_settled_as_not_sent(self):
        token = self.claimed()
        self.runop('receipt', attempt=token, outcome='sent', evidence='SIMULATED confirmed send')
        self.runop('cancel', 'engineering', reason='SIMULATED replacement')
        with self.assertRaises(CoordinationError):
            self.runop('settle_cancel', attempt=token, outcome='not_sent',
                       evidence='SIMULATED contradictory receipt')
        self.assertTrue(self.runop('show')['lease_active'])


if __name__ == '__main__':
    unittest.main()
