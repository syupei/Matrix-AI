# 阶段切换检查

何时读：产品切换 S 阶段、设计切换 D 阶段、研发承接切换 E1 子环节或标记完成之前。

在切换前用 `collaboration/tools/stage_gate.py` 做一次只读检查，把"未确认不越过审阅节点""批准绑定版本与范围"落成可检查的记录。它检查记录和文件，不代替专业判断，也不认证身份。

## 步骤

1. 计算本次成果的摘要：`python3 collaboration/tools/stage_gate.py --project . --digest <成果路径…>`，得到 `artifacts` 与 `artifact_sha256`。
2. 在本角色工作区的 `reviews/` 下写检查输入（如 `product/reviews/S3-gate.json`）：`role`（product/design/engineering）、`current`、`next`（相邻阶段，最后一步写 `complete`）、`scope`（本次范围，字符串数组）、`blockers`（核对后为空数组）、`artifacts`（上一步的结果）；审阅节点另加 `request`、`response` 两个记录文件的路径。
3. 运行 `python3 collaboration/tools/stage_gate.py --project . --state <输入文件>`。`allowed=false` 时只暂停受影响的范围，修复具体缺口后再检查；通过后由责任方更新工作状态，并按 [USER-INTERACTION](USER-INTERACTION.md) 显示新位置。

## 审阅节点的记录

需要审阅记录的切换：产品每个阶段（S1–S7）；设计 D1（设计基础）、D2（审阅 A）、D4（审阅 B）、D6（审阅 C）；研发承接 E1.4。

- **request**：`request_id`、`role`、`stage`、`scope`、`artifact_sha256`、`display_evidence`（实际展示给用户的内容或其记录的路径）。
- **response**：`request_id`、`scope`、`artifact_sha256`、`actor: "user"`、`choice: "confirm"`、`source`（用户原话与时间的记录路径）。
- 用户通过选项工具或文字回复时，把原话照录进 `source` 指向的记录；用离线审阅页 `collaboration/tools/review.html` 时，保存它导出的回复文件。不能凭推测写 `confirm`。

## 例外与限制

- 用户明确授权免审、合并或裁剪时，默认序列之外的切换会被判为阻断：保留授权原文与范围，人工核对后报告"授权例外，未经默认关卡"，不伪造确认记录。
- 检查只能发现缺文件、版本变化、范围不符、未答或部分答复、跳步和明确的阻断；不证明记录真实、材料充分或专业判断正确。
