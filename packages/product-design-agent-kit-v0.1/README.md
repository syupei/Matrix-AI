# 产品与设计 Agent 联合试验包 v0.1

包含已接受的 product-agent v0.8 和新建 experience-design-agent v0.1，以及 professional-collaboration 0.1 共用约定。产品 skill 目录与原 v0.8 逐字节相同；新增独立设计 skill，根入口改为按职责选择。协作模板仅更新当前角色提供情况和入口说明，协议字段与语义不变。

这是可供真实 demo 检验的能力包，不是已部署的多 Agent 调度系统。两个 skill 可共存于同一项目，也可分别装入不同执行实例；模型与工具独立配置。自动互调依赖宿主通道，缺少时可进行明确标注的手工文件接力。

- [旧测试项目接入与启动语](START.md)：保留已有成果，合并入口，启动设计或双角色接力。
- [产品 skill](.agents/skills/product-agent/SKILL.md) / [设计 skill](.agents/skills/experience-design-agent/SKILL.md)。
- [共用协议](collaboration/CONTRACT.md) / [角色配置](collaboration/ROLE-CONFIG-TEMPLATE.md)。
- [人的试验观察指南](DEMO-TEST.md)。

设计默认顺序：接收基线 → 粗页面总览/骨架/主要流转并人审 → 细交互 → 代表性视觉与表达并人审 → 完整设计 → 综合走查及最终人审 → 基线交付。相关能力模型和用户具体风格要求持续作用于实际元素及工具产出。

本包没有 product/ 或 design/ demo 成果，没有预设“留言板”的业务答案，不含用户原会话/记忆。未全局安装，未更改任何既有试验项目。设计标准为与产品同版本的只读分发快照，便于独立模型读取。

验证结果见 [VALIDATION.md](VALIDATION.md)。格式与包完整性检查不证明设计专业判断或跨模型互调已通过真实试验。
