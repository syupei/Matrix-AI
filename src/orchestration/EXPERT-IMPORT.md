# 自带专家接入

接入时读；核[审阅点](PRODUCTION-ADMISSION.md)，接口见[guide](PLATFORM-GUIDE.md)。包只放方法与薄入口，引用[证据格式](../base/REVIEW-EVIDENCE.md)。

## 接入与处置

答复交代结论、失败包处置及修订包验证。缺材料标待取得，不声称已保存或停用。

1. 前台保留地址、别名、原话交PM。按management/expert-professions.json人工预置类别、专业登记与实例授权核对；工具不创建类别。专业、包、模型、运行器分别登记。
2. 固定Git提交与入口子目录，expert.prepare仅经HTTPS拉取且拒重定向；锁外获取后重核授权和预置。拒归一化冲突路径；保留source及摘要，不执行原包脚本、hooks、插件或安装器。入口不明时合批询问。
3. 读实际入口、许可、依赖和目录；expert.adapt保存METHODS、薄入口及REVIEW。原文留source/审计，运行不加载其指令。许可、依赖或义务未决记unresolved；缺有效review_points在adapt即blocked。
4. 候选只用于该准入任务。用已授权运行器和独立实例真实准入、独审，再expert.validate。无实际写隔离或验证未成时保持待接入。失败包与证据保留、不可启用；已启用的以expert.disable记原因。修订另建版本重验，不覆盖失败版本。
5. 验证有效后expert.enable带决定人与真实quote，只使包可选。PM再按有效授权配置绑定、derive稳定实例ID并派活。验证、启用、绑定分别记录；范围扩大由人决定。

## 目录与实例

预置matrix-expert-professions/1含configured_by、authorization、professions，由可信平台维护。配置含expert:{id,version}、runner、aliases；别名数等于count，省expert为内置。别名去首尾空白、英文大小写不敏感，中文及内部空格保留；rename_instance留旧名，拒重名及历史名。resolve_instance后按稳定ID派发。

experts/<id>/<version>/保留manifest.json、ENTRY.md、METHODS.md、REVIEW.json、source/；验证后更新须新版本，实例保持原绑定。私稿在实例workspace/private/，候选在public/，经负责人检验采用到正式源。private是用途，不承诺读保密；实际隔离保护任务库、配置、其它实例与包。

## 逐阶段映射与验证

REVIEW含reviewer、source_entry、license、preserved_methods、directory_changes、dependencies、master审阅点。从目标专业framework_contract取全部requirements及定义版本，逐条映射stage/requirement/source:{path,section}/adapted_method/records；源缺项用source:null＋supplement。缺项、重复、未知或未满足记冲突，未触发阶段仍保留做法。内置、导入共用同专业同阶段关卡。

控制器以launch_start的admission_expert:{id,version}及admission_runner绑定包，记录实际启动、交回、成功退出。成果、stage_state及依赖分别溯源生产者的可信交回；确认及历史快照核权威DB，不信工作区伪登记。两生产者组合用[scenario_view](EXPERT-SCENARIO-VIEW.md)，不冒作者原件。

独审沿原任务checker及等级、模型、独立性要求：分派→purpose=check→started→review交回checker public证据→exit。证据须比启动时review_baseline新建或改变，预放报告不算。报告含run_id/model/runner/methods_sha256/passed/review_run_id；checks三项method_preservation/write_isolation/handoff_contract各含passed与证据。tested_requirements/untested_requirements为{stage,requirement}列表，按实际gate与当前契约差集核对。

framework_scenario含stage_state、contract_sha256、mapping_sha256、reviewer、readback。组合view用author_stage:{path,sha256}指定作者交回模板、fit:{path,sha256}指定本次checker贴合记录；控制器不能换选。独审回读原文、适配方法、成果、交回与适用图像，说明质量及未测范围；模型边界见[适配](MODEL-FIT.md)。

expert.validate的evidence含runner/report/source_sha256（METHODS摘要），可附scenario_view。工具核真实DB的运行、review事件及字节，重跑共同关卡。作者自签、自填passed、只有exit或模拟启动均不足；测一个阶段不认证整个专业。

首次通过封存management/expert-validations/<id>/<version>/<author-run-id>/。manifest.validation保存bundle、author_run_sha256、review_receipt；DB的expert_validation（id=<id>/<version>）锚定bundle与receipt_sha256，不能重封存替换。enable/bind/派发核快照、DB锚点和当前methods/package/mapping/contract；public演进可继续，改快照或receipt失效。

D-4映射含pre_review_check（submission第5版：锚点审看前取回执，审看页及非方向材料列入阶段成果，unmet可审不可放行）。旧包重做适配；adapt与gate统一检查，见[共同对照](../base/ASSET-COMPARISON.md)。

## 迁移

专业契约templates.tone_contract绑定唯一matrix/base/tone-contract-template.md及SHA。模板、记录版本或关卡变化改变framework_contract摘要，须新版本重适配准入；旧验证不能补签新义务。P-1通过仍如实列其它阶段未测。单包失效仅阻关联条目；全局配置错误仍拒绝，无关专业或仅内置方法更新不牵连有效绑定。
