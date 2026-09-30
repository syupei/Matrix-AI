#!/usr/bin/env python3
"""Build only canonical consumer sources; require real comparison evidence to publish."""
import argparse,hashlib,json,os,re,shutil,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'src'
ALLOWED=('.agents/skills/','collaboration/','shared/')
TOP={'START.md','BEHAVIOR-CHECKS.md','install.py','upgrade-bases.json'}
# Consumer text must stay host-neutral and free of build history (the capability model is quoted source text).
HOST_OR_HISTORY=re.compile(r'[Cc]odex|[Oo]pen[Aa][Ii]|[Cc]laude|[Aa]nthropic|functions\.|request_user_input|mcp__|~/|试验|来源项目|原项目|旧版|旧项目|此前版本|历史版本|本版新增|\bv0\.\d+|[A-Z]+-(?:DEC|Q)-\d{3}|COPY-00\d|STRUCT-00\d')
TEXT_EXEMPT=('.agents/skills/product-capability-model/standards/',)
RUNNERS={'codex exec':'turn.completed','claude -p':'result','claude subagent':'result'}
PRIVATE=re.compile(r'DFW(?:[-_ ]TEST)?|EC[-_ ](?:TEST|CHINA)|EAST[-_ ]CHINA|/Users/|[A-Z]:\\Users\\',re.I)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def source_files():
 files={}
 for p in sorted(SOURCE.rglob('*')):
  if not p.is_file():continue
  rel=str(p.relative_to(SOURCE))
  if '__pycache__' in p.parts or p.name in ['.DS_Store','MANIFEST.json']:continue
  if p.name.startswith('test_') or 'tests' in p.parts:raise ValueError('maintainer test in runtime source: '+rel)
  if p.is_symlink() or not (rel in TOP or rel.startswith(ALLOWED)):raise ValueError('non-runtime source: '+rel)
  if p.suffix in {'.md','.py','.html','.json','.yaml','.txt'} and PRIVATE.search(p.read_text()):raise ValueError('internal identity in package: '+rel)
  files[rel]=sha(p)
 return files

def fingerprint(files):return hashlib.sha256(json.dumps(files,sort_keys=True).encode()).hexdigest()
def check_sources():
 files=source_files();errors=[];links=0
 for rel in files:
  p=SOURCE/rel
  if p.name=='SKILL.md' and len(p.read_text())>3500:errors.append('entry exceeds 3500 characters: '+rel)
  if p.suffix in {'.md','.html'} and not rel.startswith(TEXT_EXEMPT):
   text=p.read_text().replace('.claude/skills','.<host>/skills') if rel=='START.md' else p.read_text()
   for m in HOST_OR_HISTORY.finditer(text):errors.append(f'host name or build history in consumer text: {rel}: {m.group(0)}')
  if p.suffix=='.md' and not rel.startswith('shared/'):
   for href in re.findall(r'\]\(([^)]+)\)',p.read_text()):
    path=href.split('#')[0]
    if not path or '://' in path or path.startswith('mailto:'):continue
    dest=(p.parent/path).resolve()
    if not dest.is_relative_to(SOURCE.resolve()) or not dest.exists():errors.append('broken link: '+rel+' -> '+href)
    links+=1
 if errors:raise ValueError('\n'.join(errors))
 return files,links

def check_evidence(report,files):
 data=json.loads(report.read_text())
 if data.get('candidate_hash')!=fingerprint(files):raise ValueError('behavior evidence belongs to different source')
 suite=ROOT/'evals/cases/suite.json'
 if data.get('suite_hash')!=sha(suite):raise ValueError('behavior suite changed')
 specs={c['id']:c for c in json.loads(suite.read_text())['cases']}
 expected={cid:set(c['criteria']) for cid,c in specs.items()}
 baseline=json.loads((ROOT/'package.json').read_text())['baseline']
 if data.get('baseline_ref')!=baseline:raise ValueError('wrong baseline version')
 prior=ROOT/'release-manifests'/(baseline+'.json')
 if not prior.exists():prior=ROOT/'packages'/baseline/'MANIFEST.json'
 baseline_hash=fingerprint(json.loads(prior.read_text())['files'])
 if data.get('baseline_hash')!=baseline_hash:raise ValueError('wrong baseline source')
 if set(data.get('cases',{}))!=set(expected):raise ValueError('missing/extra behavior cases')
 runners=set()
 for cid,criteria in expected.items():
  case=data['cases'][cid]
  if set(case['baseline'])!=criteria or set(case['candidate'])!=criteria:raise ValueError('incomplete criteria: '+cid)
  for criterion in criteria:
   b,c=case['baseline'][criterion],case['candidate'][criterion]
   if type(b) is not int or type(c) is not int or b not in (0,1) or c not in (0,1) or c<b or c!=1:raise ValueError('behavior regression/failure: '+cid+'/'+criterion)
  for side in ['baseline','candidate']:
   evidence=case[side+'_evidence']
   if not evidence:raise ValueError('missing actual run output: '+cid)
   for item in evidence:
    p=(report.parent/item['path']).resolve()
    if not p.is_relative_to(report.parent.resolve()) or not p.is_file() or sha(p)!=item['sha256']:raise ValueError('missing/modified actual run evidence')
   paths={str((report.parent/i['path']).resolve()) for i in evidence}
   run_path=(report.parent/case[side+'_run']).resolve()
   if str(run_path) not in paths:raise ValueError('run metadata missing from evidence')
   run=json.loads(run_path.read_text())
   source_hash=data['candidate_hash'] if side=='candidate' else baseline_hash
   if run.get('runner') not in RUNNERS or run.get('source_hash')!=source_hash or run.get('suite_hash')!=data['suite_hash']:raise ValueError('run environment/source mismatch')
   runners.add(run['runner'])
   records=[r for r in run['cases'] if r['id']==cid]
   if len(records)!=1 or [t['user'] for t in records[0]['turns']]!=specs[cid]['turns']:raise ValueError('actual user turns incomplete')
   for turn in records[0]['turns']:
    reply=(run_path.parent/turn['reply']).resolve();events=(run_path.parent/turn['events']).resolve()
    if str(reply) not in paths or str(events) not in paths or sha(reply)!=turn['sha256']:raise ValueError('actual turn output missing')
    trace=[json.loads(line) for line in events.read_text().splitlines() if line.strip()]
    if not any(e.get('type')==RUNNERS[run['runner']] and not e.get('is_error') for e in trace):raise ValueError('actual model turn did not complete')

 if len(runners)!=1:raise ValueError('baseline and candidate must use the same runner')
 if not data.get('reviewer') or not data.get('limitations'):raise ValueError('review attribution and limits required')
 return data

def build(destination):
 files,links=check_sources();config=json.loads((ROOT/'package.json').read_text());name='professional-agents-kit-v'+config['package'].split('/')[1]
 destination=destination/name
 manifest={k:config[k] for k in ['package','components','extensions']}|{'files':files}
 if destination.exists():
  existing=json.loads((destination/'MANIFEST.json').read_text())
  if existing!=manifest or any(not (destination/r).is_file() or sha(destination/r)!=h for r,h in files.items()):raise ValueError('existing build differs; move failed candidate aside or use new version')
 else:
  for rel in files:
   p=destination/rel;p.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(SOURCE/rel,p)
  (destination/'MANIFEST.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
 return destination,files,links

def main():
 p=argparse.ArgumentParser();p.add_argument('--build-dir',type=Path,required=True);p.add_argument('--publish',action='store_true');p.add_argument('--evidence',type=Path);p.add_argument('--notes',type=Path);a=p.parse_args()
 try:
  package,files,links=build(a.build_dir.resolve())
  env=dict(os.environ,MATRIX_TEST_KIT=str(package))
  for folder in ['tests/legacy','tests','tools']:
   subprocess.run([sys.executable,'-B','-m','unittest','discover','-s',str(ROOT/folder),'-p','test_*.py','-q'],env=env,check=True)
  if a.publish:
   if not a.evidence or not a.notes:raise ValueError('publish requires behavior evidence and release notes')
   check_evidence(a.evidence.resolve(),files)
   subprocess.run([sys.executable,str(ROOT/'tools/release.py'),'build',str(package),'--notes',str(a.notes.resolve()),'--latest'],check=True,env=dict(os.environ,MATRIX_BEHAVIOR_REPORT=str(a.evidence.resolve())))
   distribution=a.build_dir.resolve().parent/'dist';distribution.mkdir(exist_ok=True)
   shutil.copy2(package.with_name(package.name+'.zip'),distribution/(package.name+'.zip'))
  print(json.dumps({'package':str(package),'files':len(files),'links':links,'source_hash':fingerprint(files),'published':a.publish}))
 except (ValueError,OSError,subprocess.CalledProcessError) as e:print(str(e),file=sys.stderr);return 1
 return 0
if __name__=='__main__':raise SystemExit(main())
