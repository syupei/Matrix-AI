# 项目任务完整性与变更接续

何时读：PM 接收或接管明确交付范围、收到需求变更、分派同岗位多个实例、回答任务进度、暂停恢复及关闭交付之前。专业角色在评估变更或准备任务调整时读取本文件。

## 分层与实例

PM 管项目层任务的范围、派发、依赖和关闭；专业 owner 管本任务的内部子项与执行。共用一个任务源，不复制任务库。岗位是能力，实例是具体责任或执行者，任务是交付；同岗位可以有多个实例。

PM 用 `register_instance` 登记 `{id, instance:{role,endpoint,write_roots}}`；id 是稳定实例标识，endpoint 是实际路由，write_roots 是独立写范围。登记不启动实例、不证明它在线。新任务可将 owner、executor 指向实例 ID；工具按登记映射汇总岗位。共用文件由指定维护方合并，不靠关闭冲突检查增加并行。

普通根工作任务默认是项目层；项目任务放在阶段容器下时，创建时明确 `project_level:true`，仍由 PM 管理。内部子任务不设置此标记，由父任务 owner 创建和关闭。角色、实例、父子层级与任务 ID 不互相代替。

## 从口述到有效计划

1. 保存原话及当前依据，一条输入有多项意图就按稳定需求条目关联；一条需求可派生多个任务，一个共享任务也可服务多个需求。明确要求与讨论候选分别标明；每次变更登记到流水，不覆盖上一条输入。
2. 先登记影响分析任务，再用 `record_change` 保存来源和已知影响；未知写待分析。已知受影响的任务及其后继不能使用尚未同步的计划启动或关闭，独立工作继续。
3. 产品核对业务差异，设计、技术和 QA 按相关性提供影响或无影响依据；技术代价与设计发现可以回流产品。每个 participant 用 `assess_change` 提交自己的评估和任务调整，不让 PM 代写专业结论。
4. 用户明确要求且在授权内的变更沿依据执行；新取舍、超范围和原定人审仍按原节点。评估不等于确认，实现也不等于采用。范围变化不要求全项目重跑流程，只回查最早受影响的部分。
5. PM 用 `apply_change_plan` 汇总新项目任务与 owner 准备的命令。参与方未齐或仍待分析、已知任务没有处置、修订冲突时不生效；一个数据库事务全部成功才记录 planned，失败整体回滚，可用原 event_id 重试。文件、消息和数据库不是跨系统事务；失败时保留待同步，相关工作不放行。
6. 实际交付与验收完成后 `close_change`；计划已同步、制作完成、独立检验、必要人审、下游采用分别说明。外部修改后显式登记新版本；原检验不自动沿用。

接收后当前轮应能定位原话、分析责任和已知保护范围；下一次依赖新依据的派发或关闭前，已确定影响应已纳入计划。参与方/通道不可用时保留待接收，不声称后台正在自动分析。

## 变更流水与任务弃用

`record_change` 自动分配本项目内唯一、递增且不复用的 `change_no`，如 `CHG-000001`；省略 id 时直接以该编号为记录 ID。可选 title 写需求简述，缺省取原话；流水保留编号、登记时间、原话、来源摘要、类型、分析责任、受影响任务、评估、计划处置和状态。既有自定义 ID 可继续作内部引用，每条新记录仍有唯一流水号；旧记录不补造时间或专业结论。并发登记在同库写事务中分配，原 event_id 重试返回原编号。不同项目的编号分别管理。

因需求变更不再需要的任务，处置使用 `cancel`，生效后状态为 `deprecated`（**已弃用**），备注由工具生成为 **“受 （编号） xxx 需求调整变更”**；编号取 change_no，xxx 取需求简述。任务的 deprecation 同时记录 change_id、change_no 和备注，reason 与该备注一致。`apply_change_plan` 自动将此类撤销命令转为已弃用，不由调用者自由改写备注。普通、与需求变更无关的取消仍为 cancelled；已登记的未同步变更不能用普通取消绕过分析。

只有已评估的任务撤销才能生效；仍由本层 manager 关闭，在途执行先记录停止证据，子项先结束。已完成任务也可因撤销变更而弃用，原完成事件、检验和成果保留在历史。弃用项不计当前完成或剩余，单列数量；弃用不能满足依赖，也不能免除交付集合义务。恢复须显式重开并重新核对。

只读 `{"op":"changes"}` 按流水顺序查询；可传 id（记录 ID 或 change_no）或 state 筛选。`--render` 生成 `management/views/changes.md` 变更流水，并在任务详情展示“已弃用”、关联编号与备注。流水及视图来自同一任务库，不另建可编辑副本；完整修订在 events 中保留。

## 交付集合

任务数不能代替全部交付对象。对于已知清单，`register_scope` 从专业源 JSON 读取稳定 ID；未知范围设 `known_complete:false`，不凭空补总量。需求、场景、素材或模块都可作为集合成员。专业正文仍只有原有有效源。

用 `bind_delivery` 将成员需要的 production、qa、human、adoption 出口关联到具体任务及 work_revision；只要求本范围确实适用的出口。qa 要有不同于作者的 checker；human 必须指向有真实人审要求且当前有效的任务；adoption 另附原源的采用记录路径。工具检查记录，不能认证实际品质、身份或采用真实性。

取消任务不会删除集合义务。修改清单须关联已登记变更和范围授权；旧清单、任务与确认留在事件历史。已完成先前版本需要返工时，用新任务引用 `replaces`，历史 done 保留但不能计作当前交付。绑定需改到新版有效任务，不能拿旧批准套新版。

## 工具接口

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

## 验证边界

槽位、路由、写范围与记录权限都是协作约束，不是操作系统锁或身份认证。程序不能识别未落盘的口述、判断所有语义影响、代替人的决定或保证消息送达。用真实多轮任务及实际产物核对新增、修改、撤销、插入恢复、并行实例和旧确认适用性；机制测试只证明程序约束。
