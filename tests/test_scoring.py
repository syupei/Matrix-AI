"""Blind scoring and second-scorer re-checks (evals/scoring.py)."""
import json, subprocess, sys, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / 'evals/scoring.py'
SUITE = {c['id']: c for c in json.loads((ROOT / 'evals/cases/suite.json').read_text(encoding='utf-8'))['cases']}
CASE = 'copy'


def run(*args):
    r = subprocess.run([sys.executable, '-B', str(TOOL), *args], capture_output=True, text=True)
    if r.returncode:
        raise AssertionError(r.stdout + r.stderr)
    return r.stdout


class ScoringTests(unittest.TestCase):
    def test_blind_material_keeps_ordered_real_tool_facts(self):
        import hashlib
        trace=self.root/'cand'/(CASE+'-0.jsonl')
        events=[{'type':'item.completed','item':{'id':'write','type':'file_change','status':'completed','changes':[{'path':'note.md','kind':'add'}]}},
                {'type':'item.completed','item':{'id':'read','type':'command_execution','command':'save_and_render','exit_code':2,'aggregated_output':'{"revision":1,"resources":{"device":{"exclusive":true}}}'}},
                {'type':'item.completed','item':{'id':'text','type':'agent_message','text':'unsupported claim'}}]
        trace.write_text(''.join(json.dumps(e)+'\n' for e in events))
        run('blind','--baseline',str(self.root/'base'),'--candidate',str(self.root/'cand'),'--cases',CASE,
            '--workspace',str(self.root/'ws'),'--labels',str(self.root/'labels.json'),'--seed','7')
        side=next(k for k,v in self.labels.items() if v=='candidate')
        audit=json.loads((self.root/'ws'/CASE/side/(CASE+'-0-tools.json')).read_text())
        self.assertEqual([r['id'] for r in audit['events']],['write','read'])
        self.assertEqual(audit['events'][1]['exit_code'],2)
        self.assertEqual(audit['raw_sha256'],hashlib.sha256(trace.read_bytes()).hexdigest())
        outputs=json.loads((self.root/'ws'/CASE/side/audit['outputs_file']).read_text())
        self.assertEqual(outputs[0]['line'],2)
        self.assertEqual(json.loads(outputs[0]['output'])['resources']['device']['exclusive'],True)
        self.assertEqual(len(outputs),1)

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        for side in ('base', 'cand'):
            (self.root / side).mkdir()
            (self.root / side / (CASE + '-0.md')).write_text('SIMULATED reply of ' + side)
        (self.root / 'cand' / (CASE + '-artifacts')).mkdir()
        (self.root / 'cand' / (CASE + '-artifacts' ) / 'note.md').write_text('SIMULATED file')
        run('blind', '--baseline', str(self.root / 'base'), '--candidate', str(self.root / 'cand'), '--cases', CASE,
            '--workspace', str(self.root / 'ws'), '--labels', str(self.root / 'labels.json'), '--seed', '7')
        self.labels = json.loads((self.root / 'labels.json').read_text())[CASE]

    def scores(self, name, base, cand, flags=()):
        x, y = (base, cand) if self.labels['X'] == 'baseline' else (cand, base)
        path = self.root / name
        path.write_text(json.dumps({CASE: {'X': x, 'Y': y, 'observations': 'SIMULATED', 'flags': list(flags)}}))
        return path

    def test_blind_copies_hide_the_versions(self):
        self.assertEqual(set(self.labels.values()), {'baseline', 'candidate'})
        text = {l: (self.root / 'ws' / CASE / l / (CASE + '-0.md')).read_text() for l in 'XY'}
        self.assertEqual(text[next(l for l, s in self.labels.items() if s == 'candidate')], 'SIMULATED reply of cand')
        self.assertFalse(any('base' in p.name or 'cand' in p.name for p in (self.root / 'ws').rglob('*')))
        self.assertFalse((self.root / 'ws' / 'labels.json').exists())

    def test_merge_recheck_and_combine(self):
        ks = SUITE[CASE]['criteria']
        base = {k: 1 for k in ks}; base[ks[0]] = 0
        cand = {k: 1 for k in ks}
        first = self.scores('first.json', base, cand, flags=[ks[1]])
        run('merge', '--labels', str(self.root / 'labels.json'), '--scores', str(first), '--out', str(self.root / 'merged.json'))
        merged = json.loads((self.root / 'merged.json').read_text())[CASE]
        self.assertEqual((merged['baseline'], merged['candidate']), (base, cand))
        run('recheck', '--scores', str(self.root / 'merged.json'), '--out', str(self.root / 'recheck.json'))
        listed = json.loads((self.root / 'recheck.json').read_text())[CASE]
        self.assertEqual(listed, sorted([ks[0], ks[1]]))  # a new mechanism (baseline 0, candidate 1) and a flagged call
        second_base = dict(base); second_cand = dict(cand); second_cand[ks[1]] = 0
        second = self.scores('second.json', second_base, second_cand)
        run('merge', '--labels', str(self.root / 'labels.json'), '--scores', str(second), '--out', str(self.root / 'merged2.json'))
        out = run('combine', '--first', str(self.root / 'merged.json'), '--second', str(self.root / 'merged2.json'),
                  '--recheck', str(self.root / 'recheck.json'), '--out', str(self.root / 'combined.json'))
        self.assertEqual(json.loads(out), {'rechecked': 2, 'agreed': 1, 'to_person': 1})
        rows = json.loads((self.root / 'combined.json').read_text())['cases'][CASE]
        self.assertTrue(rows[ks[0]]['agree'])
        self.assertFalse(rows[ks[1]]['agree'])


class Carry(unittest.TestCase):
    def test_only_cases_with_identical_replies_on_both_sides_keep_their_scores(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root, ks = Path(tmp.name), SUITE[CASE]['criteria']
        for side in ('base', 'cand'):
            (root / side).mkdir()
            (root / side / (CASE + '-0.md')).write_text('SIMULATED reply of ' + side)
        sha = lambda f: __import__('hashlib').sha256(f.read_bytes()).hexdigest()
        entry = {s: [{'path': s + '/' + CASE + '-0.md', 'sha256': sha(root / d / (CASE + '-0.md'))}] for s, d in (('baseline', 'base'), ('candidate', 'cand'))}
        previous = {'cases': {CASE: {'baseline': {k: 1 for k in ks}, 'candidate': {k: 1 for k in ks}, 'baseline_evidence': entry['baseline'],
                                     'candidate_evidence': entry['candidate'], 'rechecked': {}}}}
        (root / 'previous.json').write_text(json.dumps(previous))
        args = ['carry', '--previous', str(root / 'previous.json'), '--baseline', str(root / 'base'), '--candidate', str(root / 'cand'), '--out', str(root / 'carried.json')]
        self.assertNotIn(CASE, json.loads(run(*args))['to_score'])
        carried = json.loads((root / 'carried.json').read_text())[CASE]
        self.assertEqual(({k: 1 for k in ks}, [entry['candidate'][0]['sha256']]), (carried['candidate'], carried['carried_from']['replies']['candidate']))
        (root / 'cand' / (CASE + '-0.md')).write_text('SIMULATED new reply')
        self.assertIn(CASE, json.loads(run(*args))['to_score'])



class StageCheckTests(unittest.TestCase):
    """The program part of the stage-line pilot check (evals/codex_comparison.py focus)."""

    def setUp(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location('codex_comparison', ROOT / 'evals/codex_comparison.py')
        self.cc = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.cc)

    def test_first_line_with_an_inferred_basis_is_supported(self):
        line = '**增量构建：共 3 步，当前进行第 2 步「增量循环」｜依据：按你的描述推断，可查 engineering/build/00-工作状态.md｜修正中｜下一步：重跑（研发）**'
        checks = [self.cc.stage_check(line + '\n正文')]
        self.assertTrue(checks[0]['stage_line'] and checks[0]['inferred'])
        self.assertTrue(self.cc.stage_supported(checks, records=False))

    def test_a_stage_line_after_other_text_or_without_a_basis_is_not(self):
        self.assertFalse(self.cc.stage_check('结论先行\n**共 3 步，当前进行第 2 步｜依据：本轮开始**')['stage_line'])
        self.assertFalse(self.cc.stage_check('**共 3 步，当前进行第 2 步「增量循环」｜修正中**')['stage_line'])

    def test_a_record_basis_needs_records_in_the_project(self):
        checks = [self.cc.stage_check('**共 3 步，当前进行第 2 步｜依据：engineering/build/00-工作状态.md｜修正中**')]
        self.assertFalse(self.cc.stage_supported(checks, records=False))
        self.assertTrue(self.cc.stage_supported(checks, records=True))

    def test_later_turns_may_cite_records_the_first_turn_wrote(self):
        first = self.cc.stage_check('**共 7 步，当前进行第 1 步「需求澄清」｜依据：本轮开始｜等你补充**')
        later = self.cc.stage_check('**共 7 步，当前进行第 1 步「需求澄清」｜依据：product/00-工作状态.md｜等你补充**')
        self.assertTrue(self.cc.stage_supported([first, later], records=False))

if __name__ == '__main__':
    unittest.main()
