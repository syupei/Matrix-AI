"""Synthetic project with a keyed copy table for a login screen. No real product or person is represented."""


FILES = {
    'content/文案表.md': '''# 文案表（合成数据）

| 键 | 情境 | 文字 | 变量与长度 | 语气 | 状态 | 使用位置 |
| --- | --- | --- | --- | --- | --- | --- |
| MSG-LOGIN-01 | SIT-LOGIN-01 验证码错误 v1 | 验证码不正确，请重新输入。 | ≤ 20 字 | 普通提示 | 已认可 | 登录页输入框下方 |
| MSG-LOGIN-02 | SIT-LOGIN-02 验证码过期 v1 | 验证码已失效，请重新获取。 | ≤ 20 字 | 普通提示 | 已认可 | 登录页输入框下方 |
| MSG-LOGIN-03 | SIT-LOGIN-03 发送太频繁 v1 | 发送过于频繁，请 {秒数} 秒后再试。 | 秒数为整数；≤ 22 字 | 普通提示 | 已认可 | 登录页"获取验证码"按钮下方 |
| MSG-LOGIN-04 | SIT-LOGIN-04 网络断开 v1 | 网络连接失败，请检查网络后重试。 | ≤ 20 字 | 错误 | 已认可 | 登录页顶部提示条 |
''',
    'product/01-产品定义.md': '''# 登录（合成数据）

- 短信验证码登录；四种用户情境 SIT-LOGIN-01 至 04 见行为规格，用户看到的文字见 `content/文案表.md`。
- 设计与代码引用文案键，不抄写文字。
''',
    'FIXTURE.md': 'This is a synthetic project. All records are simulated; no person, review or approval is real.\n',
}


def populate(root, case_id):
    for rel, text in FILES.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')
