# 初始化与创建

何时读：初始化任务库、创建任务或规划字段。调用前置与其余操作见[原入口](TASK-TOOL.md)。

## 初始化与创建

- `init`：`config={project,pm_actor,authorization,frontdoor_id,max_slots}`（max_slots 1–64），actor 为 pm_actor。用本项目真实主任务与委托，不复制其他项目的库；只能初始化一次。
- `configure`（仅 pm_actor）：`frontdesk_actor` 登记项目前台的身份，此后前台也可以录入 `human_review`；写 null 取消。`max_slots` 与 `limits`（unattended_launches 30、run_timeout_minutes 60、rework_cap 2、reassign_cap 2、launch_retries 3）是人的决定，带 person 与 quote。
- 平台运行（见 [TEAM-RUNTIME](TEAM-RUNTIME.md)）：`{"op":"continue"}` 只读，给出要 PM 做的事（附 revision 与命令）、停止原因的计数与额度，`"detail": true` 给出全部；`{"op":"task","id":…}` 只读一项任务；`{"op":"find","text":…}` 按词找任务与共享知识条目；执行者用 `hand_over`（run、evidence、summary）交出、`report_blocked`（run、reason）报受阻；`inbox`（PM 或前台，kind=request/answer/continue/note、text，有人的话带 person 与 quote）与 `inbox_done`（PM，带 note）；`pause_project` / `resume_project`（person、quote、reason）。`launch_start` 等运行记录由启动命令与调度器写，不手写。返工、改派超过上限时带 `escalation={decided_by,note}`，PM 派发的任务另带人的 quote。
- `create`：`task` 字段——`id`、`parent`（顶层 null）；必填 `title`、`goal`、`next_action`、`owner`（工作维护）、`checker`（专业检验）；`inputs`/`outputs`/`criteria` 为非空字符串数组（输入及版本、成果、判据，可引用专业源）；`dependencies` 为开始前须已完成的任务或里程碑 ID；`completion_requires` 为完成前置，即可以先开始、但标为完成前须已完成的任务 ID（何时用见 workflow），不与 dependencies 重复；两者都不得成环（含父子等待）；`executor` 为真实实例，未知 null；`slots` 默认 1，纯协调容器可为 0；`resources` 为独占资源名；`human_required`；`expanded`（本任务子计划已完整展开）；`source`（专业有效源）。
- 规划与协作字段（均可选）：
  - `kind`：`work` 或 `stage`，阶段里程碑写 `stage`、slots 设 0，由 PM 登记协调启动与实际回执，不派发独立执行进程；完成前置用 completion_requires 连接阶段内工作，关闭仍需成果与检验；
  - `stage`：所属阶段里程碑的 ID；
  - `direction`：子方向；
  - `people`：关系到人员 id 列表，关系为 decide、clarify、designate、execute、inform；
  - `derived_from`：派生来源任务；
  - `order`：就绪任务多于空位时的先后（小的先）；`timeout_minutes`：本任务运行多久算超时（缺省按 limits）；
  - `awaiting`：`[{person, action, item, ref?}]`，action 为 decide、clarify、designate、execute。
- 职级、风险与来源（均可选）：`difficulty`（T1–T9）、`risk`（F0–F5）、`risk_reason`；`origin` 为 `{kind:"request", id, from}`，记来自别的专业请求的工作。owner 或 executor 是已登记实例时，职级不低于 difficulty，没有职级的实例不能接有难度的任务；创建、改执行者或难度、开始前都核对。PM 的项目层任务，owner 是有专业的实例时须是该专业的 master。
- 有 `management/people.json` 时，出现的人员 id 必须在名单中。
- 顶层由 pm_actor 创建，子项由父任务 owner 创建；manager 自动确定，即派发者（输出中的 `dispatcher`），之后不能改。
