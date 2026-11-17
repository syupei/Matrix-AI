# 方向样张

何时读：P-1 澄清、分派、制作、贴合检查、合看或接续当前方向。项目做法档的模板、特征及后段义务见 [项目做法档](../base/PRACTICE-PROFILES.md)。

## 分工与准备

前台先澄清最影响核心活动的问题，取得 P-1 合看的真实授权。产品按需要与各专业并行准备，按本范围将方向成果收进产品定义入口。

- 产品写已澄清的简报、推荐做法档与参照；收集各专业结论并合成。
- 交互与视觉设计写场景结构、交互、外观与素材做法，制作一张推荐方向的低细节渲染及目标视口截图；涉及直接操作时，给可点首稿，能走到核心动作与反馈。
- 内容设计写场景文字和语气建议。合看展示两种语气，各有覆盖代表性活动时刻的实际样句；确认后逐条记录选定语气的样句。常用提示及关键后果也可作为样句。做法档声明直接操作、连续动画或关键时序反馈时，选定语气覆盖至少四个实际时刻及六条不同样句。
- 研发补外观和交互可达性、运行条件及待验证技术风险。质量补对照、复现与验收方法。已有 master 各审本职内容，未接入的专业按既有缺口处理。PM 组织交接，保留可独立完成的内容与未决事项。

## 检查与一次合看

团队中由贴合检查员使用另一实例，优先用不同模型，回读做法档、实际截图、代表样句与方向草稿。指出与核心活动、目标人群、语气的具体偏离及调整办法；按[共用信号](../base/APPLICATION-DRIFT.md)检查。未通过先返工。单对话沿同一顺序并标「同一实例检验」。缺截图能力时，记录缺口并请人实际看稿，使用[阶段关卡](../base/STAGE-GATES.md)的人工记录。真实看稿随已有 P-1 展示安排处理。

审前运行 `python3 matrix/base/tools/tone_contract.py --project . --contract product/specs/方向样张草稿.md --draft`。工具读取草稿，返回的绑定路径使用最终契约位置。将 `direction_reference` 写入贴合记录的 `tone_contract`，并写 `binding_mode: "pre_confirmation_direction"`。核对所审场景、样句与做法档的摘要。它绑定除 `confirmation` 外的方向内容；合看确认时只填写真实确认。方向内容变化时重新复核。P-1 关卡的 `artifacts` 包含最终契约，`tone_contract` 引用其完整摘要。

PM 用 `direction_sample` 组织分工与原 P-1 一次合看。登记 `id`、显示用 `profile`、澄清简报 `brief`、决定人 `person`、合看的授权原话 `combined_review_authorization`，及 `assigned` 中的五专业 master、`fit_checker`、`task_checker`。分工和输出路径取工具返回；项目档为 `product/specs/项目做法档.json`，合看草稿与最终契约分开。可附已登记但未开始的 `downstream`；采用完整范例时传 `example: "board-race"`，并在适用活动范围保留范例引用。合看展示材料保留固定版本，样张、做法档、样句和澄清结论共同确认。按[契约格式](../../.agents/skills/matrix-product/assets/tone-contract-template.md)在 `product/specs/00-方向样张.md` 登记当前版本和真实原话、答复来源，供 P-2 起接续。按[任务工具](PM-INTEGRITY-TOOLS.md)的 `human_attention` 实际记录展示与回复，PM 人的负担视图列次数、材料字数及答复用时。
