# 成品影响与验收交付

何时读：E-2.2做技术选择、E-2.4核心评审、Q-3/Q-4汇总验收、E-4.1准备发布。与做法档无关，所有类别、内置与导入专家同样适用。不增加阶段或人审点。

## 准备记录

用 `python3 matrix/base/tools/delivery_records.py --template <名称>` 只取所需模板。名称为product_impact、impact_review、acceptance_package、release_acceptance，辅助模板为candidate、inspection、decision_packet、qa_gap。模板占位须换成实际内容；不适用写理由，不用占位冒充完成。完整格式在[模板](delivery-records-template.json)，程序校验在[工具](tools/delivery_records.py)。

阶段state用独立的delivery_records对象，键为上述四种主记录名，值为{path,sha256}，不放入practice_evidence。记录的scope覆盖本阶段scope。主记录列进阶段artifacts，PM项目还须由本任务实际交回；impact_review引用的影响卡、release_acceptance引用的决定包也列入artifacts，使原人审覆盖它们。这些已校验的文字记录不充当画面、原型的视觉复核对象。其余引用按摘要验证，不复制文字结论。过阶段沿C05，错误会点名缺项或版本。

candidate引用项目实际清单（path、sha256、kind）。清单的files把项目相对文件路径映射到SHA-256；已有发布候选清单直接补此字段，保留其版本、构建等信息。kind为plan或implementation，不互代。阶段封存实际读取的材料；内容寻址的历史证据只核引用，不层层复制。

## 成品影响卡与核心评审

E-2.2按既有技术决定/R03筛查记录product_impact。命中关键技术选择，或默认选择对六类成品结果之一有影响时写卡；纯内部常规决定不逐个扩成卡，在决定索引保留不写卡的理由。索引指向原决策记录，不另造一套决定权。

六类影响：channels运行渠道/形态；interaction画面、交互和手感；data保存、恢复与迁移；capacity_deployment容量、负载与部署；maintenance_cost维护责任与费用；exit_migration退出或更换代价。每类写conclusion、basis、level和evidence。level取measured/prototype/estimate/experience/pending/not_applicable；实测/试做须实际证据，估计和待验证不能写成实测。卡另写default_choice、verification、limitations、reopen_when，不编价格或容量门槛。

E-2.4的impact_review是一张汇总表：每个决定、所选方案、主影响、验证状态，链接卡；表下列“未写卡的决定”及理由。与影响卡绑定同一方案清单，放入原核心评审包一次合看。填卡不改变委托、回升或人审权限。E-3中决定改变，只更新相关卡及既有决定来源；E-4.1再次核对当前来源摘要，防止沿用旧影响说明。

## 验收证据包与人的短体验

QA在Q-3/Q-4维护acceptance_package，引用既有验收覆盖表与检验记录，不另维护一份结论。entries只含条目ID、source、section、inspection引用，禁止复制outcome/status。结果由所引inspection记录给出：item_id、outcome、conclusion、owner、evidence；新结果同时写candidate_sha256。未测/受阻/不适用及失败写reason、next_action。缺陷引用原台账ID、级别与来源，fixed时附与本候选、缺陷ID相符且有实际证据的通过retest；未关闭缺陷仍列入待决。

只有文字或原始日志而无结构化结果的条目，显示tool_unverified；旧检验没绑定本候选摘要，显示evidence_unbound。两者都不算本候选已通过。原证据保留，不补写过去未发生的检验。

QA写trial，研发提供实际入口、环境与数据重置方法。列author、entry、environment、reset、limitations和steps；每步都有action、expected、unacceptable。试用10–15分钟是设计目标，可分段，不是保证。团队中trial.author须等于验收包实际交回者；实现者不能冒充独立QA；没有QA走原缺口机制。人的真实观察仍存原E-3.3或E-4.2审阅记录，不为了本包再请人确认一次。

core_tasks把已有核心任务连到验收条目：入口→主要动作→状态/持久化→异常/恢复→观察证据。不适用项写理由。这是当前候选的证据链，不是另做一轮可运行切片；小项目首增量可能已经覆盖。各模块分别通过不能代替实际贯通证据。质量与体验是否达标仍由实际检验判断。

## 发布决定衔接

E-4.1的release_acceptance引用当前implementation候选、Q-4包与其真实完成回执qa_completion（bundle、state_path）、当前product_impact及原发布决定包的结构化索引decision_packet。Q-4回执须经关卡真实封存，包路径和摘要须一致；团队还核已完成质量任务的可信交回及实际QA作者，不能自写stage字段冒充。决定包用decision_packet/1，必须完整列unresolved_items（未测、受阻、失败、未绑定或工具未核结果），以及unverified_impacts（估计、经验或待验证的决定ID:影响类别）。E-4.2沿原发布决定处理这些事项，不能以“直接上线”抹掉。

缺QA时引用已有有效qa_gap处置选择和实际available_evidence，带non_specialist_label；该选择原样引用，不再列为待决或重复请选。缺独立QA的证据限制、未测项、缺陷及是否带风险发布，仍交E-4.2原发布决定处理。decision_packet中的qa_gap与unresolved_items里的qa_gap保留为缺QA残余风险索引，不表示处置选择尚未决定，不伪造Q-4通过。团队下qa_gap须对应任务库中当前质量缺口；有在任QA则走其验收。单对话保留真实决定来源、完整原话及限制，工具不认证人的身份。

校验只核结构、引用、摘要、覆盖及版本，不判断观察是否真实具体，不会发现作者漏登的决定，也不把“没有未测项”直接判为体验合格。有未测项可以如实成稿并交既有门槛处理；Q0/Q1等原发布限制不变。
