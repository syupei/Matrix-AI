"""Synthetic app project for topic_perf: the home page design, the product experience requirement and the
performance finding. No real product, device result or person is represented."""
import importlib.util
from pathlib import Path

FILES = {
    'design/specs/首页.md': '# 首页：设计规格（v2，设计 master 维护，合成）\n\n- 全屏背景模糊，内容层随滚动视差移动。\n- 目标 60 帧。\n',
    'product/specs/体验要求.md': '# 体验要求（v1，已确认，合成）\n\n- EXP-03：首页要有动态的品牌感，动效是品牌体验的一部分。\n'
                               '- EXP-04：在主流与低端安卓机上，首页滚动要流畅。\n',
    'engineering/solution/性能试做.md': '# 性能试做（合成）\n\n- 低端安卓机（合成样机）：全屏模糊加视差约 38 帧，去掉模糊约 58 帧。\n',
    'exchange/群聊摘录.md': '# 群聊摘录（合成）\n\n- 代码工程 master：低端机达不到 60 帧，建议去掉全屏模糊。\n'
                              '- 产品：动效是品牌体验的一部分，不能去掉。\n- 代码工程 master：那至少低端机要降级。\n- 产品：降级会不会显得廉价？\n',
    'management/团队.md': '# 团队（合成）\n\n- 项目管理：project-management-001，统筹项目层任务。\n- 交互与视觉设计 master：你。\n'
                       '- 代码工程 master：code-engineering-001。\n- 产品负责人：user（唯一的人）。\n',
    'FIXTURE.md': 'This is a synthetic project. All records are simulated; no person, review or approval is real.\n',
}


def populate(root, case_id):
    for rel, text in FILES.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')
    _layout().adapt(root)


def _layout():
    spec = importlib.util.spec_from_file_location('fixture_layout', Path(__file__).with_name('layout.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
