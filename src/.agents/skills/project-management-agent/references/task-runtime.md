# 分层任务工具

何时读：每次调用 `pm_tasks.py` 前（初始化、写任务、生成视图）。

[pm_tasks.py](../scripts/pm_tasks.py)（Python 3.9+，仅标准库）保存任务与事件、检查角色与版本、生成只读视图；不启动 Agent、不发消息、不做调度或身份认证，证据由调用者如实填写。

## 调用

- 在项目根目录执行 `python3 {本 skill 目录}/scripts/pm_tasks.py --project . --command {命令}.json`，省略 `--command` 则读 stdin；用户内容不拼进 shell。输出 JSON，出错退出码 1。
- 写命令带唯一 `event_id` 与真实 `actor`，可带 `occurred_at`。重试用完全相同的命令；同 ID 不同内容被拒。修改已有任务带 `status` 中的 `expected_revision`；过期就重读合并，不盲目自增。
- 读：`{"op":"status"}`（`ready` 表示可以开始，`completion_pending` 列出尚未完成的完成前置）；`{"op":"events","after":0,"limit":100}`（含前后变化），按最后 seq 翻页（limit≤1000）。`--render` 在 `management/views/` 生成以下视图，均只读、可随时重建：
  - `index.md`、`tasks/{任务ID}.md`、`events.md`；
  - 全程计划表 `plan.md`、项目总入口 `project.md`、群摘要 `digest.md`；
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
- 有 `collaboration/people.json` 时，出现的人员 id 必须在名单中。
- 顶层由 pm_actor 创建，子项由父任务 owner 创建；manager 自动确定。

## 更新与流转

- `update`（owner）：`task_id,expected_revision,changes,reason`，不能改 id、parent、owner、kind。非 manager 改 goal、inputs、outputs、criteria、dependencies、completion_requires、human_required、checker、people、derived_from 时，需用 `scope_authorization` 引用实际决定或委托；撤销 human_required 一律需要。除 next_action、executor、source 与规划协作字段（stage、direction、people、derived_from、awaiting）外，其他修改都会递增 work_revision，已有检验与人工决定随之失效；外部成果变了就显式更新 evidence 或 inputs。
- `transition`（owner 或 manager）：`task_id,expected_revision,state,reason`，state 为 planned/running/waiting_review/blocked/done/cancelled/deprecated。需求变更导致的弃用与关联编号，按[任务完整性](../../../../collaboration/PM-INTEGRITY.md)办理。
  - 进 running：真实 executor、依赖已完成（完成前置不要求）、槽位与资源可用、`execution_receipt`；准备派发不算运行。
  - 离开 running：`stop_evidence`（成果已返回可用该返回），防止执行者仍在写时释放槽位。
  - done/cancelled 由 manager 记录，子项须已结束。done 另需 evidence、依赖与完成前置都已完成、checker 对当前基线的 passed、适用的 approved。取消写明原因并处理在途执行，不代替必要验收。
  - 重开：manager 转 planned 或 blocked，已关闭的上级先重开；已有检验失效，已完成的下游保留历史但提示前置已变，由责任方回查。终态任务先重开才能修改或登记检验。

## 检验、人工决定、上报、转交

- `review`（checker）：`outcome` passed/failed、`criteria_checked`（完整判据数组）、`evidence`（数组）；需已有成果 evidence，绑定当前工作、子项、依赖与完成前置的版本：完成前置原样通过时检验仍有效，前置返工后须重新检验。它是记录，不会自动检验。
- `human_review`（pm_actor，或已登记的项目前台）：`outcome` approved/changes_requested/deferred，`presented_ref,source,quote,scope` 对应已展示版本与真实答复。名单中有两人及以上时必须带 `person`，且此人是该任务或其派生上游的决定人，或拥有项目级决定权；同一工作基线上，上游已作出的不同决定不能被下游改写。批量确认按各任务范围分别录入。已有免审委托可由 update 引用后把 human_required 改为 false，不补造人工通过。
- `report`（owner）：`summary,next_action,impact,delivery`（prepared/sent/received），可带 `request_id`；sent/received 需 `receipt`（宿主消息结果或 PM 读源的接收记录）。上报不发消息，不改变合格状态。
- `handoff`（manager）：`new_owner,acceptance_receipt,reason`；任务不在 running 且无子项；保留 ID 与历史，清空 executor，接收者重新核对输入。

## 数据边界

- `management/runtime/tasks.sqlite3` 是任务事实与事件的唯一有效源，按项目约定备份，不打进发布包。共库不改变子任务自治；专业文档与协作账本各自保留。
- seq 定读取顺序，revision 防写冲突，work_revision 绑定核验；迟到事件不覆盖新修订。
- 槽位与资源只在已登记任务间检查，不是进程锁或文件隔离；进程停止与单写者由编排者核对。
- 日志只记行动、事实与结果，不存模型推理。试跑用临时目录和标明模拟的回执；模拟的人工决定或投递证据不写进真实项目。

## 交付与计划扩展

需要接管交付清单、登记需求变更、按实例/岗位查询或暂停恢复时，读取 [任务完整性](../../../../collaboration/PM-INTEGRITY.md) 的字段说明。所有关系仍在同一任务库的 pm_records 中，沿用事件幂等和修订校验；未显式接管的任务保持兼容，不推断已确认或已完成。新增项目层标记 project_level、岗位 role 与成果摘要 artifact_digests 只在实际需要时登记。
