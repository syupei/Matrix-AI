# 团队任职、参与规则与派发接口

使用现有 [PM 工具](../.agents/skills/project-management-agent/references/task-runtime.md) 的 actor、event_id 和 expected_revision。人员指定/授权来源是真实记录，接口检查不认证身份。未登记任职的历史项目保持兼容；登记范围内启动和关闭须有当前 owner/executor 任职。

| op | 字段与作用 |
| --- | --- |
| team | 只读任职、专业参与规则与未完成义务 |
| appoint | PM 提交 id=实际实例 ID，appointment 含 mode、role、root_tasks（已有任务 ID）、delegates（已注册可调配实例）、source（真实指定依据路径）；mode 为 lead/executor/workflow_pm/auxiliary |
| revoke_appointment | PM 提交 id、expected_revision、reason；阻止后续执行，实际在途工作仍须停止并交接 |
| register_participation | PM 提交 id、rule，含 role、trigger、root_tasks、mode（consultation/required_review）、source；更新带 expected_revision |
| participation_event | PM 提交 id、rule_id、rule_revision、trigger、trigger_id、affected_tasks、source；按规则修订/事件/输入摘要去重，产生待分派义务；新基线可附 supersedes、supersedes_revision 替代旧义务并保留覆盖范围及历史 |
| bind_participation | PM 提交义务 id、expected_revision、review_task；专业角色匹配且不得与被审工作形成等待环；审查改版后重新绑定 |

任职依据内容变化使任职待重核。调整任职前停在安全接点；撤权可立即登记，但不伪造进程停止。工作区路径由工具给出，宿主核对后实际创建，不以目录存在证明隔离。某范围首次接入团队时，先登记覆盖该范围所需的责任/执行任职，再派发。

项目 PM 负责录入实际任命；专业负责人创建本层子任务；workflow_pm 在任命任务树内可创建 project_level 项目任务。专业正文修改权与工具权限另外核对。人员视图和任务 query 共用原库，按主责/实例/项目层查询，不重复计父子。

## 宿主连接

[task_dispatch.py](tools/task_dispatch.py) 提供可信宿主使用的 Dispatcher(project, skills, send, wake)，复用任务库与请求账本，不创建第三份任务队列。skills 为实际安装技能目录。

- 宿主先按已有一次授权创建/定位实例，取得真实 endpoint 和只读就绪回执，并在两本账中登记。任务执行者的 write_roots 应包含自己的实例 workspace；专业共享源由维护方合并。
- dispatch(task_id, request_id, sources, authorization) 构造版本化任务包、领取租约、调用宿主 send。send 返回 outcome=sent/not_sent/uncertain 和 evidence。只有 started=true 且附 start_evidence 才记运行；之后实际开始时调用 mark_started。
- 执行者按原协作 respond 返回并停止写入。collect(request_id) 重新核对实际输入摘要、版本、任职和任务状态，记录实际回交并调用 wake 给负责人；不自动接受专业结果、不关闭任务、不制造人审。
- send 与 wake 是宿主实际能力；wake 必须按 notification.event_id 去重。无可用接续能力返回 unavailable，记录待接续。主对话只能在实际轮次中继续或由宿主真实事件触发，不能自发消息冒充后台运行。
- 任务库、消息库和远端操作不是跨系统事务。投递后任务写入失败时核对请求账本及真实执行者，修复状态，不再次发送。uncertain 保留租约并核查实际结果。重启读两本账，先核对未结请求再恢复。

调度触发来自真实新任务、回交、人答复或依赖变化；库本身不装守护进程。宿主负责验证实际调用者身份、维护受保护运行状态及注入本次任职，不把模型自报 actor 当认证。

已确认 not_sent 的请求可按原账本 retry 后重新派发；已投递或结果不明的请求不重发。旧输入或任职对应的回交通知标为 needs_attention，保留原任务状态供负责人核对实际停写并协调，不能冒充当前成果。
