"""Project front desk in the PM task tool: recording real decisions and showing who executes. Every fact is SIMULATED."""
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest

SCRIPT = Path(os.environ.get('MATRIX_TEST_KIT', str(Path(__file__).resolve().parents[1] / 'src'))) / '.agents/skills/project-management-agent/scripts/pm_tasks.py'
spec = importlib.util.spec_from_file_location('pm_frontdesk_under_test', SCRIPT)
pm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pm)


class FrontDeskTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix='pm-frontdesk-simulation-')
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.n = 0
        self.call('init', 'SIM-PM', config={'project': 'SIMULATED', 'pm_actor': 'SIM-PM',
                  'authorization': 'SIMULATED only', 'frontdoor_thread': 'SIMULATED', 'max_slots': 4})

    def call(self, op, actor='SIM-OWNER', **fields):
        self.n += 1
        return pm.execute(self.root, dict(op=op, actor=actor, event_id='SIM-' + str(self.n), **fields))

    def task(self, tid):
        return next(t for t in pm.execute(self.root, {'op': 'status'})['tasks'] if t['id'] == tid)

    def create(self, tid, **fields):
        data = dict(id=tid, parent=None, title='SIM ' + tid, owner='SIM-OWNER', checker='SIM-CHECKER',
                    goal='simulated', inputs=['in'], outputs=['out'], criteria=['ok'], next_action='next')
        data.update(fields)
        return self.call('create', 'SIM-PM', task=data)

    def decide(self, tid, actor, outcome='approved'):
        return self.call('human_review', actor, task_id=tid, expected_revision=self.task(tid)['revision'],
                         outcome=outcome, presented_ref='shown.md', source='reply.md',
                         quote='SIMULATED reply, not a human decision', scope='SIMULATED scope')

    def test_front_desk_records_decisions_only_after_configuration(self):
        self.create('D-1', human_required=True)
        with self.assertRaisesRegex(pm.TaskError, 'frontdoor'):
            self.decide('D-1', 'SIM-DESK')
        with self.assertRaisesRegex(pm.TaskError, 'only PM'):
            self.call('configure', 'SIM-DESK', frontdesk_actor='SIM-DESK')
        self.call('configure', 'SIM-PM', frontdesk_actor='SIM-DESK')
        self.decide('D-1', 'SIM-DESK')
        self.assertEqual('approved', self.task('D-1')['human_review']['outcome'])
        self.call('configure', 'SIM-PM', frontdesk_actor=None)
        with self.assertRaisesRegex(pm.TaskError, 'frontdoor'):
            self.decide('D-1', 'SIM-DESK', 'deferred')

    def test_project_page_shows_who_executes_active_work(self):
        self.create('E-1', title='增量 INC-1', direction='研发·客户端', executor='子 Agent build-1')
        self.call('transition', 'SIM-OWNER', task_id='E-1', expected_revision=self.task('E-1')['revision'],
                  state='running', reason='SIMULATED start', execution_receipt='SIMULATED receipt')
        pm.render(self.root)
        self.assertIn('执行：子 Agent build-1', (self.root / 'management/views/project.md').read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
