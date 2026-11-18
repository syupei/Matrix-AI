# 审阅与采集证据格式

何时读：准备方向确认、截图/人工看稿、实现走查或实际操作记录。阶段操作见[阶段检查](STAGE-GATES.md)，字段定义以[共同工具](tools/practice_profiles.py)与[证据工具](tools/review_evidence.py)为准。

## 展示与完整答复

确认绑定使用 `matrix-review-binding/1`：`request_id`、`scope`、`display:{path,sha256}`、`response:{path,sha256,response_id,message_sha256}`、`person`、`quote`、`outcome:"approved"`；方向另加 `direction_sha256`，scope为做法档实际活动ID数组；输入准入scope为该次展示描述。`quote` 必须是完整消息，不能从否定或有条件答复截出确认。`response_id` 可定位来源JSON的 `messages:[{id,text}]` 中一条完整消息；省略时取整个来源文件。`message_sha256` 用证据工具的 `digest` 计算。记录实答，不能补造人的决定。

PM命令的human_attention/human_review使用相同范围描述字符串；方向展示时工具另冻结全部活动ID为receipt.scope。PM通过 `human_attention` 冻结展示及答复，再由 `human_review` 或 `intake_admit` 消费同一次请求；操作见[外部输入准入](../orchestration/PRODUCTION-ADMISSION.md)。单对话保存上述binding JSON后运行 `python3 matrix/base/tools/review_evidence.py --project . --review-binding <项目相对JSON>`，成功返回 `review_receipt:{path,sha256}`。binding另写 `actor:"user"`；人工看稿另附实际展示成果的 `artifacts` refs。回执指向 `matrix-evidence-bundle/1` manifest；context保留绑定，files保留逐字节副本。已有答复不能改绑新方向；内容或范围变更回到受影响的原确认。

## 实际截图与人工回退

方向顶层写 `viewport`，如 `1280x800`。方向、外观试做、骨架和贴合记录的PNG须可解码，像素等于数值视口乘 `scale`。截图用 `screenshot:{path,sha256}`；方向中放 `parts.screenshot`。各自的 `capture_binding` 格式相同：

```json
{"artifacts":[{"path":"实际预览或成果","sha256":"摘要"}],
 "pixel_size":[1280,800],"viewport":"1280x800","scale":1,
 "method":"实际采集方式","state":"所见代表状态","source":"采集来源",
 "receipt":{"path":"采集记录.json","sha256":"摘要"}}
```

`artifacts` 在方向中绑定当前 `parts.preview`，其他记录绑定其全部实际 `artifacts`。采集时保存receipt文件：内容为同一binding去掉 `receipt` 后加 `screenshot_sha256`。保留真实采集与资源版本；独立两次采集可以同图像字节，不能拿旧采集记录冒充本次。程序核对尺寸、摘要和关联，不认证画质或实际操作者。

缺采图能力时保留实际预览、视口展示记录与失败/限制，写 `capture_unavailable`、`manual_review:{path,sha256}`（方向用 `parts.manual_review`）。PM可先登记待人看稿的展示；这不产生成功草稿回执，也不假定人已看过。同一次P-1实际答复后，`confirmation.review_receipt`可兼作方向及方向贴合的人工看稿回执，不另增人审；失败或有条件答复保留待决。其他人工看稿用 `human_review_receipt`，绑定实际展示、完整人的答复及本次成果 `artifacts`；团队核名单，单对话用真实用户答复。人工模式带截图仍须核真实答复与看稿人，不能由代理自写一句话冒人看过。

## 实际操作与时序

`playable_prototype` 的文字字段按共用定义填写；计划保留待做，完成记录写 `status:"completed"`、实际 `environment`，并引用 `run_evidence`、`timing_evidence` 两份JSON：

```json
{"status":"observed","environment":"实际环境",
 "events":[{"action":"实际操作","result":"观察结果","at_ms":100}]}
```

```json
{"status":"observed","environment":"实际环境",
 "measurements":[{"event":"测量事件","result":"实际结果","started_ms":0,"observed_ms":100}]}
```

时点相对同次记录起点，须非负且观察不早于开始。数值示例不是通用延迟门槛；结果须对应可复现操作、运行版本和环境，不能用“待定”冒已执行。E-3.3和Q-2命中相关特征时交本阶段实际记录，不能拿E-2计划替代。

## 实现走查

共同记录implementation_walkthrough写scope、tone_contract、实际artifacts，及locations、activity_effect、preserved_states（应保留HUD/状态）、preservation_basis、design_recheck_states（复查状态/操作）、recheck_method（实际证据方式）、corrections（纠正及去向）。确无适用保留项写理由，当前记录覆盖全部阶段实现。

D-6成功后，E-3.2的走查记录加design_review:{bundle:该D-6的review_bundle,state_path:该D-6的upstream_state}，引用真实设计走查快照并覆盖本次实现；D-6自身不填此字段。适用的fit仍另留记录。纯设计先行的适用性见[阶段检查](STAGE-GATES.md#实现走查与例外)。

独立准入中两生产者证据的来源与控制派生按[组合证据](../orchestration/EXPERT-SCENARIO-VIEW.md)，不改写作者原件或独审结论。
