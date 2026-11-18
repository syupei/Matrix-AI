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
from practice_fixture import put, scope, capture_binding


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

    def test_pending_candidate_input_has_no_confirmation_label_and_is_recaptured(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary).resolve()

            def capture_candidate(root, relative):
                html = (root / relative).read_text()
                self.assertIn('P-1 待审方向候选', html)
                self.assertIn('P-1 候选待审', html)
                self.assertNotIn('已确认', html)
                target = root / 'visual-evidence/preview.png'
                target.parent.mkdir()
                shutil.copyfile(probe.late_game.INPUTS / 'direction.png', target)
                return {'status': 'captured', 'screenshot': 'visual-evidence/preview.png',
                        'viewport': [1280, 800], 'sha256': probe.sha(target)}

            with patch.object(probe, 'capture', side_effect=capture_candidate) as capture:
                probe.populate(project)
            capture.assert_called_once_with(project / 'synthetic-input', probe.seed.SCENE)
            source = project / 'synthetic-input'
            self.assertNotIn('方向批准覆盖', (source/'genre-dice.md').read_text())
            receipt = probe.read_json(source/'visual-evidence/capture.json')
            self.assertEqual(probe.late_game.FILE_HASHES['direction.html'], receipt['derived_from_sha256'])
            self.assertNotEqual(receipt['derived_from_sha256'], receipt['preview_sha256'])
            self.assertIn('--check', probe.author_prompt(project))
            self.assertIn('不修改任何输入副本', probe.author_prompt(project))


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
        public,gate=self.public,self.gate
        for name in probe.PUBLIC_FILES:put(public,name,'SIMULATED fixture')
        source=self.project/'synthetic-input'
        for name,body in ((probe.seed.SCENE,'<body>Read-only reference</body>'),(probe.seed.SCREENSHOT,(probe.late_game.INPUTS/'direction.png').read_bytes()),
                          (probe.seed.CAPTURE,{'source':'SIM reference capture'}),(probe.seed.REVIEW_SOURCE,probe.QUOTE)):
            put(source,name,body)
        probe.seed.seal_inputs(source);probe.seed.copy_inputs(source,public)
        parts=dict(brief=put(public,'product/specs/方向简报.md','SIMULATED brief'),
            scene=put(public,scene,'<body><button>SIM author prototype</button></body>'),
            preview=put(public,probe.SCENE,'<body><button>SIM author prototype</button></body>'),
            samples=put(public,'content/场内样句.md','SIM samples'),screenshot=put(public,probe.PREVIEW_SCREENSHOT,(probe.late_game.INPUTS/'direction.png').read_bytes()),
            practice_profile=put(public,probe.PROFILE,dict(schema='matrix-practice-profile/1',version='1',scopes=[scope(gate.tone,'race',direct_manipulation='yes')])))
        original_binding=capture_binding([parts['preview']]);original_binding['source']=probe.PREVIEW_CAPTURE
        original_binding['receipt']=put(public,probe.PREVIEW_CAPTURE,dict(original_binding,screenshot_sha256=parts['screenshot']['sha256']))
        tone=dict(viewport='1280x800',capture_binding=original_binding,version='1',genre='SIM',profile='SIM',tone='SIM',core_loop='SIM',
            references=[dict(name=row['name'],source=row['source'],borrows='SIM',observed='SIM unvisited') for row in probe.REFERENCES],
            avoid=['Skip board'],parts=parts,samples=[dict(moment=m,text=t,consequence=c) for m,t,c in probe.late_game.SAMPLES])
        contract=put(public,probe.CONTRACT,'```tone-contract\n'+json.dumps(tone,ensure_ascii=False)+'\n```\n')
        reviewed=[parts[key] for key in ('scene','preview','samples','practice_profile')]
        screenshot=put(public,probe.FIT_SCREENSHOT,(probe.late_game.INPUTS/'direction.png').read_bytes())
        fit_binding=capture_binding(reviewed);fit_binding['source']=probe.FIT_CAPTURE
        fit_binding['receipt']=put(public,probe.FIT_CAPTURE,dict(fit_binding,screenshot_sha256=screenshot['sha256']))
        put(public,probe.AUTHOR_SELF,dict(status='author_self_check_only',pending=['independent review and control projection']))
        put(public,'product/reviews/conversation.md','SIM P-1 -> P-2')
        put(public,probe.STAGE_STATE,dict(role='product',current='P-1',next='P-2',scope=['race'],blockers=[],artifacts=[contract,parts['scene']],
            tone_contract=contract,conversation_check='product/reviews/conversation.md',request='pending-request.json',response='pending-response.json',tone_fit_review='pending-fit.json'))
        self.delivery=[gate.tone.direction_delivery(tone)]
        events=[]
        for name,binding in ((probe.PREVIEW_SCREENSHOT,original_binding),(probe.FIT_SCREENSHOT,fit_binding)):
            events.append(dict(status='captured',format='author-requested-capture/1',screenshot=name,preview=probe.SCENE,sha256=probe.sha(public/name),capture_binding=binding))
        (self.out/'author-capture-events.jsonl').write_text(''.join(json.dumps(row)+'\n' for row in events))

    def handover(self):
        return probe.author_handover(self.pm, self.project, self.out, self.public, 'SIM-RUN', self.delivery)

    def test_unconfirmed_draft_handover_does_not_require_future_checker_gate(self):
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
        self.assertEqual('pending_actual_independent_review',probe.read_json(self.out/'author-draft-precheck.json')['completion_gate'])
        self.assertFalse((self.out/'gate-precheck.json').exists())

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

    def test_author_cannot_preapprove_unseen_results(self):
        self.candidate()
        tone=self.gate.tone.read(self.public,probe.CONTRACT)
        tone['confirmation']={'person':'SIM','quote':'SIM prior approval'}
        put(self.public,probe.CONTRACT,'```tone-contract\n'+json.dumps(tone)+'\n```\n')
        with patch.object(probe,'pm_call') as call:
            with self.assertRaisesRegex(ValueError,'must not prefill confirmation'):
                self.handover()
            call.assert_not_called()

    def test_fit_capture_must_bind_current_author_materials(self):
        self.candidate()
        capture=probe.read_json(self.public/probe.FIT_CAPTURE)
        capture['artifacts'][0]['sha256']='0'*64
        put(self.public,probe.FIT_CAPTURE,capture)
        rows=[json.loads(line) for line in (self.out/'author-capture-events.jsonl').read_text().splitlines()]
        rows[-1]['capture_binding']['receipt']['sha256']=probe.sha(self.public/probe.FIT_CAPTURE)
        (self.out/'author-capture-events.jsonl').write_text(''.join(json.dumps(row)+'\n' for row in rows))
        with patch.object(probe,'pm_call') as call:
            with self.assertRaisesRegex(ValueError,'actual four author materials'):
                self.handover()
            call.assert_not_called()

    def test_static_png_and_claimed_receipt_cannot_replace_actual_author_capture(self):
        self.candidate()
        (self.out/'author-capture-events.jsonl').unlink()
        with patch.object(probe,'pm_call') as call:
            with self.assertRaisesRegex(ValueError,'no actual author capture'):
                self.handover()
            call.assert_not_called()

    def test_reference_mutation_is_rejected_and_author_preview_is_distinct(self):
        self.candidate()
        self.assertNotEqual(probe.SCENE,probe.seed.SCENE)
        put(self.project/'synthetic-input',probe.seed.SCENE,'Changed reference')
        with patch.object(probe,'pm_call') as call:
            with self.assertRaisesRegex(ValueError,'immutable reference input changed'):self.handover()
            call.assert_not_called()

    def test_workflow_pending_in_blockers_stops_before_checker(self):
        self.candidate();state=probe.read_json(self.public/probe.STAGE_STATE)
        state['blockers']=['待独审'];put(self.public,probe.STAGE_STATE,state)
        with patch.object(probe,'pm_call') as call:
            with self.assertRaisesRegex(ValueError,'business blockers'):self.handover()
            call.assert_not_called()

    def test_direction_must_have_a_current_author_delivery_receipt(self):
        self.candidate()
        self.delivery[0]['status'] = 'stale'
        with patch.object(probe, 'pm_call') as call:
            with self.assertRaisesRegex(ValueError, 'no actual author --draft receipt'):
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
        probe.seed.seal_inputs(original)
        result = probe.seed.copy_inputs(original, self.public)
        self.assertEqual(expected, (self.public / probe.seed.REVIEW_OUTPUT).read_bytes())
        self.assertEqual(quote, result['quote'])
        self.assertEqual(probe.seed.REVIEW_OUTPUT, result['source'])
        self.assertTrue(probe.seed.check_inputs(original, self.public)['unchanged'])
        changed = self.public / probe.seed.REVIEW_OUTPUT
        changed.write_text('<title>已确认</title>')
        with self.assertRaisesRegex(ValueError, 'copied synthetic input changed'):
            probe.seed.check_inputs(original, self.public)
        self.assertEqual('<title>已确认</title>', changed.read_text())


class ComposedController(unittest.TestCase):
    """Real DB operations; all business/model reports are explicitly SIMULATED."""
    def fixture(self):
        from test_expert_packages import Experts, pm
        f=Experts(methodName='runTest');f.setUp();self.addCleanup(f.doCleanups)
        f.composed_package(validate=False)
        # The fixture supplies real producer handbacks. Replace its old constructed
        # projection with the production evaluation controller under test.
        shutil.rmtree(f.scenario_view)
        author=f.e.validation_run(pm.api(),f.root,'VIEW-author-run')
        reviewer=f.e.validation_run(pm.api(),f.root,'VIEW-review-run')
        out=f.root/'probe-evidence';out.mkdir()
        return f,pm,author,reviewer,out

    def test_controller_derives_only_controls_and_validates_real_two_producer_lifecycle(self):
        f,pm,author,reviewer,out=self.fixture()
        originals={path:probe.sha(f.root/path) for path in [*author['handover']['files'], f.report_ref]}
        view=probe.assemble_scenario(pm,f.root,out,author,reviewer,f.root/f.report_ref,
            contract_path=pm.admission.load_gate().tone.DEFAULT_PATH,stage_template='stage-template.json',fit_path='fit.json',state_path='stage.json')
        params=dict(f.validation_params,evidence=dict(f.validation_params['evidence'],scenario_view=view))
        result=f.e.validate(pm.api(),f.root,params,operator='SIM-controller')
        self.assertEqual('validated',result['state'])
        projection=probe.read_json(out/'scenario-projection.json')
        self.assertNotEqual(projection['author_contract_sha256'],projection['projected_contract_sha256'])
        self.assertEqual(6,len(projection['context']['control_derivations']))
        self.assertEqual(originals,{path:probe.sha(f.root/path) for path in originals})
        self.assertTrue(projection['synthetic'])
        self.assertNotEqual('enabled',result['state'])

    def test_controller_does_not_repair_failed_independent_report(self):
        f,pm,author,reviewer,out=self.fixture()
        report=probe.read_json(f.root/f.report_ref);report['passed']=False
        probe.write_json(f.root/f.report_ref,report)
        with self.assertRaisesRegex(ValueError,'cannot create or repair'):
            probe.assemble_scenario(pm,f.root,out,author,reviewer,f.root/f.report_ref)
        self.assertFalse(probe.read_json(f.root/f.report_ref)['passed'])

    def test_prepare_binds_actual_admitted_sources_and_real_planned_task(self):
        f,pm,author,reviewer,out=self.fixture()
        business='SYNTHETIC bounded business: preserve race scope; no production approval.'
        put(f.root,'synthetic-input/genre-dice.md',business)
        boundary=probe.load('probe_source_test_boundary',KIT/'matrix/orchestration/tools/isolated_runner.py')
        with patch.multiple(probe,AUTHOR='VIEW-author',REVIEWER='VIEW-checker'):
            probe.prepare_author_instances(pm,f.root,out,boundary)
        _,manifest=f.e.read(pm.api(),f.root,f.ident)
        with patch.multiple(probe,IDENTITY=f.ident,AUTHOR='VIEW-author',REVIEWER='VIEW-checker'):
            context=probe.prepare_source_context(pm,f.root,out,manifest)
            prepared=probe.prepare_author_task(pm,f.root,out,boundary,context)
        with pm.connect(f.root,readonly=True) as db:
            task=pm.task_map(db)[probe.TASK_ID]
            sources=pm.integrity.records(db,'input_admission')
            runs=pm.integrity.records(db,'launch')
        self.assertEqual('planned',prepared['state'])
        self.assertEqual(context['admitted_inputs'],task['admitted_inputs'])
        self.assertEqual(2,len(context['admitted_inputs']))
        self.assertIn(business,(f.root/context['inputs'][0]).read_text())
        self.assertIn('experts/sim-expert/1/METHODS.md',context['inputs'])
        for key in context['admitted_inputs']:
            source=sources[key]
            self.assertEqual('admitted',source['state'])
            self.assertEqual(probe.sha(f.root/source['path']),source['sha256'])
        self.assertFalse(any(run.get('task_id')==probe.TASK_ID for run in runs.values()))

    def test_task_requires_explicit_current_source_context(self):
        for invalid in (None,{'inputs':['matrix/fake-installed-rule.md']},
                        {'inputs':['business.md'],'admitted_inputs':[]}):
            with self.assertRaisesRegex(ValueError,'prepared admitted source_context'):
                probe.author_task(Path('/SIM/project'),invalid)

    def test_source_preparation_preserves_existing_unconfirmed_config(self):
        from test_expert_packages import Experts, pm
        f=Experts(methodName='runTest');f.setUp();self.addCleanup(f.doCleanups)
        f.write('expert-professions.json',dict(schema='matrix-expert-professions/1',professions=['product'],configured_by='SIM',authorization='SIM'))
        params=f.prepare_params('product');params['review']['review_points']=[dict(who='master',what='Synthetic independent scope')]
        f.e.adapt(pm.api(),f.root,params)
        out=f.root/'probe-evidence';out.mkdir()
        put(f.root,'synthetic-input/genre-dice.md','SYNTHETIC source')
        config=put(f.root,'management/instance-config.json',dict(entries=[],user_note='keep existing human draft'))
        _,manifest=f.e.read(pm.api(),f.root,f.ident)
        with patch.object(probe,'IDENTITY',f.ident):
            with self.assertRaisesRegex(ValueError,'preserve the existing configuration'):
                probe.prepare_source_context(pm,f.root,out,manifest)
        self.assertEqual(config['sha256'],probe.sha(f.root/config['path']))
        self.assertFalse((f.root/'management/admission-inputs/import-probe-p1').exists())

    def test_prompts_separate_self_check_and_actual_independent_review(self):
        root=Path('/SIM/project')
        author=probe.author_prompt(root)
        self.assertIn('不得包含confirmation',author)
        self.assertIn('不生成独立fit',author)
        self.assertNotIn('mode=same_instance',author)
        self.assertIn('capture_preview.py',author)
