"""Task lists by asker, rework in place, reports up one level, notices, the instance ledger and the
human review summary. Mechanism tests only: every person, model, receipt and cost is SIMULATED."""
import importlib.util
import json
import os
from pathlib import Path
import re
import tempfile
import unittest

from kit import KIT
SOURCE = KIT
spec = importlib.util.spec_from_file_location('pm_lists_under_test', SOURCE / 'matrix/orchestration/tools/pm_tasks.py')
pm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pm)
REGISTRIES = {r['id']: r for r in (json.loads(p.read_text(encoding='utf-8')) for p in (SOURCE / 'matrix/professions').glob('*/profession.json'))}
CAPABILITIES = sorted({c for r in REGISTRIES.values() for c in r.get('model_capabilities', [])})
MODELS = {'models': [{'model': m, 'levels': {p: r['levels']['range'][1] for p, r in REGISTRIES.items()}, 'capabilities': CAPABILITIES,
                      'filled_by': 'SIMULATED person'} for m in ['SIM-big', 'SIM-other']]}
TEAM = {'entries': [
    {'id': 'E-M', 'profession': 'code-engineering', 'level': 'T7', 'model': 'SIM-big', 'count': 1, 'master': True},
    {'id': 'E-W', 'profession': 'code-engineering', 'level': 'T4', 'model': 'SIM-other', 'count': 2},
    {'id': 'Q-M', 'profession': 'quality-engineering', 'level': 'T6', 'model': 'SIM-other', 'count': 1, 'master': True},
    {'id': 'P-M', 'profession': 'product', 'level': 'T7', 'model': 'SIM-big', 'count': 1, 'master': True},
    {'id': 'P-W', 'profession': 'product', 'level': 'T5', 'model': 'SIM-other', 'count': 1}]}
PEOPLE = {'people': [{'id': 'boss', 'name': 'BOSS', 'decides': ['project']}, {'id': 'zhang', 'name': '张三', 'decides': ['design']}]}


class Fixture:
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix='pm-lists-simulation-')
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        (self.root / 'management').mkdir(parents=True, exist_ok=True)
        for name, data in [('model-fit.json', MODELS), ('instance-config.json', TEAM), ('people.json', PEOPLE)]:
            (self.root / 'management' / name).write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
        self.n = 0
        self.call('init', 'PM', config=dict(project='记账 App', pm_actor='PM', authorization='SIMULATED only', frontdoor_id='SIMULATED', max_slots=8))
        self.call('confirm_config', person='boss', quote='SIMULATED: 按配置来', presented_ref='SIM shown', choices={})
        for e in TEAM['entries']:
            for _ in range(e['count']):
                self.call('derive', entry=e['id'], endpoint='SIM-handle-' + str(self.n))
        # code-engineering-001 (T7 master), -002/-003 (T4); quality-engineering-001 (T6 master); product-001 (T7 master), product-002 (T5)

    def call(self, op, actor='PM', **kw):
        self.n += 1
        return pm.execute(self.root, dict(op=op, actor=actor, event_id='SIM-' + str(self.n), **kw))

    def t(self, tid):
        return next(t for t in pm.execute(self.root, {'op': 'status'})['tasks'] if t['id'] == tid)

    def create(self, tid, parent=None, **kw):
        data = dict(id=tid, parent=parent, title='SIM ' + tid, owner='code-engineering-001', checker='quality-engineering-001', goal='SIMULATED',
                    inputs=['SIM v1'], outputs=['SIM output'], criteria=['SIM correct'], next_action='SIM next ' + tid)
        data.update(kw)
        data.setdefault('executor', data['owner'])
        return self.call('create', 'PM' if parent is None else self.t(parent)['owner'], task=data)

    def mutate(self, op, tid, actor=None, **kw):
        t = self.t(tid)
        return self.call(op, actor or t['owner'], task_id=tid, expected_revision=t['revision'], **kw)

    def start(self, tid, **kw):
        return self.mutate('transition', tid, state='running', reason='SIM start', execution_receipt='SIM started', **kw)

    def hand_over(self, tid, **kw):
        return self.mutate('transition', tid, state='waiting_review', reason='SIM handed over', stop_evidence='SIM stopped',
                           evidence=['SIMULATED result ' + tid], **kw)

    def check(self, tid, outcome='passed', **kw):
        t = self.t(tid)
        if not t['evidence']:
            self.mutate('update', tid, changes={'evidence': ['SIMULATED work ' + tid]}, reason='SIM work')
        return self.mutate('review', tid, t['checker'], outcome=outcome, criteria_checked=t['criteria'], evidence=['SIMULATED check'], **kw)

    def close(self, tid):
        return self.mutate('transition', tid, self.t(tid)['manager'], state='done', reason='SIM accepted')

    def finish(self, tid):
        self.check(tid)
        return self.close(tid)

    def listing(self, asker, **kw):
        return pm.execute(self.root, dict(op='tasks_for', **{'as': asker}, **kw))

    def rows(self, asker, **kw):
        listed = self.listing(asker, **kw)
        return {r[0]: dict(zip(listed['columns'], r)) for r in listed['rows']}

    def build(self):
        """The login case of the design: one blocked chain, one person review, one task with handed-over children."""
        self.create('T-0002', owner='product-001', title='登录失败的用户情境与表现', difficulty='T5', risk='F2', risk_reason='SIM 主流程')
        self.finish('T-0002')
        self.create('T-0005', owner='code-engineering-001', title='登录异常的处理与对照表', difficulty='T6', risk='F2', risk_reason='SIM 主流程')
        self.start('T-0005')
        self.create('T-0031', 'T-0005', owner='code-engineering-002', checker='code-engineering-001', title='登录模块的异常对照表', difficulty='T4', risk='F2', risk_reason='SIM')
        self.start('T-0031')
        self.mutate('transition', 'T-0031', state='blocked', reason='缺测试环境的数据库权限', stop_evidence='SIM stopped')
        self.create('T-0006', owner='quality-engineering-001', checker='code-engineering-001', title='登录失败的验收', dependencies=['T-0005'], difficulty='T5', risk='F2', risk_reason='SIM')
        self.create('T-0004', owner='product-001', title='登录失败弹窗的交互规格', human_required=True, people={'decide': ['zhang']})
        self.check('T-0004')
        self.mutate('transition', 'T-0004', state='waiting_review', reason='SIM shown for review')
        self.create('T-0003', owner='product-001', title='登录提示文案', difficulty='T4', risk='F3', risk_reason='SIM 提示')
        self.start('T-0003')
        for child in ['T-0003.a', 'T-0003.b']:
            self.create(child, 'T-0003', owner='product-002', checker='product-001')
        self.start('T-0003.a')
        self.hand_over('T-0003.a')


class Lists(Fixture, unittest.TestCase):
    def test_pm_list_holds_only_tasks_the_pm_dispatched(self):
        self.build()
        listed = self.listing('PM')
        self.assertEqual('记账 App：PM（PM）派发的任务 5 项：受阻 1、等人审 1、进行中 1、未开始 1、已完成 1', listed['header'])
        self.assertEqual(['编号', '任务', '受领者', '难度 / 风险', '状态', '下一步', '完成后', '更新'], listed['columns'])
        self.assertEqual(['T-0005', 'T-0004', 'T-0003', 'T-0006'], [r[0] for r in listed['rows']])  # blocked, person review, then by id
        rows = self.rows('PM')
        self.assertEqual('代码工程-001（master）', rows['T-0005']['受领者'])
        self.assertEqual('T6 / F2', rows['T-0005']['难度 / 风险'])
        self.assertEqual('受阻：等 代码工程-002 的 T-0031', rows['T-0005']['状态'])  # names the child that blocks it, without listing children
        self.assertEqual('等人审：张三', rows['T-0004']['状态'])
        self.assertEqual('进行中（下游 1/2 已交出）', rows['T-0003']['状态'])
        self.assertEqual('未开始：等 代码工程-001 的 T-0005', rows['T-0006']['状态'])
        self.assertEqual('解除 T-0006', rows['T-0005']['完成后'])
        self.assertRegex(rows['T-0005']['更新'], r'^\d\d-\d\d \d\d:\d\d$')
        self.assertNotIn('T-0031', rows)
        self.assertIn('T-0002', self.rows('PM', include_closed=True))
        self.assertIn('| [T-0005](tasks/T-0005.md) |', self.render_index())

    def render_index(self):
        pm.render(self.root)
        return (self.root / 'management/views/index.md').read_text(encoding='utf-8')

    def test_instance_list_holds_only_tasks_it_received(self):
        self.build()
        master = self.listing('code-engineering-001')
        self.assertEqual('代码工程-001（T7，master）受领的任务 1 项：受阻 1', master['header'])
        self.assertEqual('上游', master['columns'][2])
        row = self.rows('code-engineering-001')['T-0005']
        self.assertEqual(('PM 派发', '交 PM；解除 T-0006'), (row['上游'], row['完成后']))
        worker = self.rows('code-engineering-002')['T-0031']
        self.assertEqual(('T-0005 · 代码工程-001', '受阻：缺测试环境的数据库权限', '交 代码工程-001'), (worker['上游'], worker['状态'], worker['完成后']))
        product = self.rows('product-001')
        self.assertEqual('检验并整合 产品-002 的 T-0003.a', product['T-0003']['下一步'])
        self.assertNotIn('T-0003.a', product)  # dispatched downstream, not received
        self.assertEqual('等检验：产品-001', self.rows('product-002')['T-0003.a']['状态'])
        self.assertEqual('未开始：就绪', self.rows('product-002')['T-0003.b']['状态'])

    def test_blocked_status_names_the_nearest_level_and_follows_to_the_root(self):
        self.create('ROOT', owner='code-engineering-001')
        self.start('ROOT')
        self.create('MID', 'ROOT', owner='code-engineering-002', checker='code-engineering-001')
        self.start('MID')
        self.create('LEAF', 'MID', owner='code-engineering-002', checker='code-engineering-002', executor='code-engineering-003')
        self.mutate('transition', 'LEAF', state='blocked', reason='SIM 缺权限')
        self.assertEqual('受阻：等 代码工程-002 的 MID', self.rows('PM')['ROOT']['状态'])
        self.assertEqual('受阻：等 代码工程-002 的 LEAF', self.rows('code-engineering-002')['MID']['状态'])
        self.create('WAIT', owner='quality-engineering-001', checker='code-engineering-001', completion_requires=['ROOT'])
        self.start('WAIT')
        self.assertEqual('受阻：等 代码工程-001 的 ROOT', self.rows('PM')['WAIT']['状态'])  # a completion prerequisite that is blocked
        self.create('NEED', owner='quality-engineering-001', checker='code-engineering-001')
        self.mutate('transition', 'MID', state='blocked', reason='SIM waiting', stop_evidence='SIM stopped', blocked_by={'task_id': 'NEED'})
        self.assertEqual('受阻：等 质量工程-001 的 NEED', self.rows('code-engineering-002')['MID']['状态'])
        with self.assertRaisesRegex(pm.TaskError, 'blocked_by'):
            self.mutate('transition', 'NEED', state='blocked', reason='SIM', blocked_by={'task_id': 'NOPE'})

    def test_next_steps_push_ready_work_and_closing(self):
        self.create('UP', owner='product-001')
        self.create('DOWN', owner='quality-engineering-001', checker='code-engineering-001', dependencies=['UP'])
        self.assertEqual('SIM next DOWN', self.rows('PM')['DOWN']['下一步'])
        self.finish('UP')
        self.assertEqual('派出给 质量工程-001', self.rows('PM')['DOWN']['下一步'])
        self.create('MINE', owner='code-engineering-001', checker='PM')
        self.start('MINE')
        self.hand_over('MINE')
        self.assertEqual(('等检验：PM', '检验并整合 代码工程-001 的 MINE'), (self.rows('PM')['MINE']['状态'], self.rows('PM')['MINE']['下一步']))


class Rework(Fixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.create('P', owner='code-engineering-001')
        self.create('W', 'P', owner='code-engineering-002', checker='code-engineering-001', difficulty='T4', risk='F3', risk_reason='SIM')
        self.start('W')
        self.hand_over('W')

    def test_failed_check_sends_the_same_task_back_with_the_checker_cause(self):
        with self.assertRaisesRegex(pm.TaskError, 'records its cause'):
            self.check('W', outcome='failed')
        self.check('W', outcome='failed', cause='requirement_clarification')
        self.assertEqual('返工中（第 2 版）：需求澄清', self.rows('code-engineering-002')['W']['状态'])
        self.mutate('transition', 'P', state='running', reason='SIM', execution_receipt='SIM started')
        master = self.rows('code-engineering-001')['P']
        self.assertEqual(('进行中（下游 0/1 已交出）', 'SIM next P'), (master['状态'], master['下一步']))  # sent back, not handed over
        with self.assertRaisesRegex(pm.TaskError, 'note'):
            self.start('W')
        with self.assertRaisesRegex(pm.TaskError, 'attributed_to'):
            self.start('W', note='SIM R-X v1 → v2')
        with self.assertRaisesRegex(pm.TaskError, 'dispute it through conflict'):
            self.start('W', rework_reason='execution', note='SIM')
        self.start('W', note='SIM R-X v1 → v2', attributed_to='product-001')
        rework = self.t('W')['rework']
        self.assertEqual((1, 'requirement_clarification', 'product-001'), (rework['count'], rework['reason'], rework['attributed_to']))
        self.assertEqual('返工中（第 2 版）：需求澄清', self.rows('code-engineering-002')['W']['状态'])
        self.hand_over('W')
        self.assertEqual('等检验：代码工程-001', self.rows('code-engineering-002')['W']['状态'])
        self.check('W', outcome='failed', cause='execution')
        self.start('W', note='SIM missed case')
        self.assertEqual(('execution', 'code-engineering-002', 2), (self.t('W')['rework']['reason'], self.t('W')['rework']['attributed_to'], self.t('W')['rework']['count']))
        self.assertEqual('返工中（第 3 版）：执行问题', self.rows('code-engineering-002')['W']['状态'])

    def test_execution_rework_after_reassignment_counts_for_the_original_producer(self):
        self.check('W', outcome='failed', cause='execution')
        self.mutate('reassign', 'W', 'code-engineering-001', to='code-engineering-003', reason_kind='failed_check', note='SIM 两次没过')
        self.start('W', note='SIM 从进度接着做')
        self.assertEqual(('code-engineering-003', 'code-engineering-002'), (self.t('W')['executor'], self.t('W')['rework']['attributed_to']))

    def test_finished_work_is_reopened_in_place_unless_downstream_uses_it(self):
        self.finish('W')
        with self.assertRaisesRegex(pm.TaskError, 'rework_reason'):
            self.mutate('transition', 'W', 'code-engineering-001', state='planned', reason='SIM reopen')
        self.create('USER', 'P', owner='code-engineering-003', checker='code-engineering-001', dependencies=['W'])
        self.start('USER')
        with self.assertRaisesRegex(pm.TaskError, 'successor'):
            self.mutate('transition', 'W', 'code-engineering-001', state='planned', reason='SIM reopen', rework_reason='execution', note='SIM bug')
        self.mutate('transition', 'USER', state='blocked', reason='SIM paused', stop_evidence='SIM stopped')
        self.mutate('transition', 'USER', state='planned', reason='SIM not started yet')
        self.mutate('transition', 'W', 'code-engineering-001', state='planned', reason='SIM reopen', rework_reason='basis_changed', note='SIM 规则 v4', attributed_to='product-001')
        self.assertEqual(1, self.t('W')['rework']['count'])
        self.assertEqual('返工中（第 2 版）：依据变化', self.rows('code-engineering-002')['W']['状态'])

    def test_successors_only_replace_finished_work(self):
        (self.root / 'oral.txt').write_text('SIMULATED change')
        self.create('ANALYZE', owner='product-001')
        self.call('record_change', type='modify', source='oral.txt', quote='SIM', analysis_task='ANALYZE', participants=['code-engineering-002'], affected_tasks=['W'])
        change = pm.execute(self.root, {'op': 'changes'})['changes'][0]
        with self.assertRaisesRegex(pm.TaskError, 'not done in place'):
            self.call('assess_change', 'code-engineering-002', id=change['id'], expected_revision=change['revision'],
                      assessment=dict(decision='impacted', reason='SIM', dispositions=[{'action': 'rework', 'task_id': 'W2', 'replaces': 'W'}]))

    def test_handover_carries_evidence(self):
        self.create('X', 'P', owner='code-engineering-003', checker='code-engineering-001')
        self.start('X')
        with self.assertRaisesRegex(pm.TaskError, 'evidence'):
            self.mutate('transition', 'X', state='waiting_review', reason='SIM', stop_evidence='SIM stopped')
        self.hand_over('X')
        self.assertEqual(['SIMULATED result X'], self.t('X')['evidence'])


class Notices(Fixture, unittest.TestCase):
    def test_notices_reach_the_views_by_kind(self):
        self.create('T-1', owner='code-engineering-001', risk='F1', risk_reason='SIM 扣费')
        with self.assertRaisesRegex(pm.TaskError, 'PM or front desk'):
            self.call('notice', 'code-engineering-001', id='N0', kind='Q1', ref='quality/defects.json#Q-1', summary='SIM', people=['boss'])
        with self.assertRaisesRegex(pm.TaskError, 'name the people'):
            self.call('notice', id='N0', kind='F1_output', ref='code/billing.md', summary='SIM', people=[])
        with self.assertRaisesRegex(pm.TaskError, 'unknown person'):
            self.call('notice', id='N0', kind='Q1', ref='quality/defects.json#Q-1', summary='SIM', people=['ghost'])
        self.call('notice', id='N1', kind='Q0', ref='quality/defects.json#Q-0', summary='SIM 发布包无法启动', people=[])
        self.call('notice', id='N2', kind='F1_output', ref='code/billing.md', summary='SIM 扣费逻辑已交出', people=['zhang'])
        self.call('notice', id='N3', kind='Q1', ref='quality/defects.json#Q-1', summary='SIM 偶发重复扣款', people=['boss'])
        self.call('notice', id='N4', kind='Q2', ref='quality/defects.json#Q-2', summary='SIM 字段不一致', people=[])
        pm.render(self.root)
        views = self.root / 'management/views'
        project, digest = (views / 'project.md').read_text(encoding='utf-8'), (views / 'digest.md').read_text(encoding='utf-8')
        self.assertLess(project.index('## 立即（Q0）'), project.index('| 子方向'))
        self.assertIn('SIM 发布包无法启动', project)
        self.assertLess(digest.index('SIM 发布包无法启动'), digest.index('## 阶段进展'))
        self.assertIn('SIM 字段不一致（Q2）', digest)
        zhang, boss = (views / 'people/zhang.md').read_text(encoding='utf-8'), (views / 'people/boss.md').read_text(encoding='utf-8')
        self.assertIn('SIM 扣费逻辑已交出（F1 成果）', zhang)
        self.assertNotIn('SIM 偶发重复扣款', zhang)
        self.assertIn('SIM 偶发重复扣款（Q1）', boss)
        self.assertNotIn('SIM 字段不一致', boss)
        records = pm.execute(self.root, {'op': 'status'})['integrity']['notice']
        self.assertEqual({'id', 'kind', 'ref', 'summary', 'people', 'recorded_by', 'at', 'revision'}, set(records['N3']))  # the defect body stays in its source


class Ledger(Fixture, unittest.TestCase):
    def ledger(self):
        pm.render(self.root)
        return (self.root / 'management/views/ledger.md').read_text(encoding='utf-8')

    def section(self, text, title):
        return text.split('## ' + title, 1)[1].split('\n## ', 1)[0]

    def row(self, text, title, first):
        return next(line for line in self.section(text, title).splitlines() if line.startswith('| ' + first + ' |'))

    def test_without_costs_the_ledger_shows_times_and_counts_only(self):
        self.create('P', owner='code-engineering-001')
        self.create('W', 'P', owner='code-engineering-002', checker='code-engineering-001', difficulty='T4')
        self.start('W')
        self.hand_over('W')
        self.finish('W')
        text = self.ledger()
        self.assertIn('| W | 代码工程-002 | SIM-other | T4 | 适用 | 1 | 通过·代码工程-001·独立检验 | 0 | 0 | — | 未接入 |', text)
        row = self.row(text, '实例', '代码工程-002')
        self.assertIn('100%（1/1）', row)
        self.assertIn('T4 ', row)
        self.assertIn('未接入', row)
        changes = self.section(text, '配置与实例变更')
        self.assertIn('确认配置', changes)
        self.assertIn('BOSS：「SIMULATED: 按配置来」', changes)
        self.assertIn('派生 | 代码工程-002（T4，执行者，配置项 E-W，适用）', changes)

    def test_costs_rework_attribution_reassignment_and_overturning(self):
        self.create('P', owner='code-engineering-001')
        self.create('W', 'P', owner='code-engineering-002', checker='code-engineering-001', difficulty='T4')
        self.start('W')
        self.hand_over('W', usage={'cost': 0.5, 'currency': 'USD', 'tokens': 1000, 'seconds': 60})
        self.check('W', outcome='failed', cause='requirement_clarification')
        self.start('W', note='SIM 需求澄清 v2', attributed_to='product-001')
        self.hand_over('W', usage={'cost': 0.25, 'currency': 'USD'})
        self.finish('W')
        self.create('V', 'P', owner='code-engineering-002', checker='code-engineering-001', difficulty='T4')
        self.start('V')
        self.mutate('report', 'V', summary='SIM 进度', next_action='SIM', impact='SIM', delivery='prepared', usage={'cost': 0.25, 'currency': 'USD'})
        self.mutate('reassign', 'V', 'code-engineering-001', to='code-engineering-003', reason_kind='executor_unable', note='SIM 拿不准边界',
                    stop_evidence='SIM progress saved')
        self.start('V')
        self.hand_over('V', usage={'cost': 1, 'currency': 'USD'})
        self.check('V', outcome='failed', cause='execution')
        self.start('V', note='SIM 漏了一种情况')
        self.hand_over('V', usage={'cost': 1, 'currency': 'USD'})
        self.call('conflict', 'code-engineering-001', id='K1', task_ids=['V', 'W'], parties=['code-engineering-002', 'code-engineering-003'], issue='SIM',
                  basis='SIM 契约', resolution='SIM 按 W', decided_by='code-engineering-001', level='master', overturned=['V'])
        with self.assertRaisesRegex(pm.TaskError, 'usage'):
            self.mutate('report', 'V', summary='SIM', next_action='SIM', impact='SIM', delivery='prepared', usage={'cost': -1})
        text = self.ledger()
        w = self.row(text, '任务', 'W')
        self.assertIn('未通过（需求澄清）·代码工程-001·独立检验；通过·代码工程-001·独立检验', w)
        self.assertIn('| 1（需求澄清→产品-001） |', w)
        self.assertIn('0.75 USD；1000 tokens；60 秒', w)
        v = self.row(text, '任务', 'V')
        self.assertIn('代码工程-002 → 代码工程-003（实例说做不了：SIM 拿不准边界）', v)
        self.assertIn('| 1（执行问题→代码工程-003） | 1 |', v)
        worker = self.row(text, '实例', '代码工程-002')
        self.assertIn('| 2 | 100%（1/1） | 0%（0/2） | 0%（0/2） | 50%（1/2） |', worker)  # clarification does not count against it
        self.assertIn('| 1.0 USD |', worker)  # all its spending, the reassigned attempt included, per accepted result (W)
        other = self.row(text, '实例', '代码工程-003')
        self.assertIn('| 1 | 0%（0/1） | 100%（1/1） | 100%（1/1） | 0%（0/1） |', other)
        self.assertIn('—（没有通过检验并被采用的成果）', other)
        self.assertTrue(self.row(text, '实例', '产品-001').endswith('| 1 |'))  # caused one rework of others


class HumanPoints(Fixture, unittest.TestCase):
    def test_summary_lists_registry_reviews_f0_human_tasks_and_reserved_decisions(self):
        self.create('T-1', owner='code-engineering-001', risk='F0', risk_reason='SIM 正式环境迁移')
        self.create('T-2', owner='product-001', human_required=True, people={'decide': ['zhang']})
        pm.render(self.root)
        text = (self.root / 'management/views/human-points.md').read_text(encoding='utf-8')
        self.assertIn('| 事项 | 来源 | 由谁决定 | 状态 |', text)
        for stage in REGISTRIES['product']['stage_flows'][0]['review'] + [s for f in REGISTRIES['code-engineering']['stage_flows'] for s in f['review']]:
            self.assertIn(stage + ' 审阅', text)
        self.assertNotIn('D-1 审阅', text)  # design is not in the configuration
        self.assertIn('| T-1 SIM T-1（F0，由人判定后生效） | 任务风险 F0 | BOSS |', text)
        self.assertIn('| T-2 SIM T-2 | 任务人审 | 张三 | 未开始：就绪 |', text)
        for item in ['发布', '接受已知的严重风险', '花钱、签约', '改变委托边界', '风险 F0 的判定']:
            self.assertIn('| ' + item + ' | 保留给人的决定（C21 §3） | BOSS | 常设 |', text)


class Views(Fixture, unittest.TestCase):
    def test_each_active_instance_gets_its_list(self):
        self.build()
        out = pm.render(self.root)
        for view in ['instances/code-engineering-001.md', 'ledger.md', 'human-points.md', 'scopes.md']:
            self.assertIn(view, out['views'])
        text = (self.root / 'management/views/instances/code-engineering-002.md').read_text(encoding='utf-8')
        self.assertIn('代码工程-002（T4，执行者）受领的任务 1 项：受阻 1', text)
        self.assertIn('| [T-0031](../tasks/T-0031.md) | 登录模块的异常对照表 | T-0005 · 代码工程-001 |', text)
        index = (self.root / 'management/views/index.md').read_text(encoding='utf-8')
        self.assertIn('| 编号 | 任务 | 受领者 | 难度 / 风险 | 状态 | 下一步 | 完成后 | 更新 |', index)
        (self.root / 'management/instance-config.json').write_text(json.dumps({'entries': [e for e in TEAM['entries'] if e['id'] != 'P-W']}), encoding='utf-8')
        self.call('confirm_config', person='boss', quote='SIMULATED: 去掉产品执行者', presented_ref='SIM', choices={}, expected_revision=1)
        self.call('retire_instance', id='product-002', expected_revision=1, reason='SIM entry removed')
        out = pm.render(self.root)
        self.assertNotIn('instances/product-002.md', out['views'])
        self.assertFalse((self.root / 'management/views/instances/product-002.md').exists())


if __name__ == '__main__':
    unittest.main()
