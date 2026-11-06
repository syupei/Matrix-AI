"""Expertise gaps: work that needs a profession the project has not set up waits for the person's choice.
Mechanism tests only: every person, expert, model, receipt and result is SIMULATED."""
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest

from kit import KIT
SOURCE = KIT
spec = importlib.util.spec_from_file_location('pm_gaps_under_test', SOURCE / 'matrix/orchestration/tools/pm_tasks.py')
pm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pm)
REGISTRIES = {r['id']: r for r in (json.loads(p.read_text(encoding='utf-8')) for p in (SOURCE / 'matrix/professions').glob('*/profession.json'))}
CAPABILITIES = sorted({c for r in REGISTRIES.values() for c in r.get('model_capabilities', [])})
MODELS = {'models': [{'model': m, 'levels': {p: r['levels']['range'][1] for p, r in REGISTRIES.items()}, 'capabilities': CAPABILITIES,
                      'filled_by': 'SIMULATED person'} for m in ['SIM-big', 'SIM-other']]}
TEAM = {'entries': [  # no content-design entry: that profession is not set up in this project
    {'id': 'E-M', 'profession': 'code-engineering', 'level': 'T7', 'model': 'SIM-big', 'count': 1, 'master': True},
    {'id': 'E-W', 'profession': 'code-engineering', 'level': 'T4', 'model': 'SIM-other', 'count': 1},
    {'id': 'Q-M', 'profession': 'quality-engineering', 'level': 'T6', 'model': 'SIM-other', 'count': 1, 'master': True},
    {'id': 'P-M', 'profession': 'product', 'level': 'T7', 'model': 'SIM-big', 'count': 1, 'master': True}]}
PEOPLE = {'people': [{'id': 'boss', 'name': 'BOSS', 'decides': ['project']}, {'id': 'zhang', 'name': '张三', 'decides': ['design']},
                     {'id': 'dev', 'name': '工程师'}]}
TAX = dict(domain='财税', kind='not_in_kit', why='SIM 提现要代扣个税', qualification='注册税务师', risk='F1')
LAW = dict(domain='法律与合规', kind='not_in_kit', why='SIM 用户协议的条款', qualification='执业律师', risk='F2')
LAW_LABEL = '非法律与合规专家产出，未经具备资质的人审定'


class Fixture:
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix='pm-gaps-simulation-')
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        (self.root / 'management').mkdir(parents=True, exist_ok=True)
        for name, data in [('model-fit.json', MODELS), ('instance-config.json', TEAM), ('people.json', PEOPLE)]:
            (self.root / 'management' / name).write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
        self.n = 0
        self.call('init', config=dict(project='SIMULATED 记账 App', pm_actor='PM', authorization='SIMULATED only', frontdoor_id='SIMULATED', max_slots=8))
        self.call('confirm_config', person='boss', quote='SIMULATED: 按配置来', presented_ref='SIM shown', choices={})
        for e in TEAM['entries']:
            for _ in range(e['count']):
                self.call('derive', entry=e['id'], endpoint='SIM-handle-' + str(self.n))
        # code-engineering-001 (T7 master), code-engineering-002 (T4), quality-engineering-001 (T6 master), product-001 (T7 master)

    def call(self, op, actor='PM', **kw):
        self.n += 1
        return pm.execute(self.root, dict(op=op, actor=actor, event_id='SIM-' + str(self.n), **kw))

    def status(self):
        return pm.execute(self.root, {'op': 'status'})

    def t(self, tid):
        return next(t for t in self.status()['tasks'] if t['id'] == tid)

    def stored(self, tid):
        db = sqlite3.connect(self.root / 'management/runtime/tasks.sqlite3')
        try:
            return json.loads(db.execute('SELECT data FROM tasks WHERE id=?', (tid,)).fetchone()[0])
        finally:
            db.close()

    def create(self, tid, parent=None, **kw):
        data = dict(id=tid, parent=parent, title='SIM ' + tid, owner='code-engineering-001', checker='quality-engineering-001', goal='SIMULATED',
                    inputs=['SIM v1'], outputs=['SIM output'], criteria=['SIM correct'], next_action='SIM next ' + tid)
        data.update(kw)
        data.setdefault('executor', data['owner'])
        return self.call('create', 'PM' if parent is None else self.t(parent)['owner'], task=data)

    def mutate(self, op, tid, actor=None, **kw):
        t = self.t(tid)
        return self.call(op, actor or t['owner'], task_id=tid, expected_revision=t['revision'], **kw)

    def start(self, tid):
        return self.mutate('transition', tid, state='running', reason='SIM start', execution_receipt='SIM started')

    def hand_over(self, tid, evidence=None):
        return self.mutate('transition', tid, state='waiting_review', reason='SIM handed over', stop_evidence='SIM stopped',
                           evidence=evidence or ['SIMULATED result ' + tid])

    def check(self, tid):
        t = self.t(tid)
        return self.mutate('review', tid, t['checker'], outcome='passed', criteria_checked=t['criteria'], evidence=['SIMULATED check'])

    def close(self, tid):
        return self.mutate('transition', tid, self.t(tid)['manager'], state='done', reason='SIM accepted')

    def gap(self, gid):
        return self.status()['gaps'][gid]

    def open(self, fields, actor='PM', **kw):
        return self.call('gap_open', actor, **dict(fields, **kw))

    def decide(self, gid, actor='PM', **kw):
        fields = dict(choice='self', person='boss', quote='SIMULATED: 我知道风险，你直接做')
        fields.update(kw)
        return self.call('gap_decide', actor, gap=gid, expected_revision=self.gap(gid)['revision'], **fields)

    def close_gap(self, gid, actor='PM', **kw):
        fields = dict(source='legal/SIM-review.md', evidence=['SIMULATED result from the designated party'])
        fields.update(kw)
        return self.call('gap_close', actor, gap=gid, expected_revision=self.gap(gid)['revision'], **fields)

    def rows(self, asker):
        listed = pm.execute(self.root, {'op': 'tasks_for', 'as': asker})
        return {r[0]: dict(zip(listed['columns'], r)) for r in listed['rows']}

    def view(self, rel):
        return (self.root / 'management/views' / rel).read_text(encoding='utf-8')


class Enforcement(Fixture, unittest.TestCase):
    def test_open_gap_blocks_start_handover_and_done(self):
        self.create('T-3')
        self.start('T-3')
        self.hand_over('T-3')
        self.check('T-3')
        self.create('T-2', owner='product-001')
        self.start('T-2')
        self.create('T-1')
        gap = self.open(TAX, task_ids=['T-1', 'T-2', 'T-3'])['record']
        self.assertEqual(('G-001', 'open', None, 'PM', ['T-1', 'T-2', 'T-3']), (gap['id'], gap['status'], gap['decision'], gap['opened_by'], gap['task_ids']))
        waiting = '缺 财税 专家，等人选择（缺口 G-001）'
        with self.assertRaisesRegex(pm.TaskError, waiting):
            self.start('T-1')
        with self.assertRaisesRegex(pm.TaskError, waiting):
            self.hand_over('T-2')
        with self.assertRaisesRegex(pm.TaskError, waiting):
            self.close('T-3')
        self.assertFalse(self.t('T-1')['ready'])
        self.assertIn(waiting, self.t('T-1')['readiness_issues'])
        self.mutate('transition', 'T-2', state='blocked', reason='SIM 等人选择', stop_evidence='SIM stopped')  # stopping stays possible
        self.assertEqual('G-001', self.t('T-1')['gap'])

    def test_decide_checks_the_choice_the_quote_the_person_and_the_expert(self):
        self.create('T-1', people={'decide': ['zhang']})
        self.open(TAX, task_ids=['T-1'])
        for fields, message in [(dict(quote=''), 'quote'), (dict(choice='later'), 'choice must be'), (dict(person='dev'), 'no decision authority'),
                                (dict(person='ghost'), 'listed person'), (dict(person=''), 'deciding person'), (dict(choice='expert'), 'expert names'),
                                (dict(choice='expert', expert=' '), 'expert names'), (dict(choice='self', expert='SIM'), 'expert names'),
                                (dict(standing='yes'), 'standing')]:
            with self.assertRaisesRegex(pm.TaskError, message):
                self.decide('G-001', **fields)
        with self.assertRaisesRegex(pm.TaskError, 'PM or front desk'):
            self.decide('G-001', actor='code-engineering-001')
        with self.assertRaisesRegex(pm.TaskError, 'stale gap revision'):
            self.call('gap_decide', gap='G-001', expected_revision=9, choice='self', person='boss', quote='SIMULATED')
        decided = self.decide('G-001', person='zhang')['record']  # the decider of the linked task
        self.assertEqual(('self', 'zhang', 'SIMULATED: 我知道风险，你直接做', True),
                         (decided['status'], decided['decision']['person'], decided['decision']['quote'], decided['decision']['standing']))

    def test_self_choice_lets_work_start_but_hand_over_only_with_the_label(self):
        self.create('T-1')
        self.open(LAW, task_ids=['T-1'])
        self.decide('G-001', quote='SIMULATED: 我知道没有法务的风险，你直接写吧')
        self.start('T-1')
        with self.assertRaisesRegex(pm.TaskError, '「' + LAW_LABEL + '」（缺口 G-001）'):
            self.hand_over('T-1')
        self.hand_over('T-1', evidence=['SIMULATED terms.md', LAW_LABEL])
        self.check('T-1')
        self.close('T-1')
        self.assertEqual('done', self.t('T-1')['state'])
        # Finished work linked afterwards cannot close without the label either.
        self.create('T-2', owner='product-001')
        self.start('T-2')
        self.hand_over('T-2')
        self.check('T-2')
        self.open(LAW, task_ids=['T-2'])  # the standing self choice applies
        with self.assertRaisesRegex(pm.TaskError, LAW_LABEL):
            self.close('T-2')
        self.mutate('update', 'T-2', changes={'evidence': ['SIMULATED result T-2', LAW_LABEL]}, reason='SIM label added')
        self.check('T-2')
        self.close('T-2')

    def test_expert_choice_waits_for_the_recorded_result(self):
        self.create('T-1')
        self.open(LAW, task_ids=['T-1'])
        with self.assertRaisesRegex(pm.TaskError, 'only a gap given to an expert or a person'):
            self.close_gap('G-001')
        self.decide('G-001', choice='expert', expert='张律师', quote='SIMULATED: 找张律师看')
        self.assertEqual('张律师', self.gap('G-001')['decision']['expert'])
        with self.assertRaisesRegex(pm.TaskError, '等 张律师 的结论（缺口 G-001）'):
            self.start('T-1')
        for fields, message in [(dict(evidence=[]), 'evidence'), (dict(evidence='SIM'), 'evidence'), (dict(source=''), 'source')]:
            with self.assertRaisesRegex(pm.TaskError, message):
                self.close_gap('G-001', **fields)
        with self.assertRaisesRegex(pm.TaskError, 'owner or manager'):
            self.close_gap('G-001', actor='product-001')
        closed = self.close_gap('G-001', actor='code-engineering-001')['record']  # the owner of the linked task records it
        self.assertEqual(('closed', 'legal/SIM-review.md', 'code-engineering-001'), (closed['status'], closed['result']['source'], closed['result']['by']))
        self.start('T-1')
        with self.assertRaisesRegex(pm.TaskError, 'is closed'):
            self.decide('G-001')

    def test_human_choice_becomes_a_to_do_of_the_person(self):
        self.create('T-1')
        self.open(TAX, task_ids=['T-1'])
        self.decide('G-001', choice='human', quote='SIMULATED: 列成我的待办，我去找会计')
        item = {'person': 'boss', 'action': 'execute', 'ref': 'G-001', 'item': '需要具备注册税务师的人处理：SIM 提现要代扣个税（缺口 G-001）'}
        self.assertEqual([item], self.t('T-1')['awaiting'])
        with self.assertRaisesRegex(pm.TaskError, '人工待办：需要具备注册税务师的人处理：SIM 提现要代扣个税（缺口 G-001）'):
            self.start('T-1')
        pm.render(self.root)
        line = '[T-1 SIM T-1](tasks/T-1.md)：BOSS（执行或试用）需要具备注册税务师的人处理：SIM 提现要代扣个税（缺口 G-001）'
        self.assertIn(line, self.view('plan.md').split('## 阶段')[0])
        self.assertIn(line.replace('(tasks/', '(../tasks/'), self.view('people/boss.md').split('## 即将轮到你')[0])
        self.mutate('update', 'T-1', changes={'awaiting': []}, reason='SIM tidied by hand')
        self.assertEqual([item], self.t('T-1')['awaiting'])  # the to-do stays while the gap is open
        self.close_gap('G-001', source='SIM 会计的答复.md')
        self.assertEqual([], self.t('T-1')['awaiting'])
        self.start('T-1')

    def test_changing_the_choice_moves_the_to_do(self):
        self.create('T-1')
        self.create('T-2', owner='product-001', awaiting=[{'person': 'zhang', 'action': 'clarify', 'item': 'SIM 提现的金额上限'}])
        self.open(TAX, task_ids=['T-1', 'T-2'])
        self.decide('G-001', choice='human')
        self.assertEqual(['zhang', 'boss'], [a['person'] for a in self.t('T-2')['awaiting']])
        self.decide('G-001', choice='expert', expert='SIM 税务师事务所', quote='SIMULATED: 改主意了，交给事务所')
        self.assertEqual([[], ['zhang']], [[a['person'] for a in self.t(x)['awaiting']] for x in ['T-1', 'T-2']])  # other items stay
        self.decide('G-001', choice='human', person='boss', quote='SIMULATED: 还是我来找人')
        self.mutate('transition', 'T-1', 'PM', state='cancelled', reason='SIM 不做了')
        self.assertEqual([], self.t('T-1')['awaiting'])  # a closed task waits for nobody
        self.mutate('transition', 'T-1', 'PM', state='planned', reason='SIM 又要做了')
        self.assertEqual(['boss'], [a['person'] for a in self.t('T-1')['awaiting']])


class Standing(Fixture, unittest.TestCase):
    def test_a_standing_self_choice_links_the_next_request_of_the_domain(self):
        for tid in ['T-1', 'T-2', 'T-3', 'T-4']:
            self.create(tid)
        self.open(LAW, task_ids=['T-1'])
        self.decide('G-001')
        again = self.open(LAW, task_ids=['T-2'])
        self.assertEqual(('G-001', 'self', 'G-001', ['T-1', 'T-2']), (again['existing'], again['choice'], again['record']['id'], again['record']['task_ids']))
        self.assertEqual(['G-001'], list(self.status()['gaps']))
        self.start('T-2')  # follows the standing choice without asking again
        severe = self.open(dict(LAW, risk='F0'), task_ids=['T-3'])  # the person accepted a lower risk
        self.assertNotIn('existing', severe)
        self.assertEqual(('G-002', 'open'), (severe['record']['id'], severe['record']['status']))
        self.decide('G-002', standing=False)
        third = self.open(dict(LAW, risk='F0'), task_ids=['T-4'])  # a one-time choice is asked again
        self.assertEqual(('G-003', 'open'), (third['record']['id'], third['record']['status']))
        with self.assertRaisesRegex(pm.TaskError, 'already waits on gap G-003'):
            self.open(TAX, task_ids=['T-4'])

    def test_a_standing_expert_choice_gives_each_request_its_own_result(self):
        for tid in ['T-1', 'T-2', 'T-3']:
            self.create(tid, owner='product-001' if tid == 'T-2' else 'code-engineering-001')
        self.open(TAX, task_ids=['T-1'])
        self.decide('G-001', choice='expert', expert='SIM 税务师事务所', quote='SIMULATED: 财税的都交给事务所')
        carried = self.open(dict(TAX, why='SIM 发票开具'), task_ids=['T-2'])
        self.assertEqual(('G-001', 'expert'), (carried['existing'], carried['choice']))
        record = carried['record']
        self.assertEqual(('G-002', 'expert', 'SIM 税务师事务所', 'G-001', 'SIM 发票开具', ['T-2']),
                         (record['id'], record['status'], record['decision']['expert'], record['decision']['standing_from'], record['why'], record['task_ids']))
        self.close_gap('G-001')
        self.start('T-1')
        with self.assertRaisesRegex(pm.TaskError, '等 SIM 税务师事务所 的结论（缺口 G-002）'):
            self.start('T-2')  # its own result is not in yet
        after_close = self.open(TAX, task_ids=['T-3'])  # a closed gap keeps its standing choice
        self.assertEqual(('expert', 'G-003', 'expert'), (after_close['choice'], after_close['record']['id'], after_close['record']['status']))

    def test_a_standing_choice_covers_only_tasks_the_person_may_decide(self):
        self.create('T-1', people={'decide': ['zhang']})
        self.create('T-2')
        self.open(LAW, task_ids=['T-1'])
        self.decide('G-001', person='zhang')
        other = self.open(LAW, task_ids=['T-2'])  # zhang has no authority for T-2
        self.assertEqual(('G-002', 'open'), (other['record']['id'], other['record']['status']))
        self.decide('G-002', choice='human', person='boss')
        with self.assertRaisesRegex(pm.TaskError, 'without authority for T-3'):
            self.create('T-3', gap='G-001')
        self.create('T-3', gap='G-002')  # boss decides at project level
        self.assertEqual('boss', self.t('T-3')['awaiting'][0]['person'])


class Linking(Fixture, unittest.TestCase):
    def test_create_and_update_link_tasks_and_leaving_an_open_gap_needs_the_person(self):
        self.open(TAX)
        self.create('T-1', gap='G-001')
        self.create('T-2', gap=None)
        self.assertNotIn('gap', self.stored('T-2'))  # stored only on tasks that have one
        for gap, message in [('G-404', 'unknown gap'), ('tax', 'gap must be a gap id')]:
            with self.assertRaisesRegex(pm.TaskError, message):
                self.create('T-3', gap=gap)
        revision = self.t('T-2')['work_revision']
        self.mutate('update', 'T-2', changes={'gap': 'G-001'}, reason='SIM also withholds tax')
        self.assertEqual(revision, self.t('T-2')['work_revision'])  # a coordination fact
        with self.assertRaisesRegex(pm.TaskError, 'leaving gap G-001 before it is closed'):
            self.mutate('update', 'T-2', changes={'gap': None}, reason='SIM')
        with self.assertRaisesRegex(pm.TaskError, 'no decision authority'):
            self.mutate('update', 'T-2', changes={'gap': None}, reason='SIM', person='dev', quote='SIMULATED')
        self.mutate('update', 'T-2', changes={'gap': None}, reason='SIM not needed', person='boss', quote='SIMULATED: 这项不涉及个税')
        self.assertNotIn('gap', self.stored('T-2'))
        self.decide('G-001', choice='human')
        self.close_gap('G-001', source='SIM 会计的答复.md')
        with self.assertRaisesRegex(pm.TaskError, 'is closed; register new work with gap_open'):
            self.mutate('update', 'T-2', changes={'gap': 'G-001'}, reason='SIM')
        self.mutate('update', 'T-1', changes={'gap': None}, reason='SIM tax settled')  # leaving a closed gap needs no person

    def test_who_opens_and_the_tasks_it_takes(self):
        self.create('T-1')
        self.create('T-2', owner='product-001')
        with self.assertRaisesRegex(pm.TaskError, 'owner or manager of every listed task'):
            self.open(TAX, actor='code-engineering-001', task_ids=['T-1', 'T-2'])
        with self.assertRaisesRegex(pm.TaskError, 'PM, front desk'):
            self.open(TAX, actor='code-engineering-001')
        with self.assertRaisesRegex(pm.TaskError, 'registered tasks once each'):
            self.open(TAX, task_ids=['T-1', 'T-1'])
        self.call('configure', frontdesk_actor='SIM-DESK')
        self.open(TAX, actor='code-engineering-001', task_ids=['T-1'])  # the owner flags its own task
        self.open(LAW, actor='SIM-DESK')
        self.start('T-2')
        self.hand_over('T-2')
        self.check('T-2')
        self.close('T-2')
        with self.assertRaisesRegex(pm.TaskError, 'T-2 is closed'):
            self.open(LAW, task_ids=['T-2'])

    def test_kind_follows_the_project_setup(self):
        for fields, message in [(dict(TAX, domain='code-engineering'), 'profession of this kit; open it as not_set_up'),
                                (dict(TAX, domain='代码工程', kind='not_set_up'), r'code-engineering is set up \(code-engineering-001,code-engineering-002\)'),
                                (dict(TAX, kind='not_set_up'), 'registry id or name'), (dict(TAX, kind='other'), 'kind'),
                                (dict(TAX, risk='F9'), 'risk'), (dict(TAX, qualification=''), 'qualification')]:
            with self.assertRaisesRegex(pm.TaskError, message):
                self.open(fields)
        gap = self.open(dict(TAX, domain='content-design', kind='not_set_up'))['record']
        self.assertEqual(('内容设计与审读', 'content-design'), (gap['domain'], gap['profession']))
        self.decide(gap['id'])
        self.assertEqual('G-001', self.open(dict(TAX, domain='内容设计与审读', kind='not_set_up'))['existing'])

    def test_each_linked_task_gets_an_event_and_retries_are_idempotent(self):
        self.create('T-1')
        cmd = dict(op='gap_open', actor='PM', event_id='SIM-GAP', task_ids=['T-1'], **TAX)
        first = pm.execute(self.root, cmd)
        self.assertEqual(first, pm.execute(self.root, cmd))
        self.assertEqual(['G-001'], list(self.status()['gaps']))
        events = [e for e in pm.execute(self.root, {'op': 'events', 'limit': 1000})['events'] if e['event_id'].startswith('SIM-GAP')]
        self.assertEqual([('SIM-GAP', None), ('SIM-GAP:gap:T-1', 'T-1')], [(e['event_id'], e['task_id']) for e in events])
        self.assertEqual((None, 'G-001'), (events[1]['before_data'].get('gap'), events[1]['after_data']['gap']))
        pm.render(self.root)
        self.assertIn('｜PM｜gap_open｜缺口 G-001：等人选择', self.view('tasks/T-1.md'))


class Views(Fixture, unittest.TestCase):
    def test_task_lists_name_the_gap_in_the_status(self):
        self.create('P', owner='code-engineering-001')
        self.start('P')
        self.create('C', 'P', owner='code-engineering-002', checker='code-engineering-001')
        self.create('OPEN', owner='product-001')
        self.create('EXPERT', owner='product-001')
        self.create('HUMAN', owner='quality-engineering-001', checker='code-engineering-001')
        self.create('SELF', owner='product-001', checker='quality-engineering-001')
        self.open(TAX, task_ids=['OPEN', 'C'])
        self.open(LAW, task_ids=['EXPERT'])
        self.decide('G-002', choice='expert', expert='张律师')
        self.open(dict(TAX, domain='安全审计', qualification='安全审计资质'), task_ids=['HUMAN'])
        self.decide('G-003', choice='human')
        self.open(dict(TAX, domain='content-design', kind='not_set_up', risk='F3'), task_ids=['SELF'])
        self.decide('G-004')
        self.start('SELF')
        rows = self.rows('PM')
        self.assertEqual('受阻：缺 财税 专家，等人选择', rows['OPEN']['状态'])
        self.assertEqual('受阻：等 张律师 的结论', rows['EXPERT']['状态'])
        self.assertEqual('人工待办：安全审计资质', rows['HUMAN']['状态'])
        self.assertEqual('进行中｜缺 内容设计与审读 专家，人已知风险，由当前实例完成', rows['SELF']['状态'])
        self.assertEqual('受阻：等 代码工程-002 的 C', rows['P']['状态'])  # the child waiting on the gap blocks its parent
        self.assertEqual('SIM next OPEN', rows['OPEN']['下一步'])
        listed = pm.execute(self.root, {'op': 'tasks_for', 'as': 'PM'})
        self.assertEqual('SIMULATED 记账 App：PM（PM）派发的任务 5 项：受阻 3、人工待办 1、进行中 1', listed['header'])
        self.assertEqual(['EXPERT', 'OPEN', 'P', 'HUMAN', 'SELF'], [r[0] for r in listed['rows']])
        self.assertEqual('受阻：缺 财税 专家，等人选择', self.rows('code-engineering-002')['C']['状态'])

    def test_human_points_list_every_gap_and_open_ones_wait_for_the_choice(self):
        self.create('T-1')
        self.open(TAX, task_ids=['T-1'])
        self.open(LAW)
        self.decide('G-002', choice='expert', expert='张律师', quote='SIMULATED: 法律方面的事情以后都请张律师来看，他是我们签约的律师，有问题直接找他就行')
        pm.render(self.root)
        points = self.view('human-points.md')
        self.assertIn('| G-001 缺 财税 专家（需要：注册税务师）：SIM 提现要代扣个税；选择：指定专家、由当前实例完成或列为人工待办 | 专业缺口（本包没有，F1） | BOSS | 等人选择 |', points)
        self.assertIn('## 专业缺口\n\n| 缺口 | 领域 | 类型 | 风险 | 资质 | 状态 | 决定人与原话 | 关联任务 |', points)
        self.assertIn('| G-001 | 财税 | 本包没有 | F1 | 注册税务师 | 等人选择 | — | T-1（受阻：缺 财税 专家，等人选择） |', points)
        self.assertIn('| G-002 | 法律与合规 | 本包没有 | F2 | 执业律师 | 指定专家：张律师，等结论 | BOSS：「SIMULATED: 法律方面的事情以后都请张律师来看，他是我们签约的律师，有问…」；常设选择 | — |', points)
        self.assertNotIn('G-002 缺', points.split('## 专业缺口')[0])  # decided gaps no longer wait for a choice
        choosing = '- 缺口 G-001：缺 财税 专家（需要：注册税务师），等人选择：指定专家、由当前实例完成或列为人工待办；挡住：[T-1 SIM T-1](tasks/T-1.md)'
        self.assertIn(choosing, self.view('plan.md').split('## 阶段')[0])
        self.assertIn(choosing, self.view('digest.md'))
        self.close_gap('G-002', source='legal/SIM-opinion.md')
        pm.render(self.root)
        self.assertIn('| 已关闭（指定专家：张律师）；成果：legal/SIM-opinion.md |', self.view('human-points.md'))

    def test_a_gap_without_tasks_is_opened_and_decided_for_the_project(self):
        gap = self.open(TAX)['record']
        self.assertEqual([], gap['task_ids'])
        with self.assertRaisesRegex(pm.TaskError, 'no decision authority'):
            self.decide('G-001', person='zhang')  # with no linked task, a project-level decision
        self.decide('G-001', choice='human', person='boss')
        self.assertEqual('human', self.gap('G-001')['status'])
        pm.render(self.root)
        self.assertIn('| G-001 | 财税 | 本包没有 | F1 | 注册税务师 | 列为人工待办 | BOSS：「SIMULATED: 我知道风险，你直接做」；常设选择 | — |', self.view('human-points.md'))
        self.close_gap('G-001', source='SIM 会计的答复.md')

    def test_without_gaps_records_and_views_stay_as_they_were(self):
        self.create('T-1')
        self.start('T-1')
        pm.render(self.root)
        self.assertNotIn('gap', self.stored('T-1'))
        self.assertEqual({}, self.status()['gaps'])
        self.assertNotIn('专业缺口', self.view('human-points.md'))
        self.assertIn('## 现在等人处理\n\n- 无\n', self.view('plan.md'))


if __name__ == '__main__':
    unittest.main()
