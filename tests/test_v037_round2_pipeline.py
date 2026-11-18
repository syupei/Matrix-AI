"""Round2 real business input and actual PM transaction chains; models/people are SIMULATED."""
import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from kit import KIT
from public_review_fixture import stage_receipt
from test_pm_instances import Fixture, pm
from practice_fixture import put, review_state


class PipelineRound2(Fixture,unittest.TestCase):
    def setUp(self):
        super().setUp();self.staff();self.gate=pm.admission.load_gate()

    def admit(self,key='IN-1',path='external/brief.md',body='SIM actual business brief: offline single-player race',family='client',**extra):
        put(self.root,path,body)
        self.call('intake_register',id=key,path=path,version=key,source='SIM full original request',source_id=family,profession='product',**extra)
        self.call('intake_submit',id=key,master='product-001')
        peers=[r['id'] for r in self.inputs().values() if r['state']=='admitted' and r['source_id']!=family]
        self.call('intake_review','product-001',id=key,outcome='approved',conclusion='SIM actual source read back',resolved_risks=[],resolved_conflicts=[],open_items=[],human_required=False,coexists_with=peers,conflicts_with=[])
        self.call('intake_admit',id=key)
        return path

    def inputs(self):
        with pm.connect(self.root,readonly=True) as db:return pm.integrity.records(db,'input_admission')

    def stage(self,paths,prefix='source-confirm'):
        existing=self.root/(prefix+'.json')
        if existing.is_file():return prefix+'.json'
        state=review_state(self.root,self.gate,paths,prefix=prefix)
        reply=json.loads((self.root/state['response']).read_text());quote='SIM complete displayed review '+prefix
        put(self.root,reply['source'],quote);reply.update(quote=quote,message_sha256=self.gate.tone.evidence.digest(quote));put(self.root,state['response'],reply)
        request=json.loads((self.root/state['request']).read_text())
        self.call('human_attention',id=prefix,kind='confirmation',display=request['display_evidence'],scope=state['scope'],inputs=paths)
        self.call('human_attention',id=prefix,response=reply['source'])
        receipt=stage_receipt(self,state,prefix,'SIM-owner')
        reply['review_receipt']=receipt;put(self.root,state['response'],reply)
        return put(self.root,prefix+'.json',state)['path']

    def business(self,tid='B',**fields):
        if 'IN-1' not in self.inputs():self.admit()
        data=dict(project_level=False,inputs=['external/brief.md'],admitted_inputs=['IN-1'],stage_transition=self.stage(['external/brief.md']),owner='code-engineering-002',executor='code-engineering-002',checker='quality-engineering-001',outputs=['src/'],practice_stage=dict(role='engineering',current='E-1.2',scope=['race']))
        data.update(fields);return self.create(tid,**data)

    def finish(self,tid,files):
        self.mutate('transition',tid,state='running',reason='SIM start',execution_receipt='SIM actual process')
        for name,body in files.items():put(self.root,name,body)
        self.mutate('transition',tid,state='waiting_review',reason='SIM handover',stop_evidence='SIM process yielded',evidence=list(files))
        task=self.t(tid);self.mutate('review',tid,task['checker'],outcome='passed',criteria_checked=task['criteria'],evidence=['SIM independent note'])
        return self.mutate('transition',tid,'PM',state='done',reason='SIM adopted')

    def upstream(self):
        self.business('U');self.finish('U',{'src/game.js':'SIM skeleton v1'})

    def downstream(self,tid='D',**fields):
        data=dict(project_level=False,inputs=['src/game.js'],dependencies=['U'],owner='code-engineering-002',executor='code-engineering-002',checker='quality-engineering-001',outputs=['src/'],practice_stage=dict(role='engineering',current='E-1.2',scope=['race']))
        data.update(fields);return self.create(tid,**data)

    def test_same_profession_evolution_closes_from_trusted_start_snapshot(self):
        self.upstream();self.downstream();self.finish('D',{'src/game.js':'SIM skeleton plus first increment'})
        self.assertEqual('done',self.t('D')['state']);self.assertIn('input_provenance',self.t('D'))
        with self.assertRaisesRegex(ValueError,'admitted input|bind inputs'):
            self.downstream('unrelated',outputs=['other/out.md'])
            self.mutate('transition','unrelated',state='running',reason='start',execution_receipt='SIM')

    def test_directory_input_is_preserved_and_rework_keeps_snapshot(self):
        self.upstream();self.downstream(inputs=['src/'])
        self.mutate('transition','D',state='running',reason='start',execution_receipt='SIM')
        self.assertEqual(['src/'],self.t('D')['inputs']);before=self.t('D')['input_provenance']
        put(self.root,'src/game.js','SIM attempt1')
        self.mutate('transition','D',state='waiting_review',reason='handover',stop_evidence='SIM',evidence=['src/game.js'])
        task=self.t('D');self.mutate('review','D',task['checker'],outcome='failed',cause='execution',criteria_checked=task['criteria'],evidence=['SIM fail'])
        self.mutate('transition','D',state='running',reason='rework',execution_receipt='SIM',rework_reason='execution',note='fix implementation')
        self.assertEqual(before,self.t('D')['input_provenance'])

    def test_read_only_upstream_input_cannot_be_mutated(self):
        self.upstream();self.downstream(outputs=['other/out.md'])
        self.mutate('transition','D',state='running',reason='start',execution_receipt='SIM')
        put(self.root,'src/game.js','SIM unrelated mutation')
        put(self.root,'other/out.md','SIM own output')
        self.mutate('transition','D',state='waiting_review',reason='handover',stop_evidence='SIM',evidence=['other/out.md'])
        self.assertTrue(any('read-only dispatched input changed' in row['action'] for row in self.t('D')['integrity_issues']))

    def test_worker_cannot_delegate_with_or_without_private_input(self):
        self.business()
        for inputs in (['matrix/base/MATRIX.md'],['inbox/private.md']):
            put(self.root,'inbox/private.md','SIM unadmitted multiplayer request')
            with self.assertRaisesRegex(ValueError,'delegation requires'):
                self.create('child',parent='B',actor='code-engineering-002',owner='code-engineering-003',executor='code-engineering-003',checker='code-engineering-002',inputs=inputs)

    def test_pm_child_inherits_business_and_checks_independent_registered_actors(self):
        self.business();self.create('child',parent='B',actor='PM',owner='code-engineering-003',executor='code-engineering-003',checker='quality-engineering-001',inputs=['matrix/base/MATRIX.md'],outputs=['src/child.md'],practice_stage=dict(role='engineering',current='E-1.2',scope=['race']))
        child=self.t('child');self.assertEqual(['IN-1'],child['admitted_inputs']);self.assertIn('external/brief.md',child['inputs']);self.assertEqual('PM',child['manager'])
        with self.assertRaisesRegex(ValueError,'register the actual'):
            self.create('unknown',parent='B',actor='PM',owner='unregistered',executor='unregistered',checker='quality-engineering-001')
        with self.assertRaisesRegex(ValueError,'independent'):
            self.create('self-check',parent='B',actor='PM',owner='code-engineering-003',executor='code-engineering-003',checker='code-engineering-003',practice_stage=dict(role='engineering',current='E-1.2',scope=['race']))

    def test_pm_cannot_semantically_rewrite_from_unadmitted_private_message(self):
        self.business()
        with self.assertRaisesRegex(ValueError,'source basis'):
            self.mutate('update','B','PM',changes={'goal':'SIM private multiplayer'},reason='customer DM')
        path=self.admit('IN-2','external/change.md','SIM approved clarified scope',family='change',new_family_reason='New isolated source, coexists with brief')
        self.mutate('update','B','PM',changes={'goal':'SIM approved clarified scope','inputs':['external/brief.md',path],'admitted_inputs':['IN-1','IN-2'],'stage_transition':self.stage(['external/brief.md',path],prefix='revised-scope')},reason='approved current sources',admission_basis=['IN-2'])
        self.assertEqual('SIM approved clarified scope',self.t('B')['goal'])

    def test_rules_only_are_not_a_business_source_but_coordination_is_explicit(self):
        with self.assertRaisesRegex(ValueError,'business source'):
            self.create('fake',business_source=False,project_level=False,owner='code-engineering-002',executor='code-engineering-002',inputs=['matrix/base/MATRIX.md'])
        self.create('coord',owner='PM',executor=None,checker='PM',kind='coordination',inputs=['matrix/base/MATRIX.md'],outputs=['management/coord.md'],practice_stage=None)
        self.assertEqual('coordination',self.t('coord')['kind'])

    def test_source_family_requires_reason_and_master_relationships(self):
        self.admit();put(self.root,'external/v2.md','SIM newer contradictory scope')
        with self.assertRaisesRegex(ValueError,'new_family_reason'):
            self.call('intake_register',id='NEW',source_id='renamed',path='external/v2.md',version='2',source='SIM',profession='product')
        self.call('intake_register',id='NEW',source_id='renamed',path='external/v2.md',version='2',source='SIM',profession='product',new_family_reason='May replace prior scope')
        self.call('intake_submit',id='NEW',master='product-001')
        fields=dict(id='NEW',outcome='approved',conclusion='SIM replaces old scope',resolved_risks=[],resolved_conflicts=[],open_items=[],human_required=False)
        with self.assertRaisesRegex(ValueError,'classify current'):
            self.call('intake_review','product-001',**fields)
        self.call('intake_review','product-001',**fields,coexists_with=[],conflicts_with=['IN-1']);self.call('intake_admit',id='NEW')
        self.assertEqual('superseded',self.inputs()['IN-1']['state'])

    def test_feedback_is_actionable_and_resolvable_without_mutating_scope(self):
        self.business();old=self.t('B')['revision'];rec=self.call('production_feedback','code-engineering-002',task_id='B',instruction='SIM customer asked multiplayer')['feedback']
        result=self.call('continue');self.assertTrue(any(r['kind']=='production_feedback' for r in result['actions']))
        self.assertTrue(self.call('tasks_for',**{'as':'PM'})['production_feedback'])
        with self.assertRaisesRegex(ValueError,'PM disposes'):
            self.call('resolve_production_feedback','code-engineering-002',id=rec['id'],disposition='rejected',reason='self disposition')
        self.call('resolve_production_feedback',id=rec['id'],disposition='rejected',reason='Outside approved scope; actual user decision needed')
        self.assertEqual(old,self.t('B')['revision']);self.assertFalse(any(r['kind']=='production_feedback' for r in self.call('continue')['actions']))

    def test_cross_profession_product_p3_cannot_start_engineering(self):
        self.business('P',owner='product-001',executor='product-001',outputs=['product/specs/'],practice_stage=dict(role='product',current='P-3',scope=['rules']))
        self.finish('P',{'product/specs/rules.md':'SIM unconfirmed P3 rules'})
        self.downstream('E',inputs=['product/specs/rules.md'],dependencies=['P'])
        with self.assertRaisesRegex(ValueError,'confirmation|confirm the product|consumed'):
            self.mutate('transition','E',state='running',reason='SIM premature start',execution_receipt='SIM')
        confirmed=self.stage(['product/specs/rules.md'],prefix='actual-product-complete')
        self.downstream('E2',inputs=['product/specs/rules.md'],dependencies=['P'],stage_transition=confirmed)
        self.mutate('transition','E2',state='running',reason='SIM confirmed product',execution_receipt='SIM')
        self.assertEqual('running',self.t('E2')['state'])

    def test_directory_reads_combine_real_upstream_handoffs_without_requiring_external_intake(self):
        self.business('U');self.finish('U',{'src/a.js':'SIM a1','src/b.js':'SIM b1'})
        self.downstream('D',inputs=['src/a.js']);self.finish('D',{'src/a.js':'SIM a2'})
        self.downstream('E',inputs=['src/'],dependencies=['U','D'],outputs=['other/'])
        self.mutate('transition','E',state='running',reason='SIM consume exact composed directory',execution_receipt='SIM')
        self.assertIn('input_provenance',self.t('E'))

    def test_start_snapshot_is_immutable_even_when_live_output_may_evolve(self):
        self.upstream();self.downstream();self.mutate('transition','D',state='running',reason='SIM start',execution_receipt='SIM')
        receipt=self.t('D')['input_provenance']['bundle'];view,_=self.gate.tone.evidence.verify_bundle(self.root,receipt)
        (view/'src/game.js').write_text('SIM altered historical evidence')
        self.assertTrue(any('stale artifact' in issue['action'] for issue in self.t('D')['integrity_issues']))

    def test_disposition_to_intake_preserves_complete_feedback_and_is_not_admission(self):
        self.business();instruction='SIM complete customer message: multiplayer is only a question, not approved.'
        feedback=self.call('production_feedback','code-engineering-002',task_id='B',instruction=instruction)['feedback']
        put(self.root,'inbox/feedback.md',instruction)
        self.call('intake_register',id='FB-IN',source_id='feedback',path='inbox/feedback.md',version='1',source='SIM exact production feedback',profession='product',new_family_reason='Pending question may coexist')
        self.call('resolve_production_feedback',id=feedback['id'],disposition='intake',target_id='FB-IN',reason='Master must review this full question')
        self.assertEqual('registered',self.inputs()['FB-IN']['state']);self.assertEqual(['IN-1'],self.t('B')['admitted_inputs'])

    def test_creator_cannot_become_checker_after_task_creation(self):
        self.business()
        with self.assertRaisesRegex(ValueError,'registered active|independent'):
            self.mutate('update','B','PM',changes={'checker':'PM'},reason='SIM invalid PM self check')

    def test_start_outbox_cannot_create_child_but_can_report_without_changing_instruction(self):
        self.business();api=__import__('importlib.util',fromlist=['x']);spec=api.spec_from_file_location('round2_real_platform',KIT/'matrix/orchestration/tools/platform_api.py');facade=api.module_from_spec(spec);spec.loader.exec_module(facade)
        config=dict(schema=facade.SPEC,project_id='SIMULATED',principals={'controller':dict(active=True,actor='PM',operations=sorted(facade.OPERATIONS),task_ops=[])},runners={'default':dict(version='SIM',models={'SIM-small':'SIM-small','SIM-big':'SIM-big'},capabilities={k:dict(state='supported',evidence='SIM controller test only') for k in ('launch','write_isolation','model_selection')})})
        put(self.root,facade.CONFIG,config)
        def invoke(op,**params):
            self.n+=1;return facade.handle(self.root,dict(protocol=facade.SPEC,project_id='SIMULATED',request_id='API-'+str(self.n),event_id='API-'+str(self.n),op=op,params=params),'controller')
        self.assertTrue(invoke('runtime.configure',mode='external',expected_generation=0)['ok'])
        plan=invoke('actions.plan')['result'];start=next(row for row in plan['actions'] if row['kind']=='start')
        claim=invoke('actions.claim',action_id=start['action_id'],expected_revision=plan['revision']);self.assertTrue(claim['ok'],claim);run=claim['result']['record']
        result=invoke('runs.event',run_id=run['id'],expected_revision=run['revision'],kind='commands',commands=[dict(op='create',task=dict(id='private-child',parent='B'))])
        self.assertFalse(result['ok']);self.assertEqual('UNAUTHORIZED',result['error']['code'])
        task=self.t('B');original=task['next_action']
        result=invoke('runs.event',run_id=run['id'],expected_revision=run['revision'],kind='commands',commands=[dict(op='report',task_id='B',expected_revision=task['revision'],summary='SIM genuine progress',next_action='SIM suggested private change',impact='No scope change',delivery='prepared')])
        self.assertTrue(result['ok'],result);self.assertEqual(original,self.t('B')['next_action']);self.assertNotIn('private-child',[row['id'] for row in self.call('status')['tasks']])

    def test_source_family_admission_rechecks_families_added_after_master_review(self):
        put(self.root,'external/a.md','SIM first source');put(self.root,'external/b.md','SIM independent second source')
        for key in ['A','B']:
            self.call('intake_register',id=key,source_id=key,path='external/'+key.lower()+'.md',version='1',source='SIM source',profession='product',new_family_reason='SIM separate bounded source')
            self.call('intake_submit',id=key,master='product-001')
            self.call('intake_review','product-001',id=key,outcome='approved',conclusion='SIM scope reviewed before concurrent admission',resolved_risks=[],resolved_conflicts=[],open_items=[],human_required=False)
        self.call('intake_admit',id='A')
        with self.assertRaisesRegex(ValueError,'families changed'):
            self.call('intake_admit',id='B')
        self.call('intake_review','product-001',id='B',outcome='approved',conclusion='SIM reviewed current coexistence',resolved_risks=[],resolved_conflicts=[],open_items=[],human_required=False,coexists_with=['A'],conflicts_with=[])
        self.call('intake_admit',id='B');self.assertEqual('admitted',self.inputs()['B']['state'])

    def test_change_plan_cannot_promote_private_message_without_master_and_admission(self):
        self.business();self.create('IA',kind='coordination',owner='PM',executor=None,checker='PM',outputs=['management/impact.md'])
        put(self.root,'inbox/private.md','SIM full original private multiplayer change')
        self.call('record_change','code-engineering-002',id='PRIVATE',affected_tasks=['B'],analysis_task='IA',participants=['code-engineering-002','code-engineering-001'],type='modify',quote='SIM full original private multiplayer change',source='inbox/private.md',title='SIM proposed change')
        def change():
            with pm.connect(self.root,readonly=True) as db:return pm.integrity.records(db,'change')['PRIVATE']
        command=dict(op='update',actor='code-engineering-002',task_id='B',expected_revision=self.t('B')['revision'],changes={'goal':'SIM multiplayer private instruction'},reason='SIM private source')
        self.call('assess_change','code-engineering-002',id='PRIVATE',expected_revision=change()['revision'],assessment=dict(decision='impacted',reason='SIM request received',dispositions=[dict(action='update',task_id='B')],commands=[command]))
        self.call('assess_change','code-engineering-001',id='PRIVATE',expected_revision=change()['revision'],assessment=dict(decision='no_impact',reason='SIM master reviewed this proposal; no separate master task mutation',dispositions=[],commands=[]))
        before=self.t('B')['goal']
        with self.assertRaisesRegex(ValueError,'admitted source basis'):
            self.call('apply_change_plan',id='PRIVATE',expected_revision=change()['revision'])
        self.assertEqual(before,self.t('B')['goal'])

    def test_professional_stage_cannot_skip_practice_by_changing_kind(self):
        self.business('STAGE',kind='stage',practice_stage=None,slots=0)
        with self.assertRaisesRegex(ValueError,'professional practice stage'):
            self.mutate('transition','STAGE',state='running',reason='SIM try kind exemption',execution_receipt='SIM')

    def test_intake_master_can_delegate_only_the_same_pending_review_input(self):
        put(self.root,'external/pending.md','SIM pending original brief')
        self.call('intake_register',id='PENDING',source_id='pending',path='external/pending.md',version='1',source='SIM pending source',profession='product')
        self.call('intake_submit',id='PENDING',master='product-001')
        self.create('INPUT-REVIEW',owner='product-001',executor='product-001',inputs=['external/pending.md'],intake_review_id='PENDING',outputs=['management/intake-reviews/master.md'])
        self.create('INPUT-CHILD',parent='INPUT-REVIEW',actor='product-001',owner='code-engineering-002',executor='code-engineering-002',checker='quality-engineering-001',inputs=['external/pending.md'],outputs=['management/intake-reviews/technical.md'])
        self.assertEqual('PENDING',self.t('INPUT-CHILD')['intake_review_id'])
        self.mutate('transition','INPUT-CHILD',state='running',reason='SIM actual delegated source review',execution_receipt='SIM process')
        with self.assertRaisesRegex(ValueError,'same pending|exact routed'):
            self.create('WRONG-INPUT',parent='INPUT-REVIEW',actor='product-001',owner='code-engineering-003',executor='code-engineering-003',checker='quality-engineering-001',inputs=['external/pending.md'],intake_review_id='OTHER',outputs=['management/intake-reviews/other.md'])

    def test_pure_pm_stage_is_coordination_but_business_outputs_and_practice_are_not(self):
        self.create('PM-MILESTONE',business_source=False,kind='stage',owner='PM',executor=None,checker='PM',inputs=['matrix/base/MATRIX.md'],outputs=['management/checkpoint.md'],practice_stage=None,slots=0)
        self.mutate('transition','PM-MILESTONE','PM',state='running',reason='SIM actual coordination begins',execution_receipt='SIM child planning')
        self.assertEqual('running',self.t('PM-MILESTONE')['state'])
        with self.assertRaisesRegex(ValueError,'business source'):
            self.create('FAKE-BUSINESS',business_source=False,kind='stage',owner='PM',executor=None,checker='PM',inputs=['matrix/base/MATRIX.md'],outputs=['product/brief.md'],practice_stage=None)
        with self.assertRaisesRegex(ValueError,'business source'):
            self.create('FAKE-P1',business_source=False,kind='stage',owner='PM',executor=None,checker='PM',inputs=['matrix/base/MATRIX.md'],outputs=['management/p1.md'],practice_stage=dict(role='product',current='P-1',scope=['test']))

    def test_pure_coordination_semantics_keep_manager_and_stop_boundaries(self):
        self.create('CONTROL',business_source=False,kind='stage',owner='PM',executor=None,checker='PM',inputs=['matrix/base/MATRIX.md'],outputs=['management/control.md'],practice_stage=None,profession='product')
        self.mutate('update','CONTROL','PM',changes={'goal':'SIM update the coordination agenda'},reason='SIM PM scheduling decision')
        self.assertEqual('SIM update the coordination agenda',self.t('CONTROL')['goal'])
        with self.assertRaisesRegex(ValueError,'task state belongs to its owner'):
            self.mutate('update','CONTROL','code-engineering-001',changes={'goal':'SIM worker instruction'},reason='SIM unappointed change')
        with self.assertRaisesRegex(ValueError,'source basis|management records'):
            self.mutate('update','CONTROL','PM',changes={'outputs':['src/hidden.js']},reason='SIM cannot turn coordination into business')
        self.mutate('transition','CONTROL','PM',state='running',reason='SIM real coordination started',execution_receipt='SIM local meeting')
        with self.assertRaisesRegex(ValueError,'stop admitted production'):
            self.mutate('update','CONTROL','PM',changes={'title':'SIM silently change active work'},reason='SIM must stop first')
