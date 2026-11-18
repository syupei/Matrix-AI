"""D-4 pre-review receipt and page generation, without a human approval or model."""
import copy
import json
import subprocess
import sys
import unittest
import test_v037_rereview_stage as fixture
from test_v037_rereview_stage import tone, BASE


class AssetSubmission(unittest.TestCase):
    def setUp(self):
        self.f=fixture.StageRegressions()
        self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.root=self.f.root
        self.f.contract,self.f.data=self.f.direction([self.f.row(asset_family='yes')])
        self.record=self.f.asset_comparison()
        self.data=json.loads((self.root/self.record['path']).read_text())
        self.state=dict(role='design',current='D-4',scope=['board'],tone_contract=self.f.contract,
                        practice_evidence={'asset_anchors':{'board':self.record}})

    def cli(self,*args):
        run=subprocess.run([sys.executable,'-B',str(BASE/'tone_contract.py'),'--project',str(self.root),*args],capture_output=True,text=True)
        self.assertEqual(0,run.returncode,run.stdout+run.stderr)
        return json.loads(run.stdout)

    def test_missing_gray_model_does_not_block_comparison_but_receipt_is_required(self):
        with self.assertRaisesRegex(ValueError,'before review B'):
            tone.check_asset_submission(self.root,self.state)
        result=self.cli('--asset-comparison',self.record['path'])
        self.state['asset_comparison_receipts']={'board':result['asset_comparison_receipt']}
        tone.check_asset_submission(self.root,self.state,result['review_page']['path'])
        with self.assertRaisesRegex(ValueError,'must show the page'):
            tone.check_asset_submission(self.root,self.state,'other.html')
        changed=copy.deepcopy(self.data);changed['comparison']['rows'][0]['difference']='Observed smaller border'
        self.state['practice_evidence']['asset_anchors']['board']=self.f.put(self.record['path'],changed)
        with self.assertRaisesRegex(ValueError,'stale'):
            tone.check_asset_submission(self.root,self.state,result['review_page']['path'])

    def test_template_prefills_features_without_claiming_comparison_complete(self):
        result=self.cli('--asset-page',self.record['path'],'--page-output','design/new-review.html')
        self.assertEqual('draft_only',result['status'])
        page=(self.root/result['review_page']['path']).read_text()
        self.assertEqual(2,page.count('<img '))
        for feature in self.data['comparison']['confirmed_features']:self.assertIn(feature,page)
        self.assertNotIn('{{',page)
        self.assertNotIn('asset_comparison_receipt',result)

    def test_copied_direction_image_cannot_be_an_anchor(self):
        changed=copy.deepcopy(self.data)
        changed['anchors'][0]=self.f.data['parts']['screenshot']
        record=self.f.put('copied.json',changed)
        with self.assertRaisesRegex(ValueError,'cannot copy'):
            tone.check_record(self.root,'asset_anchors','board',record,self.f.contract)

    def test_png_sample_binds_its_sources_without_hashing_itself(self):
        data=copy.deepcopy(self.data)
        sources=[r for r in data['artifacts'] if r['path'] not in {data['comparison']['review_page']['path'],data['comparison']['scene_sample']['path']}]
        picture,binding=self.f.capture(sources,'design/new-scene.png')
        page=self.f.put('design/png-review.html','<img src="direction.png"><img src="new-scene.png"><img src="anchor-0.svg">')
        data['artifacts']=[*sources,picture,page]
        data['comparison'].update(scene_sample=picture,capture_binding=binding,viewport='1280x800',review_page=page)
        data['comparison']['rows'][0]['reference']=self.f.data['parts']['screenshot']
        ref=self.f.put('png-record.json',data)
        self.assertTrue(self.cli('--asset-comparison',ref['path'])['allowed'])

