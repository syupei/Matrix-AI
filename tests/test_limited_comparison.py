import hashlib
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest


EVALS = Path(__file__).resolve().parents[1] / 'evals'
sys.path.insert(0, str(EVALS))
import limited_comparison as limited
from run import fingerprint


class LimitedComparisonTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.out, self.kit, self.releases = (self.root / name for name in ('bundle', 'kit', 'releases'))
        self.work = self.out / 'scoring'
        for folder in (self.work, self.kit, self.releases):
            folder.mkdir(parents=True)
        (self.kit / 'file').write_text('synthetic candidate')
        self.files = {'file': limited.sha(self.kit / 'file')}
        prior = {'file': 'b' * 64}
        limited.write(self.kit / 'MANIFEST.json', {'files': self.files})
        limited.write(self.releases / 'previous.json', {'files': prior})
        self.sources = {'candidate': fingerprint(self.kit),
                        'baseline': hashlib.sha256(json.dumps(prior, sort_keys=True).encode()).hexdigest()}
        self.case = {'id': 'one', 'turns': ['synthetic user'], 'criteria': {'one': 'criterion'}}
        self.suite = self.root / 'suite.json'
        limited.write(self.suite, {'cases': [self.case, self.case | {'id': 'omitted'}]})
        for side in limited.SIDES:
            folder = self.out / side / 'one'
            folder.mkdir(parents=True)
            reply = folder / 'one-0.md'
            reply.write_text('synthetic reply')
            (folder / 'one-0.jsonl').write_text('{"type":"turn.completed"}\n')
            limited.write(folder / 'run.json', {
                'suite_hash': limited.sha(self.suite), 'source_hash': self.sources[side],
                'runner': 'codex exec', 'cli_version': 'codex-cli 0.167.0', 'model': 'simulated',
                'effort': 'medium', 'turns': 'fresh', 'cases': [{'id': 'one', 'artifacts': {}, 'turns': [
                    {'user': 'synthetic user', 'reply': reply.name, 'events': 'one-0.jsonl',
                     'sha256': limited.sha(reply)}]}]})
        limited.bind_scoring(self.out, self.work, [self.case], limited.sha(self.suite), 'codex', 'simulated', 7)
        self.set_scores()
        self.args = SimpleNamespace(out=self.out, work=self.work, cases='one', candidate_kit=self.kit,
                                    baseline_ref='previous', reviewer='synthetic test')

    def set_scores(self, disagreement=False):
        first = {'baseline': {'one': 1}, 'candidate': {'one': 1}, 'observations': 'first'}
        cases, listed = {}, {}
        summary = {'rechecked': 0, 'agreed': 0, 'to_person': 0}
        if disagreement:
            first['candidate']['one'] = 0
            listed = {'one': ['one']}
            second = {'baseline': {'one': 1}, 'candidate': {'one': 1}, 'observations': 'second'}
            limited.write(self.work / 'second.json', {'one': second})
            cases = {'one': {'one': {'first': {'baseline': 1, 'candidate': 0},
                                     'second': {'baseline': 1, 'candidate': 1}, 'agree': False}}}
            summary = {'rechecked': 1, 'agreed': 0, 'to_person': 1}
        limited.write(self.work / 'merged.json', {'one': first})
        limited.write(self.work / 'recheck.json', listed)
        limited.write(self.work / 'combined.json', {'summary': summary, 'cases': cases})

    def summarize(self):
        report, _, _, _ = limited.summarize(self.args, self.suite, self.releases)
        return limited.read(report)

    def test_subset_cannot_be_labeled_full_or_used_as_baseline(self):
        report = self.summarize()
        self.assertEqual(report['mode'], 'limited')
        self.assertFalse(report['full_suite_pass'])
        self.assertFalse(report['eligible_as_full_baseline'])
        self.assertEqual(report['selected_cases'], ['one'])
        self.assertEqual(report['not_run_cases'], ['omitted'])
        self.assertEqual(report['candidate_files'], self.files)
        self.assertEqual((self.out / report['suite_snapshot']['path']).read_bytes(), self.suite.read_bytes())
        self.args.cases = 'one,omitted'
        with self.assertRaisesRegex(ValueError, 'strict subset'):
            self.summarize()

    def test_reports_regression_disagreement_without_claiming_pass(self):
        self.set_scores(disagreement=True)
        report = self.summarize()
        self.assertEqual(report['review_status'], 'needs_human_decision')
        self.assertFalse(report['full_suite_pass'])
        self.assertEqual(report['rechecking'], {'rechecked': 1, 'agreed': 0, 'to_person': 1})
        self.assertEqual(report['unresolved_disagreements'][0]['criterion'], 'one')
        self.assertEqual(report['cases']['one']['second_observations'], 'second')
        self.assertEqual(report['observed_regressions'], [])

    def test_missing_case_or_modified_turn_cannot_report(self):
        folder = self.out / 'candidate/one'
        original = (folder / 'run.json').read_bytes()
        (folder / 'run.json').unlink()
        with self.assertRaisesRegex(ValueError, 'missing case run'):
            self.summarize()
        (folder / 'run.json').write_bytes(original)
        (folder / 'one-0.md').write_text('changed reply')
        with self.assertRaisesRegex(ValueError, 'missing or modified turn output'):
            self.summarize()

    def test_wrong_source_or_existing_scores_with_altered_trace_cannot_report(self):
        path = self.out / 'candidate/one/run.json'
        original = limited.read(path)
        limited.write(path, original | {'source_hash': 'wrong'})
        with self.assertRaisesRegex(ValueError, 'run source mismatch'):
            self.summarize()
        limited.write(path, original)
        (path.parent / 'one-0.jsonl').write_text('{"type":"turn.completed","altered":true}\n')
        with self.assertRaisesRegex(ValueError, 'different paired inputs'):
            self.summarize()

    def test_missing_recheck_cannot_be_presented_as_complete(self):
        self.set_scores(disagreement=True)
        (self.work / 'second.json').unlink()
        with self.assertRaisesRegex(ValueError, 'do not cover the required rechecks'):
            self.summarize()


if __name__ == '__main__':
    unittest.main()
