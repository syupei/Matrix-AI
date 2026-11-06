# Matrix-AI 0.31

一组中文专业 Agent skill 的基座，分三部分：所有 Agent 共同遵守的基础部分；项目管理、项目前台负责的调度部分；产品、内容设计与审读、交互与视觉设计、代码工程、质量工程等任务专家。每个专家以"专业标识"为岗位，可以由本包自带的技能担任，也可以换成你自己的 Agent。项目启动时由人决定用哪些专业，以及各专业几个实例、什么职级、用什么基座模型；每个专业保留自己的阶段、人审节点和成果，人始终掌握关键决定。小任务也可以不分实例，在一个对话里按各专业的要求完成。

## 包含什么

| skill | 作用 |
| --- | --- |
| matrix-front-desk | 项目前台（调度）：主对话入口，启动检测并按需拉起角色，按专业登记推荐专业组合，按文件回答问询，登记并转交要求，展示待决事项 |
| matrix-project-management | 项目管理（调度）：按人确认的配置派生实例，顶层任务、依赖、子任务上报、集中人审，任务列表、进度视图与实例台账 |
| matrix-product | 产品：澄清、目标与范围、对象与规则、功能流程、体验要求、评审与交付（P-1–7） |
| matrix-content-design | 内容设计与审读：用户看到的文字（界面文案、提示与错误提示、通知、引导）与带键的文案表 |
| matrix-experience-design | 交互与视觉设计：设计基础、粗结构、细交互、代表视觉、完整设计、验证与交付（D-1–7） |
| matrix-code-engineering-intake | 代码工程的承接：输入核对与澄清、逻辑工程模型、档位与技术风险、评审与交接（E-1） |
| matrix-code-engineering-solution | 代码工程的方案：按问题作技术决定、风险试做、可运行骨架与工程基础、委托优先的技术评审，关键技术选型由人确认（E-2） |
| matrix-code-engineering-build | 代码工程的构建与发布（技术负责人）：按用户可见能力切增量、检验与集成、范围完成评审（E-3）；小型、中型项目的发布准备、发布决定包、逐批发布与交接（E-4） |
| matrix-quality-engineering | 质量工程：验收条目与覆盖、非实现者检验、质量测量、发布验收、缺陷定级与回归（贯穿 E-1–4） |
| matrix-collaboration | 协作：真实请求、唤醒、应答、人工答复与恢复；跨专业的多轮议题 |
| matrix-profession-builder | 专业创建：按专业规范新建或修改专业，带登记检查与总入口生成脚本 |
| matrix-product-capability-model | 共享知识库：优秀产品七原则、七大能力、48 项二级能力的原文 |

安装后，项目里是这样：

- **技能**：平放在宿主的技能目录（默认 `.agents/skills/`），名字是 `matrix-<专业标识>`，有几个技能的专业再加阶段，例如 `matrix-code-engineering-build`。
- **`matrix/`**：本包的规则与工具，只读，换版本时整体替换。
  - `base/`：所有 Agent 都要遵守的共同部分。`MATRIX.md` 是总入口：专业目录、怎样选专业、单对话用法。`CORE.md` 是共同底线，`GUIDANCE-INDEX.md` 是共用规则索引，`LEVELS.md` 与 `RISK-DEFECT-LEVELS.md` 是职级与风险、缺陷分级，`PROFESSION-SPEC.md` 是专业规范，`SHARED-INDEX.md` 规定共享知识怎样登记。`tools/` 里有阶段检查、委托检查、共享知识索引检查和离线审阅页。
  - `orchestration/`：调度。包括统筹与上报、任务完整性、实例、多人协作与运行；`tools/` 里有任务库（说明见 `TASK-TOOL.md`）、协作账本与派发。
  - `professions/<专业标识>/`：每个专业的岗位定义，包括登记 `profession.json`、职级与对照 `levels.md`，以及只属于这个专业的规则。派活、缺口和收发都只认专业标识。
- **项目自己的数据不放进 `matrix/`**，用到时才建：
  - `shared/`：共享知识，`index.md` 写明每项在哪、归谁、谁能读、能否给外部；
  - `management/`：调度数据，包括任务库、实例配置与档案、人员名单与进度；
  - `exchange/`：跨专业与对外的收发，包括请求与外发任务包；
  - 各专业的工作区：`product/`、`design/`、`engineering/` 等。

安装不会启动任何 Agent、初始化数据库或批准任何成果。

## 适用的宿主

适用于支持项目级 skill（带 frontmatter 的 SKILL.md）并读取项目说明文件的 Agent 宿主，不依赖特定模型。安装时告诉安装器两件事：

- `--skills-dir`：宿主在项目里发现 skill 的目录，必须是两级相对路径，例如 `.agents/skills`（默认）或 `.claude/skills`。
- `--entry`：宿主自动读取的项目说明文件，例如 `AGENTS.md`（默认）或 `CLAUDE.md`；可以重复指定多个。

宿主提供选项式提问工具时，确认节点会用它展示两个选项；没有时自动退回文本。跨角色的子任务或消息工具在项目的 `management/runtime/host.md` 中登记（见 `matrix/orchestration/RUNTIME.md`）。

## 安装

需要 Python 3.10 或更高版本。本包只装进新项目：项目里装有其他任何版本（包括更名前的 professional-agents-kit）时，安装器在写入任何文件前停止，不升级、不迁移。在本包目录运行，先预检再安装：

```sh
python3 install.py --target "<项目路径>"
python3 install.py --target "<项目路径>" --apply
```

指定宿主约定的例子：

```sh
python3 install.py --target "<项目路径>" --skills-dir .claude/skills --entry CLAUDE.md --apply
```

安装器会：

- 复制本包的 12 个 skill 与 `matrix/`；在说明文件中写入或更新一个受管入口块，块外内容原样保留。
- 在同一项目里重复安装同一版本时，没有变化的文件不改动；项目改过的指引索引（各 skill 的 `GUIDANCE-INDEX.md` 与共用规则索引）原样保留并在结果中列出，供人对照合并。
- 发现关键共同规则（`CORE.md`、`USER-INTERACTION.md` 等）或 skill 文件被改过且无法识别时，在写入任何文件前停止，先人工合并。
- 不修改项目数据和成果：`shared/`、`exchange/`、各专业工作区，以及 `management/` 里的任务库、配置与进度；原文件备份在 `management/install-backups/`，回执在 `management/install-receipt.json`。

逐文件原子写入，可以中断后重跑，但不是全项目事务。

## 安装之后

- **新项目**：先决定用哪些专业、多大规模。可以请 matrix-front-desk 按项目描述和专业登记推荐组合，由你决定；需要全流程统筹时说"请用 matrix-project-management 统筹这个项目"。
- **单对话**：只想在一个对话里完成小任务时，说明使用本技能包；模型按 `matrix/base/MATRIX.md` 的单对话用法，依次按各专业的要求工作，并如实标注"同一实例检验"。
- **已有成果、没有装过本包的项目**：让当前负责角色读取本角色 skill 和 `matrix/base/CORE.md`，从当前有效阶段继续；保留有效确认与人的修改，只补受影响的范围，不重新访谈。
- **项目调整**：在各 skill 的 `GUIDANCE-INDEX.md` 或共用规则索引的"项目说明"列写补充、替换或停用（见 `matrix/base/GUIDANCE-RESOLUTION.md`）。
- **新建专业**：用 matrix-profession-builder，按 `matrix/base/PROFESSION-SPEC.md` 写登记、职级表与对照、技能和评测情境，用它的检查脚本核对，再重新生成总入口的专业目录。
- **多人参与**：在 `management/people.json` 登记参与的人及其决定权（格式见 `matrix/orchestration/TEAM.md`；可由你们的成员管理系统同步）。之后 PM 会把事项发给对应的人，并在 `management/views/` 生成全程计划表、项目总入口、群摘要、个人视图与专业组视图。仅个人独立项目可不建名单；受邀专业成员即使只有一人也按名单中实际权限判断。
- **运行方式**：多人或中型以上项目，建议主对话使用 matrix-front-desk。它启动时检测宿主能否创建子 Agent，经你一次授权后，在各角色第一项任务就绪时为它创建子 Agent；主对话只保留问询与结论。宿主不支持时在主对话里切换角色。要让工作在你不在时也接着推进，用下面的平台运行。

## 按需加载

启动时只加载：说明文件中的入口块、当前角色的 SKILL.md、`matrix/base/CORE.md`、共用规则索引和本角色的 GUIDANCE-INDEX.md。其余指引按索引中的"何时读"打开；能力标准按二级能力逐份打开（每份一千多字），不整体加载。

## 检验

发布说明记录本版做过的检查与行为评测结果。`BEHAVIOR-CHECKS.md` 列出需要在真实项目中观察的行为，供人工试用时对照；执行角色不需要预读它。格式、安装和脚本测试通过，不代表 Agent 的实际判断与体验质量已经过验证。

## 多实例团队

负责人、执行者和工作流 PM 按 [项目任职](matrix/orchestration/TEAM-EXECUTION.md) 接入，共用专业核心与唯一任务源。负责人在委托内组织日常交付，真人保留关键判断和必要干预；没有团队配置时保持单实例方式。先核对实际宿主派发/接续能力和 [工具授权边界](matrix/orchestration/TOOL-ACCESS.md)，安装不启动服务或取得外部权限。

## 平台运行

宿主有非交互运行命令（读入提示后运行一次再退出）时，可以让实例由平台拉起、PM 统一调度（规则见 `matrix/orchestration/TEAM-RUNTIME.md` 平台运行）。

1. 在项目里写 `management/runtime/platform.json`，内容是宿主命令的模板。权限写在这里，由你确认后再用：

   ```json
   {
     "launch": ["<宿主命令>", "<非交互运行>", "<指定模型>", "{model}", "<指定会话编号>", "{session}",
                "<只允许这些工具>", "读取类工具,{write_permissions},<运行 matrix/orchestration/tools/pm_tasks.py>", "<禁止联网类工具>"],
     "write_patterns": ["<写入工具>({root}/**)"],
     "pm": {"launch": ["…同上，另允许运行 matrix/orchestration/tools/launch.py，模型写 PM 用的模型…"],
            "resume": ["<宿主命令>", "<非交互运行>", "<按会话编号续接>", "{session}", "…权限同上…"]},
     "models": {"<实例配置里的模型名>": "<宿主认得的模型名>"},
     "notify": ["<本机提醒命令>", "{message}"]
   }
   ```

   - 宿主命令须能：从标准输入读提示；指定模型；指定会话编号，PM 的命令还要能按编号续接；只允许列出的工具，没列出的直接拒绝而不弹窗询问。
   - `{write_permissions}` 按 `write_patterns` 展开成该实例每个写入范围的写权限；不要用跳过全部权限的方式。
   - 可选的数值：`check_seconds`（60）、`patrol_minutes`（60）、`pm_timeout_minutes`（20）、`resume_limit`（20）、`resume_idle_minutes`（60）。
   - 可选的数值：`settle_seconds`（60，变化后等多久再唤起 PM）、`max_wait_seconds`（300）。
   - 宿主的沙箱不让会话的子进程联网时，加 `"spawn": "scheduler"`。
   - 省用量的宿主设置：PM 的推理强度可以设低一档（日常值班以执行接续为主）；宿主支持按会话编号续接时，给 PM 配上 `resume`。
2. 启动调度器：在项目根目录运行 `python3 matrix/orchestration/tools/scheduler.py --project .`，关掉终端或中断即停止；也可以交给你授权的定时任务，每次运行 `scheduler.py --project . --once`。
3. 停下：告诉前台"暂停项目"，或停掉调度器。电脑关机或调度器停止后，不会有任何运行；再启动时从任务表接着做。
