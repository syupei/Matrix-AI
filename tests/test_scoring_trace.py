import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

evals = Path(__file__).resolve().parents[1] / 'evals'
sys.path.insert(0, str(evals))
spec = importlib.util.spec_from_file_location('matrix_scoring', evals / 'scoring.py')
scoring = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scoring)


class ToolTrace(unittest.TestCase):
    def test_claude_pairs_results_and_masks_trace_paths(self):
        root = '/synthetic/candidate/work/sample'
        events = [
            {'type': 'assistant', 'message': {'content': [
                {'type': 'tool_use', 'name': 'Read', 'id': 'r', 'input': {'file_path': root + '/a.md'}},
                {'type': 'tool_use', 'name': 'Bash', 'id': 'b', 'input': {'command': 'cat missing'}},
                {'type': 'tool_use', 'name': 'Write', 'id': 'w', 'input': {'file_path': root + '/b.md'}}]}},
            {'type': 'user', 'message': {'content': [
                {'type': 'tool_result', 'tool_use_id': 'b', 'is_error': True, 'content': 'missing'},
                {'type': 'tool_result', 'tool_use_id': 'r', 'content': 'Matrix-AI 0.35'}]}},
            {'type': 'result', 'project_root': root},
        ]
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            trace = directory / 'case-0.jsonl'
            original = '\n'.join(json.dumps(e) for e in events)
            trace.write_text(original)
            summary = directory / 'case-0-tools.json'
            scoring.write_tool_audit(trace, summary)
            report = json.loads(summary.read_text())
            self.assertEqual(['returned', 'error', 'unobserved'], [e['status'] for e in report['events']])
            self.assertEqual('<project>/a.md', report['events'][0]['file_path'])
            self.assertNotIn('exit_code', report['events'][1])
            returns = json.loads((directory / report['outputs_file']).read_text())
            self.assertEqual(['Matrix-AI <version>', 'missing'], [e['output'] for e in returns])
            self.assertEqual(original, trace.read_text())
