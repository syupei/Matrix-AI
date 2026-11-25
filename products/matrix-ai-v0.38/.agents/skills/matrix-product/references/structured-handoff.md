# 结构化交付与自动核对

何时读：P-6/7 整理交付范围；下游接收基线；基线变更回查；声明完成前。工具把引用、覆盖与证据要求变成可运行检查，只检查已登记的范围。参考来源：[ProductSpec](https://github.com/gokulrajaram/ProductSpec/blob/main/SPEC.md)；本格式 `product-contract/0.1` 不兼容 `.product-spec.md`。

## 登记

- 正文留在原 Markdown，每个源文件只加一个 `product-contract` JSON 代码块，登记已有条目的 ID、标题、引用、接收者和验证阶段，不复写正文。P-6 首次只为当前授权的交付范围登记需要追溯的条目，之后随正文维护。标注和快照不产生批准；未登记的内容不能说已被检查，也不能靠删登记项消除有效要求。
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
- `exits`：requirement 可选，要哪些专业各交什么：专业标识列表，或 `{专业标识: 交什么}`；项目有 `matrix/professions/` 时须是已登记的专业。快照与阅读稿保留它，PM 照它登记交付集合的出口。

数量、时间窗缺依据就记未知，不为通过检查编数字；决策性质与确认状态仍由正文和记录表达。

## 命令

Python 3.10+，无额外依赖，在项目根目录运行。`S` 指本 skill 的 `scripts/product_contract.py`（通常在 `.agents/skills/matrix-product/scripts/`）。

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

记录交付核验或处理变化时，读取[具体说明](handoff-check-results.md)。

## 变更与边界

记录交付核验或处理变化时，读取[具体说明](handoff-check-results.md)。
