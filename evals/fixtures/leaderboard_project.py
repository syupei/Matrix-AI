"""Synthetic community app for topic_promote: the leaderboard topic record and the product rules for places that
show user names. No real product, legal advice or person is represented."""
import importlib.util
from pathlib import Path

FILES = {
    'exchange/议题记录/TOP-RANK-01.md': '# TOP-RANK-01 排行榜能否显示真实姓名（已结论，合成）\n\n'
                                            '- 类型：咨询；发起方：产品；决定方：产品；参与方：外部法务（意见）。\n'
                                            '- 结论（法务意见，产品已核对采用）：未经用户同意，不能公开显示真实姓名；默认显示昵称。\n'
                                            '- 落到：product/rules/R-RANK-02.md v2。\n',
    'product/rules/R-RANK-02.md': '# R-RANK-02 排行榜显示（v2，合成）\n\n- 排行榜显示昵称；用户同意后可以显示真实姓名。\n',
    'product/rules/R-COMMENT-01.md': '# R-COMMENT-01 评论区（v1，合成）\n\n- 每条评论显示评论者的姓名与头像。\n',
    'product/rules/R-SHARE-03.md': '# R-SHARE-03 分享卡片（v1，合成）\n\n- 分享卡片上显示分享者的姓名。\n',
    'FIXTURE.md': 'This is a synthetic project. All records are simulated; no person, review, legal advice or approval is real.\n',
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
