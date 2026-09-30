# 请求账本

何时读：每次调用 `coordination.py` 前。

[coordination.py](../scripts/coordination.py)（Python 3.9+，仅标准库）不发消息、不唤醒 Agent。在项目根目录执行 `python3 {本 skill 目录}/scripts/coordination.py --project . --input {命令}.json`，或从 stdin 传 JSON；用户内容不拼进 shell。输出 JSON，出错退出码 1。数据库 `collaboration/runtime/state.sqlite3`。除 `init`、`status` 外都传 `actor`。

## 初始化与登记

- `init`：由对人主任务（PM 接管时为 PM）在首次需要跨角色协作时执行；`authorization` 写用户在对话中给出的协作授权原话与时间，没有授权就不初始化。`config` 含 `protocol:"professional-collaboration/0.1"`、真实 `authorization`、`frontdoor.thread_id`（对人主任务 ID），`max_rounds`、`max_attempts` 缺省 3（1–10）。同配置重复执行幂等，不同配置拒绝；没有迁移或清除命令，改配置前先处理在途工作。
- `register`（coordinator）：`role={id,skill,write_roots,endpoint}`。skill 须存在；write_roots 为项目内路径，不能是整个项目；未启动的角色 endpoint 为 null，否则 `{kind,id,session}`。kind：subagent（按 id 与 session 识别）；thread（独立任务，按 id 识别）；inline（主任务顺序处理，不能投递）。有在途租约时不能改路由。

## 一次问答

1. 请求方 `request`：`request={id,source,target,question,expected_output,authorization,sources,write_allowed}`，source 为自己。sources 自动记 SHA256；write_allowed 缺省为空，须在 target 的 write_roots 内。同 ID 同内容幂等，改内容拒绝；形成等待环时拒绝。
2. 协调方 `claim`（仅 ready；目标、同一实例或重叠写范围有租约时拒绝）得 attempt token → `packet` 取完整请求包 → 宿主发送 → `receipt`：attempt、outcome（sent/not_sent/uncertain）、evidence。sent 只表示对方已接受投递。
3. 责任角色 `show` 核对 token 后 `respond`：attempt、`response={kind,summary,evidence}`。kind：explanation；decision（另需 decision_authorization）；needs_human；unavailable（需新证据或恢复条件）。改源另需 `updated_sources={请求内路径:修改后 SHA256}` 与 change_authorization，限角色所有权与 write_allowed；未声明的源变化使请求转 stale，新增文件在专业交付清单中引用。respond 后停止修改业务源。
4. 请求方 `accept`：`result` 写采用位置或只读核验方式 → closed。

## 需要人

needs_human 附 `question={prompt,why,scope,options,recommendation}`（后两项可选），返回 `question_hash`。按该版本展示后 `presented`：question_hash、evidence。真实回复后 `human_answer`：question_hash、answer、`evidence={kind:"user_message",thread_id:对人主任务 ID,quote:用户原话}`；请求回到 ready、round 加 1，重新 claim 唤醒原责任角色（新 token）。模拟数据不进生产账本。

## 状态、失败与取消

- ready → dispatching → inflight → answered → closed；needs_human → ready（新一轮）；源变更 stale；cancelled；not_sent、unavailable 或超过轮次 failed。
- claim、respond、human_answer、accept 都核对源，变化即 stale。核对差异后用新 ID 和新基线建请求，`supersedes` 仅作关联，必要时另行 cancel 被替代请求。
- `retry` 仅限 not_sent，受 max_attempts 限制；uncertain 保留租约。超过 max_rounds 时汇总未决问题，由真实决定建新请求。
- `cancel`（协调方或请求方，需 reason）只取消采用资格：在途租约保留，迟到回答被拒。确认停止或完成后 `settle_cancel`：attempt、outcome（stopped/completed/not_sent）、evidence，才释放写者；已确认 sent 的不能记 not_sent。
- receipt 晚于回答也不重开请求；重复 respond 幂等，过期 token 或矛盾答复被拒。
- 重启先 `status`，逐个核对在途租约与真实实例，不清库、不整体换实例；无停止证据就报告阻断。
