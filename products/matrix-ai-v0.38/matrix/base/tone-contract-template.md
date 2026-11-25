# 方向样张与调性契约

P-1草稿可先放 `product/specs/方向样张草稿.md`；确认后定稿到 `product/specs/00-方向样张.md`。做法档按[共用模板](PRACTICE-PROFILES.md)，分工/样句按[方向样张](../orchestration/DIRECTION-SAMPLE.md)。genre/profile只是描述，后段义务由档内特征产生。

```tone-contract
{"version":"待填","genre":"待填","profile":"做法摘要名称","tone":"待填",
 "core_loop":"完整核心过程","viewport":"1280x800",
 "references":[{"name":"参照名","source":"来源","observed":"实际观察情况","borrows":"借鉴点"}],
 "avoid":["具体偏离"],"samples":[{"moment":"时刻","text":"样句","consequence":"规则、状态变化或下一动作"}],
 "parts":{"brief":{"path":"简报","version":"版本","sha256":"摘要"},
          "scene":{"path":"场景","version":"版本","sha256":"摘要"},
          "preview":{"path":"实际HTML或SVG预览","version":"版本","sha256":"摘要"},
          "samples":{"path":"样句文件","version":"版本","sha256":"摘要"},
          "screenshot":{"path":"实际PNG截图","version":"版本","sha256":"摘要"},
          "practice_profile":{"path":"项目做法档JSON","version":"版本","sha256":"摘要"}},
 "capture_binding":{"artifacts":[{"path":"与preview相同路径","sha256":"与preview相同摘要"}],
                    "pixel_size":[1280,800],"viewport":"1280x800","scale":1,
                    "method":"实际采集方式","state":"代表状态","source":"实际来源",
                    "receipt":{"path":"采集记录JSON","sha256":"摘要"}},
 "confirmation":{"person":"确认人","quote":"真实完整答复","source":"答复来源路径",
                 "direction_sha256":"审前工具返回的方向摘要",
                 "review_receipt":{"path":"绑定展示与答复的manifest","sha256":"摘要"}}}
```

示例按项目补足2–3个实际参照及足量样句。viewport按实际目标；PNG像素及scale必须一致。capture_binding/receipt与无图人工回退统一见[证据格式](REVIEW-EVIDENCE.md)，不靠改写摘要把旧图冒新采集。无图时保留parts.manual_review与capture_unavailable；人工看稿只用既有确认的review_receipt，不自行制造顶层回执。

审前省略confirmation，运行[契约工具](tools/tone_contract.py) `--project . --contract product/specs/方向样张草稿.md --draft`；回复取成功delivery的真实成果链接并标待确认。展示前按[共同绑定格式](REVIEW-EVIDENCE.md#展示与完整答复)准备含本轮direction_reference.direction_sha256的回复正文，并原样保存为display。实答后取得review_receipt，confirmation填同一完整答复和方向摘要；其他方向内容不变。最终用 `--project .` 检查；有PM时还须P-1里程碑实际关闭。后段tone_contract引用完整path/version/sha256。

草稿摘要可用--draft --refresh-draft读取实际文件更新；只用于未确认草稿，从已有真实采集receipt取绑定，不代造采集。成功--draft持久化<contract>.delivery.json（可--receipt指定），stdout返回tool_receipt引用；其format为direction-tool-receipt/1，包含contract真实ref、tool来源SHA、direction_reference及delivery。失败不生成成功delivery；可解析草稿仍返回draft_incomplete的direction_reference供展示，不当通过。确认按真实答复生成；不手改hash冒新材料。
