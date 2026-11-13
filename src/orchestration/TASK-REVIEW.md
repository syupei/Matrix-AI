# 检验、人工决定、上报、转交

何时读：检验、录入人工决定、上报、转交或改派。调用前置与其余操作见[原入口](TASK-TOOL.md)。

## 检验、人工决定、上报、转交

- 平台返工用 `plan_restart`（本层 manager）：`task_id,expected_revision,note`，非执行原因另带 `attributed_to`；沿用检验者记录的 cause。工具登记本次工作版本及执行者对应的重启参数，调度器照此执行；缺参数时交派发者补齐，不反复尝试无效启动。实际启动时才累计返工次数，已有额度与升级条件仍有效。

- `review`（checker）：`outcome` passed/failed、`criteria_checked`（完整判据数组）、`evidence`（数组）；需已有成果 evidence，绑定当前工作、子项、依赖与完成前置的版本：完成前置原样通过时检验仍有效，前置返工后须重新检验。failed 带 `cause`（返工原因类别）。工具按 C24 §6 记 `independence`：检验者是制作者为 same_instance，其余两条不满足为 not_independent，否则 independent。它是记录，不会自动检验。
- `human_review`（pm_actor，或已登记的项目前台）：`outcome` approved/changes_requested/deferred，`presented_ref,source,quote,scope` 对应已展示版本与真实答复。名单中有两人及以上时必须带 `person`，且此人是该任务或其派生上游的决定人，或拥有项目级决定权；同一工作基线上，上游已作出的不同决定不能被下游改写。批量确认按各任务范围分别录入。已有免审委托可由 update 引用后把 human_required 改为 false，不补造人工通过。
- `report`（owner）：`summary,next_action,impact,delivery`（prepared/sent/received），可带 `request_id`；sent/received 需 `receipt`（宿主消息结果或 PM 读源的接收记录）。上报不发消息，不改变合格状态。
- `handoff`（manager）：`new_owner,acceptance_receipt,reason`；任务不在 running 且无子项；保留 ID 与历史，清空 executor，接收者重新核对输入。
- `reassign`（manager）：`task_id,expected_revision,to,reason_kind`（failed_check/executor_unable/other）、`note`；进行中的带 `stop_evidence` 并转回 planned。目标是在用的已登记实例，与原执行者同专业、职级够、不忙；owner 就是执行者时一起转。
- `conflict`：`id,task_ids,parties,issue,basis,resolution,decided_by,level`（tool/master/owner/pm/human）、`overturned`（task_ids 中被推翻的）。只记录，不改任务状态。actor 须符合 level：tool 为当事方或 PM，master 为涉及专业的 master，owner 为受影响任务的 owner，pm 为 PM，human 由 PM 或前台带 `person`、`quote`；decided_by 是作决定的一方。被推翻的任务各记一条事件。
- `notice`（PM 或前台）：`id,kind`（F1_output/Q0/Q1/Q2）、`ref`、`summary`、`people`（F1、Q1 必填）。Q0 置于总入口与群摘要顶部，F1、Q1 进当事人的个人视图与群摘要，Q2 进群摘要；缺陷正文留在质量源。
