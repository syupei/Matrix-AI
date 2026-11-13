"""Actual local OS boundary, no model calls. Unsupported systems skip, never count as passed isolation."""
import importlib.util
import json
from pathlib import Path
import platform
import sys
import tempfile
import unittest
from kit import KIT
s=importlib.util.spec_from_file_location('write_boundary',KIT/'matrix/orchestration/tools/isolated_runner.py')
boundary=importlib.util.module_from_spec(s);s.loader.exec_module(boundary)

@unittest.skipUnless(platform.system()=='Darwin' and Path('/usr/bin/sandbox-exec').exists(),'macOS reference runner only')
class Boundary(unittest.TestCase):
    def test_real_writes_tools_descendants_links_and_parent_escape(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d).resolve();work=boundary.safe_workspace(root,'SIM-A')
            other=boundary.safe_workspace(root,'SIM-B')
            protected=root/'protected.txt';protected.write_text('unchanged')
            script='''import os,json,subprocess,sys
from pathlib import Path
root=Path.cwd();workspace=root/'management/instances/SIM-A/workspace';out={}
for name,path in [('private',workspace/'private/good.txt'),('public',workspace/'public/good.txt'),('other',root/'management/instances/SIM-B/workspace/public/no.txt'),('root',root/'bad.txt'),('parent',workspace/'../../profile.md')]:
 try:path.write_text('attempt');out[name]=True
 except OSError:out[name]=False
link=workspace/'public/link'
try:
 link.symlink_to(root/'protected.txt');link.write_text('escape');out['symlink_escape']=True
except OSError:out['symlink_escape']=False
try:os.link(root/'protected.txt',workspace/'public/hard');out['hardlink_escape']=True
except OSError:out['hardlink_escape']=False
proc=subprocess.run([sys.executable,'-c',"open('bad-script.txt','w').write('escape')"],capture_output=True)
out['child_script_escape']=proc.returncode==0
print(json.dumps(out))
'''
            result=boundary.run(root,'SIM-A',[sys.executable,'-c',script])
            self.assertEqual(0,result['exit_code'],result)
            self.assertEqual({'private':True,'public':True,'other':False,'root':False,'parent':False,'symlink_escape':False,'hardlink_escape':False,'child_script_escape':False},json.loads(result['stdout']))
            self.assertEqual('unchanged',protected.read_text())

    def test_existing_symlink_and_hardlink_are_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d).resolve();work=boundary.safe_workspace(root,'SIM-A')
            target=root/'protected';target.write_text('protected')
            link=work/'private/link';link.symlink_to(target)
            with self.assertRaisesRegex(ValueError,'links'):boundary.safe_workspace(root,'SIM-A')
            link.unlink()
            import os
            os.link(target,link)
            with self.assertRaisesRegex(ValueError,'links'):boundary.safe_workspace(root,'SIM-A')

    def test_timeout_terminates_actual_process_group(self):
        with tempfile.TemporaryDirectory() as d:
            result=boundary.run(Path(d).resolve(),'SIM-A',[sys.executable,'-c','import time; time.sleep(20)'],timeout=0.1)
            self.assertTrue(result['stopped']);self.assertTrue(result['timed_out']);self.assertNotEqual(0,result['exit_code'])

    def test_timeout_stops_term_ignoring_descendant_after_parent_exit(self):
        import os,signal,time
        with tempfile.TemporaryDirectory() as d:
            root=Path(d).resolve();work=boundary.safe_workspace(root,'SIM-A')
            child="import signal,time,os;from pathlib import Path;signal.signal(signal.SIGTERM,signal.SIG_IGN);Path('management/instances/SIM-A/workspace/public/child.pid').write_text(str(os.getpid()));time.sleep(1);Path('management/instances/SIM-A/workspace/public/late.txt').write_text('survived');time.sleep(2)"
            parent="import subprocess,time,sys;subprocess.Popen([sys.executable,'-c',"+repr(child)+"],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL);time.sleep(20)"
            result=boundary.run(root,'SIM-A',[sys.executable,'-c',parent],timeout=.5)
            self.assertTrue((work/'public/child.pid').exists(),'child must really start')
            try:
                time.sleep(1)
                self.assertTrue(result['timed_out']);self.assertTrue(result['stopped'])
                self.assertFalse((work/'public/late.txt').exists(),'descendant survived reported stop')
            finally:
                try:os.kill(int((work/'public/child.pid').read_text()),signal.SIGKILL)
                except ProcessLookupError:pass

if __name__=='__main__':unittest.main()
