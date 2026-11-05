"""Delivery sets with one production exit per profession: provenance from the items' declared exits,
exits added by a master, binding, completion and the delivery-set view. Every fact is SIMULATED."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest

SOURCE = Path(os.environ.get('MATRIX_TEST_KIT', str(Path(__file__).resolve().parents[1] / 'src')))
spec = importlib.util.spec_from_file_location('pm_exits_under_test', SOURCE / '.agents/skills/project-management-agent/scripts/pm_tasks.py')
pm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pm)
contract_spec = importlib.util.spec_from_file_location('pm_exits_product_contract', SOURCE / '.agents/skills/product-agent/scripts/product_contract.py')
contract = importlib.util.module_from_spec(contract_spec)
contract_spec.loader.exec_module(contract)
REGISTRIES = {r['id']: r for r in (json.loads(p.read_text(encoding='utf-8')) for p in (SOURCE / 'collaboration/professions').glob('*.json'))}
MODELS = {'models': [{'model': 'SIM-big', 'levels': {p: r['levels']['range'][1] for p, r in REGISTRIES.items()},
                      'capabilities': sorted({c for r in REGISTRIES.values() for c in r.get('model_capabilities', [])}), 'filled_by': 'SIMULATED person'}]}
MASTERS = ['product', 'experience-design', 'code-engineering', 'quality-engineering']
TEAM = {'entries': [{'id': p, 'profession': p, 'level': REGISTRIES[p]['levels']['master_min'], 'model': 'SIM-big', 'count': 1, 'master': True} for p in MASTERS]
        + [{'id': 'code-worker', 'profession': 'code-engineering', 'level': 'T4', 'model': 'SIM-big', 'count': 1}]}
ITEMS = [{'id': 'R-LOGIN-07', 'version': 'v1', 'exits': {'experience-design': '页面', 'code-engineering': '实现', 'quality-engineering': '验收'}},
         {'id': 'R-LOGIN-08', 'version': 'v2', 'exits': ['code-engineering', 'quality-engineering']}]
BOTH = ['production:code-engineering', 'production:quality-engineering']


class DeliveryExits(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix='pm-exits-simulation-')
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        (self.root / 'collaboration').mkdir()
        (self.root / 'collaboration/model-fit.json').write_text(json.dumps(MODELS, ensure_ascii=False), encoding='utf-8')
        (self.root / 'collaboration/instance-config.json').write_text(json.dumps(TEAM, ensure_ascii=False), encoding='utf-8')
        (self.root / 'product').mkdir()
        self.items(ITEMS)
        self.n = 0
        self.call('init', config=dict(project='SIMULATED', pm_actor='PM', authorization='SIMULATED only', frontdoor_thread='SIMULATED', max_slots=8))
        self.call('confirm_config', person='SIM-owner', quote='SIMULATED: 按配置', presented_ref='SIM shown', choices={})
        for e in TEAM['entries']:
            self.call('derive', entry=e['id'], endpoint='SIM-handle-' + e['id'])
        self.create('ALL', owner='PM', checker='quality-engineering-001')

    def items(self, items):
        (self.root / 'product/items.json').write_text(json.dumps({'items': items}, ensure_ascii=False), encoding='utf-8')

    def call(self, op, actor='PM', **kw):
        self.n += 1
        return pm.execute(self.root, dict(op=op, actor=actor, event_id='SIM-' + str(self.n), **kw))

    def t(self, tid):
        return next(t for t in pm.execute(self.root, {'op': 'status'})['tasks'] if t['id'] == tid)

    def create(self, tid, **kw):
        data = dict(id=tid, parent=None, title='SIM ' + tid, goal='SIMULATED', inputs=['SIM v1'], outputs=['SIM output'], criteria=['SIM ok'], next_action='SIM next')
        data.update(kw)
        data.setdefault('executor', data['owner'])
        return self.call('create', task=data)

    def mutate(self, op, tid, actor=None, **kw):
        t = self.t(tid)
        return self.call(op, actor or t['owner'], task_id=tid, expected_revision=t['revision'], **kw)

    def finish(self, tid):
        self.mutate('update', tid, changes={'evidence': ['SIMULATED work ' + tid]}, reason='SIM work')
        self.mutate('review', tid, self.t(tid)['checker'], outcome='passed', criteria_checked=self.t(tid)['criteria'], evidence=['SIMULATED check'])
        return self.mutate('transition', tid, self.t(tid)['manager'], state='done', reason='SIM accepted')

    def scope(self, exits=BOTH, **kw):
        return self.call('register_scope', id='S', root_task='ALL', source={'path': 'product/items.json', 'keys': ['items'], 'id_key': 'id'},
                         required_exits=list(exits), known_complete=True, **kw)

    def record(self):
        return pm.execute(self.root, {'op': 'status'})['integrity']['scope']['S']

    def bind(self, member, exit_name, tid, actor='PM'):
        return self.call('bind_delivery', actor, id='S', expected_revision=self.record()['revision'], member_id=member, exit=exit_name,
                         task_id=tid, work_revision=self.t(tid)['work_revision'])

    def add(self, actor, member='R-LOGIN-08', exit_name='production:experience-design', reason='SIM 设计提出需要插图'):
        return self.call('add_exit', actor, id='S', expected_revision=self.record()['revision'], member_id=member, exit=exit_name, reason=reason)

    def gaps(self):
        return {(i['member_id'], i['exit'], i['code']) for i in pm.execute(self.root, {'op': 'audit', 'task_ids': ['ALL']})['issues'] if 'member_id' in i}

    def test_production_exits_come_only_from_the_items_declarations(self):
        scope = self.scope()['record']
        self.assertEqual([{'item': 'R-LOGIN-07', 'version': 'v1'}, {'item': 'R-LOGIN-08', 'version': 'v2'}],
                         scope['exit_sources']['production:code-engineering']['declared_by'])
        with self.assertRaisesRegex(pm.TaskError, 'production:experience-design has no provenance: not declared by item R-LOGIN-08'):
            self.scope(BOTH + ['production:experience-design'], expected_revision=scope['revision'])
        with self.assertRaisesRegex(pm.TaskError, 'invalid delivery exits'):
            self.scope(BOTH + ['production:astrology'], expected_revision=scope['revision'])
        self.items(['R-LOGIN-07', 'R-LOGIN-08'])  # plain ids declare nothing
        self.call('register_scope', id='PLAIN', root_task='ALL', source={'path': 'product/items.json', 'keys': ['items']}, required_exits=['qa'], known_complete=True)
        with self.assertRaisesRegex(pm.TaskError, 'no provenance'):
            self.call('register_scope', id='PLAIN2', root_task='ALL', source={'path': 'product/items.json', 'keys': ['items']}, required_exits=BOTH, known_complete=True)

    def test_a_product_contract_snapshot_is_a_scope_source(self):
        meta = {'format': contract.FORMAT, 'revision': 'v3', 'items': [
            {'id': 'R-LOGIN-07', 'kind': 'requirement', 'heading': '## 登录失败：系统原因', 'exits': {'code-engineering': '实现', 'quality-engineering': '验收'}},
            {'id': 'R-LOGIN-08', 'kind': 'requirement', 'heading': '## 登录失败：账号原因', 'exits': ['code-engineering', 'quality-engineering']},
            {'id': 'AC-07', 'kind': 'acceptance', 'heading': '## 验收：系统原因', 'refs': ['product/01-产品定义.md#R-LOGIN-07'], 'verify_at': 'implementation'},
            {'id': 'AC-08', 'kind': 'acceptance', 'heading': '## 验收：账号原因', 'refs': ['product/01-产品定义.md#R-LOGIN-08'], 'verify_at': 'implementation'}]}
        body = ''.join('## ' + h + '\nSIMULATED 正文。\n\n' for h in ['登录失败：系统原因', '登录失败：账号原因', '验收：系统原因', '验收：账号原因'])
        (self.root / 'product/01-产品定义.md').write_text('# 产品\n\n' + body + '```product-contract\n' + json.dumps(meta, ensure_ascii=False) + '\n```\n', encoding='utf-8')
        (self.root / 'product/baselines').mkdir()
        (self.root / 'product/baselines/v3.json').write_text(contract.json_text(contract.capture(self.root, ['product/01-产品定义.md'])), encoding='utf-8')
        source = {'path': 'product/baselines/v3.json', 'keys': ['items'], 'id_key': 'id'}
        with self.assertRaisesRegex(pm.TaskError, 'not declared by item AC-07'):
            self.call('register_scope', id='SNAP', root_task='ALL', source=source, required_exits=BOTH, known_complete=True)
        record = self.call('register_scope', id='SNAP', root_task='ALL', source=dict(source, where={'kind': 'requirement'}),
                           required_exits=BOTH, known_complete=True)['record']
        self.assertEqual(['R-LOGIN-07', 'R-LOGIN-08'], record['members'])
        self.assertEqual([{'item': 'R-LOGIN-07', 'version': 'v3'}, {'item': 'R-LOGIN-08', 'version': 'v3'}],
                         record['exit_sources']['production:quality-engineering']['declared_by'])

    def test_a_master_adds_an_exit_with_a_reason_and_no_change_plan(self):
        self.scope()
        with self.assertRaisesRegex(pm.TaskError, 'master instance'):
            self.add('code-engineering-002')
        with self.assertRaisesRegex(pm.TaskError, 'master instance'):
            self.add('PM')
        with self.assertRaisesRegex(pm.TaskError, 'reason'):
            self.add('experience-design-001', reason='')
        with self.assertRaisesRegex(pm.TaskError, 'already required'):
            self.add('experience-design-001', exit_name='production:code-engineering')
        added = self.add('experience-design-001')['record']['member_exits']['R-LOGIN-08']['production:experience-design']
        self.assertEqual(('experience-design-001', 'SIM 设计提出需要插图'), (added['added_by'], added['reason']))
        self.assertIn(('R-LOGIN-08', 'production:experience-design', 'delivery_unmapped'), self.gaps())
        self.assertNotIn(('R-LOGIN-07', 'production:experience-design', 'delivery_unmapped'), self.gaps())

    def test_member_completes_only_with_every_exit_bound_current_and_checked(self):
        self.scope()
        self.add('experience-design-001')
        tasks = {'CODE': 'code-engineering-001', 'QA': 'quality-engineering-001', 'ART': 'experience-design-001'}
        for tid, owner in tasks.items():
            self.create(tid, owner=owner, checker='product-001')
        with self.assertRaisesRegex(pm.TaskError, 'another profession'):
            self.bind('R-LOGIN-07', 'production:code-engineering', 'QA')
        with self.assertRaisesRegex(pm.TaskError, 'unknown member or exit'):
            self.bind('R-LOGIN-07', 'production:experience-design', 'ART')  # only R-LOGIN-08 got this exit
        for member in ['R-LOGIN-07', 'R-LOGIN-08']:
            self.bind(member, 'production:code-engineering', 'CODE')
            self.bind(member, 'production:quality-engineering', 'QA')
        self.bind('R-LOGIN-08', 'production:experience-design', 'ART')
        for tid in ['CODE', 'QA']:
            self.finish(tid)
            self.bind('R-LOGIN-07', 'production:' + {'CODE': 'code-engineering', 'QA': 'quality-engineering'}[tid], tid)
            self.bind('R-LOGIN-08', 'production:' + {'CODE': 'code-engineering', 'QA': 'quality-engineering'}[tid], tid)
        self.assertEqual({('R-LOGIN-08', 'production:experience-design', 'delivery_not_current')}, self.gaps())
        listed = pm.execute(self.root, {'op': 'tasks_for', 'as': 'PM'})
        rows = {r[0]: dict(zip(listed['columns'], r)) for r in listed['rows']}
        self.assertEqual('关闭 R-LOGIN-07', rows['ALL']['下一步'])
        self.assertEqual('记 R-LOGIN-08 的 交互与视觉设计 出口', rows['ART']['完成后'])
        self.mutate('update', 'ALL', changes={'evidence': ['SIMULATED collection']}, reason='SIM')
        self.mutate('review', 'ALL', 'quality-engineering-001', outcome='passed', criteria_checked=['SIM ok'], evidence=['SIMULATED check'])
        with self.assertRaisesRegex(pm.TaskError, 'delivery_not_current'):
            self.mutate('transition', 'ALL', 'PM', state='done', reason='SIM')
        self.finish('ART')
        self.bind('R-LOGIN-08', 'production:experience-design', 'ART')
        self.assertEqual(set(), self.gaps())
        self.mutate('review', 'ALL', 'quality-engineering-001', outcome='passed', criteria_checked=['SIM ok'], evidence=['SIMULATED check'])
        self.mutate('transition', 'ALL', 'PM', state='done', reason='SIM all exits delivered')

    def test_removing_an_added_exit_needs_the_amendment_path(self):
        scope = self.scope()['record']
        self.add('experience-design-001')
        keep = {'R-LOGIN-08': []}
        with self.assertRaisesRegex(pm.TaskError, 'recorded change'):
            self.scope(expected_revision=self.record()['revision'], member_exits=keep)
        self.scope(expected_revision=self.record()['revision'])  # re-registering unchanged keeps the added exit
        self.assertIn('production:experience-design', self.record()['member_exits']['R-LOGIN-08'])
        (self.root / 'oral.txt').write_text('SIMULATED: 不要插图了')
        self.create('ANALYZE', owner='product-001', checker='quality-engineering-001')
        self.call('record_change', id='C', type='remove', source='oral.txt', quote='SIM 不要插图了', analysis_task='ANALYZE', participants=['product-001'], scope_ids=['S'])
        self.scope(expected_revision=self.record()['revision'], member_exits=keep, change_id='C', scope_authorization='SIM recorded removal')
        self.assertEqual({}, self.record()['member_exits'])
        self.assertEqual(scope['exit_sources'], self.record()['exit_sources'])

    def test_view_shows_where_every_exit_came_from(self):
        self.scope(BOTH + ['qa'])
        self.add('experience-design-001')
        self.create('CODE', owner='code-engineering-001', checker='product-001')
        self.bind('R-LOGIN-07', 'production:code-engineering', 'CODE')
        pm.render(self.root)
        text = (self.root / 'management/views/scopes.md').read_text(encoding='utf-8')
        self.assertIn('| R-LOGIN-07 | 代码工程 | 来自 R-LOGIN-07 v1 的出口声明 | CODE | 未完成 |', text)
        self.assertIn('| R-LOGIN-08 | 代码工程 | 来自 R-LOGIN-08 v2 的出口声明 | — | 未绑定 |', text)
        self.assertIn('| R-LOGIN-08 | 交互与视觉设计 | 由 交互与视觉设计-001 追加：SIM 设计提出需要插图 | — | 未绑定 |', text)
        self.assertIn('| R-LOGIN-07 | 检验 | 登记范围时要求 | — | 未绑定 |', text)


if __name__ == '__main__':
    unittest.main()
