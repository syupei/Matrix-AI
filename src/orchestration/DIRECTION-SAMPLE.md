# 方向样张

游戏与玩乐档在 P-1 建项目级样张。前台先问最影响核心活动的问题，并确认是否与 P-1 合看。PM 用 `direction_sample` 记录 `id`、`profile`（游戏与玩乐）、已澄清简报 `brief`、决定人 `person`、合看授权原话 `combined_review_authorization`，以及 `assigned` 中的 product、experience-design、content-design、fit_checker、task_checker。可附 `downstream`（已登记的待开始任务）。缺专业走既有缺口处理。单对话按同一顺序处理并标同一实例。已有专业的交付继续准备，待决定部分照实标明。

产品先写品类与参照简报。设计制作并截图，内容拟玩法时刻样句，两者并行。产品合成引用，分歧退各专业处理。另一实例优先换模型看图与文案，记录品类贴合、应用感和说明书式语句的位置；未通过先返工。P-1 和样张只合并展示一次，既有返工、人审和复核机制继续生效。需要真正展示及回复时，前台或 PM 用 `human_attention` 先写 `id`、`kind`（confirmation、clarification、correction）和实际 `display` 文件，再用同一 ID 记录实际 `response` 文件。PM 人的负担视图列次数、材料字数及答复用时。

产品将 `product/specs/00-方向样张.md` 登记在产品定义入口。确认后按[契约格式](../../.agents/skills/matrix-product/assets/tone-contract-template.md)留存。阶段关卡引用当前契约的路径、版本和 SHA-256；项目级样张与设计人审使用当前成果的贴合记录。默认工具与业务档维持既有入口。

合并审阅的展示材料保留固定版本，确认后再登记契约原话及答复来源。P-1 贴合检查覆盖确认前的场景与样句摘要。
