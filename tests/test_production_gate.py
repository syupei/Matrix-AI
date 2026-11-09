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
 def test_stage_line_template_is_the_same_in_core_and_interaction(self):
  line='**{流程}：共 {N} 步｜依据：{记录文件}｜下一步：{动作}**';ui='# C01\n\n## 7. 流程位置\n\n第一行写：\n\n'+line+'\n\n## 8. 其他\n'
  self.assertEqual(p.stage_template_errors('1. 第一行写：'+line+'。',ui),[])
  self.assertTrue(p.stage_template_errors('1. 第一行写：**{流程}：共 {N} 步｜下一步：{动作}**。',ui))
  self.assertTrue(p.stage_template_errors('1. '+line,'# C01\n\n## 6. 其他\n\n'+line+'\n\n## 7. 流程位置\n\n见上。\n'))
  real=lambda rel:(p.SOURCE/rel).read_text();self.assertEqual(p.stage_template_errors(real('base/CORE.md'),real('base/USER-INTERACTION.md')),[])
 def test_new_mechanism_score_needs_a_second_scorer(self):
  case=self.data['cases']['intake'];k=next(iter(case['baseline']));case['baseline'][k]=0
  with self.assertRaisesRegex(ValueError,'re-check missing'):self.check()
  case['rechecked']={k:{'first':{'baseline':0,'candidate':1},'second':{'baseline':0,'candidate':1},'agree':True}};self.assertTrue(self.check())
 def test_disagreeing_scorers_need_a_persons_decision(self):
  case=self.data['cases']['intake'];k=next(iter(case['baseline']));case['baseline'][k]=0
  case['rechecked']={k:{'first':{'baseline':0,'candidate':1},'second':{'baseline':0,'candidate':0},'agree':False}}
  with self.assertRaisesRegex(ValueError,'disagree'):self.check()
  case['rescored']={'decided_by':'user','kept':[k]};self.assertTrue(self.check())
 def test_flagged_borderline_call_needs_a_second_scorer_and_no_silent_change(self):
  case=self.data['cases']['intake'];k=next(iter(case['baseline']));case['flags']=[k]
  with self.assertRaisesRegex(ValueError,'re-check missing'):self.check()
  case['rechecked']={k:{'first':{'baseline':0,'candidate':1},'second':{'baseline':0,'candidate':1},'agree':True}}
  with self.assertRaisesRegex(ValueError,'changed after'):self.check()
 def test_baseline_published_under_a_waiver_blocks(self):
  from unittest.mock import patch
  with patch.object(p,'waived_release',return_value=True),self.assertRaisesRegex(ValueError,'published under a waiver'):self.check()
 def test_released_baselines_are_read_from_the_catalog(self):
  self.assertFalse(p.waived_release('professional-agents-kit-v0.29'));self.assertTrue(p.waived_release('professional-agents-kit-v0.30'))
 def waiver(self,**changes):
  config=json.loads((p.ROOT/'package.json').read_text())
  data={'package':p.release_name(config),'source_hash':p.fingerprint(self.files),'authorized_by':'user','date':'2026-11-04','authorization':'explicit human authorization to skip the comparison','scope':'behavior comparison for this version','existing_evidence':['simulated'],'limitations':['simulated']}
  data.update(changes);path=self.root/'waiver.json';path.write_text(json.dumps(data));return path
 def test_explicit_waiver_for_this_source_passes(self):self.assertTrue(p.check_waiver(self.waiver(),self.files))
 def test_waiver_for_other_source_blocks(self):
  with self.assertRaises(ValueError):p.check_waiver(self.waiver(source_hash='other'),self.files)
 def test_waiver_without_authorization_blocks(self):
  with self.assertRaises(ValueError):p.check_waiver(self.waiver(authorization=''),self.files)
 def test_waiver_for_other_version_blocks(self):
  with self.assertRaises(ValueError):p.check_waiver(self.waiver(package='professional-agents-kit-v0.0'),self.files)
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
 def reuse_with_reads(self,read,files):
  self.reuse_intake('product-agent',files);run_path=self.root/'candidate-intake/run.json';run=json.loads(run_path.read_text())
  run['cases'][0]['read_files']=read;run_path.write_text(json.dumps(run))
  for item in self.data['cases']['intake']['candidate_evidence']:
   if item['path']=='candidate-intake/run.json':item['sha256']=p.sha(run_path)
 def test_reuse_is_judged_by_the_files_the_case_read(self):
  files=self.baseline_role_files('product-agent');kept,edited=sorted(files)[0],sorted(files)[-1]
  changed=dict(files);changed[edited]='f'*64  # a file of the role that this case did not read
  self.reuse_with_reads([kept],changed);self.assertTrue(self.check())
  self.reuse_with_reads([kept,edited],changed)
  with self.assertRaisesRegex(ValueError,'read file'):self.check()
 def carried(self,previous=None,replies=None):
  case=self.data['cases']['intake'];prev=copy.deepcopy(self.data)
  if previous:previous(prev['cases']['intake'])
  (self.root/'previous.json').write_text(json.dumps(prev))
  turns={s:[t['sha256'] for t in json.loads((self.root/case[s+'_run']).read_text())['cases'][0]['turns']] for s in ['baseline','candidate']}
  case['carried_from']={'path':'previous.json','sha256':p.sha(self.root/'previous.json'),'replies':replies or turns}
 def test_carried_scores_need_identical_replies_and_unchanged_scores(self):
  self.carried();self.assertTrue(self.check())
  self.build({'file':'0'*64});self.carried(replies={'baseline':['0'*64],'candidate':['0'*64]})
  with self.assertRaisesRegex(ValueError,'changed reply'):self.check()
  self.build({'file':'0'*64});self.carried(previous=lambda c:c['baseline'].update({next(iter(c['baseline'])):0}))
  with self.assertRaisesRegex(ValueError,'carried scores changed'):self.check()
if __name__=='__main__':unittest.main()
