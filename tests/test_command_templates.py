"""Real subprocess plumbing; host-native isolation needs its separate live probe."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from kit import KIT, REPO
from test_pm_instances import Fixture, TEAM, pm

spec=importlib.util.spec_from_file_location('template_boundary',KIT/'matrix/orchestration/tools/isolated_runner.py')
boundary=importlib.util.module_from_spec(spec);spec.loader.exec_module(boundary)
spec=importlib.util.spec_from_file_location('template_production',REPO/'tools/production.py')
production=importlib.util.module_from_spec(spec);spec.loader.exec_module(production)

class Templates(unittest.TestCase):
    def test_expansion_environment_prompt_and_empty_arguments(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d).resolve()
            script="import os,sys,json;print(json.dumps({'cwd':os.getcwd(),'env':os.getenv('SIM_PARENT_PIPE'),'args':sys.argv[1:],'prompt':sys.stdin.read()}))"
            template={'argv':[sys.executable,'-c',script,'{model}','{effort}',''],'cwd':'{workspace}',
                      'unset_env':['SIM_PARENT_PIPE'],'prepend_paths':True}
            with patch.dict(os.environ,{'SIM_PARENT_PIPE':'must-not-reach-child'}):
                result=boundary.run(root,'SIM-A',[],prompt='SIM task',adapter='command-template',template=template,model='SIM-model',effort='high')
            data=json.loads(result['stdout'])
            self.assertEqual(0,result['exit_code']);self.assertIsNone(data['env'])
            self.assertEqual(['SIM-model','high',''],data['args'])
            self.assertEqual(str(root/'management/instances/SIM-A/workspace'),data['cwd'])
            self.assertIn(str(root),data['prompt']);self.assertTrue(data['prompt'].endswith('SIM task'))

    def test_unresolved_values_and_invalid_configuration_fail_before_launch(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d).resolve()
            for template in ({'argv':[sys.executable,'{effort}']},{'argv':[sys.executable,'{unknown}']},
                             {'argv':[sys.executable],'cwd':'/outside'}, {'argv':[sys.executable],'unset_env':['INVALID=NAME']},
                             {'argv':[sys.executable],'prepend_paths':'yes'}):
                with self.subTest(template=template), patch.object(boundary.subprocess,'Popen') as spawn:
                    with self.assertRaises(ValueError):
                        boundary.run(root,'SIM-A',[],adapter='command-template',template=template,model='SIM')
                    spawn.assert_not_called()

    def test_codex_01670_example_retains_tested_boundary_controls(self):
        cfg=json.loads((REPO/'docs/platforms/codex-0.167.0.json').read_text())
        self.assertEqual(('command-template','0.167.0','{workspace}'),(cfg['adapter'],cfg['version'],cfg['cwd']))
        args=cfg['argv'];self.assertEqual(['codex','exec'],args[:2])
        self.assertEqual('workspace-write',args[args.index('--sandbox')+1])
        for value in ['approval_policy="never"','sandbox_workspace_write.writable_roots=[]',
                      'sandbox_workspace_write.exclude_tmpdir_env_var=true','sandbox_workspace_write.exclude_slash_tmp=true',
                      'mcp_servers={}','model_reasoning_effort="{effort}"','skills.bundled.enabled=false']:
            self.assertIn(value,args)
        for flag in ['--ignore-user-config','--ignore-rules','--ephemeral']:
            self.assertIn(flag,args)
        self.assertIn('CODEX_APP_TOOLS_PIPE_PATH',cfg['unset_env'])
        self.assertTrue(all(c['state']=='unknown' for c in cfg['capabilities'].values()))

    def test_claude_2172_example_retains_kernel_and_tool_controls(self):
        cfg=json.loads((REPO/'docs/platforms/claude-2.1.72.json').read_text())
        self.assertEqual(('kernel','2.1.72'),(cfg['adapter'],cfg['version']))
        args=cfg['argv'];self.assertEqual(['claude','-p'],args[:2])
        self.assertEqual('{effort}',args[args.index('--effort')+1])
        self.assertEqual('',args[args.index('--setting-sources')+1])
        self.assertEqual('Read,Write,Bash',args[args.index('--tools')+1])
        for flag in ['--strict-mcp-config','--no-session-persistence','--disable-slash-commands']:
            self.assertIn(flag,args)
        self.assertTrue(json.loads(args[args.index('--settings')+1])['disableAllHooks'])
        self.assertIn('CODEX_APP_TOOLS_PIPE_PATH',cfg['unset_env'])

    def test_production_rejects_host_cli_and_environment_but_allows_install_paths(self):
        for text in ["['codex', 'exec']",'Run claude -p','codex --version',"os.environ['CODEX_THREAD_ID']"]:
            self.assertTrue(production.host_runtime_errors('matrix/tools/runner.py',text))
        self.assertFalse(production.host_runtime_errors('START.md','codex exec'))
        self.assertFalse(production.host_runtime_errors('install.py',"'.claude/skills', 'CLAUDE.md'"))

class Effort(Fixture, unittest.TestCase):
    def test_effort_follows_human_configuration_and_requires_profile_update(self):
        cfg=copy.deepcopy(TEAM);cfg['entries'][0]['effort']='medium';self.staff(cfg)
        self.assertEqual('medium',self.instance('code-engineering-001')['effort'])
        cfg['entries'][0]['effort']='high';self.write('instance-config.json',cfg);self.confirm()
        self.create('A',difficulty='T4')
        with self.assertRaisesRegex(pm.TaskError,'relevel_instance'):
            self.mutate('transition','A',state='running',reason='SIM',execution_receipt='SIM')
        rec=self.call('relevel_instance',id='code-engineering-001',expected_revision=1,reason='SIM confirmed effort update')['record']
        self.assertEqual(('T9','high'),(rec['level'],rec['effort']))
        self.mutate('transition','A',state='running',reason='SIM',execution_receipt='SIM')
