"""Synthetic tests for intake, task boundaries and the direction milestone."""

import json
import unittest

from test_pm_instances import Fixture, pm


class ProductionTest(Fixture, unittest.TestCase):
    def add_file(self, name, value):
        p = self.root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(value if isinstance(value, str) else json.dumps(value, ensure_ascii=False), encoding='utf-8')
        return name

    def stage(self, path, confirmed=True):
        gate = pm.admission.load_gate()
        d = gate.digests(self.root, [path])
        review = dict(request_id='R', stage='P-7', role='product', artifact_sha256=d['artifact_sha256'],
                      scope=['release'], display_evidence=self.add_file('display.md','Presented approved product scope'))
        response = dict(request_id='R', artifact_sha256=d['artifact_sha256'], scope=['release'],
                        actor='person' if confirmed else 'assistant', choice='confirm',
                        source=self.add_file('approval.md','Confirmed'))
        return self.add_file('stage.json',dict(role='product',current='P-7',next='complete',scope=['release'],blockers=[],
                   artifacts=d['artifacts'],request=self.add_file('request.json',review), response=self.add_file('response.json',response),
                   conversation_check=self.add_file('conversation.md','P-7 → complete')))

    def test_external_input_gates_create_and_start(self):
        self.staff()
        path=self.add_file('external/prd.md','Synthetic PRD')
        with self.assertRaisesRegex(ValueError,'admitted input'):
            self.create('A', inputs=[path], outputs=['engineering/output.md'])
        self.call('intake_register',id='PRD-1',path=path,version='1',source='external sample',profession='product')
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
        self.call('intake_admit',id='PRD-1',person='SIM-owner',quote='Confirmed')
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
        self.call('intake_register',id='PRD-1',path=path,version='1',source='external sample',profession='product')
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
        self.create('legacy',owner='legacy-worker')
        with self.assertRaisesRegex(ValueError,'production_feedback'):
            self.mutate('update','legacy',changes={'inputs':['new instruction']},
                        reason='direct instruction',scope_authorization='unverified user message')
        r=self.call('production_feedback','legacy-worker',task_id='legacy',instruction='Please change input')
        self.assertEqual(r['feedback']['recipient'],'PM')
        self.assertEqual(self.t('legacy')['inputs'],['SIM v1'])

    def test_direction_chain_and_human_attention(self):
        roles=[('product','T7',True),('experience-design','T7',True),
               ('content-design','T6',True),('quality-engineering','T7',False)]
        self.staff({'entries':[dict(id=role,profession=role,level=level,model='SIM-big',count=1,master=lead)
                               for role,level,lead in roles]})
        path=self.add_file('project-brief.md','Synthetic direction brief')
        result=self.call('direction_sample',id='direction',brief=path,profile='游戏与玩乐',
            combined_review_authorization='Owner requested one P-1 review',person='SIM-owner',
            assigned={'product':'product-001','experience-design':'experience-design-001',
                      'content-design':'content-design-001','fit_checker':'quality-engineering-001','task_checker':'PM'})
        self.assertEqual(result['direction_sample']['reserved_roles'],['art-production'])
        self.assertEqual(self.t('direction-scene')['dependencies'],['direction-brief'])
        self.assertEqual(self.t('direction-samples')['dependencies'],['direction-brief'])
        self.assertEqual(self.t('direction')['dependencies'],['direction-fit'])
        self.assertEqual([t['id'] for t in pm.execute(self.root, {'op':'status'})['tasks'] if t['human_required']],['direction'])
        self.call('human_attention',id='A1',kind='confirmation',display=path)
        self.call('human_attention',id='A1',response=self.add_file('response.md','Confirmed'))
        status=pm.execute(self.root,{'op':'human_attention_status'})
        self.assertEqual(status['answered'],1)
        self.assertEqual(status['characters'],len('Synthetic direction brief'))
