"""Identical workspaces and screenshot conditions for three first-draft probes."""


def populate(root, case):
    (root/'design').mkdir()
    (root/'content').mkdir()
    (root/'review-target.md').write_text(
        '评测环境：桌面浏览器，目标视口 1280×800。'
        'design/preview.html 是供实际渲染的候选稿。已有方向批准：无。'
        '业务与品类事实以本轮用户原话为准。\n', encoding='utf-8')
