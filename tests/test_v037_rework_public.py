"""Real public task chains, including upstream rework and manager-only coordination."""
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


if __name__ == '__main__':
    unittest.main()
