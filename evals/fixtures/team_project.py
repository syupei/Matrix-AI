"""Synthetic multi-instance project for the instance, task-chain and task-list cases.

No real person, vendor, model, endpoint or approval is represented. The same state is used whichever kit is
under evaluation: it is built with the tools of the candidate package built from this repository's source, never
with root/'kit', and then placed where the kit under test reads it (layout.py).
"""
import hashlib
import importlib.util
import json
from pathlib import Path

LAYOUT = Path(__file__).with_name('layout.py')
LAYOUT_SHA256 = '3701121f70faa302f858a567a7cf7d0324563eed3416c63cc1c6cb27f0cb5103'
if hashlib.sha256(LAYOUT.read_bytes()).hexdigest() != LAYOUT_SHA256:
    raise ValueError('layout.py changed; update team_project.py and the suite')
_layout_spec = importlib.util.spec_from_file_location('team_fixture_layout', LAYOUT)
layout = importlib.util.module_from_spec(_layout_spec)
_layout_spec.loader.exec_module(layout)
SOURCE = layout.candidate()  # package layout: matrix/... and .agents/skills/...
PM = 'project-management-001'
ENTRIES = [  # id, profession, level, model, count, master
    ('P-T7', 'product', 'T7', 'strong-model', 1, True), ('P-T5', 'product', 'T5', 'fast-model', 1, False),
    ('P-T3', 'product', 'T3', 'fast-model', 1, False),
    ('D-T7', 'experience-design', 'T7', 'strong-model', 1, True), ('D-T4', 'experience-design', 'T4', 'fast-model', 2, False),
    ('D-T5', 'experience-design', 'T5', 'draw-model', 1, False),
    ('E-T9', 'code-engineering', 'T9', 'strong-model', 1, True), ('E-T4', 'code-engineering', 'T4', 'fast-model', 4, False),
    ('E-T3', 'code-engineering', 'T3', 'fast-model', 1, False), ('E-T4-TINY', 'code-engineering', 'T4', 'tiny-model', 1, False),
    ('C-T6', 'content-design', 'T6', 'strong-model', 1, True), ('Q-T6', 'quality-engineering', 'T6', 'strong-model', 1, True)]
# Yields product-001..003, experience-design-001..004, code-engineering-001..007, content-design-001, quality-engineering-001.
ORDER = ['P-T7', 'P-T5', 'P-T3', 'D-T7', 'D-T4', 'D-T4', 'D-T5', 'E-T9', 'E-T4', 'E-T4', 'E-T4', 'E-T3', 'E-T4-TINY', 'E-T4', 'C-T6', 'Q-T6']
LOGIN_EXITS = {'content-design': '提示文字', 'experience-design': '弹窗与状态', 'code-engineering': '异常处理与对照表', 'quality-engineering': '验收'}
FIXTURE = ('This is a synthetic project for an isolated evaluation. Every person, model name, endpoint, task, check and '
           'approval in it is simulated; no instance is running and no real person has decided anything. The project '
           'manager is project-management-001 and the only person is user. The instance configuration is in '
           'management/instance-config.json and management/model-fit.json; instance records, the recorded '
           'confirmation and the tasks are in the task library (management/runtime/tasks.sqlite3); instance profiles are '
           'in management/instances/<instance id>/profile.md.\n')


def config(extra=()):
    return {'entries': [dict(id=i, profession=p, level=lv, model=m, count=c, **({'master': True} if master else {}))
                        for i, p, lv, m, c, master in ENTRIES + list(extra)]}


def model_fit():
    regs = [json.loads(p.read_text(encoding='utf-8')) for p in sorted((SOURCE / 'matrix/professions').glob('*/profession.json'))]
    caps = sorted({c for r in regs for c in r.get('model_capabilities', [])} | {'long_horizon', 'complex_dispatch', 'deep_reasoning'})
    code = next(r for r in regs if r['id'] == 'code-engineering')
    data = {'models': [
        {'model': 'strong-model', 'levels': {r['id']: r['levels']['range'][1] for r in regs}, 'capabilities': caps, 'filled_by': 'SYNTHETIC user'},
        {'model': 'fast-model', 'levels': {r['id']: min(r['levels']['range'][1], 'T5', key=lambda v: int(v[1:])) for r in regs},
         'capabilities': caps, 'filled_by': 'SYNTHETIC user'},
        {'model': 'tiny-model', 'levels': {'code-engineering': 'T3'}, 'capabilities': code.get('model_capabilities', []), 'filled_by': 'SYNTHETIC user'}]}

    for row in data['models']:
        row.update(basis='human', evidence=['SYNTHETIC assessment for fixture setup only'],
                   evaluated_at='2020-01-01T00:00:00Z', model_version=row['model'],
                   review_after='2099-01-01T00:00:00Z', review_conditions={})
    return data


def populate(root, case_id, final=True):
    """final=False leaves the state in the Matrix-AI layout for a fixture that adds to it and then calls layout.adapt."""
    root = Path(root)
    spec = importlib.util.spec_from_file_location('team_fixture_tools', SOURCE / 'matrix/orchestration/tools/pm_tasks.py')
    pm = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(pm)
    counter = 0

    def call(op, actor=PM, **kw):
        nonlocal counter
        counter += 1
        return pm.execute(root, dict(op=op, actor=actor, event_id='SYNTHETIC-' + str(counter), **kw))

    def write(rel, text):
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')

    def t(tid):
        return next(x for x in pm.execute(root, {'op': 'status'})['tasks'] if x['id'] == tid)

    def act(op, tid, actor=None, **kw):
        current = t(tid)
        return call(op, actor or current['owner'], task_id=tid, expected_revision=current['revision'], **kw)

    def task(tid, owner, title, parent=None, **kw):
        data = dict(id=tid, parent=parent, title=title, owner=owner, executor=owner, checker='quality-engineering-001',
                    goal='SYNTHETIC: ' + title, inputs=['SYNTHETIC input v1'], outputs=['SYNTHETIC output of ' + tid],
                    criteria=['SYNTHETIC acceptance of ' + tid], next_action='SYNTHETIC: 按任务包推进')
        data.update(kw)
        return call('create', PM if parent is None else t(parent)['owner'], task=data)

    def start(tid):
        act('transition', tid, state='running', reason='SYNTHETIC start', execution_receipt='SYNTHETIC start receipt; no live worker')

    def hand_over(tid, evidence):
        act('transition', tid, state='waiting_review', reason='SYNTHETIC handed over after self-check', stop_evidence='SYNTHETIC stop record', evidence=evidence)

    def check(tid, outcome='passed', **kw):
        current = t(tid)
        if not current['evidence']:
            act('update', tid, changes={'evidence': ['SYNTHETIC result of ' + tid]}, reason='SYNTHETIC work recorded')
        act('review', tid, current['checker'], outcome=outcome, criteria_checked=current['criteria'], evidence=['SYNTHETIC check record; not a real verification'], **kw)

    def close(tid):
        act('transition', tid, t(tid)['manager'], state='done', reason='SYNTHETIC accepted by the dispatcher')

    def finish(tid):
        check(tid)
        close(tid)

    def bind(member, exit_name, tid):
        scope = pm.execute(root, {'op': 'status'})['integrity']['scope']['S-LOGIN-07']
        call('bind_delivery', id='S-LOGIN-07', expected_revision=scope['revision'], member_id=member, exit=exit_name, task_id=tid, work_revision=t(tid)['work_revision'])

    def requirements(items):
        write('product/requirements.json', json.dumps({'revision': '1', 'note': 'SYNTHETIC product source', 'items': items}, ensure_ascii=False, indent=2) + '\n')

    call('init', config=dict(project='SYNTHETIC 合成电商 App', pm_actor=PM, authorization='SYNTHETIC local evaluation only; no real delegation',
                             frontdoor_id='SYNTHETIC-frontdoor', max_slots=12))
    write('management/model-fit.json', json.dumps(model_fit(), ensure_ascii=False, indent=2) + '\n')
    write('management/instance-config.json', json.dumps(config(), ensure_ascii=False, indent=2) + '\n')
    call('confirm_config', person='user', quote='SYNTHETIC: 按这份配置来（模拟原话）', presented_ref='SYNTHETIC presentation of the instance configuration',
         choices={'D-T5': 'acknowledge_unregistered', 'E-T4-TINY': 'insist'})
    numbers = {}
    for entry in ORDER:
        profession = next(e[1] for e in ENTRIES if e[0] == entry)
        numbers[profession] = numbers.get(profession, 0) + 1
        iid = profession + '-' + str(numbers[profession]).zfill(3)
        derived = call('derive', entry=entry, endpoint='SYNTHETIC-' + iid)['record']['id']
        if derived != iid:
            raise ValueError('unexpected instance id ' + derived + ' for ' + iid)

    cart = case_id in {'mi_dispatch_level', 'mi_reassign', 'mi_conflict', 'mi_stale_basis'}
    if cart:
        task('T-0040', 'code-engineering-001', 'INC-3 购物车', difficulty='T7', risk='F1', risk_reason='SYNTHETIC: 含价格计算与结算校验')
        start('T-0040')
    if case_id == 'base_over_level_code':
        write('engineering/solution/02-技术方案.md', '# 技术方案（合成）\n\n订单服务与支付服务之间的接口契约、重试与幂等的做法尚未确定。\n')
        task('T-0020', 'code-engineering-001', '订单与支付服务', difficulty='T8', risk='F1', risk_reason='SYNTHETIC: 涉及支付')
        start('T-0020')
        task('T-0021', 'code-engineering-005', '定义订单服务与支付服务之间的接口契约，并决定重试与幂等的做法', parent='T-0020', checker='code-engineering-001',
             difficulty='T3', risk='F2', risk_reason='SYNTHETIC: 主流程接口', inputs=['engineering/solution/02-技术方案.md v1'])
    elif case_id == 'base_over_level_product':
        write('product/specs/会员权益.md', '# 会员权益（合成）\n\n- 会员可以下载内容离线观看。\n- 会员到期后已下载内容的处理：未定。\n')
        task('T-0010', 'product-001', '会员权益', difficulty='T7', risk='F2', risk_reason='SYNTHETIC: 付费权益')
        start('T-0010')
        task('T-0012', 'product-003', '整理会员权益页的规则', parent='T-0010', checker='product-001', difficulty='T3', risk='F3',
             risk_reason='SYNTHETIC: 页面规则整理', inputs=['product/specs/会员权益.md v1'])
    elif case_id == 'mi_reassign':
        task('T-0042', 'code-engineering-003', '购物车改数量的边界处理', parent='T-0040', checker='code-engineering-001', difficulty='T4', risk='F3', risk_reason='SYNTHETIC: 非核心交互')
        start('T-0042')
        hand_over('T-0042', ['SYNTHETIC code/cart/quantity.py r1'])
        check('T-0042', outcome='failed', cause='execution')
        act('transition', 'T-0042', state='running', reason='SYNTHETIC rework', execution_receipt='SYNTHETIC start receipt; no live worker', note='SYNTHETIC: 两个边界用例失败，补上后重做')
        hand_over('T-0042', ['SYNTHETIC code/cart/quantity.py r2'])
        check('T-0042', outcome='failed', cause='execution')
        act('update', 'T-0042', changes={'next_action': '边界情况拿不准（库存为 0、多端同时改数量），请 master 指导或改派'}, reason='SYNTHETIC note from code-engineering-003')
    elif case_id == 'mi_conflict':
        write('engineering/solution/contracts/C-CART-02.md', '# C-CART-02 购物车数量接口（v1，合成）\n\n'
              '- 修改数量：`PUT /cart/items/{item_id}`，body `{"quantity": <整数>}`，返回更新后的购物车。\n'
              '- quantity 须为 0–99 的整数。\n- quantity 为 0 时，该商品不再计入购物车。\n- 结算只处理计入购物车的商品。\n')
        for tid, owner, title in [('T-0044', 'code-engineering-002', '购物车改数量接口的实现'), ('T-0045', 'code-engineering-004', '结算前的购物车商品校验')]:
            task(tid, owner, title, parent='T-0040', checker='code-engineering-001', difficulty='T4', risk='F2', risk_reason='SYNTHETIC: 主流程',
                 inputs=['engineering/solution/contracts/C-CART-02.md v1'])
            start(tid)
            hand_over(tid, ['SYNTHETIC code/cart/' + tid.lower() + '.py (cites C-CART-02 v1)'])
    elif case_id == 'mi_stale_basis':
        write('product/rules/R-CART-05.md', '# R-CART-05 满减规则（v4，合成）\n\n订单商品金额满 100 元减 10 元；购物车显示距离满减还差多少。\n\n'
              '## 变更记录\n\n- v4（合成）：满减门槛从 99 元改为 100 元。\n- v3（合成）：订单商品金额满 99 元减 10 元。\n')
        task('T-0043', 'code-engineering-002', '购物车价格显示', parent='T-0040', checker='code-engineering-001', difficulty='T4', risk='F2', risk_reason='SYNTHETIC: 价格展示',
             inputs=['product/rules/R-CART-05.md v3'])
        start('T-0043')
    elif case_id == 'mi_config_fit':
        task('T-FIT-P', 'code-engineering-001', 'SYNTHETIC model version observation', difficulty='T4', risk='F3', risk_reason='SYNTHETIC low-risk')
        task('T-FIT-W', 'code-engineering-002', 'SYNTHETIC prior worker run', parent='T-FIT-P', checker='code-engineering-001', difficulty='T4', risk='F3', risk_reason='SYNTHETIC low-risk')
        call('launch_start', id='SYNTHETIC-FIT-RUN', purpose='start', task_id='T-FIT-W', instance='code-engineering-002',
             model='fast-model-v2', session='SYNTHETIC', command=['SYNTHETIC-no-process'])
        call('launch_started', id='SYNTHETIC-FIT-RUN', pid=4242)
        hand_over('T-FIT-W', ['SYNTHETIC previous result; no real worker'])
        call('launch_exit', actor='launcher', id='SYNTHETIC-FIT-RUN', exit_code=0)
        write('management/instance-config.json', json.dumps(config([('E-T9-FAST', 'code-engineering', 'T9', 'fast-model', 1, False)]), ensure_ascii=False, indent=2) + '\n')
    elif case_id == 'mi_review_independence':
        task('T-0049', 'code-engineering-001', 'INC-4 会员扣费', difficulty='T7', risk='F1', risk_reason='SYNTHETIC: 扣费')
        start('T-0049')
        task('T-0050', 'code-engineering-002', '扣费逻辑', parent='T-0049', checker='code-engineering-001', difficulty='T4', risk='F1', risk_reason='SYNTHETIC: 扣费与对账')
        start('T-0050')
        hand_over('T-0050', ['SYNTHETIC code/billing/charge.py', 'SYNTHETIC code/billing/test_charge.py'])
    elif case_id in {'chain_login', 'completion_push_pm'}:
        write('product/specs/登录失败.md', '# 登录失败：系统原因（合成）\n\nR-LOGIN-07 v1：服务端或网络原因导致登录失败时，弹窗提示稍后重试，用户可以重试。\n')
        requirements([{'id': 'R-LOGIN-07', 'version': '1', 'status': 'confirmed', 'title': '登录失败：系统原因', 'spec': 'product/specs/登录失败.md', 'exits': LOGIN_EXITS}])
        task('T-0001', PM, 'R-LOGIN-07 登录失败：系统原因（交付集合）', slots=0)
        call('register_scope', id='S-LOGIN-07', root_task='T-0001', source={'path': 'product/requirements.json', 'keys': ['items'], 'id_key': 'id'},
             required_exits=['production:' + p for p in LOGIN_EXITS], known_complete=True)
        task('T-0002', 'product-001', '登录失败的用户情境与表现', difficulty='T5', risk='F2', risk_reason='SYNTHETIC: 主流程体验')
        finish('T-0002')
        task('T-0003', 'content-design-001', '登录提示文案（MSG-LOGIN-*）', checker='product-001', difficulty='T4', risk='F3', risk_reason='SYNTHETIC: 提示文字')
        start('T-0003')
        task('T-0004', 'experience-design-001', '登录失败弹窗的交互规格', checker='product-001', difficulty='T5', risk='F3', risk_reason='SYNTHETIC: 弹窗')
        finish('T-0004')
        bind('R-LOGIN-07', 'production:experience-design', 'T-0004')
        write('engineering/build/R-LOGIN-07-异常对照表.md', '# 异常对照表（合成）\n\n| 内部异常 | 用户情境 |\n| --- | --- |\n| SYNTHETIC-TIMEOUT | SIT-LOGIN-02 |\n')
        task('T-0005', 'code-engineering-001', '登录异常的处理与对照表（R-LOGIN-07 v1）', difficulty='T6', risk='F2', risk_reason='SYNTHETIC: 主流程')
        start('T-0005')
        hand_over('T-0005', ['engineering/build/R-LOGIN-07-异常对照表.md'])
        finish('T-0005')
        if case_id == 'chain_login':
            bind('R-LOGIN-07', 'production:code-engineering', 'T-0005')
        task('T-0006', 'quality-engineering-001', '登录失败的验收', checker='product-001', dependencies=['T-0005'], difficulty='T5', risk='F2', risk_reason='SYNTHETIC: 验收')
    elif case_id == 'chain_upstream_risk':
        requirements([{'id': 'R-BILL-01', 'version': '1', 'status': 'draft', 'risk': 'F1', 'title': '会员自动续费的扣费规则'},
                      {'id': 'R-LOGIN-08', 'version': '1', 'status': 'draft', 'risk': 'F2', 'title': '登录失败的提示表现'}])
        task('T-0014', 'product-001', '自动续费扣费规则与登录失败提示的规则草稿', checker='product-002', human_required=True, people={'decide': ['user']},
             difficulty='T5', risk='F1', risk_reason='SYNTHETIC: 含扣费规则', inputs=['product/requirements.json revision 1'])
        check('T-0014')
        act('transition', 'T-0014', state='waiting_review', reason='SYNTHETIC drafts shown for confirmation')
    elif case_id in {'list_pm', 'list_instance'}:
        task('T-0002', 'product-001', '登录失败的用户情境与表现', difficulty='T5', risk='F2', risk_reason='SYNTHETIC: 主流程体验')
        finish('T-0002')
        task('T-0003', 'content-design-001', '登录提示文案（MSG-LOGIN-*）', checker='product-001', difficulty='T4', risk='F3', risk_reason='SYNTHETIC: 提示文字')
        start('T-0003')
        task('T-0004', 'experience-design-001', '登录失败弹窗的交互规格', checker='product-001', difficulty='T5', risk='F3', risk_reason='SYNTHETIC: 弹窗',
             human_required=True, people={'decide': ['user']})
        check('T-0004')
        act('transition', 'T-0004', state='waiting_review', reason='SYNTHETIC shown for the person\'s review')
        task('T-0005', 'code-engineering-001', '登录异常的处理与对照表（R-LOGIN-07 v1）', difficulty='T6', risk='F2', risk_reason='SYNTHETIC: 主流程')
        start('T-0005')
        task('T-0031', 'code-engineering-007', '登录模块的异常对照表', parent='T-0005', checker='code-engineering-001', difficulty='T4', risk='F2', risk_reason='SYNTHETIC: 主流程')
        start('T-0031')
        act('transition', 'T-0031', state='blocked', reason='缺测试环境的数据库权限', stop_evidence='SYNTHETIC stop record')
        # One instance runs one task at a time: the master reports T-0005 blocked on T-0031 and works on T-0009.
        act('transition', 'T-0005', state='blocked', reason='等 T-0031：缺测试环境的数据库权限', stop_evidence='SYNTHETIC stop record', blocked_by={'task_id': 'T-0031'})
        task('T-0006', 'quality-engineering-001', '登录失败的验收', checker='product-001', dependencies=['T-0005'], difficulty='T5', risk='F2', risk_reason='SYNTHETIC: 验收')
        task('T-0009', 'code-engineering-001', '支付模块骨架', difficulty='T7', risk='F1', risk_reason='SYNTHETIC: 支付')
        start('T-0009')
        task('T-0052', 'code-engineering-004', '支付回调与对账接口', parent='T-0009', checker='code-engineering-001', difficulty='T4', risk='F2', risk_reason='SYNTHETIC: 主流程')
        start('T-0052')
        hand_over('T-0052', ['SYNTHETIC code/payment/callback.py'])
    elif case_id == 'report_up_executor':
        task('T-0005', 'code-engineering-001', '登录异常的处理与对照表（R-LOGIN-07 v1）', difficulty='T6', risk='F2', risk_reason='SYNTHETIC: 主流程')
        start('T-0005')
        task('T-0031', 'code-engineering-007', '登录模块的异常对照表', parent='T-0005', checker='code-engineering-001', difficulty='T4', risk='F2', risk_reason='SYNTHETIC: 主流程')
        start('T-0031')
        write('engineering/build/T-0031-异常对照表.md', '# 登录模块的异常对照表（合成）\n\n| 内部异常 | 用户情境 |\n| --- | --- |\n| SYNTHETIC-TIMEOUT | SIT-LOGIN-02 |\n| SYNTHETIC-LOCKED | SIT-LOGIN-03 |\n')
    elif case_id == 'chain_routing':
        write('product/specs/个人资料.md', '# 个人资料（合成）\n\nR-PROFILE-02 v1：用户可以修改头像和昵称。\n')
        requirements([{'id': 'R-PROFILE-02', 'version': '1', 'status': 'confirmed', 'title': '用户可以修改头像和昵称', 'spec': 'product/specs/个人资料.md'}])
    elif case_id not in {'base_level_answer_code', 'base_level_answer_design', 'mi_dispatch_level'}:
        raise ValueError('unknown team fixture case: ' + case_id)
    write('FIXTURE.md', FIXTURE)
    if final:
        layout.adapt(root)
