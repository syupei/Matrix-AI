# 结构化交付与自动核对

何时读：S6/S7 整理交付范围；下游接收基线；基线变更回查；声明完成前。工具把引用、覆盖与证据要求变成可运行检查，只检查已登记的范围。参考来源：[ProductSpec](https://github.com/gokulrajaram/ProductSpec/blob/main/SPEC.md)；本格式 `product-contract/0.1` 不兼容 `.product-spec.md`。

## 登记

- 正文留在原 Markdown，每个源文件只加一个 `product-contract` JSON 代码块，登记已有条目的 ID、标题、引用、接收者和验证阶段，不复写正文。S6 首次只为当前授权的交付范围登记需要追溯的条目，之后随正文维护。标注和快照不产生批准；未登记的内容不能说已被检查，也不能靠删登记项消除有效要求。
- 条目地址是"项目相对路径#ID"（如 `product/specs/01-产品模型.md#R-1`），不是网页锚点；不同文件同 ID 不冲突，搬移文件要改引用。`heading` 须是独占一行的 ATX 标题，与文中标题完全相同且唯一，范围截到下一个同级或更高级标题。

示例（假设位于 `product/01-产品定义.md`）：

```product-contract
{"format": "product-contract/0.1", "revision": "v1", "items": [
 {"id": "R-1", "kind": "requirement", "heading": "## 留言发布规则", "audiences": ["design", "qa"]},
 {"id": "AC-1", "kind": "acceptance", "heading": "## 发布验收", "refs": ["product/01-产品定义.md#R-1"], "verify_at": "implementation"}]}
```

- `revision`：该文件正文的修订号，不是 skill 版本。`id` 不含空白、`#`、斜杠。
- `kind`：`context` 背景与假设；`requirement` 要求；`acceptance` 交付判据；`outcome` 上线效果。
- `refs`：本次来源内的条目地址；验收用直接 refs 指向所覆盖的要求，间接关联不算覆盖。
- `audiences`：可选接收角色，省略表示全部；阅读稿会补入引用依赖。
- `verify_at`：acceptance 必填 product/design/implementation；outcome 固定 post_launch。
- `coverage`：requirement 默认 required，须有直接关联的验收；确不适用填 not_applicable 并写 `reason`。

数量、时间窗缺依据就记未知，不为通过检查编数字；决策性质与确认状态仍由正文和记录表达。

## 命令

Python 3.10+，无额外依赖，在项目根目录运行。`S` 指本 skill 的 `scripts/product_contract.py`（通常在 `.agents/skills/product-agent/scripts/`）。

```sh
python3 $S --root . capture --source product/01-产品定义.md --output product/baselines/v1.json  # 可多次 --source
python3 $S --root . check --baseline product/baselines/v1.json --stage product  # 可加 --json
python3 $S --root . draft --baseline product/baselines/v1.json --output product/checks/v1.json
python3 $S --root . check --baseline product/baselines/v1.json --stage product --receipt product/checks/v1.json --output product/checks/v1-report.md
python3 $S --root . handoff --baseline product/baselines/v1.json --role design --output product/handoffs/design-v1.md
```

- 退出码 0：未发现机械阻断；1：有待处理项；2：输入或格式错误、检查未完成（不是通过）。check 默认只读，给 `--output` 才写；输出不覆盖已有文件。脚本不联网，不改正文、任务状态或人审记录。
- capture 记录来源路径、声明版本、文件哈希与条目指纹；引用缺失或要求缺验收时拒绝生成。候选快照可供人审，原人审或委托依据成立后才能作正式基线引用。
- handoff 生成只读阅读稿；正式交接仍引用原确认、专业评审、未决问题和 `03-交付说明.md`，稿中文字仍按 COPY-QUALITY 复核。

## 核验记录

- draft 生成的记录初始全为 not_checked，由当次核验方填写；引用已有核验前先核对其输入版本与证据。`baseline_sha256` 绑定具体快照，不改哈希让旧记录通过；`checker`、`checked_at`（ISO 时间）、`stage` 写实际情况。
- 每条 result 的 status 为 passed/failed/not_checked，附 method 与必要 note。可用方法：product 含 reasoning 等；design 为 tool_readback/prototype/user_test；implementation 为 implementation/user_test；post_launch 为 measurement/user_test。方法名须有真实工作支撑。
- passed 至少一项 evidence `{"path": "项目相对文件", "sha256": "实际哈希"}`，可指向原专业报告；外部原型链接附在回读记录里，单独 URL 不算核验；哈希一致不证明证据充分。不用需求原文、空报告或无关测试充当证据。
- 当前阶段应核验而未通过的报待处理，后续阶段的显示待承接；上线效果未观察不阻断交付，已知失败不因阶段靠后而隐瞒。

## 变更与边界

- 正文改了而版本没改也报 `stale_source`；条目增删、引用或验证阶段变化同样检查。报告给出直接变化和沿引用推导的回查范围，行号移动不算语义变更；文件级失配不代表所有确认失效，只回查受影响内容。
- 完成影响处理后才生成新快照，旧快照与证据保留；沿用未受影响的核验要记录依据。handoff 拒绝从旧快照拼接新正文。
- 工具不理解语义、不判断假设或文风、发现不了未登记的要求、不验证外部证据、不调度任务、不批准产品。
