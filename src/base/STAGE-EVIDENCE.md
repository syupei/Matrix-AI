# 阶段证据与接续

何时读：填写实际试做、D-6、首增量完成证据或接续历史记录。基本ref/采集格式见[审阅证据](REVIEW-EVIDENCE.md)，动态字段/版本见[共同定义](tools/practice_profiles.py)。只读本阶段适用部分。

## 封存、来源与范围

成功stage_gate输出review_bundle/upstream_state及带bundle的practice_evidence。PM从task.practice_receipt的bundle/state_path读取冻结state，取其practice_evidence接续；派发和完成的entry证据、upstream/upstream_bundle须一致。上游同时传这两个字段，缺半份明确拒绝，不先过后坏。

当前完成的artifacts覆盖真实本任务/子任务交回；普通笔记不能代实现。封存记录实际读过的交接、委托、答复及上游文件，在快照内自检后才登记management/stage-receipts。历史记录须来源于该成功阶段的冻结state；手工seal_bundle不等于关卡回执。E-2.4还查E-2.3骨架活成果，此间变化回到受影响复核；进入增量后正常演进读已验快照。

已封存贴合可用后来退役的已登记实例，新复核须在任并有真实独立交回；无可信检验会话的单对话标same_instance，不编independent。每份成果逐项按path＋sha绑定实际交回与已登记producer，不以同内容不同路径或部分交回代全份；独检记录自身也核真实交回路径＋sha，checker不得是任何生产者。PM在E-3.2父任务下首个实际实现子项交回时调用既有increment_fit＋D6复核，下一实现项启动前核首项回执，独检子项不冒实现。E-3.1若显式提前交付，用delivery_kind:first_operable_increment触发同检查；纯计划不触发，不改真实阶段或冒称关闭E-3.2。

新确认中本活动scope的特征/专业段落及共同tone、核心过程、参照、样句、避忌、viewport未变时，可沿用其旧封存事实；改变的范围重审。不能用新增admin范围抹掉原board约束，也不因新增无关范围使全部旧事实失效。发布E-4.3须消费E-4.2决定快照，并递归保留E-3.3确认。

## 实际操作、时序与试玩

playable_prototype写status:completed、实际environment；run_evidence/timing_evidence指JSON，均须含本记录全部artifacts（path/sha256）和实际stage，另分别有：

- run：status:observed、environment、events:[{action,result,at_ms}]。
- timing：status:observed、environment、measurements:[{event,result,started_ms,observed_ms}]。

时间非负，观察不早于开始；不设普遍毫秒阈值。其他版本/阶段的日志不冒当前执行，声称未运行/未测量的说明不能同时当observed。

E-2技术试做允许playtest_status:pending，playtest说明既有试玩安排，不新增人审。E-3.3/Q-2按既有实际验收需playtest_status:observed及playtest_evidence ref；其JSON写status:observed、environment、同artifacts、sessions:[{player,source:{path,sha256},observations:[实际观察]}]。只追溯真实已有反馈，不强加新审批或多名玩家。Q-2另写tested_stage:{bundle,state_path}引用成功E-3.3版本，record.artifacts包含其被测成果，不只QA报告。记录绑定不认证人的身份或好不好玩。

## 实现走查

implementation_walkthrough仍写scope、tone_contract、实际artifacts及locations/activity_effect/preservation_basis/recheck_method。以下改为结构行：

- preserved_states:[{state,layer,basis}]；无适用项时空数组，写理由，并由实际fit检验人以preservation_review:{checker,conclusion}确认。
- design_recheck_states:[{state,method,evidence:{path,sha256}}]；图像证据另附该行capture_binding，沿共用采集校验。
- corrections:[{location,type,destination}]；无纠偏用空数组，type为implementation_deviation/acceptable_difference/design_gap/product_decision四类。

不能用“无”几句空话代逐状态记录。PM下D6快照须来自真实已关闭的设计专业D-6任务；E-3.2的design_review:{bundle,state_path}引用它并覆盖本次实现。纯设计的implementation_handoff须有实际依据和全部artifacts，不拿design_only豁免实现交回；D-6自身不重复填design_review。这些是既有走查/复核的证据结构，不加人审节点。

导入专家按当前professional_contract映射并验证各阶段共同记录；定义变化后旧摘要不静默沿用。D-4交审与完成均核[锚点对照回执](ASSET-COMPARISON.md)。
