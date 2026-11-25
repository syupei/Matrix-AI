# 核验记录

何时读：记录交付核验或处理变化。调用前置与其余操作见[原入口](structured-handoff.md)。

## 核验记录

- draft 生成的记录初始全为 not_checked，由当次核验方填写；引用已有核验前先核对其输入版本与证据。`baseline_sha256` 绑定具体快照，不改哈希让旧记录通过；`checker`、`checked_at`（ISO 时间）、`stage` 写实际情况。
- 每条 result 的 status 为 passed/failed/not_checked，附 method 与必要 note。可用方法：product 含 reasoning 等；design 为 tool_readback/prototype/user_test；implementation 为 implementation/user_test；post_launch 为 measurement/user_test。方法名须有真实工作支撑。
- passed 至少一项 evidence `{"path": "项目相对文件", "sha256": "实际哈希"}`，可指向原专业报告；外部原型链接附在回读记录里，单独 URL 不算核验；哈希一致不证明证据充分。不用需求原文、空报告或无关测试充当证据。
- 当前阶段应核验而未通过的报待处理，后续阶段的显示待承接；上线效果未观察不阻断交付，已知失败不因阶段靠后而隐瞒。

## 变更与边界

- 正文改了而版本没改也报 `stale_source`；条目增删、引用或验证阶段变化同样检查。报告给出直接变化和沿引用推导的回查范围，行号移动不算语义变更；文件级失配不代表所有确认失效，只回查受影响内容。
- 完成影响处理后才生成新快照，旧快照与证据保留；沿用未受影响的核验要记录依据。handoff 拒绝从旧快照拼接新正文。
- 工具不理解语义、不判断假设或文风、发现不了未登记的要求、不验证外部证据、不调度任务、不批准产品。
