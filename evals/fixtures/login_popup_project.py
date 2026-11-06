"""Synthetic app project for base_route_owner_code: the design specification of the login failure popup and the
half-implemented code. No real product or person is represented."""
import importlib.util
from pathlib import Path

FILES = {
    'design/specs/DS-PG-07.md': '# DS-PG-07 登录失败弹窗（v3，已交付，合成）\n\n'
                               '- 宽度 480px，居中；标题、说明（文案键 MSG-LOGIN-07）、按钮"重试"。\n'
                               '- 适配：本规格只写了 375px 以上的屏幕。\n',
    'code/login/failure_popup.py': '"""登录失败弹窗（合成，实现中）。"""\nPOPUP_WIDTH = 480  # DS-PG-07 v3\n\n\n'
                                   'def show_failure_popup(screen_width, copy):\n    # TODO: 屏幕窄于弹窗时怎样显示，规格没有写\n'
                                   '    return {"width": POPUP_WIDTH, "message": copy["MSG-LOGIN-07"], "button": "重试"}\n',
    'engineering/build/00-工作状态.md': '# 工作状态（合成）\n\n- 负责人：用户 / matrix-code-engineering-build\n'
                                       '- 当前位置：增量构建共 3 步，当前第 2 步「增量循环」，INC-2 登录\n'
                                       '- 进行中：登录失败弹窗（引用 DS-PG-07 v3）；登录页其余部分\n- 下周提测\n',
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
