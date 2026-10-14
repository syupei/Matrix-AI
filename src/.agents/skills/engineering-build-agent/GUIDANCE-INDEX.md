# 指引索引：engineering-build-agent

启动时读一次；之后按"何时读"打开对应文件，不整体预读。"项目说明"由项目填写补充、替换或停用（规则见 [GUIDANCE-RESOLUTION](../../../collaboration/GUIDANCE-RESOLUTION.md)），空白表示沿用默认。

| ID | 指引 | 何时读 | 项目说明 |
| --- | --- | --- | --- |
| C00 | [共同底线](../../../collaboration/CORE.md) | 启动时 | |
| C01 | [用户确认与流程位置](../../../collaboration/USER-INTERACTION.md) | E3.3 范围完成评审、E4.2 发布决定；需要人决定时 | |
| C02 | [研发流程、档位与决策权](../../../collaboration/ENGINEERING-FLOW.md) | 启动时；判断档位、决策级别、可试用版本与待决规则时 | |
| C03 | [反馈处理](../../../collaboration/FEEDBACK-PROTOCOL.md) | 收到试用意见或其他反馈；续做、评审前 | |
| C04 | [协作约定](../../../collaboration/CONTRACT.md) | 请设计走查；回到产品、设计、E1、E2 回查时 | |
| C05 | [阶段检查](../../../collaboration/STAGE-GATES.md) | 切换子环节或标记完成前 | |
| R01 | [增量与任务卡](references/increments.md) | E3.1；每个增量开始前 | |
| R02 | [实现、检验与上报](references/verification.md) | E3.2；需要上报时 | |
| R03 | [集成与范围完成](references/scope-complete.md) | E3.3 | |
| R04 | [发布准备与发布决定](references/release.md) | E4.1、E4.2；E3.1 列出发布前只能由人办的事项时 | |
| R05 | [发布、观察与交接](references/handoff.md) | E4.3；触发停止条件或发布后发现问题时；起草交接包时 | |
| X01 | [技术评审：委托边界与回升条件](../engineering-solution-agent/references/technical-review.md) | 判断是否越界、哪些代码必须人审；引入新的存储、组件或算法时；需要改变已确认的决定时 | |
| X02 | [缺陷分级与回归](../quality-verification-agent/references/defects.md) | 判断缺陷级别对发布的影响时 | |
| T01 | [工作区模板](assets/build-workspace-template.md) | 建立 `engineering/build/` 下的文件时 | |
| T02 | [发布工作区模板](assets/release-workspace-template.md) | 建立 `engineering/release/` 下的文件时 | |
