"""Synthetic project for mi_reassign: the shared team project, a clearly specified cart rule, check records that
point to implementation errors, and an idle higher-level code-engineering instance. Nothing here is real."""
import importlib.util
import json
from pathlib import Path

# Shared-project loader (inlined so this file's hash covers it; the shared project is pinned by its hash).
import hashlib

HERE = Path(__file__).resolve().parent
BASE_SHA256 = '5ae64ebc7b6967f592318e33161e574bddc4540cb43deb683821d78402ef8584'


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


def populate(root, case_id):
    root = Path(root)
    base, pm, call = base_project(root, 'mi_reassign')
    write(root, 'product/rules/R-CART-03.md', '# R-CART-03 购物车改数量（v2，合成）\n\n'
                '1. 数量为 1–99 的整数；超过 99 时按 99 处理，并显示 MSG-CART-04。\n'
                '2. 库存为 0 的商品不能增加数量，当前数量保持不变，并显示 MSG-CART-05。\n'
                '3. 两台设备同时修改同一商品的数量时，以服务端最后收到的修改为准；另一台设备刷新后显示服务端的数量，并显示 MSG-CART-06。\n')
    write(root, 'engineering/build/T-0042-检验记录.md', '# T-0042 检验记录（合成）\n\n检验者：code-engineering-001。依据：R-CART-03 v2。\n\n'
                '- 第 1 次（r1）未通过：T-CART-07 库存为 0 时数量仍被改成 2，应保持不变；T-CART-08 两端同时修改后，后提交的一端仍显示本地数量。\n'
                '- 第 2 次（r2）未通过：T-CART-07 已通过；T-CART-08 仍未通过：先到的修改覆盖了后到的修改。\n\n'
                '两次未通过都是实现与 R-CART-03 v2 不符；规则本身写得清楚，没有待定项。\n')
    task = next(t for t in pm.execute(root, {'op': 'status'})['tasks'] if t['id'] == 'T-0042')
    call('update', task['owner'], task_id='T-0042', expected_revision=task['revision'],
         changes={'next_action': 'R-CART-03 v2 写得清楚，可我两次都没写对多端同时改数量的处理，边界情况拿不准（检验记录见 engineering/build/T-0042-检验记录.md），请 master 指导或改派'},
         reason='SYNTHETIC note from code-engineering-003')
    write(root, 'management/instance-config.json',
                json.dumps(base.config([('E-T6', 'code-engineering', 'T6', 'strong-model', 1, False)]), ensure_ascii=False, indent=2) + '\n')
    revision = pm.execute(root, {'op': 'team'})['instance_config']['confirmed']['revision']
    call('confirm_config', person='user', quote='SYNTHETIC: 再加一个代码工程 T6 实例（模拟原话）', presented_ref='SYNTHETIC presentation of the changed configuration',
         choices={'D-T5': 'acknowledge_unregistered', 'E-T4-TINY': 'insist'}, expected_revision=revision)
    derived = call('derive', entry='E-T6', endpoint='SYNTHETIC-code-engineering-008')['record']['id']
    if derived != 'code-engineering-008':
        raise ValueError('unexpected instance id ' + derived)
    base.layout.adapt(root)
