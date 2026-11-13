# 平台协议 matrix-platform/1

入口：[platform_api.py](tools/platform_api.py)。操作字段唯一表：[platform_contract.py](tools/platform_contract.py)；机器信封：[schema](schemas/platform-request.json)。用户接入顺序见 [guide](PLATFORM-GUIDE.md)。CLI 为首个传输层，其它传输复用 handle，不另建任务状态机。

## 信封与身份

所有请求含 protocol、request_id、project_id、op，params 为对象。写请求另含 event_id；修改任务或运行带当前 expected_revision，运行权带 expected_generation。未知信封/操作字段拒绝。principal 由可信传输参数提供，映射 active、actor、operations、task_ops。tasks.command 禁止正文传 actor/event_id；既有 PM 权限及人工批准检查照常执行。

同 request_id 同正文返回原结果，不再执行。相同 event_id 的等价事件可换 request_id 重试；内容变化报 IDEMPOTENCY_CONFLICT。调用方收到原领取结果时应核对 run_id，不能重新启动。CLI 本身不是网络认证服务，隔离执行者不能任意运行此入口。

## 操作

| 操作 | params 与行为 |
| --- | --- |
| capabilities | 无；协议、操作、运行器版本、模型映射与能力状态/证据 |
| inspect / validate | 无；当前运行权、配置能力及任务事件修订；不声称已进行专业质量检验 |
| tasks.query | op（默认 status），按查询可带 id/text/name/detail；status/task/team/find/continue/project/resolve_instance |
| tasks.command | 原 PM 工具命令体，省略 actor/event_id；业务修改仍须原命令要求的修订和授权 |
| expert.prepare | id/version/profession/url/commit，可选 subdir；固定来源进入 awaiting_adaptation |
| expert.adapt | id/version/methods/review，可选 unresolved；保存改写与审查，未决冲突进入 blocked |
| expert.validate | id/version/evidence；真实运行报告与方法摘要匹配后 validated |
| expert.enable | id/version；已验证包变为 enabled，不自动派生或启动实例 |
| expert.disable | id/version/reason；停用包，阻止新启动及在途成果自动交回，实际进程仍由平台停止 |
| actions.plan | 无；只读动作列表 action_id、revision、owner 及待 PM 判断事项 |
| actions.claim | action_id/expected_revision；原子复核动作与运行权，登记 starting，返回运行与任务包 |
| runs.query | 可选 run_id；读取真实运行记录 |
| runs.event | run_id/expected_revision/kind；started 加 pid/model/receipt；accepted/heartbeat/unknown 加 receipt；handover 加 summary/evidence；blocked 加 reason；commands 加 commands 列表（本运行任务树内的非配置命令，禁止自行指定 actor/event_id）；failed 加 receipt；finished/stopped 加 receipt/exit_code，可选 usage |
| runs.cancel | run_id/expected_revision/reason；只记 cancel_requested，不宣称 stopped |
| runtime.configure | mode=local/external、expected_generation；无在途运行才切换；调用 principal 为唯一控制器 |
| scripts.inspect | 无；脚本精确 argv、权限及副作用配置 |
| scripts.request | id，可选空 args；只请求已登记脚本，拒绝增加任意实参 |

能力至少查询 launch、cancel、scripts、timers、write_isolation、session_resume、usage、model_selection。supported 必须有证据；未填为 unknown。自动领取要求 launch/write_isolation/model_selection 均 supported。能力表是可信平台的声明，实际准入仍需运行验证。

## 状态、错误与恢复

运行沿用任务工具的 starting/running/not_started/exited/lost；signal 记录 accepted/heartbeat/unknown 等外层事实。unknown 不释放活动占用。cancel_requested 不等于退出。回报模型必须匹配领取模型；实例修订或平台配置变化使在途成果待核实，仍允许回报停止事实。结束事件不自动做专业检验或人的批准。

稳定错误码包括 INVALID_REQUEST、INVALID_JSON、UNSUPPORTED_PROTOCOL、PROJECT_MISMATCH、UNAUTHORIZED、INVALID_CONFIG、OWNER_MISMATCH、STALE_REVISION、NOT_READY、UNSUPPORTED、RUNS_ACTIVE、RUN_CLOSED、RUN_STOPPING、AUTHORIZATION_CHANGED、MODEL_MISMATCH、IDEMPOTENCY_CONFLICT、STORAGE_BUSY、STORAGE_ERROR、SOURCE_UNAVAILABLE；原业务规则拒绝统一为 REJECTED 并保留具体 message。仅明确可重新查询后重试的修订冲突标 retryable。

平台定时触发 plan 后再 claim。领取成功、启动失败、失联和确实结束分别回报；事件事务持久化与模型进程不是同一事务，启动不确定时保留 unknown 并核实，不靠租约到期重复启动。项目为单机 SQLite 控制面；跨机器必须由一个可信服务串行访问它，不能把数据库直接放在共享对象存储中并发写。
