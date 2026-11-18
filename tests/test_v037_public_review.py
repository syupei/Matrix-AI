"""Public PM review acceptance, with synthetic people and no direct database writes."""
import ast
import json
from pathlib import Path
import unittest

from test_pm_instances import Fixture, pm
from practice_fixture import put, review_state
from public_review_fixture import stage_receipt


class PublicReview(Fixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.staff()

    def shown(self, attention='stage-review', task=None):
        gate = pm.admission.load_gate()
        artifact = put(self.root, 'product/specs/current.md', 'SIM confirmed product definition')
        state = review_state(self.root, gate, [artifact['path']], prefix=attention)
        request = json.loads((self.root / state['request']).read_text())
        reply = json.loads((self.root / state['response']).read_text())
        reply['quote'] = 'SIM actual approval ' + attention
        reply['message_sha256'] = gate.tone.evidence.digest(reply['quote'])
        put(self.root, reply['source'], reply['quote'])
        put(self.root, state['response'], reply)
        self.call('human_attention', id=attention, kind='confirmation', task_id=task,
                  display=request['display_evidence'], scope=state['scope'], inputs=[artifact['path']])
        self.call('human_attention', id=attention, response=reply['source'])
        return state, request, reply

    def test_public_stage_confirmation_covers_actual_displayed_artifacts(self):
        state, _, reply = self.shown()
        reply['review_receipt'] = stage_receipt(self, state, 'stage-review', 'SIM-owner')
        put(self.root, state['response'], reply)
        self.assertTrue(pm.admission.load_gate().check(self.root, state)['allowed'])

    def test_public_confirmation_retry_is_idempotent(self):
        state,_,_=self.shown()
        first=stage_receipt(self,state,'stage-review','SIM-owner')
        self.assertEqual(first,stage_receipt(self,state,'stage-review','SIM-owner'))

    def test_stage_confirmation_rejects_changed_artifacts_and_unanswered_request(self):
        state, _, _ = self.shown()
        with self.assertRaisesRegex(ValueError, 'actual answered'):
            stage_receipt(self, state, 'unanswered', 'SIM-owner')
        put(self.root, 'product/specs/current.md', 'SIM changed after display')
        with self.assertRaisesRegex(ValueError, 'changed|stale'):
            stage_receipt(self, state, 'stage-review', 'SIM-owner')

    def test_task_human_review_returns_a_trusted_receipt(self):
        self.create('T', human_required=True)
        state, request, reply = self.shown(task='T')
        result = self.mutate('human_review', 'T', 'PM', outcome='approved', person='SIM-owner',
                             attention_id='stage-review', presented_ref=request['display_evidence'],
                             source=reply['source'], quote=reply['quote'], scope=state['scope'])
        receipt = result['task']['human_review']['review_receipt']
        binding = pm.admission.load_gate().tone.evidence.verify_human_receipt(
            self.root, receipt, artifacts=state['artifacts'])
        self.assertEqual('T', binding['task_id'])
        self.create('OTHER', human_required=True)
        with self.assertRaisesRegex(ValueError, 'request for this task'):
            self.mutate('human_review', 'OTHER', 'PM', outcome='approved', person='SIM-owner',
                         attention_id='stage-review', presented_ref=request['display_evidence'],
                         source=reply['source'], quote=reply['quote'], scope=state['scope'])


class PublicAcceptanceGuard(unittest.TestCase):
    def test_acceptance_files_do_not_bind_receipts_or_write_database_internally(self):
        for name in ('test_v037_public_review.py', 'public_review_fixture.py',
                     'test_v037_round2_pipeline.py', 'test_v037_round2_pm_stages.py',
                     'test_v037_direction_recovery.py','test_v037_rework_public.py',
                     'test_v037_game_pm_public.py','pm_game_fixture.py','test_v037_longchain_public.py','longchain_fixture.py'):
            tree = ast.parse(Path(__file__).with_name(name).read_text())
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                    continue
                self.assertNotIn(node.func.attr, {'bind_attention', 'review_receipt', 'save', 'executemany', 'executescript'}, name)
                if node.func.attr == 'execute' and node.args and isinstance(node.args[0], ast.Constant):
                    self.assertFalse(isinstance(node.args[0].value, str), name + ': direct SQL')
