# 议题

何时读：登记或处理跨专业多轮议题。调用前置与其余操作见[原入口](ledger.md)。

## 议题

规则见 C25。`id` 为议题 ID，幂等同请求。

- `topic_open`（actor 为发起方）：`topic={id,kind,cause:{item,version},purpose,participants:[{id,tier}],decider,visibility:{affected_owners,confidential},max_rounds,deadline}`。kind：consult/handle/review/discuss/notify；tier：internal（已登记，含发起方）或 external（只记录）；decider：角色或 `human:{人员 ID}`；max_rounds 缺省 3（1–10）；deadline 为 ISO 日期。
- `topic_note`（内部参与方，open 时）：`note={id,summary,references:[{path,sha256}]}`，summary ≤500 字，sha256 可省（自动记录）。发起方每条开一轮，他人本轮回复；超轮数或过期限被拒。
- `topic_conclude`（决定方；人决定由发起方附 quote 记录）：`conclusion={text,effect,applies_to,lands_in:{path,version},plan_impact,promote:{id,text,scope}}`。effect：binding/advice/decision/disagreement；专业 decisions.binding 为空的角色不能给 binding。
- `topic_adopt`（受影响责任方）：`adoption={outcome,…}`：satisfied 写 how；risk_accepted 限 binding，写 person、quote；declined 限 advice，写 reason。
- `topic_escalate`（发起方或决定方）：to（owner/change/human）、summary，转 escalated，仍可结论。
- `topic_close`（发起方）：需结论，binding、advice 需各受影响责任方采用；escalated 可直接关闭。
- `topics`：内部参与方、决定方见全部；他人（含 PM）只见头信息，非保密议题的受影响责任方另见结论与 lands_in。这是工具按 actor 过滤，不是加密。
- `request` 可带 open 议题的 `topic`，请求方须是参与方。
