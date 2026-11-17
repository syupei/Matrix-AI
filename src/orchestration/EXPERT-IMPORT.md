# 自带专家接入

启用前确认[准入要求的审阅点](PRODUCTION-ADMISSION.md)。

用户给出 Git 地址并要求接入时，前台保留原话交 PM；PM 或有对应平台权限的主实例按本页推进。导入包是专业方法与适配入口，Matrix 共同规则和专业登记只引用一份。工具接口见 [平台 guide](PLATFORM-GUIDE.md)；实例派生仍按 [团队运行](TEAM-RUNTIME.md)。

## 准入答复的处置单

回答“能否通过/启用”时，先交代三件事：**结论、失败包处置、修订包验证**。未通过的失败包及原始失败证据保留、维持不可启用；已启用的用 expert.disable 记录原因。修正另建版本并重新验证，失败版本不覆盖。缺实际包或报告时，也明确这份处置计划，标注待取得材料后执行；不声称已经保存或停用。

## 从口述到可派发实例

1. 读取 `management/expert-professions.json` 的人工预置类别和 `matrix/professions/` 专业登记，核对现有实例配置及授权。用户给出的别名用于称呼，专业、专家包、模型、运行器分别登记。缺少类别时登记待人配置事项；导入工具不创建类别。
2. 解析 Git 地址与入口所在子目录，固定完整提交号，调用 `expert.prepare`。工具在锁外仅经 HTTPS 拉取（拒绝重定向），返回后重核授权与预置，以短事务登记；拒绝大小写或 Unicode 归一化后冲突的路径。保存原始文件、来源与摘要，不运行原包脚本、hooks、插件或安装器。无法定位入口或缺少必要信息时合批询问。
3. 主实例审阅实际入口与依赖，整理专业方法、项目接口、平台依赖、许可及目录映射。按本页映射要求生成 `methods`，用 `expert.adapt` 保存薄入口、方法与适配审阅。原始内容留在 `source/` 供审计，运行时不加载其中的指令。依赖无法适配、许可不清或共同义务不满足时列入 `unresolved`，交既有决定方。
4. 在目标运行器做真实准入验证，按本页证据格式调用 `expert.validate`。无实际写隔离时保持待接入。
5. 验证有效后，`expert.enable` 带决定人和真实授权原话，仅标记包可选用。PM 按有效授权配置绑定；范围扩大时由人决定。`derive` 产稳定实例 ID；任务引用该 ID，平台按就绪条件启动。

## 记录与目录

- 人工预置：`{"schema":"matrix-expert-professions/1","configured_by":"真实配置人","authorization":"真实授权引用","professions":["code-engineering"]}`。由可信平台维护，执行实例没有修改权限。
- 实例配置项在原字段上可加 `expert:{"id":"example","version":"1"}`、`runner:"runner-id"`、`aliases:["小王.ai"]`。别名数量须与该项 count 相等；省略时用稳定 ID。内置包省略 expert。
- `experts/<id>/<version>/` 保存 `manifest.json`、`ENTRY.md`、`METHODS.md`、`REVIEW.json` 及原始 `source/`。验证后不覆盖，更新产生新版本；已派生实例保持原绑定。
- 私有草稿写 `management/instances/<id>/workspace/private/`；候选交付写 `workspace/public/`，由负责人检验并采用到唯一正式源。公有候选不自动成为正式成果。
- 本地磁盘通读时，private 表示用途，不承诺读保密。任务库、配置、专家包、其它实例工作区由可信工具和实际隔离保护。
- 别名去首尾空白、英文大小写不敏感，中文和内部空格保留。用 `resolve_instance` 查到稳定 ID 后派发；`rename_instance` 保留旧名历史，重名和历史名占用被拒绝。权限以稳定 ID 为准。

## 逐阶段适配与报告

- `review` 保留 reviewer、source_entry、license、preserved_methods、directory_changes、dependencies 和 [master 审阅点](PRODUCTION-ADMISSION.md)。从目标专业登记取得阶段和共同条目，在 `REVIEW.json` 逐项写 `stage`、`requirement`、`source:{path,section}`、`adapted_method`、`records`；来源缺项时写 `source:null` 和 `supplement`。阶段条件未在准入样例触发时也写明做法。缺项或方法不满足时登记冲突，保持不可启用。运行按本专业当前阶段读共同规则和适配方法。
- 在已授权的准入任务上由可信控制器用 `launch_start` 传 `admission_expert:{id,version}`、`admission_runner`，启动绑定当前包。保留实际启动、交回与成功退出。待验专家只在该准入任务使用。
- 报告含 run_id、model、runner、methods_sha256、passed 和三项 `checks`（method_preservation、write_isolation、handoff_contract），各附实际证据和结果。专业登记有共同义务时，至少一个实际场景触发本专业相关条目。审阅者实际回读成果与交回，填 `framework_scenario:{stage_state,contract_sha256,mapping_sha256,reviewer,readback}`。关卡输入文件 `stage_state` 的项目相对路径须列入实际交回，其中业务路径以本次实例 `workspace/public/` 为根；可信控制器重跑关卡并留回执。候选自填通过、只回报进程退出或模拟启动均不构成该证据。
- `expert.validate` 的 evidence 含 runner、report、source_sha256；可信控制器提交，工具核对候选版本与内容、绑定模型和运行器、真实交回与结束。独立检查说明证据覆盖范围，保留未验证的阶段与专业质量问题。报告中的模型边界见[模型适配](MODEL-FIT.md)。

## 重新核验与迁移

启用、绑定和派发时核对映射完整无冲突、专业共同契约与证据仍匹配。相关契约变更或缺适配映射时，另建包版本，重新适配、验证并按有效授权绑定。保留原包与报告；无关专业材料或单纯内置方法更新沿用原有效绑定。任务阶段准入见[共同检查](PRODUCTION-ADMISSION.md)。
