# 产品与设计 Agent 联合试验包 v0.3

包含 product-agent v0.10、experience-design-agent v0.3。消息协议 professional-collaboration 0.1 和反馈规则 0.1 保持不变，新增专业成果核对指引 0.1。保留原始能力模型、48 项能力、首轮表单、产品/设计七阶段和既有人审节点。

本版落实七项已确认优化：对象最小完整规格；关键参数来源及未知解除条件；跨对象/状态组合场景；实际成果覆盖与一致性；可复用质量样板；按需媒体生命周期；现有专业审阅入口与编辑来源。前五项按复杂度应用，第六项条件启用，第七项只增强现有入口。不是增加七个审批点。

- [接入、升级与启动语](START.md)。
- [产品 skill](.agents/skills/product-agent/SKILL.md) / [设计 skill](.agents/skills/experience-design-agent/SKILL.md)。
- [对象规格与组合场景](.agents/skills/product-agent/references/model-completeness.md) / [质量样板与媒体](.agents/skills/experience-design-agent/references/quality-samples-and-media.md)。
- [专业成果核对与审阅入口](collaboration/PROFESSIONAL-REVIEW.md)。
- [共同反馈规则](collaboration/FEEDBACK-PROTOCOL.md) / [协作协议](collaboration/CONTRACT.md) / [实际角色配置模板](collaboration/ROLE-CONFIG-TEMPLATE.md)。
- [工具与素材](.agents/skills/experience-design-agent/references/tool-execution.md) / [外部资料接入](.agents/skills/experience-design-agent/references/external-inputs.md)。
- [人的试验观察指南](DEMO-TEST.md) / [验证范围](VALIDATION.md)。

项目流程管理另留未来独立 skill，本包不加入工作包、任务依赖调度、项目总看板或独立阅读器。既有阶段提示、反馈分流、跨角色澄清和真实审阅继续有效。本包也不启动运行实例、连接工具账号、自动提醒或自动做语义审查。

核对规则检查真实项目成果，结果留在已有评审文件；小项目允许人工或 Agent 核对，不强制机器台账、额外 JSON 或每对象一页。资料、素材和反馈记录仍按实际需要创建。

本包不含实际产品/设计 demo、来源项目记忆或私人路径。没有覆盖用户原测试项目，也没有全局安装。完整多轮行为与跨模型接力仍由独立试验检验，格式与分发验证不代表这些行为已通过。
