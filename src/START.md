# professional-agents-kit 0.30

一组中文专业 Agent skill，按专业组织：一个共同底座，加上产品、内容设计与审读、交互与视觉设计、代码工程、质量工程，以及项目管理、项目前台两个调度专业。项目启动时由人决定用哪些专业，以及各专业几个实例、什么职级、用什么基座模型；每个专业保留自己的阶段、人审节点和成果，人始终掌握关键决定。小任务也可以不分实例，在一个对话里按各专业的要求完成。

## 包含什么

| skill | 作用 |
| --- | --- |
| project-front-desk-agent | 项目前台（调度）：主对话入口，启动检测并按需拉起角色，按专业登记推荐专业组合，按文件回答问询，登记并转交要求，展示待决事项 |
| project-management-agent | 项目管理（调度）：按人确认的配置派生实例，顶层任务、依赖、子任务上报、集中人审，任务列表、进度视图与实例台账 |
| product-agent | 产品：澄清、目标与范围、对象与规则、功能流程、体验要求、评审与交付（P-1–7） |
| content-design-review | 内容设计与审读：用户看到的文字（界面文案、提示与错误提示、通知、引导）与带键的文案表 |
| experience-design-agent | 交互与视觉设计：设计基础、粗结构、细交互、代表视觉、完整设计、验证与交付（D-1–7） |
| engineering-intake-agent | 代码工程的承接：输入核对与澄清、逻辑工程模型、档位与技术风险、评审与交接（E-1） |
| engineering-solution-agent | 代码工程的方案：按问题作技术决定、风险试做、可运行骨架与工程基础、委托优先的技术评审，关键技术选型由人确认（E-2） |
| engineering-build-agent | 代码工程的构建与发布（技术负责人）：按用户可见能力切增量、检验与集成、范围完成评审（E-3）；小型、中型项目的发布准备、发布决定包、逐批发布与交接（E-4） |
| quality-verification-agent | 质量工程：验收条目与覆盖、非实现者检验、质量测量、发布验收、缺陷定级与回归（贯穿 E-1–4） |
| professional-agent-collaboration | 协作：真实请求、唤醒、应答、人工答复与恢复；跨专业的多轮议题 |
| profession-builder | 专业创建：按专业规范新建或修改专业，带登记检查与总入口生成脚本 |
| product-capability-model | 共享知识库：优秀产品七原则、七大能力、48 项二级能力的原文 |

`collaboration/` 是所有专业共用的底座，安装到项目根目录：

- `MATRIX.md` 是总入口：专业目录、项目启动时怎样选专业、在一个对话里完成任务的用法。
- `CORE.md` 是每个角色启动时读的共同底线；`GUIDANCE-INDEX.md` 是共用规则索引，列出其余规则何时读。
- `LEVELS.md` 规定职级 T1–T9（T10 归人）；`RISK-DEFECT-LEVELS.md` 规定风险 F0–F5 与缺陷 Q0–Q5 的定级与处理。
- `INSTANCES.md` 规定实例的配置、派生、档案与台账；`TOPICS.md` 规定跨专业的多轮交流。
- `professions/` 是各专业的登记、职级表与风险、缺陷对照；`PROFESSION-SPEC.md` 是新建专业要遵守的规范。
- 其余是按需读取的专项规则，例如研发流程、安全、性能、运维与部署、任务包、多人协作。

`collaboration/tools/` 里有阶段切换检查脚本 `stage_gate.py`（阶段与人审点从各专业的登记读取）和离线审阅页 `review.html`。

安装不会启动任何 Agent、初始化数据库或批准任何成果。

## 适用的宿主

适用于支持项目级 skill（带 frontmatter 的 SKILL.md）并读取项目说明文件的 Agent 宿主，不依赖特定模型。安装时告诉安装器两件事：

- `--skills-dir`：宿主在项目里发现 skill 的目录，必须是两级相对路径，例如 `.agents/skills`（默认）或 `.claude/skills`。
- `--entry`：宿主自动读取的项目说明文件，例如 `AGENTS.md`（默认）或 `CLAUDE.md`；可以重复指定多个。

宿主提供选项式提问工具时，确认节点会用它展示两个选项；没有时自动退回文本。跨角色的子任务或消息工具在项目的 `collaboration/runtime/host.md` 中登记（见 `collaboration/RUNTIME.md`）。

## 安装

需要 Python 3.10 或更高版本。本包只装进新项目：项目里装有更早的版本（包括 0.29）时，安装器在写入任何文件前停止，不升级、不迁移。在本包目录运行，先预检再安装：

```sh
python3 install.py --target "<项目路径>"
python3 install.py --target "<项目路径>" --apply
```

指定宿主约定的例子：

```sh
python3 install.py --target "<项目路径>" --skills-dir .claude/skills --entry CLAUDE.md --apply
```

安装器会：

- 复制本包的 12 个 skill 与共用规则；在说明文件中写入或更新一个受管入口块，块外内容原样保留。
- 在同一项目里重复安装同一版本时，没有变化的文件不改动；项目改过的指引索引（各 skill 的 `GUIDANCE-INDEX.md` 与共用规则索引）原样保留并在结果中列出，供人对照合并。
- 发现关键共同规则（`CORE.md`、`USER-INTERACTION.md` 等）或 skill 文件被改过且无法识别时，在写入任何文件前停止，先人工合并。
- 不修改 `product/`、`design/`、`engineering/`、`collaboration/feedback.md`、运行数据库等业务成果；原文件备份在 `management/install-backups/`，回执在 `management/install-receipt.json`。

逐文件原子写入，可以中断后重跑，但不是全项目事务。

## 安装之后

- **新项目**：先决定用哪些专业、多大规模。可以请 project-front-desk-agent 按项目描述和专业登记推荐组合，由你决定；需要全流程统筹时说"请用 project-management-agent 统筹这个项目"。
- **单对话**：只想在一个对话里完成小任务时，说明使用本技能包；模型按 `collaboration/MATRIX.md` 的单对话用法，依次按各专业的要求工作，并如实标注"同一实例检验"。
- **已有成果、没有装过本包的项目**：让当前负责角色读取本角色 skill 和 `collaboration/CORE.md`，从当前有效阶段继续；保留有效确认与人的修改，只补受影响的范围，不重新访谈。
- **项目调整**：在各 skill 的 `GUIDANCE-INDEX.md` 或共用规则索引的"项目说明"列写补充、替换或停用（见 `collaboration/GUIDANCE-RESOLUTION.md`）。
- **新建专业**：用 profession-builder，按 `collaboration/PROFESSION-SPEC.md` 写登记、职级表与对照、技能和评测情境，用它的检查脚本核对，再重新生成总入口的专业目录。
- **多人参与**：在 `collaboration/people.json` 登记参与的人及其决定权（格式见 `collaboration/TEAM.md`；可由你们的成员管理系统同步）。之后 PM 会把事项发给对应的人，并在 `management/views/` 生成全程计划表、项目总入口、群摘要、个人视图与专业组视图。仅个人独立项目可不建名单；受邀专业成员即使只有一人也按名单中实际权限判断。
- **运行方式**：多人或中型以上项目，建议主对话使用 project-front-desk-agent。它启动时检测宿主能否创建子 Agent，经你一次授权后，在各角色第一项任务就绪时为它创建子 Agent；主对话只保留问询与结论。宿主不支持时在主对话里切换角色。

## 按需加载

启动时只加载：说明文件中的入口块、当前角色的 SKILL.md、`collaboration/CORE.md`、共用规则索引和本角色的 GUIDANCE-INDEX.md。其余指引按索引中的"何时读"打开；能力标准按二级能力逐份打开（每份一千多字），不整体加载。

## 检验

发布说明记录本版做过的检查与行为评测结果。`BEHAVIOR-CHECKS.md` 列出需要在真实项目中观察的行为，供人工试用时对照；执行角色不需要预读它。格式、安装和脚本测试通过，不代表 Agent 的实际判断与体验质量已经过验证。

## 多实例团队

负责人、执行者和工作流 PM 按 [项目任职](collaboration/TEAM-EXECUTION.md) 接入，共用专业核心与唯一任务源。负责人在委托内组织日常交付，真人保留关键判断和必要干预；没有团队配置时保持单实例方式。先核对实际宿主派发/接续能力和 [工具授权边界](collaboration/TOOL-ACCESS.md)，安装不启动服务或取得外部权限。
