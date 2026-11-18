"""Single-conversation confirmation failures must not consume a valid human reply."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from kit import KIT
from practice_fixture import direction, put, scope

spec = importlib.util.spec_from_file_location('retry_tone', KIT / 'matrix/base/tools/tone_contract.py')
tone = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tone)


class ConfirmationRetry(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        _, data = direction(self.root, tone)
        data.pop('confirmation')
        draft = put(self.root, tone.DEFAULT_PATH, '```tone-contract\n' + json.dumps(data) + '\n```\n')
        digest = tone.direction_binding(tone.DEFAULT_PATH, data)['direction_sha256']
        display = put(self.root, 'shown.md', 'SIM actual displayed direction ' + digest)
        reply = put(self.root, 'answer.md', 'SIM actual new complete approval')
        self.binding = dict(format='matrix-review-binding/1', request_id='R', scope=['workspace'],
                            person='owner', quote='SIM actual new complete approval', outcome='approved', actor='user',
                            direction_sha256=digest, direction_draft=draft, display=display,
                            response=dict(reply, message_sha256=tone.evidence.digest('SIM actual new complete approval')))

    def invoke(self):
        put(self.root, 'binding.json', self.binding)
        run = subprocess.run([sys.executable, '-B', str(KIT/'matrix/base/tools/review_evidence.py'),
                              '--project', str(self.root), '--review-binding', 'binding.json'],
                             text=True, capture_output=True)
        return run.returncode, json.loads(run.stdout)

    def registrations(self):
        return set((self.root/'management/review-bindings').glob('*.json'))

    def test_stale_display_failure_leaves_no_binding_and_corrected_retry_succeeds(self):
        before = self.registrations()
        self.binding['display']['sha256'] = '0'*64
        self.assertEqual(1, self.invoke()[0])
        self.assertEqual(before, self.registrations())
        self.binding['display'] = tone.evidence.ref(self.root, 'shown.md')
        self.assertEqual(0, self.invoke()[0])

    def test_wrong_direction_digest_does_not_burn_the_reply(self):
        expected = self.binding['direction_sha256']
        before = self.registrations()
        self.binding['direction_sha256'] = '0'*64
        self.assertEqual(1, self.invoke()[0])
        self.assertEqual(before, self.registrations())
        self.binding['direction_sha256'] = expected
        self.assertEqual(0, self.invoke()[0])

    def test_old_display_cannot_bind_new_direction_by_inventing_a_message_id(self):
        self.binding['display'] = put(self.root, 'shown.md', 'SIM old direction shown without this draft version')
        self.binding['response'] = dict(put(self.root, 'answer.json', {'messages':[{'id':'invented', 'text':self.binding['quote']}]}),
                                       response_id='invented', message_sha256=tone.evidence.digest(self.binding['quote']))
        code, result = self.invoke()
        self.assertEqual(1, code)
        self.assertIn('display', result['error'])

    def two_activities(self):
        _, data = direction(self.root, tone, rows=[scope(tone), scope(tone, 'admin')])
        data.pop('confirmation')
        self.binding['direction_draft'] = put(self.root, tone.DEFAULT_PATH,
                                             '```tone-contract\n'+json.dumps(data)+'\n```\n')
        digest = tone.direction_binding(tone.DEFAULT_PATH, data)['direction_sha256']
        self.binding['direction_sha256'] = digest
        self.binding['display'] = put(self.root, 'shown.md', 'SIM actual displayed direction '+digest)
        return data

    def test_incomplete_or_extra_scope_does_not_consume_reply_before_corrected_retry(self):
        self.two_activities()
        before = self.registrations()
        for ids in (['workspace'], ['workspace','admin','unknown'], ['workspace','workspace']):
            self.binding['scope'] = ids
            code, result = self.invoke()
            self.assertEqual(1, code)
            self.assertIn('all activity scopes', result['error'])
            self.assertEqual(before, self.registrations())
        self.binding['scope'] = ['workspace','admin']
        code, result = self.invoke()
        self.assertEqual(0, code)
        self.binding['scope'] = ['admin','workspace']
        code, reordered = self.invoke()
        self.assertEqual(0, code)
        self.assertEqual(result['review_receipt'],reordered['review_receipt'])

    def test_legacy_partial_approval_cannot_confirm_unreviewed_activity(self):
        data = self.two_activities()
        receipt = tone.evidence.review_receipt(self.root, self.binding)
        data['confirmation'] = dict(person=self.binding['person'], quote=self.binding['quote'],
                                    source=self.binding['response']['path'],
                                    direction_sha256=self.binding['direction_sha256'], review_receipt=receipt)
        put(self.root, tone.DEFAULT_PATH, '```tone-contract\n'+json.dumps(data)+'\n```\n')
        with self.assertRaisesRegex(ValueError, 'all activity scopes'):
            tone.validate(self.root, tone.DEFAULT_PATH)
