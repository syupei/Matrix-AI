# 单对话合并交付表

先保存并回读实际成果。送审前，登记每个有产出的专业、采用的具体要求和文件。多个专业共用一份文件也要分行。交付表在回复正文中取代文件链接清单，放在确认提问之前。

将交付清单保存为 JSON 数组。每行含 profession（登记的专业 ID）、requirement（实际应用的规则或检查）、file（现有成果的项目相对路径）。例如：

```json
[
  {"profession":"product","requirement":"写明规则及可观察的验收结果","file":"feature.md"},
  {"profession":"content-design","requirement":"文案有键，按可见情境列出","file":"feature.md"},
  {"profession":"code-engineering","requirement":"实现后运行测试，报告实际结果","file":"feature.py"}
]
```

运行 `python3 matrix/base/tools/delivery_table.py <交付清单文件>`（使用实际安装路径）。按本次有成果的专业加 `--require`，例如 `--require product --require content-design --require code-engineering`。把生成的 Markdown 表直接放入回复，再说明检验身份、未验证范围和本次审阅请求。
