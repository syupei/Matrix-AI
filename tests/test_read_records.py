"""Path/operation regressions; these tests make no claim about model behavior."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'evals'))
from read_records import extract, intersects, changes, record_reads
import subagent_turns

FILES = {'matrix/base/CORE.md':'1', 'matrix/orchestration/tools/pm_tasks.py':'2',
         '.agents/skills/matrix-front-desk/SKILL.md':'3', '.agents/skills/matrix-product/SKILL.md':'4'}
FRONT = '.agents/skills/matrix-front-desk/SKILL.md'


class ReadDomains(unittest.TestCase):
    def shell(self, cmd):
        return extract([{'item':{'type':'command_execution','command':cmd}}], 'codex exec', FILES, project_root='/project')

    def test_absolute_project_reads_and_searches_stay_outside_kit(self):
        for name, inp in [('Read',{'file_path':'/project/product/spec.md'}),
                          ('Grep',{'path':'/project/product','pattern':'rule'}),
                          ('Glob',{'pattern':'/external/**/*.md'})]:
            out=extract([{'type':'tool_use','name':name,'input':inp}], 'claude subagent', FILES, project_root='/project')
            self.assertEqual([],intersects(out,{FRONT:'added'}))
        self.assertEqual([],self.shell('cat /external/kit-other/notes.md')['files'])

    def test_name_observations_only_intersect_tree_changes(self):
        for cmd in ['ls kit/.agents/skills', 'find . -type f | sort', 'rg --files --hidden kit | rg product',
                    'git -C . status --short']:
            reads=self.shell(cmd)
            self.assertFalse(intersects(reads,changes(FILES,dict(FILES,**{FRONT:'new'}))),cmd)
            self.assertTrue(intersects(reads,changes(FILES,dict(FILES,**{FRONT+'.new':'new'}))),cmd)
            self.assertTrue(intersects(reads,changes(FILES,{k:v for k,v in FILES.items() if k!=FRONT})),cmd)

    def test_content_search_and_ordinary_file_reads(self):
        self.assertEqual(['matrix/base/CORE.md'],self.shell('sed -n 1,80p kit/matrix/base/CORE.md')['files'])
        self.assertTrue(intersects(self.shell('rg rule kit'),{FRONT:'modified'}))
        self.assertFalse(intersects(self.shell('rg rule kit/matrix'),{FRONT:'modified'}))
        self.assertFalse(intersects(self.shell("rg '^rule$' kit/matrix"),{FRONT:'modified'}))
        self.assertTrue(intersects(self.shell('echo x | rg --files'),{FRONT:'added'}))

    def test_script_execution_covers_matrix_but_not_unloaded_skills(self):
        reads=self.shell('python3 -I kit/matrix/orchestration/tools/pm_tasks.py --project . --command management/query.json')
        self.assertIn('matrix',reads['scopes'])
        self.assertFalse(intersects(reads,{FRONT:'modified'}))
        self.assertTrue(intersects(reads,{'matrix/base/CORE.md':'modified'}))

    def test_static_cwd_and_paths_resolve(self):
        reads=self.shell('cd kit && cat matrix/base/CORE.md')
        self.assertEqual(['matrix/base/CORE.md'],reads['files'])
        reads=self.shell('cd /external && cat notes.md; cat /project/kit/matrix/base/CORE.md')
        self.assertEqual(['matrix/base/CORE.md'],reads['files'])

    def test_unresolved_dynamic_access_is_conservative(self):
        for cmd in ['cat "$FILE"','eval "$CMD"','cd "$HERE" && cat x','python3 -c "open(path).read()"']:
            self.assertIn('',self.shell(cmd)['scopes'],cmd)

    def test_literal_assignment_and_bounded_loop_do_not_expand_to_whole_kit(self):
        for cmd in ['p=product/spec.md; cat "$p"', 'for f in management/instances/*/profile.md; do cat "$f"; done',
                    'wc -c $(find kit/matrix -type f | sort)']:
            self.assertFalse(intersects(self.shell(cmd),{FRONT:'modified'}),cmd)

    def test_wrapper_heredoc_and_stdin_search(self):
        cmd='/bin/zsh -lc "python3 kit/matrix/orchestration/tools/pm_tasks.py --project . <<\'JSON\'\n{}\nJSON"'
        self.assertFalse(intersects(self.shell(cmd),{FRONT:'modified'}))
        self.assertFalse(intersects(self.shell('ls . | grep kit; echo "$?"'),{FRONT:'modified'}))

    def test_python_paths_resolve_without_executing(self):
        cmd="python3 - <<'PY'\nsrc = '/project/product/spec.md'\ntext = open(src).read()\nPY"
        self.assertFalse(intersects(self.shell(cmd),{FRONT:'modified'}))
        cmd="python3 - <<'PY'\np = 'kit/matrix/base/CORE.md'\nif unknown: p = 'outside'\nopen(p).read()\nPY"
        self.assertIn('',self.shell(cmd)['scopes'])

    def test_python_method_reads_and_dynamic_execution(self):
        reads=self.shell("python3 -c \"from pathlib import Path; Path('kit/matrix/base/CORE.md').open().read()\"")
        self.assertIn('matrix/base/CORE.md',reads['files'])
        for code in ["import os; os.chdir('kit'); open('matrix/base/CORE.md').read()", "exec(code)"]:
            self.assertIn('',self.shell('python3 -c "'+code+'"')['scopes'])

    def test_real_trace_fragments(self):
        path=Path(__file__).with_name('fixtures')/'read-trace-fragments.json'
        for example in json.loads(path.read_text())['examples']:
            reads=extract(example['events'],example['runner'],FILES,project_root='/project')
            self.assertEqual(example['front_content_dependency'],bool(intersects(reads,{FRONT:'modified'})),example['id'])
            if example.get('matrix_content_dependency'):
                self.assertTrue(intersects(reads,{'matrix/base/CORE.md':'modified'}),example['id'])


class TranscriptCollection(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        (self.root/'replies').mkdir();(self.root/'work/case/kit').mkdir(parents=True)
        (self.root/'work/case/kit/MANIFEST.json').write_text(json.dumps({'files':FILES}))
        self.raw=b'{"type":"assistant","message":{"content":[{"type":"tool_use","id":"t","name":"Read","input":{"file_path":"/project/kit/matrix/base/CORE.md"}}]}}\n{"type":"user","message":{"content":[{"type":"tool_result","tool_use_id":"t","content":"original result"}]}}\n'
        (self.root/'raw.jsonl').write_bytes(self.raw)
        (self.root/'replies/case-0.md').write_text('original reply')
        (self.root/'map.json').write_text(json.dumps({'case-0':'raw.jsonl'}))
        self.args=SimpleNamespace(kit=self.root/'work/case/kit',out=self.root,cases='case',transcripts=self.root/'map.json')

    def collect(self):
        with patch.object(subagent_turns,'spec',return_value={'id':'case','turns':['ask']}):
            subagent_turns.collect(self.args)

    def test_original_bytes_and_completion_are_preserved(self):
        self.collect()
        raw=(self.root/'run/case-0.jsonl').read_bytes()
        self.assertTrue(raw.startswith(self.raw))
        end=json.loads(raw.splitlines()[-1]);self.assertEqual('orchestrator',end['recorded_by'])
        self.assertEqual('original reply',(self.root/'run/case-0.md').read_text())
        self.assertEqual('case-0',end['case_turn'])
        context=json.loads((self.root/'run/comparison-context.json').read_text())
        self.assertEqual(FILES,context['candidate_files'])
        self.assertEqual(subagent_turns.SUITE.read_bytes(),(self.root/'run/suite.snapshot.json').read_bytes())

    def test_missing_mapping_or_completion_only_trace_rejected_before_writes(self):
        for mapping, raw in [({},self.raw),({'case-0':'raw.jsonl'},b'{"type":"result"}\n')]:
            (self.root/'map.json').write_text(json.dumps(mapping));(self.root/'raw.jsonl').write_bytes(raw)
            with self.assertRaises(SystemExit):self.collect()
            self.assertFalse((self.root/'run').exists())

    def test_one_transcript_cannot_stand_for_two_fresh_turns(self):
        (self.root/'map.json').write_text(json.dumps({'case-0':'raw.jsonl','case-1':'raw.jsonl'}))
        (self.root/'replies/case-1.md').write_text('second original reply')
        with patch.object(subagent_turns,'spec',return_value={'id':'case','turns':['ask','followup']}):
            with self.assertRaisesRegex(SystemExit,'own transcript'):
                subagent_turns.collect(self.args)
        self.assertFalse((self.root/'run').exists())

    def test_every_turn_needs_tool_evidence(self):
        run=self.root/'run.json'
        (self.root/'a.jsonl').write_bytes(self.raw)
        (self.root/'b.jsonl').write_text('{"type":"result"}\n')
        run.write_text(json.dumps({'runner':'claude subagent'}))
        record={'turns':[{'events':'a.jsonl'},{'events':'b.jsonl'}]}
        self.assertFalse(record_reads(run,record,FILES)['complete'])


class FullReportContext(unittest.TestCase):
    def test_report_assembler_preserves_manifest_and_suite_snapshot(self):
        import codex_comparison as comparison
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);work=root/'scoring';work.mkdir();kit=root/'kit';kit.mkdir()
            (kit/'MANIFEST.json').write_text(json.dumps({'files':FILES}))
            (work/'merged.json').write_text(json.dumps({'one':{'baseline':{'ok':1},'candidate':{'ok':1}}}))
            (work/'combined.json').write_text(json.dumps({'cases':{},'summary':{'rechecked':0}}))
            for side in ['baseline','candidate']:
                folder=root/side/'one';folder.mkdir(parents=True)
                (folder/'run.json').write_text('{}')
            args=SimpleNamespace(out=root,work=work,candidate_kit=kit,baseline_ref='matrix-ai-v0.34',reviewer='SIMULATED')
            with patch.object(comparison,'cases',return_value=[{'id':'one'}]):comparison.assemble(args)
            report=json.loads((root/'comparison.json').read_text())
            self.assertEqual(FILES,report['candidate_files'])
            self.assertEqual(comparison.SUITE.read_bytes(),(root/report['suite_snapshot']['path']).read_bytes())
