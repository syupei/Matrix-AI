# 自带专家接入

何时读：自带专家适配、准入、启用或重新绑定。先核[准入审阅点](PRODUCTION-ADMISSION.md)；接口见[guide](PLATFORM-GUIDE.md)。导入包放专业方法与薄入口，引用共同登记及[证据格式](../base/REVIEW-EVIDENCE.md)。

## 准入答复的处置单

答复交代结论、失败包处置及修订包验证。失败包及原始证据保留、不可启用；已启用用expert.disable记原因。修订另建版本重验，不覆盖失败版本。缺材料标待取得，不声称已保存或停用。

## 从口述到实例

1. 前台保留地址、别名及接入原话交PM。按 `management/expert-professions.json` 人工预置类别、安装的专业登记与实例授权核对。专业、专家包、模型、运行器分别登记；缺类别由人配置，工具不创建类别。别名仅称呼。
2. 固定Git提交与入口子目录，调用expert.prepare；只经HTTPS拉取且拒重定向，锁外获取后重核授权和预置再登记。拒大小写/Unicode归一化冲突路径。保留原始source和摘要，不执行原包脚本、hooks、插件或安装器。入口不明时合批询问。
3. 读实际入口、依赖、许可与目录，整理METHODS，expert.adapt保存薄入口和适配审阅。原文留source/供审计，运行不加载其指令。依赖/许可不明或义务不满足列unresolved。缺或无效review_points在adapt即blocked；未决修好可重适配，不能等实跑后才发现缺点。
4. 按授权的运行器及实例配置做真实准入、独审，再调用expert.validate。无实际写隔离或验证未成时保持待接入。
5. 验证有效后，expert.enable带决定人和真实quote，仅使包可选。PM再按有效授权配置绑定、derive稳定实例ID并派活；范围扩大由人决定。验证、启用、绑定分开记录。

## 记录与目录

- 人工预置写schema为matrix-expert-professions/1、configured_by、authorization及professions列表，由可信平台维护，执行实例不可改。
- 配置项可加 `expert:{"id":"example","version":"1"}`、runner及aliases；别名数等于count。内置省expert，省别名用稳定ID。别名去首尾空白、英文大小写不敏感，中文及内部空格保留。resolve_instance后用稳定ID授权/派发；rename_instance留旧名，重名及历史名拒占。
- `experts/<id>/<version>/` 保留manifest.json、ENTRY.md、METHODS.md、REVIEW.json及source/。验证后不可覆盖，更新建新版本，实例保持原绑定。
- 私稿在实例workspace/private/，候选在workspace/public/，经负责人检验采用到唯一正式源；公有候选不自动正式。通读磁盘时private只是用途，不承诺读保密；任务库、配置、其它实例及包由可信工具和实际隔离保护。

## 逐阶段适配与真实验证

review含reviewer、source_entry、license、preserved_methods、directory_changes、dependencies与[master审阅点](PRODUCTION-ADMISSION.md)。从目标专业framework_contract取全部requirements和定义版本，逐条映射 `stage/requirement/source:{path,section}/adapted_method/records`；源缺项用source:null＋supplement。未触发阶段也保留做法，缺项/重复/未知/未满足记冲突。内置、导入按同专业同阶段的共同定义运行，产品P-1按[方向样张](DIRECTION-SAMPLE.md)。

控制器用launch_start的admission_expert:{id,version}及admission_runner绑定包，保存真实启动/交回/成功退出；候选只用于该准入任务。成果、stage_state及依赖须分别溯源实际生产者的可信交回，确认/历史快照核真实权威来源，不信工作区伪登记。两生产者合成验证用[scenario_view](EXPERT-SCENARIO-VIEW.md)，不冒作者原件。

独审沿原任务checker及等级/模型/独立性要求：分派→purpose=check启动→started→review交回checker的public报告→exit。报告含`run_id/model/runner/methods_sha256/passed/review_run_id`，checks三项method_preservation/write_isolation/handoff_contract各含passed与真实evidence；`tested_requirements/untested_requirements`均为 `{stage,requirement}` 列表，按实际gate与当前契约差集核对。framework_scenario含stage_state、contract_sha256、mapping_sha256、reviewer、readback。控制器用当前专业登记重跑同一关卡；只测一个阶段不认证整个专业。

expert.validate的evidence含runner/report/source_sha256（METHODS摘要），由可信控制器提交；可附上述scenario_view。工具核作者与独审真实DB运行、原review事件及报告字节；作者自签、候选自填passed、只有exit或模拟启动均不足。独审须实际回读原文、适配方法、成果、交回与适用图像，说明专业质量及未测范围。模型边界见[适配](MODEL-FIT.md)。

首次通过封存到 `management/expert-validations/<id>/<version>/<author-run-id>/`；manifest.validation保存bundle、author_run_sha256及review_receipt（真实DB的run/event/file摘要）等绑定。不塞进专家包目录改变package摘要。后续enable/bind/派发核完整快照、原可信receipt及当前methods/package/mapping/contract；正常public演进不打掉已验事实，改快照或receipt仍失效。

## 重新核验

旧验证缺新快照/独审绑定不能补签为有效，另建版本重适配与准入；契约变化也须新版本。无关专业或仅内置方法更新不牵连有效绑定。单包失效仅阻关联条目，全局配置错误仍拒绝。任务准入见[共同检查](PRODUCTION-ADMISSION.md)。
