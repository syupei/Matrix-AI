# 结构化交付与自动核对 0.1

S6/S7、下游接收基线、变更回查及完成声明前使用。它把既有引用、覆盖与证据要求落实为可运行检查，不改变七阶段、五类成果、人审或专业判断。工具仅检查明确登记的范围；遗漏登记的业务规则及语义质量仍需专业审读。

借鉴 ProductSpec 的稳定条目、版本绑定、验收/效果区分、派生交接和证据核对机制；参考 [规范](https://github.com/gokulrajaram/ProductSpec/blob/main/SPEC.md)、[Agent Handoff](https://github.com/gokulrajaram/ProductSpec/blob/main/docs/agent-handoff.md)、[Agent Run](https://github.com/gokulrajaram/ProductSpec/blob/main/docs/agent-run.md)。本实现为本项目的 `product-contract/0.1`，未复制其实现，也不宣称兼容 `.product-spec.md`、提供 ProductSpec MCP 或安装其工具。兼容导出可后续另行扩展。

## 唯一有效源与接入时机

正文继续放在现有 Markdown 中。元数据只登记原条目 ID、所在标题、引用、接收者及验证阶段，不重复写一份规则正文。首次在 S6 整理当前交付范围；后续随正文维护。同一文件仅有一个 `product-contract` JSON 代码块，可放在文末；多个条目可以共用一节，小项目不要求拆文件。只有实际需要追溯的条目才登记，不为凑数量重编号。

工具以“项目相对文件路径#原 ID”作为引用，例如 `product/specs/01-产品模型.md#R-1`。这是条目地址，不是浏览器标题锚点。不同文件的相同 ID 不冲突；文件搬移需要修正引用并保留迁移依据。标题需使用独占一行的 ATX 标题（`## 标题` 等），与 metadata 完全相同且在该文件唯一；截取到下一个同级或更高级标题，代码示例中的标题不算。引用某节即涵盖其下级内容。

旧项目沿用已有正文、确认和历史，从当前授权的交付/回查范围补最小标注，不重做访谈。标注与快照本身不会继承或生成批准。未登记的文件可作为原交付说明中的阅读资料，但不能说工具已检查它们；不能通过删登记项消除仍有效的要求。

## 源文档示例

以下内容仅演示格式，不是任何实际留言板的需求。

````markdown
# 产品定义

## 留言发布规则
用户提交后，应保留提交内容，并明确告知提交结果。

## 发布验收
在允许提交的条件下成功提交后，可以读取刚才的内容；失败不显示成功。

## 使用效果
观察留言是否获得有效回应。目标值与观察窗口须有依据；当前未知时保留待确定及解除条件。

```product-contract
{
  "format": "product-contract/0.1",
  "revision": "v1",
  "items": [
    {"id": "R-1", "kind": "requirement", "heading": "## 留言发布规则", "audiences": ["design", "engineering", "qa"]},
    {"id": "AC-1", "kind": "acceptance", "heading": "## 发布验收", "refs": ["product/01-产品定义.md#R-1"], "verify_at": "implementation"},
    {"id": "SM-1", "kind": "outcome", "heading": "## 使用效果", "verify_at": "post_launch"}
  ]
}
```
````

示例引用以其文件位于 `product/01-产品定义.md` 为前提，实际使用必须换成真实路径。

| 字段 | 含义 |
| --- | --- |
| format / revision | 固定格式版本；本文件真实正文修订，非 skill 版本 |
| id / heading | 已有 ID 与准确标题；id 不含空白、`#`、斜杠 |
| kind | `context` 背景/目标/假设/阅读说明；`requirement` 要求；`acceptance` 交付判据；`outcome` 上线效果 |
| refs | 当前交付来源内的条目地址；可多对多。验收用直接 refs 指向它覆盖的要求；间接关联不冒充覆盖 |
| audiences | 可选接收角色列表；省略或空列表表示所有接收者。阅读稿会补入所选条目的引用依赖 |
| verify_at | acceptance 必填 product/design/implementation；outcome 固定 post_launch；其它类型不需要 |
| coverage / reason | requirement 默认 required，必须有关联验收；确实不适用时填 not_applicable 并写 reason，理由仍需专业审查 |

正文中的目标、可检验假设与成功判断继续使用原位置；交付判据与上线效果分开。数量和时间窗缺依据就记录未知，不为了格式或检查通过编造数字。原有固定约束、建议、委托设计、待澄清及确认状态仍由原正文/记录表达，这四个 kind 不替代它们。

## 工具使用

使用 Python 3.10+，无额外依赖。以下命令在目标项目根目录运行，路径均需换成真实项目文件。脚本位于本 skill 的 [scripts/product_contract.py](../scripts/product_contract.py)。

```sh
# 登记本次交付涉及的全部有效源；每个源均有上述元数据。可多次传 --source。
python3 .agents/skills/product-agent/scripts/product_contract.py --root . capture \
  --source product/01-产品定义.md --output product/baselines/candidate-v1.json

# 产品阶段核对；尚未发生的设计/实现验证列为后续事项。
python3 .agents/skills/product-agent/scripts/product_contract.py --root . check \
  --baseline product/baselines/candidate-v1.json --stage product

# 为真实核验准备记录草稿；初始均为 not_checked，不预填通过。
python3 .agents/skills/product-agent/scripts/product_contract.py --root . draft \
  --baseline product/baselines/candidate-v1.json --output product/checks/review-v1.json

# 实际核验后填记录，再按本次任务阶段检查。
python3 .agents/skills/product-agent/scripts/product_contract.py --root . check \
  --baseline product/baselines/candidate-v1.json --stage product \
  --receipt product/checks/review-v1.json --output product/checks/report-v1.md

# 从相同有效源生成角色阅读稿。不是另一个可修改的 PRD。
python3 .agents/skills/product-agent/scripts/product_contract.py --root . handoff \
  --baseline product/baselines/candidate-v1.json --role design \
  --output product/handoffs/design-v1.md
```

`check --json` 输出结构化报告。退出码 0 仅表示未发现机械阻断项；1 表示发现应处理项；2 表示输入/格式错误或检查未能完成。不能把 2 当成检查通过。check 默认只读；给出 --output 才写报告，所有输出拒绝覆盖已存在文件。脚本不联网、不修改业务正文、不改变任务状态或人审记录。

capture 生成来源路径/声明版本/全文件哈希及条目指纹，不复制正文。引用缺失、要求缺验收等结构问题会拒绝生成候选。候选可供人审；只有原人审/委托依据和专业条件成立后，才能将它引用为正式交付基线。基线文件的存在不是确认凭据。

S7 的正式交接仍引用原确认、专业审阅、未决问题和 `03-交付说明.md` 中的任务/边界；生成阅读稿只是附加视图。按 [全量文案规则](../../../../collaboration/COPY-QUALITY.md) 复核实际文字；从有效成稿提取不免除表达责任。

## 核验记录及证据

draft 生成的 JSON 是执行事实记录，不是产品正文副本。由当次核验责任方在自己的维护位置填写；已有核验依据先引用，避免多个角色同时改一份记录。工具当前每次接收一份本次汇总记录；若需承接此前核验，核对其输入版本、实际证据与适用范围后引用，不重新伪造执行。证据路径可以指向原专业报告。

- `baseline` 与 `baseline_sha256` 绑定具体交付快照，不能盲目改哈希使旧记录通过。
- `checker`、`checked_at`、`stage` 记录实际核验者、ISO 时间和阶段。
- 每条 result 引用实际条目，status 为 passed / failed / not_checked，注明 method 和必要 note。
- product 允许 reasoning 等实际方法；design 需要 tool_readback / prototype / user_test；implementation 需要 implementation / user_test；post_launch 需要 measurement / user_test。方法名只是声明，记录必须有真实工作支撑。
- passed 的 evidence 至少一项 `{ "path": "项目相对文件", "sha256": "实际文件SHA256" }`。外部原型/设计链接附在实际回读记录中，或作为 evidence 的 url 补充；单独 URL 不算已核验。本地文件存在且哈希相同，也不能自动证明证据内容真实充分。

需要获得真实证据哈希时可用本地文件哈希工具。不能拿需求原文、空报告或无关测试凑证据；正文审批、Agent 推演、工具回读、实现实测、真实用户研究分别记录。

当前阶段已到期的核验项未通过会报待处理；后续阶段项显示待承接，保持信息可见。上线效果未观察不阻断产品/实现交付；已知失败不能因其阶段较晚而隐瞒。

## 变更与边界

正文改动但未升版本也会触发 stale_source；条目新增/删除、引用或验证阶段变化同样检查。报告给出直接变化和沿已登记引用推导的关联回查范围；移动行号不会单独判成语义变更。文件级快照失配不表示所有人的确认失效：由责任方核对实际变化，只回查受影响内容，保留其余确认。

只有完成影响处理后才生成新快照；旧快照与证据保留。需要重新关联未受影响的核验时记录采用依据，不能只更新指纹。handoff 拒绝从旧快照拼接新正文。

工具不自动理解正文语义、判定假设合理、判断文风、检测所有未登记要求、验证外部证据或认证检查者；它也不调度任务、收集上线指标或批准产品。完整性与专业质量仍是产品/设计等责任方的工作。
