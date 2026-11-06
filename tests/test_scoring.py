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


if __name__ == '__main__':
    unittest.main()
