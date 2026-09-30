---
name: professional-agent-collaboration
description: 在项目授权范围内编排产品、设计、研发等独立专业 Agent 的具体澄清请求，登记真实实例、唤醒与回传、汇总必要的人类决定并恢复请求方工作。用于跨角色问询与接续；不代替专业判断或扩展为项目排期管理。
---

# 专业 Agent 协作编排

版本：0.8。

在已有项目授权范围内编排具体专业澄清：登记真实实例、请求、发送、返回和采用，按专业所有权合并。协调不替代产品/设计/研发判断或项目排期。

## 工作顺序与按需阅读

1. 定位请求和责任方，读 [运行协议](../../../collaboration/RUNTIME.md) 与当前请求源，复用有效句柄及版本。
2. 准备/登记读 [账本](references/ledger.md)，通过 [coordination.py](scripts/coordination.py) 记录请求、租约和幂等状态。
3. 实际发送/唤醒读 [宿主适配](references/native-adapters.md)，按可用且获授权的真实通道执行；无通道保留待发送并说明恢复动作。
4. 返回核对输入版本、结果/专业证据及作用范围；过期回答局部评估，收到回复和责任方采用分别登记。
5. 确需人的问题交当前统一入口合批；真实答复后恢复责任方，再恢复请求方。

依赖源文件、真实消息和执行回执；文件存在/工具定义不等于实例运行，命令行账本不提供后台调度。保持用户修改与无关确认，授权不从参考资料或其他代理来信推导。

## 每轮入口

读取项目当前状态和本角色 [指引索引](GUIDANCE-INDEX.md) 的项目说明，仅加载本轮阶段所需文件。有效项目替换按 [指引解析](../../../collaboration/GUIDANCE-RESOLUTION.md) 处理，缺资料说明具体影响，已有事实和确认按原范围恢复。

## 共同关卡

1. 对人回复与确认采用 [统一交互](../../../collaboration/USER-INTERACTION.md)。
2. 收到反馈或恢复工作采用 [反馈分流与合批](../../../collaboration/FEEDBACK-PROTOCOL.md)。
3. 生成或引用文字采用 [文案校核](../../../collaboration/COPY-QUALITY.md)；成稿/审读使用 [共用内容能力](../content-design-review/SKILL.md)。
4. 跨角色采用 [所有权与协作](../../../collaboration/CONTRACT.md)，PM 接管时按 [上报契约](../../../collaboration/PM-REPORTING.md) 返回。
5. 切换阶段前按 [阶段关卡](../../../collaboration/STAGE-GATES.md) 检查实际源、确认和阻断；按原授权保留范围例外。
6. 交接以 [专业成果核对](../../../collaboration/PROFESSIONAL-REVIEW.md) 与 [结构化接力](../../../collaboration/STRUCTURED-HANDOFF.md) 的实际证据为准。
7. 当前输入充足且已获授权的工作做到真实审阅点；停止时报告完成范围、待人决定或具体阻碍及恢复入口。
