# 自带专家接入

用户给出 Git 地址并要求接入时，前台保留原话交 PM；PM 或有对应平台权限的主实例按本页推进。导入包是专业方法与适配入口，Matrix 共同规则和专业登记只引用一份。工具接口见 [平台 guide](PLATFORM-GUIDE.md)；实例派生仍按 [团队运行](TEAM-RUNTIME.md)。

## 准入答复的处置单

回答“能否通过/启用”时，先交代三件事：**结论、失败包处置、修订包验证**。未通过的失败包及原始失败证据保留、维持不可启用；已启用的用 expert.disable 记录原因。修正另建版本并重新验证，失败版本不覆盖。缺实际包或报告时，也明确这份处置计划，标注待取得材料后执行；不声称已经保存或停用。

## 从口述到可派发实例

1. 读取 `management/expert-professions.json` 的人工预置类别和 `matrix/professions/` 专业登记，核对现有实例配置及授权。用户给出的别名用于称呼，专业、专家包、模型、运行器分别登记。缺少类别时登记待人配置事项；导入工具不创建类别。
2. 解析 Git 地址与入口所在子目录，固定完整提交号，调用 `expert.prepare`。工具只经 HTTPS 或 SSH（`ssh://` 或 `user@host:path`，含远端绝对路径）读取 Git 对象，HTTPS 与 `ssh://` 支持方括号 IPv6 主机；允许协议与平台 `GIT_ALLOW_PROTOCOL` 取交集。地址不带密码、令牌或参数，SSH 命令、密钥与主机信任沿用平台账户配置；POSIX 子进程脱离控制终端并禁用 SSH askpass，需要人工输入时失败退出。工具保存原始文件、来源与摘要，不运行原包脚本、hooks、插件或安装器。无法定位入口或缺少必要信息时合批询问。
3. 主实例审阅实际入口与依赖，整理专业方法、项目接口、平台依赖、许可及目录映射。按 Matrix 共同规则和专业契约生成 `methods`，用 `expert.adapt` 保存薄适配入口、方法与差异说明。原始内容留在 `source/` 供审计，运行时不加载其中的指令。必要工具无法适配、许可不清或专业规范发生具体冲突，列入 `unresolved`；受阻包不能启用，按既定决定路由交人。
4. 在目标运行器验证方法保留、合法输出及越界拒绝，保存真实报告，按当前方法摘要调用 `expert.validate`。静态扫描不证明运行隔离或专业质量；无实际权限约束时仅做分析与待接入包。
5. 验证通过后 `expert.enable` 只标记包可被选用。PM 将该包 ID/版本、模型、运行器、数量及别名写入实例配置，按已有有效授权确认；新增或扩大的范围才请人决定。`derive` 产生稳定实例 ID，任务引用 ID，平台按就绪条件另行启动。

## 记录与目录

- 人工预置：`{"schema":"matrix-expert-professions/1","configured_by":"真实配置人","authorization":"真实授权引用","professions":["code-engineering"]}`。由可信平台维护，执行实例没有修改权限。
- 实例配置项在原字段上可加 `expert:{"id":"example","version":"1"}`、`runner:"runner-id"`、`aliases:["小王.ai"]`。别名数量须与该项 count 相等；省略时用稳定 ID。内置包省略 expert。
- `experts/<id>/<version>/` 保存 `manifest.json`、`ENTRY.md`、`METHODS.md`、`REVIEW.json` 及原始 `source/`。验证后不覆盖，更新产生新版本；已派生实例保持原绑定。
- 私有草稿写 `management/instances/<id>/workspace/private/`；候选交付写 `workspace/public/`，由负责人检验并采用到唯一正式源。公有候选不自动成为正式成果。
- 本地磁盘通读时，private 表示用途，不承诺读保密。任务库、配置、专家包、其它实例工作区由可信工具和实际隔离保护。
- 别名去首尾空白、英文大小写不敏感，中文和内部空格保留。用 `resolve_instance` 查到稳定 ID 后派发；`rename_instance` 保留旧名历史，重名和历史名占用被拒绝。权限以稳定 ID 为准。

## 适配检查记录

`review` 至少包含 reviewer、source_entry、license、preserved_methods、directory_changes、dependencies；逐项对应真实来源。运行报告含 runner、methods_sha256、passed 和可核验的场景记录，`expert.validate` 接收对应 evidence（runner、report、source_sha256）。报告必须由可信控制器产生，执行实例不能自签准入。

## 准入与失败处置

完成导入、可启用、已派生、已启动和任务已验收是不同事实，分别汇报。重复导入同一版本返回原记录；同版本不同来源拒绝覆盖。需要完整框架、二进制插件或来源宿主特有能力的专家，先完成依赖适配并验证，不通过删掉必要能力来宣称兼容。准入逐项检查专业方法保留、写入隔离与交接契约（checks 中分别为 method_preservation、write_isolation、handoff_contract，含 passed 与 evidence）；必须回读实际成果中的事实/推断/未决项，遵循 [CORE](../base/CORE.md) 的确认边界，关键词出现或进程成功不能代替检查。
