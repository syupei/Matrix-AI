# 分层任务工具 0.1

Python 3.9+，仅标准库。脚本：[pm_tasks.py](../scripts/pm_tasks.py)。本工具保存任务/事件、检查协作性角色和版本、生成可阅读索引；实际 Agent 启动、消息与等待仍使用宿主及原公共协作 skill。它不提供后台调度或身份认证，调用者必须如实填写证据。

## 调用

在项目根目录执行 `python3 .agents/skills/project-management-agent/scripts/pm_tasks.py --project . --command 本次命令.json`；也可从 stdin 输入 JSON。不要在 shell 字符串中拼入用户内容。

每个变更包含唯一 `event_id` 和真实 `actor`，重试使用完全相同命令；同 ID 不同内容拒绝。修改现有任务必须提供从 status 取得的 `expected_revision`，过期则重新读取并合并，不能盲目自增绕过冲突。事务同时保存状态、历史和幂等结果。

读取：`{"op":"status"}`。事件：`{"op":"events","after":0,"limit":100}`，用结果最后 seq 分页。生成视图：`python3 .agents/skills/project-management-agent/scripts/pm_tasks.py --project . --render`。入口 `management/views/index.md`，单项 `management/views/tasks/任务ID.md`，事件索引 `management/views/events.md`；这些都是只读派生文件。完整事件含 before/after、命令及引用，使用 events 查询。

## 初始化与创建

首次 init：`op,event_id,actor,config`。config 包含 `project,pm_actor,authorization,frontdoor_thread,max_slots`。使用当前项目真实主任务和实际用户委托，不能复制试验项目的实例/状态库；重复初始化只能重放原 event_id 的同一命令，已有配置不覆盖。

create 包含 `task` 对象：

| 字段 | 语义 |
| --- | --- |
| id / parent | 稳定项目内 ID / 父任务 ID；顶层 parent=null |
| title / goal | 任务名称 / 范围目标 |
| owner / checker | 工作维护责任 / 专业检验责任；不是身份认证 |
| inputs / outputs / criteria | 非空字符串数组：实际输入及版本、关键成果、验收条件；可引用专业源 |
| dependencies | 任务或成果里程碑 ID 数组，必须先登记，禁止包含依赖环和父子等待环 |
| executor | 真实执行实例标识；未知为 null，派发后更新 |
| slots / resources | 实际执行占用的并发槽位 / 独占资源名数组；纯协调容器可为 0，无限套容器不能绕过叶项配额 |
| human_required | 本任务原规则/实际委托是否要求人工确认 |
| expanded | 当前子计划是否已完整展开；不代表全项目已展开 |
| next_action / source | 明确下一动作 / 专业有效源入口 |

顶层只能 pm_actor 创建；子项由父任务 owner 创建。manager 根据层级自动登记，不能自填。create 后 planned、revision=1，无执行/确认记录。

用成果里程碑表达部分交付：它也是一个有条件和证据的任务节点。跨树依赖指向其稳定 ID，版本条件写 inputs；使用前专业接收方仍要核对实际源版本，不因 done 字样跳过核对。

## 更新与执行

update：`task_id,expected_revision,changes,reason`，由 owner 发起。changes 可写 next_action、evidence、executor、expanded、source、reason、title、goal、inputs、outputs、criteria、dependencies、resources、slots、human_required、checker。父 ID、owner、manager 不可随意改。

改目标/输入/交付/判据/依赖/人审/检验者时，若 owner 不是 manager，必须附 `scope_authorization` 引用实际管理决定或既有委托；字符串存在只是协作检查，不能充当真实授权。重要工作变化递增 work_revision 并使旧核验失效。不要只改引用标签而不读取实际源；外部成果改变后显式 update 证据/输入版本以失效旧核验。

transition：`task_id,expected_revision,state,reason`。state 为 planned/running/waiting_review/blocked/done/cancelled。

- 转 running 需要实际 executor、前置 done、资源就绪和 `execution_receipt`。只有工具实际开始后才能登记；准备派发不记成运行。
- running 转任何非运行状态都需要 `stop_evidence`，避免原执行者还在写时释放槽位。实际成果已返回后转 waiting_review，使用真实返回事实作为停止/让出证据。
- done/cancelled 由 manager 记录；子项需全部结束。取消必须说明原因并处理在途执行，不能以取消替代必要验收。
- done 还要求：成果 evidence、依赖完成、指定 checker 当前基线的 passed 结论、适用的人审通过。子任务全结束不自动让父项通过。
- 终态返工先由 manager 以原因重开为 planned/blocked，若父层已关闭先从上层往下重开。旧检验失效。关联已完成后继保留历史，但前置/核验适用性会提示变化，责任方必须回查。

资源检查只覆盖已登记任务。实际宿主进程/子 Agent 停止、文件写入互斥等仍由编排者核对；不要拿数据库记录代替真实隔离。

## 检验、人工决定、上报

review：由 task.checker 调用，字段 `task_id,expected_revision,outcome`（passed/failed）、`criteria_checked`（完整原判据数组）、`evidence`（核验结果入口数组）。记录绑定当前工作、子项及依赖版本；它不是自动执行专业检验。终态任务须先明确重开，才能登记新的专业或人工核验，避免状态保持完成而核验已失败。

human_review：只有 pm_actor 记录，字段 `task_id,expected_revision,outcome`（approved/changes_requested/deferred）、`presented_ref,source,quote,scope`。须对应已展示版本和真实答复；多个任务的批量确认分别录入各自范围，不能用一个“同意”覆盖未展示任务。原有明确免审委托可使相应 human_required=false，但不伪造一条人工通过。

report：由 owner 调用，字段 `task_id,expected_revision,summary,next_action,impact,delivery`（prepared/sent/received），可关联 request_id。sent/received 必须给 `receipt`，对应真实宿主消息结果或 PM 读取源的接收记录；prepared 仅表示已准备。上报不自动发送，不自动改变成果合格状态。

handoff：manager 调用，字段 `task_id,expected_revision,new_owner,acceptance_receipt,reason`。旧任务必须非 running，当前仅支持没有子项的任务转交；有子项时先明确各层责任再接入，工具不会静默重写整棵树。保留任务编号/历史，清空旧 executor，接收者需重新核对输入。

## 恢复与数据边界

SQLite `management/runtime/tasks.sqlite3` 是新登记任务事实与事件的唯一有效源。各专业角色拥有自己的任务行，物理共库不改变子任务自治；专业阶段文档、内容事实及已有协作数据库仍各自保留。不要将 runtime 数据库打进通用发布包。

events 的全局 seq 为读取顺序，任务 revision 为写入冲突校验，work_revision 为核验绑定；发生时间和接收时间另存，迟到事件不会覆盖新修订。CLI 拒绝过期写入后先核对，不创建“新事件”强盖。

业务文件不会因管理事务自动加锁。用户直接编辑专业源后，owner 重新校对成果版本、记录变化和影响。日志记行动、事实与结果，不存模型内部推理。源库备份与恢复按项目约定操作，生成视图可随时重建。

首次试跑用临时目录及明确模拟回执，禁止将模拟 human_review 或投递证据写进真实项目。真实接入只登记真实状态；未核验的历史完成项宁可先留范围外，也不补签。
