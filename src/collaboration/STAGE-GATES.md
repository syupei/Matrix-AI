# 阶段切换检查

切换产品S1–S7、设计D1–D7或E1子阶段前，先从已有状态、确认记录和实际文件形成一次检查输入，再运行：

```sh
python3 shared/stage_gate.py --project . --state path/to/gate-input.json
```

输入是原状态的投影，不是第二份权威台账。输出allowed=false时只暂停受影响范围，修复具体缺口后再检查。工具不修改阶段；成功后责任方更新原工作状态/任务源并按统一交互显示位置。

输入字段：`role`为product/design/engineering，`current`和`next`是相邻阶段或最后一步到complete；`scope`为本次范围字符串数组；`blockers`必须是已核对的空数组；`artifacts`列出相对项目根路径`path`和实际`sha256`。

审阅节点还提供`request`、`response`两个既有记录导出的JSON路径。request含`request_id,role,stage,scope,artifact_sha256,display_evidence`；response含`request_id,scope,artifact_sha256,actor="user",choice="confirm",source`。display_evidence/source指向真实展示与用户消息的本地引用记录，保留原消息ID/时间及原文；真实工具答复也按同样协议映射。产物组合摘要由stage_gate.artifact_digest计算，按路径排序。浏览器导出回复后补真实回传来源再检查。

关卡按 [统一交互](USER-INTERACTION.md) 的原审阅节点执行。用户明确免审/合并/裁剪时，保留原文与范围并由责任方解释记录；当前检查器对默认序列以外的转换返回阻断，不能伪造confirm绕过。此类明确例外采用原记录人工核对，报告“授权例外，未通过默认程序关卡”，可独立工作继续；后续再为真实需要实现经测试的适配。

本检查只能识别缺文件、改过的版本、范围不匹配、未答/部分答复、跳步及显式阻断。它没有身份认证，不证明消息抄录真实、材料充分或专业判断正确。将它与真实宿主回执、专业评审和行为测试结合，不把JSON字段当作人的授权。
