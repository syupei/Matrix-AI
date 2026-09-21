# 专业 Agent 完整测试包 0.2

本包包含全部五个现有角色，可按任务选择使用，不需要同时启动五个实例。

| 角色 | 版本 | 入口 |
| --- | --- | --- |
| 产品 | 0.12 | [.agents/skills/product-agent/SKILL.md](.agents/skills/product-agent/SKILL.md) |
| 交互与视觉设计 | 0.6 | [.agents/skills/experience-design-agent/SKILL.md](.agents/skills/experience-design-agent/SKILL.md) |
| 研发承接 E1 | 0.3 | [.agents/skills/engineering-intake-agent/SKILL.md](.agents/skills/engineering-intake-agent/SKILL.md) |
| 项目管理 | 0.2 | [.agents/skills/project-management-agent/SKILL.md](.agents/skills/project-management-agent/SKILL.md) |
| 专业协作 | 0.3 | [.agents/skills/professional-agent-collaboration/SKILL.md](.agents/skills/professional-agent-collaboration/SKILL.md) |

## 这次修正了什么

[文案转译与校核规则](collaboration/COPY-QUALITY.md) 贯穿五个角色：所有产出、外部资料、上游已确认内容、引用和工具默认文字都按用户要求检查。来源事实、内部核查判断与面向读者的成稿分清用途；保持事实含义，不把普通源文逐字相等当成质量标准。代表样板确定尺度后，检查当前全部实际内容，制作后回读，并将修订合并回唯一有效文案源。

产品负责成稿及语义依据；设计负责完整呈现与复核；E1 承接文案源、变量和约束；PM 检查实际校核证据；协作负责问题返回、版本和采用。实际评审须记录改了什么、哪些含义保持、检查了哪些范围，不能只写“已按 P3 检查”。

原产品能力模型、七项专业增强、基础澄清、人审提示、阶段反馈、设计工具优先规则、E1、PM 分层任务及通信运行工具保留。设计仍优先读取并使用适用的已安装设计 skill，例如 Figma；受阻时说明实际原因，不静默改为自行写页面。

原通信协议、运行账本及 PM-REPORTING 版本保持不变。包内不含外部工具的账号连接，不实现 E2/E3/QA 专业 Agent 或后台调度。QA 所需的文案验收依据已纳入专业交接。

## 安装与升级

解压后，在本包目录中先运行预检，再执行安装（需要 Python 3.10 或更高版本）：

```sh
python3 install.py --target "/实际项目路径"
python3 install.py --target "/实际项目路径" --apply
```

也可以让目标项目的 Agent 读取本说明，使用解压目录中的 `install.py` 完成预检与安装。不要直接解压覆盖整个业务项目。

安装器核对文件哈希及已知旧版。它安装五个 skill 和共用规则，增补或更新 AGENTS.md 中的角色入口，保留原入口正文；不覆盖产品、设计、工程业务成果、人的修改、确认、反馈或运行数据库。原文件备份和回执位于目标项目的 `management/install-backups/` 与 `management/install-receipt.json`。

未知的专业 skill 定制或关键公共规则冲突会在写入前停止，先差异合并再安装；其它项目自定义公共文件保留并在回执列出，由接管者检查兼容性。不能为通过安装而把未知文件冒充已知旧版。安装采用逐文件原子写入，可中断重跑，不是全项目事务。

安装本身不启动 Agent、初始化数据库或批准任何候选成果。已在运行的任务需要在安全检查点实际读取新规则；单纯复制文件不能证明旧会话已采用。无需为此重做产品访谈或新建任务。

## 在旧测试项目中接续文案修正

完成安装后，可把下面这段发给原任务：

> 请读取本项目 AGENTS.md、当前责任角色的 skill 和 collaboration/COPY-QUALITY.md，从当前有效阶段修正已有文案。沿用已经给出的读者、文风与产品约束，先定位产品成稿源和已制作的设计，不重启访谈。检查本次产品及设计范围内的全部实际文字，包括资料引用、长正文、辅助、限制和异常；将内部核查口吻转成读者能理解的表达，保持事实、条件、数值和不确定性。修订合并回有效文案源，再按项目已安装的设计 skill 更新派生成果并回读。保留历史与不受影响的确认；报告实际修改、覆盖范围、未验证项和可打开的成果入口。需要跨角色时沿用现有真实协作通道，不能把安装视为内容已经修好。

当前阶段若还有其它已授权任务，由现有负责人按影响安排；需要人判断时提供具体成果及问题。不要仅预告下一步后结束并写“无需操作”。

## 管理与协作入口

已有 PM 项目继续使用当前任务源；新项目需要管理时再按 PM skill 初始化实际项目名、责任者、授权和并发额度。专业角色自管子任务并按 [PM-REPORTING](collaboration/PM-REPORTING.md) 上报。运行工具生成的 `management/views/index.md` 可展开任务、依赖和检验记录；生成视图只读，专业正文仍由原角色维护。

真实协作实例及通道按 [RUNTIME](collaboration/RUNTIME.md) 配置。没有实例或通道时如实说明，不能把角色文件视为已唤醒的同事。现有专业进度不重做，历史完成项不得无依据补签。

## 怎样检验本次修正

实际行为观察见 [DEMO-TEST.md](DEMO-TEST.md)，文件与运行机制的检查结果见 [VALIDATION.md](VALIDATION.md)。检查脚本通过不证明文案已符合需求，真实 Agent 和设计工具的完整试验仍需在测试项目进行。安装本包不会自动改写旧项目的文案或 Figma 文件。
