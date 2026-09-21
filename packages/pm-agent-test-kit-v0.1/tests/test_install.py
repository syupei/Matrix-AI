"""Install behavior in disposable projects; never writes to EC-TEST."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

KIT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('pm_kit_install',KIT/'install.py')
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='pm-install-fixture-')
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)

    def put(self,path,data):
        p=self.root/path
        p.parent.mkdir(parents=True,exist_ok=True)
        p.write_text(data)

    def test_dry_run_does_not_mutate(self):
        self.put('AGENTS.md','human edits\n')
        before={str(x.relative_to(self.root)):x.read_bytes() for x in self.root.rglob('*') if x.is_file()}
        result=mod.install(self.root)
        self.assertTrue(result['dry_run'])
        self.assertEqual(before,{str(x.relative_to(self.root)):x.read_bytes() for x in self.root.rglob('*') if x.is_file()})

    def test_install_preserves_business_and_root_and_backs_up(self):
        self.put('AGENTS.md','human project instructions\n')
        for path in ['product/source.md','design/confirmed.md','engineering/intake/baseline.md','collaboration/feedback.md','collaboration/runtime/state.sqlite3']:
            self.put(path,'untouched '+path)
        mod.install(self.root,True)
        self.assertIn('human project instructions',(self.root/'AGENTS.md').read_text())
        self.assertTrue(list((self.root/'management/install-backups').rglob('AGENTS.md')))
        for path in ['product/source.md','design/confirmed.md','engineering/intake/baseline.md','collaboration/feedback.md','collaboration/runtime/state.sqlite3']:
            self.assertEqual((self.root/path).read_text(),'untouched '+path)

    def test_reinstall_is_idempotent_and_keeps_first_receipt(self):
        mod.install(self.root,True)
        first=(self.root/'management/install-receipt.json').read_bytes()
        again=mod.install(self.root,True)
        self.assertEqual(again['written'],[])
        self.assertEqual(first,(self.root/'management/install-receipt.json').read_bytes())
        self.assertEqual((self.root/'AGENTS.md').read_text().count(mod.BEGIN),1)

    def test_unknown_professional_customization_stops_before_any_write(self):
        self.put('.agents/skills/product-agent/SKILL.md','custom professional requirements')
        with self.assertRaisesRegex(ValueError,'custom/unknown'):
            mod.install(self.root,True)
        self.assertFalse((self.root/'AGENTS.md').exists())
        self.assertFalse((self.root/'.agents/skills/project-management-agent').exists())

    def test_common_project_customization_is_preserved_and_reported(self):
        self.put('collaboration/CONTRACT.md','project custom contract')
        result=mod.install(self.root,True)
        self.assertIn('collaboration/CONTRACT.md',result['preserved_custom_common'])
        self.assertEqual((self.root/'collaboration/CONTRACT.md').read_text(),'project custom contract')

    def test_symlink_target_is_rejected(self):
        with tempfile.TemporaryDirectory() as other:
            (self.root/'.agents').symlink_to(other,target_is_directory=True)
            with self.assertRaisesRegex(ValueError,'unsafe|symlink'):
                mod.install(self.root,True)
            self.assertEqual(list(Path(other).iterdir()),[])

    def test_malformed_managed_block_is_not_overwritten(self):
        self.put('AGENTS.md',mod.BEGIN+'\nhuman unfinished block')
        with self.assertRaisesRegex(ValueError,'malformed'):
            mod.install(self.root,True)
        self.assertFalse((self.root/'.agents').exists())


if __name__=='__main__':
    unittest.main()
