import importlib.util,json,tempfile,unittest,hashlib,copy
from pathlib import Path
s=importlib.util.spec_from_file_location('production',Path(__file__).resolve().parents[1]/'tools/production.py');p=importlib.util.module_from_spec(s);s.loader.exec_module(p)
class PublishingGateTests(unittest.TestCase):
 def setUp(self):self.build({'file':'0'*64})
 def build(self,files):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name);self.files=dict(files);suite=p.ROOT/'evals/cases/suite.json'
  suite_data=json.loads(suite.read_text());config=json.loads((p.ROOT/'package.json').read_text());baseline=config['baseline'];prior=p.ROOT/'release-manifests'/(baseline+'.json')
  if not prior.exists():prior=p.ROOT/'packages'/baseline/'MANIFEST.json'
  bh=p.fingerprint(json.loads(prior.read_text())['files']);ch=p.fingerprint(self.files);cases={}
  for c in suite_data['cases']:
   case={'baseline':{x:1 for x in c['criteria']},'candidate':{x:1 for x in c['criteria']}}
   for side,h in [('baseline',bh),('candidate',ch)]:
    directory=self.root/(side+'-'+c['id']);directory.mkdir();turns=[]
    for n,user in enumerate(c['turns']):
     raw=directory/(str(n)+'.md');raw.write_text('simulated fixture; not actual behavior evidence')
     events=directory/(str(n)+'.jsonl');events.write_text('{"type":"turn.completed"}\n')
     turns.append({'user':user,'reply':raw.name,'events':events.name,'sha256':p.sha(raw)})
    run=directory/'run.json';run.write_text(json.dumps({'runner':'codex exec','source_hash':h,'suite_hash':p.sha(suite),'cases':[{'id':c['id'],'turns':turns,**({'fixture_sha256':c['fixture_sha256']} if c.get('fixture') else {})}]}))
    case[side+'_run']=str(run.relative_to(self.root));case[side+'_evidence']=[{'path':str(f.relative_to(self.root)),'sha256':p.sha(f)} for f in directory.iterdir()]
   cases[c['id']]=case
  self.data={'baseline_ref':baseline,'baseline_hash':bh,'candidate_hash':ch,'suite_hash':p.sha(suite),'cases':cases,'reviewer':'test fixture','limitations':['simulated mechanism check, not real behavior']};self.report=self.root/'report.json'
 def check(self):self.report.write_text(json.dumps(self.data));return p.check_evidence(self.report,self.files)
 def test_complete_fixture_validates_schema(self):self.assertTrue(self.check())
 def test_source_change_blocks(self):
  self.files['file']='1'*64
  with self.assertRaises(ValueError):self.check()
 def test_suite_change_blocks(self):
  self.data['suite_hash']='old'
  with self.assertRaises(ValueError):self.check()
 def test_missing_case_blocks(self):
  self.data['cases'].pop('intake')
  with self.assertRaises(ValueError):self.check()
 def test_regression_blocks(self):
  self.data['cases']['intake']['candidate']['shows_stage']=0
  with self.assertRaises(ValueError):self.check()
 def test_changed_raw_evidence_blocks(self):
  (self.root/'candidate-intake/0.md').write_text('changed')
  with self.assertRaises(ValueError):self.check()
 def test_absent_evidence_blocks(self):
  self.data['cases']['intake']['candidate_evidence']=[]
  with self.assertRaises(ValueError):self.check()
 def test_relabeling_stale_run_blocks(self):
  self.files['file']='2'*64;self.data['candidate_hash']=p.fingerprint(self.files)
  with self.assertRaises(ValueError):self.check()
 def test_wrong_baseline_blocks(self):
  self.data['baseline_ref']='unknown'
  with self.assertRaises(ValueError):self.check()
 def test_incomplete_model_turn_blocks(self):
  path=self.root/'candidate-intake/0.jsonl';path.write_text('{"type":"turn.failed"}\n')
  for item in self.data['cases']['intake']['candidate_evidence']:
   if item['path']==str(path.relative_to(self.root)):item['sha256']=p.sha(path)
  with self.assertRaises(ValueError):self.check()
 def baseline_role_files(self,role):
  files=json.loads((p.ROOT/'release-manifests'/(self.data['baseline_ref']+'.json')).read_text())['files']
  return {k:v for k,v in files.items() if k.startswith('.agents/skills/'+role+'/')}
 def reuse_intake(self,role,files,source=None):
  self.build(files);run_path=self.root/'candidate-intake/run.json';run=json.loads(run_path.read_text())
  run['cases'][0].update(role=role,reused_from={'run':'previous/run.json','source_hash':source or self.data['baseline_hash']});run_path.write_text(json.dumps(run))
  for item in self.data['cases']['intake']['candidate_evidence']:
   if item['path']=='candidate-intake/run.json':item['sha256']=p.sha(run_path)
 def test_reuse_for_unchanged_role_passes(self):
  self.reuse_intake('product-agent',self.baseline_role_files('product-agent'));self.assertTrue(self.check())
 def test_reuse_for_changed_role_blocks(self):
  changed=self.baseline_role_files('product-agent');changed[next(iter(changed))]='f'*64;self.reuse_intake('product-agent',changed)
  with self.assertRaisesRegex(ValueError,'changed role'):self.check()
 def test_reuse_from_other_source_blocks(self):
  self.reuse_intake('product-agent',self.baseline_role_files('product-agent'),source='0'*64)
  with self.assertRaisesRegex(ValueError,'baseline release'):self.check()
if __name__=='__main__':unittest.main()
