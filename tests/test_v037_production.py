"""Synthetic tests for intake, task boundaries and the direction milestone."""

import json
import unittest

from test_pm_instances import Fixture, pm, confirmed_stage
from practice_fixture import direction, practice_record, put, scope, review_state, pm_closed_fixture


class ProductionTest(Fixture, unittest.TestCase):
    def add_file(self, name, value):
        p = self.root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(value if isinstance(value, str) else json.dumps(value, ensure_ascii=False), encoding='utf-8')
        return name

    def stage(self, path, confirmed=True):
        path=confirmed_stage(self,[path],prefix='review-'+('valid' if confirmed else 'invalid')+'-'+str(self.n))
        if not confirmed:
            state=json.loads((self.root/path).read_text());reply=json.loads((self.root/state['response']).read_text());reply['actor']='assistant'
            self.add_file(state['response'],reply)
        return path

    def test_external_input_gates_create_and_start(self):
        self.staff()
        path=self.add_file('external/prd.md','Synthetic PRD')
        with self.assertRaisesRegex(ValueError,'admitted business source'):
            self.create('A', inputs=[path], outputs=['engineering/output.md'])
        self.call('intake_register',id='PRD-1',source_id='PRD-family',path=path,version='1',source='external sample',profession='product')
        self.call('intake_submit',id='PRD-1',master='product-001')
        with self.assertRaisesRegex(ValueError,'master records'):
            self.call('intake_review',id='PRD-1')
        self.create('Review-PRD', owner='product-001', inputs=[path], intake_review_id='PRD-1',
                    outputs=['management/intake-reviews/prd.md'])
        self.call('intake_review','product-001',id='PRD-1',outcome='changes_requested',conclusion='Need clarification',
                  resolved_risks=[],resolved_conflicts=[],open_items=['Scope still in conflict'],human_required=True)
        with self.assertRaisesRegex(ValueError,'master approval'):
            self.call('intake_admit',id='PRD-1',person='SIM-owner',quote='Confirmed')
        self.call('intake_review','product-001',id='PRD-1',outcome='approved',conclusion='Ready',resolved_risks=[],resolved_conflicts=[],open_items=[],human_required=True)
        with self.assertRaisesRegex(ValueError,'confirmation'):
            self.call('intake_admit',id='PRD-1')
        self.call('human_attention',id='intake-display',kind='confirmation',intake_id='PRD-1',scope='PRD-1',display=self.add_file('input-display.md','Displayed current input'))
        self.call('human_attention',id='intake-display',response=self.add_file('input-reply.md','Confirmed'))
        self.call('intake_admit',id='PRD-1',person='SIM-owner',quote='Confirmed',attention_id='intake-display',scope='PRD-1')
        with self.assertRaisesRegex(ValueError,'human confirmation'):
            self.create('A',inputs=[path],admitted_inputs=['PRD-1'],stage_transition=self.stage(path,False),outputs=['engineering/output.md'])
        self.create('A',inputs=[path],admitted_inputs=['PRD-1'],stage_transition=self.stage(path),outputs=['engineering/output.md'])
        old=self.t('A')['revision']
        result=self.call('production_feedback','code-engineering-001',task_id='A',instruction='Change the agreed requirement')
        self.assertEqual(result['feedback']['recipient'],'PM')
        self.assertEqual(old,self.t('A')['revision'])
        with self.assertRaisesRegex(ValueError,'return to the PM'):
            self.mutate('update','A', changes={'goal':'New requirement'},reason='A request',scope_authorization='claimed')
        self.add_file(path,'Changed bytes')
        with self.assertRaisesRegex(ValueError,'changed input'):
            self.mutate('transition','A',state='running',reason='start',execution_receipt='receipt')
        self.assertFalse(self.t('A')['ready'])

    def test_successful_admitted_start_and_scoped_submission(self):
        self.staff()
        path=self.add_file('external/prd.md','Synthetic PRD')
        self.call('intake_register',id='PRD-1',source_id='PRD-family',path=path,version='1',source='external sample',profession='product')
        self.call('intake_submit',id='PRD-1',master='product-001')
        self.call('intake_review','product-001',id='PRD-1',outcome='approved',conclusion='Ready',resolved_risks=[],resolved_conflicts=[],open_items=[],human_required=False)
        self.call('intake_admit',id='PRD-1')
        self.create('A',inputs=[path],admitted_inputs=['PRD-1'],stage_transition=self.stage(path),outputs=['engineering/output.md'])
        self.mutate('transition','A',state='running',reason='start',execution_receipt='receipt')
        with self.assertRaisesRegex(ValueError,'outside admitted'):
            self.mutate('transition','A',state='waiting_review',reason='handover',stop_evidence='yielded',evidence=[path])
        output=self.add_file('engineering/output.md','produced within the task')
        self.mutate('transition','A',state='waiting_review',reason='handover',stop_evidence='yielded',evidence=[output])

    def test_direct_work_instruction_on_existing_untyped_task(self):
        with self.assertRaisesRegex(ValueError,'register the actual'):
            self.create('unknown',owner='legacy-worker')
        self.staff();self.create('legacy',owner='code-engineering-002',project_level=False)
        with self.assertRaisesRegex(ValueError,'production_feedback'):
            self.mutate('update','legacy',changes={'inputs':['new instruction']},
                        reason='direct instruction',scope_authorization='unverified user message')
        r=self.call('production_feedback','code-engineering-002',task_id='legacy',instruction='Please change input')
        self.assertEqual(r['feedback']['recipient'],'PM')
        self.assertIn('external/SIM-business-source.md',self.t('legacy')['inputs'])

    def test_direction_chain_and_human_attention(self):
        assignments=[('product','product','T7',True),('design','experience-design','T7',True),
                     ('content','content-design','T6',True),('code','code-engineering','T7',True),
                     ('qa','quality-engineering','T6',True),('fit','quality-engineering','T6',False),('checks','quality-engineering','T6',False)]
        self.staff({'entries':[dict(id=key,profession=role,level=level,model='SIM-big',count=1,master=lead)
                               for key,role,level,lead in assignments]})
        basis=self.admitted_business_fixture();path='external/SIM-business-source.md'
        result=self.call('direction_sample',id='direction',brief=path,admitted_inputs=basis['admitted_inputs'],profile='业务管理与查询',
            combined_review_authorization='Owner requested one P-1 review',person='SIM-owner',
            assigned={'product':'product-001','experience-design':'experience-design-001',
                      'content-design':'content-design-001','code-engineering':'code-engineering-001',
                      'quality-engineering':'quality-engineering-001',
                      'fit_checker':'quality-engineering-002','task_checker':'quality-engineering-003'})
        self.assertEqual(result['direction_sample']['reserved_roles'],['art-production'])
        self.assertEqual(self.t('direction-scene')['dependencies'],['direction-brief'])
        self.assertIn('design/preview.html',self.t('direction-scene')['outputs'])
        self.assertIn('design/preview.html',self.t('direction-compose')['inputs'])
        self.assertEqual(self.t('direction-samples')['dependencies'],['direction-brief'])
        self.assertEqual(self.t('direction')['dependencies'],['direction-fit'])
        self.assertEqual([t['id'] for t in pm.execute(self.root, {'op':'status'})['tasks'] if t['human_required']],['direction'])
        self.call('human_attention',id='A1',kind='confirmation',display=path)
        self.call('human_attention',id='A1',response=self.add_file('response.md','Confirmed'))
        status=pm.execute(self.root,{'op':'human_attention_status'})
        self.assertEqual(status['answered'],2)
        self.assertEqual(status['characters'],sum(item['characters'] for item in status['items']))
        self.assertEqual(next(item['characters'] for item in status['items'] if item['id']=='A1'),len((self.root/path).read_text()))

    def test_dispatch_checks_only_prerequisites_and_close_checks_current_phase(self):
        from test_v037_review_repairs import DirectionBindings
        controller=DirectionBindings('test_real_display_reply_and_milestone_close_are_all_required');controller.direction_rows=[scope(pm.admission.load_gate().tone,appearance_target='yes')];controller.setUp();self.addCleanup(controller.doCleanups)
        controller.show_and_answer();controller.approve_direction();controller.close('Direction')
        self.root=controller.root;self.n=controller.n+1000;self._business_fixture=controller._business_fixture
        tone=controller.tone;data=controller.data;contract=dict(tone.evidence.ref(self.root,tone.DEFAULT_PATH),version=data['version'])
        entry = dict(role='solution',current='E-2.2',scope=['workspace'],tone_contract=contract)
        self.create('TRY',practice_stage=entry,practice_completion='gate.json',outputs=['gate.json','result.md'])
        self.mutate('transition','TRY',state='running',reason='start',execution_receipt='receipt')
        result = put(self.root,'result.md','Synthetic rendering comparison')
        choice = practice_record(self.root,tone,contract,'rendering_choice',[result])
        put(self.root,'conversation.md','E-2.2 → E-2.3')
        put(self.root,'gate.json',dict(entry,next='E-2.3',blockers=[],artifacts=[result],conversation_check='conversation.md',
            practice_evidence={'rendering_choice':{'workspace':choice}}))
        self.mutate('transition','TRY',state='waiting_review',reason='handover',stop_evidence='yielded',evidence=['gate.json','result.md'])
        self.check('TRY')
        with self.assertRaisesRegex(ValueError,'appearance_proof'):
            self.close('TRY')
        invalid = dict(entry,current='E-2.3')
        self.create('SKIP-PROOF',practice_stage=invalid)
        with self.assertRaisesRegex(ValueError,'rendering_choice'):
            self.mutate('transition','SKIP-PROOF',state='running',reason='start',execution_receipt='receipt')

    def test_child_or_dispatch_owner_cannot_omit_phase_even_with_no_contract(self):
        self.call('register_instance',id='legacy-code',instance={'role':'code-engineering','endpoint':'SIM-legacy'})
        self.staff()
        self.create('COORDINATE',owner='PM',executor=None,checker='PM',kind='coordination',outputs=['management/coord.md'])
        self.create('OMIT',parent='COORDINATE',project_level=False,practice_stage=None)
        self.create('OMIT-PM',owner='PM',executor='code-engineering-001',project_level=False,practice_stage=None)
        for tid in ('OMIT','OMIT-PM'):
            with self.subTest(task=tid), self.assertRaisesRegex(ValueError, 'professional practice stage'):
                self.mutate('transition',tid,state='running',reason='start',execution_receipt='receipt')
        with self.assertRaisesRegex(ValueError,'match the assigned and executing professions'):
            self.create('WRONG-ROLE',owner='legacy-code',
                        practice_stage={'role':'product','current':'P-3','scope':['workspace']})
