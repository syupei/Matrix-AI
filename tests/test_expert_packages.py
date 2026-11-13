"""Mechanism tests: source packages, models, people and runner reports are SIMULATED."""
import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from test_pm_instances import Fixture, pm
from kit import KIT

s=importlib.util.spec_from_file_location('expert_api_test', KIT/'matrix/orchestration/tools/platform_api.py')
api=importlib.util.module_from_spec(s);s.loader.exec_module(api)


class Experts(Fixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.write('expert-professions.json', dict(schema='matrix-expert-professions/1', professions=['code-engineering'], configured_by='SIM-person', authorization='SIM-human preset'))
        self.e=pm.team.experts
        self.ident=dict(id='sim-expert',version='1')

    def package(self):
        with patch.object(self.e,'fetch',return_value={'SKILL.md':b'SIM professional method','LICENSE':b'SIM permission'}):
            self.e.prepare(pm.api(),self.root,dict(self.ident,profession='code-engineering',url='https://example.org/sim.git',commit='a'*40))
        self.e.adapt(pm.api(),self.root,dict(self.ident,methods='Use SIM professional method. Save under workspace/private/ or workspace/public/.',review=dict(reviewer='SIM',source_entry='SKILL.md',license='SIM permission',preserved_methods='SIM method',directory_changes='SIM destinations mapped',dependencies='none')))
        base,m=self.e.read(pm.api(),self.root,self.ident)
        sha=self.e.digest((base/'METHODS.md').read_bytes())
        self.write('sim-validation.json',dict(passed=True, methods_sha256=sha,runner='SIM-worker',checks={k:dict(passed=True,evidence='SIMULATED only') for k in ('method_preservation','write_isolation','handoff_contract')}))
        self.e.validate(pm.api(),self.root,dict(self.ident,evidence=dict(runner='SIM-worker',report='management/sim-validation.json',source_sha256=sha)))
        self.e.enable(pm.api(),self.root,self.ident)

    def config(self):
        return {'entries':[dict(id='internal',profession='code-engineering',level='T7',model='SIM-big',count=1,master=True,aliases=['小 M.ai']),
                           dict(id='imported',profession='code-engineering',level='T4',model='SIM-small',count=1,aliases=['小王.ai'],expert=self.ident,runner='SIM-other')]}

    def test_two_sources_and_aliases_keep_distinct_stable_identity(self):
        self.package();self.staff(self.config())
        a,b=[self.instance('code-engineering-'+x) for x in ['001','002']]
        self.assertEqual('builtin',a['expert']['id']);self.assertEqual('sim-expert',b['expert']['id'])
        self.assertEqual('SIM-other',b['runner'])
        self.assertIsNone(self.e.entry(pm.api(),self.root,a))
        self.assertEqual('experts/sim-expert/1/ENTRY.md',self.e.entry(pm.api(),self.root,b))
        self.assertEqual(a['id'],pm.execute(self.root,dict(op='resolve_instance',name=' 小 m.AI '))['record']['id'])
        self.call('rename_instance',id=b['id'],expected_revision=1,alias='小王二.ai')
        self.assertEqual(b['id'],pm.execute(self.root,dict(op='resolve_instance',name='小王.ai'))['record']['id'])
        with self.assertRaisesRegex(ValueError,'duplicate'):
            self.call('rename_instance',id=a['id'],expected_revision=1,alias='小王.ai')

    def test_legacy_binding_defaults_and_renamed_profile(self):
        self.staff({'entries':[dict(id='legacy',profession='code-engineering',level='T4',model='SIM-big',count=1)]})
        iid='code-engineering-001'
        db=pm.connect(self.root)
        old=pm.integrity.records(db,'instance')[iid]
        for key in ('expert','runner','alias','alias_history'):old.pop(key,None)
        pm.integrity.save(pm.api(),db,'instance',old);db.commit();db.close()
        self.write('instance-config.json',{'entries':[dict(id='legacy',profession='code-engineering',level='T5',model='SIM-big',count=1)]})
        self.confirm()
        self.call('relevel_instance',id=iid,expected_revision=1,reason='SIM confirmed level')
        self.call('rename_instance',id=iid,expected_revision=2,alias='新别名.ai')
        profile=(self.root/'management/instances'/iid/'profile.md').read_text()
        self.assertIn('新别名.ai',profile)
        db=pm.connect(self.root,readonly=True)
        try:self.assertIn('新别名.ai',pm.views.name(pm.views.context(pm.api(),self.root,db),iid))
        finally:db.close()

    def test_transport_success_alone_is_not_admission(self):
        self.package()
        base,manifest=self.e.read(pm.api(),self.root,self.ident)
        manifest['state']='awaiting_validation'
        self.e.save(pm.api(),base,manifest)
        self.write('sim-validation.json',dict(passed=True,methods_sha256=self.e.digest((base/'METHODS.md').read_bytes()),runner='SIM-worker'))
        with self.assertRaisesRegex(ValueError,'method, isolation and handoff'):
            self.e.validate(pm.api(),self.root,dict(self.ident,evidence=dict(runner='SIM-worker',report='management/sim-validation.json',source_sha256=self.e.digest((base/'METHODS.md').read_bytes()))))

    def test_preset_and_unvalidated_package_rejected(self):
        with self.assertRaisesRegex(ValueError,'not preset'):
            self.e.allowed(pm.api(),self.root,'product')
        with patch.object(self.e,'fetch',return_value={'SKILL.md':b'SIM'}):
            self.e.prepare(pm.api(),self.root,dict(self.ident,profession='code-engineering',url='https://example.org/sim.git',commit='a'*40))
        with self.assertRaisesRegex(ValueError,'not enabled'):
            self.e.binding(pm.api(),self.root,'code-engineering',self.ident)
        with self.assertRaisesRegex(ValueError,'validated expert'):
            self.e.enable(pm.api(),self.root,self.ident)

    def test_alias_duplicates_and_package_mutation_blocked(self):
        self.package();cfg=self.config();cfg['entries'][1]['aliases']=['小 m.AI']
        self.write('instance-config.json',cfg)
        with self.assertRaisesRegex(ValueError,'duplicate'):
            self.confirm()
        self.staff(self.config())
        base,_=self.e.read(pm.api(),self.root,self.ident)
        (base/'METHODS.md').write_text('tampered')
        with self.assertRaisesRegex(ValueError,'changed'):
            self.e.entry(pm.api(),self.root,self.instance('code-engineering-002'))

    def test_disabling_pinned_package_blocks_existing_instance(self):
        self.package();self.staff(self.config())
        self.e.disable(pm.api(),self.root,dict(self.ident,reason='SIM failed review'))
        with self.assertRaisesRegex(ValueError,'not enabled'):
            self.e.entry(pm.api(),self.root,self.instance('code-engineering-002'))

    def test_source_nested_manifest_is_hashed(self):
        self.package();base,m=self.e.read(pm.api(),self.root,self.ident)
        (base/'source/manifest.json').write_text('{}')
        with self.assertRaisesRegex(ValueError,'changed'):
            self.e.read(pm.api(),self.root,self.ident)

    def test_changed_preset_blocks_existing_package(self):
        self.package()
        self.write('expert-professions.json',dict(schema='matrix-expert-professions/1',professions=[],configured_by='SIM',authorization='SIM revoked'))
        with self.assertRaisesRegex(ValueError,'not preset'):
            self.e.binding(pm.api(),self.root,'code-engineering',self.ident)

    def test_git_fetch_rejects_credentials_and_nonfixed_refs_without_network(self):
        for url,commit in [('https://token@example.org/a.git','a'*40),('file:///tmp/a','a'*40),('https://example.org/a.git','main')]:
            with self.assertRaises(ValueError):
                self.e.fetch(url,commit)


class PlatformFixture(Fixture):
    def setUp(self):
        super().setUp()
        assessments=json.loads((self.root/'management/model-fit.json').read_text())
        for row in assessments['models']:
            if row['model']=='SIM-big': row['model_version']='SIM-actual'
            if row['model']=='SIM-small': row['model_version']='SIM-actual-small'
        self.write('model-fit.json',assessments)
        self.staff()
        self.create('A')
        caps={k:{'state':'supported','evidence':'SIMULATED fixture; no real sandbox claim'} for k in ('launch','write_isolation','model_selection')}
        self.config=dict(schema=api.SPEC, project_id='SIMULATED', principals={'SIM-controller':dict(active=True,actor='PM',operations=sorted(api.OPERATIONS),task_ops=['create','derive'])},
                         runners={'default':dict(version='SIM',models={'SIM-big':'SIM-actual'},capabilities=caps)})
        self.access()
        self.seq=0

    def access(self):
        (self.root/api.CONFIG).write_text(json.dumps(self.config))

    def req(self,operation,**params):
        self.seq+=1
        return dict(protocol=api.SPEC,project_id='SIMULATED',request_id='SIM-request-'+str(self.seq),event_id='SIM-event-'+str(self.seq),op=operation,params=params)

    def run_api(self,request):
        return api.handle(self.root,request,'SIM-controller')

    def invoke(self,op,**params):
        out=self.run_api(self.req(op,**params))
        self.assertTrue(out['ok'],out)
        return out['result']

    def claim(self):
        self.invoke('runtime.configure',mode='external',expected_generation=0)
        plan=self.invoke('actions.plan')
        return self.invoke('actions.claim',action_id=plan['actions'][0]['action_id'],expected_revision=plan['revision'])['record']

class Platform(PlatformFixture, unittest.TestCase):
    def test_plan_is_readonly_and_claim_is_atomic_idempotent(self):
        self.invoke('runtime.configure',mode='external',expected_generation=0)
        plan=self.invoke('actions.plan');again=self.invoke('actions.plan')
        self.assertEqual(plan,again);self.assertEqual('planned',self.t('A')['state'])
        req=self.req('actions.claim',action_id=plan['actions'][0]['action_id'],expected_revision=plan['revision'])
        first=self.run_api(req);self.assertTrue(first['ok'],first);self.assertEqual(first,self.run_api(req))
        self.assertEqual('running',self.t('A')['state'])
        stale=self.run_api(self.req('actions.claim',action_id=plan['actions'][0]['action_id'],expected_revision=plan['revision']))
        self.assertEqual('STALE_REVISION',stale['error']['code'])
        self.assertEqual(1,len(self.invoke('runs.query')['runs']))

    def test_owner_blocks_local_launch_and_switch_during_run(self):
        rec=self.claim()
        state=pm.execute(self.root,{'op':'continue'})
        self.assertEqual('managed',state['scheduler_health']['state'])
        self.assertNotIn('重启',state['scheduler_health']['message'])
        with self.assertRaisesRegex(ValueError,'external runtime'):
            self.call('launch_start',id='SIM-local',purpose='start',task_id='A',instance=rec['instance'],model='SIM',session='SIM',command=['SIM'])
        self.assertEqual('RUNS_ACTIVE',self.run_api(self.req('runtime.configure',mode='local',expected_generation=1))['error']['code'])

    def test_cancel_does_not_claim_stopped_and_unknown_does_not_relaunch(self):
        rec=self.claim()
        rec=self.invoke('runs.event',run_id=rec['id'],expected_revision=rec['revision'],kind='unknown',receipt='SIM connection lost')['record']
        self.assertEqual([],self.invoke('actions.plan')['actions'])
        result=self.invoke('runs.cancel',run_id=rec['id'],expected_revision=rec['revision'],reason='SIM stop')
        self.assertFalse(result['stopped']);self.assertEqual('starting',result['record']['state'])
        rec=result['record']
        rec=self.invoke('runs.event',run_id=rec['id'],expected_revision=rec['revision'],kind='failed',receipt='SIM runtime confirms never started')['record']
        self.assertEqual('not_started',rec['state'])
        self.assertEqual('RUN_CLOSED',self.run_api(self.req('runs.event',run_id=rec['id'],expected_revision=rec['revision'],kind='started',pid=123,model='SIM-actual',receipt='SIM late'))['error']['code'])

    def test_auth_actor_spoof_schema_and_idempotency(self):
        self.assertEqual('UNAUTHORIZED',api.handle(self.root,self.req('inspect'),'attacker')['error']['code'])
        self.assertEqual('INVALID_REQUEST',self.run_api(self.req('tasks.command',op='derive',actor='PM'))['error']['code'])

    def test_protocol_error_and_changed_request(self):
        req=self.req('inspect');req['protocol']='matrix-platform/99'
        self.assertEqual('UNSUPPORTED_PROTOCOL',self.run_api(req)['error']['code'])
        req=self.req('runtime.configure',mode='external',expected_generation=0)
        self.assertTrue(self.run_api(req)['ok']);req['params']['mode']='local'
        self.assertEqual('IDEMPOTENCY_CONFLICT',self.run_api(req)['error']['code'])

    def test_unknown_isolation_blocks_claim_without_start(self):
        self.config['runners']['default']['capabilities']['write_isolation']={'state':'unknown'};self.access()
        self.invoke('runtime.configure',mode='external',expected_generation=0)
        plan=self.invoke('actions.plan')
        result=self.run_api(self.req('actions.claim',action_id=plan['actions'][0]['action_id'],expected_revision=plan['revision']))
        self.assertEqual('UNSUPPORTED',result['error']['code']);self.assertEqual('planned',self.t('A')['state'])

    def test_two_concurrent_claims_start_at_most_one_run(self):
        from concurrent.futures import ThreadPoolExecutor
        self.invoke('runtime.configure',mode='external',expected_generation=0)
        plan=self.invoke('actions.plan')
        requests=[self.req('actions.claim',action_id=plan['actions'][0]['action_id'],expected_revision=plan['revision']) for _ in range(2)]
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(self.run_api,requests))
        self.assertEqual(1,sum(r['ok'] for r in results))
        self.assertEqual(1,len(self.invoke('runs.query')['runs']))

    def test_failed_git_retrieval_is_machine_readable(self):
        import subprocess
        with patch.object(api.pm.team.experts,'prepare',side_effect=subprocess.CalledProcessError(128,['git'])):
            result=self.run_api(self.req('expert.prepare',id='x',version='1',profession='product',url='https://example.org/x',commit='a'*40))
        self.assertEqual('SOURCE_UNAVAILABLE',result['error']['code'])
        self.assertTrue(result['error']['retryable'])

    def test_wrong_actual_model_rejected(self):
        rec=self.claim()
        result=self.run_api(self.req('runs.event',run_id=rec['id'],expected_revision=1,kind='started',pid=123,model='WRONG',receipt='SIM receipt'))
        self.assertEqual('MODEL_MISMATCH',result['error']['code'])


if __name__=='__main__':unittest.main()

@unittest.skipUnless(__import__('platform').system()=='Darwin', 'local kernel reference runner')
class ReferenceWorker(PlatformFixture, unittest.TestCase):
    def test_reference_controller_hands_over_without_worker_database_write(self):
        spec=importlib.util.spec_from_file_location('reference_worker_test', KIT/'matrix/orchestration/tools/reference_worker.py')
        worker=importlib.util.module_from_spec(spec);spec.loader.exec_module(worker)
        import sys
        script='''import sys,re,json
from pathlib import Path
text=sys.stdin.read()
print(json.dumps({'type':'system','subtype':'init','model':'SIM-concrete-version'}),flush=True)
out=re.search(r'management/instances/[^ ]+/workspace/public/run-[a-z0-9]+-handoff.json',text).group(0).rstrip('。')
p=Path(out);p.parent.mkdir(parents=True,exist_ok=True)
file=p.parent/'candidate.txt';file.write_text('SIM worker real file')
p.write_text(json.dumps({'summary':'SIM actual local worker handover','evidence':[str(file)]}))
'''
        self.config['runners']['default']['argv']=[sys.executable,'-c',script,''];self.access()
        self.invoke('runtime.configure',mode='local',expected_generation=0)
        result=worker.execute(self.root,'SIM-controller',timeout=10)
        self.assertTrue(result['handed'],result)
        self.assertEqual('waiting_review',self.t('A')['state'])
        runs=self.invoke('runs.query')['runs'];self.assertEqual('exited',runs[0]['state'])
        self.assertEqual('SIM-actual',runs[0]['model'])
        self.assertEqual('SIM-concrete-version',runs[0]['reported_model'])


    def test_parallel_workers_complete_start_callbacks_and_handover(self):
        import sys
        import subprocess
        from concurrent.futures import ThreadPoolExecutor
        spec=importlib.util.spec_from_file_location('parallel_reference_worker', KIT/'matrix/orchestration/tools/reference_worker.py')
        worker=importlib.util.module_from_spec(spec);spec.loader.exec_module(worker)
        script='''import sys,re,json,time
from pathlib import Path
text=sys.stdin.read()
p=Path(re.search(r'management/instances/[^ ]+/workspace/public/run-[a-z0-9]+-handoff.json',text).group(0).rstrip('。'))
f=p.parent/'candidate.txt';f.write_text('SIM actual parallel worker')
p.write_text(json.dumps({'summary':'SIM real process handover','evidence':[str(f)]}))
time.sleep(0.05)
'''
        class Case(PlatformFixture,unittest.TestCase):pass
        # Exercise mixed query/write connections while both real children run,
        # in one multithreaded controller and in two independent controllers.
        for mode in ('threads','processes'):
            for iteration in range(6):
                with self.subTest(mode=mode,iteration=iteration):
                    c=Case();c.setUp()
                    try:
                        c.create('B',executor='code-engineering-002')
                        c.config['runners']['default'].update(argv=[sys.executable,'-c',script])
                        c.config['runners']['default']['models']['SIM-small']='SIM-actual-small'
                        c.access();c.invoke('runtime.configure',mode='local',expected_generation=0)
                        actions=c.invoke('actions.plan')['actions']
                        self.assertEqual(2,len(actions))
                        def execute(action):
                            for attempt in range(4):
                                try:
                                    if mode=='threads':
                                        return worker.execute(c.root,'SIM-controller',action['action_id'],timeout=10)
                                    proc=subprocess.run([sys.executable,str(KIT/'matrix/orchestration/tools/reference_worker.py'),'--project',str(c.root),'--principal','SIM-controller','--action',action['action_id'],'--timeout','10'],capture_output=True,text=True,timeout=20)
                                    result=json.loads(proc.stdout)
                                    if proc.returncode:raise ValueError(result)
                                    return result
                                except ValueError as error:
                                    if 'STALE_REVISION' not in str(error) or attempt==3:raise
                        with ThreadPoolExecutor(max_workers=2) as pool:
                            results=list(pool.map(execute,actions))
                        self.assertTrue(all(r.get('handed') for r in results),results)
                        runs=c.invoke('runs.query')['runs']
                        self.assertEqual(2,len(runs));self.assertTrue(all(r['state']=='exited' and r.get('pid') for r in runs),runs)
                        self.assertEqual({'waiting_review'},{c.t(t)['state'] for t in ('A','B')})
                        db=pm.connect(c.root,readonly=True)
                        try:self.assertEqual('ok',db.execute('PRAGMA integrity_check').fetchone()[0])
                        finally:db.close()
                    finally:c.doCleanups()
