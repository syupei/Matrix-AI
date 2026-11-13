# 分层任务工具

何时读：首次调用 `pm_tasks.py` 或入口/调用条件改变时；随后只读本次操作对应章节，输入版本变化时重读受影响部分。

[pm_tasks.py](tools/pm_tasks.py)（Python 3.9+，仅标准库）保存任务与事件、检查角色与版本、生成只读视图；不启动 Agent、不发消息、不做调度或身份认证，证据由调用者如实填写。

## 调用

先定位本文件同级的 [`tools/pm_tasks.py`](tools/pm_tasks.py)，用该脚本的实际路径调用。下列示例以技能包安装在项目根目录为例；包位于其他目录时，只替换脚本路径，`--project` 仍指向当前业务项目。已有 shell 和 Python 时，这个本地脚本就是工具入口，无需额外的宿主专用按钮；入口疑似缺失时先检查链接目标并实际运行只读 `status`，以返回结果判断缺脚本、缺任务库或其他错误。

- 在项目根目录执行 `python3 matrix/orchestration/tools/pm_tasks.py --project . --command {命令}.json`，省略 `--command` 则读 stdin；命令文件也可以是一个命令列表，按顺序执行，各自返回结果；用户内容不拼进 shell。输出 JSON，出错退出码 1。
- 写命令带唯一 `event_id` 与真实 `actor`，可带 `occurred_at`。重试用完全相同的命令；同 ID 不同内容被拒。修改已有任务带 `status` 中的 `expected_revision`；过期就重读合并，不盲目自增。
- 读：`{"op":"status"}`（`ready` 表示可以开始，`completion_pending` 列出尚未完成的完成前置）；`{"op":"events","after":0,"limit":100}`（含前后变化），按最后 seq 翻页（limit≤1000）；`{"op":"tasks_for","as":"<pm_actor 或实例 ID>","include_closed":false}`：问 PM 列它派发的任务，问实例列它受领的任务，列与状态照 [PM-REPORTING](PM-REPORTING.md) §5，下一步与完成后由任务关系现算。`--render` 在 `management/views/` 生成以下视图，均只读、可随时重建：
  - `index.md`（PM 的任务列表）、`tasks/{任务ID}.md`、`events.md`；
  - 全程计划表 `plan.md`、项目总入口 `project.md`、群摘要 `digest.md`；
  - 每个在用实例的列表 `instances/{实例}.md`、实例台账 `ledger.md`、人审点汇总 `human-points.md`、交付集合 `scopes.md`；
  - 名单中有两人及以上时，另生成个人视图 `people/{id}.md` 与专业组视图 `groups/{组}.md`。

## 初始化与创建

初始化任务库、创建任务或规划字段时，读取[具体说明](TASK-CREATE.md)。

## 更新与流转

更新、开始、交出、关闭或重开任务时，读取[具体说明](TASK-TRANSITIONS.md)。

## 检验、人工决定、上报、转交

检验、录入人工决定、上报、转交或改派时，读取[具体说明](TASK-REVIEW.md)。

## 专业缺口

登记、决定或关闭专业缺口时，读取[具体说明](TASK-GAPS.md)。

## 数据边界

- `management/runtime/tasks.sqlite3` 是任务事实与事件的唯一有效源，按项目约定备份，不打进发布包。共库不改变子任务自治；专业文档与协作账本各自保留。
- seq 定读取顺序，revision 防写冲突，work_revision 绑定核验；迟到事件不覆盖新修订。
- 槽位与资源只在已登记任务间检查，不是进程锁或文件隔离；进程停止与单写者由编排者核对。
- 日志只记行动、事实与结果，不存模型推理。试跑用临时目录和标明模拟的回执；模拟的人工决定或投递证据不写进真实项目。

## 交付与计划扩展

需要接管交付清单、登记需求变更、按实例/岗位查询或暂停恢复时，读取 [任务完整性](PM-INTEGRITY.md) 的字段说明。所有关系仍在同一任务库的 pm_records 中，沿用事件幂等和修订校验；未显式接管的任务保持兼容，不推断已确认或已完成。新增项目层标记 project_level、岗位 role 与成果摘要 artifact_digests 只在实际需要时登记。

实例配置的确认与派生、任职、工作流 PM 的局部项目任务、专业介入义务及任务投递接续见 [团队接口](TEAM-RUNTIME.md)。有人员名单时人工答复必须标明有权的人，名单人数不赋予权限。现有目录部署仅提供协作约束；强制工具隔离需要受信宿主。
## 项目类型、资源、结果与收尾

登记项目目标、资源或检查收尾时，读取[具体说明](TASK-PROJECT.md)。

## 阶段与协作配置

查询阶段、协作档位或决定人及委托时，读取[具体说明](TASK-GOVERNANCE.md)。
