# 分层任务工具

何时读：每次调用 `pm_tasks.py` 前（初始化、写任务、生成视图）。

[pm_tasks.py](tools/pm_tasks.py)（Python 3.9+，仅标准库）保存任务与事件、检查角色与版本、生成只读视图；不启动 Agent、不发消息、不做调度或身份认证，证据由调用者如实填写。

## 调用

- 在项目根目录执行 `python3 matrix/orchestration/tools/pm_tasks.py --project . --command {命令}.json`，省略 `--command` 则读 stdin；用户内容不拼进 shell。输出 JSON，出错退出码 1。
- 写命令带唯一 `event_id` 与真实 `actor`，可带 `occurred_at`。重试用完全相同的命令；同 ID 不同内容被拒。修改已有任务带 `status` 中的 `expected_revision`；过期就重读合并，不盲目自增。
- 读：`{"op":"status"}`（`ready` 表示可以开始，`completion_pending` 列出尚未完成的完成前置）；`{"op":"events","after":0,"limit":100}`（含前后变化），按最后 seq 翻页（limit≤1000）；`{"op":"tasks_for","as":"<pm_actor 或实例 ID>","include_closed":false}`：问 PM 列它派发的任务，问实例列它受领的任务，列与状态照 [PM-REPORTING](PM-REPORTING.md) §5，下一步与完成后由任务关系现算。`--render` 在 `management/views/` 生成以下视图，均只读、可随时重建：
  - `index.md`（PM 的任务列表）、`tasks/{任务ID}.md`、`events.md`；
  - 全程计划表 `plan.md`、项目总入口 `project.md`、群摘要 `digest.md`；
  - 每个在用实例的列表 `instances/{实例}.md`、实例台账 `ledger.md`、人审点汇总 `human-points.md`、交付集合 `scopes.md`；
  - 名单中有两人及以上时，另生成个人视图 `people/{id}.md` 与专业组视图 `groups/{组}.md`。

## 初始化与创建

- `init`：`config={project,pm_actor,authorization,frontdoor_thread,max_slots}`（max_slots 1–64），actor 为 pm_actor。用本项目真实主任务与委托，不复制其他项目的库；只能初始化一次。
- `configure`（仅 pm_actor）：`frontdesk_actor` 登记项目前台的身份，此后前台也可以录入 `human_review`；写 null 取消。
- `create`：`task` 字段——`id`、`parent`（顶层 null）；必填 `title`、`goal`、`next_action`、`owner`（工作维护）、`checker`（专业检验）；`inputs`/`outputs`/`criteria` 为非空字符串数组（输入及版本、成果、判据，可引用专业源）；`dependencies` 为开始前须已完成的任务或里程碑 ID；`completion_requires` 为完成前置，即可以先开始、但标为完成前须已完成的任务 ID（何时用见 workflow），不与 dependencies 重复；两者都不得成环（含父子等待）；`executor` 为真实实例，未知 null；`slots` 默认 1，纯协调容器可为 0；`resources` 为独占资源名；`human_required`；`expanded`（本任务子计划已完整展开）；`source`（专业有效源）。
- 规划与协作字段（均可选）：
  - `kind`：`work` 或 `stage`，阶段里程碑写 `stage`；
  - `stage`：所属阶段里程碑的 ID；
  - `direction`：子方向；
  - `people`：关系到人员 id 列表，关系为 decide、clarify、designate、execute、inform；
  - `derived_from`：派生来源任务；
  - `awaiting`：`[{person, action, item, ref?}]`，action 为 decide、clarify、designate、execute。
- 职级、风险与来源（均可选）：`difficulty`（T1–T9）、`risk`（F0–F5）、`risk_reason`；`origin` 为 `{kind:"request", id, from}`，记来自别的专业请求的工作。owner 或 executor 是已登记实例时，职级不低于 difficulty，没有职级的实例不能接有难度的任务；创建、改执行者或难度、开始前都核对。PM 的项目层任务，owner 是有专业的实例时须是该专业的 master。
- 有 `management/people.json` 时，出现的人员 id 必须在名单中。
- 顶层由 pm_actor 创建，子项由父任务 owner 创建；manager 自动确定，即派发者（输出中的 `dispatcher`），之后不能改。

## 更新与流转

- `update`（owner）：`task_id,expected_revision,changes,reason`，不能改 id、parent、owner、kind。非 manager 改 goal、inputs、outputs、criteria、dependencies、completion_requires、human_required、checker、people、derived_from 时，需用 `scope_authorization` 引用实际决定或委托；撤销 human_required 一律需要。除 next_action、executor、source 与规划协作字段（stage、direction、people、derived_from、awaiting、gap）外，其他修改都会递增 work_revision，已有检验与人工决定随之失效；外部成果变了就显式更新 evidence 或 inputs。difficulty、risk、risk_reason 也需 manager 授权；把 F0、F1 调低另带 `person`、`quote`（有名单时须是有权的人）。
- `transition`（owner 或 manager）：`task_id,expected_revision,state,reason`，state 为 planned/running/waiting_review/blocked/done/cancelled/deprecated。需求变更导致的弃用与关联编号，按[任务完整性](PM-INTEGRITY.md)办理。
  - 进 running：真实 executor、依赖已完成（完成前置不要求）、槽位与资源可用、`execution_receipt`；准备派发不算运行。
  - 离开 running：`stop_evidence`（成果已返回可用该返回），防止执行者仍在写时释放槽位。交出（转 waiting_review）带 `evidence`（成果与证据路径，任务已有时可省）；转 blocked 可带 `blocked_by:{task_id}`。
  - done/cancelled 由 manager 记录，子项须已结束。done 另需 evidence、依赖与完成前置都已完成、checker 对当前基线的 passed、适用的 approved。取消写明原因并处理在途执行，不代替必要验收。F0–F2（模型被坚持使用的实例做的按 F1）且制作者是派生实例时，检验须为 independent；项目里没有其他在用、职级不低于难度的实例时，same_instance 也可关闭；有这样的实例但都与制作者同模型、而本需不同模型时不能关闭，请 PM 按配置派生不同模型的实例，或请人改配置。
  - 返工就在原任务上做：检验未通过后再进 running，或 manager 重开已完成的任务（转 planned 或 blocked），带 `rework_reason`（execution/requirement_clarification/basis_changed/other；检验未通过的沿用其 cause，可省）、`note`，不是 execution 的另带 `attributed_to`（实例 ID）。work_revision 加 1，已有检验与人工决定失效。已完成且下游已在用（依赖它或以它为完成前置的任务已开始或完成）的不重开，改用变更计划的后继任务。重开时已关闭的上级先重开；终态任务先重开才能修改或登记检验。
  - transition 与 report 可带 `usage:{cost,currency,tokens,seconds}`，记入台账。

## 检验、人工决定、上报、转交

- `review`（checker）：`outcome` passed/failed、`criteria_checked`（完整判据数组）、`evidence`（数组）；需已有成果 evidence，绑定当前工作、子项、依赖与完成前置的版本：完成前置原样通过时检验仍有效，前置返工后须重新检验。failed 带 `cause`（返工原因类别）。工具按 C24 §6 记 `independence`：检验者是制作者为 same_instance，其余两条不满足为 not_independent，否则 independent。它是记录，不会自动检验。
- `human_review`（pm_actor，或已登记的项目前台）：`outcome` approved/changes_requested/deferred，`presented_ref,source,quote,scope` 对应已展示版本与真实答复。名单中有两人及以上时必须带 `person`，且此人是该任务或其派生上游的决定人，或拥有项目级决定权；同一工作基线上，上游已作出的不同决定不能被下游改写。批量确认按各任务范围分别录入。已有免审委托可由 update 引用后把 human_required 改为 false，不补造人工通过。
- `report`（owner）：`summary,next_action,impact,delivery`（prepared/sent/received），可带 `request_id`；sent/received 需 `receipt`（宿主消息结果或 PM 读源的接收记录）。上报不发消息，不改变合格状态。
- `handoff`（manager）：`new_owner,acceptance_receipt,reason`；任务不在 running 且无子项；保留 ID 与历史，清空 executor，接收者重新核对输入。
- `reassign`（manager）：`task_id,expected_revision,to,reason_kind`（failed_check/executor_unable/other）、`note`；进行中的带 `stop_evidence` 并转回 planned。目标是在用的已登记实例，与原执行者同专业、职级够、不忙；owner 就是执行者时一起转。
- `conflict`：`id,task_ids,parties,issue,basis,resolution,decided_by,level`（tool/master/owner/pm/human）、`overturned`（task_ids 中被推翻的）。只记录，不改任务状态。actor 须符合 level：tool 为当事方或 PM，master 为涉及专业的 master，owner 为受影响任务的 owner，pm 为 PM，human 由 PM 或前台带 `person`、`quote`；decided_by 是作决定的一方。被推翻的任务各记一条事件。
- `notice`（PM 或前台）：`id,kind`（F1_output/Q0/Q1/Q2）、`ref`、`summary`、`people`（F1、Q1 必填）。Q0 置于总入口与群摘要顶部，F1、Q1 进当事人的个人视图与群摘要，Q2 进群摘要；缺陷正文留在质量源。

## 专业缺口

需要的专业在项目里没有设立时（[CORE](../base/CORE.md) §7），登记缺口，由人选择。编号 G-001 起由工具分配；任务以可选字段 `gap` 关联（create、update 可写），缺口关闭前改掉须带有权的 `person` 与 `quote`。`status` 的 `gaps` 列出缺口与关联任务。

- `gap_open`（PM、前台，或所列任务的 owner、manager）：`domain`（领域，或专业的 ID、名称）、`kind`（not_in_kit 本包没有；not_set_up 项目里没有在用实例）、`why`、`qualification`、`risk`，可带 `task_ids`。该领域已有常设选择时不再问人，返回 `existing` 与 `choice`，照此执行：self 挂到原缺口（风险更高时重新问）；expert、human 另建沿用该选择的缺口（`record`），各自交付、关闭。
- `gap_decide`（PM 或前台）：`gap,expected_revision,choice`（expert/self/human）、`person,quote`，expert 另带 `expert`（专家 Agent 或人的名称、地址），`standing` 默认 true。person 须对每个关联任务有决定权，无关联任务时为项目级决定人。可以改选；human 给关联任务加"现在等人处理"的条目。
- `gap_close`（记录者同 gap_open）：只用于 expert、human，`gap,expected_revision,source,evidence`（数组），记下对方成果，去掉等人条目。
- 缺口未选择，或 expert、human 未关闭时，关联任务不能开工、交出或完成；选 self 的可以做，交出与完成时 evidence 须有一条含"非{领域}专家产出，未经具备资质的人审定"。任务列表、人审点汇总、计划表与群摘要显示缺口。

## 数据边界

- `management/runtime/tasks.sqlite3` 是任务事实与事件的唯一有效源，按项目约定备份，不打进发布包。共库不改变子任务自治；专业文档与协作账本各自保留。
- seq 定读取顺序，revision 防写冲突，work_revision 绑定核验；迟到事件不覆盖新修订。
- 槽位与资源只在已登记任务间检查，不是进程锁或文件隔离；进程停止与单写者由编排者核对。
- 日志只记行动、事实与结果，不存模型推理。试跑用临时目录和标明模拟的回执；模拟的人工决定或投递证据不写进真实项目。

## 交付与计划扩展

需要接管交付清单、登记需求变更、按实例/岗位查询或暂停恢复时，读取 [任务完整性](PM-INTEGRITY.md) 的字段说明。所有关系仍在同一任务库的 pm_records 中，沿用事件幂等和修订校验；未显式接管的任务保持兼容，不推断已确认或已完成。新增项目层标记 project_level、岗位 role 与成果摘要 artifact_digests 只在实际需要时登记。

实例配置的确认与派生、任职、工作流 PM 的局部项目任务、专业介入义务及任务投递接续见 [团队接口](TEAM-RUNTIME.md)。有人员名单时人工答复必须标明有权的人，名单人数不赋予权限。现有目录部署仅提供协作约束；强制工具隔离需要受信宿主。
