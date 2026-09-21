#!/usr/bin/env python3
"""Installer tests use temporary projects and SIMULATED task/authorization values."""
import hashlib
from pathlib import Path
import tempfile
import unittest

from install import BLOCK, SKILL, CoordinationError, execute, install


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.config = {'authorization': 'SIMULATED INSTALL TEST; not real user approval',
                       'frontdoor': {'thread_id': 'simulated-v2'}}
        for name in ('product-agent', 'engineering-intake-agent', 'experience-design-agent'):
            self.write('.agents/skills/' + name + '/SKILL.md', 'SIMULATED professional skill: ' + name)
        for path in ('product/confirmed.md', 'design/confirmed.md', 'engineering/intake/model.md'):
            self.write(path, 'SIMULATED professional source must remain byte-identical')
        self.write('AGENTS.md', '# Original project instructions\n\nKeep human edits.\n')

    def write(self, path, value):
        dest = self.root / path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(value.encode() if isinstance(value, str) else value)
        return dest

    def snapshot(self, root=None):
        root = root or self.root
        return {str(p.relative_to(root)): (p.read_bytes(), p.stat().st_mtime_ns)
                for p in root.rglob('*') if p.is_file()}

    def test_first_install_registers_available_roles_without_starting_transport(self):
        result = install(self.root, self.config)
        self.assertTrue(result['installed'])
        self.assertFalse(result['transport_started'])
        self.assertTrue((self.root / SKILL / 'SKILL.md').is_file())
        status = execute(self.root, {'op': 'status'})
        roles = {r['id']: r for r in status['roles']}
        self.assertEqual(set(roles), {'engineering-intake', 'product', 'experience-design'})
        self.assertIsNone(roles['product']['endpoint'])
        self.assertEqual(roles['engineering-intake']['endpoint']['kind'], 'inline')

    def test_identical_reinstall_has_zero_file_writes(self):
        install(self.root, self.config)
        before = self.snapshot()
        result = install(self.root, self.config)
        self.assertEqual(result['files_written'], [])
        self.assertEqual(before, self.snapshot())

    def test_original_agents_preserved_and_exactly_backed_up(self):
        before = (self.root / 'AGENTS.md').read_bytes()
        install(self.root, self.config)
        self.assertTrue((self.root / 'AGENTS.md').read_bytes().startswith(before))
        backups = list((self.root / 'collaboration/runtime/install-backups').glob('AGENTS.*.md'))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_bytes(), before)

    def test_professional_skills_and_sources_keep_original_hashes_and_times(self):
        before = self.snapshot()
        protected = {p: value for p, value in before.items() if p != 'AGENTS.md'}
        install(self.root, self.config)
        after = self.snapshot()
        self.assertEqual(protected, {p: after[p] for p in protected})

    def test_existing_custom_professional_protocol_is_preserved(self):
        self.write('collaboration/CONTRACT.md', 'Project customized professional agreement')
        before = (self.root / 'collaboration/CONTRACT.md').read_bytes()
        result = install(self.root, self.config)
        self.assertEqual((self.root / 'collaboration/CONTRACT.md').read_bytes(), before)
        self.assertIn('collaboration/CONTRACT.md', result['preserved_project_protocol'])

    def test_runtime_conflict_rejected_before_any_write(self):
        self.write('collaboration/RUNTIME.md', 'Different installed runtime edition')
        before = self.snapshot()
        with self.assertRaises(CoordinationError):
            install(self.root, self.config)
        self.assertEqual(before, self.snapshot())

    def test_existing_real_role_mapping_not_reset(self):
        install(self.root, self.config)
        spec = {'id': 'product', 'skill': '.agents/skills/product-agent/SKILL.md',
                'write_roots': ['product'], 'endpoint': {
                    'kind': 'subagent', 'id': 'simulated-existing-real-endpoint', 'session': 'simulated-session'}}
        execute(self.root, {'op': 'register', 'actor': 'coordinator', 'role': spec})
        before = self.snapshot()
        install(self.root, self.config)
        status = execute(self.root, {'op': 'status'})
        self.assertEqual(next(r for r in status['roles'] if r['id'] == 'product'), spec)
        self.assertEqual(before, self.snapshot())

    def test_different_config_rejected_without_changes(self):
        install(self.root, self.config)
        before = self.snapshot()
        with self.assertRaises(CoordinationError):
            install(self.root, {**self.config, 'frontdoor': {'thread_id': 'different-simulated-task'}})
        self.assertEqual(before, self.snapshot())

    def test_missing_required_role_does_not_install_any_files(self):
        with tempfile.TemporaryDirectory() as empty:
            path = Path(empty)
            with self.assertRaises(CoordinationError):
                install(path, self.config)
            self.assertEqual(list(path.iterdir()), [])

    def test_optional_design_role_may_be_absent(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp)
            for name in ('product-agent', 'engineering-intake-agent'):
                skill = target / '.agents/skills' / name / 'SKILL.md'
                skill.parent.mkdir(parents=True)
                skill.write_text('SIMULATED required role')
            self.assertTrue(install(target, self.config)['installed'])
            self.assertEqual(len(execute(target, {'op': 'status'})['roles']), 2)

    def test_destination_symlink_escape_rejected_without_outside_or_inside_changes(self):
        with tempfile.TemporaryDirectory() as outside:
            external = Path(outside)
            (external / 'sentinel.md').write_text('Do not touch')
            (self.root / 'collaboration').symlink_to(external, target_is_directory=True)
            before, external_before = self.snapshot(), self.snapshot(external)
            with self.assertRaises(CoordinationError):
                install(self.root, self.config)
            self.assertEqual(self.snapshot(), before)
            self.assertEqual(self.snapshot(external), external_before)

    def test_database_symlink_escape_rejected_before_installing(self):
        with tempfile.TemporaryDirectory() as outside:
            external = Path(outside) / 'state.sqlite3'
            external.write_bytes(b'outside sentinel')
            runtime = self.root / 'collaboration/runtime'
            runtime.mkdir(parents=True)
            (runtime / 'state.sqlite3').symlink_to(external)
            before = self.snapshot()
            with self.assertRaises(CoordinationError):
                install(self.root, self.config)
            self.assertEqual(self.snapshot(), before)
            self.assertEqual(external.read_bytes(), b'outside sentinel')

    def test_malformed_agents_block_rejected_before_changes(self):
        self.write('AGENTS.md', '<!-- professional-agent-collaboration:begin -->\nUnclosed')
        before = self.snapshot()
        with self.assertRaises(CoordinationError):
            install(self.root, self.config)
        self.assertEqual(before, self.snapshot())

    def test_crlf_agents_original_bytes_preserved_in_file_and_backup(self):
        original = b'# Human instructions\r\n\r\nKeep original line endings.\r\n'
        self.write('AGENTS.md', original)
        install(self.root, self.config)
        self.assertTrue((self.root / 'AGENTS.md').read_bytes().startswith(original))
        backups = list((self.root / 'collaboration/runtime/install-backups').glob('AGENTS.*.md'))
        self.assertEqual(backups[0].read_bytes(), original)

    def test_file_where_runtime_subdirectory_needed_rejected_before_any_write(self):
        self.write(str(SKILL / 'references'), 'Existing file cannot become directory')
        before = self.snapshot()
        with self.assertRaises((CoordinationError, OSError)):
            install(self.root, self.config)
        self.assertEqual(before, self.snapshot())

    def test_whitespace_authorization_rejected_before_installing(self):
        before = self.snapshot()
        with self.assertRaises(CoordinationError):
            install(self.root, {**self.config, 'authorization': '   '})
        self.assertEqual(before, self.snapshot())

    def test_nonstring_authorization_rejected_before_installing(self):
        before = self.snapshot()
        with self.assertRaises(CoordinationError):
            install(self.root, {**self.config, 'authorization': ['not an authorization reference']})
        self.assertEqual(before, self.snapshot())

    def test_corrupt_preexisting_agents_backup_rejected_before_installing(self):
        original = (self.root / 'AGENTS.md').read_bytes()
        sha = hashlib.sha256(original).hexdigest()[:16]
        self.write('collaboration/runtime/install-backups/AGENTS.' + sha + '.md',
                   'A mismatched old backup must not be silently trusted')
        before = self.snapshot()
        with self.assertRaises(CoordinationError):
            install(self.root, self.config)
        self.assertEqual(before, self.snapshot())


if __name__ == '__main__':
    unittest.main()
