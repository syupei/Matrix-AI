import base64
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest


EVALS = Path(__file__).resolve().parents[1] / 'evals'
sys.path.insert(0, str(EVALS))
import scoring_packet as packet


class ScoringPacketTest(unittest.TestCase):
    def test_missing_or_duplicate_guide_anchor_refuses_packet(self):
        for guide in ('body', '<!-- scoring-core:start -->x<!-- scoring-core:start --><!-- scoring-core:end -->'):
            with self.assertRaisesRegex(ValueError, 'anchor'):
                packet.section(guide, 'scoring-core')

    def test_full_reply_and_deep_business_record_are_included(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            suite = root/'suite.json'
            suite.write_text(json.dumps({'rubric_revision': 'test', 'cases': [{'id': 'one', 'turns': ['input'], 'criteria': ['ok']}]}))
            guide = root/'README.md'
            guide.write_text('<!-- scoring-core:start -->rules<!-- scoring-core:end -->\n'
                             '<!-- scoring-case-notes:start -->notes<!-- scoring-case-notes:end -->')
            reply = 'r' * 1900 + 'VISIBLE_END_OF_REPLY'
            for side in ('X', 'Y'):
                folder = root/'ws/one'/side
                deep = folder/'one-artifacts/a/b/c/d/e/f/proof.md'
                deep.parent.mkdir(parents=True)
                deep.write_text('COMPLETE_DEEP_PROOF')
                (folder/'one-0.md').write_text(reply)
            _, manifest = packet.prepare(root, ['one'], suite, guide)
            text = Path(manifest['business_materials']['path']).read_text()
            self.assertEqual(2, text.count('VISIBLE_END_OF_REPLY'))
            self.assertEqual(2, text.count('COMPLETE_DEEP_PROOF'))
            self.assertEqual(4, len(manifest['files']))

    def test_visual_score_needs_actual_native_image_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            scorer = root/'scorer'
            scorer.mkdir()
            thread = 'a1234567-b123-4123-a123-a123456789ab'
            (scorer/'run.log').write_text(json.dumps({'type': 'thread.started', 'thread_id': thread})+'\n')
            sessions = root/'sessions'
            native = sessions/'2026/11/18'/f'rollout-{thread}.jsonl'
            native.parent.mkdir(parents=True)
            image = b'fixed image bytes'
            digest = hashlib.sha256(image).hexdigest()
            manifest = {'images': [{'sha256': digest}]}
            native.write_text('{"type":"response_item","payload":{"type":"message","content":[]}}\n')
            with self.assertRaisesRegex(ValueError, 'did not receive'):
                packet.verify_received_images(scorer, manifest, sessions)
            url = 'data:image/png;base64,' + base64.b64encode(image).decode()
            native.write_text(json.dumps({'type':'response_item','payload':{'type':'message',
                              'content':[{'type':'input_image','image_url':url}]}})+'\n')
            result = packet.verify_received_images(scorer, manifest, sessions)
            self.assertEqual('received', result['status'])
            self.assertEqual([digest], result['received'])


if __name__ == '__main__':
    unittest.main()
