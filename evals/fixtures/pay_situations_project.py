"""Synthetic shop project: product user situations for payment failures and a keyed copy table.
No real product, payment provider or person is represented."""

CAUSES = [
    ('MSG-PAY-01', 'SIT-PAY-01', '余额不足', '账户余额不足，请换一种方式付款。'),
    ('MSG-PAY-02', 'SIT-PAY-01', '卡被冻结', '这张卡暂时不能使用，请换一张卡或其他方式付款。'),
    ('MSG-PAY-03', 'SIT-PAY-01', '银行风控拦截', '银行暂未通过这笔付款，请换一种方式付款。'),
    ('MSG-PAY-04', 'SIT-PAY-02', '网络超时', '网络有点慢，请稍后再试。'),
    ('MSG-PAY-05', 'SIT-PAY-02', '银行系统维护', '银行系统正在维护，请稍后再试。'),
    ('MSG-PAY-06', 'SIT-PAY-02', '支付渠道返回未知错误', '付款没有完成，请稍后再试；如已扣款会自动退回。'),
    ('MSG-PAY-07', 'SIT-PAY-02', '重复提交', '这笔付款正在处理，请稍候查看结果。'),
    ('MSG-PAY-08', 'SIT-PAY-03', '订单已过期', '订单已超时，请重新下单。'),
    ('MSG-PAY-09', 'SIT-PAY-03', '金额校验失败', '订单信息有变化，请重新确认后付款。'),
    ('MSG-PAY-10', 'SIT-PAY-03', '优惠券已失效', '优惠券已失效，请重新确认订单金额。'),
    ('MSG-PAY-11', 'SIT-PAY-03', '商品已下架', '部分商品已下架，请重新确认订单。'),
    ('MSG-PAY-12', 'SIT-PAY-03', '库存不足', '部分商品库存不足，请重新确认订单。'),
]

SITUATIONS = '''# 功能与行为规格：支付失败（合成数据）

### 用户情境表

| 编号 | 用户遇到的情况 | 产品怎样表现 | 包括哪些失败或原因 | 文案键（内容填） |
| --- | --- | --- | --- | --- |
| SIT-PAY-01 v1 | 这种方式付不了，换一种就行 | 留在收银台，提示原因，主按钮"换一种方式付款" | 余额不足、卡被冻结、银行风控拦截 | MSG-PAY-01 至 03 |
| SIT-PAY-02 v1 | 暂时付不了，稍后再试 | 留在收银台，提示原因，主按钮"重试"；结果未知时显示处理中并可查看订单 | 网络超时、银行系统维护、支付渠道返回未知错误、重复提交 | MSG-PAY-04 至 07 |
| SIT-PAY-03 v1 | 订单变了，要重新确认 | 回到订单确认页，标出变化的部分，主按钮"重新确认" | 订单已过期、金额校验失败、优惠券已失效、商品已下架、库存不足 | MSG-PAY-08 至 12 |
'''


def populate(root, case_id):
    spec = root / 'product/specs/02-功能与行为规格.md'
    spec.parent.mkdir(parents=True, exist_ok=True)
    spec.write_text(SITUATIONS, encoding='utf-8')
    rows = ['| 键 | 情境 | 文字 | 状态 |', '| --- | --- | --- | --- |']
    rows += [f'| {key} | {sit} v1（{cause}） | {text} | 已认可 |' for key, sit, cause, text in CAUSES]
    table = root / 'content/文案表.md'
    table.parent.mkdir(parents=True, exist_ok=True)
    table.write_text('# 文案表（合成数据）\n\n' + '\n'.join(rows) + '\n', encoding='utf-8')
    note = root / 'design/00-工作状态.md'
    note.parent.mkdir(parents=True, exist_ok=True)
    note.write_text('# 工作状态（合成数据）\n\n- 设计方向与组件库已确认；已有组件：提示条、弹窗、整页提示（标题、说明、主按钮、次按钮）。\n- 下一步：支付失败的界面。\n', encoding='utf-8')
    (root / 'FIXTURE.md').write_text('This is a synthetic project. All records are simulated; no person, review or approval is real.\n', encoding='utf-8')
