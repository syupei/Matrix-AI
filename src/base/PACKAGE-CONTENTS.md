# 包含什么

何时读：查找专业与安装后的目录职责。调用前置与其余操作见[原入口](../../START.md)。

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
