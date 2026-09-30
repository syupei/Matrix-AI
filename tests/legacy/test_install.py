"""Installer behavior, exercised only in disposable temporary projects."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

import os
KIT_ENV = os.environ.get('MATRIX_TEST_KIT')
if not KIT_ENV:
    raise unittest.SkipTest('set MATRIX_TEST_KIT to a built package (tools/production.py does this)')
KIT=Path(KIT_ENV)
spec=importlib.util.spec_from_file_location('pm_kit_install',KIT/'install.py')
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
PACKAGE=json.loads((KIT/'MANIFEST.json').read_text())['package']


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
        self.assertIn(mod.block(PACKAGE,'.agents/skills').rstrip('\n'),result)

    def test_all_roles_installed_without_runtime_initialization(self):
        result=mod.install(self.root,True)
        for role in ['product-agent','experience-design-agent','engineering-intake-agent','project-management-agent','professional-agent-collaboration','content-design-review','product-capability-model']:
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
        self.assertTrue((self.root/'.agents/skills/experience-design-agent/SKILL.md').is_file())
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

    def package_copy(self, bases_update):
        """A temporary copy of the kit whose upgrade bases include extra known releases."""
        import shutil
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        package=Path(tmp.name)
        shutil.copytree(KIT,package,dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
        bases=json.loads((package/'upgrade-bases.json').read_text())
        for rel,digest in bases_update.items():
            bases.setdefault(rel,[]).append(digest)
        (package/'upgrade-bases.json').write_text(json.dumps(bases))
        return package

    def test_legacy_marker_block_is_migrated(self):
        self.put('AGENTS.md','intro\n<!-- pm-agent-test:begin -->\nold entry\n<!-- pm-agent-test:end -->\noutro\n')
        mod.install(self.root,True)
        text=(self.root/'AGENTS.md').read_text()
        self.assertNotIn('pm-agent-test',text)
        self.assertNotIn('old entry',text)
        self.assertTrue(text.startswith('intro\n') and text.endswith('\noutro\n'))
        self.assertEqual(text.count(mod.BEGIN),1)

    def test_host_specific_skills_dir_and_entry(self):
        result=mod.install(self.root,True,'.claude/skills',['CLAUDE.md'])
        self.assertEqual(result['skills_dir'],'.claude/skills')
        self.assertTrue((self.root/'.claude/skills/product-agent/SKILL.md').is_file())
        self.assertFalse((self.root/'.agents').exists())
        self.assertFalse((self.root/'AGENTS.md').exists())
        entry=(self.root/'CLAUDE.md').read_text()
        self.assertIn('(.claude/skills/product-agent/SKILL.md)',entry)
        self.assertTrue((self.root/'collaboration/CORE.md').is_file())

    def test_multiple_entries_receive_the_same_block(self):
        self.put('CLAUDE.md','host notes\n')
        mod.install(self.root,True,'.agents/skills',['AGENTS.md','CLAUDE.md'])
        for name in ['AGENTS.md','CLAUDE.md']:
            self.assertEqual((self.root/name).read_text().count(mod.BEGIN),1)
        self.assertIn('host notes',(self.root/'CLAUDE.md').read_text())

    def test_invalid_skills_dir_or_entry_rejected(self):
        for bad in ['/abs/skills','skills','a/b/c','../x']:
            with self.assertRaisesRegex(ValueError,'skills dir'):
                mod.install(self.root,True,bad)
        with self.assertRaisesRegex(ValueError,'entry'):
            mod.install(self.root,True,'.agents/skills',['docs/AGENTS.md'])
        self.assertEqual(list(self.root.iterdir()),[])

    def test_unmodified_retired_file_is_removed_with_backup(self):
        from unittest.mock import patch
        rel='.agents/skills/product-agent/references/retired-guide.md'
        old=b'guide shipped by an earlier release'
        self.put(rel,old.decode())
        package=self.package_copy({rel:mod.sha(old)})
        with patch.object(mod,'ROOT',package):
            preview=mod.install(self.root)
            self.assertIn(rel,preview['retire'])
            result=mod.install(self.root,True)
        self.assertFalse((self.root/rel).exists())
        self.assertEqual([x['path'] for x in result['retired']],[rel])
        self.assertEqual((self.root/'management/install-backups'/mod.sha(old)/rel).read_bytes(),old)

    def test_modified_retired_file_is_kept_and_reported(self):
        from unittest.mock import patch
        rel='.agents/skills/product-agent/references/retired-guide.md'
        package=self.package_copy({rel:mod.sha(b'released content')})
        self.put(rel,'project edited this guide')
        with patch.object(mod,'ROOT',package):
            result=mod.install(self.root,True)
        self.assertEqual(result['retired_modified_kept'],[rel])
        self.assertEqual((self.root/rel).read_text(),'project edited this guide')

    def test_unmodified_shared_file_from_other_release_is_retired(self):
        from unittest.mock import patch
        rel='shared/stage_gate.py'
        old=b'shipped by another release line'
        self.put(rel,old.decode())
        package=self.package_copy({rel:mod.sha(old)})
        with patch.object(mod,'ROOT',package):
            result=mod.install(self.root,True)
        self.assertEqual([x['path'] for x in result['retired']],[rel])
        self.assertFalse((self.root/'shared').exists())

    def test_custom_core_rules_stop_before_any_write(self):
        self.put('collaboration/CORE.md','project rewrote the shared baseline')
        with self.assertRaisesRegex(ValueError,'custom/unknown'):
            mod.install(self.root,True)
        self.assertFalse((self.root/'.agents').exists())

    def test_legacy_entry_text_is_reported_not_removed(self):
        self.put('AGENTS.md','# 产品与设计联合试验入口\nlegacy text\n')
        result=mod.install(self.root,True)
        self.assertEqual(result['legacy_entry_review'],['AGENTS.md: # 产品与设计联合试验入口'])
        self.assertIn('legacy text',(self.root/'AGENTS.md').read_text())


if __name__=='__main__':
    unittest.main()
