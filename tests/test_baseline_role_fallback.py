"""New synthetic probes must resolve an actual entry on the complete baseline."""
import json,unittest
from pathlib import Path
class BaselineFallbackTests(unittest.TestCase):
 def test_expert_probes_resolve_old_pm_entry_without_changing_criteria(self):
  root=Path(__file__).resolve().parents[1]
  suite=json.loads((root/'evals/cases/suite.json').read_text())['cases']
  files=json.loads((root/'release-manifests/professional-agents-kit-v0.29.json').read_text())['files']
  ids={'expert_adaptation_boundary','expert_alias_identity','expert_import_preset','platform_unknown_isolation'}
  for c in suite:
   if c['id'] in ids:
    selected=next((r for r in c['role'] if '.agents/skills/'+r+'/SKILL.md' in files),None)
    self.assertEqual(selected,'project-management-agent');self.assertTrue(c['criteria'])
