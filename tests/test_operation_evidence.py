import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import shutil

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'evals'))

from operation_evidence import check, check_direction, snapshot, TONE_PRODUCT_ENTRY, TONE_TOOL
from fixtures import late_game


class OperationEvidenceTest(unittest.TestCase):
    def test_real_product_receipt_and_frozen_failure_examples(self):
        script = ROOT / 'src/professions/product/skills/matrix-product/scripts/product_contract.py'
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / 'product/specs/draft.md'
            path.parent.mkdir(parents=True)
            reply = '本轮已形成局部草稿。[草稿](product/specs/draft.md)'
            call = [sys.executable, str(script), '--root', str(root), 'reply-receipt',
                    '--kind', 'draft', '--path', 'product/specs/draft.md', '--marker', '账号草稿']
            self.assertTrue(check(root, 'draft', reply, [], {}, {})['errors'])
            self.assertTrue(check(root, 'feedback', '已记录本批第一条反馈。', [], {}, {})['errors'])
            self.assertFalse(check(root, 'feedback', '已收到第一条，我等你补充。', [], {}, {})['errors'])
            self.assertEqual(2, subprocess.run(call, capture_output=True).returncode)

            path.write_text('# 账号草稿\n')
            result = subprocess.run(call, capture_output=True, text=True, check=True)
            receipt = json.loads(result.stdout)
            self.assertEqual(receipt['sha256'], hashlib.sha256(path.read_bytes()).hexdigest())
            event = {'type': 'item.completed',
                     'item': {'id': '1', 'type': 'command_execution',
                              'command': ' '.join(call), 'exit_code': 0,
                              'aggregated_output': result.stdout}}
            after = snapshot(root)
            self.assertFalse(check(root, 'draft', reply, [event], {}, after)['errors'])
            self.assertTrue(check(root, 'draft', reply, [event], after, after)['errors'])
            self.assertTrue(check(root, 'draft', reply, [], {}, after)['errors'])
            path.write_text('# 后续变更\n')
            self.assertTrue(check(root, 'draft', reply, [event], {}, snapshot(root))['errors'])

            missing_marker = subprocess.run(call, capture_output=True)
            self.assertEqual(2, missing_marker.returncode)
            call[call.index('--path') + 1] = '../out.md'
            self.assertEqual(2, subprocess.run(call, capture_output=True).returncode)


class DirectionOperationEvidenceTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name).resolve()
        self.preview = 'design/direction/sample.html'
        self.claim = f'已完成风脊竞走方向样张：[可点预览]({self.preview})。'

    def event(self, command, output, exit_code=0):
        return {'type': 'item.completed', 'item': {'type': 'command_execution', 'command': command,
                'exit_code': exit_code, 'aggregated_output': output}}

    def audit(self, reply, events=(), *, after=None, expects_receipt=False):
        return check_direction(self.root, reply, events, {}, snapshot(self.root, 'direction') if after is None else after,
                               self.preview, expects_receipt)

    def test_frozen_unsupported_reply_and_post_turn_harness_capture(self):
        self.assertTrue(self.audit(self.claim)['errors'])
        late_game.put(self.root, self.preview, '<html><main>Board</main></html>')
        before_capture = snapshot(self.root, 'direction')
        late_game.fixed(self.root, 'direction.png', 'visual-evidence/preview.png')
        evidence = self.audit(self.claim + '已完成截图。', [self.event(f'cat {self.preview}', '<html><main>Board</main></html>')],
                              after=before_capture)
        self.assertFalse(evidence['pre_final_pictures'])
        self.assertIn('缺作者答复前的实际截图', evidence['errors'][0])
        self.assertFalse(self.audit('还没生成或保存预览。')['errors'])

    def test_baseline_preview_and_successful_readback_needs_no_new_interface(self):
        body = '<html><main>Board</main></html>'
        late_game.put(self.root, self.preview, body)
        evidence = self.audit(self.claim, [self.event(f'/bin/zsh -lc "cat {self.preview}"', body)])
        self.assertFalse(evidence['errors'])
        self.assertEqual([{'line': 1, 'path': self.preview}], evidence['observed_preview_reads'])
        self.assertTrue(self.audit(self.claim, [self.event(f'cat {self.preview}', body, 1)])['errors'])

    def test_completed_language_and_unlinked_path_require_actual_output(self):
        for reply in ('已经完成，design/direction/sample.html。',
                      '做好了，原型保存在 `design/direction/sample.html`。',
                      '方向预览已经完成。', '做好了这份方向样张。'):
            with self.subTest(reply=reply):
                evidence = self.audit(reply)
                self.assertTrue(evidence['claims'])
                self.assertTrue(evidence['errors'])
        for reply in ('尚未完成方向样张。', '还没有生成预览。', '以后可以保存 design/direction/sample.html。'):
            self.assertFalse(self.audit(reply)['claims'])

    def test_real_draft_receipt_must_match_files_and_precede_reply(self):
        late_game.populate(self.root, 'late_rendering_solution')
        base = ROOT / 'src/base'
        (self.root / TONE_TOOL).parent.mkdir(parents=True)
        for source in (base/'tools/tone_contract.py', base/'tools/practice_profiles.py', base/'tools/review_evidence.py'):
            shutil.copyfile(source, (self.root / TONE_TOOL).parent / source.name)
        shutil.copyfile(base/'practice-profile-example-game.json', (self.root / TONE_TOOL).parents[1]/'practice-profile-example-game.json')
        wrapper = self.root / TONE_PRODUCT_ENTRY
        wrapper.parent.mkdir(parents=True)
        shutil.copyfile(ROOT/'src/professions/product/skills/matrix-product/scripts/tone_contract.py', wrapper)
        manifest = {path.relative_to('kit').as_posix(): hashlib.sha256((self.root/path).read_bytes()).hexdigest()
                    for path in (TONE_TOOL, TONE_PRODUCT_ENTRY)}
        (self.root/'kit/MANIFEST.json').write_text(json.dumps({'files': manifest}))
        argv = ['python3', '-B', str(TONE_TOOL), '--project', '.', '--draft']
        result = subprocess.run(argv, cwd=self.root, capture_output=True, text=True, check=True)
        observed = self.event(' '.join(argv), result.stdout)
        good = self.audit(self.claim + '已保存截图。', [observed], expects_receipt=True)
        self.assertFalse(good['errors'])
        self.assertEqual('direction-delivery/1', good['receipts'][0]['delivery']['format'])
        self.assertTrue(self.audit(self.claim, [self.event('echo tone_contract.py --draft', result.stdout)], expects_receipt=True)['errors'])
        wrapper_argv = ['python3', '-B', str(TONE_PRODUCT_ENTRY), '--project', '.', '--draft']
        wrapper_output = subprocess.check_output(wrapper_argv, cwd=self.root, text=True)
        wrapper_event = self.event(' '.join(wrapper_argv), wrapper_output)
        self.assertFalse(self.audit(self.claim, [wrapper_event], expects_receipt=True)['errors'])
        alias = self.root.parent / (self.root.name + '-path-alias')
        alias.symlink_to(self.root, target_is_directory=True)
        self.addCleanup(alias.unlink)
        evidence = check_direction(alias, self.claim, [wrapper_event], {}, snapshot(self.root, 'direction'), self.preview, True)
        self.assertFalse(evidence['errors'])
        self.assertEqual(1, len(evidence['receipts']))
        self.assertTrue(self.audit(self.claim, [self.event('python3 product/tone_contract.py --project . --draft',
                                                         wrapper_output)], expects_receipt=True)['errors'])
        wrapper.write_bytes(wrapper.read_bytes() + b'\n# modified wrapper\n')
        self.assertTrue(self.audit(self.claim, [wrapper_event], expects_receipt=True)['errors'])
        final = {'type': 'item.completed', 'item': {'type': 'agent_message', 'text': self.claim}}
        self.assertFalse(self.audit(self.claim, [final, observed], expects_receipt=True)['receipts'])
        late_game.put(self.root, self.preview, '<html><main>Later bytes</main></html>')
        self.assertTrue(self.audit(self.claim, [observed], expects_receipt=True)['errors'])



if __name__ == '__main__':
    unittest.main()
