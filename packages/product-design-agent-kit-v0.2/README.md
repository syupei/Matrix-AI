# 产品与设计 Agent 联合试验包 v0.2

包含 product-agent v0.9、experience-design-agent v0.2、professional-collaboration 0.1 和新增共同反馈工作规则 0.1。旧联合包 v0.1 保留。产品七阶段、设计七阶段及既有人审节点不变；原能力模型、48 项能力和产品首轮表单不变。

本次纳入三项用户已要求的改进：

1. 工具与素材选择：按任务、真实工具能力和现有体系选择；分阶段制作、记录来源/版本/使用位置，检查实际结果。
2. 外部资料接入：区分强制规范、参考、素材及旧稿，提取可追溯约束，处理冲突与中途新增的影响。
3. 产品与设计共同反馈处理：收到意见说明阶段归属与理由；当前事项实际调整、后续事项持久记录，基础变化及时处理，阶段切换主动接续。

- [接入、升级与启动语](START.md)。
- [产品 skill](.agents/skills/product-agent/SKILL.md) / [设计 skill](.agents/skills/experience-design-agent/SKILL.md)。
- [共同反馈规则](collaboration/FEEDBACK-PROTOCOL.md) / [协作协议](collaboration/CONTRACT.md) / [实际角色配置模板](collaboration/ROLE-CONFIG-TEMPLATE.md)。
- [工具与素材](.agents/skills/experience-design-agent/references/tool-execution.md) / [外部资料接入](.agents/skills/experience-design-agent/references/external-inputs.md)。
- [人的试验观察指南](DEMO-TEST.md) / [验证范围](VALIDATION.md)。

共同反馈规则是流程补充，消息协议仍为 0.1；存在工具/skill 不等于账号已连接或两个 Agent 正在运行。本包没有安装插件、注册模型、实现调度器或后台提醒；不同执行实例仍需真实配置。

项目反馈索引 collaboration/feedback.md 和资料/素材记录由 Agent 在出现实际内容时按需创建；不随包提供空项目台账。现有反馈记录按唯一位置纳入索引，不搬走或覆盖用户成果。

本包未包含实际 product/ 或 design/ demo、来源项目记忆或私人路径。测试仍在用户独立项目进行；格式/引用/压缩检查不等于真实多轮行为、专业设计或跨模型协作已经通过。
