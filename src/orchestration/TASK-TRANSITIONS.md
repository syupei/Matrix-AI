# 更新与流转

何时读：更新、开始、交出、关闭或重开任务。调用前置与其余操作见[原入口](TASK-TOOL.md)。

## 更新与流转

- `update`（owner；manager 也可改 checker 及协调字段）：`task_id,expected_revision,changes,reason`，不能改 id、parent、owner、kind。非 manager 改 goal、inputs、outputs、criteria、dependencies、completion_requires、human_required、checker、people、derived_from 时，需用 `scope_authorization` 引用实际决定或委托；撤销 human_required 一律需要。除 next_action、executor、source 与规划协作字段（stage、direction、people、derived_from、awaiting、gap）外，其他修改都会递增 work_revision，已有检验与人工决定随之失效；外部成果变了就显式更新 evidence 或 inputs。difficulty、risk、risk_reason 也需 manager 授权；把 F0、F1 调低另带 `person`、`quote`（有名单时须是有权的人）。
- `transition`（owner 或 manager）：`task_id,expected_revision,state,reason`，state 为 planned/running/waiting_review/blocked/done/cancelled/deprecated。需求变更导致的弃用与关联编号，按[任务完整性](PM-INTEGRITY.md)办理。
  - 进 running：真实 executor、依赖已完成（完成前置不要求）、槽位与资源可用、`execution_receipt`；准备派发不算运行。
  - 离开 running：`stop_evidence`（成果已返回可用该返回），防止执行者仍在写时释放槽位。交出（转 waiting_review）带 `evidence`（成果与证据路径，任务已有时可省）；转 blocked 可带 `blocked_by:{task_id}`。
  - done/cancelled 由 manager 记录，子项须已结束。done 另需 evidence、依赖与完成前置都已完成、checker 对当前基线的 passed、适用的 approved。取消写明原因并处理在途执行，不代替必要验收。F0–F2（模型被坚持使用的实例做的按 F1）且制作者是派生实例时，检验须为 independent；项目里没有其他在用、职级不低于难度的实例时，same_instance 也可关闭；有这样的实例但都与制作者同模型、而本需不同模型时不能关闭，请 PM 按配置派生不同模型的实例，或请人改配置。
  - 返工就在原任务上做：检验未通过后再进 running，或 manager 重开已完成的任务（转 planned 或 blocked），带 `rework_reason`（execution/requirement_clarification/basis_changed/other；检验未通过的沿用其 cause，可省）、`note`，不是 execution 的另带 `attributed_to`（实例 ID）。work_revision 加 1，已有检验与人工决定失效。已完成且下游已在用（依赖它或以它为完成前置的任务已开始或完成）的不重开，改用变更计划的后继任务。重开时已关闭的上级先重开；终态任务先重开才能修改或登记检验。
  - transition 与 report 可带 `usage:{cost,currency,tokens,seconds}`，记入台账。
