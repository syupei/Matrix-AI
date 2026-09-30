# professional-agents-kit 0.17

一组中文专业 Agent skill：从一句话需求出发，按产品 → 交互与视觉设计 → 研发承接的专业流程推进，由 PM 统筹，由协作 skill 处理跨角色问询。每个角色保留自己的阶段、人审节点和成果；人始终掌握关键决定。

## 包含什么

| skill | 作用 |
| --- | --- |
| project-management-agent | 统筹：顶层任务、依赖、子任务上报、集中人审、进度视图 |
| product-agent | 产品：澄清、目标与范围、对象与规则、功能流程、体验要求、评审与交付（S1–S7） |
| experience-design-agent | 交互与视觉设计：设计基础、粗结构、细交互、代表视觉、完整设计、验证与交付（D1–D7） |
| engineering-intake-agent | 研发承接：输入核对与澄清、逻辑工程模型、评审与交接（E1） |
| professional-agent-collaboration | 协作：真实请求、唤醒、应答、人工答复与恢复 |
| content-design-review | 产品与设计共用的文案写作与审读方法 |
| product-capability-model | 共享知识库：优秀产品七原则、七大能力、48 项二级能力的原文 |

`collaboration/` 是所有角色共用的规则，安装到项目根目录；`CORE.md` 是每个角色启动时读的共同底线。

安装不会启动任何 Agent、初始化数据库或批准任何成果。

## 适用的宿主

适用于支持项目级 skill（带 frontmatter 的 SKILL.md）并读取项目说明文件的 Agent 宿主，不依赖特定模型。安装时告诉安装器两件事：

- `--skills-dir`：宿主在项目里发现 skill 的目录，必须是两级相对路径，例如 `.agents/skills`（默认）或 `.claude/skills`。
- `--entry`：宿主自动读取的项目说明文件，例如 `AGENTS.md`（默认）或 `CLAUDE.md`；可以重复指定多个。

宿主提供选项式提问工具时，确认节点会用它展示两个选项；没有时自动退回文本。跨角色的子任务或消息工具在项目的 `collaboration/runtime/host.md` 中登记（见 `collaboration/RUNTIME.md`）。

## 安装与升级

需要 Python 3.10 或更高版本。在本包目录运行，先预检再安装：

```sh
python3 install.py --target "<项目路径>"
python3 install.py --target "<项目路径>" --apply
```

指定宿主约定的例子：

```sh
python3 install.py --target "<项目路径>" --skills-dir .claude/skills --entry CLAUDE.md --apply
```

安装器会：

- 复制七个 skill 与共用规则；在说明文件中写入或更新一个受管入口块，块外内容原样保留。
- 按文件哈希识别本包发布过的版本：与已知发布版一致的文件直接更新；本版不再使用、且未被改动的文件在备份后移除；项目改过的 `GUIDANCE-INDEX.md` 原样保留并在结果中列出，供人对照合并。
- 发现关键共同规则（`CORE.md`、`USER-INTERACTION.md` 等）或 skill 文件被改过且无法识别时，在写入任何文件前停止，先人工合并。
- 不修改 `product/`、`design/`、`engineering/`、`collaboration/feedback.md`、运行数据库等业务成果；原文件备份在 `management/install-backups/`，回执在 `management/install-receipt.json`。
- 说明文件中若有早期单独安装留下的入口文字，在结果中列出（`legacy_entry_review`）供人工查看，不自动删除。

逐文件原子写入，可以中断后重跑，但不是全项目事务。

## 安装之后

- **新项目**：直接向宿主描述需求；需要全流程统筹时说"请用 project-management-agent 统筹这个项目"。
- **已有成果的项目**：让当前负责角色读取本角色 skill 和 `collaboration/CORE.md`，从当前有效阶段继续；保留有效确认与人的修改，只补受影响的范围，不重新访谈。
- **项目调整**：在各 skill 的 `GUIDANCE-INDEX.md` "项目说明"列写补充、替换或停用（见 `collaboration/GUIDANCE-RESOLUTION.md`）。

## 按需加载

启动时只加载：说明文件中的入口块、当前角色的 SKILL.md、`collaboration/CORE.md` 和本角色的 GUIDANCE-INDEX.md。其余指引按索引中的"何时读"打开；能力标准按二级能力逐份打开（每份一千多字），不整体加载。

## 检验

`VALIDATION.md` 记录本版做过的检查。`BEHAVIOR-CHECKS.md` 列出需要在真实项目中观察的行为，供人工试用时对照；执行角色不需要预读它。格式、安装和脚本测试通过，不代表 Agent 的实际判断与体验质量已经过验证。
