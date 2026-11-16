# 按行动人生成收件人草案

即使只有本轮口述，也可按已知事项和职责编制草案；临时编号与角色称呼可用，正式地址留待核实。合批前列 JSON 数组。每项填非空 `id`、`title` 与布尔值 `action`。需行动时填 `recipient` 和所挡任务 `blocked`；仅知悉或可试用时填 `action: false`。

运行 `python3 matrix/orchestration/tools/notification_plan.py <事项文件>`。只对 `direct_actions` 的行动人点名，同一人合并、阻断事项优先；`group_summary` 放群摘要，`pending_recipient` 先核实。工具只生成草案。展示时按阻断待办与非阻断摘要列出，并保留谁需回复、卡住什么。
