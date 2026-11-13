import importlib.util,unittest
from pathlib import Path
spec=importlib.util.spec_from_file_location('production_budget',Path(__file__).resolve().parents[1]/'tools/production.py')
p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)
class GuidanceBudgetTests(unittest.TestCase):
 def test_long_reference_fails_without_reasoned_exception(self):
  docs={'matrix/base/TEST.md':'文'*3001}
  self.assertTrue(p.guidance_budget_errors(docs,{}))
  self.assertTrue(p.guidance_budget_errors(docs,{'matrix/base/TEST.md':{'max_characters':3100,'reason':''}}))
  self.assertEqual(p.guidance_budget_errors(docs,{'matrix/base/TEST.md':{'max_characters':3100,'reason':'An indivisible reviewed reference'}}),[])
 def test_exception_has_ceiling_and_cannot_outlive_reference(self):
  e={'matrix/base/TEST.md':{'max_characters':3100,'reason':'Retain complete contract'}}
  self.assertTrue(p.guidance_budget_errors({'matrix/base/TEST.md':'文'*3101},e))
  self.assertTrue(p.guidance_budget_errors({},e))
 def test_standard_exemption_does_not_hide_adjacent_guidance(self):
  root='.agents/skills/matrix-product-capability-model/'
  self.assertEqual(p.guidance_budget_errors({root+'standards/original.md':'文'*9000},{}),[])
  self.assertTrue(p.guidance_budget_errors({root+'capability-index.md':'文'*3001},{}))
 def test_entry_and_index_budgets_are_distinct(self):
  self.assertEqual(p.guidance_budget_errors({'.agents/skills/example/SKILL.md':'文'*3500},{}),[])
  self.assertTrue(p.guidance_budget_errors({'.agents/skills/example/GUIDANCE-INDEX.md':'文'*1501},{}))
