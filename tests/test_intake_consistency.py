"""Catch real drift between intake UI metadata and its governing references."""
import importlib.util
from pathlib import Path
import shutil
import tempfile
import unittest

from kit import KIT

spec = importlib.util.spec_from_file_location(
    'intake_check', Path(__file__).resolve().parents[1] / 'tools/check_intake_form.py')
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)


class IntakeConsistencyTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.skill = Path(temporary.name) / 'product'
        shutil.copytree(KIT / '.agents/skills/matrix-product', self.skill)

    def change(self, relative, before, after):
        path = self.skill / relative
        text = path.read_text()
        self.assertIn(before, text)
        path.write_text(text.replace(before, after, 1))

    def test_current_form_and_guides_agree(self):
        self.assertEqual(checker.check(self.skill), [])

    def test_missing_color_review_stage_reproduces_the_reported_drift(self):
        self.change('references/initial-intake.md', '配色方向在 P-5 审阅', '配色方向审阅')
        self.assertTrue(any('I11 latest stage' in p for p in checker.check(self.skill)))

    def test_missing_form_item_is_reported(self):
        self.change('assets/initial-intake-form.html', 'data-id="I11"', 'data-id="I99"')
        self.assertTrue(any('IDs differ' in p for p in checker.check(self.skill)))

    def test_duplicate_form_item_is_reported(self):
        self.change('assets/initial-intake-form.html', 'data-id="I11"', 'data-id="I10"')
        self.assertIn('duplicate form fieldset IDs', checker.check(self.skill))

    def test_changed_importance_is_reported(self):
        self.change('assets/initial-intake-form.html', "I01:{level:'必须确认", "I01:{level:'可选")
        self.assertTrue(any('I01 importance' in p for p in checker.check(self.skill)))

    def test_changed_capability_basis_is_reported(self):
        self.change('assets/initial-intake-form.html', "basis:['P1-1']", "basis:['P1-9']")
        self.assertTrue(any('I01 basis' in p for p in checker.check(self.skill)))

    def test_unsupported_preset_is_reported(self):
        path = self.skill / 'assets/initial-intake-form.html'
        text = path.read_text()
        start = text.index('tone:{label:')
        position = text.index('options:[', start) + len('options:[')
        path.write_text(text[:position] + "'UNREGISTERED'," + text[position:])
        self.assertTrue(any('tone options' in p for p in checker.check(self.skill)))
