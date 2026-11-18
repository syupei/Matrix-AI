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

    def test_new_direction_can_use_same_words_from_a_distinct_real_reply_source(self):
        self.assertEqual(0,self.invoke()[0])
        data=tone.read(self.root,self.binding['direction_draft']['path'])
        data['tone']='SIM revised direction shown in a new actual request'
        self.binding['direction_draft']=put(self.root,tone.DEFAULT_PATH,'```tone-contract\n'+json.dumps(data)+'\n```\n')
        self.binding['direction_sha256']=tone.direction_binding(tone.DEFAULT_PATH,data)['direction_sha256']
        self.binding['display']=put(self.root,'shown-v2.md','SIM new displayed direction '+self.binding['direction_sha256'])
        self.binding['request_id']='R2'
        code,result=self.invoke()
        self.assertEqual(1,code)
        self.assertIn('already bound',result['error'])
        self.binding['response']=dict(put(self.root,'answer-R2.md',self.binding['quote']),
                                      message_sha256=tone.evidence.digest(self.binding['quote']))
        code,result=self.invoke()
        self.assertEqual(0,code,result)

    def test_no_capture_draft_uses_one_display_and_reply_through_p1(self):
        registrations_before=self.registrations()
        data=tone.read(self.root,self.binding['direction_draft']['path'])
        data['parts'].pop('screenshot');data.pop('capture_binding',None)
        data['capture_unavailable']='SIM host has no capture channel; actual viewport is shown to the person'
        data['parts']['manual_review']=put(self.root,'manual-viewport.md','SIM current actual viewport displayed at 1280x800')
        put(self.root,tone.DEFAULT_PATH,'```tone-contract\n'+json.dumps(data)+'\n```\n')
        draft=subprocess.run([sys.executable,'-B',str(KIT/'matrix/base/tools/tone_contract.py'),
            '--project',str(self.root),'--draft'],text=True,capture_output=True)
        result=json.loads(draft.stdout)
        self.assertEqual('draft_incomplete',result['status'])
        self.binding.update(direction_draft=result['draft'],direction_sha256=result['direction_reference']['direction_sha256'],
            artifacts=list(data['parts'].values()))
        self.binding['display']=put(self.root,'shown.md','SIM actual direction and viewport '+self.binding['direction_sha256'])
        code,approved=self.invoke();self.assertEqual(0,code,approved)
        data['confirmation']=dict(person='owner',quote=self.binding['quote'],source=self.binding['response']['path'],
            direction_sha256=self.binding['direction_sha256'],review_receipt=approved['review_receipt'])
        contract=dict(put(self.root,tone.DEFAULT_PATH,'```tone-contract\n'+json.dumps(data)+'\n```\n'),version=data['version'])
        fit=put(self.root,'fit-manual.json',dict(tone_contract=result['direction_reference'],binding_mode='pre_confirmation_direction',
            mode='human',producer='SIM-maker',checker='owner',outcome='passed',artifacts=list(data['parts'].values()),
            viewport='1280x800',capture='SIM actual manual viewport observation',genre_fit='SIM activity remains clear',
            application_drift='SIM checked controls in activity',copy_fit='SIM words match the moment',
            manual_review=data['parts']['manual_review'],capture_unavailable=data['capture_unavailable'],human_review_receipt=approved['review_receipt']))
        spec=importlib.util.spec_from_file_location('single_no_capture_gate',KIT/'matrix/base/tools/stage_gate.py')
        gate=importlib.util.module_from_spec(spec);spec.loader.exec_module(gate)
        digest=gate.artifact_digest(self.root,[contract]);display=self.binding['display']
        request=put(self.root,'request.json',dict(request_id='R',role='product',stage='P-1',scope=['workspace'],artifact_sha256=digest,
            display_evidence=display['path'],display_sha256=display['sha256']))
        response=put(self.root,'response.json',dict(request_id='R',actor='user',choice='confirm',scope=['workspace'],artifact_sha256=digest,
            source=self.binding['response']['path'],quote=self.binding['quote'],message_sha256=tone.evidence.digest(self.binding['quote']),display_sha256=display['sha256']))
        state=put(self.root,'p1.json',dict(role='product',current='P-1',next='P-2',scope=['workspace'],blockers=[],artifacts=[contract],tone_contract=contract,
            tone_fit_review=fit['path'],request=request['path'],response=response['path'],conversation_check=put(self.root,'conversation.md','P-1->P-2')['path']))
        run=subprocess.run([sys.executable,'-B',str(KIT/'matrix/base/tools/stage_gate.py'),'--project',str(self.root),'--state',str(self.root/state['path'])],text=True,capture_output=True)
        self.assertEqual(0,run.returncode,run.stdout+run.stderr)
        self.assertEqual(1,len(self.registrations()-registrations_before))

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
