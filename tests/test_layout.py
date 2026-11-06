"""Package layout: kit files only under matrix/ and the skills directory, skill names follow the profession ids,
no project data or earlier-layout paths inside the kit, and the shared knowledge index check."""
import importlib.util, json, re, tempfile, unittest
from pathlib import Path

from kit import KIT

ROOT = Path(__file__).resolve().parents[1]
TOP = {'START.md', 'BEHAVIOR-CHECKS.md', 'install.py', 'MANIFEST.json'}
# Project data lives outside matrix/ (shared/, management/, exchange/ and the work areas).
PROJECT_DATA = re.compile(r'matrix/(?:shared|management|exchange)/|matrix/[^\s`)]*\.sqlite3')
# Names and paths of the layout before Matrix-AI; only the installer's detection of earlier kits may name them
# (MANIFEST.json lists feature identifiers such as profession-builder/0.1, which are not skill names).
OLD = re.compile(r'(?<![\w-])(?:project-front-desk-agent|project-management-agent|professional-agent-collaboration|product-agent|'
                 r'content-design-review|experience-design-agent|engineering-(?:intake|solution|build)-agent|quality-verification-agent|'
                 r'profession-builder|product-capability-model)(?![\w-])|(?<![\w.-])collaboration/(?!0\.1)|\.agent-runtime/|upgrade-bases')
OLD_ALLOWED = {'install.py', 'MANIFEST.json'}
# Commands in the rules run from the project root (install.py from the kit), so they name the installed path.
COMMAND = re.compile(r'python3 ((?:\{[^}]*\})?\S*?\.py)(?![\w.])')


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class LayoutTests(unittest.TestCase):
    def files(self):
        return [p.relative_to(KIT) for p in KIT.rglob('*') if p.is_file() and '__pycache__' not in p.parts]

    def test_kit_files_are_under_matrix_or_the_skills_directory(self):
        for rel in self.files():
            self.assertTrue(str(rel) in TOP or rel.parts[0] == 'matrix' or rel.parts[:2] == ('.agents', 'skills'), rel)

    def test_skill_names_follow_the_profession_ids(self):
        skills = {p.name for p in (KIT / '.agents/skills').iterdir() if p.is_dir()}
        listed = set()
        for reg in (KIT / 'matrix/professions').glob('*/profession.json'):
            data = json.loads(reg.read_text(encoding='utf-8'))
            self.assertEqual(data['id'], reg.parent.name)
            for skill in data['skills']:
                self.assertIn(skill, skills)
                self.assertRegex(skill, '^matrix-' + re.escape(data['id']) + r'(-[a-z]+)?$')
                listed.add(skill)
        # Skills that are not a profession's: collaboration, profession creation and the knowledge base.
        self.assertEqual(skills - listed, {'matrix-collaboration', 'matrix-profession-builder', 'matrix-product-capability-model'})
        for skill in skills:
            self.assertIn('name: ' + skill + '\n', (KIT / '.agents/skills' / skill / 'SKILL.md').read_text(encoding='utf-8'))

    def test_no_project_data_or_earlier_layout_inside_the_kit(self):
        for rel in self.files():
            if rel.suffix not in {'.md', '.py', '.json', '.html', '.yaml'}:
                continue
            text = (KIT / rel).read_text(encoding='utf-8')
            self.assertIsNone(PROJECT_DATA.search(text), rel)
            if str(rel) not in OLD_ALLOWED:
                m = OLD.search(text)
                self.assertIsNone(m, f'{rel}: {m and m.group(0)}')

    def test_commands_name_installed_tools(self):
        for rel in self.files():
            if rel.suffix == '.md':
                for path in COMMAND.findall((KIT / rel).read_text(encoding='utf-8')):
                    self.assertTrue((KIT / path).is_file(), f'{rel}: python3 {path}')

    def test_package_name_is_matrix_ai(self):
        manifest = json.loads((KIT / 'MANIFEST.json').read_text(encoding='utf-8'))
        self.assertTrue(manifest['package'].startswith('matrix-ai/'))
        self.assertTrue((KIT / 'START.md').read_text(encoding='utf-8').startswith('# Matrix-AI '))


class SharedIndexTests(unittest.TestCase):
    def setUp(self):
        self.check = load(KIT / 'matrix/base/tools/shared_index.py', 'shared_index_under_test').check
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        for pid in ('product', 'content-design'):
            (self.root / 'matrix/professions' / pid).mkdir(parents=True)
            (self.root / 'matrix/professions' / pid / 'profession.json').write_text('{}')
        (self.root / 'product').mkdir()
        (self.root / 'product/01-产品定义.md').write_text('SIMULATED baseline')

    def index(self, *rows):
        head = '| 编号 | 内容 | 位置 | 负责专业 | 版本或摘要 | 谁能读 | 对外 | 含个人数据或凭证 |\n| --- | --- | --- | --- | --- | --- | --- | --- |\n'
        (self.root / 'shared').mkdir(exist_ok=True)
        (self.root / 'shared/index.md').write_text('# 共享知识索引\n\n' + head + ''.join('| ' + ' | '.join(r) + ' |\n' for r in rows))

    def test_no_index_passes(self):
        self.assertEqual(self.check(self.root), [])

    def test_valid_row_passes(self):
        self.index(['K-001', '产品基线', 'product/01-产品定义.md', 'product', 'v1', '全部', '只给摘录', '否'])
        self.assertEqual(self.check(self.root), [])

    def test_problems_are_reported(self):
        self.index(['K-001', '产品基线', 'product/missing.md', 'legal', 'v1', 'product、design', '随便', '否'],
                   ['K-001', '人员名单', 'product/01-产品定义.md', 'product', 'v1', '全部', '可外发', '是'])
        problems = '\n'.join(self.check(self.root))
        for part in ['location not found', 'owner is not a registered profession: legal', 'readers not registered: design',
                     '对外 must be one of', 'id must be K-nnn and unique', 'personal data or credentials must be 不外发']:
            self.assertIn(part, problems)


if __name__ == '__main__':
    unittest.main()
