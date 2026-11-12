"""Dependency decisions survive handoff without becoming blanket approval."""
import importlib.util
import unittest
from test_platform import Project, pm, TOOLS

spec = importlib.util.spec_from_file_location('packet_launch', TOOLS / 'launch.py')
launch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launch)


class UpstreamPacketTests(Project, unittest.TestCase):
    def test_downstream_packet_carries_current_scope_quote_and_evidence(self):
        self.call('update','product-001',task_id='A',expected_revision=self.t('A')['revision'],changes={'human_required':True},reason='SIM human gate',scope_authorization='SIM PM authorizes human gate')
        rid=self.launch('A');self.hand_over('A');self.exit(rid)
        self.call('review',task_id='A',expected_revision=self.t('A')['revision'],outcome='passed',criteria_checked=self.t('A')['criteria'],evidence=['SIM checked'])
        self.call('human_review',task_id='A',expected_revision=self.t('A')['revision'],outcome='approved',person='SIM-owner',
                  quote='SIM approve candidate only; retry safety remains unresolved',source='SIM reply',presented_ref='input.md',scope='SIM candidate wording only')
        self.call('transition',task_id='A',expected_revision=self.t('A')['revision'],state='done',reason='SIM adopted')
        status=pm.execute(self.root,{'op':'status'});tasks={t['id']:t for t in status['tasks']}
        rows=launch.upstream_context(pm,tasks['B'],tasks)
        self.assertTrue(rows[0]['currently_complete'])
        self.assertTrue(rows[0]['human_review']['current'])
        self.assertEqual(rows[0]['human_review']['scope'],'SIM candidate wording only')
        _,text=launch.packet(pm,self.root,'SIM-packet','start',status['integrity']['instance']['product-001'],[tasks['B']],{},tasks)
        self.assertIn('SIM work A',text)
        self.assertIn('retry safety remains unresolved',text)
        tasks['A']['human_review']['basis']='stale'
        self.assertFalse(launch.upstream_context(pm,tasks['B'],tasks)[0]['human_review']['current'])

    def test_completion_prerequisite_is_not_claimed_completed_or_approved(self):
        self.task('C',completion_requires=['A'])
        tasks={t['id']:t for t in pm.execute(self.root,{'op':'status'})['tasks']}
        row=launch.upstream_context(pm,tasks['C'],tasks)[0]
        self.assertEqual(row['relation'],'completion_requires')
        self.assertFalse(row['currently_complete'])
        self.assertIsNone(row['human_review'])
