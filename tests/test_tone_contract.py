"""Direction artifacts, confirmation and fit review are bound by their actual bytes."""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from kit import KIT

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
        self.png=self.put('screen.png',b'\x89PNG\r\n\x1a\n' + b'SYNTHETIC format segment')
        self.put('human.md','I confirm this direction')
        self.data=dict(version='1',genre='route game',profile='游戏与玩乐',tone='warm',core_loop='choose and move',
                       references=[dict(name=f'Ref {i}',borrows='operate the token',observed='not observed') for i in range(2)],
                       avoid=['forms as the main scene'],
                       samples=[dict(moment=f'm{i%4}',text=f'Sample {i}') for i in range(6)],
                       parts=dict(brief=self.brief,scene=self.scene,samples=self.samples,screenshot=self.png),
                       confirmation=dict(person='owner',quote='I confirm this direction',source='human.md'))
        self.fit=dict(outcome='passed',mode='independent',checker='checker',producer='maker',artifacts=[self.scene],
                      screenshot=self.png,viewport='1280x800',capture='browser',genre_fit='fits loop',
                      application_drift='none',copy_fit='fits tone')

    def put(self, name, content):
        p=self.root/name
        p.parent.mkdir(parents=True,exist_ok=True)
        data=content.encode() if isinstance(content,str) else content
        p.write_bytes(data)
        return dict(path=name,version='1',sha256=tone.sha(data))

    def contract(self):
        return self.put(tone.DEFAULT_PATH,'# Direction\n\n```tone-contract\n'+json.dumps(self.data)+'\n```\n')

    def stage(self):
        return dict(current='D-1',next='D-2',tone_contract=self.contract(),
                    tone_fit_review=self.put('fit.json',json.dumps(self.fit))['path'])

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
        with self.assertRaisesRegex(ValueError,'quote missing'):
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
        self.put('fit.json',json.dumps(self.fit))
        self.assertEqual(tone.check_fit(self.root,'fit.json',[self.scene])['mode'],'human')
        self.put('human-viewport.md','')
        with self.assertRaisesRegex(ValueError,'stale artifact'):
            tone.check_fit(self.root,'fit.json',[self.scene])


    def test_p1_fit_covers_scene_and_samples_before_contract_confirmation(self):
        state=self.stage()
        state.update(current='P-1',next='P-2',response=self.put('response.json',json.dumps(
            {'source':'human.md','person_id':'owner'}))['path'])
        self.fit['artifacts']=[self.scene,self.samples]
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
