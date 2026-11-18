"""No model: the common fixed P-1 input must pass the repaired protocol before paid runs."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from kit import KIT

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO/'evals'))
from fixtures import late_game

class FixedPriorDirection(unittest.TestCase):
    def test_confirmed_business_fixture_is_valid_and_pinned(self):
        suite=json.loads((REPO/'evals/cases/suite.json').read_text())
        cases=suite if isinstance(suite,list) else suite['cases']
        digest=hashlib.sha256(Path(late_game.__file__).read_bytes()).hexdigest()
        spec=importlib.util.spec_from_file_location('fixed_prior_gate',KIT/'matrix/base/tools/stage_gate.py')
        gate=importlib.util.module_from_spec(spec);spec.loader.exec_module(gate)
        for case in [row for row in cases if row.get('fixture')=='late_game']:
            with self.subTest(case=case['id']),TemporaryDirectory() as temp:
                self.assertEqual(case['fixture_sha256'],digest)
                root=Path(temp);late_game.populate(root,case['id'])
                draft=gate.tone.validate(root,late_game.CONTRACT)
                self.assertEqual(draft['confirmation']['person'],'synthetic-owner')
                self.assertEqual((root/'design/direction/sample.png').read_bytes(),(late_game.INPUTS/'direction.png').read_bytes())
                self.assertTrue(all('不宣称访问' in row['observed'] for row in draft['references']))

if __name__=='__main__':unittest.main()
