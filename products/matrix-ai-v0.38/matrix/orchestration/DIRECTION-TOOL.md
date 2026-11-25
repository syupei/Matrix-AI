# 方向任务登记与接续

何时读：PM 调用方向工具登记 P-1、补齐专业缺口或绑定合看答复。分工与一次合看见[方向样张](DIRECTION-SAMPLE.md)，调用入口见[任务工具](TASK-TOOL.md)。

## 建立方向任务

`direction_sample`：`id,profile,brief,admitted_inputs,person,combined_review_authorization,assigned`。brief 是真实已澄清简报，admitted_inputs 绑定它的当前准入版本；安装规则不能充当业务简报。profile 是显示名称，可用 `example: "board-race"` 采用完整范例，不按该名字触发后段义务。

assigned 按已在岗专业填 master，可留缺项；另填独立的 fit_checker、task_checker。检验者与制作人分开；task_checker 也不能是创建任务的 PM，PM 负责采用检验和关闭任务。缺少合格 task_checker 时先补配置。任务、输出路径和 missing_roles/pending_contributions 取返回记录。downstream 可列 PM 已登记但未开工的任务，工具为其绑定里程碑依赖。

## 补齐已有专业缺口

按[专业缺口](TASK-GAPS.md)记录人的选择与真实成果。`direction_resolve_gap` 由 PM 调用，传 `id,role,gap`，用 `task_id` 引用同缺口下已检验关闭的交付任务；人工或外部专家的已关闭缺口也可用 `admitted_inputs` 引用已采用的成果。它们须覆盖该专业的原定输出，不能仅写“已解决”。self 产出保留非专业标注。需补派合成任务时用 `assignee` 指明承担缺口工作的已登记实例，不能虚构 master。

工具保存缺口版本与成果摘要，再补派已具备输入的合成/贴合工作。缺口未决定、未交回、成果过期或未准入时维持阻碍。fit_checker 的人工替代沿同一次 P-1 合看，由该答复及真实贴合记录证明，不能自填独立检验人。

## 展示、答复和重新审阅

用 human_attention 登记 `id,kind,display,task_id,scope`；scope 是展示范围描述，工具另冻结全部活动 ID 为 receipt.scope，与 P-1 request.scope 数组一致。答复用同 id 登记 response，可附真实稳定 response_id。human_review 引用 attention_id、同一材料/展示范围、完整原话；回执写入该已答复记录，供关卡核对来源。

方向改变后重新展示，用新的真实答复；里程碑已关闭则按既有返工程序重开。新批准替换当前绑定，旧批准留在 confirmation_history。同一答复不能为新材料重绑。最终契约依[共同模板](../base/tone-contract-template.md)引用这次回执；里程碑实际关闭后供后段使用。无图时工具可返回待看稿及 direction_reference，但不会返回成功 delivery；人的实际看稿仍并入已有一次合看。
