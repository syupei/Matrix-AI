# 团队任职、参与规则与派发接口

使用现有 [PM 工具](TASK-TOOL.md) 的 actor、event_id 和 expected_revision。人员指定/授权来源是真实记录，接口检查不认证身份。未登记任职的历史项目保持兼容；登记范围内启动和关闭须有当前 owner/executor 任职。

| op | 字段与作用 |
| --- | --- |
| team | 只读任职、专业参与规则与未完成义务，以及实例配置：确认记录、是否当前、各项适用性 |
| confirm_config | PM 或前台记录人的确认：person、quote、presented_ref、choices（不适用的项为 insist，未登记的为 acknowledge_unregistered）；校验 `management/instance-config.json`，按 `model-fit.json` 核对适用性，记下文件哈希；文件再改就不再当前，重新确认带 expected_revision；有名单时 person 须有项目级决定权 |
| derive | PM 提交 entry、endpoint（宿主返回的真实地址）、write_roots；配置当前、该项未满数才登记，编号 `<专业标识>-<序号>` 由工具生成、不复用，write_roots 自动含实例 workspace；生成档案 `management/instances/<编号>/profile.md`，不写地址与凭证 |
| relevel_instance / retire_instance | PM 提交 id、expected_revision、reason；新确认的配置改了该项职级才可调级（重写档案），删去该项、数量少于在用实例或换了模型才可停用；实例不能有进行中的工作 |
| appoint | PM 提交 id=实际实例 ID，appointment 含 mode、role、root_tasks（已有任务 ID）、delegates（已注册可调配实例）、source（真实指定依据路径）；mode 为 lead/executor/workflow_pm/auxiliary；workflow_pm 的 role 为项目管理 |
| revoke_appointment | PM 提交 id、expected_revision、reason；阻止后续执行，实际在途工作仍须停止并交接 |
| register_participation | PM 提交 id、rule，含 role、trigger、root_tasks、mode（consultation/required_review）、source；更新带 expected_revision |
| participation_event | PM 提交 id、rule_id、rule_revision、trigger、trigger_id、affected_tasks、source；按规则修订/事件/输入摘要去重，产生待分派义务；新基线可附 supersedes、supersedes_revision 替代旧义务并保留覆盖范围及历史 |
| bind_participation | PM 提交义务 id、expected_revision、review_task；专业角色匹配且不得与被审工作形成等待环；审查改版后重新绑定 |

任职依据内容变化使任职待重核。调整任职前停在安全接点；撤权可立即登记，但不伪造进程停止。工作区路径由工具给出，宿主核对后实际创建，不以目录存在证明隔离。某范围首次接入团队时，先登记覆盖该范围所需的责任/执行任职，再派发。

项目 PM 负责录入实际任命；专业负责人创建本层子任务；workflow_pm 在任命任务树内可创建 project_level 项目任务。专业正文修改权与工具权限另外核对。人员视图和任务 query 共用原库，按主责/实例/项目层查询，不重复计父子。

## 平台运行

项目设好 `management/runtime/platform.json`（宿主命令的模板，例子见 START.md）后，实例由平台拉起，PM 统一调度。

- **定时器**：[timer.py](tools/timer.py) 由人启动：在终端里常驻，或接到人授权的定时任务上每次跑一轮；不自动安装，检查时不调用模型。
  - 每分钟看任务表的新记录与在运行的进程；有要 PM 处理的事、PM 又不在处理时唤起 PM，每 60 分钟巡检一次。PM 自己写的记录不算变化。
  - PM 单次处理超过 20 分钟视为卡住，停止后新开。忙时续接同一个 PM 会话，续接满 20 次或空闲 1 小时就新开。
  - PM 停下等人时，运行配置里的提醒命令。
- **接续**：`{"op":"continue"}` 只读，列出现在要做的事、每项未完成任务唯一的停止原因、该不该停与无人值守额度。PM 每次被唤起，按 [值班说明](PM-DUTY.md) 反复运行接续，直到没有可做的事。
- **启动命令**：[launch.py](tools/launch.py) 由 PM 调用。`--task <ID>` 启动执行者；`--purpose check --tasks …` 拉起检验者；`--purpose attend --tasks …` 拉起派发者处理停住的任务。
  - 先在任务库登记这次运行（launch_start），核对就绪、任职、额度与暂停，一个实例同时只有一次运行；执行运行同时把任务记为进行中。再在后台启动宿主命令，记下进程号与实际传入的模型。
  - 运行结束由运行包装记退出（launch_exit）：执行者没交出、也没有未完的子任务的，任务记为受阻"结束未交出"；运行期间任务、输入或任职变了的，成果标为"依据已变"。进程不见了，定时器记 launch_lost。
  - PM 决定不再等时，用 `--stop <运行ID> --reason …` 停止并留下记录。
- **派出分两步**：派发者在任务库里登记子任务与执行者，PM 实际拉起。实例只在任务库登记一次；请求账本只用于跨角色问答与议题。
- **人**：前台把人的新需求、答复与"继续"写进收件箱（`inbox`，带原话），表一变 PM 就被唤起；PM 处理后记 `inbox_done`。人要停下整个项目时记 `pause_project`，恢复记 `resume_project`，都带原话。
- **刹车**：
  - 自人上次答复起最多拉起 30 次；同一任务启动失败最多 3 次。
  - 同一任务返工、改派各超过 2 次，下一次由上一级负责人决定；PM 派发的任务由人决定，记原话。
  - 数值由人在 `configure` 的 limits 里定（原话）；同时运行上限是 max_slots。
- **权限**：后台运行的实例只写自己的工作区与登记的写入范围，能运行包里的工具，不联网、不安装软件；要更多权限时报受阻，由人放开。权限写在宿主命令里，不用跳过全部权限的启动方式。

没有设平台运行的项目，PM 与各专业在对话里工作（[RUNTIME](RUNTIME.md) §4）；回复如实说明不会自动继续，人回来说"继续"后从记录恢复。

任务库不认证调用者，身份仍是协作标签。启动命令记下了每次运行的进程、模型与时间，之后的认证可以以此为基础。
