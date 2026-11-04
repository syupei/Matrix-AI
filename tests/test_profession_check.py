"""Profession registries, the registry check and the generated total entry."""
import importlib.util, json, shutil, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'src'
SCRIPTS = SRC / '.agents/skills/profession-builder/scripts'


def load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / (name + '.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


check, entry = load('profession_check'), load('build_entry')


class ProfessionCheckTests(unittest.TestCase):
    def test_package_registries_pass_with_suite(self):
        self.assertEqual(check.check(SRC, ROOT / 'evals/cases/suite.json'), [])

    def test_total_entry_matches_registries(self):
        text, new = entry.build(SRC)
        self.assertEqual(text, new, 'run build_entry.py')

    def test_every_registry_eval_case_exists_and_new_cases_are_linked(self):
        ids = {c['id'] for c in json.loads((ROOT / 'evals/cases/suite.json').read_text())['cases']}
        linked = set()
        for p in (SRC / 'collaboration/professions').glob('*.json'):
            linked |= set(json.loads(p.read_text(encoding='utf-8'))['evals'])
        self.assertLessEqual(linked, ids)
        for case in ['risk_destructive_script', 'risk_billing_rule', 'risk_legal_text', 'defect_wrong_path_delete',
                     'defect_minor_copy', 'content_copy_only', 'desk_profession_mix']:
            self.assertIn(case, linked)

    def copy(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        shutil.copytree(SRC / 'collaboration', root / 'collaboration', ignore=shutil.ignore_patterns('__pycache__'))
        shutil.copytree(SRC / '.agents', root / '.agents', ignore=shutil.ignore_patterns('__pycache__'))
        return root, load_from(root)

    def edit_json(self, path, change):
        data = json.loads(path.read_text(encoding='utf-8'))
        change(data)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    def test_missing_field_is_reported(self):
        root, mod = self.copy()
        self.edit_json(root / 'collaboration/professions/product.json', lambda d: d.pop('not_handles'))
        self.assertTrue(any('product.json: not_handles' in p for p in mod.check(root)))

    def test_level_row_and_anchor_gaps_are_reported(self):
        root, mod = self.copy()
        doc = root / 'collaboration/professions/quality-engineering.md'
        lines = [l for l in doc.read_text(encoding='utf-8').splitlines() if not l.startswith('| T4 |') and not l.startswith('- F3：')]
        doc.write_text('\n'.join(lines) + '\n', encoding='utf-8')
        problems = mod.check(root)
        self.assertTrue(any('T4' in p for p in problems))
        self.assertTrue(any('F3' in p for p in problems))

    def test_duplicate_stage_flow_and_bad_upstream_are_reported(self):
        root, mod = self.copy()
        self.edit_json(root / 'collaboration/professions/experience-design.json', lambda d: d['stage_flows'][0].update(key='product'))
        self.edit_json(root / 'collaboration/professions/code-engineering.json',
                       lambda d: d['stage_flows'][2]['upstream'].update({'E3.1': ['solution', 'E9.9']}))
        problems = mod.check(root)
        self.assertTrue(any('duplicated: product' in p for p in problems))
        self.assertTrue(any('invalid upstream' in p for p in problems))

    def test_index_without_level_link_and_stale_entry_are_reported(self):
        root, mod = self.copy()
        index = root / '.agents/skills/product-agent/GUIDANCE-INDEX.md'
        index.write_text('\n'.join(l for l in index.read_text(encoding='utf-8').splitlines() if not l.startswith('| L01 |')) + '\n', encoding='utf-8')
        self.edit_json(root / 'collaboration/professions/product.json', lambda d: d.update(participation='只在需要时参与'))
        problems = mod.check(root)
        self.assertTrue(any('must link the level table' in p for p in problems))
        self.assertTrue(any('MATRIX.md is out of date' in p for p in problems))

    def test_unknown_eval_case_is_reported_with_suite(self):
        root, mod = self.copy()
        self.edit_json(root / 'collaboration/professions/front-desk.json', lambda d: d['evals'].append('no_such_case'))
        self.assertTrue(any('no_such_case' in p for p in mod.check(root, ROOT / 'evals/cases/suite.json')))


def load_from(root):
    """The check script as installed in a copied project, so it resolves skills there."""
    spec = importlib.util.spec_from_file_location('copied_check', root / '.agents/skills/profession-builder/scripts/profession_check.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


if __name__ == '__main__':
    unittest.main()
