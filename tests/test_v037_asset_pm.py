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
        controller.direction_rows=[scope(tone,'board',asset_family='yes'),scope(tone,'admin')]
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
        put(self.root,'design/questions.md','SIM please provide missing gray-box states')
        for kind in ('clarification','correction'):
            self.call('human_attention',id=kind,task_id='D4',kind=kind,scope=['board'],
                      display='design/questions.md')
        quote='SIM here are the missing state descriptions'
        put(self.root,'design/input-answer.md',quote)
        self.call('human_attention',id='clarification',response='design/input-answer.md')
        with self.assertRaisesRegex(ValueError,'confirmation request'):
            self.mutate('human_review','D4','PM',outcome='approved',person='SIM-owner',
                        attention_id='clarification',presented_ref='design/questions.md',
                        source='design/input-answer.md',quote=quote,scope=['board'])
        with self.assertRaisesRegex(ValueError,'before anchor review'):
            self.call('human_attention',id='missing',task_id='D4',kind='confirmation',scope=['board'],
                      display='design/review.html',stage_state=path,review_purpose='asset_anchors')
        result=tone.asset_comparison_receipt(self.root,record['path'])
        state['asset_comparison_receipts']={'board':result['asset_comparison_receipt']};put(self.root,path,state)
        state['practice_scope']=['admin'];put(self.root,path,state)
        with self.assertRaisesRegex(ValueError,'practice_scope must match'):
            self.call('human_attention',id='wrong-scope',task_id='D4',kind='confirmation',scope=['board'],
                      display='design/review.html',stage_state=path,review_purpose='asset_anchors')
        state.pop('practice_scope');put(self.root,path,state)
        put(self.root,'design/wrong-review.html','SIM other page')
        with self.assertRaisesRegex(ValueError,'must show the page'):
            self.call('human_attention',id='wrong',task_id='D4',kind='confirmation',scope=['board'],
                      display='design/wrong-review.html',stage_state=path,review_purpose='stage_review')
        self.call('human_attention',id='correct',task_id='D4',kind='confirmation',scope=['board'],
                  display='design/review.html',stage_state=path,review_purpose='stage_review')
        self.assertEqual({'clarification','correction','correct'},
                         {row['id'] for row in self.call('human_attention_status')['items'] if row.get('task_id')=='D4'})

