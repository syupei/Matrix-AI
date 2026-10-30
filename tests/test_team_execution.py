"""Mechanism tests only. All appointments, people and receipts are SIMULATED."""
import importlib.util
import json
import tempfile
import subprocess
import sys
import time
import unittest
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

ROOT = Path(__file__).resolve().parents[1]/'src'
def load(name, path):
    s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
pm=load('team_pm_test',ROOT/'.agents/skills/project-management-agent/scripts/pm_tasks.py')
gw=load('team_gateway_test',ROOT/'collaboration/tools/tool_gateway.py')
gate=load('team_gate_test',ROOT/'collaboration/tools/stage_gate.py')
bridge=load('team_dispatch_test',ROOT/'collaboration/tools/task_dispatch.py')

class ProjectFixture:
    def setUp(self):
        t=tempfile.TemporaryDirectory();self.addCleanup(t.cleanup);self.root=Path(t.name);self.n=0
        self.call('init','PM',config=dict(project='SIMULATED',pm_actor='PM',authorization='SIMULATED',frontdoor_thread='SIM',max_slots=4))
        (self.root/'authority.md').write_text('SIMULATED designation: lead manages A; workers W and X allocated.')
        (self.root/'input.md').write_text('SIMULATED baseline')
        for iid,role in [('L','product-agent'),('W','product-agent'),('X','product-agent'),('M','project-management-agent'),('S','security-specialist')]:
            self.call('register_instance','PM',id=iid,instance=dict(role=role,endpoint='SIM-'+iid,write_roots=['.agent-runtime/instances/'+iid+'/workspace']))
        self.create('A',owner='L',slots=0);self.create('B',owner='X')
        self.app('L','lead',['A'],['W'])
        self.app('W','executor',['A'])
    def call(self,op,actor='L',**kw):
        self.n+=1;return pm.execute(self.root,dict(op=op,actor=actor,event_id='S-'+str(self.n),**kw))
    def app(self,iid,mode,roots,delegates=None):
        role=next(x for x in pm.execute(self.root,{'op':'status'})['integrity']['instance'].values() if x['id']==iid)['role']
        return self.call('appoint','PM',id=iid,appointment=dict(mode=mode,role=role,root_tasks=roots,delegates=delegates or [],source='authority.md'))
    def create(self,tid,parent=None,actor='PM',**kw):
        d=dict(id=tid,parent=parent,title=tid,owner='W',checker='CHECKER',goal='SIM task',inputs=['input.md'],outputs=['candidate'],criteria=['consistent'],next_action='produce',executor=kw.get('owner','W'))
        d.update(kw);return self.call('create',actor,task=d)
    def t(self,tid):return next(t for t in pm.execute(self.root,{'op':'status'})['tasks'] if t['id']==tid)
    def mutate(self,op,tid,actor=None,**kw):
        t=self.t(tid);return self.call(op,actor or t['owner'],task_id=tid,expected_revision=t['revision'],**kw)
    def complete(self,tid):
        self.mutate('update',tid,changes={'evidence':['SIM actual artifact']},reason='SIM completion')
        self.mutate('review',tid,'CHECKER',outcome='passed',criteria_checked=['consistent'],evidence=['SIM independently checked'])
        return self.mutate('transition',tid,self.t(tid)['manager'],state='done',reason='SIM checked')

class Appointments(ProjectFixture, unittest.TestCase):
    def test_lead_assigns_only_allocated_workers(self):
        self.create('A-1','A','L')
        self.assertEqual('L',self.t('A-1')['manager'])
        with self.assertRaisesRegex(pm.TaskError,'allocated'):self.create('A-2','A','L',owner='X')
    def test_worker_cannot_redelegate_or_edit_other_scope(self):
        self.create('A-1','A','L')
        with self.assertRaisesRegex(pm.TaskError,'cannot delegate'):self.create('DEEP','A-1','W')
        with self.assertRaisesRegex(pm.TaskError,'outside task scope'):self.create('B-1','B','L')
    def test_lead_cannot_become_project_pm(self):
        with self.assertRaisesRegex(pm.TaskError,'workflow PM'):self.create('A-P','A','L',project_level=True)
    def test_workflow_pm_scoped_project_tasks(self):
        self.app('M','workflow_pm',['A'],['W'])
        self.create('A-P','A','M',project_level=True)
        self.assertEqual('M',self.t('A-P')['manager'])
        with self.assertRaisesRegex(pm.TaskError,'outside task scope'):self.create('B-P','B','M',project_level=True)
    def test_revocation_blocks_work_but_allows_yield(self):
        self.create('A-1','A','L')
        self.mutate('transition','A-1',state='running',reason='SIM',execution_receipt='SIM started')
        self.call('revoke_appointment','PM',id='W',expected_revision=1,reason='SIM withdrawn')
        with self.assertRaisesRegex(pm.TaskError,'inactive'):self.mutate('update','A-1',changes={'next_action':'continue'},reason='SIM')
        self.mutate('transition','A-1',state='blocked',reason='SIM stopped',stop_evidence='SIM process stopped')
    def test_authority_edits_invalidate_appointment(self):
        self.create('A-1','A','L');(self.root/'authority.md').write_text('SIM changed authority')
        with self.assertRaisesRegex(pm.TaskError,'stale'):self.mutate('transition','A-1',state='running',reason='SIM',execution_receipt='SIM')
        self.assertFalse(next(a for a in pm.execute(self.root,{'op':'team'})['appointments'] if a['id']=='W')['current'])
    def test_assignment_to_unallocated_executor_rejected(self):
        self.create('A-1','A','L')
        with self.assertRaisesRegex(pm.TaskError,'allocated'):self.mutate('update','A-1',changes={'executor':'X'},reason='SIM')
    def test_required_specialist_review_blocks_closure_and_deduplicates(self):
        self.create('A-1','A','L')
        self.call('register_participation','PM',id='SEC',rule=dict(role='security-specialist',trigger='requirement',root_tasks=['A'],mode='required_review',source='authority.md'))
        fields=dict(rule_id='SEC',rule_revision=1,trigger='requirement',trigger_id='INPUT1',affected_tasks=['A-1'],source='input.md')
        self.call('participation_event','PM',id='OB1',**fields)
        out=self.call('participation_event','PM',id='OB2',**fields);self.assertTrue(out['duplicate'])
        with self.assertRaisesRegex(pm.TaskError,'specialist_review_pending'):self.complete('A-1')
        self.create('REVIEW',owner='S',role='security-specialist');self.app('S','executor',['REVIEW'])
        self.call('bind_participation','PM',id='OB1',expected_revision=1,review_task='REVIEW')
        self.complete('REVIEW')
        self.call('bind_participation','PM',id='OB1',expected_revision=2,review_task='REVIEW')
        self.complete('A-1')
    def test_review_wait_cycle_rejected(self):
        self.create('A-1','A','L')
        self.call('register_participation','PM',id='SEC',rule=dict(role='security-specialist',trigger='requirement',root_tasks=['A'],mode='required_review',source='authority.md'))
        self.call('participation_event','PM',id='OB1',rule_id='SEC',rule_revision=1,trigger='requirement',trigger_id='I1',affected_tasks=['A-1'],source='input.md')
        self.create('REVIEW',owner='S',role='security-specialist',dependencies=['A-1'])
        with self.assertRaisesRegex(pm.TaskError,'wait cycle'):self.call('bind_participation','PM',id='OB1',expected_revision=1,review_task='REVIEW')
    def test_new_specialist_obligation_blocks_downstream_start(self):
        self.create('A-1','A','L');self.complete('A-1')
        self.create('DOWN',owner='X',dependencies=['A-1'])
        self.call('register_participation','PM',id='SEC',rule=dict(role='security-specialist',trigger='requirement',root_tasks=['A'],mode='required_review',source='authority.md'))
        self.call('participation_event','PM',id='OB1',rule_id='SEC',rule_revision=1,trigger='requirement',trigger_id='I1',affected_tasks=['A-1'],source='input.md')
        self.assertFalse(self.t('DOWN')['ready'])
        with self.assertRaisesRegex(pm.TaskError,'specialist_review_pending'):
            self.mutate('transition','DOWN',state='running',reason='SIM',execution_receipt='SIM started')
    def test_new_baseline_replaces_old_specialist_obligation_with_history(self):
        self.create('A-1','A','L')
        self.call('register_participation','PM',id='SEC',rule=dict(role='security-specialist',trigger='requirement',root_tasks=['A'],mode='required_review',source='authority.md'))
        fields=dict(rule_id='SEC',rule_revision=1,trigger='requirement',affected_tasks=['A-1'],source='input.md')
        self.call('participation_event','PM',id='OB1',trigger_id='I1',**fields)
        (self.root/'input.md').write_text('SIM revised baseline')
        self.call('participation_event','PM',id='OB2',trigger_id='I2',supersedes='OB1',supersedes_revision=1,**fields)
        obs=pm.execute(self.root,{'op':'team'})['obligations']
        self.assertEqual('OB2',obs['OB1']['superseded_by'])
        self.assertEqual(2,len(obs))
    def test_team_owner_cannot_certify_own_delivery(self):
        self.create('A-1','A','L',checker='W')
        self.mutate('update','A-1',changes={'evidence':['SIM candidate']},reason='SIM')
        with self.assertRaisesRegex(pm.TaskError,'independent checker'):
            self.mutate('review','A-1','W',outcome='passed',criteria_checked=['consistent'],evidence=['SIM self-check'])
    def test_query_and_audit_show_revoked_appointment(self):
        self.create('A-1','A','L')
        self.call('revoke_appointment','PM',id='W',expected_revision=1,reason='SIM')
        q=pm.execute(self.root,{'op':'query','level':'children','parent':'A'})
        self.assertIn('appointment_required',[x['code'] for x in q['tasks'][0]['integrity_issues']])
        a=pm.execute(self.root,{'op':'audit','task_ids':['A-1']})
        self.assertIn('appointment_required',[x['code'] for x in a['issues']])
    def test_render_cannot_silently_discard_mutation(self):
        self.create('A-1','A','L');task=self.t('A-1')
        command=dict(op='update',actor='W',event_id='CLI',task_id='A-1',expected_revision=task['revision'],changes={'next_action':'updated'},reason='SIM')
        cli=[sys.executable,str(ROOT/'.agents/skills/project-management-agent/scripts/pm_tasks.py'),'--project',str(self.root)]
        rejected=subprocess.run(cli+['--render'],input=json.dumps(command),text=True,capture_output=True)
        self.assertNotEqual(0,rejected.returncode);self.assertIn('render does not execute',rejected.stdout)
        self.assertEqual(task['revision'],self.t('A-1')['revision'])
        updated=subprocess.run(cli,input=json.dumps(command),text=True,capture_output=True)
        self.assertEqual(0,updated.returncode,updated.stdout)
        rendered=subprocess.run(cli+['--render'],input='',text=True,capture_output=True)
        self.assertEqual(0,rendered.returncode,rendered.stdout)
        self.assertEqual('updated',self.t('A-1')['next_action'])
    def test_single_listed_person_does_not_get_all_decisions(self):
        (self.root/'collaboration').mkdir(exist_ok=True)
        (self.root/'collaboration/people.json').write_text(json.dumps({'people':[{'id':'product-human','name':'Product','decides':['product']}]}))
        self.create('H',owner='X',human_required=True)
        with self.assertRaisesRegex(pm.TaskError,'no decision authority'):
            self.mutate('human_review','H','PM',person='product-human',outcome='approved',presented_ref='SIM',source='SIM',quote='SIM',scope='SIM')

class ToolIsolation(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory();self.addCleanup(t.cleanup);self.root=Path(t.name);self.active=True
        self.adapter=gw.FileArtifactAdapter(self.root/'protected',{'file-a':'a.md','file-b':'b.md'})
        self.grants={'GA':dict(instance='D2',tasks=['T2'],connection='design-A',operations=['read','write'],resources=['file-a'],expires_at=time.time()+1000,max_calls=10,revision=1),
                     'GB':dict(instance='D3',tasks=['T3'],connection='design-A',operations=['read'],resources=['file-b'],expires_at=time.time()+1000,max_calls=10,revision=1)}
        self.gateway=gw.Gateway(self.root/'host/db.sqlite3',self.grants,{'design-A':self.adapter},lambda s:self.active)
        self.token=self.gateway.open_run('D2','T2','R2','baseline', ['GA'],time.time()+100)
    def call(self,cid='C1',**kw):
        d=dict(grant_id='GA',operation='write',resource='file-a',parameters={'content':'candidate'});d.update(kw)
        return self.gateway.call(self.token,cid,**d)
    def test_allowed_write_and_idempotent_result(self):
        first=self.call();self.assertEqual('candidate',(self.root/'protected/a.md').read_text())
        self.assertEqual(first,self.call())
        with self.assertRaisesRegex(gw.Denied,'different request'):self.call(parameters={'content':'changed'})
    def test_cross_instance_tool_and_file_denied_before_side_effect(self):
        with self.assertRaisesRegex(gw.Denied,'not assigned'):self.call(grant_id='GB')
        with self.assertRaisesRegex(gw.Denied,'outside grant'):self.call(resource='file-b')
        self.assertFalse((self.root/'protected').exists())
    def test_read_only_cannot_write(self):
        token=self.gateway.open_run('D3','T3','R3','baseline',['GB'],time.time()+100)
        with self.assertRaisesRegex(gw.Denied,'outside grant'):self.gateway.call(token,'C','GB','write','file-b',{'content':'wrong'})
    def test_parameters_cannot_override_target_or_run_script(self):
        for extra in ({'resource':'file-b'},{'script':'arbitrary'},{'url':'external'}):
            with self.assertRaisesRegex(gw.Denied,'unexpected'):self.call(parameters=dict(content='x',**extra))
    def test_unknown_token_or_stale_execution_denied(self):
        with self.assertRaisesRegex(gw.Denied,'unknown'):self.gateway.call('forged','C','GA','read','file-a',{})
        self.active=False
        with self.assertRaisesRegex(gw.Denied,'stale'):self.call()
    def test_revoke_run_and_grant(self):
        self.gateway.revoke_run(self.token)
        with self.assertRaisesRegex(gw.Denied,'revoked'):self.call()
        self.token=self.gateway.open_run('D2','T2','R3','baseline',['GA'],time.time()+100)
        self.gateway.revoke_grant('GA')
        with self.assertRaisesRegex(gw.Denied,'revoked'):self.call()
    def test_quota_and_no_connection_fallback(self):
        self.gateway.grants['GA']['max_calls']=1
        self.token=self.gateway.open_run('D2','T2','R-new','baseline',['GA'],time.time()+100);self.call()
        with self.assertRaisesRegex(gw.Denied,'quota'):self.call('C2')
        self.gateway.adapters={}
        with self.assertRaisesRegex(gw.Denied,'unavailable'):self.call('C3')
    def test_uncertain_write_is_not_retried_and_holds_resource(self):
        original=self.adapter.invoke;calls=[]
        def crash(*args):calls.append(args);original(*args);raise OSError('SIM connection lost after write')
        self.adapter.invoke=crash
        with self.assertRaises(OSError):self.call()
        self.adapter.invoke=original
        with self.assertRaisesRegex(gw.Denied,'uncertain'):self.call()
        with self.assertRaisesRegex(gw.Denied,'busy'):self.call('C2')
        self.assertEqual(1,len(calls));self.gateway.settle(self.token,'C1',{'observed':'candidate'},'SIM reread actual file')
        self.call('C2')
    def test_concurrent_duplicate_calls_have_one_side_effect(self):
        original=self.adapter.invoke;calls=[]
        def slow(*args):calls.append(args);time.sleep(.05);return original(*args)
        self.adapter.invoke=slow
        def invoke():
            try:return self.call()
            except gw.Denied:return 'pending'
        with ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(lambda _:invoke(),range(2)))
        self.assertEqual(1,len(calls))
    def test_old_run_cannot_inherit_revised_grant_after_host_restart(self):
        self.grants['GA'].update(revision=2,resources=['file-b'])
        restarted=gw.Gateway(self.gateway.path,self.grants,{'design-A':self.adapter},lambda s:True)
        with self.assertRaisesRegex(gw.Denied,'authorization changed'):
            restarted.call(self.token,'C','GA','write','file-b',{'content':'wrong'})
        self.assertFalse((self.root/'protected/b.md').exists())
    def test_symlink_mapping_is_rejected(self):
        (self.root/'protected').mkdir();(self.root/'outside.md').write_text('keep')
        (self.root/'protected/a.md').symlink_to(self.root/'outside.md')
        with self.assertRaisesRegex(gw.Denied,'escapes'):self.call()
        self.assertEqual('keep',(self.root/'outside.md').read_text())

class DelegatedGate(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory();self.addCleanup(t.cleanup);self.root=Path(t.name);(self.root/'collaboration').mkdir()
        for ref,text in {'authority.md':'SIM human delegates S3 for A to P1', 'artifact.md':'SIM rules A', 'decision.md':'SIM professional rationale', 'check.md':'SIM independent verification', 'conversation.md':'S3 → S4'}.items():(self.root/ref).write_text(text)
        art=gate.digests(self.root,['artifact.md'])
        self.grant=dict(id='D',revision=1,person_id='user',instance_id='P1',role='product',stages=['S3'],scope=['A'],source='authority.md',source_sha256=gate.digest(self.root/'authority.md'),expires_at='2099-01-01T00:00:00+00:00',revoked=False)
        self.decision=dict(delegation_id='D',delegation_revision=1,instance_id='P1',decision_kind='routine',role='product',stage='S3',scope=['A'],artifact_sha256=art['artifact_sha256'],source='decision.md',review='review.json',producers=['P1','AUTHOR'])
        self.review=dict(checker='P2',outcome='passed',scope=['A'],artifact_sha256=art['artifact_sha256'],evidence='check.md')
        self.state=dict(role='product',current='S3',next='S4',scope=['A'],blockers=[],conversation_check='conversation.md',delegated_decision='decision.json',**art)
    def check(self):
        for ref,data in [('collaboration/delegations.json',{'delegations':[self.grant]}),('decision.json',self.decision),('review.json',self.review)]: (self.root/ref).write_text(json.dumps(data))
        return gate.check(self.root,self.state)
    def test_delegation_is_not_human_confirmation(self):
        result=self.check();self.assertEqual('delegated',result['decision_basis']);self.assertNotIn('confirmed_by',result)
    def test_revoked_expired_or_changed_authority_blocks(self):
        self.grant['revoked']=True
        with self.assertRaisesRegex(ValueError,'revoked'):self.check()
        self.grant['revoked']=False;self.grant['expires_at']='2000-01-01T00:00:00+00:00'
        with self.assertRaisesRegex(ValueError,'expired'):self.check()
        self.grant['expires_at']='2099-01-01T00:00:00+00:00';(self.root/'authority.md').write_text('changed')
        with self.assertRaisesRegex(ValueError,'changed'):self.check()
    def test_wrong_actor_scope_and_self_check_block(self):
        self.decision['instance_id']='P3'
        with self.assertRaisesRegex(ValueError,'wrong'):self.check()
        self.decision['instance_id']='P1';self.grant['scope']=['B']
        with self.assertRaisesRegex(ValueError,'scope'):self.check()
        self.grant['scope']=['A'];self.review['checker']='P1'
        with self.assertRaisesRegex(ValueError,'independent'):self.check()
    def test_actual_author_cannot_be_independent_checker(self):
        self.review['checker']='AUTHOR'
        with self.assertRaisesRegex(ValueError,'independent'):self.check()
        self.decision.pop('producers')
        with self.assertRaisesRegex(ValueError,'producers'):self.check()
    def test_release_cannot_use_proxy_decision(self):
        self.state.update(role='release',current='E4.2',next='E4.3');(self.root/'conversation.md').write_text('E4.2 → E4.3')
        with self.assertRaisesRegex(ValueError,'cannot be delegated'):self.check()
    def test_single_listed_person_needs_actual_role_authority(self):
        (self.root/'collaboration/people.json').write_text(json.dumps({'people':[{'id':'designer','decides':['design']}]}))
        self.grant['person_id']='designer'
        with self.assertRaisesRegex(ValueError,'no decision authority'):self.check()

class Dispatch(ProjectFixture, unittest.TestCase):
    def setup_bridge(self,started=True):
        self.create('A-1','A','L');self.sends=[];self.wakes={}
        def send(endpoint,packet):
            self.sends.append(packet);return dict(outcome='sent',evidence='SIM delivered',started=started,start_evidence='SIM started')
        def wake(endpoint,note):self.wakes.setdefault(note['event_id'],note);return {'outcome':'sent','evidence':'SIM wake'}
        self.dispatcher=bridge.Dispatcher(self.root,ROOT/'.agents/skills',send,wake)
        c=self.dispatcher.c
        c('init',config={'protocol':'professional-collaboration/0.1','authorization':'SIMULATED','frontdoor':{'thread_id':'SIM-MAIN'}})
        for iid in ['L','W']:
            c('register',role=dict(id=iid,skill='kit-product.md',write_roots=['.agent-runtime/instances/'+iid+'/workspace'],endpoint={'kind':'subagent','id':'SIM-'+iid,'session':'SIM-session-'+iid}))
    def test_return_wakes_lead_without_closing_or_approving(self):
        (self.root/'kit-product.md').write_text('SIM product capability')
        self.setup_bridge()
        out=self.dispatcher.dispatch('A-1','REQ1',['input.md'],'authority.md')
        self.assertEqual('running',self.t('A-1')['state'])
        self.dispatcher.dispatch('A-1','REQ1',['input.md'],'authority.md')
        self.dispatcher.c('respond','W',id='REQ1',attempt=out['request']['attempt'],response=dict(kind='explanation',summary='SIM candidate ready',evidence=['SIM result artifact']))
        self.dispatcher.collect('REQ1');self.dispatcher.collect('REQ1')
        self.assertEqual('waiting_review',self.t('A-1')['state']);self.assertIsNone(self.t('A-1')['human_review'])
        self.assertEqual(1,len(self.sends));self.assertEqual(1,len(self.wakes))
    def test_sent_is_not_started(self):
        (self.root/'kit-product.md').write_text('SIM product capability');self.setup_bridge(False)
        self.dispatcher.dispatch('A-1','REQ1',['input.md'],'authority.md')
        self.assertEqual('planned',self.t('A-1')['state'])
        self.dispatcher.dispatch('A-1','REQ1',['input.md'],'authority.md')
        self.assertEqual(1,len(self.sends))
    def test_confirmed_not_sent_can_retry(self):
        (self.root/'kit-product.md').write_text('SIM capability');self.setup_bridge(False)
        original=self.dispatcher.send
        def failed(endpoint,packet):
            self.sends.append(packet);return dict(outcome='not_sent',evidence='SIM rejected before delivery')
        self.dispatcher.send=failed
        self.dispatcher.dispatch('A-1','R',['input.md'],'authority.md')
        self.dispatcher.c('retry',id='R');self.dispatcher.send=original
        result=self.dispatcher.dispatch('A-1','R',['input.md'],'authority.md')
        self.assertTrue(result['sent_now']);self.assertEqual(2,len(self.sends))
    def test_input_change_after_response_does_not_adopt_return(self):
        (self.root/'kit-product.md').write_text('SIM capability');self.setup_bridge()
        out=self.dispatcher.dispatch('A-1','R',['input.md'],'authority.md')
        self.dispatcher.c('respond','W',id='R',attempt=out['request']['attempt'],response=dict(kind='explanation',summary='SIM result',evidence=['SIM']))
        (self.root/'input.md').write_text('SIM revised after response')
        result=self.dispatcher.collect('R')
        self.assertFalse(result['notification']['source_current'])
        self.assertEqual('needs_attention',result['notification']['kind'])
    def test_reappointment_invalidates_pending_start(self):
        (self.root/'kit-product.md').write_text('SIM capability');self.setup_bridge(False)
        self.dispatcher.dispatch('A-1','R',['input.md'],'authority.md')
        self.call('appoint','PM',id='W',expected_revision=1,appointment=dict(mode='executor',role='product-agent',root_tasks=['A'],delegates=[],source='authority.md'))
        with self.assertRaisesRegex(self.dispatcher.pm.TaskError,'changed after dispatch'):
            self.dispatcher.mark_started('R','SIM actual start')
        self.assertEqual('planned',self.t('A-1')['state'])
    def test_late_start_cannot_resurrect_returned_work(self):
        (self.root/'kit-product.md').write_text('SIM capability');self.setup_bridge(False)
        out=self.dispatcher.dispatch('A-1','R',['input.md'],'authority.md')
        self.dispatcher.c('respond','W',id='R',attempt=out['request']['attempt'],response=dict(kind='explanation',summary='SIM result',evidence=['SIM']))
        self.dispatcher.collect('R')
        self.dispatcher.mark_started('R','SIM delayed start receipt')
        self.dispatcher.collect('R')
        self.assertNotEqual('running',self.t('A-1')['state'])

if __name__=='__main__':unittest.main()
