import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

spec = importlib.util.spec_from_file_location('release', Path(__file__).with_name('release.py'))
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / 'test-kit-v0.1'
        self.source.mkdir()
        (self.source / 'sample.md').write_text('verified content')
        self.expected = {'sample.md': release.sha(self.source / 'sample.md')}
        (self.source / 'MANIFEST.json').write_text(json.dumps({'files': self.expected}))
        self.zip = self.root / 'test-kit-v0.1.zip'

    def test_manifest_mismatch_stops_before_archive(self):
        (self.source / 'sample.md').write_text('changed')
        with self.assertRaises(ValueError):
            release.build_archive(self.source, self.zip)
        self.assertFalse(self.zip.exists())

    def test_build_and_repeat_preserve_archive(self):
        expected = release.build_archive(self.source, self.zip)
        digest = release.sha(self.zip)
        release.build_archive(self.source, self.zip)
        self.assertEqual(digest, release.sha(self.zip))
        release.verify_archive(self.zip, self.source.name, expected)

    def test_existing_different_zip_is_not_overwritten(self):
        with zipfile.ZipFile(self.zip, 'w') as z:
            z.writestr('wrong/file', 'other content')
        digest = release.sha(self.zip)
        with self.assertRaises(ValueError):
            release.build_archive(self.source, self.zip)
        self.assertEqual(digest, release.sha(self.zip))

    def test_unlisted_private_files_are_excluded(self):
        (self.source / 'MEMORY.md').write_text('not published')
        release.build_archive(self.source, self.zip)
        with zipfile.ZipFile(self.zip) as z:
            self.assertFalse(any(n.endswith('MEMORY.md') for n in z.namelist()))

    def test_listed_private_file_is_rejected(self):
        (self.source / 'MEMORY.md').write_text('not published')
        (self.source / 'MANIFEST.json').write_text(json.dumps({'files': {'MEMORY.md': release.sha(self.source / 'MEMORY.md')}}))
        with self.assertRaises(ValueError):
            release.package_files(self.source)

    def test_manifest_traversal_is_rejected(self):
        (self.root / 'outside').write_text('outside')
        (self.source / 'MANIFEST.json').write_text(json.dumps({'files': {'../outside': release.sha(self.root / 'outside')}}))
        with self.assertRaises(ValueError):
            release.package_files(self.source)

    def test_symlink_is_rejected(self):
        (self.root / 'outside').write_text('verified content')
        (self.source / 'link').symlink_to(self.root / 'outside')
        (self.source / 'MANIFEST.json').write_text(json.dumps({'files': {'link': release.sha(self.root / 'outside')}}))
        with self.assertRaises(ValueError):
            release.package_files(self.source)

    def test_existing_snapshot_cannot_be_replaced(self):
        expected = release.package_files(self.source)
        target = self.root / 'snapshot'
        release.copy_snapshot(self.source, target, expected)
        (target / 'sample.md').write_text('human change')
        with self.assertRaises(ValueError):
            release.copy_snapshot(self.source, target, expected)

    def test_upload_failure_does_not_publish_draft(self):
        release.build_archive(self.source, self.zip)
        entry = {'tag': self.source.name, 'title': 'test', 'notes': 'note.md', 'assets': [{'name': self.zip.name, 'sha256': release.sha(self.zip)}]}
        remote = {'draft': True, 'assets': [], 'html_url': 'test'}
        with patch.object(release, 'api', return_value=remote), patch.object(release, 'command', side_effect=RuntimeError('upload failed')) as cmd:
            with self.assertRaises(RuntimeError):
                release.publish(entry, self.root)
        self.assertEqual(cmd.call_count, 1)
        self.assertEqual(cmd.call_args.args[0][:3], ['gh', 'release', 'upload'])

    def test_remote_mismatch_never_overwrites(self):
        release.build_archive(self.source, self.zip)
        entry = {'tag': self.source.name, 'assets': [{'name': self.zip.name, 'sha256': release.sha(self.zip)}]}
        remote = {'draft': False, 'assets': [{'name': self.zip.name, 'size': 0}]}
        with patch.object(release, 'api', return_value=remote), patch.object(release, 'command') as cmd:
            with self.assertRaises(ValueError):
                release.publish(entry, self.root)
            cmd.assert_not_called()


if __name__ == '__main__':
    unittest.main()
