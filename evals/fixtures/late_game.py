"""Frozen confirmed direction and separate downstream snapshots for paired evaluations."""

import hashlib
import json
from pathlib import Path


INPUTS = Path(__file__).with_name('late_game_inputs')
FILE_HASHES = {
    'direction.html': 'b550917ffb232a03ca0e89560ac2f3983f567049c034ba75d3cfcb7aa8a952b3',
    'direction.png': '203d18a87127dd6cdf9b0c04e7b048579684c1b5689dfa5a1ebd3c6e0a71768e',
    'drifted-increment.html': '90d03f8478f8f5203ef28a478cf614fbf6f2df96b74d44d85d2ca2201a026f51',
    'drifted-increment.png': 'e71f4ff09aa6fc7c9cd52f2783f7a6028169bfa364a60a2d38102b7ce8f4ed5b',
    'practice-profile.json': 'ed3a9044725dd9342999b60b60c09d3cbd7b70d19a7ff10293185e13dde1f17b',
    'skeleton.html': '2892a4ae8d8cfb6c4b13928feefa1b67aed9e2ce8afc7f599848d8d97e78afa0',
    'skeleton.png': '4a3c113c53d8d77fb113109794ad3d561c812e17598806c014c41b3f4ef574f1',
}
CONTRACT = 'product/specs/00-方向样张.md'
BRIEF = '''# 风脊竞走 · 合成项目方向 v1

单人离线桌面浏览器，目标视口 1280×800，普通办公笔记本与键盘可用，约十分钟一局。
进入棋盘、看棋子和路径，到岔路选安全线或迎风捷径，随后掷骰、看骰面、沿路移动、到营地结算并可再来一局。安全线多走两格，迎风捷径掷到 1 回岔路。

棋盘占据主视野。同屏看见棋子、岔路、两条路线及汇合点。青蓝地形衬出浅色实线和琥珀色虚线，棋子与落点清楚可辨。简短的回合提示及骰子留在棋盘周边。可用键盘选线。正常反馈是骰面、路径、落点依次出现，减少动效时保留同样信息；中断不能重复扣回合或挪棋。语气短促、略俏皮，规则后果直说。

需制作协调的地貌、格点与路线、棋子、骰子、落点状态、极少量 HUD。方向批准覆盖上述取舍；没有批准量产素材、实际可玩性、游戏上线或进一步偏离。
'''
SAMPLES = [
    ('开局', '风向正好，出发！'),
    ('到岔路', '安全线多走两格，迎风捷径更短。选好再掷。'),
    ('选捷径', '抄近道？掷到 1 就回岔路。'),
    ('显骰面', '掷出 4，沿选中路线走四格。'),
    ('退回', '骰子是 1，阵风把你送回岔路。重新选线。'),
    ('结算', '抵达营地！再走一局？'),
]
REFERENCES = [
    {'name': 'Royal Game of Ur', 'borrows': '棋盘路径本身提示可走位置和特别格',
     'observed': '合成项目列出的待观察参照，夹具不宣称访问'},
    {'name': 'Backgammon', 'borrows': '在同一棋盘区分棋子、落点与骰面',
     'observed': '合成项目列出的待观察参照，夹具不宣称访问'},
]


def put(root, relative, data):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data.encode('utf-8') if isinstance(data, str) else data)
    return {'path': relative, 'version': '1', 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def fixed(root, source, relative):
    data = (INPUTS / source).read_bytes()
    if hashlib.sha256(data).hexdigest() != FILE_HASHES[source]:
        raise ValueError('changed frozen downstream fixture input: ' + source)
    return put(root, relative, data)


def populate(root, case):
    brief = put(root, 'product/specs/方向简报.md', BRIEF)
    samples = put(root, 'content/场内样句.md', '\n'.join(f'- {moment}｜{line}' for moment, line in SAMPLES) + '\n')
    scene = fixed(root, 'direction.html', 'design/direction/sample.html')
    screenshot = fixed(root, 'direction.png', 'design/direction/sample.png')
    practice = fixed(root, 'practice-profile.json', 'product/specs/项目做法档.json')
    response = 'management/合成方向确认.md'
    quote = '确认风脊竞走方向 v1，按这份棋盘样张、场内样句和项目做法开展后段。'
    put(root, response, '# 合成确认记录\n\n仅为固定评测输入。\n\n合成项目负责人：' + quote + '\n')
    contract = {
        'version': '1', 'genre': '单人桌面掷骰路线竞赛', 'profile': '游戏与玩乐',
        'tone': '短促、略俏皮，后果直说', 'core_loop': '看棋盘和当前位置，选岔路、掷骰、沿路径移动、抵达营地、再走一局',
        'references': REFERENCES, 'avoid': ['把路线、棋子和落点拆成脱离棋盘的状态卡和操作列表'],
        'parts': {'brief': brief, 'scene': scene, 'samples': samples, 'screenshot': screenshot, 'practice_profile': practice},
        'samples': [{'moment': moment, 'text': line} for moment, line in SAMPLES],
        'confirmation': {'person': 'synthetic-owner', 'source': response, 'quote': quote},
    }
    put(root, CONTRACT, '# 已确认方向 v1 · 合成夹具\n\n正文见方向简报；场景和截图是同一视口的固定输入。\n\n'
        '```tone-contract\n' + json.dumps(contract, ensure_ascii=False, indent=2) + '\n```\n')

    if case == 'late_core_skeleton':
        fixed(root, 'skeleton.html', 'engineering/skeleton/skeleton.html')
        fixed(root, 'skeleton.png', 'engineering/skeleton/skeleton.png')
        put(root, 'engineering/skeleton/handoff.md',
            '# E-2.3 至 E-3.1 · 合成交接\n\nS-1 是 SVG/DOM 核心场景骨架，打开 skeleton.html 可复现 '
            '1280×800 的初始截图。工程侧交出了可运行页面，没有独立贴合复核记录；可见的骰面与棋子是示意，'
            '选线、出骰结果、移动、中断和键盘还没有接到规则。没有第一个可玩增量或真人试玩记录。\n')
    if case == 'late_implementation_walkthrough':
        fixed(root, 'drifted-increment.html', 'engineering/increment/i-1.html')
        fixed(root, 'drifted-increment.png', 'engineering/increment/i-1.png')
        put(root, 'engineering/increment/handoff.md',
            '# I-1 实现走查输入 · 合成\n\n目标是第 3 回合的岔路、选线和出骰反馈。1280×800 初始图见 '
            'i-1.png，本地打开 i-1.html 可点选两条路、掷骰和重来；测试数据固定出 4，'
            '只供走查，不称完整棋规、试玩或发布通过。方向仅以已确认版本 v1 为准。\n')
