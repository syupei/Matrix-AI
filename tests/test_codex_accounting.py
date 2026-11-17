import json
from pathlib import Path
import sys
import tempfile
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'evals'))
from codex_accounting import collect


class CodexAccountingTest(unittest.TestCase):
    def test_native_windows_preserve_only_requested_public_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            thread = 'c1234567-d123-4321-1123-c123456789ab'
            trace = root / 'cli.jsonl'
            trace.write_text('prefix from stderr\n' + '\n'.join(json.dumps(event) for event in (
                {'type': 'thread.started', 'thread_id': thread}, {'type': 'turn.started'},
                {'type': 'turn.completed', 'usage': {'input_tokens': 20, 'cached_input_tokens': 8,
                                                      'output_tokens': 10, 'reasoning_output_tokens': 4}},
            )))
            native = root / '2026/11/17' / f'rollout-{thread}.jsonl'
            native.parent.mkdir(parents=True)
            windows = [{'timestamp': f'2026-11-17T16:4{number}:00Z', 'payload': {'type': 'token_count', 'rate_limits': {
                'primary': {'used_percent': percent, 'window_minutes': 10080, 'resets_at': 1795000000},
                'credits': {'balance': 'private'}, 'plan_type': 'private',
            }}} for number, percent in enumerate((41, 42))]
            native.write_text('\n'.join(json.dumps(event) for event in windows))
            result = collect(trace, root)
            self.assertEqual(12, result['tokens']['uncached_input_tokens'])
            self.assertEqual(10, result['tokens']['output_tokens'])
            self.assertEqual(4, result['tokens']['reasoning_output_tokens'])
            self.assertEqual([{'timestamp': '2026-11-17T16:41:00Z', 'used_percent': 42,
                               'window_minutes': 10080, 'resets_at': 1795000000}], result['native_limit_windows'])
            self.assertNotIn('private', json.dumps(result))

    def test_missing_usage_or_limit_stays_unknown(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            trace = root / 'cli.jsonl'
            trace.write_text('{"type":"turn.completed","usage":{"input_tokens":5,"output_tokens":2}}\n')
            result = collect(trace, root)
            self.assertEqual('unknown', result['limit_status'])
            self.assertIsNone(result['tokens']['cached_input_tokens'])
            self.assertIsNone(result['tokens']['uncached_input_tokens'])


if __name__ == '__main__':
    unittest.main()
