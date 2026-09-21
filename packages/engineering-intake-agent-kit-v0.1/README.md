# 研发第一阶段 Agent 试验包 v0.1

新增 engineering-intake-agent v0.1：承接产品与已有设计成果，完成工程输入核对、必要澄清、逻辑工程建模、走查及进入技术方案阶段的交接。

这是增量包，不包含产品/设计 skill，不修改其版本。与产品 v0.10、设计 v0.3 及 professional-collaboration 0.1 按接口规则设计兼容；真实多轮和跨模型联调仍待试验。其他来源的产品材料也可读取，但须核对等价内容及缺口。

- [接入与可复制启动语](START.md)
- [研发 skill](.agents/skills/engineering-intake-agent/SKILL.md)
- [项目入口示例](AGENTS.md)
- [实际角色接入补充](collaboration/ENGINEERING-INTAKE-ROLE.md)
- [人的试验观察指南](DEMO-TEST.md)
- [验证范围](VALIDATION.md)

默认交付三类共用成果：工程需求与输入基线、逻辑工程模型与映射、澄清评审与阶段交接。另有轻量角色状态入口；小项目可合并正文，不要求照模板创建空文件。

本包不提供 E2 整体技术路线 Agent、E3 编码/部署 Agent、QA 执行器或项目管理调度器。发布后持续监测不在本轮范围；已要求的可运维能力会形成后续设计/实现/验证依据。复制 skill 不会连接账号、启动其他 Agent 或使某模型具备新的工具。

## 共用规则的来源与使用

`collaboration/CONTRACT.md`、`FEEDBACK-PROTOCOL.md`、`REQUEST-RESPONSE-TEMPLATE.md`、`ROLE-CONFIG-TEMPLATE.md` 为产品设计联合包 v0.3 中的原样快照。它们的历史角色表/说明反映原包提供情况；本增量包只新增研发第一阶段，当前接入范围由本 README 与 ENGINEERING-INTAKE-ROLE.md 说明。没有改写共同协议版本或旧角色规则。

独立迁移需携带完整 skill 和上述依赖，或引用目标项目中同版本的有效共用规则。只放一个 SKILL.md 会缺少工作流与模板，不构成完整接入。包中不包含真实产品成果、项目私人记忆或已填写实例配置。
