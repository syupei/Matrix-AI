"""The stage gate uses declared activities, current artifacts and real evidence paths."""
import importlib.util
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from kit import KIT
from practice_fixture import PIXEL, direction, fit_record, practice_record, put, scope


spec = importlib.util.spec_from_file_location('practice_gate_test', KIT/'matrix/base/tools/stage_gate.py')
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)
tone = gate.tone


class PracticeStages(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.artifact = put(self.root, 'render/scenario.html', '<main>Synthetic scenario</main>')

    def state(self, stage, next_stage, rows=None, label='Arbitrary display label'):
        ref, _ = direction(self.root, tone, rows, label=label)
        record = put(self.root, 'conversation.md', stage + ' → ' + next_stage)
        return dict(role='solution', current=stage, next=next_stage, scope=['workspace'], blockers=[],
                    artifacts=[self.artifact], conversation_check=record['path'], tone_contract=ref,
                    practice_evidence={})

    def add_record(self, state, key, sid='workspace', **fields):
        ref = practice_record(self.root, tone, state['tone_contract'], key, [self.artifact], sid, **fields)
        state['practice_evidence'].setdefault(key, {})[sid] = ref
        return ref

    def test_default_profile_is_required_regardless_of_label(self):
        state = self.state('E-2.1', 'E-2.2', label='工具与业务')
        self.assertTrue(gate.check(self.root, state)['allowed'])
        state.pop('tone_contract')
        with self.assertRaisesRegex(ValueError, 'current tone contract'):
            gate.check(self.root, state)
        for extra in ({'traffic_peak':None}, {'new_feature':{'value':'no','basis':'unknown'}}):
            row = scope(tone)
            row['features'].update(extra)
            if 'traffic_peak' in extra:
                row['features'].pop('traffic_peak')
            state = self.state('E-2.1','E-2.2',[row])
            with self.assertRaisesRegex(ValueError,'all seven practice features'):
                gate.check(self.root,state)

    def test_pending_feature_blocks_stage_that_depends_on_it(self):
        state = self.state('E-2.1','E-2.2',[scope(tone, traffic_peak='pending')])
        gate.check(self.root,state)
        state.update(current='E-2.2',next='E-2.3')
        put(self.root,'conversation.md','E-2.2 → E-2.3')
        with self.assertRaisesRegex(ValueError,'unresolved practice feature.*traffic_peak'):
            gate.check_entry(self.root,state)
        with self.assertRaisesRegex(ValueError,'unresolved practice feature.*traffic_peak'):
            gate.check(self.root,state)

    def test_game_cannot_skip_rendering_or_tryout_after_renaming_label(self):
        state = self.state('E-2.2','E-2.3',[scope(tone,appearance_target='yes',direct_manipulation='yes')],
                           label='普通管理工具')
        gate.check_entry(self.root,state)
        with self.assertRaisesRegex(ValueError,'rendering_choice'):
            gate.check(self.root,state)
        self.add_record(state,'rendering_choice')
        with self.assertRaisesRegex(ValueError,'appearance_proof'):
            gate.check(self.root,state)
        self.add_record(state,'appearance_proof',screenshot=put(self.root,'proof.png',PIXEL))
        with self.assertRaisesRegex(ValueError,'playable_prototype'):
            gate.check(self.root,state)
        self.add_record(state,'playable_prototype')
        self.assertTrue(gate.check(self.root,state)['allowed'])

    def test_mixed_project_keeps_obligations_in_their_scope(self):
        game = scope(tone,'game',appearance_target='yes')
        mis = scope(tone,'mis',traffic_peak='yes')
        state = self.state('E-2.2','E-2.3',[game,mis])
        self.add_record(state,'rendering_choice','game')
        self.add_record(state,'appearance_proof','game',screenshot=put(self.root,'proof.png',PIXEL))
        with self.assertRaisesRegex(ValueError,'mis: missing practice evidence: load_test_plan'):
            gate.check(self.root,state)
        self.add_record(state,'load_test_plan','mis')
        self.assertTrue(gate.check(self.root,state)['allowed'])
        state.update(scope=['game','mis'],practice_scope=['mis'])
        with self.assertRaisesRegex(ValueError,'match the worked activity scope'):
            gate.check(self.root,state)
        state['scope']=['mis']
        state['practice_evidence'].pop('appearance_proof')
        self.assertTrue(gate.check(self.root,state)['allowed'])

    def test_skeleton_requires_capture_or_real_manual_record_and_current_fit(self):
        state = self.state('E-2.3','E-2.4',[scope(tone,appearance_target='yes')])
        self.add_record(state,'rendering_choice')
        self.add_record(state,'appearance_proof',screenshot=put(self.root,'proof.png',PIXEL))
        self.add_record(state,'core_scene_skeleton')
        with self.assertRaisesRegex(ValueError,'screenshot or recorded human'):
            gate.check(self.root,state)
        manual = put(self.root,'human-viewport.md','Synthetic viewer described the actual screen')
        self.add_record(state,'core_scene_skeleton',capture_unavailable='Capture channel unavailable',manual_review=manual)
        fit = fit_record(self.root, dict(state['tone_contract'],version='expired'), [self.artifact])
        state['practice_evidence']['skeleton_fit']={'workspace':fit}
        with self.assertRaisesRegex(ValueError,'stale or missing tone contract'):
            gate.check(self.root,state)
        reference = tone.read(self.root,tone.DEFAULT_PATH)['parts']['screenshot']
        fit = fit_record(self.root,state['tone_contract'],[self.artifact],mode='same_instance',checker='maker',
                         reference_screenshot=reference, reference_viewport='1280×800',
                         comparison_state='Initial selection with keyboard focus on the start square')
        state['practice_evidence']['skeleton_fit']['workspace']=fit
        self.assertTrue(gate.check(self.root,state)['allowed'])

    def test_skeleton_and_increment_require_separate_comparable_views(self):
        state = self.state('E-3.2','E-3.3',[scope(tone,appearance_target='yes')])
        state['role'] = 'build'
        contract = state['tone_contract']
        self.add_record(state,'core_scene_skeleton',screenshot=put(self.root,'core.png',PIXEL))
        reference = tone.read(self.root,tone.DEFAULT_PATH)['parts']['screenshot']
        view = dict(reference_screenshot=reference,reference_viewport='1280×800',
                    comparison_state='Start round three and leave the route selection open')
        fit = fit_record(self.root,contract,[self.artifact], **view)
        state['practice_evidence']['skeleton_fit']={'workspace':fit}
        with self.assertRaisesRegex(ValueError,'missing practice evidence: increment_fit'):
            gate.check(self.root,state)
        state['practice_evidence']['increment_fit']={'workspace':fit}
        with self.assertRaisesRegex(ValueError,'separate fit review records'):
            gate.check(self.root,state)
        for extra, message in (
            (dict(view,reference_viewport='1024x768'),'same numeric viewport'),
            (dict(view,comparison_state=''),'representative comparison state'),
            (dict(view,reference_screenshot=put(self.root,'unrelated.png',PIXEL)), 'current direction reference'),
        ):
            with self.subTest(message=message):
                increment = fit_record(self.root,contract,[self.artifact],record_path='increment-fit.json', **extra)
                state['practice_evidence']['increment_fit']['workspace'] = increment
                with self.assertRaisesRegex(ValueError,message):
                    gate.check(self.root,state)
        increment = fit_record(self.root,contract,[self.artifact],record_path='increment-fit.json', **view)
        state['practice_evidence']['increment_fit']['workspace'] = increment
        self.assertTrue(gate.check(self.root,state)['allowed'])

    def test_human_skeleton_comparison_uses_current_direction_viewport_record(self):
        state = self.state('E-2.3','E-2.4',[scope(tone,appearance_target='yes')])
        data = tone.read(self.root,tone.DEFAULT_PATH)
        direction_review = put(self.root,'direction-view.md','Synthetic human view of the direction selection')
        data['parts'].pop('screenshot')
        data['parts']['manual_review'] = direction_review
        data['capture_unavailable'] = 'Direction capture unavailable'
        state['tone_contract'] = put(self.root,tone.DEFAULT_PATH,'# Direction\n```tone-contract\n'
                                     + json.dumps(data) + '\n```\n')
        manual = put(self.root,'skeleton-view.md','Reviewer saw the same initial selection at desktop width')
        self.add_record(state,'rendering_choice')
        self.add_record(state,'appearance_proof',capture_unavailable='No capture channel',manual_review=manual)
        self.add_record(state,'core_scene_skeleton',capture_unavailable='No capture channel',manual_review=manual)
        common = dict(mode='human',capture_unavailable='No capture channel',manual_review=manual,
                      reference_viewport='1280x800',comparison_state='Initial selection')
        fit = fit_record(self.root,state['tone_contract'],[self.artifact], **common)
        state['practice_evidence']['skeleton_fit']={'workspace':fit}
        with self.assertRaisesRegex(ValueError,'reference_manual_review'):
            gate.check(self.root,state)
        fit = fit_record(self.root,state['tone_contract'],[self.artifact],reference_manual_review=direction_review, **common)
        state['practice_evidence']['skeleton_fit']['workspace']=fit
        self.assertTrue(gate.check(self.root,state)['allowed'])

    def test_selected_example_requires_reviewed_deviations(self):
        row = tone.practice.load_example()['scopes'][0]
        row['example']={'id':'board-race'}
        row['features']['appearance_target']['value']='no'
        state = self.state('E-2.1','E-2.2',[row])
        with self.assertRaisesRegex(ValueError,'every changed feature'):
            gate.check_entry(self.root,state)
        row['example']['deviations']={'appearance_target':dict(reason='Specified visual output is excluded',
                                                               master_review=put(self.root,'master.txt','Synthetic master decision'))}
        state = self.state('E-2.1','E-2.2',[row])
        gate.check_entry(self.root,state)
