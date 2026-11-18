# 外部输入准入

何时读：收到外部材料、确认或变更，准备将其用于生产，或执行收到任务卡外直接指令。

## 沟通与生产

人与前台、PM、专业负责人完成澄清、审阅、风险/冲突处理和必要确认，PM掌管版本准入。生产实例只执行已派发任务卡和已准入版本；直接指令用production_feedback登记原意与任务交PM，继续不受影响的原范围。

改标题、下一步、范围、输入/输出、验收、检验人、人审或完成前置等任务语义由有权限的PM经准入/变更修改；执行者只提交成果、进度和反馈，自写scope_authorization不能提权。在运行时先按流程停止，再改工作版本并重核受影响检验/确认。启动包只用管理者批准的指令，不能让执行者report里的“下一步”改掉任务。

## 全来源核对

专业任务的每项业务输入均须是当前已准入版本、已完成上游的真实交回成果（摘要匹配），或与安装包相同的固定规则。按输入依据判断，不按目录或文件名放行；新路径、纯文字或换专业同样核对。纯文字先落为真实受理材料再登记，不以缺metadata或自填internal跳过。普通协调保持原流程，不得用协调任务包裹专业生产绕开。子任务继承父项准入关系，新增输入补绑。

## 操作

- intake_register：PM写id、稳定的source_id（同一需求文档族）、项目相对path、version、真实source及profession。内容或版本改动给新id；替换同族当前版本可传supersedes。换路径仍用同一source_id，被替换版本不再新派发；不同名字是否同族由PM辨认，工具不承诺语义识别。
- intake_submit：写id与实际任职master。内置/导入同检查；master可派子实例审阅并负责最终结论。审阅任务以intake_review_id绑定，产出仅限management/intake-reviews/审阅稿。
- intake_review：由该master写id、outcome（approved/changes_requested）、conclusion、resolved_risks、resolved_conflicts、open_items、human_required；有风险/冲突保持审阅中，无事项明确空数组。
- 需要人审时先human_attention：id、kind、display、intake_id、scope（展示范围描述字符串），可附inputs；实际展示即冻结材料与版本。答复时用同id写response，可用response_id定位完整消息。intake_admit由PM带id、person、完整quote、attention_id与同一scope消费该次展示/答复，不能只填人名原话自签。已有确认覆盖时引用实际来源，不加一次重复人审。intake_status查待办。共同格式见[证据格式](../base/REVIEW-EVIDENCE.md)。
- 生产任务inputs列实际路径，admitted_inputs列当前输入id，stage_transition指上游有效人审记录；成果摘要须覆盖绑定版本。产品基线型研发承接核产品最终确认。创建、启动和完成沿同一核对；工具提示负责处理方。候选只写outputs明确路径，目录以/结尾。
- 专家adapt的review.review_points每项含who:master与what，在运行前核有效。逐阶段映射、独审与失效迁移按[专家接入](EXPERT-IMPORT.md)。
- practice_stage写role/current/scope，及适用practice_scope/tone_contract/practice_evidence/upstream/upstream_bundle/implementation_handoff。派发查entry，完成用practice_completion指本阶段检查输入。成功封存返回引用的接力按[阶段检查](../base/STAGE-GATES.md)，不能把自填通过当回执。

一条工具记录只证明该来源、范围与版本的核对；宿主提供身份与写入边界。旧来源/答复未绑定新字段时须补核，不追改历史为已批准。
