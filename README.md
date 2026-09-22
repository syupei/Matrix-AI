# Matrix-AI

独立专业 Agent 的协作与交付技能包：产品、交互与视觉设计、研发承接、项目管理、专业协作，以及共用内容设计与审读能力。

[最新完整包及下载](https://github.com/syupei/Matrix-AI/releases/latest) · [全部历史版本](https://github.com/syupei/Matrix-AI/releases) · [版本目录](releases.json) · [下载包 SHA256](SHA256SUMS)

目前推荐 **professional-agents-kit-v0.9**，使用说明见 [START](packages/professional-agents-kit-v0.9/START.md)。安装不等于启动 Agent 或批准业务成果；具体能力、限制及实际验证以各版说明为准。

## 历史档案

- `packages/`：19 个已发布版本的完整源码快照，含隐藏 `.agents/skills/`、公共规则、原始来源及各版清单。
- GitHub Releases：对应版本标签、原 ZIP 或明确标注的重建 ZIP。早期误命名的 `product-design-agent-kit-v0.zip` 保留为 v0.1 的历史附件。
- `archive/unreleased/`：未发布的完整包 v0.4 中间稿，保持原样并说明清单不一致，不作为可安装版。
- 早期产品包 v0.1/v0.4、完整包 v0.5 的原 ZIP 缺失，已从哈希完整的原目录重建。重建不改变文件内容，但压缩文件哈希与原 ZIP 可能不同。
- 曾被删除的产品/设计联合包 v0.4 已无现存文件，仅记录缺失；其已确认能力包含在后续版本中。

本仓库于 2026-09-21 迁入历史发行物，标签和提交是迁移快照，不伪造过去的 Git 历史或原发布时间。原发布包保留原有来源与许可说明；没有为第三方材料重新授予许可。个人记忆、业务运行数据、临时研究和安装备份不在发布范围。

## 构建后同步发布

完成已获确认的版本修改和专业验证后，更新该版本文件清单，并使用统一入口：

```sh
python3 tools/release.py build /path/to/professional-agents-kit-v0.8 --notes /path/to/release-notes.md --latest
```

本地需要 Python 3.10+、Git 与已登录的 GitHub CLI，并具有本仓库写入权限。命令验证清单及 ZIP，运行包内测试，保存版本快照，提交、推送并创建 GitHub Release；上传后核对远端资产。只有整个过程成功才算发布完成。移交源文件须已获当前任务授权，外部同步不额外批准未审阅的技能改造。

同版本不同内容会被拒绝，必须提升版本号。网络中断可用同一命令重试；已发布且一致的资产不重复上传，不使用覆盖旧资产的选项。上传失败保留待发布状态，退出码非零；不会只生成 ZIP 就宣称同步成功。`releases.json` 的 `latest` 字段是当前版本依据。

批量重试已登记历史版本：

```sh
python3 tools/release.py sync --assets /path/to/zip-directory
```

只读检查和发布工具测试：

```sh
python3 tools/release.py verify
python3 -m unittest discover -s tools -p 'test_*.py' -v
```

这一机制由每次构建触发，不依赖后台轮询。发布包不会自动安装到任何实际项目。
