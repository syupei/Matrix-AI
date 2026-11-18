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
        self.state=dict(role='design',current='D-4',scope=['board'],tone_contract=self.f.contract,artifacts=self.data['artifacts'],
                        practice_evidence={'asset_anchors':{'board':self.record}})

    def cli(self,*args):
        run=subprocess.run([sys.executable,'-B',str(BASE/'tone_contract.py'),'--project',str(self.root),*args],capture_output=True,text=True)
        self.assertEqual(0,run.returncode,run.stdout+run.stderr)
        return json.loads(run.stdout)

    def test_missing_gray_model_does_not_block_comparison_but_receipt_is_required(self):
        with self.assertRaisesRegex(ValueError,'before anchor review'):
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
        self.assertEqual(1,page.count('<img '))
        self.assertEqual(1,page.count('<iframe '))
        for feature in self.data['comparison']['confirmed_features']:self.assertIn(feature,page)
        self.assertNotIn('{{',page)
        self.assertNotIn('asset_comparison_receipt',result)

    def test_generated_placeholders_and_html_in_an_image_slot_are_rejected(self):
        result=self.cli('--asset-page',self.record['path'],'--page-output','design/pending-review.html')
        data=copy.deepcopy(self.data)
        data['comparison']['review_page']=result['review_page']
        data['artifacts'].append(result['review_page'])
        for row in data['comparison']['rows']:
            row['anchor']=data['comparison']['scene_sample']
            row['reference']=self.f.data['parts']['screenshot']
        record=self.f.put('pending-assets.json',data)
        with self.assertRaisesRegex(ValueError,'review page.*placeholder'):
            tone.check_record(self.root,'asset_anchors','board',record,self.f.contract)
        page=self.f.put('design/broken-image.html','<img src="direction.png"><img src="current-scene.html">')
        data['comparison']['review_page']=page;data['artifacts'].append(page)
        record=self.f.put('broken-assets.json',data)
        with self.assertRaisesRegex(ValueError,'image element.*image file'):
            tone.check_record(self.root,'asset_anchors','board',record,self.f.contract)

    def test_table_header_cannot_replace_each_features_actual_status(self):
        data=copy.deepcopy(self.data)
        row=data['comparison']['rows'][0];feature=row['feature']
        source=(self.root/data['comparison']['review_page']['path']).read_text()
        for status in ('','close','unmet'):
            page=self.f.put('design/table-review.html',source+'<table><thead><tr><th>achieved close unmet</th></tr></thead><tbody><tr><td>'+feature+'</td><td>SIM direction</td><td>SIM anchor</td><td>'+status+'</td><td>SIM difference</td></tr></tbody></table>')
            changed=copy.deepcopy(data);changed['comparison']['review_page']=page
            record=self.f.put('table-record.json',changed)
            with self.subTest(status=status):
                run=subprocess.run([sys.executable,'-B',str(BASE/'tone_contract.py'),'--project',str(self.root),
                                    '--asset-comparison',record['path']],capture_output=True,text=True)
                self.assertNotEqual(0,run.returncode,run.stdout)
                self.assertIn('status differs',json.loads(run.stdout)['error'])

    def test_inline_markup_preserves_feature_text_in_comparison_row(self):
        data=copy.deepcopy(self.data);row=data['comparison']['rows'][0]
        feature=row['feature'];left,right=feature.split(' ',1)
        source=(self.root/data['comparison']['review_page']['path']).read_text()
        page=self.f.put('design/markup-review.html',source+'<table><tr><td>'+left+' <b>'+right+'</b></td><td>SIM direction</td><td>SIM anchor</td><td>achieved</td><td>SIM difference</td></tr></table>')
        data['comparison']['review_page']=page
        record=self.f.put('markup-record.json',data)
        self.assertTrue(self.cli('--asset-comparison',record['path'])['allowed'])

    def test_copied_direction_image_cannot_be_an_anchor(self):
        changed=copy.deepcopy(self.data)
        changed['anchors'][0]=self.f.data['parts']['screenshot']
        record=self.f.put('copied.json',changed)
        with self.assertRaisesRegex(ValueError,'cannot copy'):
            tone.check_record(self.root,'asset_anchors','board',record,self.f.contract)

    def test_unmet_receipt_can_be_shown_but_not_released(self):
        data=copy.deepcopy(self.data)
        data['comparison']['rows'][0]['status']='unmet'
        page=self.f.put('design/unmet-review.html',(self.root/'design/review.html').read_text().replace('achieved','unmet'))
        data['comparison']['review_page']=page;data['artifacts'].append(page)
        record=self.f.put('unmet.json',data)
        self.assertFalse(self.cli('--asset-comparison',record['path'])['release_ready'])

    def test_png_sample_binds_its_sources_without_hashing_itself(self):
        data=copy.deepcopy(self.data)
        sources=[r for r in data['artifacts'] if r['path'] not in {data['comparison']['review_page']['path'],data['comparison']['scene_sample']['path']}]
        picture,binding=self.f.capture(sources,'design/new-scene.png')
        page=self.f.put('design/png-review.html','Visible layered object contour: achieved<img src="direction.png"><img src="new-scene.png"><img src="anchor-0.svg">')
        data['artifacts']=[*sources,picture,page]
        data['comparison'].update(scene_sample=picture,capture_binding=binding,viewport='1280x800',review_page=page)
        data['comparison']['rows'][0]['reference']=self.f.data['parts']['screenshot']
        ref=self.f.put('png-record.json',data)
        self.assertTrue(self.cli('--asset-comparison',ref['path'])['allowed'])

