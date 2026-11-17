# 方向样张与调性契约

附上品类简报、设计场景、样句及截图的路径、版本和 SHA-256。展示时呈现两种语气，确认后在选定语气下逐条登记文案。把下列代码块填入 `product/specs/00-方向样张.md`。用 [调性契约工具](../scripts/tone_contract.py) 的 `--project` 检查。阶段记录写 `tone_contract: {path,version,sha256}`。

```tone-contract
{"version":"待填","genre":"待填","profile":"游戏与玩乐","tone":"待填",
 "core_loop":"待填","references":[{"name":"参照名","observed":"已实看或未实看","borrows":"借鉴点"}],
 "avoid":["待填"],"samples":[{"moment":"时刻","text":"样句"}],
 "parts":{"brief":{"path":"简报","version":"版本","sha256":"摘要"},
          "scene":{"path":"场景","version":"版本","sha256":"摘要"},
          "samples":{"path":"样句文件","version":"版本","sha256":"摘要"},
          "screenshot":{"path":"浏览器截图","version":"版本","sha256":"摘要"}},
 "confirmation":{"person":"确认人","quote":"实际原话","source":"答复出处"}}
```
