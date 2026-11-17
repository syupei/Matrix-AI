import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'evals'))

from operation_evidence import check, snapshot


class OperationEvidenceTest(unittest.TestCase):
    def test_real_product_receipt_and_frozen_failure_examples(self):
        script = ROOT / 'src/professions/product/skills/matrix-product/scripts/product_contract.py'
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / 'product/specs/draft.md'
            path.parent.mkdir(parents=True)
            reply = '本轮已形成局部草稿。[草稿](product/specs/draft.md)'
            call = [sys.executable, str(script), '--root', str(root), 'reply-receipt',
                    '--kind', 'draft', '--path', 'product/specs/draft.md', '--marker', '账号草稿']
            self.assertTrue(check(root, 'draft', reply, [], {}, {})['errors'])
            self.assertTrue(check(root, 'feedback', '已记录本批第一条反馈。', [], {}, {})['errors'])
            self.assertFalse(check(root, 'feedback', '已收到第一条，我等你补充。', [], {}, {})['errors'])
            self.assertEqual(2, subprocess.run(call, capture_output=True).returncode)

            path.write_text('# 账号草稿\n')
            result = subprocess.run(call, capture_output=True, text=True, check=True)
            receipt = json.loads(result.stdout)
            self.assertEqual(receipt['sha256'], hashlib.sha256(path.read_bytes()).hexdigest())
            event = {'type': 'item.completed',
                     'item': {'id': '1', 'type': 'command_execution',
                              'command': ' '.join(call), 'exit_code': 0,
                              'aggregated_output': result.stdout}}
            after = snapshot(root)
            self.assertFalse(check(root, 'draft', reply, [event], {}, after)['errors'])
            self.assertTrue(check(root, 'draft', reply, [event], after, after)['errors'])
            self.assertTrue(check(root, 'draft', reply, [], {}, after)['errors'])
            path.write_text('# 后续变更\n')
            self.assertTrue(check(root, 'draft', reply, [event], {}, snapshot(root))['errors'])

            missing_marker = subprocess.run(call, capture_output=True)
            self.assertEqual(2, missing_marker.returncode)
            call[call.index('--path') + 1] = '../out.md'
            self.assertEqual(2, subprocess.run(call, capture_output=True).returncode)


if __name__ == '__main__':
    unittest.main()
