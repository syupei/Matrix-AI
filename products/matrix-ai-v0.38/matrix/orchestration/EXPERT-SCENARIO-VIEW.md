# 准入场景的组合证据

何时读：真实准入的作者与独审分别交回成果，需要由可信控制器组合后验证。普通单来源接口不变；前置授权、独立性与准入规则见[专家接入](EXPERT-IMPORT.md)。

expert.validate的evidence可加 `scenario_view:{path,sha256}`，引用可信控制器封存的bundle。view是有来源的验证投影，不是作者原件，不提供关卡豁免。

- context用 `format:"matrix-admission-scenario/1"`，绑定真实DB的author_run_id、review_run_id，以及等于独审原报告framework_scenario.stage_state的state_path。
- origins逐项记logical_path、source_path、sha256、origin（author/review）；分别溯源作者真实handover与checker真实review交回。原件逐字节保留，每个逻辑文件须有唯一归属，不能给额外文件伪造来源。独审fit和report须为checker原件。
- control_derivations记录logical_path、kind、sha256、diff及适用source_path。控制器仅补契约confirmation、阶段绑定和request/response；display、synthetic_response须匹配可信回执的真实展示及完整答复。按[工具定义](tools/expert_packages.py)逐字段比对，保留派生前原件。不能改业务内容、scope、fit、report.passed、checks或专业结论。
- 用相同stage_gate验证完整view，registry仍取真实项目。P-1本阶段可尚未closed，后段仍须真实已关闭记录；不能用准入通过冒生产确认。合成答复仅用于明确标为仿真的隔离准入场景，不构成真人生产授权。

验证成功后，view及来源/diff清单、两生产者原件和可信运行/独审摘要进入包外validation快照；gate_receipt保存scenario_view/view_files。后续读封存字节，不依赖会正常演进的public/view活路径。组合文件齐全或无模型演练通过，都不等于实际专业准入和质量通过。
