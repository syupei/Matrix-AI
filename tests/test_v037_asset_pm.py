"""Public PM refuses review B until the current comparison page is checked."""
import unittest
from test_pm_instances import Fixture,pm
import test_v037_direction_recovery as recovery
import test_v037_rereview_stage as materials
from practice_fixture import scope,put


class AssetPM(Fixture,unittest.TestCase):
    def test_review_b_is_blocked_before_receipt_and_for_a_different_page(self):
        controller=recovery.DirectionRecovery();controller.setUp();self.addCleanup(controller.doCleanups)
        tone=pm.admission.load_gate().tone
        controller.direction_rows=[scope(tone,'board',asset_family='yes')]
        brief,assigned=controller.setup_direction()
        rec=controller.call('direction_sample',id='DIR',brief=brief,admitted_inputs=['BRIEF'],profile='SIM assets',
                            person='SIM-owner',combined_review_authorization='SIM one P1 review',assigned=assigned)['direction_sample']
        controller.complete_direction(rec,assigned)
        self.root=controller.root;self.n=controller.n+100
        contract=dict(tone.evidence.ref(self.root,tone.DEFAULT_PATH),version='1')
        fixture=materials.StageRegressions();fixture.root=self.root;fixture.data=controller.data;fixture.contract=contract;fixture.serial=0
        record=fixture.asset_comparison()
        entry=dict(role='design',current='D-4',scope=['board'],tone_contract=contract)
        state=dict(entry,practice_evidence={'asset_anchors':{'board':record}})
        self.create('D4',project_level=False,owner='experience-design-001',executor='experience-design-001',
                    checker='quality-engineering-003',inputs=[tone.DEFAULT_PATH],admitted_inputs=[],dependencies=['DIR'],
                    practice_stage=entry,outputs=['design/current-scene.html','design/review.html'])
        path='design/d4-review-state.json';put(self.root,path,state)
        with self.assertRaisesRegex(ValueError,'before review B'):
            self.call('human_attention',id='missing',task_id='D4',kind='confirmation',scope=['board'],
                      display='design/review.html',stage_state=path)
        result=tone.asset_comparison_receipt(self.root,record['path'])
        state['asset_comparison_receipts']={'board':result['asset_comparison_receipt']};put(self.root,path,state)
        put(self.root,'design/wrong-review.html','SIM other page')
        with self.assertRaisesRegex(ValueError,'must show the page'):
            self.call('human_attention',id='wrong',task_id='D4',kind='confirmation',scope=['board'],
                      display='design/wrong-review.html',stage_state=path)
        self.call('human_attention',id='correct',task_id='D4',kind='confirmation',scope=['board'],
                  display='design/review.html',stage_state=path)
        self.assertEqual(['correct'],[row['id'] for row in self.call('human_attention_status')['items'] if row.get('task_id')=='D4'])

