"""Program checks for the independent admission probe; no real sessions ran."""

import importlib.util
import json
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from kit import KIT
from practice_fixture import put, scope


EVALS = Path(__file__).resolve().parents[1] / 'evals'
sys.path.insert(0, str(EVALS))
try:
    spec = importlib.util.spec_from_file_location('v037_imported_framework_probe', EVALS / 'imported_framework_probe.py')
    probe = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(probe)
finally:
    sys.path.remove(str(EVALS))


class ImportedFrameworkProbe(unittest.TestCase):
    def test_reservation_keeps_first_session_and_refuses_reuse(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'ledger/author.json'
            probe.reserve(path, {'run_id': 'first'})
            with self.assertRaises(FileExistsError):
                probe.reserve(path, {'run_id': 'another'})
            self.assertEqual({'run_id': 'first'}, probe.read_json(path))

    def test_handoff_whitelist_needs_actual_regular_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            public = Path(tmp).resolve() / 'public'
            for name in probe.PUBLIC_FILES:
                path = public / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('synthetic')
            first = public / probe.PUBLIC_FILES[0]
            self.assertEqual(len(probe.PUBLIC_FILES), len(probe.verified_files(public)))
            first.unlink()
            first.symlink_to(public / probe.PUBLIC_FILES[1])
            with self.assertRaisesRegex(ValueError, 'missing or linked'):
                probe.verified_files(public)

    def test_boundary_claim_needs_completed_actual_shell_run(self):
        path = Path('/example/boundary-probe.py')
        item = {'type': 'command_execution', 'command': f'python3 {path} author', 'aggregated_output': 'BOUNDARY_RESULT={"inside":true}'}
        self.assertEqual([], probe.author_boundary([{'type': 'item.started', 'item': item}], path))
        self.assertEqual([{'inside': True}], probe.author_boundary([{'type': 'item.completed', 'item': item}], path))
        self.assertFalse(probe.turn_completed([{'type': 'turn.completed'}, {'type': 'turn.completed'}]))
        self.assertTrue(probe.turn_completed([{'type': 'turn.completed'}]))

    def test_image_is_supplied_to_native_runner_without_changing_policy(self):
        template = probe.read_json(probe.TEMPLATE)
        image = probe.late_game.INPUTS / 'direction.png'
        runner = probe.runner_with_image(template, image)
        self.assertEqual(template['argv'][:-1], runner['argv'][:-2])
        self.assertEqual(['--image=' + str(image), '-'], runner['argv'][-2:])
        self.assertEqual(template['adapter'], runner['adapter'])


class AuthorHandover(unittest.TestCase):
    def setUp(self):
        work = tempfile.TemporaryDirectory()
        self.addCleanup(work.cleanup)
        self.out = Path(work.name).resolve()
        self.project = self.out / 'project'
        self.public = self.project / 'workspace/public'
        self.gate = probe.load('probe_test_gate', KIT / 'matrix/base/tools/stage_gate.py')
        self.registry = self.project / 'matrix/professions/product/profession.json'
        self.registry.parent.mkdir(parents=True)
        shutil.copyfile(KIT / 'matrix/professions/product/profession.json', self.registry)
        self.pm = SimpleNamespace(admission=SimpleNamespace(load_gate=lambda: self.gate))

    def candidate(self, scene=probe.SCENE):
        public, gate = self.public, self.gate
        for name in probe.PUBLIC_FILES:
            put(public, name, 'SIMULATED fixture')
        for source, path, content in (
            (probe.SCENE, probe.SCENE, '<body>SIMULATED board</body>'),
            ('design/preview.png', 'design/preview.png', (probe.late_game.INPUTS / 'direction.png').read_bytes()),
            ('review-input.md', 'product/reviews/合成P-1审阅输入.md', 'SIMULATED\n' + probe.QUOTE),
        ):
            put(public, path, content)
            put(self.project / 'synthetic-input', source, content)

        parts = {
            'brief': put(public, 'product/specs/方向简报.md', 'SIMULATED brief'),
            'scene': put(public, scene, '<body>SIMULATED board</body>'),
            'preview': put(public, probe.SCENE, '<body>SIMULATED board</body>'),
            'samples': put(public, 'content/场内样句.md', 'SIMULATED samples'),
            'screenshot': {'path': 'design/preview.png', 'version': '1',
                           'sha256': probe.sha(public / 'design/preview.png')},
            'practice_profile': put(public, probe.PROFILE, {'schema': 'matrix-practice-profile/1',
                                                            'version': '1', 'scopes': [scope(gate.tone, 'race', direct_manipulation='yes')]}),
        }
        source = 'product/reviews/合成P-1审阅输入.md'
        tone = dict(version='1', genre='SIM', profile='SIM', tone='SIM', core_loop='SIM',
                    references=[dict(name=row['name'], source=row['source'], borrows='SIM', observed='SIM unvisited')
                                for row in probe.REFERENCES], avoid=['Skip the board'], parts=parts,
                    samples=[dict(moment=moment, text=text, consequence=consequence)
                             for moment, text, consequence in probe.late_game.SAMPLES],
                    confirmation=dict(person='SIM', source=source, quote=probe.QUOTE))
        contract = put(public, probe.CONTRACT, '```tone-contract\n' + json.dumps(tone, ensure_ascii=False) + '\n```\n')
        fit = dict(outcome='passed', mode='same_instance', checker=probe.AUTHOR, producer=probe.AUTHOR,
                   tone_contract=gate.tone.direction_binding(probe.CONTRACT, tone),
                   binding_mode='pre_confirmation_direction', artifacts=[parts[key] for key in ('scene', 'preview', 'samples', 'practice_profile')],
                   screenshot=parts['screenshot'], viewport='1280x800', capture='SIM', genre_fit='SIM',
                   application_drift='SIM', copy_fit='SIM')
        put(public, probe.FIT, fit)
        artifacts = [contract, parts['scene']]
        digest = gate.artifact_digest(public, artifacts)
        review = 'product/reviews/'
        put(public, review+'request.json', dict(request_id='SIM', role='product', stage='P-1', scope=['race'],
                                                artifact_sha256=digest, display_evidence=review+'展示.md'))
        put(public, review+'response.json', dict(request_id='SIM', actor='user', choice='confirm', scope=['race'],
                                                 artifact_sha256=digest, source=source, quote=probe.QUOTE))
        put(public, review+'conversation.md', 'SIM P-1 → P-2')
        self.delivery = [gate.tone.direction_delivery(tone)]
        put(public, probe.STAGE_STATE, dict(role='product', current='P-1', next='P-2', blockers=[], scope=['race'],
                                          artifacts=artifacts, tone_contract=contract, tone_fit_review=probe.FIT,
                                          request=review+'request.json', response=review+'response.json',
                                          conversation_check=review+'conversation.md'))

    def handover(self):
        return probe.author_handover(self.pm, self.project, self.out, self.public, 'SIM-RUN', self.delivery)

    def test_fixed_scene_can_be_handed_over_after_shared_gate(self):
        self.candidate()
        shutil.copytree(KIT / 'matrix/base/tools', self.project / 'matrix/base/tools')
        wrapper = self.project / probe.PRODUCT_TONE_WRAPPER
        wrapper.parent.mkdir(parents=True)
        shutil.copyfile(KIT / probe.PRODUCT_TONE_WRAPPER, wrapper)
        for relative in (probe.TONE_TOOL, probe.PRODUCT_TONE_WRAPPER):
            with self.subTest(script=relative):
                command = [sys.executable, '-B', str(self.project / relative),
                           '--project', str(self.public), '--contract', probe.CONTRACT, '--draft']
                receipt = subprocess.run(command, capture_output=True, text=True, check=True)
                shell_command = shlex.join(['/bin/zsh', '-lc', shlex.join(command)])
                self.assertEqual(self.delivery, probe.author_delivery(
                    [self.command_event(shell_command, receipt.stdout)], self.project, self.public))
        with patch.object(probe, 'pm_call') as call:
            paths = self.handover()
        self.assertEqual(paths, [self.public / name for name in probe.PUBLIC_FILES])
        self.assertEqual(call.call_args.args[3], 'hand_over')
        self.assertEqual(call.call_args.kwargs['evidence'],
                         [path.relative_to(self.project).as_posix() for path in paths])
        self.assertIn(probe.SCENE, probe.read_json(self.out / 'gate-precheck.json')['required_outputs'])

    def command_event(self, command, output, code=0):
        return {'type': 'item.completed', 'item': {'type': 'command_execution',
                'command': command, 'exit_code': code, 'aggregated_output': output}}

    def test_echoed_json_wrong_installed_path_or_scope_is_not_an_author_receipt(self):
        self.candidate()
        output = json.dumps({'allowed': True, 'delivery': self.delivery[0]})
        command = [sys.executable, '-B', str(self.project / probe.TONE_TOOL),
                   '--project', str(self.public), '--contract', probe.CONTRACT, '--draft']
        echo = 'echo ' + shlex.quote(shlex.join(command)) + '; echo ' + shlex.quote(output)
        alternate = [
            self.command_event(echo, output),
            self.command_event(shlex.join(command) + ' && echo ' + shlex.quote(output), output),
            self.command_event(shlex.join([*command[:2], str(self.public / 'tone_contract.py'), *command[3:]]), output),
            self.command_event(shlex.join([*command[:4], str(self.project), *command[5:]]), output),
            self.command_event(shlex.join([*command[:6], 'product/specs/other.md', '--draft']), output),
            self.command_event(shlex.join(command), output, code=1),
        ]
        self.assertEqual([], probe.author_delivery(alternate, self.project, self.public))

    def test_extra_scene_is_rejected_before_handover(self):
        self.candidate('product/specs/方向场景.md')
        with patch.object(probe, 'pm_call') as call:
            with self.assertRaisesRegex(ValueError, 'undeclared scene output'):
                self.handover()
            call.assert_not_called()
        self.assertFalse((self.out / 'gate-precheck.json').exists())

    def test_escaped_path_cannot_expand_handover_list(self):
        self.candidate()
        state = probe.read_json(self.public / probe.STAGE_STATE)
        state['artifacts'].append({'path': '../outside.md', 'sha256': '0'*64})
        put(self.public, probe.STAGE_STATE, state)
        with patch.object(probe, 'pm_call') as call:
            with self.assertRaisesRegex(ValueError, r'undeclared framework output: \.\./outside.md'):
                self.handover()
            call.assert_not_called()

    def test_extra_preview_is_rejected_before_handover(self):
        self.candidate()
        tone = self.gate.tone.read(self.public, probe.CONTRACT)
        tone['parts']['preview'] = put(self.public, 'design/other.html', '<body>Different preview</body>')
        put(self.public, probe.CONTRACT, '```tone-contract\n' + json.dumps(tone, ensure_ascii=False) + '\n```\n')
        with patch.object(probe, 'pm_call') as call:
            with self.assertRaisesRegex(ValueError, 'undeclared preview output'):
                self.handover()
            call.assert_not_called()

    def test_undeclared_path_from_shared_gate_closure_is_rejected(self):
        self.candidate()
        extra = 'product/specs/extra-proof.md'
        put(self.public, extra, 'SIM extra artifact')
        original = self.gate.framework_outputs

        def outputs(*args, **kwargs):
            complete, paths = original(*args, **kwargs)
            return complete, paths | {extra}

        with patch.object(self.gate, 'framework_outputs', side_effect=outputs), patch.object(probe, 'pm_call') as call:
            with self.assertRaisesRegex(ValueError, 'undeclared framework output: ' + extra):
                self.handover()
            call.assert_not_called()

    def test_public_registry_cannot_override_installed_requirements(self):
        self.candidate()
        registry = probe.read_json(self.registry)
        registry['framework_requirements'] = {}
        put(self.public, 'matrix/professions/product/profession.json', registry)
        with patch.object(probe, 'pm_call') as call:
            self.handover()
        gate = probe.read_json(self.out / 'gate-precheck.json')
        self.assertEqual({row['requirement'] for row in gate['completed']},
                         {'tone_contract', 'direction_profile', 'direction_fit'})
        self.assertNotIn('workspace/public/matrix/professions/product/profession.json', call.call_args.kwargs['evidence'])


    def test_direction_must_have_a_current_author_delivery_receipt(self):
        self.candidate()
        self.delivery[0]['status'] = 'stale'
        with patch.object(probe, 'pm_call') as call:
            with self.assertRaisesRegex(ValueError, 'no actual author --draft receipt'):
                self.handover()
            call.assert_not_called()

    def test_reply_quote_cannot_drop_original_prefix(self):
        self.candidate()
        response = probe.read_json(self.public / 'product/reviews/response.json')
        response['quote'] = response['quote'].split('：', 1)[1]
        put(self.public, 'product/reviews/response.json', response)
        with patch.object(probe, 'pm_call') as call:
            with self.assertRaisesRegex(ValueError, 'verbatim synthetic input'):
                self.handover()
            call.assert_not_called()

    def test_synthetic_preview_does_not_count_as_a_second_reference(self):
        self.candidate()
        tone = self.gate.tone.read(self.public, probe.CONTRACT)
        tone['references'][1]['source'] = probe.SCENE
        put(self.public, probe.CONTRACT, '```tone-contract\n' + json.dumps(tone, ensure_ascii=False) + '\n```\n')
        with patch.object(probe, 'pm_call') as call:
            with self.assertRaisesRegex(ValueError, 'two actual external game references'):
                self.handover()
            call.assert_not_called()

    def test_copy_helper_preserves_fixture_bytes_and_source_quote(self):
        self.candidate()
        original = self.project / 'synthetic-input'
        quote = '合成审阅输入：逐字保留！'
        expected = ('# SIMULATED\r\n\r\n' + quote + '\r\n').encode('utf-8')
        (original / probe.seed.REVIEW_SOURCE).write_bytes(expected)
        result = probe.seed.copy_inputs(original, self.public)
        self.assertEqual(expected, (self.public / probe.seed.REVIEW_OUTPUT).read_bytes())
        self.assertEqual(quote, result['quote'])
        self.assertEqual(probe.seed.REVIEW_OUTPUT, result['source'])
