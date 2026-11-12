import copy
import importlib.util
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location(
    'registry', Path(__file__).resolve().parents[1] / 'tools/rule_registry.py')
registry = importlib.util.module_from_spec(spec)
spec.loader.exec_module(registry)


class RuleRegistryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.source = Path(temporary.name)
        (self.source / 'rule.md').write_text('# Rule\n')
        self.rule = {'id': 'R', 'file': 'rule.md', 'section': 'Rule', 'registered_in': '0.31',
                     'check': {'criteria': ['checks_fact'], 'tools': []}, 'evidence': {}}
        self.suite = {'cases': [{'id': 'one', 'criteria': ['checks_fact']}]}

    def inspect(self, rules=None):
        return registry.inspect_registry({'rules': rules or [self.rule]}, self.source, self.suite)

    def test_valid_location_and_criterion(self):
        self.assertEqual(self.inspect()['broken'], [])

    def test_missing_section_is_reported(self):
        self.rule['section'] = 'Removed'
        self.assertTrue(self.inspect()['broken'])

    def test_unknown_criterion_is_reported(self):
        self.rule['check']['criteria'] = ['missing']
        self.assertTrue(self.inspect()['broken'])

    def test_source_cannot_escape_inventory_root(self):
        self.rule['file'] = '../outside.md'
        self.assertTrue(self.inspect()['broken'])

    def test_repeated_runs_are_not_three_versions(self):
        self.rule['evidence'] = {f'0.31-run-{n}': {'items': 0} for n in range(4)}
        self.assertEqual(self.inspect()['no_evidence_three_versions'], [])
        self.assertEqual(self.inspect()['history_insufficient'], ['R'])

    def test_missing_evidence_is_checked_across_registry_versions(self):
        other = copy.deepcopy(self.rule)
        other['id'] = 'S'
        other['evidence'] = {v: {'items': 1} for v in ['0.31', '0.32', '0.33']}
        self.assertEqual(self.inspect([self.rule, other])['no_evidence_three_versions'], ['R'])

    def test_newly_registered_rule_is_not_prematurely_stale(self):
        self.rule['registered_in'] = '0.33'
        self.rule['evidence'] = {v: {'items': 0} for v in ['0.31', '0.32', '0.33']}
        self.assertEqual(self.inspect()['no_evidence_three_versions'], [])

    def test_latest_failure_and_unchecked_rule_are_visible(self):
        self.rule['check']['criteria'] = []
        self.rule['evidence']['0.31'] = {'items': 1, 'candidate_zeros': ['one/checks_fact']}
        report = self.inspect()
        self.assertEqual(report['unchecked'], ['R'])
        self.assertEqual(report['latest_failures'][0]['rule'], 'R')
