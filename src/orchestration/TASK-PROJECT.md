# 项目类型、资源、结果与收尾

何时读：登记项目目标、资源或检查收尾。调用前置与其余操作见[原入口](TASK-TOOL.md)。

## 项目类型、资源、结果与收尾

`{"op":"project"}` 查询项目事实及revision，`{"op":"closure_check"}` 查询收尾缺口。PM用 `project_config` 保存，带 actor、唯一event_id、expected_revision、source（实际来源）和changes；只提交改变的顶层字段，goals/resources/closure 各字段整体替换，先读后改以保留其他记录。

```json
{"op":"project_config","actor":"PM","event_id":"project-facts-1","expected_revision":0,"source":"用户原话及需求记录","changes":{"project_type":"product_development","goals":[{"id":"adoption","target":"约定的业务目标","owner":"证据提供者","state":"pending","evidence":[]}],"resources":{"device-1":{"kind":"device","exclusive":true,"status":"available","evidence":["已核实的设备记录"]}}}}
```

- 项目类型使用 product_development 或实际其他类型；其他类型返回路线缺口，不表示本包已具备对应专业能力。
- 任务 `resources` 引用资源ID。目录 kind 为 person/device/supplier/budget/procurement，status 为 available/pending/unavailable，exclusive 为布尔值；可记owner和note。可用必须有事实依据；未知容量、成本和采购交期留pending。目录一经启用，缺登记的资源也阻断就绪。相同独占资源按任务order、登记时间、ID排先后，非就绪任务不占预约，运行中的占用优先；共享资源必须明确exclusive:false，不编容量。
- 业务目标必填id/target/owner/state/evidence；state为pending/met/not_met，后两者还需measurement（观测结果）及非空evidence。目标证据是独立记录，任务done和通过检验不替代它。
- 收尾是 `kind:"stage",closure:true` 的任务。changes.closure 含 accepted（当前已验收顶层工作ID），handoffs（已验收项的交接），pending（所有未结顶层工作）；handoffs/pending 每项含 task_id、receiver、next_action、非空evidence。已知未结事项先建原任务库任务，不另建无法核对的流水。收尾门槛允许目标显式待证据且责任已明确，不把它改记达标。
- closure.lessons 可选，每项 observation、conditions、evidence，只有实际观察才写。`closure_check` 仅检验记录齐备与当前任务证据，专业质量、接收人的真实答复仍需核实；关闭还须原有任务检验与适用人审，关闭后改变项目事实先显式重开收尾里程碑。
