# 模型适配：证据、试岗与复核

何时读：评估模型、确认高职级配置、适配结论失效或实绩触发复核时。实例与人的权限见[实例规则](INSTANCES.md)。

## 登记与有效性

项目 `management/model-fit.json` 的 `models` 每项沿用 `model`、`levels`（专业→最高职级）、`capabilities`、`filled_by`，补充：

| 字段 | 内容 |
| --- | --- |
| basis | trial（试岗）、performance（项目实绩）、human（人的判断）、host（宿主信息）之一 |
| evidence | 非空证据引用列表；写出可回读的任务、检验或判断依据 |
| evaluated_at | 带时区的评估时间；不填未来时间 |
| model_version | 评估时实际使用的模型版本；不凭别名猜版本 |
| review_after | 带时区的复核期限，晚于评估时间 |
| review_conditions | 指标→可容忍次数；超出任一数值触发复核。空对象表示只按时间和版本复核 |

例（均为示意，由人或人指定的评估工具填写）：

```json
{"models":[{"model":"project-model","model_version":"project-model-version-1","levels":{"product":"T7"},"capabilities":["长文阅读与结构化写作","long_horizon","complex_dispatch","deep_reasoning"],"filled_by":"项目决定人","basis":"human","evidence":["management/assessments/product.md"],"evaluated_at":"2026-11-01T00:00:00Z","review_after":"2026-12-01T00:00:00Z","review_conditions":{"review_failed":2,"rework":2,"escalation":1,"ended_without_handover":0}}]}
```

工具核对字段、状态与登记的运行事实；证据引用的专业质量仍由人或授权评估者审定。缺证据字段、到期、评估后各实例最新启动记录的实际版本与登记不同，或实绩超阈值，该模型按“未登记”处理，`team` 的 `review_reasons` 给出原因。旧字段保留，旧结论不冒充有效。启动失败且未真正运行的记录不算版本变化；没有启动记录不证明实际选模成功。

适配文件或适配状态变化会使旧配置确认失效，派生和下一次启动前重新核对。正在运行的任务不被工具自动停止或降级。PM 展示证据与影响，给人换模型、降职级、明确继续使用三个选择；也可先复测。未登记继续用 `acknowledge_unregistered`，明确不适用而坚持用 `insist`，后者成果按 F1 检验。人的确认只承认本次状态，不变成能力认证。确认后适配标记有变化，用 `relevel_instance` 同步档案（保留已确认职级）；不靠旧档案跳过检验要求。

## 试岗与能力标签

配高职级前，从项目选一个风险低、但达到目标职级难度的真实任务；不可把难度降到容易通过。用现有任务与独立检验机制，由另一模型的实例检验。保存任务难度、风险、两方实际模型版本、成果、检验原文及通过/失败；人或其指定工具根据证据填写最高职级与能力，失败不写成适用。试岗仍需原有派发/执行授权，不新增题库，不使用发布评测集充当项目实绩。

- `long_horizon`：跨步骤、跨会话仍保持目标、约束与状态。
- `complex_dispatch`：拆分、派发、整合时保留难度、责任和依赖。
- `deep_reasoning`：在多方约束下给出有依据的权衡。

各专业职级表和登记 `levels.capabilities` 给出累计要求；评估只针对任务实际覆盖的能力，不以一次试岗认证所有专业。模型名称、训练记忆或新模型传闻只能生成“未核实，建议复测”，不能直接改结论。

## 实绩查询

调用任务工具 `{"op":"model_performance"}`，平台经 `tasks.query` 使用同一 op。可带 `since`（带时区时间，取之后的事件）。按配置模型、实际版本、专业、任务难度分别汇总：`review_failed` 检验不通过、`rework` 返工、`escalation` 已登记上报（已发/已收或上级决定）、`ended_without_handover` 结束未交出。每项附事件号、任务、实例、原因与版本来源；没有启动记录时按配置归类并标明，不冒充实跑。

阈值按该模型评估时间之后的指标合计，不跨模型；不同任务难度仍在查询里分列。返工按已有归因登记，检验失败保留原因；上报统计已发/已收的报告事件及工具接受的上级决定，待发草稿不算，未登记的口头上报不猜测。次数不是因果证明，PM 带原始记录请人复核；是否降级、换模型由人决定。
