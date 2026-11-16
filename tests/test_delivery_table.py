import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from kit import KIT


class DeliveryTable(unittest.TestCase):
    def test_installed_tool_checks_coverage_and_renders_existing_links(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / '规格 与文案.md').write_text('Synthetic fixture', encoding='utf-8')
            manifest = root / 'delivery.json'
            rows = [{'profession': 'product', 'requirement': '可观察的验收条件', 'file': '规格 与文案.md'}]
            manifest.write_text(json.dumps(rows), encoding='utf-8')
            command = [sys.executable, str(KIT / 'matrix/base/tools/delivery_table.py'), str(manifest),
                       '--project', str(root), '--require', 'product', '--require', 'content-design']

            result = subprocess.run(command, text=True, capture_output=True)
            self.assertEqual(result.returncode, 1)
            self.assertIn('缺少已交付的专业行：content-design', result.stderr)

            rows.append({'profession': 'content-design', 'requirement': '按情境记录文案键',
                         'file': '规格 与文案.md'})
            manifest.write_text(json.dumps(rows), encoding='utf-8')
            result = subprocess.run(command, text=True, capture_output=True, check=True)
            self.assertIn('| 产品 | 可观察的验收条件 |', result.stdout)
            self.assertIn('| 内容设计与审读 | 按情境记录文案键 |', result.stdout)
            self.assertIn('%20', result.stdout)

            rows[1]['file'] = '../outside.md'
            manifest.write_text(json.dumps(rows), encoding='utf-8')
            result = subprocess.run(command, text=True, capture_output=True)
            self.assertEqual(result.returncode, 1)
            self.assertIn('须为项目内已存在的相对文件', result.stderr)
