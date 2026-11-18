# 阶段切换检查

何时读：各专业进入、派发或完成已登记阶段前。需准入的生产任务由[任务工具](../orchestration/PRODUCTION-ADMISSION.md)调用同一关卡；当前契约和内容触发条件见[做法档](PRACTICE-PROFILES.md)。

工具检查“未确认不越过审阅节点、批准绑定版本与范围”，不代替专业判断或认证人的身份。阶段、人审点、上游约束与共同条目从真实项目安装的[专业登记](../professions/)读取，不能用工作区或快照里的伪登记替换。

## 步骤

1. 用 `python3 matrix/base/tools/stage_gate.py --project . --digest <成果路径…>` 取得 `artifacts` 与合并的 `artifact_sha256`。
2. 在本专业 `reviews/` 写JSON输入：`role`（登记的stage_flows.key）、`current`、`next`（相邻阶段，末步写complete）、`scope`（非空且不重复的范围数组）、`blockers:[]`、实际 `artifacts`，以及 `conversation_check` 路径。对话核对须含本次阶段箭头，见[反馈 §6](FEEDBACK-PROTOCOL.md)。人审节点另附 `request`、`response` 路径。
3. 运行 `python3 matrix/base/tools/stage_gate.py --project . --state <输入文件>`。拒绝时暂停受影响范围，修复具体缺口；通过后保存完整返回值并更新工作状态，按[流程位置](USER-INTERACTION.md)告知。

有上游确认要求时，传 `upstream`（前段成功返回的 `upstream_state`）和 `upstream_bundle`（前段 `review_bundle`）。例如E-3接E-2.4，E-4接E-3.3；直接派后续子阶段也继承本流程的上游要求。

## 审阅节点的记录

- request：`request_id`、`role`、`stage`、`scope`、`artifact_sha256`、`display_evidence`（实际展示来源）、其实际文件摘要 `display_sha256`。
- response：同一 `request_id/scope/artifact_sha256`，`actor`、`choice:"confirm"`、`source`、完整 `quote`、同一 `display_sha256`、`message_sha256`，可用 `response_id` 定位完整消息。[证据格式](REVIEW-EVIDENCE.md#展示与完整答复)说明答复绑定与计算方式。离线[审阅页](tools/review.html)导出的回复同样需保留真实来源，缺字段明确补核，不能默认通过。
- 只有一个人且无名单时actor写user；有人员名单（含单人）写person并加person_id。按[团队 §3](../orchestration/TEAM.md)查本流程或上游决定权；发布决定只认项目级或release决定人。

## 做法档证据

- 状态写 `tone_contract:{path,version,sha256}`。默认覆盖全部活动；部分范围用 `practice_scope` 列活动ID，与 `scope` 集合相同。P-1一次合看覆盖全部档内范围，`tone_fit_review` 单列审前记录，见[方向样张](../orchestration/DIRECTION-SAMPLE.md)。
- `framework_requirements` 的entry用于派发；完成查entry与complete。`practice_evidence` 按共同条目/活动ID引用记录，例如 `{"appearance_target":{"race":{"path":"design/reviews/外观.json","sha256":"实际摘要"}}}`。普通JSON记录含单个 `scope`、当前 `tone_contract`、非空实际 `artifacts` 和[条目字段](tools/practice_profiles.py)；asset_anchors另附3–5个不同元素的refs `anchors`。
- 贴合JSON含 `outcome/checker/producer/mode/artifacts/viewport/capture/genre_fit/application_drift/copy_fit`。团队independent须真实实例及已分派检验、真实交回；same_instance仅实际单对话无团队配置时使用。人工回退用human。如实保留身份、缺口与结果；截图和人工回执按[证据格式](REVIEW-EVIDENCE.md)。
- 当前完成核验活成果、实际实现覆盖与绑定；成功才封存最小依赖闭包，返回各证据ref的 `bundle`、`review_bundle`、`upstream_state`。将返回的 `practice_evidence` refs原样带入后段。entry核封存记录和当前契约，正常删除弃用试做、在骨架上演进不使前段事实过期；当前成果改变仍须本阶段复核。快照不可覆盖或改写，契约变更重审受影响范围。

## 实现走查与例外

D-6有实现时交 `implementation_walkthrough` 与fit；纯设计先行可用 `implementation_handoff` 引用实际JSON `{delivery_kind:"design_only",basis,artifacts}`，artifacts等于当前阶段全部成果；有实现用implemented或不填，不得伪称无实现。走查字段、E-3.2消费D-6结果见[共同格式](REVIEW-EVIDENCE.md#实现走查)。实际操作记录见[证据格式](REVIEW-EVIDENCE.md#实际操作与时序)。

## 例外与限制

用户明确免审、合并或裁剪时，可在授权范围按[委托检查](DELEGATED-REVIEW.md)提供delegated_decision，核实际委托、范围、版本及独立检查，不记为人确认。跳步仍报告例外，不补造默认通过。缺文件、过期、范围不符、未答/部分答、缺核对及明确阻断均会被拒；文件齐备不等于专业质量通过。
