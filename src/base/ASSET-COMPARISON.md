# 素材锚点与已确认方向样张对照

何时读：本活动范围的asset_family为yes，进入D-4锚点/素材成套制作。内置和导入专家用同一asset_anchors记录；不是按品类名触发，不增加人的审阅节点。

先做3–5个代表元素，组成实际核心场景小样。审看页把已确认方向样稿与本轮小样并排嵌入，结合具体特征当场比较，不能只写检查计划、只说放回场景或把比较推迟。至少覆盖本范围已确认的可观察外观特征；完整性和视觉贴合由原D-4专业审阅判断。

## 记录

可先运行 `tone_contract.py --project <项目> --asset-page <记录.json> --page-output <新审看页.html>`，按confirmed_features生成双侧嵌入区和逐项待观察行。补上实际观察、差异和限制，更新记录中的审看页摘要后再做交审前检查；生成页面不代表比较通过。

asset_anchors含scope、tone_contract、artifacts、anchors（3–5个不同真实ref）、scene_comparison、series_production及comparison：

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

缺灰模只延后放回灰模与成套放行；已有方向样张时，锚点当轮仍须对照。在锚点交人整体审看之前运行`python3 matrix/base/tools/tone_contract.py --project . --asset-comparison <asset_anchors记录>`，取得asset_comparison_receipt；在阶段状态asset_comparison_receipts中按活动ID引用。回执绑定记录、审看页、方向与小样；本次展示及后续审阅B可直接使用该页，也可用iframe/object嵌入本阶段全部范围的回执页。改稿后重查。无回执可存草稿，不能交审或完成。模板见[并排审看页](asset-comparison-template.html)，按confirmed_features逐行填写，不虚构观察。comparison.state写实际代表状态；生成页的状态、观察和限制占位全部替换。

团队human_attention显式写review_purpose：锚点整体审看为asset_anchors，阶段审阅为stage_review，并带task_id与stage_state（已存在的D-4 JSON，含契约、scope、artifacts、practice_evidence和asset_comparison_receipts）。澄清、更正及家族合批确认不使用这两个purpose，也不能凭其答复越过阶段。阶段确认消费时会再核对绑定任务和当前回执。单对话锚点审看时靠本指引执行，完成关卡再核回执。

ref均为项目相对path/sha256。confirmed_features逐项来自已确认样稿，不随本轮做法任意删减；rows逐项覆盖，不用“精致/统一/以后再看”等空话代实际观察。reference须是当前契约parts.preview或parts.screenshot。anchor须是本记录anchors或scene_sample；小样属于本次artifacts，不能拿方向样稿本身冒新小样。审看页用img/iframe/object等真实嵌入两侧和小样，写路径或链接不等于并排呈现；依赖文件同交回并保持摘要有效。HTML/SVG保留实际内容；若小样是PNG，comparison另写viewport/capture_binding，按[采集证据](REVIEW-EVIDENCE.md)绑定实际artifacts和采集receipt。

status仅achieved（达到）/close（接近）/unmet（未达到），按模板列序：第一格写特征原文，第四格只写状态；说明写入差异格，同一特征只列一次。表头不算结果。生成占位词被拦时按报错改成具体观察或未决事项，不在正式句子里沿用“待观察”等占位词。缺表、占位、旧ref或素材时不发回执。unmet可取得release_ready:false并如实交人决定，完成与成套放行仍被阻断；不要为交审改成close。close保留实际差异与取舍，沿已有D-4审阅决定，不因表齐自动合格。程序不认证画质或观察真实性。

D-4阶段artifacts按当前摘要列入审看页、小样、锚点和记录artifacts声明的交付材料；采集receipt是控制证据，不列入成果，仍核摘要及图像来源。团队提请inputs包含这些成果；包装页不替代它们。批准后改动任一材料须重新展示并取得实答，不能只刷新回执沿用旧批准。

导入专家须映射当前记录及pre_review_check，缺交审回执或未绑定审看材料同样被拦。隐藏嵌入、伪造展示和拆词规避仍须宿主与人核实；工具不认证实际可见性；未列入记录的依赖不受批准锁定。历史封存与当前成果见[阶段证据](STAGE-EVIDENCE.md)。
