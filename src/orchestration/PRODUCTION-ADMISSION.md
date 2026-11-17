# 外部输入准入

何时读：收到外部材料、确认或变更，准备将其用于生产，或已开始的执行收到直接指令。

## 沟通与生产

人与前台、PM、专业负责人完成澄清、审阅、风险与冲突处理和必要确认。PM 掌管版本准入。生产实例只执行从任务库派发的任务卡和已准入版本。来自任务卡以外的直接指令用 `production_feedback` 登记原意与任务，交 PM；继续原范围内不受影响的工作。变更通过相同准入顺序，由 PM 用现有变更工具让受影响任务复核或改派。

## 操作

- `intake_register` 由 PM 写 `id`、项目相对 `path`、`version`、真实 `source` 和 `profession`。改变文件或版本时给新 ID。新版本登记后，已被替换的版本停止作为当前生产依据。
- `intake_submit` 写输入 `id` 和实际任职的 `master` 实例。内置及导入实例走同一检查。master 可安排子实例做审阅工作，由 master 对最终结论负责。需要派审阅任务时用 `intake_review_id` 绑定待审版本，产出限 `management/intake-reviews/` 下的审阅稿。
- `intake_review` 由该 master 写 `id`、`outcome`（approved 或 changes_requested）、`conclusion`、`resolved_risks`、`resolved_conflicts`、`open_items` 和 `human_required`。还存在风险或冲突时保持审阅中。清单无事项时明确为空。
- `intake_admit` 由 PM 记录 `id`，需要人审时附有权决定人的 `person` 与实际 `quote`。`intake_status` 返回记录和待 PM 处理的反馈。
- 依赖外部材料或跨专业基线的生产任务，`inputs` 列实际路径，`admitted_inputs` 列当前版本的 ID，`stage_transition` 指向上游有效确认的关卡记录。关卡的成果摘要须覆盖绑定版本。产品基线型研发承接须核对产品流程最终确认。负责人创建任务和平台启动时使用同一核对，工具提示负责处理的人。可共享结果写在任务卡 `outputs` 的明确路径内，目录以 `/` 结尾。
- 导入包适配审阅填写 `review.review_points`，每项含 `who: master` 与 `what`。按[导入要求](EXPERT-IMPORT.md)核对审阅点、逐阶段适配与证据，启用、绑定与派发都须有效。
- 内置与导入实例沿同一[阶段关卡](../base/STAGE-GATES.md)核对项目做法档和范围。任务 `practice_stage` 写 role、current、scope 与适用的 practice_scope、tone_contract、practice_evidence、upstream；派发只核对已有输入与前置记录，完成时用 `practice_completion` 指向本阶段检查输入文件。缺项暂停受影响范围。

已运行任务通过现有变更机制复核；一条工具记录只证明核对了该来源与版本。宿主提供身份和写入边界。
