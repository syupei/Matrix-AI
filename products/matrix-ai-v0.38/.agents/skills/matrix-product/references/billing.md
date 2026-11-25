# 可校验的计费规则

涉及价格、扣费、退款或自动续费时用此格式。按专业风险表标 F1 或交人判定 F0；先运行校验器的 `--notice`，把它生成的「给决定人的风险告知」放在回复阶段行后的第一段，再列草案及待定项。生成的告知是当前回复的一部分。首次口述是规则输入。首次写出的候选一律标 draft，汇报用「按你提供的规则起草；本版待确认」。仅在有权决定者明确回应已经展示的对应版本后，才登记 approved 或报告「已确认」。

口述里有试用到期扣费、周期自动续费和当期取消不退款时，分别登记 charge、auto_renew、refund 三条。即使退款金额为零，也保留 refund 条目，缺口写入 pending。校验时按口述识别的类型逐个传 --require-kind，例如 `--require-kind charge --require-kind auto_renew --require-kind refund`。

将规则候选放在 `product/billing-rules.json`，正式规则引用同一份来源。根对象含 `schema: "matrix-billing/1"` 和非空的 `rules` 数组。

| 每条规则字段 | 写法 |
| --- | --- |
| id、kind | 唯一编号；kind 取下表之一，涉及多类则分别登记 |
| source、status、risk | 可定位的输入来源；draft 或 approved；F0 或 F1 |
| terms、pending | 都是对象。每个规定条款在 terms 写已有明确的内容，或在 pending 写待核实的问题。没有给出的金额、币种、退款期限和流程保留待定 |
| financial_impact、compliance_questions、notify | 金钱影响、须核实的合规事项、本次有权审阅的决定人或职责 |
| review、checks | review 对象含 owner、method；checks 是非空数组，每项含 scenario 和 expected |
| approval | approved 时填写 person、quote、version，请用真实决定人、确认原话及其对应内容版本 |

| kind | 必须逐项填写或列为待定的条款键（值为非空字符串） |
| --- | --- |
| pricing | amount 金额、currency 币种、unit 计价单位、eligibility 适用条件 |
| charge | amount、currency、trigger 扣费时机、duplicate_handling 重复请求、unknown_result 扣费结果未知时的处理 |
| refund | eligibility、amount_rule 金额规则、deadline 期限、destination_or_exception 退款去向或例外 |
| auto_renew | trial 试用条件、interval 周期、amount、currency、notice 告知方式、cancel_effect 取消后何时停止及当期影响 |

运行 `python3 .agents/skills/matrix-product/scripts/billing_check.py product/billing-rules.json`。技能装在其他位置时替换成实际路径。准备回复时加 `--notice`（与类别参数同时传）；正式研发交接前另外加 `--handoff`。校验报错时按字段路径修正或登记待核实项。格式通过只证明字段完整；PM 和产品负责人仍按共同规则核实授权、证据及检验结果。检查覆盖相关的试用转扣费、取消边界、退款金额和重复扣费情境，未执行的测试标为计划。
