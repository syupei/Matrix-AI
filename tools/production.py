#!/usr/bin/env python3
"""Build only canonical consumer sources; require real comparison evidence, or an explicit human waiver, to publish."""
import argparse,hashlib,json,os,re,shutil,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'src'
# The source is grouped by layer; the package (and a project after install) has skills flat in the host's skills
# directory and everything else under matrix/. LAYERS are the source folders; TOP files stay at the package root.
LAYERS=('base','orchestration','professions','knowledge')
TOP={'START.md','BEHAVIOR-CHECKS.md','install.py'}
# Consumer text must stay host-neutral and free of build history (the capability model is quoted source text).
HOST_OR_HISTORY=re.compile(r'[Cc]odex|[Oo]pen[Aa][Ii]|[Cc]laude|[Aa]nthropic|functions\.|request_user_input|mcp__|~/|试验|来源项目|原项目|旧版|旧项目|此前版本|历史版本|本版新增|\bv0\.\d+|[A-Z]+-(?:DEC|Q)-\d{3}|COPY-00\d|STRUCT-00\d')
TEXT_EXEMPT=('.agents/skills/matrix-product-capability-model/standards/',)
RUNNERS={'codex exec':'turn.completed','claude -p':'result','claude subagent':'result'}
PRIVATE=re.compile(r'DFW(?:[-_ ]TEST)?|EC[-_ ](?:TEST|CHINA)|EAST[-_ ]CHINA|/Users/|[A-Z]:\\Users\\',re.I)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def package_path(rel):
 """Where a source file lands in the package: a skill folder goes to .agents/skills/, the rest under matrix/."""
 if rel in TOP:return rel
 parts=rel.split('/')
 if parts[0] in ('base','orchestration','knowledge') and len(parts)>2 and parts[1]=='skills':return '.agents/skills/'+'/'.join(parts[2:])
 if parts[0]=='professions' and len(parts)>3 and parts[2]=='skills':return '.agents/skills/'+'/'.join(parts[3:])
 if parts[0] in LAYERS:return 'matrix/'+rel
 raise ValueError('non-runtime source: '+rel)
def layout():
 """Package path -> source file, for every runtime source file."""
 out={}
 for p in sorted(SOURCE.rglob('*')):
  if not p.is_file():continue
  rel=str(p.relative_to(SOURCE))
  if '__pycache__' in p.parts or p.name in ['.DS_Store','MANIFEST.json']:continue
  if p.name.startswith('test_') or 'tests' in p.parts:raise ValueError('maintainer test in runtime source: '+rel)
  if p.is_symlink():raise ValueError('non-runtime source: '+rel)
  dest=package_path(rel)
  if dest in out:raise ValueError('two sources for one package path: '+dest)
  out[dest]=p
 return out
def source_files():
 files={}
 for rel,p in layout().items():
  if p.suffix in {'.md','.py','.html','.json','.yaml','.txt'} and PRIVATE.search(p.read_text()):raise ValueError('internal identity in package: '+rel)
  files[rel]=sha(p)
 return files

# The stage-line template is the one rule kept in two places: CORE §6, which every model reads, and USER-INTERACTION §7,
# which explains it. Models that follow only what they are sure to read copy the CORE line, so the two must not drift.
STAGE_LINE=re.compile(r'^\*\*(\{流程\}：[^\n]*)\*\*$',re.M)
def stage_template_errors(core,interaction):
 section=interaction.split('\n## 7.',1)[1] if '\n## 7.' in interaction else ''
 m=STAGE_LINE.search(section.split('\n## ',1)[0])
 if not m:return ['USER-INTERACTION §7 has no stage-line template']
 return [] if '**'+m.group(1)+'**' in core else ['stage-line template in CORE differs from USER-INTERACTION §7']
# Every skill entry with a startup list points at that line in its first step: entries are always read whole.
STAGE_POINTER='每轮回复的第一行写阶段行'
def entry_stage_errors(rel,text):
 if '## 启动' not in text:return []
 m=re.search(r'^1\. .*$',text.split('## 启动',1)[1].split('\n## ',1)[0],re.M)
 return [] if m and STAGE_POINTER in m.group(0) else ['startup step 1 does not point at the stage line: '+rel]
def fingerprint(files):return hashlib.sha256(json.dumps(files,sort_keys=True).encode()).hexdigest()
def guidance_budget(rel):
 if rel.startswith(TEXT_EXEMPT) or not rel.endswith('.md'):return None
 name=Path(rel).name
 if name=='SKILL.md':return 3500
 if name=='GUIDANCE-INDEX.md':return 2500 if rel=='matrix/base/GUIDANCE-INDEX.md' else 1500
 return 3000

def guidance_budget_errors(documents,exceptions):
 errors=[]
 for rel,text in documents.items():
  limit=guidance_budget(rel)
  if limit is None:continue
  exception=exceptions.get(rel)
  if exception is not None:
   if not isinstance(exception,dict) or not isinstance(exception.get('reason'),str) or not exception['reason'].strip() or type(exception.get('max_characters')) is not int or exception['max_characters']<=limit:
    errors.append('invalid guidance budget exception: '+rel);continue
   limit=exception['max_characters']
  if len(text)>limit:errors.append(f'guidance exceeds {limit} characters: {rel} ({len(text)})')
 for rel in exceptions:
  if rel not in documents or guidance_budget(rel) is None:errors.append('stale guidance budget exception: '+rel)
 return errors

def check_sources():
 files=source_files();src=layout();errors=[];links=0
 dirs={str(Path(r).parent) for r in files}
 dirs|={str(Path(d).parents[i]) for d in list(dirs) for i in range(len(Path(d).parts))}
 for rel in files:
  p=src[rel]
  if p.name=='SKILL.md' and len(p.read_text())>3500:errors.append('entry exceeds 3500 characters: '+rel)
  if p.suffix in {'.md','.html'} and not rel.startswith(TEXT_EXEMPT):
   text=p.read_text().replace('.claude/skills','.<host>/skills') if rel=='START.md' else p.read_text()
   for m in HOST_OR_HISTORY.finditer(text):errors.append(f'host name or build history in consumer text: {rel}: {m.group(0)}')
  if p.suffix=='.md':
   # Links are written for the installed layout, so they are checked against package paths.
   for href in re.findall(r'\]\(([^)]+)\)',p.read_text()):
    path=href.split('#')[0]
    if not path or '://' in path or path.startswith('mailto:'):continue
    dest=os.path.normpath(os.path.join(os.path.dirname(rel),path))
    if dest.startswith('..') or (dest not in files and dest not in dirs):errors.append('broken link: '+rel+' -> '+href)
    links+=1
 errors+=[e for rel in files if src[rel].name=='SKILL.md' for e in entry_stage_errors(rel,src[rel].read_text())]
 errors+=stage_template_errors(src['matrix/base/CORE.md'].read_text(),src['matrix/base/USER-INTERACTION.md'].read_text())
 errors+=guidance_budget_errors({rel:p.read_text() for rel,p in src.items() if p.suffix=='.md'},json.loads((ROOT/'docs/guidance-budget-exceptions.json').read_text()))
 if errors:raise ValueError('\n'.join(errors))
 return files,links

def waived_release(tag):
 catalog=ROOT/'releases.json'
 entry=next((e for e in json.loads(catalog.read_text())['releases'] if e['tag']==tag),{}) if catalog.exists() else {}
 return bool((entry.get('behavior_evidence') or {}).get('waived'))

def check_carried(report,cid,case,turns):
 # Scores carried from a previous comparison stand only for byte-identical replies, unchanged with their re-checks.
 ref=case.get('carried_from')
 if not ref:return
 prev=(report.parent/ref.get('path','')).resolve()
 if not prev.is_relative_to(report.parent.resolve()) or not prev.is_file() or sha(prev)!=ref.get('sha256'):raise ValueError('carried scores need the previous comparison: '+cid)
 old=json.loads(prev.read_text())['cases'].get(cid) or {}
 for side in ['baseline','candidate']:
  then=(ref.get('replies') or {}).get(side)
  if not then or turns[side]!=then:raise ValueError('carried scores for a changed reply: '+cid)
  if not set(then)<={i['sha256'] for i in old.get(side+'_evidence',[])}:raise ValueError('carried replies are not in the previous comparison: '+cid)
 if any(case.get(k)!=old.get(k) for k in ['baseline','candidate','rechecked','rescored']):raise ValueError('carried scores changed: '+cid)

def check_recheck(cid,case,criteria):
 """A second, blind scorer re-checks the scores that decide the gate or a new mechanism, and flagged borderline calls;
 a disagreement stands only with a person's recorded decision."""
 b,c=case['baseline'],case['candidate'];rechecked=case.get('rechecked',{})
 need={k for k in criteria if c[k]==0 or c[k]<b[k] or (b[k]==0 and c[k]==1)}|set(case.get('flags',[]))
 decided=case.get('rescored') or {}
 person={ch['criterion'] for ch in decided.get('changes',[])}|set(decided.get('kept',[])) if decided.get('decided_by')=='user' else set()
 for k in sorted(need):
  r=rechecked.get(k)
  if not r or set(r)!={'first','second','agree'}:raise ValueError('second-scorer re-check missing: '+cid+'/'+k)
  if r['agree']!=(r['first']==r['second']):raise ValueError('re-check agreement misstated: '+cid+'/'+k)
  final={'baseline':b[k],'candidate':c[k]}
  if r['agree'] and final!=r['first'] and k not in person:raise ValueError('score changed after agreeing re-check: '+cid+'/'+k)
  if not r['agree'] and k not in person:raise ValueError('scorers disagree without a person\'s decision: '+cid+'/'+k)

def check_evidence(report,files):
 data=json.loads(report.read_text())
 if data.get('candidate_hash')!=fingerprint(files):raise ValueError('behavior evidence belongs to different source')
 suite=ROOT/'evals/cases/suite.json'
 if data.get('suite_hash')!=sha(suite):raise ValueError('behavior suite changed')
 specs={c['id']:c for c in json.loads(suite.read_text())['cases']}
 expected={cid:set(c['criteria']) for cid,c in specs.items()}
 baseline=json.loads((ROOT/'package.json').read_text())['baseline']
 if data.get('baseline_ref')!=baseline:raise ValueError('wrong baseline version')
 # A release published under a waiver had no full comparison, so it cannot be the baseline of another.
 if waived_release(baseline):raise ValueError('baseline '+baseline+' was published under a waiver; compare against a release with full behavior evidence')
 prior=ROOT/'release-manifests'/(baseline+'.json')
 if not prior.exists():prior=ROOT/'packages'/baseline/'MANIFEST.json'
 base_files=json.loads(prior.read_text())['files'];baseline_hash=fingerprint(base_files)
 if data.get('baseline_hash')!=baseline_hash:raise ValueError('wrong baseline source')
 if set(data.get('cases',{}))!=set(expected):raise ValueError('missing/extra behavior cases')
 runners=set()
 for cid,criteria in expected.items():
  case=data['cases'][cid]
  if set(case['baseline'])!=criteria or set(case['candidate'])!=criteria:raise ValueError('incomplete criteria: '+cid)
  for criterion in criteria:
   b,c=case['baseline'][criterion],case['candidate'][criterion]
   if type(b) is not int or type(c) is not int or b not in (0,1) or c not in (0,1) or c<b or c!=1:raise ValueError('behavior regression/failure: '+cid+'/'+criterion)
  check_recheck(cid,case,criteria)
  turns={}
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
   runners.add((run['runner'],run.get('model'),run.get('effort')))  # one runner, model and effort for both versions
   records=[r for r in run['cases'] if r['id']==cid]
   if len(records)!=1 or [t['user'] for t in records[0]['turns']]!=specs[cid]['turns']:raise ValueError('actual user turns incomplete')
   if specs[cid].get('fixture') and records[0].get('fixture_sha256')!=specs[cid].get('fixture_sha256'):
    # A baseline run carried from the baseline's own earlier run may keep the fixture it was made with, when a check
    # showed that both fixture versions build the same project for that kit.
    eq=records[0].get('fixture_equivalent') or {}
    same=side=='baseline' and records[0].get('carried_from') and eq.get('suite_fixture_sha256')==specs[cid]['fixture_sha256'] and eq.get('old_fixture_sha256')==records[0].get('fixture_sha256') and eq.get('old_digest') and eq.get('old_digest')==eq.get('new_digest')
    if not same:raise ValueError('run fixture mismatch: '+cid)
   reuse=records[0].get('reused_from')
   if reuse:
    # Carried over from the previous release's run: allowed only while every file the case read is unchanged. A run
    # without a record of its reads counts the role's files and the common rules as read.
    if side!='candidate' or reuse.get('source_hash')!=baseline_hash:raise ValueError('reused evidence must come from the baseline release: '+cid)
    read=records[0].get('read_files')
    if read is None:
     prefix='.agents/skills/'+str(records[0].get('role',''))+'/'
     if not records[0].get('role') or not any(k.startswith(prefix) for k in files):raise ValueError('reused evidence for a changed role: '+cid)
     read=[k for k in set(base_files)|set(files) if k.startswith(prefix) or k.startswith('matrix/base/')]
    changed=sorted(k for k in read if base_files.get(k)!=files.get(k))
    if not read or changed:raise ValueError('reused evidence for a changed role or read file: '+cid+' ('+', '.join(changed[:5])+')')
   turns[side]=[t['sha256'] for t in records[0]['turns']]
   for turn in records[0]['turns']:
    reply=(run_path.parent/turn['reply']).resolve();events=(run_path.parent/turn['events']).resolve()
    if str(reply) not in paths or str(events) not in paths or sha(reply)!=turn['sha256']:raise ValueError('actual turn output missing')
    trace=[json.loads(line) for line in events.read_text().splitlines() if line.strip()]
    if not any(e.get('type')==RUNNERS[run['runner']] and not e.get('is_error') for e in trace):raise ValueError('actual model turn did not complete')
  check_carried(report,cid,case,turns)

 if len(runners)!=1:raise ValueError('baseline and candidate must use the same runner, model and effort')
 if not data.get('reviewer') or not data.get('limitations'):raise ValueError('review attribution and limits required')
 return data

def release_name(config):
 name,version=config['package'].split('/');return name+'-v'+version

WAIVER_FIELDS=('authorized_by','date','authorization','scope','existing_evidence','limitations')
def check_waiver(path,files):
 # Only an explicit human authorization to skip verification waives the comparison; a plain request to publish does not.
 data=json.loads(path.read_text());config=json.loads((ROOT/'package.json').read_text())
 if data.get('package')!=release_name(config):raise ValueError('waiver names a different version')
 if data.get('source_hash')!=fingerprint(files):raise ValueError('waiver belongs to different source')
 if any(not data.get(k) for k in WAIVER_FIELDS):raise ValueError('waiver requires '+', '.join(WAIVER_FIELDS))
 return data

def build(destination):
 files,links=check_sources();config=json.loads((ROOT/'package.json').read_text());name=release_name(config);src=layout()
 destination=destination/name
 manifest={k:config[k] for k in ['package','components','extensions']}|{'files':files}
 if destination.exists():
  existing=json.loads((destination/'MANIFEST.json').read_text())
  if existing!=manifest or any(not (destination/r).is_file() or sha(destination/r)!=h for r,h in files.items()):raise ValueError('existing build differs; move failed candidate aside or use new version')
 else:
  for rel in files:
   p=destination/rel;p.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src[rel],p)
  (destination/'MANIFEST.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
 return destination,files,links

def main():
 p=argparse.ArgumentParser();p.add_argument('--build-dir',type=Path,required=True);p.add_argument('--publish',action='store_true');p.add_argument('--evidence',type=Path);p.add_argument('--waiver',type=Path);p.add_argument('--notes',type=Path);a=p.parse_args()
 try:
  package,files,links=build(a.build_dir.resolve())
  env=dict(os.environ,MATRIX_TEST_KIT=str(package))
  for folder in ['tests/legacy','tests','tools']:
   subprocess.run([sys.executable,'-B','-m','unittest','discover','-s',str(ROOT/folder),'-p','test_*.py','-q'],env=env,check=True)
  if a.publish:
   if not a.notes or bool(a.evidence)==bool(a.waiver):raise ValueError('publish requires release notes and either behavior evidence or an explicit human waiver')
   release_env={k:v for k,v in os.environ.items() if k not in ('MATRIX_BEHAVIOR_REPORT','MATRIX_BEHAVIOR_WAIVER')}
   if a.waiver:check_waiver(a.waiver.resolve(),files);release_env['MATRIX_BEHAVIOR_WAIVER']=str(a.waiver.resolve())
   else:check_evidence(a.evidence.resolve(),files);release_env['MATRIX_BEHAVIOR_REPORT']=str(a.evidence.resolve())
   subprocess.run([sys.executable,str(ROOT/'tools/release.py'),'build',str(package),'--notes',str(a.notes.resolve()),'--latest'],check=True,env=release_env)
   distribution=a.build_dir.resolve().parent/'dist';distribution.mkdir(exist_ok=True)
   shutil.copy2(package.with_name(package.name+'.zip'),distribution/(package.name+'.zip'))
  print(json.dumps({'package':str(package),'files':len(files),'links':links,'source_hash':fingerprint(files),'published':a.publish}))
 except (ValueError,OSError,subprocess.CalledProcessError) as e:print(str(e),file=sys.stderr);return 1
 return 0
if __name__=='__main__':raise SystemExit(main())
