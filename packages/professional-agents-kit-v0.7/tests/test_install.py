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

    def test_copy_rule_conflict_stops_before_installing_any_role(self):
        self.put('collaboration/COPY-QUALITY.md','custom copy policy')
        self.put('AGENTS.md','existing project instructions')
        before={str(x.relative_to(self.root)):x.read_bytes() for x in self.root.rglob('*') if x.is_file()}
        with self.assertRaisesRegex(ValueError,'custom/unknown'):
            mod.install(self.root,True)
        self.assertEqual(before,{str(x.relative_to(self.root)):x.read_bytes() for x in self.root.rglob('*') if x.is_file()})

    def test_structured_handoff_conflict_stops_before_any_write(self):
        self.put('collaboration/STRUCTURED-HANDOFF.md','project custom handoff rules')
        before={str(x.relative_to(self.root)):x.read_bytes() for x in self.root.rglob('*') if x.is_file()}
        with self.assertRaisesRegex(ValueError,'custom/unknown'):
            mod.install(self.root,True)
        self.assertEqual(before,{str(x.relative_to(self.root)):x.read_bytes() for x in self.root.rglob('*') if x.is_file()})

    def test_upgrade_replaces_managed_entry_and_keeps_surrounding_instructions(self):
        self.put('AGENTS.md','before\n'+mod.BEGIN+'\nprevious release entry\n'+mod.END+'\nafter\n')
        mod.install(self.root,True)
        result=(self.root/'AGENTS.md').read_text()
        self.assertTrue(result.startswith('before\n'))
        self.assertTrue(result.endswith('\nafter\n'))
        self.assertNotIn('previous release entry',result)
        self.assertEqual(result.count(mod.BEGIN),1)
        self.assertIn(mod.BLOCK.rstrip('\n'),result)

    def test_all_roles_installed_without_runtime_initialization(self):
        result=mod.install(self.root,True)
        for role in ['product-agent','experience-design-agent','engineering-intake-agent','project-management-agent','professional-agent-collaboration']:
            self.assertTrue((self.root/'.agents/skills'/role/'SKILL.md').is_file())
        self.assertFalse(result['runtime_initialized'])
        self.assertFalse(list(self.root.rglob('*.sqlite3')))
        self.assertFalse((self.root/'product').exists())
        self.assertFalse((self.root/'design').exists())

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

    def test_custom_guidance_preserved_in_preflight_install_and_repeat(self):
        rel='.agents/skills/experience-design-agent/GUIDANCE-INDEX.md'
        custom='项目引用：采用现有动效规范；禁用额外声音。\n'
        self.put(rel,custom)
        before={str(x.relative_to(self.root)):x.read_bytes() for x in self.root.rglob('*') if x.is_file()}
        preview=mod.install(self.root)
        self.assertEqual(preview['preserved_custom_guidance'],[rel])
        self.assertEqual(preview['guidance_review_required'],[rel])
        self.assertNotIn(rel,preview['changes'])
        self.assertEqual(before,{str(x.relative_to(self.root)):x.read_bytes() for x in self.root.rglob('*') if x.is_file()})
        result=mod.install(self.root,True)
        self.assertEqual(result['preserved_custom_guidance'],[rel])
        self.assertEqual((self.root/rel).read_text(),custom)
        self.assertTrue((self.root/'.agents/skills/experience-design-agent/references/default-interaction.md').is_file())
        again=mod.install(self.root,True)
        self.assertEqual(again['written'],[])
        self.assertEqual(again['guidance_review_required'],[rel])
        self.assertEqual((self.root/rel).read_text(),custom)

    def test_all_six_fresh_guidance_indexes_installed(self):
        result=mod.install(self.root,True)
        roles=['product-agent','experience-design-agent','engineering-intake-agent','project-management-agent','professional-agent-collaboration','content-design-review']
        for role in roles:
            rel=Path('.agents/skills')/role/'GUIDANCE-INDEX.md'
            self.assertEqual((self.root/rel).read_bytes(),(KIT/rel).read_bytes())
        self.assertEqual(result['preserved_custom_guidance'],[])

    def test_known_old_guidance_default_upgrades_and_is_backed_up(self):
        from unittest.mock import patch
        import shutil
        rel='.agents/skills/product-agent/GUIDANCE-INDEX.md'
        old=b'original previous release index'
        self.put(rel,old.decode())
        with tempfile.TemporaryDirectory() as package:
            package=Path(package)
            shutil.copytree(KIT,package,dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
            bases=json.loads((package/'upgrade-bases.json').read_text())
            bases[rel]=[mod.sha(old)]
            (package/'upgrade-bases.json').write_text(json.dumps(bases))
            with patch.object(mod,'ROOT',package):
                result=mod.install(self.root,True)
        self.assertEqual(result['preserved_custom_guidance'],[])
        self.assertEqual((self.root/rel).read_bytes(),(KIT/rel).read_bytes())
        self.assertEqual((self.root/'management/install-backups'/mod.sha(old)/rel).read_bytes(),old)

    def test_custom_guidance_symlink_is_rejected_before_write(self):
        rel='.agents/skills/product-agent/GUIDANCE-INDEX.md'
        self.put('outside.md','user index')
        dest=self.root/rel
        dest.parent.mkdir(parents=True)
        dest.symlink_to(self.root/'outside.md')
        with self.assertRaisesRegex(ValueError,'symlink'):
            mod.install(self.root,True)
        self.assertFalse((self.root/'AGENTS.md').exists())
        self.assertEqual((self.root/'outside.md').read_text(),'user index')


if __name__=='__main__':
    unittest.main()
