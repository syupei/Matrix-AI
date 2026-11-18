"""Multi-person coordination in the PM task tool. Every person, reply and receipt is SIMULATED."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest

from pm_test_inputs import business_source,actual_output
from kit import KIT
SCRIPT = KIT / 'matrix/orchestration/tools/pm_tasks.py'
spec = importlib.util.spec_from_file_location('pm_team_under_test', SCRIPT)
pm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pm)

ROSTER = {'groups': [{'id': 'design', 'name': '设计组'}, {'id': 'dev', 'name': '研发组'}],
          'people': [{'id': 'boss', 'name': 'BOSS', 'decides': ['project']},
                     {'id': 'pm-lead', 'name': '产品经理', 'decides': ['product']},
                     {'id': 'art', 'name': '美术负责人', 'groups': ['design'], 'decides': ['design']},
                     {'id': 'dev1', 'name': '工程师', 'groups': ['dev']}]}


class TeamTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix='pm-team-simulation-')
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        (self.root / 'management').mkdir(parents=True, exist_ok=True)
        (self.root / 'management/people.json').write_text(json.dumps(ROSTER, ensure_ascii=False))
        self.n = 0
        self.call('init', 'SIM-PM', config={'project': 'SIMULATED', 'pm_actor': 'SIM-PM',
                  'authorization': 'SIMULATED only', 'frontdoor_id': 'SIMULATED', 'max_slots': 4})
        self.business=business_source(self,pm,pm_actor='SIM-PM',actors=[('SIM-OWNER', 'SIM-task-engine-owner'), ('SIM-CHECKER', 'SIM-task-engine-checker')])

    def call(self, op, actor='SIM-OWNER', **fields):
        self.n += 1
        return pm.execute(self.root, dict(op=op, actor=actor, event_id='SIM-' + str(self.n), **fields))

    def task(self, tid):
        return next(t for t in pm.execute(self.root, {'op': 'status'})['tasks'] if t['id'] == tid)

    def create(self, tid, **fields):
        data = dict(id=tid, parent=None, title='SIM ' + tid, owner='SIM-OWNER', checker='SIM-CHECKER',
                    goal='simulated', inputs=['in'], outputs=['out'], criteria=['ok'], next_action='next')
        data.update(fields)
        if data['inputs']==['in'] and data.get('kind','work')!='coordination':data.update(self.business)
        data.setdefault('executor',data['owner'])
        return self.call('create', 'SIM-PM', task=data)

    def update(self, tid, actor='SIM-OWNER', authorization=None, **changes):
        extra = {'scope_authorization': authorization} if authorization else {}
        return self.call('update', actor, task_id=tid, expected_revision=self.task(tid)['revision'],
                         changes=changes, reason='SIMULATED change', **extra)

    def decide(self, tid, person, outcome='approved'):
        return self.call('human_review', 'SIM-PM', task_id=tid, expected_revision=self.task(tid)['revision'],
                         outcome=outcome, presented_ref='shown.md', source='reply.md', quote='SIMULATED reply',
                         scope='SIMULATED scope', person=person)

    def build_project(self):
        self.create('STAGE-D', kind='stage', title='设计', people={'decide': ['art']})
        self.create('P-1', title='功能与流程', direction='产品', people={'decide': ['pm-lead']})
        self.create('D-1', title='风格锚点', direction='设计·界面', stage='STAGE-D', human_required=True,
                    derived_from=['P-1'], people={'decide': ['art'], 'inform': ['dev1']},
                    awaiting=[{'person': 'art', 'action': 'decide', 'item': '确认 3 个风格锚点'}])
        self.create('E-1', title='商店界面', direction='研发·客户端', dependencies=['D-1'], people={'execute': ['dev1']})
        self.create('E-1.a', parent='E-1', title='函数模块 A')
        self.create('E-2', title='网络同步', direction='研发·服务端', people={'execute': ['dev1']})

    def test_unknown_person_is_rejected(self):
        with self.assertRaises(pm.TaskError):
            self.create('X', people={'decide': ['nobody']})
        with self.assertRaises(pm.TaskError):
            self.create('Y', awaiting=[{'person': 'art', 'action': 'approve', 'item': 'x'}])

    def test_only_listed_deciders_and_upstream_may_confirm(self):
        self.build_project()
        with self.assertRaises(pm.TaskError):
            self.decide('D-1', 'dev1')          # opinion of a non-decider is feedback, not confirmation
        with self.assertRaises(pm.TaskError):
            self.call('human_review', 'SIM-PM', task_id='D-1', expected_revision=self.task('D-1')['revision'],
                      outcome='approved', presented_ref='a', source='b', quote='c', scope='d')  # person missing
        self.decide('D-1', 'art')
        self.assertEqual('art', self.task('D-1')['human_review']['person'])
        self.decide('D-1', 'pm-lead', 'changes_requested')  # upstream may override downstream
        with self.assertRaises(pm.TaskError):
            self.decide('D-1', 'art', 'approved')  # downstream cannot overturn the upstream decision
        self.decide('D-1', 'boss', 'approved')    # project-level decider sits above the chain

    def test_coordination_changes_keep_professional_review(self):
        self.build_project()
        before = self.task('D-1')['work_revision']
        self.update('D-1', awaiting=[])
        self.assertEqual(before, self.task('D-1')['work_revision'])
        with self.assertRaises(pm.TaskError):
            self.update('D-1', people={'decide': ['pm-lead']})  # reassigning a decider needs manager authority
        self.update('D-1', actor='SIM-PM', authorization='SIMULATED designation recorded by the project lead', people={'decide': ['pm-lead']})

    def test_stage_reference_must_be_a_stage(self):
        self.create('W', title='work')
        with self.assertRaises(pm.TaskError):
            self.create('Z', stage='W')

    def test_views_filter_by_relation_and_direct_dependency(self):
        self.build_project()
        out = pm.render(self.root)
        self.assertIn('people/art.md', out['views'])
        art = (self.root / 'management/views/people/art.md').read_text()
        self.assertIn('确认 3 个风格锚点', art)          # waiting on this person
        self.assertIn('商店界面', art)                    # dependency neighbour, shown at top level
        self.assertNotIn('函数模块 A', art)               # internal sub-task stays hidden
        self.assertNotIn('网络同步', art)                 # unrelated work stays hidden
        dev = (self.root / 'management/views/people/dev1.md').read_text()
        self.assertIn('只需知悉', dev)                    # inform-only items go to the digest
        group = (self.root / 'management/views/groups/design.md').read_text()
        self.assertIn('风格锚点', group)
        plan = (self.root / 'management/views/plan.md').read_text()
        self.assertIn('确认 3 个风格锚点', plan)
        self.assertIn('阻塞：商店界面', plan)
        project = (self.root / 'management/views/project.md').read_text()
        for direction in ['产品', '设计·界面', '研发·客户端']:
            self.assertIn(direction, project)
        self.assertIn('在等的人', (self.root / 'management/views/digest.md').read_text())

    def test_project_page_links_to_professional_progress_source(self):
        (self.root / 'engineering/build').mkdir(parents=True)
        (self.root / 'engineering/build/01-增量计划.md').write_text('SIMULATED plan', encoding='utf-8')
        self.create('E-9', title='增量构建', direction='研发·客户端', source='engineering/build/01-增量计划.md')
        pm.render(self.root)
        project = (self.root / 'management/views/project.md').read_text(encoding='utf-8')
        self.assertIn('engineering/build/01-增量计划.md', project)

    def test_single_person_project_has_no_personal_views(self):
        (self.root / 'management/people.json').write_text(json.dumps({'people': [{'id': 'me', 'name': '我'}]}))
        self.create('A', title='only task',kind='coordination',owner='SIM-PM',executor=None,outputs=['management/only.md'])
        out = pm.render(self.root)
        self.assertNotIn('people/me.md', out['views'])
        self.assertIn('plan.md', out['views'])


if __name__ == '__main__':
    unittest.main()
