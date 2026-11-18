"""Real public task chains, including upstream rework and manager-only coordination."""
import json
import unittest
import test_v037_round2_pipeline as pipeline
from test_pm_instances import Fixture
from practice_fixture import put


class ReworkPublic(Fixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.staff()
        self.gate = pipeline.pm.admission.load_gate()
    admit = pipeline.PipelineRound2.admit
    inputs = pipeline.PipelineRound2.inputs
    stage = pipeline.PipelineRound2.stage
    business = pipeline.PipelineRound2.business
    finish = pipeline.PipelineRound2.finish
    upstream = pipeline.PipelineRound2.upstream
    downstream = pipeline.PipelineRound2.downstream
    def test_upstream_rework_refreshes_only_a_new_trusted_handover(self):
        self.upstream()
        self.downstream(outputs=['other/result.md'])
        self.finish('D', {'other/result.md': 'SIM consumes skeleton v1'})
        old = self.t('D')['input_provenance']
        for tid in ('D', 'U'):
            self.mutate('transition', tid, 'PM', state='planned', reason='SIM requested rework',
                        rework_reason='basis_changed', attributed_to='code-engineering-002', note='SIM approved upstream correction')
        self.finish('U', {'src/game.js': 'SIM skeleton v2'})
        self.finish('D', {'other/result.md': 'SIM consumes skeleton v2'})
        self.assertNotEqual(old, self.t('D')['input_provenance'])
        self.assertEqual('done', self.t('D')['state'])
        self.mutate('transition', 'D', 'PM', state='planned', reason='SIM recheck',
                    rework_reason='execution', note='SIM recheck')
        put(self.root, 'src/game.js', 'SIM unrelated unreviewed edit')
        with self.assertRaisesRegex(ValueError, 'read-only dispatched input changed'):
            self.mutate('transition', 'D', state='running', reason='SIM start', execution_receipt='SIM process')

    def test_coordinating_evolved_work_preserves_input_provenance(self):
        self.upstream()
        self.downstream()
        self.mutate('transition', 'D', state='running', reason='SIM start', execution_receipt='SIM process')
        original = self.t('D')['input_provenance']
        self.mutate('update', 'D', 'PM', changes={'timeout_minutes': 40, 'order': 2, 'expanded': True}, reason='SIM coordination')
        put(self.root, 'src/game.js', 'SIM own evolved work')
        self.mutate('transition', 'D', state='waiting_review', reason='SIM yield', stop_evidence='SIM', evidence=['src/game.js'])
        self.mutate('review', 'D', self.t('D')['checker'], outcome='failed', cause='execution',
                    criteria_checked=self.t('D')['criteria'], evidence=['SIM correction requested'])
        self.mutate('update', 'D', 'PM', changes={'executor': 'code-engineering-003', 'checker': 'quality-engineering-002'},
                    reason='SIM replace executor and retired checker')
        self.assertEqual(original, self.t('D')['input_provenance'])
        self.mutate('transition', 'D', state='running', reason='SIM rework', execution_receipt='SIM process',
                    rework_reason='execution', note='SIM fix')
        self.assertEqual('running', self.t('D')['state'])

    def test_restart_keeps_original_owned_input_while_refreshing_another_upstream(self):
        self.upstream()
        self.business('V',outputs=['src/settings.js'])
        self.finish('V',{'src/settings.js':'SIM settings v1'})
        self.downstream(inputs=['src/game.js','src/settings.js'],dependencies=['U','V'],outputs=['src/game.js'])
        self.finish('D',{'src/game.js':'SIM locally evolved game'})
        for tid in ('D','V'):
            self.mutate('transition',tid,'PM',state='planned',reason='SIM settings correction',
                        rework_reason='execution',note='SIM actual correction')
        self.finish('V',{'src/settings.js':'SIM settings v2'})
        self.mutate('transition','D',state='running',reason='SIM resume evolved game',execution_receipt='SIM')
        view,manifest=self.gate.tone.evidence.verify_bundle(self.root,self.t('D')['input_provenance']['bundle'])
        self.assertEqual('SIM settings v2',(view/'src/settings.js').read_text())
        self.assertNotEqual('SIM locally evolved game',(view/'src/game.js').read_text())
        self.assertEqual('SIM locally evolved game',(self.root/'src/game.js').read_text())

    def test_close_cannot_accept_unchecked_later_output_bytes(self):
        self.business('CHECKED',outputs=['src/checked.js'])
        self.mutate('transition','CHECKED',state='running',reason='SIM start',execution_receipt='SIM')
        put(self.root,'src/checked.js','SIM professionally checked version')
        self.mutate('transition','CHECKED',state='waiting_review',reason='SIM handover',stop_evidence='SIM',evidence=['src/checked.js'])
        self.check('CHECKED')
        put(self.root,'src/checked.js','SIM unrelated later edit')
        with self.assertRaisesRegex(ValueError,'changed after professional verification'):
            self.close('CHECKED')
        self.assertNotEqual('done',self.t('CHECKED')['state'])
        self.check('CHECKED');self.close('CHECKED')
        self.assertEqual('done',self.t('CHECKED')['state'])

    def test_semantic_edit_retains_owned_input_and_freezes_new_input(self):
        self.upstream()
        self.business('V',outputs=['src/settings.js'])
        self.finish('V',{'src/settings.js':'SIM independently checked settings'})
        self.downstream(outputs=['src/game.js'])
        self.mutate('transition','D',state='running',reason='SIM start',execution_receipt='SIM process')
        original=self.t('D')['input_provenance']
        put(self.root,'src/game.js','SIM evolved implementation')
        self.mutate('transition','D',state='waiting_review',reason='SIM handover',stop_evidence='SIM',evidence=['src/game.js'])
        self.mutate('review','D',self.t('D')['checker'],outcome='failed',cause='execution',criteria_checked=self.t('D')['criteria'],evidence=['SIM fix requested'])
        self.mutate('update','D','PM',changes=dict(inputs=['src/game.js','src/settings.js','external/brief.md'],dependencies=['U','V'],
                    admitted_inputs=['IN-1'],stage_transition=self.stage(['external/brief.md']),outputs=['src/game.js','src/turn.js']),
                    reason='SIM admitted scope extension',admission_basis=['IN-1'])
        self.assertEqual(original,self.t('D')['input_provenance'])
        self.mutate('transition','D',state='running',reason='SIM rework',execution_receipt='SIM',rework_reason='execution',note='SIM fix')
        view,_=self.gate.tone.evidence.verify_bundle(self.root,self.t('D')['input_provenance']['bundle'])
        self.assertEqual('SIM skeleton v1',(view/'src/game.js').read_text())
        self.assertEqual('SIM independently checked settings',(view/'src/settings.js').read_text())

    def successor_rebind(self, *, completed=False, remove_first=False, evolve=False):
        self.upstream()
        self.business('V',outputs=['src/settings.js'])
        self.finish('V',{'src/settings.js':'SIM settings v1'})
        inputs=['src/game.js','src/settings.js','external/brief.md']
        output='src/settings.js' if evolve else 'other/result.md'
        self.downstream(inputs=inputs,dependencies=['U','V'],outputs=[output],admitted_inputs=['IN-1'],
                        stage_transition=self.stage(['external/brief.md']))
        self.mutate('transition','D',state='running',reason='SIM consume V',execution_receipt='SIM')
        put(self.root,output,'SIM locally evolved settings' if evolve else 'SIM initial result')
        self.mutate('transition','D',state='waiting_review',reason='SIM yield',stop_evidence='SIM',evidence=[output])
        if completed:self.check('D');self.close('D')
        else:
            self.mutate('review','D',self.t('D')['checker'],outcome='failed',cause='execution',
                        criteria_checked=self.t('D')['criteria'],evidence=['SIM correct result'])
        with self.assertRaisesRegex(ValueError,'successor'):
            self.mutate('transition','V','PM',state='planned',reason='SIM revised source',
                        rework_reason='execution',note='SIM used source must be replaced')
        self.business('V2',outputs=['src/settings.js'])
        self.finish('V2',{'src/settings.js':'SIM settings v2 successor'})
        if completed:
            self.mutate('transition','D','PM',state='planned',reason='SIM rework consumer',
                        rework_reason='execution',note='SIM new trusted source')
        if remove_first:
            self.mutate('update','D','PM',changes={'inputs':['src/game.js','external/brief.md'],'dependencies':['U','V2']},
                        reason='SIM temporarily remove replaced input',admission_basis=['IN-1'])
        change=dict(inputs=inputs,dependencies=['U','V2'])
        if evolve:
            with self.assertRaisesRegex(ValueError,'evolved input changed upstream; merge'):
                self.mutate('update','D','PM',changes=change,reason='SIM replace source',admission_basis=['IN-1'])
            return
        self.mutate('update','D','PM',changes=change,reason='SIM replace source',admission_basis=['IN-1'])
        self.mutate('transition','D',state='running',reason='SIM resume against successor',execution_receipt='SIM',
                    rework_reason='execution',note='SIM independent corrected output')
        view,manifest=self.gate.tone.evidence.verify_bundle(self.root,self.t('D')['input_provenance']['bundle'])
        self.assertEqual('V2',manifest['context']['sources']['src/settings.js']['task_id'])
        self.assertEqual('SIM settings v2 successor',(view/'src/settings.js').read_text())
        put(self.root,output,'SIM corrected result from V2')
        self.mutate('transition','D',state='waiting_review',reason='SIM corrected result',stop_evidence='SIM',evidence=[output])
        self.check('D');self.close('D')
        self.assertEqual('done',self.t('D')['state'])

    def test_failed_consumer_can_rebind_retained_input_to_successor(self):
        self.successor_rebind()

    def test_reopened_consumer_can_rebind_retained_input_to_successor(self):
        self.successor_rebind(completed=True)

    def test_remove_and_readd_input_before_restart_uses_successor(self):
        self.successor_rebind(remove_first=True)

    def test_replacing_source_of_locally_evolved_input_requires_merge(self):
        self.successor_rebind(evolve=True)

    def test_unrelated_manager_edit_does_not_adopt_tampered_retained_input(self):
        self.upstream();self.business('V',outputs=['src/settings.js'])
        self.finish('V',{'src/settings.js':'SIM settings v1'})
        self.business('W',outputs=['src/audio.js']);self.finish('W',{'src/audio.js':'SIM audio v1'})
        self.downstream(inputs=['src/game.js','src/settings.js','external/brief.md'],dependencies=['U','V'],
                        outputs=['src/game.js'],admitted_inputs=['IN-1'],stage_transition=self.stage(['external/brief.md']))
        self.mutate('transition','D',state='running',reason='SIM start',execution_receipt='SIM')
        put(self.root,'src/settings.js','SIM unauthorized edit')
        put(self.root,'src/game.js','SIM own evolution')
        self.mutate('transition','D',state='waiting_review',reason='SIM yield',stop_evidence='SIM',evidence=['src/game.js'])
        self.mutate('review','D',self.t('D')['checker'],outcome='failed',cause='execution',
                    criteria_checked=self.t('D')['criteria'],evidence=['SIM correction'])
        with self.assertRaisesRegex(ValueError,'read-only dispatched input changed'):
            self.mutate('update','D','PM',changes={'inputs':['src/game.js','src/settings.js','external/brief.md','src/audio.js'],
                        'dependencies':['U','V','W']},reason='SIM add independent input',admission_basis=['IN-1'])

    def test_legacy_review_alias_does_not_hide_a_production_delivery(self):
        # A legacy snapshot may predate the ancestor-output dispatch restriction.
        # Feed its recorded shape to the aggregation routine; no database is edited.
        self.business('ROOT',outputs=['src/'])
        self.business('PRODUCE',parent='ROOT',actor='PM',outputs=['src/levels.json'])
        self.finish('PRODUCE',{'src/levels.json':'SIM real product data'})
        self.business('INSPECT',parent='ROOT',actor='PM',outputs=['reviews/note.json'])
        self.finish('INSPECT',{'reviews/note.json':'SIM independent inspection'})
        tasks={row['id']:row for row in self.call('status')['tasks']}
        alias=tasks['INSPECT'];alias['review_for']='ROOT'
        alias['handed_output_sha256']['src/levels.json']=tasks['PRODUCE']['handed_output_sha256']['src/levels.json']
        path=put(self.root,'aggregation-state.json',json.dumps({'current':'E-1.2'}))['path']
        with pipeline.pm.connect(self.root,readonly=True) as db:
            context=pipeline.pm.admission.completion_context(pipeline.pm.api(),self.root,db,tasks['ROOT'],tasks,path)
        self.assertNotIn('src/levels.json',context['control_files'])
        self.assertIn('reviews/note.json',context['control_files'])


if __name__ == '__main__':
    unittest.main()
