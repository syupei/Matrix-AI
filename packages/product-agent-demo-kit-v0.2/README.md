# 产品 Agent 独立试验包 v0.2

这是供 AI 读取执行的产品角色、工作指引、能力标准和文档模板，不是独立运行的服务或已经训练完成的模型。需要一个能读取并编辑项目文件的 AI 环境。当前版本的工作流程待真实 demo 检验，不宣称已证明具有产品专家能力。

## 开始使用

1. 将压缩包解压到一个新的独立目录；建议不要放在原讨论项目内部。直接将解压得到的 `product-agent-demo-kit-v0.2` 文件夹作为新项目根目录。这样会保留隐藏目录 `.agents`。
2. 在这个目录中新建对话。不要复制原项目的 MEMORY.md、聊天记录或既有产品方案。
3. 复制 [START.md](START.md) 中的启动语发送给 AI，然后用真实想法回答它的问题。
4. 从 `product/` 查看它逐步创建的产出。可以直接改文件，也可以在对话中修正。首次启动前没有产品定义，也没有已经确认的留言板方案。

若复制到已有项目，请保留原 AGENTS.md 并人工合并本包入口，不直接覆盖。若 AI 没有自动使用本包，启动语中的显式文件路径仍可作为入口；无法读取项目文件的环境需由人提供相关文本，不得声称已加载标准。

## v0.2 的变化与升级

根据首轮 demo 反馈，第一步改为两组基础表单：产品意图与任务，以及平台、人群特征、使用情境、范围约束、文案、风格和颜色品牌期望。已知内容不重复问；“未回答、待定、无偏好、请建议”分别记录。后续再用少量问题深化，避免遗漏基础条件。

优先由 Agent 使用环境自带的选项和输入框；没有原生表单时，可打开 [本地基础澄清表](.agents/skills/product-agent/assets/initial-intake-form.html)，用浏览器填写并导出回答。表单不联网、不自动保存，导出文件或预览文本需要交给当前项目的 Agent，才会进入产品记录。通用表单可补充少量与当前产品相关的关键问题。

在已有试验项目升级时，保留 `product/`、确认快照和观察记录。更新本包的 skill 文件夹；如自行修改过 skill，先比较并合并。根目录 AGENTS.md 也需合并新增的首轮要求。然后使用 START.md 中的升级语，让 Agent 只补齐缺项并检查影响，不从头清空或重做项目。

## 包内内容

| 路径 | 用途 |
| --- | --- |
| [AGENTS.md](AGENTS.md) | 新项目入口和试验范围 |
| [.agents/skills/product-agent/SKILL.md](.agents/skills/product-agent/SKILL.md) | 产品 Agent 的角色与执行契约 |
| [.agents/skills/product-agent/references/principles.md](.agents/skills/product-agent/references/principles.md) | 必须继承的产品质量标准 |
| [.agents/skills/product-agent/references/workflow.md](.agents/skills/product-agent/references/workflow.md) | 七个工作环节、确认方式、变更与续做 |
| [.agents/skills/product-agent/references/initial-intake.md](.agents/skills/product-agent/references/initial-intake.md) | 首轮基础项、控件形式、默认与未知处理、后续影响 |
| [.agents/skills/product-agent/assets/initial-intake-form.html](.agents/skills/product-agent/assets/initial-intake-form.html) | 实际可填写的本地表单，可导出 Markdown/JSON |
| [.agents/skills/product-agent/references/capability-index.md](.agents/skills/product-agent/references/capability-index.md) | 7 大能力、48 项二级能力及原文阅读入口 |
| [.agents/skills/product-agent/references/review-and-handoff.md](.agents/skills/product-agent/references/review-and-handoff.md) | 自检、评审、交付对象和设计回验 |
| [.agents/skills/product-agent/assets/product-workspace-template.md](.agents/skills/product-agent/assets/product-workspace-template.md) | 按需生成工作文档的模板 |
| [.agents/skills/product-agent/sources/SOURCE-NOTES.md](.agents/skills/product-agent/sources/SOURCE-NOTES.md) | 原始资料、版本差异和可核对来源 |
| [.agents/skills/product-agent/references/standards/](.agents/skills/product-agent/references/standards/) | 从完整模型按模块原文提取的阅读切片 |
| [DEMO-TEST.md](DEMO-TEST.md) | 供人使用的试验观察和问题记录方法 |

所有关键定义、规则、状态和人的确认用 Markdown 保存，便于人和 AI 共同编辑。无需额外数据库、运行框架、API 密钥或全局 skill 安装。产品工作需要外部证据时，按当前环境权限和用户授权处理，并说明证据来源。

## 能力与试验流程的版本

- 能力来源：用户提供的《产品领域专家能力要求模型》，总纲 V0.2、P1 V1.1、P2–P7 V1.0，汇编构建日期 2026-08-31。
- 本包工作指引：v0.2，整理日期 2026-09-17，依据用户关于人机共同阅读、编辑、监督与逐步确认的要求，以及本次讨论的七环节草案。
- 七大能力是专业判断视角；七个工作环节是本次试验的流程假设，二者不一一对应，也没有把 Agent 拆成七个实例。
- 提供完整源材料不等于每次都加载全文；Agent 根据当前工作读取相关正式定义、二级能力和案例。遇到证据缺口应明确记录。

项目入口和 skill 目录采用官方文档说明的 [AGENTS.md 机制](https://learn.chatgpt.com/docs/agent-configuration/agents-md)与[项目 skill 结构](https://learn.chatgpt.com/docs/build-skills)。实际加载仍受宿主环境与更高层指令影响。

## 验证范围

交付前检查 skill 格式、运行指引引用、48 项能力完整性、原文切片和源文件一致性、压缩包完整性与可迁移路径，并检查本地表单的填写与导出行为。v0.2 来自用户对 v0.1 的实际反馈；本次打包未代替用户进行新版完整多轮 demo，实际判断质量、确认节奏和返工行为仍需在新项目中检验。
