# 阶段切换检查

需准入的生产任务由[任务工具](../orchestration/PRODUCTION-ADMISSION.md)调用同一关卡。当前调性契约与内容触发条件见[做法档](PRACTICE-PROFILES.md)。

何时读：产品切换 P 阶段、设计切换 D 阶段、研发承接切换 E-1 子环节、技术方案切换 E-2 子环节、增量构建切换 E-3 或 E-4 子环节，以及有共同要求的内容与质量阶段派发或完成前。

在切换前用 `matrix/base/tools/stage_gate.py` 做一次只读检查，把"未确认不越过审阅节点""批准绑定版本与范围"落成可检查的记录。它检查记录和文件，不代替专业判断，也不认证身份。

## 步骤

1. 计算成果摘要：`python3 matrix/base/tools/stage_gate.py --project . --digest <成果路径…>`，得到 `artifacts` 与 `artifact_sha256`。
2. 在本角色工作区的 `reviews/` 下写检查输入：`role`（阶段流程的标识，即登记里 `stage_flows` 的 `key`）、`current`、`next`（相邻阶段，最后一步写 `complete`）、`scope`（本次范围，字符串数组）、`blockers`（核对后为空数组）、`artifacts`（上一步的结果）、`conversation_check`（对话核对记录的路径，其中要有本次切换的一段，见 [FEEDBACK-PROTOCOL](FEEDBACK-PROTOCOL.md) §6）；审阅节点另加 `request`、`response` 两个记录文件的路径。增量构建从 E-3.1 进入 E-3.2 时另加 `upstream`：技术方案 E-2.4 那次检查的输入文件路径；检查会重新核对它的确认记录仍然有效，未确认或确认后成果已变化时不能开始实现。发布与交接从 E-4.1 进入 E-4.2 时同样加 `upstream`：范围完成评审 E-3.3 那次检查的输入文件路径。
3. 运行 `python3 matrix/base/tools/stage_gate.py --project . --state <输入文件>`。`allowed=false` 时只暂停受影响的范围，修复具体缺口后再检查；通过后由责任方更新工作状态，按 [USER-INTERACTION](USER-INTERACTION.md) 告知新位置。

## 审阅节点的记录

需要审阅记录的切换以各专业登记的 `stage_flows` 为准（[professions/](../professions/)），检查脚本直接读取。沿用登记中的人审节点。

- **request**：`request_id`、`role`、`stage`、`scope`、`artifact_sha256`、`display_evidence`（实际展示给用户的内容或其记录的路径）。
- **response**：`request_id`、`scope`、`artifact_sha256`、`actor`、`choice: "confirm"`、`source`（原话与时间的记录路径）。`actor` 在只有一个人的项目写 `"user"`；有人员名单时（含单人）写 `"person"`，并加 `person_id`。检查会核对此人是否对该流程或其上游流程有决定权（见 [TEAM](../orchestration/TEAM.md) §3）；发布决定只认项目级决定人或 `decides` 含 release 的人。
- 用户通过选项工具或文字回复时，把原话照录进 `source` 指向的记录；用离线审阅页 `matrix/base/tools/review.html` 时，保存它导出的回复文件。不能凭推测写 `confirm`。

## 做法档证据

- 关卡状态写当前 `tone_contract: {path,version,sha256}`。默认取档内全部活动范围。只做部分范围时，`practice_scope` 写活动 ID 列表，须与状态的 `scope` 一致。P-1 合看确认覆盖全部活动。
- 以专业登记的 `framework_requirements` 选择适用条目。派发查 `entry`，阶段完成核对 `entry` 与 `complete`。需要按范围交证据时，`practice_evidence` 按共同条目、活动 ID 指向记录摘要，例如 `{"appearance_target":{"race":{"path":"design/reviews/外观.json","sha256":"实际摘要"}}}`。
- 普通记录 JSON 写 `scope`（单个活动 ID）、当前 `tone_contract`、非空 `artifacts`（成果 `path/sha256` 列表）及[对应条目的字段](tools/practice_profiles.py)。`asset_anchors` 另附 3–5 个不同元素的摘要引用 `anchors`。外观试做和核心场景骨架记录附实际渲染 `screenshot` 的路径及摘要；人工回退按下条记 `capture_unavailable` 和 `manual_review`。
- 贴合记录写 `outcome`、`checker`、`producer`、`mode`、实际 `artifacts`、`viewport`、`capture` 以及 `genre_fit`、`application_drift`、`copy_fit`。实际截图记 `screenshot: {path,sha256}`。异实例写 `independent`、优先换模型；单对话写 `same_instance`，标明同一实例换视角。缺截图能力时由人实际看稿，用 `human`、`capture_unavailable` 和核对记录 `manual_review: {path,sha256}`。如实记录缺口及结果。
- P-1 的 `tone_fit_review` 单独放在关卡状态，写审前绑定，见[方向样张](../orchestration/DIRECTION-SAMPLE.md)。后段贴合以同一个 JSON 格式写入对应范围证据并绑定确认后的 `tone_contract`。成果或所绑契约改变后按影响范围复核。

## 例外与限制

- 用户明确授权免审、合并或裁剪时，相邻阶段的授权内决定可按 [委托检查](DELEGATED-REVIEW.md) 提供 delegated_decision；工具校验实际委托、范围、版本及独立检查，不记为人工确认。合并/裁剪造成跳步仍报告授权例外，不伪造默认关卡通过。
- 检查只能发现缺文件、版本变化、范围不符、未答或部分答复、跳步、缺对话核对和明确的阻断；不证明记录真实、材料充分或专业判断正确。
