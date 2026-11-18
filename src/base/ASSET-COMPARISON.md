# 素材锚点与已确认样稿对照

何时读：本活动范围的asset_family为yes，进入D-4锚点/素材成套制作。内置和导入专家用同一asset_anchors记录；不是按品类名触发，不增加人的审阅节点。

先做3–5个代表元素，组成实际核心场景小样。审看页把已确认方向样稿与本轮小样并排嵌入，结合具体特征当场比较，不能只写检查计划、只说放回场景或把比较推迟。至少覆盖本范围已确认的可观察外观特征；完整性和视觉贴合由原D-4专业审阅判断。

## 记录

asset_anchors保留scope、tone_contract、artifacts、anchors（3–5个不同真实ref）、scene_comparison、series_production，新增comparison：

```json
{"confirmed_features":["已确认的具体可观察特征"],
 "rows":[{"feature":"同一特征",
   "reference":{"path":"方向样稿文件","sha256":"当前摘要"},
   "reference_observation":"样稿中实际看见的关系",
   "anchor":{"path":"本轮锚点或场景小样","sha256":"当前摘要"},
   "anchor_observation":"本轮实际看见的关系",
   "status":"close","difference":"具体差异及影响"}],
 "review_page":{"path":"并排审看.html","sha256":"当前摘要"},
 "scene_sample":{"path":"本轮场景.html","sha256":"当前摘要"}}
```

ref均为项目相对path/sha256。confirmed_features逐项来自已确认样稿，不随本轮做法任意删减；rows逐项覆盖，不用“精致/统一/以后再看”等空话代实际观察。reference须是当前契约parts.preview或parts.screenshot。anchor须是本记录anchors或scene_sample；小样属于本次artifacts，不能拿方向样稿本身冒新小样。审看页用img/iframe/object等真实嵌入两侧和小样，写路径或链接不等于并排呈现；依赖文件同交回并保持摘要有效。HTML/SVG保留实际内容；若小样是PNG，comparison另写viewport/capture_binding，按[采集证据](REVIEW-EVIDENCE.md)绑定实际artifacts和采集receipt。

status仅achieved（达到）/close（接近）/unmet（未达到）。缺表、占位、旧ref、缺小样/审看素材或unmet时，保存待补草稿，不能完成成套放行。close必须保留实际差异与取舍，沿已有D-4审阅决定，不因表齐自动合格。程序只核结构、覆盖、文件和版本，不认证画质或观察确实发生。

共同定义asset_anchors版本更新后，导入专家按当前专业契约重做映射与验证；旧摘要不静默沿用。其他阶段的历史封存和当前成果规则见[阶段证据](STAGE-EVIDENCE.md)。
