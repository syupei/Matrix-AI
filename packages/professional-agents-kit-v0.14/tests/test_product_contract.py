"""Behavioral checks in disposable projects; no real user approval or business data."""
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / '.agents/skills/product-agent/scripts/product_contract.py'
spec = importlib.util.spec_from_file_location('product_contract', SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class ContractTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='product-contract-test-')
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.source = 'product/spec.md'
        self.baseline = 'product/baselines/b1.json'
        self.meta = {'format': mod.FORMAT, 'revision': 'v1', 'items': [
            {'id': 'R-1', 'kind': 'requirement', 'heading': '## 留言规则', 'audiences': ['design']},
            {'id': 'AC-1', 'kind': 'acceptance', 'heading': '## 留言验收',
             'verify_at': 'implementation', 'refs': [self.source + '#R-1'], 'audiences': ['qa']},
            {'id': 'SM-1', 'kind': 'outcome', 'heading': '## 实际效果', 'verify_at': 'post_launch'},
        ]}
        self.body = '# 产品\n\n## 留言规则\n提交后保留用户原始文字。\n\n## 留言验收\n提交成功后显示相同留言。\n\n## 实际效果\n实际回应情况；目标待研究，不能猜。\n'
        self.source_write()
        self.capture()

    def put(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')

    def source_write(self):
        self.put(self.source, self.body + '\n```product-contract\n' + json.dumps(self.meta, ensure_ascii=False) + '\n```\n')

    def capture(self):
        self.put(self.baseline, mod.json_text(mod.capture(self.root, [self.source])))

    def check(self, stage='product', receipt=None):
        return mod.check(self.root, self.baseline, stage, receipt)

    def codes(self, report):
        return {i['code'] for i in report['issues']}

    def receipt(self):
        receipt = mod.draft_receipt(self.root, self.baseline)
        receipt.update(checker='fixture-only', checked_at='2026-09-21T10:00:00+08:00', stage='implementation')
        self.put('evidence/test.md', 'Simulated implementation evidence, not a live test.')
        receipt['results'][0].update(status='passed', method='implementation', evidence=[{
            'path': 'evidence/test.md', 'sha256': mod.digest((self.root / 'evidence/test.md').read_bytes())}])
        return receipt

    def save_receipt(self, receipt):
        self.put('checks/result.json', mod.json_text(receipt))
        return 'checks/result.json'

    def test_product_handoff_does_not_require_unbuilt_implementation(self):
        result = self.check()
        self.assertTrue(result['mechanical_checks_passed'])
        self.assertEqual(self.codes(result), {'downstream_verification'})

    def test_implementation_claim_requires_actual_checks(self):
        self.assertFalse(self.check('implementation')['mechanical_checks_passed'])
        self.assertIn('pending_verification', self.codes(self.check('implementation')))

    def test_valid_implementation_evidence_leaves_launch_metrics_pending(self):
        name = self.save_receipt(self.receipt())
        result = self.check('implementation', name)
        self.assertTrue(result['mechanical_checks_passed'])
        self.assertIn('downstream_verification', self.codes(result))

    def test_outcome_requires_measurement_only_at_later_stage(self):
        name = self.save_receipt(self.receipt())
        self.assertFalse(self.check('post_launch', name)['mechanical_checks_passed'])

    def test_draft_never_marks_any_item_passed(self):
        result = mod.draft_receipt(self.root, self.baseline)
        self.assertTrue(all(r['status'] == 'not_checked' and not r['evidence'] for r in result['results']))

    def test_source_edit_without_revision_change_is_detected(self):
        self.body = self.body.replace('原始文字', '文字及时间')
        self.source_write()
        result = self.check()
        self.assertIn('stale_source', self.codes(result))
        self.assertIn(self.source + '#R-1', result['changed_items'])
        self.assertIn(self.source + '#AC-1', result['affected_items'])
        self.assertNotIn(self.source + '#SM-1', result['affected_items'])

    def test_line_movement_does_not_mark_unchanged_item_as_semantic_change(self):
        self.body = '\n\n' + self.body
        self.source_write()
        result = self.check()
        self.assertIn('stale_source', self.codes(result))
        self.assertEqual(result['changed_items'], [])

    def test_removed_item_and_old_inbound_reference_are_reported(self):
        self.meta['items'].pop(0)
        self.source_write()
        result = self.check()
        self.assertIn('missing_reference', self.codes(result))
        self.assertIn(self.source + '#AC-1', result['affected_items'])

    def test_new_item_is_detected(self):
        self.meta['items'].append({'id': 'C-1', 'kind': 'context', 'heading': '# 产品'})
        self.source_write()
        self.assertIn(self.source + '#C-1', self.check()['changed_items'])

    def test_uncovered_requirement_blocks_snapshot(self):
        self.meta['items'][1]['refs'] = []
        self.source_write()
        with self.assertRaisesRegex(ValueError, 'uncovered_requirement'):
            mod.capture(self.root, [self.source])

    def test_documented_nonapplicability_is_allowed(self):
        self.meta['items'][0].update(coverage='not_applicable', reason='仅术语约束，当前无需行为判据；需专业确认')
        self.meta['items'][1]['refs'] = []
        self.source_write()
        self.assertTrue(mod.capture(self.root, [self.source]))

    def test_nonapplicability_requires_reason(self):
        self.meta['items'][0]['coverage'] = 'not_applicable'
        self.source_write()
        with self.assertRaisesRegex(ValueError, '理由'):
            mod.capture(self.root, [self.source])

    def test_duplicate_item_is_rejected(self):
        self.meta['items'].append(copy.deepcopy(self.meta['items'][0]))
        self.source_write()
        with self.assertRaisesRegex(ValueError, '重复条目'):
            mod.capture(self.root, [self.source])

    def test_dangling_reference_is_rejected(self):
        self.meta['items'][1]['refs'].append('product/missing.md#R-2')
        self.source_write()
        with self.assertRaisesRegex(ValueError, 'missing_reference'):
            mod.capture(self.root, [self.source])

    def test_same_id_in_two_documents_is_namespaced(self):
        second = 'product/other.md'
        self.put(second, '## Context\nAnother object\n```product-contract\n' + json.dumps({
            'format': mod.FORMAT, 'revision': '1',
            'items': [{'id': 'R-1', 'kind': 'context', 'heading': '## Context'}]}) + '\n```\n')
        data = mod.capture(self.root, [self.source, second])
        self.assertIn(second + '#R-1', data['items'])
        self.assertIn(self.source + '#R-1', data['items'])

    def test_duplicate_heading_is_rejected(self):
        self.body += '\n## 留言规则\nDuplicate\n'
        self.source_write()
        with self.assertRaisesRegex(ValueError, '不唯一'):
            mod.capture(self.root, [self.source])

    def test_code_sample_headings_are_not_real_sections(self):
        self.body = '```markdown\n## 留言规则\nsample\n```\n' + self.body
        self.source_write()
        self.assertTrue(mod.capture(self.root, [self.source]))

    def test_empty_registered_section_is_rejected(self):
        self.body = self.body.replace('提交成功后显示相同留言。', '')
        self.source_write()
        with self.assertRaisesRegex(ValueError, '正文为空'):
            mod.capture(self.root, [self.source])

    def test_unknown_metadata_cannot_override_source_path(self):
        self.meta['items'][0]['source'] = '../../other'
        self.source_write()
        with self.assertRaisesRegex(ValueError, '未知条目字段'):
            mod.capture(self.root, [self.source])

    def test_missing_source_reports_failure_without_overwriting(self):
        (self.root / self.source).unlink()
        self.assertIn('invalid_source', self.codes(self.check()))

    def test_pass_without_evidence_is_rejected(self):
        receipt = self.receipt()
        receipt['results'][0]['evidence'] = []
        self.assertIn('missing_evidence', self.codes(self.check('implementation', self.save_receipt(receipt))))

    def test_external_url_alone_is_not_evidence(self):
        receipt = self.receipt()
        receipt['results'][0]['evidence'] = [{'url': 'https://example.com/results'}]
        self.assertIn('missing_evidence', self.codes(self.check('implementation', self.save_receipt(receipt))))

    def test_changed_evidence_is_rejected(self):
        receipt = self.receipt()
        self.put('evidence/test.md', 'changed result')
        self.assertIn('invalid_evidence', self.codes(self.check('implementation', self.save_receipt(receipt))))

    def test_reasoning_cannot_pass_implementation(self):
        receipt = self.receipt()
        receipt['results'][0]['method'] = 'reasoning'
        self.assertIn('invalid_verification_method', self.codes(self.check('implementation', self.save_receipt(receipt))))

    def test_early_stage_cannot_pass_implementation(self):
        receipt = self.receipt()
        receipt['stage'] = 'product'
        self.assertIn('invalid_verification_method', self.codes(self.check('implementation', self.save_receipt(receipt))))

    def test_stale_receipt_is_rejected_even_with_valid_evidence(self):
        receipt = self.receipt()
        receipt['baseline_sha256'] = '0' * 64
        self.assertIn('stale_receipt', self.codes(self.check('implementation', self.save_receipt(receipt))))

    def test_duplicate_results_are_not_silently_overwritten(self):
        receipt = self.receipt()
        receipt['results'].append(copy.deepcopy(receipt['results'][0]))
        with self.assertRaisesRegex(ValueError, '重复'):
            self.check('implementation', self.save_receipt(receipt))

    def test_unknown_checked_item_is_reported(self):
        receipt = self.receipt()
        receipt['results'][0]['item'] = self.source + '#AC-999'
        self.assertIn('unknown_checked_item', self.codes(self.check('implementation', self.save_receipt(receipt))))

    def test_failed_check_blocks_even_with_evidence(self):
        receipt = self.receipt()
        receipt['results'][0]['status'] = 'failed'
        self.assertIn('failed_check', self.codes(self.check('implementation', self.save_receipt(receipt))))

    def test_readonly_check_keeps_all_files_unchanged(self):
        before = {str(p): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        self.check()
        self.assertEqual(before, {str(p): p.read_bytes() for p in self.root.rglob('*') if p.is_file()})

    def test_handoff_includes_referenced_sources_for_recipient(self):
        text = mod.handoff(self.root, self.baseline, 'qa')
        self.assertIn('提交后保留用户原始文字。', text)
        self.assertIn('提交成功后显示相同留言。', text)
        self.assertNotIn('```product-contract', text)

    def test_stale_handoff_is_refused(self):
        self.body += '\nNew unregistered note.\n'
        self.source_write()
        with self.assertRaisesRegex(ValueError, '源已变化'):
            mod.handoff(self.root, self.baseline, 'design')

    def test_existing_output_is_never_overwritten(self):
        self.put('human.md', 'human edit')
        with self.assertRaisesRegex(ValueError, '已存在'):
            mod.write_new(self.root, 'human.md', 'replace')
        self.assertEqual((self.root / 'human.md').read_text(), 'human edit')

    def test_paths_outside_root_are_rejected(self):
        for path in ['../outside.md', '/tmp/outside.md', 'product/../outside.md']:
            with self.subTest(path=path), self.assertRaises(ValueError):
                mod.location(self.root, path)

    def test_symlink_evidence_is_not_followed(self):
        receipt = self.receipt()
        (self.root / 'evidence/link.md').symlink_to(self.root / 'evidence/test.md')
        receipt['results'][0]['evidence'][0]['path'] = 'evidence/link.md'
        self.assertIn('invalid_evidence', self.codes(self.check('implementation', self.save_receipt(receipt))))

    def test_cli_exit_codes_and_report_are_actionable(self):
        base = [sys.executable, str(SCRIPT), '--root', str(self.root), 'check', '--baseline', self.baseline, '--json']
        good = subprocess.run(base, capture_output=True, text=True)
        self.assertEqual(good.returncode, 0, good.stderr)
        self.assertTrue(json.loads(good.stdout)['mechanical_checks_passed'])
        waiting = subprocess.run(base + ['--stage', 'implementation'], capture_output=True, text=True)
        self.assertEqual(waiting.returncode, 1)
        bad = subprocess.run(base + ['--receipt', 'missing.json'], capture_output=True, text=True)
        self.assertEqual(bad.returncode, 2)

    def test_cli_capture_draft_handoff_and_no_overwrite(self):
        base = [sys.executable, str(SCRIPT), '--root', str(self.root)]
        commands = [
            ['capture', '--source', self.source, '--output', 'product/baselines/cli.json'],
            ['draft', '--baseline', 'product/baselines/cli.json', '--output', 'checks/cli.json'],
            ['handoff', '--baseline', 'product/baselines/cli.json', '--role', 'qa', '--output', 'handoff/qa.md'],
        ]
        for command in commands:
            result = subprocess.run(base + command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('提交成功后显示相同留言。', (self.root / 'handoff/qa.md').read_text())
        before = (self.root / 'handoff/qa.md').read_bytes()
        again = subprocess.run(base + commands[-1], capture_output=True, text=True)
        self.assertEqual(again.returncode, 2)
        self.assertEqual(before, (self.root / 'handoff/qa.md').read_bytes())

    def test_duplicate_json_keys_are_rejected(self):
        path = self.root / self.source
        path.write_text(path.read_text().replace('"revision": "v1"', '"revision": "v1", "revision": "v2"'))
        with self.assertRaisesRegex(ValueError, '重复 JSON 字段'):
            mod.capture(self.root, [self.source])


if __name__ == '__main__':
    unittest.main()
