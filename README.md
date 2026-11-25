# Matrix-AI

一组中文专业工作方法与协作规则，包含共同基础、项目管理与前台，以及产品、内容设计、交互与视觉设计、代码工程和质量工程等专业。可在单个对话中使用，也可按项目需要配置多个专业实例；关键决定由人掌握。

[下载 Matrix-AI 0.38](https://github.com/syupei/Matrix-AI/releases/tag/matrix-ai-v0.38) · [本版变化与已知限制](release-notes/matrix-ai-v0.38.md) · [版本目录](releases.json) · [下载核对](SHA256SUMS)

## 安装与开始使用

完整包与可阅读的规则、技能、模板及运行脚本位于 [products/matrix-ai-v0.38/](products/matrix-ai-v0.38/)。请先阅读 [START](products/matrix-ai-v0.38/START.md)。需要 Python 3.10 或更高版本；本版不提供 Windows 支持。

将完整包解压后，在包目录运行：

```sh
python3 install.py --target "<新项目路径>"
python3 install.py --target "<新项目路径>" --apply
```

先预检再安装。已装有其它版本的项目会在写入前停止；本安装器不作跨版本升级或迁移。安装不会启动任务，也不代表批准业务成果。

安装后，可先请项目前台按项目描述推荐专业组合，由你决定；小任务也可以在一个对话中按各专业要求完成。各专业保留自己的阶段、审阅点和交付要求。

## 使用注意

请阅读[本版说明中的使用注意和已知限制](release-notes/matrix-ai-v0.38.md)。通知完整性、已有确认的接续、专业边界、设计与实现的核对，以及关键风险与发布决定仍需要人工把关。本版不提供美术专业与图像生成接口。

## 旧版本

[已发布版本](https://github.com/syupei/Matrix-AI/releases)及 `packages/` 中已有的产品资料保留原样；下载对应版本时，请使用相应说明与核对信息。
