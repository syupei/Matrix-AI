# 专业缺口

何时读：登记、决定或关闭专业缺口。调用前置与其余操作见[原入口](TASK-TOOL.md)。

## 专业缺口

需要的专业在项目里没有设立时（[CORE](../base/CORE.md) §7），登记缺口，由人选择。编号 G-001 起由工具分配；任务以可选字段 `gap` 关联（create、update 可写），缺口关闭前改掉须带有权的 `person` 与 `quote`。`status` 的 `gaps` 列出缺口与关联任务。

- `gap_open`（PM、前台，或所列任务的 owner、manager）：`domain`（领域，或专业的 ID、名称）、`kind`（not_in_kit 本包没有；not_set_up 项目里没有在用实例）、`why`、`qualification`、`risk`，可带 `task_ids`。该领域已有常设选择时不再问人，返回 `existing` 与 `choice`，照此执行：self 挂到原缺口（风险更高时重新问）；expert、human 另建沿用该选择的缺口（`record`），各自交付、关闭。
- `gap_decide`（PM 或前台）：`gap,expected_revision,choice`（expert/self/human）、`person,quote`，expert 另带 `expert`（专家 Agent 或人的名称、地址），`standing` 默认 true。person 须对每个关联任务有决定权，无关联任务时为项目级决定人。可以改选；human 给关联任务加"现在等人处理"的条目。
- `gap_close`（记录者同 gap_open）：只用于 expert、human，`gap,expected_revision,source,evidence`（数组），记下对方成果，去掉等人条目。
- 缺口未选择，或 expert、human 未关闭时，关联任务不能开工、交出或完成；选 self 的可以做，交出与完成时 evidence 须有一条含"非{领域}专家产出，未经具备资质的人审定"。任务列表、人审点汇总、计划表与群摘要显示缺口。
