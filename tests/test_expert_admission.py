"""Synthetic package/model/authorization facts; concurrency and Git argv are actual code paths."""
import copy
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import subprocess
import threading
import unittest
from unittest.mock import patch
from test_expert_packages import PlatformFixture, api, pm
import test_expert_packages as base

class Admission(base.Fixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.write('expert-professions.json', dict(schema='matrix-expert-professions/1', professions=['code-engineering'], configured_by='SIM-person', authorization='SIM-human preset'))
        self.e=pm.team.experts
        self.ident=dict(id='sim-expert',version='1')

    def package(self):
        base.Experts.package(self)

    def report(self, **change):
        p=self.root/'management/sim-validation.json';data=json.loads(p.read_text());data.update(change);p.write_text(json.dumps(data))
        return dict(self.ident,evidence=dict(runner='SIM-worker',report='management/sim-validation.json',source_sha256=data['methods_sha256']))

    def test_real_run_binding_state_model_and_presence_are_required(self):
        self.package()
        with pm.connect(self.root) as db: original=pm.integrity.records(db,'launch')['SIM-admission']
        for change in ({'state':'running'},{'exit_code':1},{'handed':False},{'cancel_requested':True},{'running_at':None},{'model':'OTHER'},
                       {'admission_runner':'OTHER'},{'admission_expert':dict(original['admission_expert'],version='2')}):
            with self.subTest(change=change):
                with pm.connect(self.root) as db: pm.integrity.save(pm.api(),db,'launch',dict(original,**change))
                with self.assertRaises(ValueError):self.e.validate(pm.api(),self.root,self.report(),operator='SIM-controller')
        with self.assertRaisesRegex(ValueError,'must exist'):
            self.e.validate(pm.api(),self.root,self.report(run_id='MISSING'),operator='SIM-controller')

    def test_launch_binds_admission_to_exact_package_content(self):
        self.package();self.staff();self.create('A')
        run=self.call('launch_start',id='SIM-new-run',purpose='start',task_id='A',instance='code-engineering-001',
                      model='SIM-big',session='SIM',command=['SIM-cli'],admission_expert=self.ident,admission_runner='SIM-runner')['record']
        self.assertEqual(self.e.admission_binding(pm.api(),self.root,self.ident),run['admission_expert'])
        self.assertEqual('SIM-runner',run['admission_runner'])

    @unittest.skipUnless(__import__('platform').system()=='Darwin','actual kernel boundary requires macOS')
    def test_admission_lifecycle_records_actual_process_and_handover(self):
        import importlib.util,sys
        from kit import KIT,REPO
        self.package()
        def load(name,path):
            spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
        lifecycle=load('admission_test_lifecycle',REPO/'evals/admission_run.py')
        boundary=load('admission_test_boundary',KIT/'matrix/orchestration/tools/isolated_runner.py')
        runner={'argv':[sys.executable,'-c',"from pathlib import Path;Path('management/instances/ADMISSION/workspace/public/admission.md').write_text('SIM result')"]}
        result=lifecycle.run(pm,boundary,self.root,self.ident,'SIM-kernel',runner,'SIM-model','medium','SIM prompt')
        with pm.connect(self.root,readonly=True) as db:run=pm.integrity.records(db,'launch')[result['run_id']]
        self.assertEqual(('exited',0,True),(run['state'],run['exit_code'],run['handed']))
        self.assertGreater(run['pid'],0)
        self.assertEqual(self.e.admission_binding(pm.api(),self.root,self.ident),run['admission_expert'])

    def test_enable_requires_authorization_and_retains_operator(self):
        self.package();base,m=self.e.read(pm.api(),self.root,self.ident)
        self.assertEqual('SIM-controller',m['validation']['operator'])
        self.assertEqual('SIM-person',m['enable_authorization']['person'])
        self.assertEqual('SIMULATED enable authorization',m['enable_authorization']['quote'])
        with self.assertRaisesRegex(ValueError,'enable requires'):
            self.e.enable(pm.api(),self.root,self.ident,operator='SIM-controller')

    def test_git_is_https_only_without_redirects_and_rejects_colliding_paths(self):
        calls=[]
        def fake(names):
            def run(argv,**kwargs):
                calls.append(argv)
                tail=argv[argv.index('credential.helper=')+1:]
                cmd=tail[0]
                if cmd=='rev-parse': out=b'a'*40+b'\n'
                elif cmd=='ls-tree':out=b'\0'.join(b'100644 blob '+b'b'*40+b'\t'+n.encode() for n in names)+b'\0'
                elif cmd=='cat-file':out=b'1' if tail[1]=='-s' else b'x'
                else:out=b''
                return subprocess.CompletedProcess(argv,0,stdout=out)
            return run
        for names in [('A.md','a.md'),('caf\u00e9.md','cafe\u0301.md'),('Dir/a.md','dir/b.md')]:
            with patch.object(self.e.subprocess,'run',side_effect=fake(names)):
                with self.assertRaisesRegex(ValueError,'collision'):self.e.fetch('https://example.org/test.git','a'*40)
        self.assertTrue(calls)
        for argv in calls:
            self.assertIn('protocol.allow=never',argv);self.assertIn('protocol.https.allow=always',argv)
            self.assertIn('http.followRedirects=false',argv)

class FetchTransaction(PlatformFixture,unittest.TestCase):
    def setup_prepare(self):
        self.write('expert-professions.json',dict(schema='matrix-expert-professions/1',professions=['code-engineering'],configured_by='SIM-person',authorization='SIM preset'))
        self.config['scripts']={'SIM':{'argv':['SIM-never-executed'],'permissions':'SIM','effect':'SIM register only'}};self.access()
        return self.req('expert.prepare',id='sim-new',version='1',profession='code-engineering',url='https://example.org/test.git',commit='a'*40)

    def test_fetch_holds_neither_process_nor_database_write_lock(self):
        request=self.setup_prepare();entered=threading.Event();release=threading.Event()
        def fetch(**kw):entered.set();release.wait(5);return {'SKILL.md':b'SIM'}
        with patch.object(api.pm.team.experts,'fetch',side_effect=fetch),ThreadPoolExecutor(max_workers=2) as pool:
            future=pool.submit(self.run_api,request)
            try:
                self.assertTrue(entered.wait(2))
                other=pool.submit(self.invoke,'scripts.request',id='SIM')
                self.assertEqual('requested',other.result(timeout=2)['state'])
            finally:release.set()
            self.assertTrue(future.result(timeout=3)['ok'])

    def test_existing_package_deleted_after_preflight_cannot_register_empty_source(self):
        import shutil
        request=self.setup_prepare()
        experts=api.pm.team.experts
        with patch.object(experts,'fetch',return_value={'SKILL.md':b'SIM'}):
            self.assertTrue(self.run_api(request)['ok'])
        plan=experts.prepare_plan(api.pm.api(),self.root,request['params'])
        self.assertIn('existing',plan)
        shutil.rmtree(self.root/'experts/sim-new/1')
        with self.assertRaisesRegex(ValueError,'source must not be empty'):
            experts.prepare(api.pm.api(),self.root,request['params'],prepared={'source':{},'preset':plan['preset']})
        self.assertFalse((self.root/'experts/sim-new/1').exists())

    def test_preset_is_rechecked_after_fetch(self):
        request=self.setup_prepare()
        def changed(**kw):
            path=self.root/'management/expert-professions.json'
            data=json.loads(path.read_text());data['authorization']='SIM changed preset';path.write_text(json.dumps(data))
            return {'SKILL.md':b'SIM'}
        with patch.object(api.pm.team.experts,'fetch',side_effect=changed):
            result=self.run_api(request)
        self.assertFalse(result['ok']);self.assertFalse((self.root/'experts/sim-new/1').exists())

    def test_authorization_is_rechecked_after_fetch_and_retry_does_not_refetch(self):
        request=self.setup_prepare()
        def revoked(**kw):
            self.config['principals']['SIM-controller']['active']=False;self.access();return {'SKILL.md':b'SIM'}
        with patch.object(api.pm.team.experts,'fetch',side_effect=revoked):
            result=self.run_api(request)
        self.assertEqual('UNAUTHORIZED',result['error']['code']);self.assertFalse((self.root/'experts/sim-new/1').exists())
        self.config['principals']['SIM-controller']['active']=True;self.access()
        with patch.object(api.pm.team.experts,'fetch',return_value={'SKILL.md':b'SIM'}) as fetch:
            first=self.run_api(request);again=self.run_api(request)
            self.assertTrue(first['ok']);self.assertEqual(first,again);self.assertEqual(1,fetch.call_count)
