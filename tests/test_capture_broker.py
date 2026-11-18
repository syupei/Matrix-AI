import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
import os


EVALS = Path(__file__).resolve().parents[1] / 'evals'
sys.path.insert(0, str(EVALS))
import capture_broker as capture


class CaptureBrokerTest(unittest.TestCase):
    def test_paths_cannot_escape_or_read_installed_kit(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            for value in ('../outside.html', '/tmp/out.html', 'kit/secret.html', '_evaluation/secret.html'):
                with self.subTest(path=value), self.assertRaises(ValueError):
                    capture.project_file(root, value, {'.html'})
            (root/'design').symlink_to(root.parent, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, 'linked capture path'):
                capture.project_file(root, 'design/out.html', {'.html'})

    def test_output_never_overwrites_existing_or_linked_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            output = root/'design/actual.png'
            capture.publish_new_file(root, output, b'original')
            with self.assertRaises(FileExistsError):
                capture.publish_new_file(root, output, b'changed')
            self.assertEqual(b'original', output.read_bytes())
            output.unlink()
            output.symlink_to(root/'outside')
            with self.assertRaises(FileExistsError):
                capture.publish_new_file(root, output, b'changed')
            self.assertFalse((root/'outside').exists())

    def test_capture_protocol_does_not_accept_browser_code_or_command(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            with self.assertRaisesRegex(ValueError, 'only preview, output'):
                capture.capture_request(root, {'preview': 'design/a.html', 'output': 'design/a.png', 'command': 'sh'})

    def test_source_closure_rejects_hard_linked_host_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            (root/'design').mkdir()
            secret = root/'source.html'
            secret.write_text('host file')
            os.link(secret, root/'design/linked.html')
            with self.assertRaisesRegex(ValueError, 'unlinked regular file'):
                capture.read_project(root, Path('design/linked.html'))


if __name__ == '__main__':
    unittest.main()
