"""Synthetic project for mi_stale_basis: the shared team project plus the half-written price display code
(written against R-CART-05 v3) and the executor's progress note. Nothing here is real."""
import importlib.util
from pathlib import Path

# Shared-project loader (inlined so this file's hash covers it; the shared project is pinned by its hash).
import hashlib

HERE = Path(__file__).resolve().parent
BASE_SHA256 = '141df320809afcee2103443a9390cf0f46c77cc120ae5e2a6982bd3ad0f62969'


def load(name):
    path = HERE / (name + '.py')
    spec = importlib.util.spec_from_file_location('team_extra_' + name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def base_project(root, case_id):
    """Populate the shared project for case_id and return (base module, task tool, call)."""
    path = HERE / 'team_project.py'
    if hashlib.sha256(path.read_bytes()).hexdigest() != BASE_SHA256:
        raise ValueError('team_project.py changed; update the extending fixtures')
    base = load('team_project')
    base.populate(root, case_id, final=False)
    spec = importlib.util.spec_from_file_location('team_extra_tools', base.SOURCE / 'matrix/orchestration/tools/pm_tasks.py')
    pm = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(pm)
    counter = [0]

    def call(op, actor=base.PM, **kw):
        counter[0] += 1
        return pm.execute(root, dict(op=op, actor=actor, event_id='SYNTHETIC-X-' + str(counter[0]), **kw))
    return base, pm, call


def write(root, rel, text):
    path = Path(root) / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')

CODE = '''"""购物车价格显示（合成；按 R-CART-05 v3 写到一半）。"""

FULL_REDUCTION_THRESHOLD = 9900  # 分；R-CART-05 v3：满 99 元减 10 元
FULL_REDUCTION_AMOUNT = 1000


def format_amount(cents):
    """金额显示，与满减规则无关。"""
    return '¥{}.{:02d}'.format(cents // 100, cents % 100)


def goods_total(items):
    """商品金额合计，与满减规则无关。"""
    return sum(item['price_cents'] * item['quantity'] for item in items)


def reduction_hint(total_cents):
    """距离满减还差多少（依赖 R-CART-05）。写到一半。"""
    if total_cents >= FULL_REDUCTION_THRESHOLD:
        return '已满减'
    # TODO: 显示还差多少元


# 还没写：
# - shipping_display(items)：运费显示，按 R-CART-06，与满减规则无关；
# - payable_display(items)：应付金额 = 商品金额 - 满减，依赖 R-CART-05。
'''

PROGRESS = '''# T-0043 进度（code-engineering-002，合成）

依据：R-CART-05 v3（满减）、R-CART-06 v1（运费）。代码（候选，在本实例工作区）：code/cart/price_display.py。

- 已完成：format_amount、goods_total（与满减规则无关）。
- 进行中：reduction_hint（依赖满减门槛）。
- 未开始：shipping_display（与满减规则无关）、payable_display（依赖满减）。
'''


def populate(root, case_id):
    root = Path(root)
    base, pm, call = base_project(root, 'mi_stale_basis')
    write(root, 'management/instances/code-engineering-002/workspace/code/cart/price_display.py', CODE)
    write(root, 'product/rules/R-CART-06.md', '# R-CART-06 运费规则（v1，合成）\n\n- 商品金额满 59 元免运费，不满 59 元收运费 6 元。\n- 运费按商品金额计算，与满减无关。\n')
    write(root, 'management/instances/code-engineering-002/workspace/T-0043-进度.md', PROGRESS)
    task = next(t for t in pm.execute(root, {'op': 'status'})['tasks'] if t['id'] == 'T-0043')
    call('update', task['owner'], task_id='T-0043', expected_revision=task['revision'],
         changes={'next_action': '按 R-CART-05 v3 与 R-CART-06 v1 继续写工作区里的 code/cart/price_display.py；进度见 management/instances/code-engineering-002/workspace/T-0043-进度.md'},
         reason='SYNTHETIC progress note from code-engineering-002')
    base.layout.adapt(root)
