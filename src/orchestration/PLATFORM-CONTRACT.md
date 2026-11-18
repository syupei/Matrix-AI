# 平台协议 matrix-platform/1

入口：[platform_api.py](tools/platform_api.py)。字段表：[platform_contract.py](tools/platform_contract.py)；机器信封：[schema](schemas/platform-request.json)。见[guide](PLATFORM-GUIDE.md)。

## 信封与身份

所有请求含 protocol、request_id、project_id、op，params 为对象。写请求另含 event_id；修改任务或运行带当前 expected_revision，运行权带 expected_generation。未知字段拒绝。principal由可信传输提供，映射active/actor/operations/task_ops。tasks.command 禁止正文传 actor/event_id；既有 PM 权限及人工批准检查照常执行。

同request_id同正文返回原结果。相同 event_id 的等价事件可换 request_id 重试；内容变化报 IDEMPOTENCY_CONFLICT。收到原领取结果须核对run_id，不能重启。CLI 本身不是网络认证服务，隔离执行者不能任意运行此入口。

## 操作

| 操作 | params 与行为 |
| --- | --- |
| capabilities | 无；协议、操作、运行器版本、模型映射与能力状态/证据 |
| inspect / validate | 无；运行权、配置能力及事件修订，不认证专业质量 |
| tasks.query | op（默认 status），按查询可带 id/text/name/detail；status/task/team/find/continue/project/resolve_instance |
| tasks.command | PM命令体，省略 actor/event_id；业务修改仍须原命令要求的修订和授权 |
| expert.prepare | id/version/profession/url/commit，可选 subdir；固定来源进入 awaiting_adaptation |
| expert.adapt | id/version/methods/review，可选 unresolved；保存改写与审查，未决冲突进入 blocked |
| expert.validate | id/version/evidence；核对真实作者与独审run、报告、动态专业契约和交回，封存验证闭包，记录操作者 |
| expert.enable | id/version/person/quote；记录授权与操作者，仅启用包 |
| expert.disable | id/version/reason；停用包，阻止关联实例新启动及在途成果自动交回；无关条目不受牵连，进程仍由平台停止 |
| actions.plan | 无；只读动作列表 action_id、revision、owner 及待 PM 判断事项 |
| actions.claim | action_id/expected_revision；原子复核动作与运行权，登记 starting，返回运行与任务包 |
| runs.query | 可选 run_id；读取真实运行记录 |
| runs.event | run_id/expected_revision/kind；started 加 pid/model/receipt；accepted/heartbeat/unknown 加 receipt；handover 加 summary/evidence；blocked 加 reason；commands 加 commands 列表（本运行任务树内的非配置命令，禁止自行指定 actor/event_id）；failed 加 receipt；finished/stopped 加 receipt/exit_code，可选 usage |
| runs.cancel | run_id/expected_revision/reason；只记 cancel_requested，不宣称 stopped |
| runtime.configure | mode=local/external、expected_generation；无在途运行才切换；调用 principal 为唯一控制器 |
| scripts.inspect | 无；脚本精确 argv、权限及副作用配置 |
| scripts.request | id，可选空 args；只请求已登记脚本，拒绝增加任意实参 |

验证报告、独审及可选scenario_view见[专家接入](EXPERT-IMPORT.md)，passed不能替代真实检验。

能力至少查询 launch、cancel、scripts、timers、write_isolation、session_resume、usage、model_selection。supported 必须有证据；未填为 unknown。自动领取要求 launch/write_isolation/model_selection 均 supported。能力声明仍须实跑验证。

## 状态、错误与恢复

运行沿用任务工具的 starting/running/not_started/exited/lost；signal 记录 accepted/heartbeat/unknown 等外层事实。unknown 不释放活动占用。cancel_requested 不等于退出。started.model 匹配领取标识；started/退出回执可另报 reported_model，见[适配](MODEL-FIT.md)；实例或配置变更使在途成果待核，仍可回报停止。结束事件不自动做专业检验或人的批准。

稳定错误码包括 INVALID_REQUEST、INVALID_JSON、UNSUPPORTED_PROTOCOL、PROJECT_MISMATCH、UNAUTHORIZED、INVALID_CONFIG、OWNER_MISMATCH、STALE_REVISION、NOT_READY、UNSUPPORTED、RUNS_ACTIVE、RUN_CLOSED、RUN_STOPPING、AUTHORIZATION_CHANGED、MODEL_MISMATCH、IDEMPOTENCY_CONFLICT、STORAGE_BUSY、STORAGE_ERROR、SOURCE_UNAVAILABLE；原业务规则拒绝统一为 REJECTED 并保留具体 message。仅可重查的修订冲突标retryable。

领取成功、启动失败、失联和确实结束分别回报；事件事务与模型进程不属同一事务，启动不确定时保留 unknown 并核实，不靠租约到期重复启动。单机SQLite控制面跨机器须经一个可信服务串行访问，不把数据库放共享对象存储并发写。
