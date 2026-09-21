import importlib.util
import json
from pathlib import Path
import tempfile
import subprocess
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

    def test_draft_lookup_prevents_duplicate_creation(self):
        draft = {'id': 42, 'tag_name': 'test-kit-v0.1', 'draft': True}
        with patch.object(release, 'api', side_effect=[None, [draft]]):
            self.assertEqual(release.release_info('test-kit-v0.1'), draft)

    def test_new_build_commits_and_retries_without_duplicate_version(self):
        checkout = self.root / 'publishing'
        checkout.mkdir()
        for args in [['init', '-b', 'main'], ['config', 'user.name', 'Test'], ['config', 'user.email', 'test@example.invalid'], ['remote', 'add', 'origin', 'https://github.com/syupei/Matrix-AI.git']]:
            subprocess.run(['git', *args], cwd=checkout, check=True, capture_output=True)
        (checkout / 'README.md').write_text('目前推荐 **previous**，old link\n')
        (checkout / 'releases.json').write_text(json.dumps({'latest': None, 'releases': []}))
        (checkout / 'SHA256SUMS').write_text('')
        subprocess.run(['git', 'add', '.'], cwd=checkout, check=True)
        subprocess.run(['git', 'commit', '-m', 'test baseline'], cwd=checkout, check=True, capture_output=True)
        notes = self.root / 'notes.md'
        notes.write_text('New verified version')
        real_git = release.git

        def local_git(*args, **kwargs):
            if args[0] == 'push':
                return subprocess.CompletedProcess(args, 0, '', '')
            return real_git(*args, **kwargs)

        with patch.object(release, 'ROOT', checkout), patch.object(release, 'CATALOG', checkout / 'releases.json'), patch.object(release, 'git', side_effect=local_git), patch.object(release, 'publish') as publish:
            release.build_and_publish(self.source, notes, True)
            first = real_git('rev-parse', 'HEAD').stdout
            release.build_and_publish(self.source, notes, True)
            self.assertEqual(first, real_git('rev-parse', 'HEAD').stdout)
            self.assertEqual(publish.call_count, 2)
            self.assertEqual(real_git('status', '--porcelain').stdout, '')
        catalog = json.loads((checkout / 'releases.json').read_text())
        self.assertEqual(len(catalog['releases']), 1)
        self.assertEqual(catalog['latest'], self.source.name)
        self.assertIn(self.source.name, (checkout / 'README.md').read_text())


if __name__ == '__main__':
    unittest.main()
