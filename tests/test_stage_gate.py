import importlib.util,json,tempfile,unittest,hashlib,copy
from pathlib import Path
P=Path(__file__).resolve().parents[1]/'src/collaboration/tools/stage_gate.py'
s=importlib.util.spec_from_file_location('gate',P);g=importlib.util.module_from_spec(s);s.loader.exec_module(g)
class GateTests(unittest.TestCase):
 def test_flows_from_registries_match_previous_gate(self):
  # Same flows, review points and upstream links as the earlier hard-coded gate; only the codes are now <abbr>-<n>.
  self.assertEqual(g.STAGES,{'product':['P-1','P-2','P-3','P-4','P-5','P-6','P-7','complete'],'design':['D-1','D-2','D-3','D-4','D-5','D-6','D-7','complete'],'engineering':['E-1.1','E-1.2','E-1.3','E-1.4','complete'],'solution':['E-2.1','E-2.2','E-2.3','E-2.4','complete'],'build':['E-3.1','E-3.2','E-3.3','complete'],'release':['E-4.1','E-4.2','E-4.3','complete']})
  self.assertEqual(g.REVIEW,{'product':{'P-1','P-2','P-3','P-4','P-5','P-6','P-7'},'design':{'D-1','D-2','D-4','D-6'},'engineering':{'E-1.4'},'solution':{'E-2.4'},'build':{'E-3.3'},'release':{'E-4.2'}})
  self.assertEqual(g.CHAIN,['project','product','design','engineering','solution','build'])
  self.assertEqual(g.AUTHORITY,{'release':{'project','release'}})
  self.assertEqual(g.UPSTREAM,{('build','E-3.1'):('solution','E-2.4'),('release','E-4.1'):('build','E-3.3')})
 def test_digest_helper_matches_gate(self):
  out=g.digests(self.root,['artifact.md'])
  self.assertEqual(out['artifact_sha256'],g.artifact_digest(self.root,out['artifacts']))
  with self.assertRaises(ValueError):g.digests(self.root,['../outside.md'])
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
  (self.root/'artifact.md').write_text('version 1');(self.root/'shown.md').write_text('visible review artifact v1');(self.root/'user.md').write_text('User confirms v1 and scope A')
  artifacts=[{'path':'artifact.md','sha256':g.digest(self.root/'artifact.md')}];h=g.artifact_digest(self.root,artifacts)
  self.req={'request_id':'R1','role':'design','stage':'D-1','scope':['A'],'artifact_sha256':h,'display_evidence':'shown.md'}
  self.reply={'request_id':'R1','scope':['A'],'artifact_sha256':h,'actor':'user','choice':'confirm','source':'user.md'}
  self.state={'role':'design','current':'D-1','next':'D-2','scope':['A'],'blockers':[],'artifacts':artifacts,'request':'request.json','response':'response.json','conversation_check':'conversation.md'}
  self.write_conversation=True
 def run_check(self):
  (self.root/'request.json').write_text(json.dumps(self.req));(self.root/'response.json').write_text(json.dumps(self.reply))
  if self.write_conversation:(self.root/'conversation.md').write_text('## 核对：%s → %s\n- 无\n'%(self.state['current'],self.state['next']),encoding='utf-8')
  return g.check(self.root,self.state)
 def test_conversation_check_is_required_for_each_transition(self):
  self.write_conversation=False;self.state.pop('conversation_check')
  with self.assertRaisesRegex(ValueError,'conversation'):self.run_check()
  self.state['conversation_check']='conversation.md'
  (self.root/'conversation.md').write_text('## 核对：P-1 → P-2\n- 无\n',encoding='utf-8')  # an older entry does not cover D-1 → D-2
  with self.assertRaisesRegex(ValueError,'conversation'):self.run_check()
  (self.root/'conversation.md').write_text('## 核对：P-1 → P-2\n- 无\n## 核对：D-1->D-2\n- 按钮加大，已记入 DS-ACT-3\n',encoding='utf-8')
  self.assertTrue(self.run_check()['allowed'])
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
  self.state['next']='D-3'
  with self.assertRaises(ValueError):self.run_check()
 def test_real_blocker_blocks(self):
  self.state['blockers']=['missing business input']
  with self.assertRaises(ValueError):self.run_check()
 def test_internal_design_step_needs_no_extra_approval(self):
  self.state.update(current='D-3',next='D-4');self.state.pop('request');self.state.pop('response');self.assertTrue(self.run_check()['allowed'])
 def test_solution_core_review_needs_human_confirmation(self):
  self.req.update(role='solution',stage='E-2.4');self.state.update(role='solution',current='E-2.4',next='complete')
  self.assertTrue(self.run_check()['allowed'])
  self.reply['actor']='assistant'
  with self.assertRaises(ValueError):self.run_check()
 def test_solution_internal_step_needs_no_review(self):
  self.state.update(role='solution',current='E-2.2',next='E-2.3');self.state.pop('request');self.state.pop('response');self.assertTrue(self.run_check()['allowed'])
 def test_solution_cannot_skip_to_complete(self):
  self.state.update(role='solution',current='E-2.2',next='complete')
  with self.assertRaises(ValueError):self.run_check()
 def test_team_reply_must_name_a_deciding_person(self):
  (self.root/'collaboration').mkdir()
  (self.root/'collaboration/people.json').write_text(json.dumps({'people':[{'id':'lead','name':'P','decides':['product']},{'id':'art','name':'A','decides':['design']},{'id':'dev','name':'D'}]}))
  with self.assertRaises(ValueError):self.run_check()
  self.reply.update(actor='person',person_id='dev')
  with self.assertRaises(ValueError):self.run_check()
  self.reply['person_id']='art';self.assertEqual('art',self.run_check()['confirmed_by'])
  self.reply['person_id']='lead';self.assertTrue(self.run_check()['allowed'])  # upstream flow may confirm
  self.req.update(role='product',stage='P-1');self.state.update(role='product',current='P-1',next='P-2');self.reply['person_id']='art'
  with self.assertRaises(ValueError):self.run_check()  # downstream cannot confirm an upstream flow
 def test_build_needs_confirmed_technical_review_before_implementation(self):
  (self.root/'solution.md').write_text('core review package v1')
  arts=[{'path':'solution.md','sha256':g.digest(self.root/'solution.md')}];h=g.artifact_digest(self.root,arts)
  self.req.update(role='solution',stage='E-2.4',artifact_sha256=h);self.reply['artifact_sha256']=h
  (self.root/'e2-gate.json').write_text(json.dumps({'role':'solution','current':'E-2.4','next':'complete','scope':['A'],'blockers':[],'artifacts':arts,'request':'request.json','response':'response.json'}))
  self.state.update(role='build',current='E-3.1',next='E-3.2');self.state.pop('request');self.state.pop('response')
  with self.assertRaisesRegex(ValueError,'upstream'):self.run_check()  # no technical review record
  self.state['upstream']='e2-gate.json'
  self.assertEqual('e2-gate.json',self.run_check()['upstream'])
  self.reply['actor']='assistant'
  with self.assertRaisesRegex(ValueError,'upstream'):self.run_check()  # review not confirmed by a person
  self.reply['actor']='user';(self.root/'solution.md').write_text('core review package v2')
  with self.assertRaisesRegex(ValueError,'upstream'):self.run_check()  # confirmed baseline changed since
 def test_build_scope_review_needs_human_confirmation(self):
  self.req.update(role='build',stage='E-3.3');self.state.update(role='build',current='E-3.3',next='complete')
  self.assertTrue(self.run_check()['allowed'])
  self.reply['actor']='assistant'
  with self.assertRaises(ValueError):self.run_check()
 def test_build_internal_step_needs_no_review(self):
  self.state.update(role='build',current='E-3.2',next='E-3.3');self.state.pop('request');self.state.pop('response');self.assertTrue(self.run_check()['allowed'])
 def test_release_decision_needs_still_valid_scope_review(self):
  (self.root/'scope.md').write_text('scope complete package v1')
  arts=[{'path':'scope.md','sha256':g.digest(self.root/'scope.md')}];h=g.artifact_digest(self.root,arts)
  self.req.update(role='build',stage='E-3.3',artifact_sha256=h);self.reply['artifact_sha256']=h
  (self.root/'e3-gate.json').write_text(json.dumps({'role':'build','current':'E-3.3','next':'complete','scope':['A'],'blockers':[],'artifacts':arts,'request':'request.json','response':'response.json'}))
  self.state.update(role='release',current='E-4.1',next='E-4.2');self.state.pop('request');self.state.pop('response')
  with self.assertRaisesRegex(ValueError,'upstream'):self.run_check()  # no scope review record
  self.state['upstream']='e3-gate.json'
  self.assertEqual('e3-gate.json',self.run_check()['upstream'])
  (self.root/'scope.md').write_text('scope complete package v2')
  with self.assertRaisesRegex(ValueError,'upstream'):self.run_check()  # confirmed scope changed since
 def test_release_decision_needs_human_confirmation_of_this_package(self):
  self.req.update(role='release',stage='E-4.2');self.state.update(role='release',current='E-4.2',next='E-4.3')
  self.assertTrue(self.run_check()['allowed'])
  self.reply['actor']='assistant'
  with self.assertRaises(ValueError):self.run_check()  # an agent cannot decide a release
  self.reply['actor']='user';(self.root/'artifact.md').write_text('candidate rebuilt after the decision')
  with self.assertRaises(ValueError):self.run_check()  # the decision covered a different package
 def test_release_internal_steps_need_no_review_and_cannot_skip(self):
  self.state.update(role='release',current='E-4.3',next='complete');self.state.pop('request');self.state.pop('response')
  self.assertTrue(self.run_check()['allowed'])
  self.state.update(current='E-4.1',next='E-4.3')
  with self.assertRaises(ValueError):self.run_check()  # cannot skip the decision
 def test_release_decision_is_not_inherited_from_professional_flows(self):
  (self.root/'collaboration').mkdir()
  (self.root/'collaboration/people.json').write_text(json.dumps({'people':[{'id':'boss','name':'B','decides':['project']},{'id':'rel','name':'R','decides':['release']},{'id':'pm','name':'P','decides':['product']},{'id':'lead','name':'L','decides':['build']}]}))
  self.req.update(role='release',stage='E-4.2');self.state.update(role='release',current='E-4.2',next='E-4.3');self.reply['actor']='person'
  for pid in ('pm','lead'):
   self.reply['person_id']=pid
   with self.assertRaises(ValueError):self.run_check()
  for pid in ('rel','boss'):
   self.reply['person_id']=pid;self.assertEqual(pid,self.run_check()['confirmed_by'])
 def test_traversal_blocks(self):
  self.state['artifacts'][0]['path']='../outside'
  with self.assertRaises(ValueError):self.run_check()
if __name__=='__main__':unittest.main()
