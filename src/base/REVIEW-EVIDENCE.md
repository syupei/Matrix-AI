# 审阅与采集证据格式

何时读：准备方向确认、截图/人工看稿、实现走查或实际操作记录。阶段操作见[阶段检查](STAGE-GATES.md)，字段定义以[共同工具](tools/practice_profiles.py)与[证据工具](tools/review_evidence.py)为准。

## 展示与完整答复

确认绑定使用 `matrix-review-binding/1`：`request_id`、`scope`、`display:{path,sha256}`、`response:{path,sha256,response_id,message_sha256}`、`person`、`quote`、`outcome:"approved"`；方向另加 `direction_sha256`，scope为做法档实际活动ID数组；输入准入scope为该次展示描述。`quote` 必须是完整消息，不能从否定或有条件答复截出确认。`response_id` 可定位来源JSON的 `messages:[{id,text}]` 中一条完整消息；省略时取整个来源文件。`message_sha256` 用证据工具的 `digest` 计算。记录实答，不能补造人的决定。

PM命令的human_attention/human_review使用相同范围描述字符串；方向展示时工具另冻结全部活动ID为receipt.scope。PM通过 `human_attention` 冻结展示及答复，再由 `human_review` 或 `intake_admit` 消费同一次请求；操作见[外部输入准入](../orchestration/PRODUCTION-ADMISSION.md)。单对话保存上述binding JSON后运行 `python3 matrix/base/tools/review_evidence.py --project . --review-binding <项目相对JSON>`，成功返回 `review_receipt:{path,sha256}`。binding另写 `actor:"user"`；人工看稿另附实际展示成果的 `artifacts` refs。回执指向 `matrix-evidence-bundle/1` manifest；context保留绑定，files保留逐字节副本。完整答复identity持久绑定展示、范围和方向；不能换文件名重用。不同真实消息可记录稳定response_id，不能把相同原话自当新授权。内容或范围变更回到受影响确认。

## 实际截图与人工回退

方向顶层写 `viewport`，如 `1280x800`。方向、外观试做、骨架和贴合记录的PNG须可解码，像素等于数值视口乘scale，scale不得小于1，不能用缩略图冒目标视口。截图用 `screenshot:{path,sha256}`；方向中放 `parts.screenshot`。各自的 `capture_binding` 格式相同：

```json
{"artifacts":[{"path":"实际预览或成果","sha256":"摘要"}],
 "pixel_size":[1280,800],"viewport":"1280x800","scale":1,
 "method":"实际采集方式","state":"所见代表状态","source":"采集来源",
 "receipt":{"path":"采集记录.json","sha256":"摘要"}}
```

`artifacts` 在方向中绑定当前 `parts.preview`，其他记录绑定其全部实际 `artifacts`。采集时保存receipt文件：内容为同一binding去掉 `receipt` 后加 `screenshot_sha256`。保留真实采集与资源版本；仅同来源且同状态的独立采集可同字节；若图SHA与方向/前段相同而绑定成果或状态不同，拒绝并需采本次实际成果。不能拿旧记录冒本次。程序核对尺寸、摘要和关联，不认证画质或实际操作者。

缺采图能力时保留实际预览、视口展示记录与失败/限制，写 `capture_unavailable`、`manual_review:{path,sha256}`（方向用 `parts.manual_review`）。PM可先登记待人看稿的展示；这不产生成功草稿回执，也不假定人已看过。同一次P-1实际答复后，`confirmation.review_receipt`可兼作方向及方向贴合的人工看稿回执，不另增人审；失败或有条件答复保留待决。其他人工看稿用 `human_review_receipt`，绑定实际展示、完整人的答复及本次成果 `artifacts`；团队核名单，单对话用真实用户答复。人工模式带截图仍须核真实答复与看稿人，不能由代理自写一句话冒人看过。

## 阶段实际记录与历史接力

操作/时序、试玩与D-6结构记录按[阶段证据格式](STAGE-EVIDENCE.md)。当前完成核验活成果；成功封存所有实际读取的材料，在快照中自检通过才登记stage-receipts并发回执。后段使用已登记的真实阶段证据，不接受仅自制bundle。实例退役不抹掉已验事实，新复核仍须在任。范围不变的契约接续条件同该页。

独立准入中两生产者证据的来源与控制派生按[组合证据](../orchestration/EXPERT-SCENARIO-VIEW.md)，不改写作者原件或独审结论。
