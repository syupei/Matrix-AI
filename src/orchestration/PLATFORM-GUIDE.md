# 平台接入 guide

Matrix 管专业、任务、批准、就绪与成果采用；平台管模型进程、定时触发、凭证和实际权限。平台按本页接入。详细字段见 [协议](PLATFORM-CONTRACT.md)，专家转换见 [自带专家接入](EXPERT-IMPORT.md)。首批宿主附件与实测边界见[平台文档](https://github.com/syupei/Matrix-AI/tree/main/docs/platforms)。

平台附件同时声明已验证的负责人／执行者与模型组合；接入时按该范围配置，未验证组合另行验证。进程能够启动及交接成功，只证明相应链路，不等于具备复杂负责人的拆分、定级与检验安排能力，也不授予模型固定职级。

## 六步接入

1. **安装并准备项目。** 按 [START](../../START.md) 安装到新项目，初始化任务库；确认人员、专业与实例配置。不要让运行器自动填入人的批准。平台身份映射来自已认证会话，而非请求正文的 actor。
2. **配置可信控制器。** 由平台维护 `management/runtime/platform-access.json`，格式为 `matrix-platform/1`；包含 project_id、principals、runners，可选 scripts。每个 principal 有 active、actor、operations 白名单及 task_ops 白名单。配置不存凭证，执行实例不可修改它。
3. **验证能力。** 查询 capabilities；每个运行器逐项记录 supported/unsupported/unknown 与证据。启动、模型映射、实际写入隔离缺一项就不能自动执行。运行器配置中 models 把实例模型名映射到真实模型，argv 为可信参数模板（支持 `{workspace}`、`{model}`、`{effort}`；effort 来自已确认实例）。可配 cwd、unset_env 与 prepend_paths；任务不能覆盖模板。kernel 使用内核写边界，command-template 依赖已验证的宿主原生边界。先用无模型工作器验证协议与隔离，再验证实际模型。
4. **指定唯一执行方。** 在无在途运行时调用 runtime.configure，mode 为 local 或 external，expected_generation 来自 inspect。当前控制器 principal 取得运行权；原 scheduler 不再启动工作。local 使用本机参考控制器，external 由外层平台消费同一协议。没有配置运行权的原有本地流程保持原入口。
5. **计划、领取、执行、回报。** actions.plan 只读，选择 action_id，携带返回的 revision 调用 actions.claim。领取原子复核就绪并创建独立 run_id；平台随后启动。只重复相同请求不能再起进程。真实进程启动后回报 started；候选通过 handover 回报；实际退出后回报 finished 或 stopped。成功退出不自动验收任务。
6. **核验后启用。** 验证重复领取、取消、失联、迟到、撤权、越界、同专业双实例和下游输入版本。保存宿主版本、系统、模型、权限配置及原始证据；只登记已验证范围。其它平台通过同一契约后再登记，不因能启动命令而自动认证。

## 一次往返

可信平台在项目根目录执行，JSON 可从 stdin 输入，也可用 `--request request.json`。`--principal` 由登录后的平台调用层填写，不能暴露为执行者自行选择的参数。

```sh
python3 matrix/orchestration/tools/platform_api.py --project . --principal controller --request request.json
```

只读请求示例：

```json
{"protocol":"matrix-platform/1","request_id":"plan-1","project_id":"example","op":"actions.plan","params":{}}
```

领取请求将 action_id 和 revision 换成计划中的当前值：

```json
{"protocol":"matrix-platform/1","request_id":"claim-1","event_id":"claim-1","project_id":"example","op":"actions.claim","params":{"action_id":"从计划返回","expected_revision":12}}
```

响应为 `{protocol,request_id,ok,result,revision}`；失败为 `{protocol,request_id,ok:false,error:{code,message,retryable}}`。stdout 只放 JSON，日志不混入响应。领取结果包含任务包、实例身份、实际配置模型、专家绑定与运行记录。

本机参考工作器完成领取与回报，并以进程组处理取消与超时：

```sh
python3 matrix/orchestration/tools/reference_worker.py --project . --principal controller --timeout 180
```

每次调用最多领取一个动作；平台可按授权并发调用，数据库原子决定可领数量。不在这里启动第二个业务调度器。执行者把回报写入其 `workspace/public/<run_id>-handoff.json`：`{"summary":"摘要","evidence":["本实例公有候选的项目相对路径"]}`；受阻写 `{"reason":"缺口及待谁处理"}`。控制器验证路径后以真实实例身份登记，执行者不能直接写任务库。

## 平台必须保护的边界

- 管理工具只在可信控制器内调用。JSON 参数和 actor 字符串不承担身份认证；不能向隔离实例开放控制器的任意执行权限。
- 参考内核隔离器只允许当前实例 workspace 写入；所有子进程受同一策略约束。它不提供读保密或网络隔离。原生宿主隔离适配须另有该版本实测证据；未知系统返回 unsupported。
- 专家包与任务源只读，正式源采用交给负责人或可信管理流程。额外写入权限需实际授权与独立验证，参考工作器不自动放宽。
- 凭证由平台保管；包、任务、候选和公开日志不携带密钥。传输层还应限制请求大小与访问范围。
- scripts.request 只登记配置中精确 argv 的执行请求，外层平台负责权限和生命周期；不把任意 shell 文本当开放接口。

## 常见情况

处理平台返回错误或运行状态不明时，读取[具体说明](PLATFORM-TROUBLESHOOTING.md)。
