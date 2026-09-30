# Matrix-AI

独立专业 Agent 的协作与交付技能包：产品、交互与视觉设计、研发承接、项目管理、专业协作，以及共用内容设计与审读能力。

[最新完整包及下载](https://github.com/syupei/Matrix-AI/releases/latest) · [全部历史版本](https://github.com/syupei/Matrix-AI/releases) · [版本目录](releases.json) · [下载包 SHA256](SHA256SUMS)

目前推荐 **professional-agents-kit-v0.15**，使用说明见 [START](packages/professional-agents-kit-v0.15/START.md)。v0.16 正在按确认授权发布；远端核对完成前仍为候选。

## 历史档案

- `packages/`：v0.15 及此前已发布版本的完整源码快照，含隐藏 `.agents/skills/`、公共规则、原始来源及各版清单。
- GitHub Releases：对应版本标签、原 ZIP 或明确标注的重建 ZIP。早期误命名的 `product-design-agent-kit-v0.zip` 保留为 v0.1 的历史附件。
- `archive/unreleased/`：未发布的完整包 v0.4 中间稿，保持原样并说明清单不一致，不作为可安装版。
- 早期产品包 v0.1/v0.4、完整包 v0.5 的原 ZIP 缺失，已从哈希完整的原目录重建。重建不改变文件内容，但压缩文件哈希与原 ZIP 可能不同。
- 曾被删除的产品/设计联合包 v0.4 已无现存文件，仅记录缺失；其已确认能力包含在后续版本中。

本仓库于 2026-09-21 迁入历史发行物，标签和提交是迁移快照，不伪造过去的 Git 历史或原发布时间。原发布包保留原有来源与许可说明；没有为第三方材料重新授予许可。个人记忆、业务运行数据、临时研究和安装备份不在发布范围。

## 修改与发布

唯一可编辑源码在 `src/`，版本在 `package.json`。从 v0.16 开始，Git 标签和 `release-manifests/` 保存版本依据，不再逐版复制完整目录。维护测试、合成行为场景与运行器分别在 `tests/`、`evals/`；它们不进入使用方 ZIP。

```sh
python3 tools/production.py --build-dir build
python3 evals/run.py --source /path/to/previous-source --output /path/to/baseline-results
python3 evals/run.py --source src --output /path/to/candidate-results
python3 tools/production.py --build-dir build --publish --evidence /path/to/comparison.json --notes /path/to/release-notes.md
```

先完成实际行为比较与逐项审阅，报告格式见 [评测说明](evals/README.md)，维护约束见 [CONTRIBUTING](docs/CONTRIBUTING.md)。缺结果、源码/场景不匹配、测试未完成或发生退步均阻断发布。脚本检查不能认证人身份或代替专业判断。

本地需要 Python 3.10+、Git、已登录的 GitHub CLI；行为运行器需要已登录的 Codex CLI。正式发布验证源码与 ZIP、执行测试、推送源代码和标签、上传 Release 并核对远端资产。上传失败保留未完成状态；同版本内容不可替换，网络失败可按原命令重试。发布不等于安装，也不批准待审提案。

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
