# 产品 Agent 独立试验包 v0.8

这是供 AI 读取执行的产品角色、工作指引、能力标准和文档模板，不是独立运行的服务或已经训练完成的模型。需要一个能读取并编辑项目文件的 AI 环境。当前版本的工作流程待真实 demo 检验，不宣称已证明具有产品专家能力。

## 开始使用

1. 将压缩包解压到一个新的独立目录；建议不要放在原讨论项目内部。直接将解压得到的 `product-agent-demo-kit-v0.8` 文件夹作为新项目根目录。这样会保留隐藏目录 `.agents`。
2. 在这个目录中新建对话。不要复制原项目的 MEMORY.md、聊天记录或既有产品方案。
3. 复制 [START.md](START.md) 中的启动语发送给 AI，然后用真实想法回答它的问题。
4. 从 `product/` 查看它逐步创建的产出。可以直接改文件，也可以在对话中修正。首次启动前没有产品定义，也没有已经确认的留言板方案。

若复制到已有项目，请保留原 AGENTS.md 并人工合并本包入口，不直接覆盖。本版 skill 依赖根目录 `collaboration/` 的同版本共用规范，迁移时须同时保留；不能只复制隐藏的 skill 文件夹后声称完整接入。若 AI 没有自动使用本包，启动语中的显式文件路径仍可作为入口；无法读取项目文件的环境需由人提供相关文本，不得声称已加载标准。

## v0.8：产品联调基线与独立专业 Agent 协作

产品七阶段与五类共用成果保持稳定。本版明确设计方是具有完整空间/交互/视觉判断能力、能调用工具落地的独立专业 Agent；产品方定义要求、维护产品事实并保留产品验收责任。双方可分别使用不同模型、工具包和专业规则。

本版补充：

- 交接条目的决策性质：必须保持、可替换建议、交由下游设计、待澄清，与草稿/已确认分开。
- 产品协作入口：接收其他角色的具体问题，查询基线、作有依据的解释或授权内决定，必要时提出变更/缺口，返回后继续；不重启整套访谈。
- 根目录 `collaboration/` 提供可复用的共用协议 0.1、独立角色配置模板、请求与返回模板。各角色引用同一协议，跨职责修改由成果责任方核对合并，处理旧版本、重复与取消后的结果。
- 常规已授权交流不逐条找人；原定人审节点保留，Agent 共识不冒充人工批准。

本版作为第二个 skill 接入时的固定产品基线，停止无依据扩张产品范围；真实联调发现问题后以新版本修正，不覆盖本发布包。当前是规则与接口基线，不是已经通过跨模型运行验证的稳定版本。

本包只提供产品 skill 及共用协作规范，没有创建第二个设计 skill，也没有实现消息投递、模型切换或自动恢复服务。没有实际接入时只能如实准备交接材料；配置好并获授权的协作通道才可以实际调用。

## v0.7 的变化：共用产品依据，按接收方交付

产品成果分为五类：产品模型、功能与行为规格、界面与交互要求、感知与风格要求、验收与验证要求。`01-产品定义.md` 作为统一入口，正文默认按需放在 `product/specs/`；简单项目可保留在同一文件的明确章节。状态、产品评审和交付说明仍独立维护，五类内容不是新增五个审批环节。

`03-交付说明.md` 按负责人、UI/UE、技术、QA 给出读取版本/范围、接力任务、预期返回、依赖和可探索边界。运营/客服、运维、安全/隐私/法务/来源专家、数据分析、内容/本地化、用户研究与专项体验验证仅按实际需求纳入。所有角色引用同一套规则；不为每个角色生成重复 PRD，也不自动调用下游 Agent。

QA 复用共用验收场景，补需求到验收的追溯、前置/数据条件、可观察判据、覆盖与风险依据、待验证项和变更回归影响。测试用例细化、自动化与执行由 QA/技术承接。产品推演、人工确认、测试通过分别记录。

详见 [共用成果与接收方](.agents/skills/product-agent/references/deliverables-and-recipients.md)。已有项目先建立章节映射，拆分保留 ID、快照和确认依据；只搬移不重新审批，实质新增/变更仍需按原约定审阅。

## v0.6 的变化：连续执行与真实停止原因

修正“下一步由我整理、目前无需操作”后轮次结束却不执行的问题：已授权且输入足够的工作在当前轮次做到下一个真实审阅点。进展播报不是停止点，不需要用户反复发“请继续”。

真正需要审阅时交出成果、链接和具体问题；真正受阻时说明停止原因、已完成范围与恢复所需动作。工作状态新增执行与恢复字段，不能在停止后仍写正在处理、无需操作。对旧版遗留停顿，恢复已有授权工作；不把恢复消息追认为批准草稿，也不额外增加审批。

规则见 [审阅交互第 1.1 节](.agents/skills/product-agent/references/review-interaction.md)。本包仍是 skill 指引，不附带后台调度服务。不能只靠文案声称轮次结束后会自动运行，也不为解决普通停顿创建额外自动化。

## v0.5 的变化：必需澄清与可委托偏好

按能力模型区分“必须确认 · 核心”“条件必确认 · 关键”“可选 · 偏好/辅助”，给出原因和解决时点。用户可以先说不清楚；AI 不能代填真实目标、用户事实和领域约束。文案、视觉、非强制配色及参考增加“AI 帮你选”、自定义等选项。

文案新增调皮俏皮、轻松自然、温暖亲切、清晰直接、专业正式、严肃克制、严谨规范（条款式）；视觉新增日式清新、公务严肃、游戏炫酷、动漫可爱、极简现代、商务专业、温暖生活、科技未来。均为未预选的候选，按产品场景调整，不把形容词当验收标准。具体依据见 [澄清责任与风格选项](.agents/skills/product-agent/references/intake-decisions-and-styles.md)。

HTML 表单同步升级至 0.5，显示重要性、原因及必要补充提醒；JSON/Markdown 导出保留分类与委托范围。草稿可导出，不把已填写计数当作阶段完成。

## v0.4 的变化：随时知道处于哪个阶段

每轮实质性产品回复开头显示“当前阶段｜工作状态｜处理范围”。首次、阶段切换、返工和定稿给出阶段总览；等待人或其他 Agent 时说明谁需要提供什么，以及返回后由谁处理。

固定路线为：需求澄清 → 目标与范围 → 对象与规则 → 功能与流程 → 体验要求 → 评审与修正 → 定稿与交接。路线允许回查与协同，不表示必须单向执行，也不是七大能力的排列。

例如“主阶段：评审与修正｜回查：对象与规则｜等待领域专家补充规则”，会同时说明返工原因和受影响范围。产品草稿、Agent 已返回、人已确认和实际交接分别记录，不用文件存在或阶段序号虚构完成率。本包提供状态指引，不自动运行其他 Agent 或后台监控。

## 保留 v0.3 的审阅提示

当工作需要人介入，Agent 必须在本轮最终对话中给出明确提示，包含本次成果摘要、可点击的实际文件链接、版本与审阅范围、重点与未决项、可回复方式，以及确认后下一步。文件存在、面板已打开或状态写着“待确认”，都不能代替这条提示。

例如，Agent 应说明“现在请确认目标与首期范围”，指出具体需要检查的决定，并让用户可以直接说同意、提出修改或要求解释。无需记编号、寻找文件或猜测“继续”是什么意思。如果前一轮确实已到审阅点却遗漏入口，Agent 应补齐提示；若只是已授权工作被提前中断，则直接恢复执行，不能将用户的“请继续”追认为对未展示成果的批准。

## 保留 v0.2 的首轮基础澄清

根据首轮 demo 反馈，第一步改为两组基础表单：产品意图与任务，以及平台、人群特征、使用情境、范围约束、文案、风格和颜色品牌期望。已知内容不重复问；“未回答、待定、无偏好、请建议”分别记录。后续再用少量问题深化，避免遗漏基础条件。

优先由 Agent 使用环境自带的选项和输入框；没有原生表单时，可打开 [本地基础澄清表](.agents/skills/product-agent/assets/initial-intake-form.html)，用浏览器填写并导出回答。表单不联网、不自动保存，导出文件或预览文本需要交给当前项目的 Agent，才会进入产品记录。通用表单可补充少量与当前产品相关的关键问题。

## 在已有试验项目中升级

保留 `product/`、确认快照和观察记录。更新本包的 skill 文件夹与 `collaboration/` 三个规范/模板文件；如自行修改过，先比较并合并。保留项目已有协作请求、角色实际配置和运行记录，不能整目录覆盖。不同协议版本先核对兼容性。根目录 AGENTS.md 也需合并产品协作入口，保留已有连续执行规则；多角色项目不要让设计/技术实例误用产品专用入口。然后使用 START.md 中的升级语，让 Agent 根据实际成果和确认依据恢复当前位置、补齐阶段概览，并展示当前动作。不从头清空或重做项目，不把未知历史进度补成已完成。v0.8 沿用 v0.5 的表单（版本仍为 0.5）；旧版输入与已有效确认仍保留，不将旧版“请建议”追认为新委托。

## 包内内容

| 路径 | 用途 |
| --- | --- |
| [AGENTS.md](AGENTS.md) | 新项目入口和试验范围 |
| [.agents/skills/product-agent/SKILL.md](.agents/skills/product-agent/SKILL.md) | 产品 Agent 的角色与执行契约 |
| [collaboration/CONTRACT.md](collaboration/CONTRACT.md) | 独立专业 Agent 共用协作约定 0.1 |
| [collaboration/ROLE-CONFIG-TEMPLATE.md](collaboration/ROLE-CONFIG-TEMPLATE.md) | 角色职责、独立模型/工具配置和接入字段 |
| [collaboration/REQUEST-RESPONSE-TEMPLATE.md](collaboration/REQUEST-RESPONSE-TEMPLATE.md) | 请求、答复、版本核对及关闭记录模板 |
| [.agents/skills/product-agent/references/product-collaboration.md](.agents/skills/product-agent/references/product-collaboration.md) | 产品方收到或发出协作问题时的实际处理 |
| [.agents/skills/product-agent/references/principles.md](.agents/skills/product-agent/references/principles.md) | 必须继承的产品质量标准 |
| [.agents/skills/product-agent/references/workflow.md](.agents/skills/product-agent/references/workflow.md) | 七个工作环节、确认方式、变更与续做 |
| [.agents/skills/product-agent/references/stage-and-collaboration.md](.agents/skills/product-agent/references/stage-and-collaboration.md) | 阶段总览、当前责任方、返工与并行、协作交接及定稿状态 |
| [.agents/skills/product-agent/references/review-interaction.md](.agents/skills/product-agent/references/review-interaction.md) | 对话审阅提示、链接、回复方式、遗漏恢复与“继续”的处理 |
| [.agents/skills/product-agent/references/initial-intake.md](.agents/skills/product-agent/references/initial-intake.md) | 首轮基础项、控件形式、默认与未知处理、后续影响 |
| [.agents/skills/product-agent/assets/initial-intake-form.html](.agents/skills/product-agent/assets/initial-intake-form.html) | 实际可填写的本地表单，可导出 Markdown/JSON |
| [.agents/skills/product-agent/references/capability-index.md](.agents/skills/product-agent/references/capability-index.md) | 7 大能力、48 项二级能力及原文阅读入口 |
| [.agents/skills/product-agent/references/deliverables-and-recipients.md](.agents/skills/product-agent/references/deliverables-and-recipients.md) | 五类成果、角色接力、QA 依据、版本组合与旧项目迁移 |
| [.agents/skills/product-agent/references/review-and-handoff.md](.agents/skills/product-agent/references/review-and-handoff.md) | 自检、评审、交付对象和设计回验 |
| [.agents/skills/product-agent/assets/product-workspace-template.md](.agents/skills/product-agent/assets/product-workspace-template.md) | 按需生成工作文档的模板 |
| [.agents/skills/product-agent/sources/SOURCE-NOTES.md](.agents/skills/product-agent/sources/SOURCE-NOTES.md) | 原始资料、版本差异和可核对来源 |
| [.agents/skills/product-agent/references/standards/](.agents/skills/product-agent/references/standards/) | 从完整模型按模块原文提取的阅读切片 |
| [DEMO-TEST.md](DEMO-TEST.md) | 供人使用的试验观察和问题记录方法 |

所有关键定义、规则、状态和人的确认用 Markdown 保存，便于人和 AI 共同编辑。无需额外数据库、运行框架、API 密钥或全局 skill 安装。产品工作需要外部证据时，按当前环境权限和用户授权处理，并说明证据来源。

## 能力与试验流程的版本

- 能力来源：用户提供的《产品领域专家能力要求模型》，总纲 V0.2、P1 V1.1、P2–P7 V1.0，汇编构建日期 2026-08-31。
- 本包工作指引：v0.8，整理日期 2026-09-18，依据用户关于人机共同阅读、编辑、监督与逐步确认的要求，以及本次讨论的七环节草案。
- 七大能力是专业判断视角；七个工作环节是本次试验的流程假设，二者不一一对应，也没有把 Agent 拆成七个实例。
- 提供完整源材料不等于每次都加载全文；Agent 根据当前工作读取相关正式定义、二级能力和案例。遇到证据缺口应明确记录。

项目入口和 skill 目录采用官方文档说明的 [AGENTS.md 机制](https://learn.chatgpt.com/docs/agent-configuration/agents-md)与[项目 skill 结构](https://learn.chatgpt.com/docs/build-skills)。实际加载仍受宿主环境与更高层指令影响。

## 验证范围

本次检查 skill 格式、包内引用与迁移路径、源标准和 HTML 表单一致性、ZIP 解压与哈希；对照协议检查新需求/续做/跨角色问题路由、决策性质、旧版本与重复请求、授权内澄清和超范围变更的规则一致性。观察场景保存在 DEMO-TEST.md，未把情境检查声称为真实多 Agent 测试。第二 skill、跨模型通道与自动恢复尚未实现，需未来真实接入验证；源模型和表单保持不变。
