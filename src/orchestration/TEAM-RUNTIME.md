# 团队任职、参与规则与派发接口

使用现有 [PM 工具](TASK-TOOL.md) 的 actor、event_id 和 expected_revision。人员指定/授权来源是真实记录，接口检查不认证身份。未登记任职的历史项目保持兼容；登记范围内启动和关闭须有当前 owner/executor 任职。

| op | 字段与作用 |
| --- | --- |
| team | 只读任职、专业参与规则与未完成义务，以及实例配置：确认记录、是否当前、各项适用性 |
| model_performance | 只读查询模型在各任务职级的检验失败、返工、上报及结束未交出；可带 since；字段与复核见[模型适配](MODEL-FIT.md) |
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

自带专家、别名、版本与预置专业按 [专家接入](EXPERT-IMPORT.md)；跨平台控制器按 [平台 guide](PLATFORM-GUIDE.md)。别名用 resolve_instance 解析，改名用 rename_instance（id、alias、expected_revision），任务仍用稳定 ID。

## 平台运行

接入调度器、启动实例或处理运行回报时，读取[具体说明](TEAM-PLATFORM.md)。
