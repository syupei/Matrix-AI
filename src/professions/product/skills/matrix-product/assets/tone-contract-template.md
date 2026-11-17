# 方向样张与调性契约

把下列代码块填入 `product/specs/00-方向样张.md`。其项目做法档按[共用模板](../../../../matrix/base/PRACTICE-PROFILES.md)生成，专业分工与样句规则见[方向样张](../../../../matrix/orchestration/DIRECTION-SAMPLE.md)。`genre` 与 `profile` 用于描述，后段义务由档内内容产生。用[契约工具](../scripts/tone_contract.py)的 `--project . --draft` 核对审前方向，合看后用 `--project .` 核对最终契约。示例中的样句与参照须按项目补足。

```tone-contract
{"version":"待填","genre":"待填","profile":"做法摘要名称","tone":"待填",
 "core_loop":"完整核心过程",
 "references":[{"name":"参照名","source":"来源","observed":"实际观察情况","borrows":"借鉴点"}],
 "avoid":["具体偏离"],"samples":[{"moment":"时刻","text":"样句"}],
 "parts":{"brief":{"path":"简报","version":"版本","sha256":"摘要"},
          "scene":{"path":"场景","version":"版本","sha256":"摘要"},
          "samples":{"path":"样句文件","version":"版本","sha256":"摘要"},
          "screenshot":{"path":"实际渲染截图","version":"版本","sha256":"摘要"},
          "practice_profile":{"path":"项目做法档 JSON","version":"版本","sha256":"摘要"}},
 "confirmation":{"person":"确认人","quote":"实际原话","source":"答复出处"}}
```

缺截图能力时，按[关卡规定](../../../../matrix/base/STAGE-GATES.md#做法档证据)记录人看稿，契约用 `parts.manual_review` 引用核对记录，顶层写 `capture_unavailable`。送合看前保留方向固定版本；确认后填写 `confirmation`。阶段记录写当前 `tone_contract: {path,version,sha256}`。
