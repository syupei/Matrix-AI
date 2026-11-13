# 阶段与协作配置

何时读：查询阶段、协作档位或决定人及委托。调用前置与其余操作见[原入口](TASK-TOOL.md)。

## 阶段与协作配置

接续仍用 `{"op":"continue"}`。有阶段里程碑时，输出 `stage_line` 和 `project_stages`；PM 的项目阶段行直接引用 `stage_line`。`runtime_state` 表示暂停或额度恢复条件，不改变 `planned` 等任务状态。专业流程总步数用 `{"op":"stage_flow","profession":"product","flow":"product"}` 从专业登记取得；未知流程不猜数。

协作约定见 [TEAM](TEAM.md)；先用 `{"op":"collaboration"}` 读当前配置与 revision。配置保存在任务库，勿另建不被工具读取的配置文件。人员及各专业唯一真人主责仍由负责人维护 `management/people.json`，每人用 `masters:["product"]` 登记主责，项目负责人为唯一 `decides:["project"]` 的人。

以下是命令结构示例；person、quote 必须替换为实际决定人及原话：

```json
{"op":"collaboration_config","actor":"PM","event_id":"unique-id","expected_revision":0,"person":"leader-id","quote":"实际原话","changes":{"default":"regular","profiles":{"product":"deep","code-engineering":"quick"}}}
```

- 模式：quick 快速出品、regular 常规协作、deep 精细共创。未选择的专业沿默认，`confirmed:false`；先向人实际提出问题与选择，再记 `collaboration_asked`，带 `professions:["product"]`、`question`（实际问题原文）、`presented_ref`（已展示问题的消息或记录）、actor、event_id 和 expected_revision。仅列出“待确认”、计划提问或工具调用不算问过；没问就保持 `ask_once` 待问。`ask_once` 排除已问未答项，不把问过当确认。
- 运行中改档仍用 `collaboration_config`，由项目负责人或该专业真人主责决定；只变更明确指定的专业，事件保留前后选择及原话。
- 若问题在上一轮末尾才展示，本轮先依据真实对话回填已问记录，再读 `ask_once`；用户尚未选档仍保持待确认，不把同一问题重问一次。
- `changes.delegations` 是增改列表，每项含 `id, profession, scope, person, grantor, quote, decisions`，可带 `task_ids` 和 `active:false` 撤权。decisions 显式列 professional、release、budget 或 project。grantor 必须是本次 person；发布、预算及项目级授权只能由项目负责人给出。scope 精确匹配已登记范围，不用相似词扩大授权；交叠范围先解决再路由。
- `{"op":"decision_route","profession":"product","scope":"导出功能","kind":"professional"}` 返回 person 与依据；也可传 task_id，从任务的 `profession,decision_scope,decision_kind` 读取。任务创建/修改要登记这三个字段，实际 human_review 和个人视图使用同一路由；没有范围授权则专业真人主责兜底，再到项目负责人。F0 路由额外返回需立即告知的项目负责人。
- `changes.engineering` 独立保存 `{"tier":"medium","basis":"规模、风险与不确定性的事实","stage":"E-1"}`，由研发真人主责确认；tier 为 small/medium/large。协作模式不会改变此字段。
- `--render` 派生 `management/views/collaboration.md`，显示每专业的模式、主责、审阅粒度、必需材料与待确认项。配置写入是协作记录，不认证人的身份；不自动派生实例、免除审阅或启动任务。
