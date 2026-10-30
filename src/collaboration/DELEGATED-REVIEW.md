# 委托内决定的阶段检查

何时读：已有明确委托让专业负责人处理某些阶段决定，而本次不是保留给人的关键判断时。专业过程不省略；没有委托沿原审阅节点。向真实用户发布、接受已知严重风险、实际花钱签约和改变委托边界仍由人决定。

真实授权记录后，项目维护 `collaboration/delegations.json`，包含 delegations 数组，每项为：id、revision、person_id（名单中的决定人；无名单个人项目为 user）、instance_id、role、stages、scope、source、source_sha256、expires_at（带时区的时间）、revoked（明确 false）。授权范围、期限和保留事项来自实际委托，不自行编造或扩大。撤回立即更新，来源内容变化使原摘要失效。人的名单即使只有一人也按其实际权限核对。

默认阶段检查保留。委托覆盖的阶段以 delegated_decision 替代该次 request/response 输入，指向记录 JSON：delegation_id、delegation_revision、instance_id、decision_kind= routine、role、stage、scope、artifact_sha256、source（决定依据）、producers（实际作者及整合实例清单，不得遗漏）、review（独立检查记录）。review 含 checker、outcome=passed、scope、artifact_sha256、evidence，checker 不得为本次决定/整合实例。实际实施者也不得承担自己成果的独立检验。

[阶段工具](tools/stage_gate.py) 重新核对有效期、授权来源、决定人权限、角色/阶段/范围、当前成果摘要和独立检查。通过返回 decision_basis=delegated，明确为“授权内决定”，不生成 human_review approved 或“用户已确认”。发布决定不接受此路径；关键取舍或事实未知也不能伪装 routine。

工具仍只检查记录，不认证人的身份或判断决定是否真的常规。由可信项目授权来源和运行层确保记录权限；人工批准与代理决定分别保留。已经明确保留的人审不因使用团队模式消失；部分答复只放行该范围，独立工作可继续。
