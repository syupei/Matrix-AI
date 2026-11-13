"""Scope gate tests use simulated traces only; they are not release evidence."""
import copy,hashlib,json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import production as gate
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'evals'))
from read_records import extract

class ReadTests(unittest.TestCase):
    files={'matrix/base/a.md':'a','matrix/base/b.md':'b','other':'c'}
    def test_codex_directory_covers_added_files(self):
        r=extract([{'item':{'type':'command_execution','command':'rg needle kit/matrix/base'}}],'codex exec',self.files)
        self.assertEqual(r['files'],['matrix/base/a.md','matrix/base/b.md']);self.assertEqual(r['scopes'],['matrix/base'])
    def test_claude_tool_use_and_unknown_cwd(self):
        r=extract([{'message':{'content':[{'type':'tool_use','name':'Read','input':{'file_path':'/tmp/proj/kit/matrix/base/a.md'}}]}}],'claude subagent',self.files)
        self.assertEqual(r['files'],['matrix/base/a.md']);self.assertTrue(r['complete'])
        self.assertEqual(extract([{'item':{'type':'command_execution','command':'cd kit && cat matrix/base/a.md'}}],'codex exec',self.files)['scopes'],[''])
    def test_completion_alone_is_not_read_evidence(self):
        self.assertFalse(extract([{'type':'result'}],'claude subagent',self.files)['complete'])

class ScopedTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.repo=self.root/'repo';(self.repo/'evals/cases').mkdir(parents=True);(self.repo/'release-manifests').mkdir()
        self.files={'a.md':'a'*64,'b.md':'b'*64};self.suite={'cases':[{'id':'one','role':'x','turns':['ask'],'criteria':['ok']}]}
        (self.repo/'package.json').write_text(json.dumps({'baseline':'v1'}));(self.repo/'release-manifests/v1.json').write_text(json.dumps({'files':self.files}))
        self.suitefile=self.repo/'evals/cases/suite.json';self.suitefile.write_text(json.dumps(self.suite));self.patch=patch.object(gate,'ROOT',self.repo);self.patch.start();self.addCleanup(self.patch.stop)
        self.old=self.make_report('old',self.files)
    def make_report(self,name,files):
        data={'mode':'full','candidate_hash':gate.fingerprint(files),'candidate_files':files,'baseline_ref':'v1','baseline_hash':gate.fingerprint(self.files),'suite_hash':gate.sha(self.suitefile),'reviewer':'SIMULATED','limitations':['mechanism test only'],'cases':{}}
        snap=self.root/(name+'-suite.json');snap.write_bytes(self.suitefile.read_bytes());data['suite_snapshot']={'path':snap.name,'sha256':gate.sha(snap)}
        for c in self.suite['cases']:
            case={side:{k:1 for k in c['criteria']} for side in ['baseline','candidate']}
            for side in ['baseline','candidate']:
                folder=self.root/(name+'-'+c['id']+'-'+side);folder.mkdir();reply=folder/'reply.md';reply.write_text('SIMULATED')
                events=[{'item':{'type':'command_execution','command':'cat kit/a.md'}},{'type':'turn.completed'}]
                trace=folder/'events.jsonl';trace.write_text('\n'.join(json.dumps(e) for e in events))
                record={'id':c['id'],'turns':[{'user':c['turns'][0],'reply':reply.name,'events':trace.name,'sha256':gate.sha(reply)}],'read_set':extract(events,'codex exec',files)}
                run=folder/'run.json';run.write_text(json.dumps({'runner':'codex exec','source_hash':data[side+'_hash'],'suite_hash':data['suite_hash'],'cases':[record]}))
                case[side+'_run']=str(run.relative_to(self.root));case[side+'_evidence']=[{'path':str(p.relative_to(self.root)),'sha256':gate.sha(p)} for p in [reply,trace,run]]
            data['cases'][c['id']]=case
        path=self.root/(name+'.json');path.write_text(json.dumps(data));return path
    def scope(self,name,previous,files):
        old=json.loads(previous.read_text());data=copy.deepcopy(old);data.update(mode='scoped',candidate_hash=gate.fingerprint(files),candidate_files=files,previous={'path':previous.name,'sha256':gate.sha(previous)})
        for cid,case in data['cases'].items():
            replies={s:[t['sha256'] for t in json.loads((self.root/case[s+'_run']).read_text())['cases'][0]['turns']] for s in ['baseline','candidate']}
            case['carried_from']={'path':previous.name,'sha256':gate.sha(previous),'replies':replies}
        path=self.root/(name+'.json');path.write_text(json.dumps(data));return path
    def test_unread_change_is_carried_and_third_scope_rejected(self):
        files=dict(self.files,**{'b.md':'c'*64});one=self.scope('one',self.old,files);self.assertTrue(gate.check_evidence(one,files))
        files=dict(files,**{'b.md':'d'*64});two=self.scope('two',one,files);self.assertTrue(gate.check_evidence(two,files))
        third=self.scope('three',two,files)
        with self.assertRaisesRegex(ValueError,'third consecutive'):gate.check_evidence(third,files)
    def test_changed_read_new_case_and_modified_metadata_block(self):
        files=dict(self.files,**{'a.md':'c'*64});one=self.scope('one',self.old,files)
        with self.assertRaisesRegex(ValueError,'intersects'):gate.check_evidence(one,files)
        files=dict(self.files);one=self.scope('two',self.old,files)
        self.suite['cases'][0]['turns']=['changed'];self.suitefile.write_text(json.dumps(self.suite));d=json.loads(one.read_text());d['suite_hash']=gate.sha(self.suitefile);one.write_text(json.dumps(d))
        with self.assertRaisesRegex(ValueError,'new/changed'):gate.check_evidence(one,files)
    def test_missing_reads_and_tampered_previous_block(self):
        d=json.loads(self.old.read_text());c=d['cases']['one'];p=self.root/c['candidate_run'];r=json.loads(p.read_text());r['cases'][0].pop('read_set');p.write_text(json.dumps(r))
        for e in c['candidate_evidence']:
            if e['path']==c['candidate_run']:e['sha256']=gate.sha(p)
        self.old.write_text(json.dumps(d));one=self.scope('one',self.old,self.files)
        with self.assertRaisesRegex(ValueError,'no verifiable'):gate.check_evidence(one,self.files)
        self.old.write_text(self.old.read_text()+' ')
        with self.assertRaisesRegex(ValueError,'reference'):gate.check_evidence(one,self.files)
    def test_scope_assembler_preserves_original_run_bytes(self):
        from scoped_run import carry
        kit=self.root/'kit';kit.mkdir();files=dict(self.files,**{'b.md':'d'*64});(kit/'MANIFEST.json').write_text(json.dumps({'files':files}))
        out=self.root/'bundle';result=carry(self.old,out,kit,['one'])
        cases=json.loads((out/'carried-cases.json').read_text());old=json.loads(self.old.read_text())
        self.assertEqual((out/cases['one']['candidate_run']).read_bytes(),(self.root/old['cases']['one']['candidate_run']).read_bytes())
        data=dict(old,mode='scoped',previous=result['previous'],cases=cases,candidate_files=files,candidate_hash=gate.fingerprint(files))
        data['suite_snapshot']={'path':'current-suite.json','sha256':gate.sha(self.suitefile)};(out/'current-suite.json').write_bytes(self.suitefile.read_bytes())
        report=out/'comparison.json';report.write_text(json.dumps(data));self.assertTrue(gate.check_evidence(report,files))
    def test_fresh_run_must_match_final_source(self):
        d=json.loads(self.old.read_text());files=dict(self.files,**{'a.md':'c'*64});d.update(candidate_hash=gate.fingerprint(files),candidate_files=files);self.old.write_text(json.dumps(d))
        with self.assertRaisesRegex(ValueError,'source mismatch'):gate.check_evidence(self.old,files)
