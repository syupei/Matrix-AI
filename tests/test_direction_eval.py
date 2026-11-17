import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

EVALS = Path(__file__).resolve().parents[1] / 'evals'
sys.path.insert(0, str(EVALS))
import direction_slice
import visual_evidence
from kit import KIT


class DirectionEvalTest(unittest.TestCase):
    def test_capture_states_and_direct_image_evidence(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            with patch.object(visual_evidence,'browser',return_value=None):
                self.assertEqual(visual_evidence.capture(root)['status'],'browser_unavailable')
            with patch.object(visual_evidence,'browser',return_value='fake-browser'):
                self.assertEqual(visual_evidence.capture(root)['status'],'preview_missing')
                (root/'design').mkdir()
                (root/'design/preview.html').write_text('<button>Play</button>')
                def rendered(argv, **_):
                    target=next(a.partition('=')[2] for a in argv if a.startswith('--screenshot='))
                    Path(target).write_bytes(visual_evidence.IMAGE_MAGIC+b'fixture')
                with patch.object(visual_evidence.subprocess,'run',side_effect=rendered):
                    result=visual_evidence.capture(root)
                self.assertEqual(result['status'],'captured')
                self.assertTrue((root/result['screenshot']).is_file())
                self.assertTrue((root/'design/preview.html').is_file())

    def test_simulated_stakeholder_parser_and_model_usage(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'response.json'
            p.write_text(json.dumps({'decision':'correct','answer':'Move the main interaction into the core scene'}))
            self.assertEqual(direction_slice.ask(p)['decision'],'correct')
            p.write_text(json.dumps({'decision':'confirmed from silence','answer':''}))
            with self.assertRaises(ValueError):
                direction_slice.ask(p)
            p.write_text('{"type":"turn.completed","usage":{"input_tokens":17,"output_tokens":3}}\n')
            self.assertEqual(direction_slice.usage(p),{'input_tokens':17,'output_tokens':3})


    def test_slice_archives_visuals_and_records_real_displayed_material(self):
        def simulated_turn(root, log, name, *args):
            if name=='product-clarify':
                (root/'澄清.md').write_text('是一人玩还是本地双人？')
            elif name.startswith('stakeholder-'):
                decision='answer' if name.endswith('-1') else 'confirm'
                (root/'response.json').write_text(json.dumps(dict(decision=decision,answer='合成答复')))
            elif name.startswith('fit-'):
                (root/'fit.json').write_text(json.dumps(dict(decision='confirm',answer='合成贴合观察')))
            elif name=='product-brief':
                (root/'product').mkdir()
                (root/'product/direction-brief.md').write_text('合成简报')
            elif name in ('design-first','design-review-a'):
                (root/'design').mkdir(exist_ok=True)
                name_out='preview.html' if name=='design-first' else 'review-a.html'
                (root/'design'/name_out).write_text('<button>Test</button>')
            elif name=='content-first':
                (root/'content').mkdir()
                (root/'content/samples.md').write_text('合成文案')
            return {'name':name,'usage':{'input_tokens':1}}

        def simulated_capture(root, name='design/preview.html'):
            self.assertTrue((root/name).is_file())
            (root/'visual-evidence').mkdir(exist_ok=True)
            (root/'visual-evidence/preview.png').write_bytes(visual_evidence.IMAGE_MAGIC+b'fixture')
            return {'status':'captured','screenshot':'visual-evidence/preview.png'}

        with tempfile.TemporaryDirectory() as folder:
            output=Path(folder)/'take'
            with patch.object(direction_slice,'turn',side_effect=simulated_turn), patch.object(
                    direction_slice,'capture',side_effect=simulated_capture):
                direction_slice.slice_run(KIT, output, {role:'SIM' for role in ['product','content','design','stakeholder']}, 'medium')
            data=json.loads((output/'result.json').read_text())
            self.assertEqual(data['pm_attention']['answered'],2)
            self.assertEqual(len(data['fit_reviews']),1)
            self.assertEqual(data['last_decision'],'confirm')
            self.assertTrue((output/'first-preview.png').is_file())
            self.assertTrue((output/'review-a.png').is_file())
