"""Direction artifacts, confirmation and fit review are bound by their actual bytes."""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from kit import KIT
from practice_fixture import PIXEL, practice_record, scope, approve, capture_binding, human_receipt

spec = importlib.util.spec_from_file_location('tone_test', KIT/'matrix/base/tools/tone_contract.py')
tone = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tone)


class ToneContractTest(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve()
        self.brief=self.put('brief.md','the genre and references')
        self.scene=self.put('scene.html','<body>the rendered core scene</body>')
        self.samples=self.put('samples.md','sample catalogue')
        self.png=self.put('screen.png',PIXEL)
        self.profile=dict(schema=tone.practice.SCHEMA,version='1',scopes=[scope(tone,appearance_target='yes',direct_manipulation='yes')])
        self.put('human.md','I confirm this direction')
        self.data=dict(viewport='1280x800',capture_binding=capture_binding([self.scene],root=self.root,screenshot=self.png),version='1',genre='route game',profile='游戏与玩乐',tone='warm',core_loop='choose and move',
                       references=[dict(name=f'Ref {i}',source=f'Guide, section {i}',borrows='operate the token',observed='not observed') for i in range(2)],
                       avoid=['forms as the main scene'],
                       samples=[dict(moment=f'm{i%4}',text=f'Sample {i}',consequence='Resolve the selection') for i in range(6)],
                       parts=dict(brief=self.brief,scene=self.scene,preview=self.scene,samples=self.samples,screenshot=self.png,
                                  practice_profile=self.put('practice.json',json.dumps(self.profile))),
                       confirmation=dict(person='owner',quote='I confirm this direction',source='human.md'))
        self.fit=dict(outcome='passed',mode='independent',checker='checker',producer='maker',artifacts=[self.scene],
                      screenshot=self.png,viewport='1280x800',capture_binding=capture_binding([self.scene],root=self.root,screenshot=self.png),capture='browser',genre_fit='fits loop',
                      application_drift='none',copy_fit='fits tone')

    def put(self, name, content):
        p=self.root/name
        p.parent.mkdir(parents=True,exist_ok=True)
        data=content.encode() if isinstance(content,str) else content
        p.write_bytes(data)
        return dict(path=name,version='1',sha256=tone.sha(data))

    def contract(self):
        if self.data.get('confirmation') is not None and 'review_receipt' not in self.data['confirmation']:
            approve(self.root,tone,self.data)
        return self.put(tone.DEFAULT_PATH,'# Direction\n\n```tone-contract\n'+json.dumps(self.data)+'\n```\n')

    def stage(self):
        binding = self.contract()
        self.fit['tone_contract'] = binding
        return dict(current='D-1',next='D-2',tone_contract=binding,
                    tone_fit_review='fit.json', practice_evidence={
                        'appearance_target':{'workspace':practice_record(self.root,tone,binding,'appearance_target',[self.scene])},
                        'direction_contribution':{'workspace':practice_record(self.root,tone,binding,'direction_contribution',[self.scene])},
                        'design_fit':{'workspace':self.put('fit.json',json.dumps(self.fit))},
                    })

    def test_requires_actual_parts_and_latest_fit(self):
        state=self.stage()
        tone.check_stage(self.root,state,[self.scene])
        self.put('scene.html','different scene')
        with self.assertRaisesRegex(ValueError,'stale artifact'):
            tone.check_stage(self.root,state,[self.scene])

    def test_requires_current_contract_version_and_real_confirming_quote(self):
        state=self.stage()
        state['tone_contract']['version']='different'
        with self.assertRaisesRegex(ValueError,'version'):
            tone.check_stage(self.root,state,[self.scene])
        self.data['confirmation']['quote']='An invented confirmation'
        self.contract()
        with self.assertRaisesRegex(ValueError,'quote'):
            tone.validate(self.root,tone.DEFAULT_PATH)

    def test_game_samples_and_checker_independence(self):
        self.data['samples'] = self.data['samples'][:4]
        self.contract()
        with self.assertRaisesRegex(ValueError,'six distinct'):
            tone.validate(self.root,tone.DEFAULT_PATH)
        self.fit['checker']=self.fit['producer']
        self.put('fit.json',json.dumps(self.fit))
        with self.assertRaisesRegex(ValueError,'independent'):
            tone.check_fit(self.root,'fit.json',[self.scene])

    def test_human_viewport_review_fallback_requires_record(self):
        self.fit.update(mode='human',checker='owner',capture_unavailable='no browser in this host',
                        manual_review=self.put('human-viewport.md','Observed the rendered scene on desktop'))
        self.fit.pop('screenshot')
        self.fit['human_review_receipt']=human_receipt(self.root,tone,[self.scene],person='owner')
        self.put('fit.json',json.dumps(self.fit))
        self.assertEqual(tone.check_fit(self.root,'fit.json',[self.scene])['mode'],'human')
        self.put('human-viewport.md','')
        with self.assertRaisesRegex(ValueError,'stale artifact'):
            tone.check_fit(self.root,'fit.json',[self.scene])


    def test_p1_fit_covers_scene_and_samples_before_contract_confirmation(self):
        state=self.stage()
        state.update(current='P-1',next='P-2',response=self.put('response.json',json.dumps(
            {'source':'human.md','person_id':'owner'}))['path'])
        receipt=self.data['confirmation']['review_receipt']
        _,manifest=tone.evidence.verify_bundle(self.root,receipt)
        shown=manifest['context']['display']
        state['request']=self.put('p1-request.json',json.dumps(dict(request_id='synthetic-direction',scope=['workspace'],
            display_evidence=shown['path'],display_sha256=shown['sha256'])))['path']
        self.fit.update(artifacts=[self.scene,self.samples,self.data['parts']['practice_profile']],
                        binding_mode='pre_confirmation_direction', tone_contract=tone.direction_binding(tone.DEFAULT_PATH,self.data))
        self.fit['capture_binding']=capture_binding(self.fit['artifacts'],root=self.root,screenshot=self.png)
        self.put('fit.json',json.dumps(self.fit))
        tone.check_stage(self.root,state,[state['tone_contract']])
        self.put('response.json',json.dumps({'source':'unrelated.md','person_id':'owner'}))
        with self.assertRaisesRegex(ValueError,'P-1 response'):
            tone.check_stage(self.root,state,[state['tone_contract']])


    def test_installed_product_cli_uses_shared_validator(self):
        self.contract()
        p = KIT/'.agents/skills/matrix-product/scripts/tone_contract.py'
        result = subprocess.run([sys.executable,'-B',str(p),'--project',str(self.root)],
                                text=True,capture_output=True,check=True)
        self.assertTrue(json.loads(result.stdout)['allowed'])

    def draft_delivery(self):
        contract = self.contract()
        p = KIT/'.agents/skills/matrix-product/scripts/tone_contract.py'
        result = subprocess.run([sys.executable,'-B',str(p),'--project',str(self.root),
                                 '--contract',contract['path'],'--draft'], text=True,capture_output=True)
        return result.returncode, json.loads(result.stdout)

    def test_draft_cli_returns_validated_files_without_approval(self):
        self.data.pop('confirmation')
        code, result = self.draft_delivery()
        self.assertEqual(code, 0)
        self.assertEqual(result['delivery']['format'], 'direction-delivery/1')
        self.assertEqual(result['delivery']['status'], 'draft_pending_confirmation')
        self.assertEqual(result['delivery']['direction_reference'], result['direction_reference'])
        self.assertEqual(result['delivery']['preview'], {k:self.scene[k] for k in ('path','sha256')})
        self.assertEqual(result['delivery']['capture']['kind'], 'screenshot')
        self.assertEqual(result['delivery']['capture']['sha256'], self.png['sha256'])
        (self.root/self.scene['path']).unlink()
        code, result = self.draft_delivery()
        self.assertNotEqual(code, 0)
        self.assertFalse(result['allowed'])
        self.assertNotIn('delivery', result)

    def test_draft_without_capture_rejects_completion_until_actual_human_record(self):
        self.data['parts'].pop('screenshot')
        self.data['capture_unavailable'] = 'Browser capture unavailable'
        code, result = self.draft_delivery()
        self.assertNotEqual(code, 0)
        self.assertNotIn('delivery', result)
        self.data['parts']['manual_review'] = self.put('viewport.md','Reviewer saw the current selection in the preview')
        self.data['human_review_receipt'] = human_receipt(self.root,tone,[self.scene],person='owner')
        code, result = self.draft_delivery()
        self.assertEqual(code, 0)
        self.assertEqual(result['delivery']['capture']['kind'], 'human')
        self.assertEqual(result['delivery']['capture']['limitation'], 'Browser capture unavailable')

    def test_draft_rejects_fake_capture_with_image_signature(self):
        self.data['parts']['screenshot'] = self.put('fake.png', PIXEL[:8] + b'Screenshot pending')
        code, result = self.draft_delivery()
        self.assertNotEqual(code, 0)
        self.assertIn('actual rendered screenshot', result['error'])
        self.assertNotIn('delivery', result)

    def test_draft_rejects_unfinished_preview_sources_and_sample_consequences(self):
        preview = self.put('placeholder.html','Preview will be made later')
        self.data['parts']['preview'] = preview
        code, result = self.draft_delivery()
        self.assertNotEqual(code, 0)
        self.assertIn('preview', result['error'])
        self.data['parts']['preview'] = self.scene
        source = self.data['references'][0].pop('source')
        self.assertIn('source', self.draft_delivery()[1]['error'])
        self.data['references'][0]['source'] = source
        self.data['samples'][0].pop('consequence')
        self.assertIn('consequence', self.draft_delivery()[1]['error'])
