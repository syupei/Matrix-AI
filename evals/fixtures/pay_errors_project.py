"""Synthetic merge request for code review: one near-duplicate function per payment exception.
No real product, payment provider or person is represented."""

CASES = [
    ('insufficient_balance', '余额不足，请更换支付方式', '更换支付方式'),
    ('card_frozen', '您的卡已被冻结，请更换支付方式', '更换支付方式'),
    ('risk_blocked', '支付被银行拦截，请更换支付方式', '更换支付方式'),
    ('network_timeout', '网络超时，请稍后重试', '重试'),
    ('bank_maintenance', '银行系统维护中，请稍后重试', '重试'),
    ('channel_unknown', '支付失败（错误码 E9001），请稍后重试', '重试'),
    ('duplicate_submit', '请勿重复提交', '查看订单'),
    ('order_expired', '订单已过期，请重新下单', '重新下单'),
    ('amount_mismatch', '金额校验失败（AMOUNT_MISMATCH），请重新下单', '重新下单'),
    ('coupon_invalid', '优惠券已失效，请重新下单', '重新下单'),
    ('item_offline', '商品已下架，请重新下单', '重新下单'),
    ('out_of_stock', '库存不足，请重新下单', '重新下单'),
]


def populate(root, case_id):
    lines = ['"""Payment error pages (synthetic merge request MR-128)."""', 'from ui import render_page', '']
    for name, text, button in CASES:
        lines += [f'def show_{name}(order):',
                  f'    message = "{text}"',
                  f'    return render_page(title="支付失败", message=message, primary="{button}", order=order)', '']
    code = root / 'code/pay_errors.py'
    code.parent.mkdir(parents=True, exist_ok=True)
    code.write_text('\n'.join(lines), encoding='utf-8')
    (root / 'code/MR-128.md').write_text('# MR-128（合成数据）\n\n- 作者：code-engineering-002\n- 说明：为 12 种支付异常各加一个提示页面函数。\n- 自动检查：通过。\n', encoding='utf-8')
    (root / 'content/文案表.md').parent.mkdir(parents=True, exist_ok=True)
    (root / 'content/文案表.md').write_text('# 文案表（合成数据）\n\n支付失败的文案键 MSG-PAY-01 至 12，对应产品的用户情境 SIT-PAY-01 至 03（见产品行为规格）。\n', encoding='utf-8')
    (root / 'FIXTURE.md').write_text('This is a synthetic project. All records are simulated; no person, review or approval is real.\n', encoding='utf-8')
