# 请求账本与恢复

Python 3.9+，仅标准库。入口 `scripts/coordination.py --project /absolute/project --input /absolute/command.json`；也可通过 stdin 传 JSON。脚本不发送消息，不唤醒 Agent。命令行输出 JSON，错误退出 1 并回滚该次事务。角色名是约定的责任声明，不是身份认证。

## 安装后的首次角色绑定

`status` 无需 actor；其余命令均传 actor。`init`/`register` 通常由安装器完成。实际启动角色后，协调方使用 `register` 登记真实 endpoint；初始化时未启动角色为 null。禁止填想象的任务 ID。角色的 skill 必须存在，write_roots 必须是项目内、非整个项目的路径。

```json
{"op":"register","actor":"coordinator","role":{"id":"product","skill":".agents/skills/product-agent/SKILL.md","write_roots":["product"],"endpoint":{"kind":"subagent","id":"真实工具返回的角色句柄","session":"当前主任务ID"}}}
```

endpoint.kind 为 subagent/thread/inline；inline 表示当前主任务顺序处理，不能成为消息投递目标。独立 thread 按真实 ID 识别，同一 thread 改 session 标签也不是新实例。子Agent按真实宿主会话和句柄识别。活动租约期间不能换路由；重启后先核对旧执行者已终止。

## 一次直接专业问答

1. 请求方执行 request。下面 ID 为格式示意；使用当前真实文件路径和用户授权，不照抄业务结论。

```json
{"op":"request","actor":"engineering-intake","request":{"id":"REQ-001","source":"engineering-intake","target":"product","question":"指定规则的适用范围是什么？","expected_output":"给出范围、依据位置和仍未知部分","authorization":"当前项目已授权的只读专业澄清","sources":["product/实际基线.md"],"write_allowed":[]}}
```

sources 自动记录文件 SHA256。write_allowed 缺省为空；写权限还须被 target.write_roots 覆盖并有实际用户委托，字段本身不会授权业务变更。相同 ID+完整相同 payload 幂等；同 ID 改问题拒绝。跨角色未完成依赖构成环时拒绝新请求，由协调方处理现有依赖。

2. 协调方执行 `{"op":"claim","actor":"coordinator","id":"REQ-001"}`，获得 attempt。只有 ready 可领取；目标/实例/重叠所有权有租约时不能领。同一专业源安排一个写者；这只是协作约束，并不锁住外部编辑器。
3. 用 `packet`（同 actor/id）取得完整请求包，通过实际宿主工具发送。发送确实被接受后，用 receipt 记录原 attempt、outcome=sent 和实际工具结果 evidence；明确没有发送为 not_sent，不确定为 uncertain。sent 只表示接受投递。
4. 责任角色读取 show 核对 token，处理请求后执行 respond。完成 respond 后本轮停止修改业务源，回传摘要；不要继续后台编辑。示意：

```json
{"op":"respond","actor":"product","id":"REQ-001","attempt":"领取所得token","response":{"kind":"explanation","summary":"结论与限制","evidence":["实际文件/条目/版本及内容依据"]}}
```

kind=decision 另需 decision_authorization，准确引用已有专业决定委托。无资料/工具可返回 unavailable；此时需要新证据或恢复条件，不能当作未投递自动重试。默认只读。确有改源授权时，updated_sources={"请求内路径":"修改后SHA256"}、change_authorization 必填；必须同时符合角色所有权和本次 write_allowed。新增文件通过专业交付清单引用，现有源的版本变化必须声明。
5. 请求方实际核对并采用后执行 `accept`，actor 必须是原 source，result 写明确采用到哪里、或只读核验怎样完成。只有 answered 且源版本有效才能 closed；answered 本身不是用户审批或实现交付。

## 需要人：返回问题、真实对话、重唤原角色

response.kind=needs_human 时提供 summary/evidence，以及 question={prompt,why,scope,options?,recommendation?}。主任务读取返回的 question_hash，按这个版本向用户展示问题；展示后执行 presented，传 question_hash 和实际展示 evidence。等待用户答复，继续无依赖工作；绝不把超时/默认选项当同意。

收到真实回复后执行：

```json
{"op":"human_answer","actor":"coordinator","id":"REQ-001","question_hash":"已展示的问题摘要","answer":"实际人类答复","evidence":{"kind":"user_message","thread_id":"登记的主任务ID","quote":"用户真实原话"}}
```

此操作把请求变回 ready，增加 round。协调方必须重新 claim、唤醒责任角色、记录 receipt；新轮使用新 token。原责任角色按人决定补齐正式结论/受权源，原请求方接受后才闭环。人工证据字段只是结构校验，不能证明真实身份；Agent 必须读取真实对话，不伪造引用。测试中的模拟数据绝不能写入生产账本。

## 状态、失败与取消

正常：ready → dispatching → inflight → answered → closed。
需要人：inflight → needs_human → 实际展示及真实回复 → ready → 新一轮处理。
源变更：stale。取消：cancelled。通道明确失败/无处理能力/超过轮次：failed。

- claim/respond/human_answer/accept 均核对输入源；未申明或越权的变化不能自动采用。stale 后核对差异，用新 ID、真实新基线并在 payload.supersedes 引用旧 ID；该字段仅关联，不取消旧请求，必要时另行 cancel。
- retry 仅限 delivery.outcome=not_sent，默认为最多 3 次领取；不确定投递保持租约，不能靠超时再派。needs_human 默认最多 3 轮；超过时汇总未解决问题，由真实决定产生新请求，不无限互调。
- cancel 由协调方或请求方发出，须有 reason；它只取消采用资格，**不会停止宿主中的 Agent**。在途 lease_active 继续保留，迟到回答拒绝采用。先用真实宿主中断/等待确认停止或完成，再执行 settle_cancel，附原 attempt、outcome=stopped/completed、实际证据。确认根本未投递时可用 not_sent；已确证 sent 不能倒退成 not_sent。只有完成此步才能释放旧写者并换路由/重新派工。
- 快速回答可能早于 receipt；迟到的同 token receipt 不得重新打开已答复状态。重复相同 respond 不重复执行；旧 token 或矛盾答复被拒绝。
- 重启先 status：逐个核对活动租约和真实宿主实例，不直接清库或更换全部实例。无实际停止证据时报告阻断。SQLite 事件保留本地排查记录，不包含宿主凭证。

## 初始化

安装器要求实际授权字符串及 frontdoor.thread_id，配置 protocol=professional-collaboration/0.1，max_rounds/max_attempts 缺省 3。同一配置重复初始化幂等；不同配置拒绝覆盖。实际迁移先处理在途工作再安排变更，本版本没有强制迁移/清除在途记录命令。
