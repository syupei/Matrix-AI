import importlib.util,json,tempfile,unittest,hashlib,copy
from pathlib import Path
P=Path(__file__).resolve().parents[1]/'src/collaboration/tools/stage_gate.py'
s=importlib.util.spec_from_file_location('gate',P);g=importlib.util.module_from_spec(s);s.loader.exec_module(g)
class GateTests(unittest.TestCase):
 def test_digest_helper_matches_gate(self):
  out=g.digests(self.root,['artifact.md'])
  self.assertEqual(out['artifact_sha256'],g.artifact_digest(self.root,out['artifacts']))
  with self.assertRaises(ValueError):g.digests(self.root,['../outside.md'])
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
  (self.root/'artifact.md').write_text('version 1');(self.root/'shown.md').write_text('visible review artifact v1');(self.root/'user.md').write_text('User confirms v1 and scope A')
  artifacts=[{'path':'artifact.md','sha256':g.digest(self.root/'artifact.md')}];h=g.artifact_digest(self.root,artifacts)
  self.req={'request_id':'R1','role':'design','stage':'D1','scope':['A'],'artifact_sha256':h,'display_evidence':'shown.md'}
  self.reply={'request_id':'R1','scope':['A'],'artifact_sha256':h,'actor':'user','choice':'confirm','source':'user.md'}
  self.state={'role':'design','current':'D1','next':'D2','scope':['A'],'blockers':[],'artifacts':artifacts,'request':'request.json','response':'response.json'}
 def run_check(self):
  (self.root/'request.json').write_text(json.dumps(self.req));(self.root/'response.json').write_text(json.dumps(self.reply));return g.check(self.root,self.state)
 def test_actual_records_allow(self):self.assertTrue(self.run_check()['allowed'])
 def test_absent_reply_fails(self):
  self.reply={}
  with self.assertRaises(ValueError):self.run_check()
 def test_adjust_does_not_approve(self):
  self.reply['choice']='adjust'
  with self.assertRaises(ValueError):self.run_check()
 def test_agent_does_not_approve(self):
  self.reply['actor']='assistant'
  with self.assertRaises(ValueError):self.run_check()
 def test_changed_artifact_blocks(self):
  (self.root/'artifact.md').write_text('v2')
  with self.assertRaises(ValueError):self.run_check()
 def test_stale_request_blocks(self):
  self.reply['request_id']='R0'
  with self.assertRaises(ValueError):self.run_check()
 def test_partial_scope_blocks(self):
  self.state['scope']=['A','B'];self.req['scope']=['A','B']
  with self.assertRaises(ValueError):self.run_check()
 def test_no_display_blocks(self):
  (self.root/'shown.md').write_text('')
  with self.assertRaises(ValueError):self.run_check()
 def test_skip_blocks(self):
  self.state['next']='D3'
  with self.assertRaises(ValueError):self.run_check()
 def test_real_blocker_blocks(self):
  self.state['blockers']=['missing business input']
  with self.assertRaises(ValueError):self.run_check()
 def test_internal_design_step_needs_no_extra_approval(self):
  self.state.update(current='D3',next='D4');self.state.pop('request');self.state.pop('response');self.assertTrue(self.run_check()['allowed'])
 def test_traversal_blocks(self):
  self.state['artifacts'][0]['path']='../outside'
  with self.assertRaises(ValueError):self.run_check()
if __name__=='__main__':unittest.main()
