# 任务完整性的工具接口

何时读：调用查询、审计、实例与集合登记、变更流水、计划生效、暂停与恢复等操作前。规则本身见 [任务完整性](PM-INTEGRITY.md)（C07）。

沿用 [任务工具](../.agents/skills/project-management-agent/references/task-runtime.md) 的调用、event_id、actor 与修订约束。读接口无需 event_id：

```json
{"op":"query","level":"project","role":"engineering-build"}
```

`query` 的 level 为 project（默认）、children（另传 parent）、all；可按 role 或 instance 筛选。项目回答默认只看项目层，专业问询按直接子项展开。取消、弃用及历史完成待复核分别单列，父子不混算。只统计已登记范围；时间戳是读取时间，最近执行看任务 updated_at/上报与专业源。

```json
{"op":"audit","task_ids":["DELIVERY"]}
```

省略 task_ids 检查全部已登记任务；日常传受影响任务，集合变更或全量关闭时检查其出口。结果给 code、具体任务/对象、修复动作及恢复候选。审计只读，不构建或派发；status 的 integrity 返回实例、集合、变更和暂停记录，可用于断点恢复。现有数据未接管前，不推断其缺失要求或补签历史。

写接口字段如下，id 是对应记录 ID；修改记录带 expected_revision：

| op | 主要字段 |
| --- | --- |
| register_instance | instance 的 role、endpoint、write_roots；可选 batch_limit 限制该实例每批准备的命令数；PM 登记，可同岗位多实例 |
| register_scope | root_task、source 的 path/keys/id_key、known_complete、required_exits；source 选择 JSON 数组，元素为 ID 字符串或含 id_key 的对象；修改范围带 change_id 和 scope_authorization |
| bind_delivery | member_id、exit、task_id、work_revision；采用另带 adoption_source |
| record_change | type（add/modify/remove/mixed）、source（原话记录文件）、quote、analysis_task、participants、affected_tasks、scope_ids；id 可省略自动分配；title 为需求简述；替代未关闭输入另传 supersedes 和 supersession_authorization，继承未处置范围 |
| assess_change | assessment 的 decision（impacted/no_impact/pending）、reason、dispositions、commands；actor 必须是指定参与方，只准备自己的命令 |
| apply_change_plan | PM 提交 pm_commands（仅 PM 权限的 create/update/transition）；工具再应用各参与方准备的 commands，不代签检验或人审 |
| close_change | PM 核对本次交付及范围完成；defer 仍未交付时不提前关闭 |
| pause_task | task_id、task_revision、checkpoint、remaining、resume_after、resume_when、reason；离开 running 另带真实 stop_evidence |
| resume_task | task_revision、reason；工作版本已变另带 rebase_evidence；仅转 planned，不启动实例 |

dispositions 每项有 action 和 task_id，action 为 new/update/rework/keep/cancel/replace/defer。rework/replace 的 task_id 为新后继，replaces 为旧任务；旧任务也要明确保留历史或取消处置。defer 带具体 trigger。commands 使用原任务命令结构、真实 actor、expected_revision 和必要授权，不带新的人工批准。集合里仍有有效义务时，取消并不能使父项通过。

任务可用 `artifact_digests` 登记实际成果路径到 SHA256 的映射；用已有 [摘要工具](tools/stage_gate.py) 取得摘要后转为该映射。文件内容改变会使检验待复核；共享大文件变化后由专业责任方判断影响范围，不自动宣称所有条目失败。未登记摘要的路径仍需人工核对，不把兼容读取称为已验证。
