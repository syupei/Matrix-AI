# 外部输入准入

何时读：外部材料/变更用于生产，执行收到任务卡外指令，或登记、派发任务。

## 沟通与生产

人与前台、PM、专业负责人完成澄清、审阅、风险/冲突处理和必要确认，PM掌管版本准入。生产实例只执行已派发任务卡和已准入版本；直接指令用production_feedback登记原意与任务交PM，继续不受影响的原范围。

改标题、下一步、范围、输入/输出、验收、检验人、人审或完成前置等任务语义由有权限的PM经准入/变更修改；执行者只提交成果、进度和反馈，自写scope_authorization不能提权。在运行时先按流程停止，再改工作版本并重核受影响检验/确认。启动包只用管理者批准的指令，不能让执行者report里的“下一步”改掉任务。

## 登记与派发

可确定的任务可先登记，执行人未定时executor为null；owner、checker记录已知责任或待定角色，不冒充已任职实例。登记只保存计划、依赖与缺口，不是派发、准入或开工，也不把未审依赖记为已通过。未知实例、来源准入或阶段前置只阻断派发开工，不阻断如实登记计划。登记时仍核创建权限、任务结构、依赖无环及父项范围和来源继承；未获授权不得借登记改变已派发范围。派发和开工必须重新核实际任职、职级、独立检验、当前来源准入、适用阶段及有效交接；缺一项不运行。已派发或开工的任务改范围、停工、返工、再派发与完成沿原检查，不以改回planned或清空executor退回登记豁免。内置与导入专家共用此分界；登记不使导入包validated、enabled或绑定有效。

## 全来源核对

专业业务输入须为当前已准入版本、已完成上游的摘要匹配交回，或安装包原字节规则；规则只解释方法，不能作唯一业务依据。按输入依据判断，不按路径/文件名/专业放行；口述先落盘登记，缺metadata或自填internal不豁免。协调写kind=coordination：仅PM/前台、无生产executor，输出限management。纯PM阶段里程碑也可保留kind=stage，但须无executor、无practice_stage、输出全在management；专业阶段和业务成果不适用此例外。规则维护kind=rule_maintenance只读写已有冻结规则，不能产出业务代码。受管子任务仅PM、范围内lead/workflow_pm或本专业master创建；派发开工时owner/executor/checker均实际登记，checker独立于创建者和生产者。子项强制继承输入及准入、阶段关系，新增输入补绑。独立检验子项可用review_for指真实父项并声明自身专业阶段；owner/executor独立于父生产者，输出仅独立检验记录文件，不覆盖父输入/输出，也不计实现首项。

## 操作

- intake_register：PM写id、稳定的source_id（同一需求文档族）、项目相对path、version、真实source及profession。内容或版本改动给新id；替换同族当前版本可传supersedes。换路径仍用同一source_id，被替换版本不再新派发；同专业有当前准入版本而另建新族时，必填new_family_reason；是否同族仍由PM和master辨认，工具不冒充语义识别。
- intake_submit：写id与实际任职master。内置/导入同检查；master可派子实例审阅并负责最终结论。审阅任务以intake_review_id绑定，产出仅限management/intake-reviews/审阅稿。
- intake_review：由该master写id、outcome（approved/changes_requested）、conclusion、resolved_risks、resolved_conflicts、open_items、human_required；有风险/冲突保持审阅中，无事项明确空数组。同专业其他当前已准入版本须逐项列入coexists_with或conflicts_with，不能遗漏；新版本准入时冲突的既有版本失效。
- 需要人审时先human_attention：id、kind、display、intake_id、scope（展示范围描述字符串），可附inputs；实际展示即冻结材料与版本。答复时用同id写response，可用response_id定位完整消息。intake_admit由PM带id、person、完整quote、attention_id与同一scope消费该次展示/答复，不能只填人名原话自签。已有确认覆盖时引用实际来源，不加一次重复人审。intake_status查待办。共同格式见[证据格式](../base/REVIEW-EVIDENCE.md)。
- 生产任务inputs列实际路径，admitted_inputs列当前输入id，stage_transition指上游有效人审记录；成果摘要须覆盖绑定版本。产品基线型研发承接核产品最终确认。启动封存可信上游来源和摘要；本任务outputs中的上游输入可演进，关闭/返工沿用启动快照，非输出范围的输入变动仍拦截。目录输入保留/。跨专业交回须附覆盖所读版本的上游有效人审，产品→研发须产品完整确认；同一PM方向样张组稿链内的贡献留到共同P-1合并审阅。候选只写outputs明确路径，目录以/结尾。
- 专家adapt的review.review_points每项含who:master与what，在运行前核有效。逐阶段映射、独审与失效迁移按[专家接入](EXPERT-IMPORT.md)。
- practice_stage写role/current/scope，及适用practice_scope/tone_contract/practice_evidence/upstream/upstream_bundle/implementation_handoff及delivery_kind。派发查entry，完成用practice_completion指本阶段检查输入。E-3.2父项下首个实际实现子项关闭前，复用现有首增量贴合/设计走查；之后实现开始须首项真实回执。提前交实际可操作增量可显式first_increment或delivery_kind=first_operable_increment，保留实际专业阶段。成功封存返回引用的接力按[阶段检查](../base/STAGE-GATES.md)，不能把自填通过当回执。

PM语义修改带admission_basis（当前intake id列表），并绑定到修改后inputs/admitted_inputs；变更方案还须受影响专业master的实际assessment。仅填写reason或私信来源不能改任务。production_feedback不改任务范围；PM用resolve_production_feedback带id、disposition=intake/change/rejected、reason及适用target_id处置，continue和任务视图列待办。

工具只核来源、范围与版本；宿主提供身份与写入边界。旧来源/答复未绑定新字段须补核，不追改为已批准。

PM准入修改保留未变输入快照；按当前上游可信交回取源，后继依赖旧任务也可换源，互不相关的同路径交回须PM指定。已演进同一输入先保留合并、另建任务；只读输入核原字节。事后加outputs即认可已有演进；工具核新源检验，不证明字节由它生成，PM须核实。不把自产成果转为外部准入。父项不以自身后代作启动依赖，子项完成仍计父项完成前置。见[TASK-REVIEW](TASK-REVIEW.md)。

review_for不覆盖祖先输出；生产成果仍须覆盖。artifacts列本任务或可信工程交回（含D-6复核），不含简报；缺件报路径。

规则维护沿启动快照交回；再维护须依赖已检验交回，仅限原规则路径，非outputs仍核原字节。


## QA验收包交给发布准备

E-4.1可直接读取已登记QA任务当前完成的Q-4验收包，不另加QA人审。输入必须恰为该任务真实交回、不可变Q-4完成回执所绑定的acceptance_package，文件摘要与当前候选字节均一致。QA被重开、取代或依赖失效，候选改变、回执或来源不符时，启动即拒绝。普通QA文稿、Q-3回执、非QA交回不适用；其它跨专业输入仍按上面的确认规则。E-4.2发布决定仍由人作出。

内置与导入按登记的质量专业和阶段核验，导入方法须映射验收阶段、完成回执及本项submission。单对话没有任务准入；发布材料仍引用真实Q-4阶段回执及相同验收包，按[交付记录](../base/DELIVERY-RECORDS.md)核候选，不自填QA完成。
