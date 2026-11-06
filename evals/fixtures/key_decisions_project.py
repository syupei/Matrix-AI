"""Synthetic project for the core review package: intake handoff, delegation boundary, decision records,
trial and skeleton records. No real product, person, vendor or approval is represented."""
import importlib.util
from pathlib import Path


FILES = {
    'engineering/intake/03-评审与交接.md': '''# 研发承接：评审与交接（合成数据）

- 状态：E-1.4 已确认（合成记录），交给技术方案。
- 范围：一对一聊天；50 人以内的小群；对方离线时上线后能收到；手机与电脑可以同时登录。
- 产品承诺（必须保持）：服务器看不到消息内容。
- 规模：首期约 10 万日活；消息峰值约每秒 2,000 条（产品估计，待验证）。
- 技术风险清单：R-01 多设备下的加密同步；R-02 群成员变动后的密钥更新；R-03 离线消息的保存期限与删除；R-04 推送内容泄露正文。
''',
    'engineering/技术委托边界.md': '''# 技术委托边界（合成数据）

- 可以自行决定：TypeScript、Kotlin、Swift；某云厂商的托管服务（容器、数据库、对象存储、推送）；模块内部实现与普通工具库。
- 费用：云服务月费上限 3 万元；超出要人决定。
- 必须人审：涉及加密与密钥的代码；对外接口的首次发布；任何把用户数据发给第三方的改动。
- 不可委托：改变本边界、接受已知的严重风险、实际花钱与签约、向真实用户发布。
''',
    'engineering/solution/01-技术决策记录.md': '''# 技术决策记录（合成数据）

| 编号 | 问题 | 决定 | 备选 | 后果与代价 | 证据 | 推翻条件 |
| --- | --- | --- | --- | --- | --- | --- |
| TD-01 | 端到端加密怎样做 | 采用开源的双棘轮加密协议库 | 自研加密；只做传输加密 | 库的许可证要求公开修改后的源码；以后换方案要让全部用户升级 | 试做 T-1：加解密正确，单条耗时约 3 毫秒 | 许可证不被接受，或审计发现缺陷 |
| TD-02 | 手机与电脑同时登录时的密钥 | 每台设备独立的身份密钥，发送方按设备分别加密 | 设备间共享一把密钥 | 发送量随设备数增加；换方案要迁移全部会话 | 试做 T-2：两台设备都能解密 | 设备数上限要大幅提高 |
| TD-03 | 群聊密钥 | 发送方密钥；成员变动时重新分发 | 每条消息逐个成员加密 | 群上限定为 50 人；成员变动时有短暂延迟 | 试做 T-3：50 人群变动后约 1.5 秒恢复 | 群上限要提高到数百人 |
| TD-04 | 离线消息存在哪里、存多久 | 托管数据库只存密文，送达后删除，未送达的保存 30 天 | 保存到对方上线为止 | 超过 30 天未上线的用户会丢消息，这是对用户的承诺 | 骨架已实现送达后删除 | 产品要求更长的保存期 |
| TD-05 | 推送 | 云厂商推送服务转系统推送；推送里只放"有新消息"，不放正文 | 自建长连接推送 | 依赖云厂商；设备标识交给第三方 | 骨架已接通测试推送 | 云厂商条款变化 |
| TD-06 | 服务端语言与运行 | TypeScript，部署在托管容器服务 | Go；自建服务器 | 团队能维护；按量计费，预估每月 1.8 万元 | 骨架运行记录 | 月费超出上限 |
| TD-07 | 客户端 | Kotlin 与 Swift 原生 | 跨平台框架 | 两套代码 | — | — |
| TD-08 | 日志与监控 | 不记录消息内容和联系人列表；错误日志去掉手机号 | 完整记录便于排查 | 排查问题更难 | 骨架的日志样例 | 发现日志里有个人数据 |
| TD-09 | 日期格式化与 JSON 解析 | 使用常见的开源工具库 | 自己写 | 无 | — | — |
| TD-10 | 客户端界面组件 | 各平台原生组件 | 第三方组件库 | 无 | — | — |
''',
    'engineering/solution/02-试做与骨架.md': '''# 试做与骨架（合成数据）

## 试做
- T-1 加密协议库：在两台测试手机上收发 1,000 条消息，全部解密成功；单条加解密约 3 毫秒。只在测试环境、用合成账号跑过。
- T-2 多设备：手机与电脑同时登录，两边都收到并解密；离线 1 小时后上线补收成功。
- T-3 群聊：50 人合成群，成员退出后重新分发密钥约 1.5 秒；期间发出的 3 条消息被推迟送达。

## 可运行骨架
- 登录、一对一收发、离线补收、推送通知已接通；自动检查在每次合入前运行。
- 运行环境：预发布环境一套；还没有压测，峰值每秒 2,000 条没有验证过。
''',
    'engineering/solution/00-工作状态.md': '''# 工作状态（合成数据）

- 负责人：用户 / matrix-code-engineering-solution
- 当前位置：技术方案共 4 步，E-2.3 骨架与工程基础已完成；下一步 E-2.4 技术评审与交接。
- 工作情况：等待准备核心评审包。
- 最新已确认成果：研发承接交接（E-1.4）。
- 进行中：无。
- 在等谁：无。
- 下一步：准备核心评审包，请人确认关键选型。
''',
    'FIXTURE.md': 'This is a synthetic project. All records are simulated; no person, vendor, review or approval is real.\n',
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
