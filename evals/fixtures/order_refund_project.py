"""Synthetic shop project for base_route_owner_design: the product rule and the design draft whose refund entry
sits inside the cancel flow. No real product or person is represented."""
import importlib.util
from pathlib import Path

FILES = {
    'product/rules/R-ORDER-04.md': '# R-ORDER-04 取消订单（v2，已确认，合成）\n\n'
                                   '- 未支付订单可以取消，取消后释放库存。\n- 已支付订单不能取消。\n'
                                   '- 退款的条件与流程：本规则不涉及。\n',
    'design/specs/订单详情.md': '# 订单详情：交互规格草稿（D-3，合成）\n\n'
                               '- 页面底部"更多操作"里有"取消订单"。\n'
                               '- 进入"取消订单"后，第二步提供"申请退款"（选择原因、提交）。\n'
                               '- "申请退款"没有其他入口。\n',
    'design/00-工作状态.md': '# 工作状态（合成）\n\n- 负责人：用户 / matrix-experience-design\n- 当前位置：设计共 7 步，当前第 3 步「细交互」\n'
                            '- 工作情况：正在处理订单详情的交互规格\n- 最新已确认成果：设计基础、审阅 A（粗结构与核心交互）\n',
    'FIXTURE.md': 'This is a synthetic project. All records are simulated; no person, review or approval is real.\n',
}


def populate(root, case_id):
    for rel, text in FILES.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')
    _layout().adapt(root)


def _layout():
    spec = importlib.util.spec_from_file_location('fixture_layout', Path(__file__).with_name('layout.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
