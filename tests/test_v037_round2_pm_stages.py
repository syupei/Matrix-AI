"""Actual PM transactions over the common stage gate; synthetic work and human text only."""
import copy
import json
import unittest
from test_pm_instances import Fixture, TEAM, pm
import test_v037_review_repairs as repairs
from practice_fixture import put


class PMStageRound2(Fixture,unittest.TestCase):
    def setUp(self):
        controller=repairs.DirectionBindings('test_real_display_reply_and_milestone_close_are_all_required')
        config=copy.deepcopy(TEAM)
        config['entries'].append(dict(id='D-T7',profession='experience-design',level='T7',model='SIM-big',count=1,master=True))
        controller.staff=lambda config_ignored=None:Fixture.staff(controller,config)
        controller.setUp();self.addCleanup(controller.doCleanups)
        controller.show_and_answer();controller.approve_direction();controller.close('Direction')
        self.root=controller.root;self.n=controller.n+1000;self._business_fixture=controller._business_fixture
        self.gate=pm.admission.load_gate();self.tone=self.gate.tone;self.serial=0
        self.contract=dict(self.tone.evidence.ref(self.root,self.tone.DEFAULT_PATH),version=controller.data['version'])

    def completion(self,entry,paths,**fields):
        self.serial+=1;prefix='pm-stage/SIM-'+str(self.serial)
        state=dict(entry,next=self.gate.STAGES[entry['role']][self.gate.STAGES[entry['role']].index(entry['current'])+1],blockers=[],artifacts=[self.tone.evidence.ref(self.root,p) for p in paths],**fields)
        state['conversation_check']=put(self.root,prefix+'-conversation.md',state['current']+' → '+state['next'])['path']
        if state['current'] in self.gate.REVIEW[state['role']]:
            digest=self.gate.artifact_digest(self.root,state['artifacts']);quote='SIM complete stage approval '+prefix
            shown=put(self.root,prefix+'-shown.md','SIM actually displayed the current complete artifacts')
            reply=put(self.root,prefix+'-reply.md',quote)
            request=dict(request_id='R-'+str(self.serial),role=state['role'],stage=state['current'],scope=state['scope'],artifact_sha256=digest,display_evidence=shown['path'],display_sha256=shown['sha256'])
            response=dict(request_id=request['request_id'],scope=state['scope'],artifact_sha256=digest,actor='user',choice='confirm',source=reply['path'],quote=quote,display_sha256=shown['sha256'],message_sha256=self.tone.evidence.digest(quote))
            self.call('human_attention',id=request['request_id'],kind='confirmation',display=shown['path'],scope=state['scope'],inputs=paths)
            self.call('human_attention',id=request['request_id'],response=reply['path'])
            with pm.connect(self.root) as db:response['review_receipt']=pm.direction.bind_attention(pm.api(),self.root,db,request['request_id'],person='SIM-owner',quote=quote,scope=state['scope'],expected={})
            state.update(request=put(self.root,prefix+'-request.json',request)['path'],response=put(self.root,prefix+'-response.json',response)['path'])
        path=put(self.root,prefix+'-state.json',state)['path'];return path,state

    def close_work(self,tid,paths):
        self.mutate('transition',tid,state='running',reason='SIM actual start',execution_receipt='SIM actual process')
        self.mutate('transition',tid,state='waiting_review',reason='SIM actual handover',stop_evidence='SIM returned',evidence=paths)
        # Real registered independent checker, with its actual check run and file.
        task=self.t(tid);rid='check-'+tid
        self.call('launch_start',id=rid,purpose='check',task_id=tid,instance=task['checker'],model='SIM-big',session='SIM-'+rid,command=['SIM-check'])
        self.call('launch_started',id=rid,pid=4242)
        review=put(self.root,'management/reviews/'+tid+'.md','SIM actual criteria inspected')
        self.mutate('review',tid,task['checker'],run=rid,outcome='passed',criteria_checked=task['criteria'],evidence=[review['path']])
        self.call('launch_exit','launcher',id=rid,exit_code=0)
        self.close(tid)

    def solution(self,tid='SOL'):
        artifact=put(self.root,'engineering/confirmed-plan-'+tid+'.md','SIM actual solution')
        entry=dict(role='solution',current='E-2.4',scope=['workspace'],tone_contract=self.contract)
        path,state=self.completion(entry,[artifact['path']])
        self.create(tid,practice_stage=entry,practice_completion=path,outputs=[artifact['path'],path])
        self.close_work(tid,[artifact['path'],path]);return self.t(tid)['practice_receipt']

    def build_entry(self,current='E-3.2'):
        up=self.solution()
        return dict(role='build',current=current,scope=['workspace'],tone_contract=self.contract,upstream=up['state_path'],upstream_bundle=up['bundle'])

    def test_design_d6_closes_with_real_human_receipt_and_d7_can_start(self):
        artifact=put(self.root,'design/final-spec.md','SIM design-only specification')
        entry=dict(role='design',current='D-6',scope=['workspace'],tone_contract=self.contract)
        handoff=put(self.root,'design/handoff.json',dict(delivery_kind='design_only',basis='This task hands over design specifications only',artifacts=[artifact]))
        path,state=self.completion(entry,[artifact['path']],implementation_handoff=handoff)
        self.create('D6',owner='experience-design-001',executor='experience-design-001',practice_stage=entry,practice_completion=path,outputs=[artifact['path'],handoff['path'],path])
        self.close_work('D6',[artifact['path'],handoff['path'],path])
        self.assertFalse(self.t('D6')['needs_recheck']);self.assertEqual('done',self.t('D6')['state'])
        self.create('D7',owner='experience-design-001',executor='experience-design-001',practice_stage=dict(entry,current='D-7'),outputs=['design/maintenance.md'])
        self.mutate('transition','D7',state='running',reason='SIM real maintenance',execution_receipt='SIM process')
        self.assertEqual('running',self.t('D7')['state'])

    def test_independent_review_child_keeps_sources_and_its_own_stage(self):
        entry=self.build_entry();self.create('BUILD',practice_stage=entry,outputs=['src/'])
        self.create('REVIEW',parent='BUILD',actor='PM',owner='quality-engineering-001',executor='quality-engineering-001',checker='quality-engineering-002',review_for='BUILD',practice_stage=dict(role='quality',current='Q-1',scope=['workspace']),outputs=['design/independent-review.json'])
        review=self.t('REVIEW');self.assertEqual('Q-1',review['practice_stage']['current'])
        self.assertEqual(self.t('BUILD')['admitted_inputs'],review['admitted_inputs'])
        with self.assertRaisesRegex(ValueError,'separate inspection'):
            self.create('FAKE-REVIEW',parent='BUILD',actor='PM',owner='quality-engineering-001',executor='quality-engineering-001',checker='quality-engineering-002',review_for='BUILD',outputs=['src/fake.md'],practice_stage=dict(role='quality',current='Q-1',scope=['workspace']))
        with self.assertRaisesRegex(ValueError,'parent producers'):
            self.create('SELF-REVIEW',parent='BUILD',actor='PM',review_for='BUILD',outputs=['design/check.json'])

    def test_first_actual_increment_cannot_close_without_receipt_or_start_later_sibling(self):
        entry=self.build_entry();self.create('BUILD',practice_stage=entry,outputs=['src/'])
        self.create('ONE',parent='BUILD',actor='PM',owner='code-engineering-002',executor='code-engineering-002',checker='quality-engineering-001',outputs=['src/one.js','pm-stage/one.json'])
        self.create('TWO',parent='BUILD',actor='PM',owner='code-engineering-003',executor='code-engineering-003',checker='quality-engineering-001',outputs=['src/two.js'])
        self.mutate('transition','ONE',state='running',reason='SIM first actual implementation',execution_receipt='SIM process')
        with self.assertRaisesRegex(ValueError,'first actual increment'):
            self.mutate('transition','TWO',state='running',reason='SIM premature second',execution_receipt='SIM process')
        put(self.root,'src/one.js','const first=1')
        self.mutate('transition','ONE',state='waiting_review',reason='SIM incomplete first handover',stop_evidence='SIM returned',evidence=['src/one.js'])
        self.check('ONE')
        with self.assertRaisesRegex(ValueError,'completion record'):
            self.close('ONE')
        path,state=self.completion(entry,['src/one.js']);self.mutate('update','ONE','PM',changes={'outputs':['src/one.js',path],'practice_completion':path},admission_basis=self.t('ONE')['admitted_inputs'],reason='SIM bind existing actual first increment record')
        self.mutate('update','ONE',changes={'evidence':['src/one.js',path]},reason='SIM complete handover')
        self.check('ONE');self.close('ONE')
        self.assertTrue(self.t('ONE')['practice_receipt']['increment_review'])
        self.mutate('transition','TWO',state='running',reason='SIM subsequent implementation after receipt',execution_receipt='SIM process')
        self.assertEqual('running',self.t('TWO')['state'])

    def test_completion_cannot_replace_selected_upstream_with_another_valid_receipt(self):
        entry=self.build_entry(current='E-3.1');other=self.solution('SOL-OTHER')
        artifact=put(self.root,'engineering/workplan.md','SIM scoped work plan')
        path,state=self.completion(entry,[artifact['path']])
        state.update(upstream=other['state_path'],upstream_bundle=other['bundle']);put(self.root,path,state)
        self.create('PLAN',practice_stage=entry,practice_completion=path,outputs=[artifact['path'],path])
        with self.assertRaisesRegex(ValueError,'dispatched upstream'):
            self.close_work('PLAN',[artifact['path'],path])

    def test_closed_stage_replays_after_real_checker_retirement(self):
        receipt=self.solution();config=json.loads((self.root/'management/instance-config.json').read_text())
        config['entries']=[entry for entry in config['entries'] if entry['id']!='Q-T7']
        self.write('instance-config.json',config);self.confirm()
        self.call('retire_instance',id='quality-engineering-001',expected_revision=self.instance('quality-engineering-001')['revision'],reason='SIM person approved removal after all actual work closed')
        self.assertFalse(self.instance('quality-engineering-001')['active'])
        self.assertFalse(self.t('SOL')['needs_recheck'])
        view,_=self.tone.evidence.verify_bundle(self.root,receipt['bundle']);state=json.loads((view/receipt['state_path']).read_text())
        self.assertTrue(self.gate.check(view,state,registry_root=self.root,seal=False)['allowed'])
