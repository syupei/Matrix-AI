"""Exercise the installed checkers against accepted and rejected handoff data."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from kit import KIT


class InstalledChecks(unittest.TestCase):
    def run_script(self, script, data, *args):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'input.json'
            path.write_text(json.dumps(data), encoding='utf-8')
            return subprocess.run([sys.executable, str(KIT / script), str(path), *args],
                                  text=True, capture_output=True, check=False)

    def test_billing_draft_can_record_unknowns_but_cannot_handoff(self):
        script = '.agents/skills/matrix-product/scripts/billing_check.py'
        rule = {
            'id': 'R-1', 'kind': 'auto_renew', 'status': 'draft', 'risk': 'F1',
            'source': '试用规则提案', 'financial_impact': '到期扣费',
            'compliance_questions': '核对通知期限', 'notify': '产品决定人',
            'terms': {'trial': '7天', 'interval': '每月', 'amount': '30', 'currency': 'CNY',
                      'cancel_effect': '下周期停止'},
            'pending': {'notice': '待确认提醒时点'},
            'review': {'owner': 'QA', 'method': '固定测试数据'},
            'checks': [{'scenario': '到期前取消', 'expected': '无后续扣费'}],
        }
        data = {'schema': 'matrix-billing/1', 'rules': [rule]}
        self.assertEqual(0, self.run_script(script, data).returncode)
        missing = self.run_script(script, data, '--require-kind', 'charge', '--require-kind', 'refund')
        self.assertEqual(1, missing.returncode)
        self.assertIn('缺少 charge', missing.stderr)
        self.assertIn('缺少 refund', missing.stderr)
        self.assertEqual(0, self.run_script(script, data, '--require-kind', 'auto_renew').returncode)
        self.assertIn('rules[0].status', self.run_script(script, data, '--handoff').stderr)
        rule.update(status='approved', pending={})
        errors = self.run_script(script, data, '--handoff')
        self.assertEqual(1, errors.returncode)
        self.assertIn('rules[0].terms.notice', errors.stderr)
        self.assertIn('rules[0].approval.person', errors.stderr)
        rule['terms']['notice'] = '到期前告知'
        rule['approval'] = {'person': 'SIM', 'quote': 'SIM 批准规则', 'version': 'R-1 v1'}
        self.assertEqual(0, self.run_script(script, data, '--handoff').returncode)

    def test_action_only_recipient_routing(self):
        result = self.run_script('matrix/orchestration/tools/notification_plan.py', [
            {'id': 'A', 'title': '审批', 'action': True, 'recipient': '负责人', 'blocked': 'T-1'},
            {'id': 'B', 'title': '试用', 'action': False, 'recipient': '老板'},
            {'id': 'C', 'title': '核对', 'action': True},
        ])
        self.assertEqual(0, result.returncode, result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(['负责人'], list(data['direct_actions']))
        self.assertEqual(['B'], [i['id'] for i in data['group_summary']])
        self.assertEqual(['C'], [i['id'] for i in data['pending_recipient']])
