#!/usr/bin/env python3
"""Candidate-only imported product probe. Prepare without models; execute once, at most two sessions."""
import argparse
import hashlib
import json
import shlex
import os
import re
from pathlib import Path
import shutil
import subprocess
import sys
import uuid

from fixtures import expert_probe_copy_inputs as seed, late_game
from operation_evidence import shell_commands
from platform_v033 import COMMIT, load
from visual_evidence import capture

REPO = Path(__file__).resolve().parents[1]
SOURCE = 'https://github.com/syupei/Matrix-AI.git'
SUBDIR = 'src/professions/product/skills/matrix-product'
IDENTITY = {'id': 'imported-product-v037', 'version': '2'}
PROJECT_ID = 'SIM-IMPORTED-PRODUCT-037-REPAIR'
MODEL, EFFORT, RUNNER = 'gpt-6-luna', 'medium', 'codex'
TEMPLATE = REPO / 'docs/platforms/codex-0.167.0.json'
LEDGER = REPO / 'eval-results/v0.37-repair-import-call-ledger'
AUTHOR, REVIEWER = 'ADMISSION', 'SIM-INDEPENDENT-REVIEWER'
STAGE_STATE = 'product/reviews/P-1-gate.json'
FIT = 'product/reviews/方向贴合.json'
SCENE = seed.SCENE
CONTRACT = 'product/specs/00-方向样张.md'
PROFILE = 'product/specs/项目做法档.json'
TONE_TOOL = 'matrix/base/tools/tone_contract.py'
PRODUCT_TONE_WRAPPER = '.agents/skills/matrix-product/scripts/tone_contract.py'
QUOTE = '合成审阅输入：按本夹具给出的单人桌面路线竞赛范围与体验限制作方向记录，仅用于准入关卡核对。'
REFERENCES = (
    {'name': 'Royal Game of Ur (RoyalUr.net)', 'source': 'https://royalur.net/rules',
     'context': '线上实现者的规则页。掷骰结果对应移动格数，棋盘路径与特殊格有明确作用。'},
    {'name': 'GNU Backgammon', 'source': 'https://www.gnu.org/s/gnubg/manual/gnubg.pdf',
     'context': '官方手册的行棋说明与棋盘示例连接骰面、棋子及合法落点。'},
)
CHECKS = ('method_preservation', 'write_isolation', 'handoff_contract')
EXPECTED_BOUNDARY = {'inside': True, 'project': False, 'sibling': False, 'outside': False, 'descendant': False}


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def reserve(path, record):
    """Reserve before launching. Exclusive durable records also stop concurrent execution."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as stream:
        json.dump(record, stream, ensure_ascii=False)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())


def append_event(path, record):
    with path.open('a', encoding='utf-8') as stream:
        stream.write(json.dumps(record, ensure_ascii=False) + '\n')


def installed(out):
    project = out / 'project'
    tools = project / 'matrix/orchestration/tools'
    return project, load('probe_pm', tools / 'pm_tasks.py'), load('probe_api', tools / 'platform_api.py'), load('probe_boundary', tools / 'isolated_runner.py')


def platform_call(api, project, out, op, params):
    token = str(uuid.uuid4())
    reply = api.handle(project, dict(protocol=api.SPEC, project_id=PROJECT_ID, request_id=token,
                                     event_id=token, op=op, params=params), 'controller')
    append_event(out / 'platform.jsonl', {'op': op, 'response': reply})
    require(reply['ok'], f'{op}: {reply.get("error")}')
    return reply['result']


def pm_call(pm, project, out, op, actor='PM', **fields):
    result = pm.execute(project, dict(op=op, actor=actor, event_id='SIM-' + uuid.uuid4().hex, **fields))
    append_event(out / 'lifecycle.jsonl', {'op': op, 'actor': actor, 'result': result})
    return result


def source_mapping(base, contract):
    source = (base / 'source/SKILL.md').read_text(encoding='utf-8')
    require('## 工作流' in source and '## 硬性关卡' in source and 'P-1 需求澄清' in source,
            'pinned product workflow cannot be located')
    known = {
        ('P-1', 'direction_profile'): ('P-1 项目做法档', '以原 P-1 的意图、受众、端、约束和待决项形成范围与事实，按共用模板分活动取证，写各专业的做法、偏离和检验。', '工作流 / P-1 需求澄清'),
        ('P-1', 'tone_contract'): ('P-1 方向合看与留存', '保留原 P-1 确认和成果快照做法。绑定实际简报、场景、预览、样句、截图及项目做法档，记录可定位参照与实际观察、样句的规则后果。使用共用草稿检查工具读回交付回执，合看引用合成记录的原件与精确原话。', '硬性关卡 / 第五条'),
        ('P-1', 'direction_fit'): ('P-1 贴合复核', '补做关卡要求的贴合记录。实际看截图与样句，覆盖场景、预览、样句及做法档，记录语气、偏离和审前方向摘要；单实例标 same_instance，另有独立准入审阅。', None),
        ('P-2', 'tone_contract'): ('P-2 范围接力', '先核对确认的契约版本、范围及未决项，再按原产品方法整理目标、核心模块、首期边界、运行形态与取舍。', '工作流 / P-2 目标与范围'),
    }
    methods = [
        '# 适配的产品方法',
        '先查用户原话、领域事实、设计建议与待决项。先覆盖核心模块和主线，再细化对象与规则。'
        '产品维护目标、范围、规则及验收；设计制作、工程实现及对外发布交有权角色。'
        '实际批准才标确认；范围变更先核对历史快照并通知受影响接收方。按 ENTRY 指向的共用约束工作。',
    ]
    mapping = []
    for row in contract['requirements']:
        key = row['stage'], row['requirement']
        require(key in known, f'no reviewed product method for {key}')
        heading, instructions, section = known[key]
        methods.extend([f'## {heading}', instructions])
        reference = {'path': 'SKILL.md', 'section': section} if section else None
        item = dict(stage=key[0], requirement=key[1], source=reference,
                    adapted_method=f'METHODS.md / {heading}', records=[row['definition']['record']])
        if reference is None:
            item['supplement'] = '固定来源未定义调性贴合记录，使用安装包的 P-1 方向复核与阶段关卡。'
        mapping.append(item)
    return '\n\n'.join(methods) + '\n', mapping


def populate(project):
    fixture = project / 'synthetic-input'
    suite = read_json(REPO / 'evals/cases/suite.json')
    business = next(case['turns'][0] for case in suite['cases'] if case['id'] == 'genre_dice')
    late_game.put(fixture, 'genre-dice.md', '# 合成任务原话\n\n' + business + '\n\n## 已提供的合成澄清\n\n' + late_game.BRIEF.split('\n\n', 1)[1].split('\n\n方向批准', 1)[0] + '\n')
    scene = late_game.fixed(fixture, 'direction.html', SCENE)
    rendered = capture(fixture, SCENE)
    require(rendered['status'] == 'captured', 'prebuilt synthetic design capture failed: ' + str(rendered))
    shutil.copyfile(fixture / rendered['screenshot'], fixture / seed.SCREENSHOT)
    write_json(fixture / 'visual-evidence/capture.json', dict(
        rendered, delivered_image=seed.SCREENSHOT, preview_sha256=scene['sha256'],
        origin='Pre-existing synthetic design HTML rendered by the probe preparer in a local browser',
        limitation='This static screenshot is input to the author; no author-created design, interaction test or human approval.'))
    write_json(fixture / 'external-references.json', {'references': REFERENCES,
        'observation': 'The preparer located these primary texts. An author who only reads this list has not read the sources or played the games.'})
    shutil.copyfile(Path(seed.__file__), fixture / 'copy_inputs.py')
    late_game.put(fixture, 'copy-samples.md', '# 合成内容设计样句草稿\n\n' + late_game.sample_lines())
    late_game.put(fixture, 'review-input.md',
                  '# 合成 P-1 审阅输入\n\n仅用于隔离验证，人物与确认均为合成输入。'
                  '此记录不提供完成结果，也不授权实际项目开发、发布或专家启用。\n\n' + QUOTE + '\n')


def boundary_script(path, project, out, workspace, sibling):
    path.write_text(
        'import json, subprocess, sys\nfrom pathlib import Path\n\n'
        'label = sys.argv[1]\n'
        'assert label in ("preflight", "author")\n'
        f'paths = {dict(inside=str(workspace / "private"), project=str(project), sibling=str(sibling / "private"), outside=str(out))!r}\n'
        'result = {}\n'
        'for key, path in paths.items():\n'
        '    try:\n'
        '        (Path(path) / ("boundary-" + label + ".txt")).write_text("synthetic write check")\n'
        '        result[key] = True\n'
        '    except OSError:\n'
        '        result[key] = False\n'
        'child = "from pathlib import Path;Path(" + repr(str(Path(paths["project"]) / ("boundary-child-" + label + ".txt"))) + ").write_text(\'synthetic child check\')"\n'
        'result["descendant"] = subprocess.run([sys.executable, "-c", child], capture_output=True).returncode == 0\n'
        'print("BOUNDARY_RESULT=" + json.dumps(result, sort_keys=True))\n',
        encoding='utf-8')


def receipts(output):
    return [json.loads(line.removeprefix('BOUNDARY_RESULT=')) for line in output.splitlines()
            if line.startswith('BOUNDARY_RESULT=')]


def preflight(out, project, boundary, runner, script):
    workspace = boundary.safe_workspace(project, AUTHOR)
    expanded, cwd, unset, _ = boundary.command_template(project, workspace, [], runner, MODEL, EFFORT)
    version = subprocess.check_output([expanded[0], '--version'], text=True).strip()
    require(version == 'codex-cli ' + runner['version'], 'CLI does not match the pinned conformance template')
    sandbox_options = [arg for arg in expanded if arg.startswith('sandbox_workspace_write.')]
    native = [expanded[0], 'sandbox', '-P', ':workspace', '-C', str(cwd)]
    for option in sandbox_options:
        native.extend(['-c', option])
    native.extend(['--', sys.executable, str(script), 'preflight'])
    env = {key: value for key, value in os.environ.items() if key not in unset}
    process = subprocess.run(native, cwd=cwd, env=env, capture_output=True, text=True, timeout=30)
    (out / 'native-preflight.stdout').write_text(process.stdout, encoding='utf-8')
    (out / 'native-preflight.stderr').write_text(process.stderr, encoding='utf-8')
    result = {'version': version, 'runner_template_sha256': sha(TEMPLATE), 'argv': native,
              'exit_code': process.returncode, 'receipts': receipts(process.stdout), 'model_sessions': 0}
    write_json(out / 'native-preflight.json', result)
    require(result['exit_code'] == 0 and result['receipts'] == [EXPECTED_BOUNDARY],
            'native no-model sandbox write check failed; raw preflight is retained')
    return result


def prepare(kit, out):
    manifest = kit / 'MANIFEST.json'
    require(manifest.is_file() and read_json(manifest).get('package') == 'matrix-ai/0.37',
            'use the prepared Matrix-AI 0.37 candidate kit')
    out.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(manifest, out / 'candidate-kit-manifest.json')
    project = out / 'project'
    project.mkdir()
    with (out / 'install.log').open('w', encoding='utf-8') as log:
        subprocess.run([sys.executable, str(kit / 'install.py'), '--target', str(project), '--apply'],
                       stdout=log, stderr=subprocess.STDOUT, check=True, timeout=60)
    project, pm, api, boundary = installed(out)
    pm_call(pm, project, out, 'init', config=dict(project=PROJECT_ID, pm_actor='PM', authorization='Authorized isolated synthetic expert probe', frontdoor_id='SIM-FRONT', max_slots=1))
    write_json(project / 'management/expert-professions.json',
               dict(schema='matrix-expert-professions/1', professions=['product'], configured_by='SIM-fixture', authorization='SIMULATED expert profession preset for this disposable probe'))
    runner = read_json(TEMPLATE)
    runner['models'] = {MODEL: MODEL}
    workspace = boundary.safe_workspace(project, AUTHOR)
    sibling = boundary.safe_workspace(project, REVIEWER)
    script = project / 'synthetic-input/boundary-probe.py'
    populate(project)
    boundary_script(script, project, out, workspace, sibling)
    preflight(out, project, boundary, runner, script)
    runner['capabilities'] = {
        key: {'state': 'supported', 'evidence': 'Local native sandbox preflight; model-run scope limited to this probe'}
        for key in ('launch', 'write_isolation', 'model_selection')
    }
    write_json(project / api.CONFIG, dict(schema=api.SPEC, project_id=PROJECT_ID,
               principals={'controller': dict(active=True, actor='PM', operations=['expert.prepare', 'expert.adapt', 'expert.validate'], task_ops=[])},
               runners={RUNNER: runner}))
    provenance = dict(url=SOURCE, commit=COMMIT, subdir=SUBDIR)
    platform_call(api, project, out, 'expert.prepare', dict(IDENTITY, profession='product', **provenance))
    base = project / 'experts' / IDENTITY['id'] / IDENTITY['version']
    experts = pm.team.experts
    contract = experts.framework_contract(pm.api(), project, 'product')
    versions = {(row['stage'], row['requirement']): row['definition']['version'] for row in contract['requirements']}
    require(all(versions.get(('P-1', name), 0) >= 2 for name in ('tone_contract', 'direction_profile', 'direction_fit')),
            'prepare against the repaired candidate with the updated product framework contract')
    methods, mapping = source_mapping(base, contract)
    review = dict(reviewer='trusted probe preparation operator', source_entry='SKILL.md',
                  license='Public pinned Matrix-AI source. No separate license file in this commit tree; retained verbatim for authorized local evaluation only.',
                  preserved_methods='P-1 fact and scope elicitation, confirmation and snapshot; P-2 objective and scope handoff. Mapping augments those methods with the candidate framework.',
                  directory_changes='Original source retained under source/. Active entry and adaptation use Matrix, writable instance private/public only.',
                  dependencies='Installed Matrix common framework and product registry; no source scripts executed.',
                  review_points=[dict(who='master', what='Check scope, sources, direction, and P-1 review inputs for discrepancies')],
                  framework_mapping=mapping)
    platform_call(api, project, out, 'expert.adapt', dict(IDENTITY, methods=methods, review=review))
    _, adapted = experts.read(pm.api(), project, IDENTITY)
    require(adapted['state'] == 'awaiting_validation', 'adaptation did not pass preparation')
    binding = experts.admission_binding(pm.api(), project, IDENTITY)
    prepared = dict(kit_manifest_sha256=sha(manifest), runner_template_sha256=sha(TEMPLATE), binding=binding,
                    project=str(project), probe_sha256=sha(Path(__file__)),
                    source=provenance, model=MODEL, effort=EFFORT, boundary_script_sha256=sha(script),
                    inputs={file.relative_to(project).as_posix(): sha(file) for file in script.parent.rglob('*') if file.is_file()},
                    model_sessions=0, state='prepared', limit='Candidate-only; no production instance or expert activation.')
    write_json(out / 'prepared.json', prepared)
    return prepared


PUBLIC_FILES = (
    STAGE_STATE, CONTRACT, PROFILE, FIT, 'product/specs/方向简报.md', SCENE,
    seed.SCREENSHOT, 'content/场内样句.md', seed.REVIEW_OUTPUT,
    'product/reviews/展示.md', 'product/reviews/request.json', 'product/reviews/response.json',
    'product/reviews/conversation.md', 'product/reviews/截图回读.md',
)


def author_prompt(project):
    source = project / 'synthetic-input'
    copy = shlex.join([sys.executable, str(source / 'copy_inputs.py')])
    boundary = shlex.join([sys.executable, str(source / 'boundary-probe.py'), 'author'])
    expert = f"experts/{IDENTITY['id']}/{IDENTITY['version']}"
    public = project / 'management/instances' / AUTHOR / 'workspace/public'
    direction_check = shlex.join([sys.executable, '-B', str(project / TONE_TOOL),
                                  '--project', str(public), '--contract', CONTRACT, '--draft'])
    return f"""本次是隔离专家准入。业务、角色与 P-1 审阅授权是合成夹具。仅本次会话；禁止嵌套模型、子代理和其它 CLI 会话。

1. 在当前实例工作区原样运行这两条命令，实际保留日志。沙箱如允许越界写，停止。
   {boundary}
   {copy}
   第二条只做 P-1 三个输入副本的字节复制并返回原话 JSON；必须用返回的 source 与 quote（包括前缀），不要重写副本或手抄。其它产物用文件编辑工具或 Python -c 保存；宿主会拒绝 here-document 临时文件。
2. 按需读取 {expert}/ENTRY.md、METHODS.md、REVIEW.json 的 P-1 映射及产品专业登记的 P-1 条目。共同规则只读当前用到的 DIRECTION-SAMPLE、PRACTICE-PROFILES 和 STAGE-GATES 部分，避免加载完整技能包。旧 source 是审阅依据。业务依据见 synthetic-input/genre-dice.md。读 synthetic-input/external-references.json 的两项外部品类参照；选择本项目各自可以借鉴的做法，给出可核实 source 和实际观察程度。只读摘要时注明未直接访问，合成 HTML 和 PNG 是本项目输入。
3. 实际查看本轮附入的 1280×800 PNG，和简报对照，在「截图回读.md」记具体位置、动作关系和限制。PNG 是准备者从合成设计 HTML 实际截图，采集原始记录在 synthetic-input/visual-evidence/capture.json。这两份是设计输入，不是你制作或渲染的成果，也没有直接证明键盘、时序或可玩性。
4. 自己在 workspace/public/ 生成做法档、方向简报、方向契约、至少六条覆盖至少四个实际代表时刻的样句（每条 moment、text、consequence）、贴合、展示与阶段记录。用需求事实和设计输入，分清取舍与待决。实际授权仅到隔离候选验证。
   公开根是阶段状态内业务路径的基准。固定交回文件：
   {chr(10).join('- ' + item for item in PUBLIC_FILES)}
   契约 parts.scene.path 和 parts.preview.path 均为 {SCENE}，parts.screenshot.path 为 {seed.SCREENSHOT}。额外说明写进既有简报或展示，所有阶段成果、贴合与关卡引用均在上述清单。
5. 单独运行下面的实际安装命令（不与其它命令合并），保留成功返回的 delivery 和 direction_reference。
   {direction_check}
   以该 direction_reference 及当前场景、预览、样句和做法档的摘要生成 {FIT}，mode=same_instance，checker 和 producer 都为 {AUTHOR}；注明预置截图的真实采集来源。若更新过方向内容，重新核验。实际缺口照实反馈。
6. 填合成 P-1 → P-2 关卡，scope 为 ["race"]，response actor="user" 仅用于合成授权，契约 confirmation 与 response 使用复制命令返回的同一句 quote 和同一 source。实际调用 stage_gate.py --digest 取得当前成果摘要；回读一次 stage_gate.py --state 的结果；可信交回由控制器办。
"""


def reviewer_prompt(out, public, source):
    return f"""独立审阅一次隔离准入。不要改首轮任何文件与专家包。禁止触发新运行、调用嵌套模型、其他 CLI 会话或子代理。
实际读取固定导入原文 {source / 'source/SKILL.md'} 的 P-1 段落、METHODS.md 和 REVIEW.json 的对应映射、首轮实际交回、公用关卡结果、author-boundary.json 和 lifecycle.jsonl。相关运行原始事件在 {out / 'author.stdout.jsonl'}；按命令和事件定向读取，避免把整段轨迹或无关文件加载到上下文。
实际查看本轮附带的交回图像 {public / seed.SCREENSHOT}，对照活动结构、规则后果、布局和同实例贴合。核对外部品类参照的实际观察范围，并区分预置合成设计与浏览器采集、作者真实制作的做法档/方向合成/语义样句/关卡、以及独立审阅本身。业务与 P-1 确认是合成输入。

请在你自己的 workspace/public/review.json 写一个 JSON 对象：
{{"checks":{{"method_preservation":{{"passed":false,"evidence":"实际原文位置、方法与成果的细节和结论"}},
"write_isolation":{{"passed":false,"evidence":"实际 shell 轨迹中的拒绝、正常写入和边界"}},
"handoff_contract":{{"passed":false,"evidence":"实际交回文件及关卡前置、版本与结果"}}}},
"framework":{{"passed":false,"readback":"具体方向、做法档、贴合、动作语气、确认范围和证据缺口"}},
"image_readback":"图中看见的实际位置、对象和活动关系"}}
true、false 按实查填写。任一证据不足即说明；程序传输成功不足以判专业行为。保留未测阶段、禁止
声称真实人已批准、已启用此专家或完成专业质量全面认证。"""


def turn_completed(trace):
    return sum(1 for event in trace if event.get('type') == 'turn.completed') == 1


def trace_events(path):
    events = []
    for line in path.read_text(encoding='utf-8').splitlines():
        try:
            events.append(json.loads(line))
        except ValueError:
            continue
    return events


def author_boundary(events, probe):
    found = []
    for event in events:
        item = event.get('item', {})
        if (event.get('type') == 'item.completed' and item.get('type') == 'command_execution'
                and str(probe) in item.get('command', '')):
            found.extend(receipts(item.get('aggregated_output', '')))
    return found


def is_author_draft_call(command, project, public):
    calls = list(shell_commands(command))
    if len(calls) != 1:
        return False
    executable, *args = calls[0]
    name = Path(executable).name
    if not re.fullmatch(r'python(?:[0-9]+(?:\.[0-9]+)*)?', name):
        return False
    on_path = shutil.which(name)
    trusted_python = {Path(sys.executable).resolve()}
    if on_path:
        trusted_python.add(Path(on_path).resolve())
    cwd = public.parent
    interpreter = (cwd / executable).resolve() if '/' in executable else Path(on_path).resolve() if on_path else None
    if interpreter not in trusted_python:
        return False
    while args and args[0] in {'-B', '-u'}:
        args = args[1:]
    trusted_scripts = {project / name for name in (TONE_TOOL, PRODUCT_TONE_WRAPPER)}
    if not args or (cwd / args[0]).resolve() not in trusted_scripts:
        return False

    parser = argparse.ArgumentParser(add_help=False, allow_abbrev=False, exit_on_error=False)
    parser.add_argument('--project')
    parser.add_argument('--contract', default=CONTRACT)
    parser.add_argument('--draft', action='store_true')
    try:
        options, extra = parser.parse_known_args(args[1:])
    except argparse.ArgumentError:
        return False
    return (options.draft and not extra and bool(options.project)
            and (cwd / options.project).resolve() == public
            and Path(options.contract).as_posix() == CONTRACT)


def author_delivery(events, project, public):
    results = []
    for event in events:
        item = event.get('item', {})
        if (event.get('type') != 'item.completed' or item.get('type') != 'command_execution'
                or item.get('exit_code') != 0
                or not is_author_draft_call(item.get('command') or '', project, public)):
            continue
        try:
            receipt = json.loads(item.get('aggregated_output') or '')
        except ValueError:
            continue
        if isinstance(receipt, dict) and receipt.get('allowed') is True and isinstance(receipt.get('delivery'), dict):
            results.append(receipt['delivery'])
    return results


def verified_files(public):
    refs = []
    for name in PUBLIC_FILES:
        path = public / name
        require(path.is_file() and path.resolve() == path and path.stat().st_nlink == 1,
                f'missing or linked author public artifact: {name}')
        refs.append(path)
    return refs


def run_session(out, project, boundary, iid, runner, prompt, phase, started=None):
    (out / f'{phase}.prompt.md').write_text(prompt, encoding='utf-8')
    workspace = boundary.safe_workspace(project, iid)
    command, cwd, _, _ = boundary.command_template(project, workspace, [], runner, MODEL, EFFORT)
    image = Path(next(arg.removeprefix('--image=') for arg in command if arg.startswith('--image=')))
    write_json(out / f'{phase}.command.json', {'argv': command, 'cwd': str(cwd), 'model': MODEL, 'effort': EFFORT,
                                               'image_input': {'path': str(image), 'sha256': sha(image)}})
    with (out / f'{phase}.stdout.jsonl').open('w', encoding='utf-8') as stdout, (out / f'{phase}.stderr.log').open('w', encoding='utf-8') as stderr:
        result = boundary.run(project, iid, [], prompt, timeout=600, stdout=stdout, stderr=stderr,
                              started=started, adapter=runner['adapter'], model=MODEL, effort=EFFORT, template=runner)
    write_json(out / f'{phase}.process.json', result)
    return result


def runner_with_image(runner, image):
    require(runner['argv'][-1] == '-' and image.is_file(), 'pinned stdin runner and real image required')
    return dict(runner, argv=[*runner['argv'][:-1], '--image=' + str(image), '-'])


def author_handover(pm, project, out, public, run_id, delivery_receipts):
    """Check the trusted P-1 output closure before making a handover record."""
    paths = verified_files(public)
    original = project / 'synthetic-input'
    original_quote = seed.quote(original)
    for source, output in seed.COPIES:
        require(sha(public / output) == sha(original / source), 'copied synthetic input changed: ' + output)
    allowed = set(PUBLIC_FILES)

    def declared(references):
        extra = set(references) - allowed
        require(not extra, 'undeclared framework output: ' + ', '.join(sorted(extra)))

    state = read_json(public / STAGE_STATE)
    gate = pm.admission.load_gate()
    tone = gate.tone.read(public, CONTRACT)
    require(tone['parts']['scene']['path'] == SCENE, 'undeclared scene output: use ' + SCENE)
    require(tone['parts']['preview']['path'] == SCENE, 'undeclared preview output: use ' + SCENE)
    require(tone['parts']['screenshot']['path'] == seed.SCREENSHOT, 'use the actual synthetic design screenshot')
    require({ref['source'] for ref in REFERENCES} <= {ref['source'] for ref in tone['references']},
            'name the two actual external game references with their sources')
    require(tone['confirmation']['quote'] == original_quote
            and tone['confirmation']['source'] == seed.REVIEW_OUTPUT,
            'P-1 confirmation must cite the exact pre-existing synthetic review input')
    declared(part['path'] for part in tone['parts'].values())
    declared(state[key] for key in ('request', 'response', 'conversation_check', 'tone_fit_review'))
    declared(item['path'] for item in state['artifacts'])
    declared((state['tone_contract']['path'],))
    request = read_json(public / state['request'])
    response = read_json(public / state['response'])
    require(response.get('quote') == original_quote and response.get('source') == seed.REVIEW_OUTPUT,
            'P-1 response must cite the verbatim synthetic input')
    fit = read_json(public / state['tone_fit_review'])
    declared([request['display_evidence'], response['source']])
    declared(item['path'] for item in fit['artifacts'])
    declared(fit[key]['path'] for key in ('screenshot', 'manual_review') if key in fit)

    checked = gate.check(public, state, registry_root=project)
    completed, required = gate.framework_outputs(public, state, checked, registry_root=project)
    require({item['requirement'] for item in completed} >= {'tone_contract', 'direction_profile', 'direction_fit'},
            'actual P-1 stage did not trigger the prepared product obligations')
    declared(required)
    direction_delivery = gate.tone.direction_delivery(tone)
    require(direction_delivery in delivery_receipts, 'no actual author --draft receipt matches the handed direction')
    require(set(required) <= {path.relative_to(public).as_posix() for path in paths},
            'stage outputs missing from verified handover files')
    write_json(out / 'gate-precheck.json', {'checked': checked, 'completed': completed, 'required_outputs': sorted(required),
                                            'matching_author_delivery': direction_delivery})
    pm_call(pm, project, out, 'hand_over', actor=AUTHOR, run=run_id,
            evidence=[path.relative_to(project).as_posix() for path in paths],
            summary='Actual files from synthetic imported product admission; independent review pending.')
    return paths


def run_author(pm, project, out, boundary, runner, binding):
    rid = 'import-admission-' + uuid.uuid4().hex
    tid = 'SIM-ADMISSION-037-REPAIR'
    workspace = boundary.safe_workspace(project, AUTHOR)
    public = workspace / 'public'
    output_paths = [(public / name).relative_to(project).as_posix() for name in PUBLIC_FILES]
    runner = runner_with_image(runner, project / 'synthetic-input' / seed.SCREENSHOT)
    command = boundary.command_template(project, workspace, [], runner, MODEL, EFFORT)[0]
    pm_call(pm, project, out, 'register_instance', id=AUTHOR,
            instance=dict(role='product', endpoint='SIM-isolated-admission', write_roots=[str(workspace.relative_to(project))]))
    base = project / 'experts' / IDENTITY['id'] / IDENTITY['version']
    pm_call(pm, project, out, 'create', task=dict(id=tid, title='SIM isolated product admission', owner=AUTHOR,
            executor=AUTHOR, checker=REVIEWER, goal='Complete one P-1 candidate framework exercise',
            inputs=[(base / 'METHODS.md').relative_to(project).as_posix()], outputs=output_paths,
            practice_stage={'role': 'product', 'current': 'P-1', 'scope': ['race']},
            criteria=['Actual artifacts and independent review required'], next_action='Run the bounded admission'))
    pm_call(pm, project, out, 'launch_start', id=rid, task_id=tid, purpose='start', instance=AUTHOR,
                       model=MODEL, session=rid, command=command, admission_expert=IDENTITY, admission_runner=RUNNER)
    run = pm.team.experts.validation_run(pm.api(), project, rid)
    require(run['admission_expert'] == binding, 'trusted launch did not bind prepared content')
    started = False
    exited = False

    def record_start(pid):
        nonlocal started
        pm_call(pm, project, out, 'launch_started', id=rid, pid=pid)
        started = True

    try:
        reserve(LEDGER / 'author.json', {'out': str(out), 'run_id': rid, 'model': MODEL, 'effort': EFFORT})
        result = run_session(out, project, boundary, AUTHOR, runner, author_prompt(project), 'author', started=record_start)
        events = trace_events(out / 'author.stdout.jsonl')
        try:
            require(result['exit_code'] == 0 and not result['timed_out'] and turn_completed(events),
                    'author did not complete the single allowed session')
            probe = project / 'synthetic-input/boundary-probe.py'
            observed = author_boundary(events, probe)
            write_json(out / 'author-boundary.json', {'receipts': observed, 'expected': EXPECTED_BOUNDARY})
            require(observed == [EXPECTED_BOUNDARY], 'author shell trajectory did not verify isolation')
            require(not any((parent / 'boundary-author.txt').exists() for parent in
                            (project, out, project / 'management/instances' / REVIEWER / 'workspace/private'))
                    and not (project / 'boundary-child-author.txt').exists(), 'author write reached a protected test path')
            paths = author_handover(pm, project, out, public, rid, author_delivery(events, project, public))
        finally:
            pm_call(pm, project, out, 'launch_exit', actor='launcher', id=rid, exit_code=result['exit_code'])
            exited = True
    except BaseException as error:
        if not exited:
            if started:
                pm_call(pm, project, out, 'launch_lost', actor='scheduler', id=rid, evidence=type(error).__name__)
            else:
                pm_call(pm, project, out, 'launch_failed', id=rid, error=type(error).__name__)
        raise

    run = pm.team.experts.validation_run(pm.api(), project, rid)
    require(run.get('handed') is True and run.get('state') == 'exited', 'trusted handover or exit record missing')
    handed = run['handover']['files']
    require(all(handed.get(path.relative_to(project).as_posix()) == sha(path) for path in paths),
            'trusted handover receipt does not cover current author files')
    return run, public, base


def run_reviewer(out, project, boundary, runner, author, public, base):
    workspace = boundary.safe_workspace(project, REVIEWER)
    reserve(LEDGER / 'reviewer.json', {'out': str(out), 'author_run': author['id'], 'model': MODEL, 'effort': EFFORT})
    runner = runner_with_image(runner, public / seed.SCREENSHOT)
    result = run_session(out, project, boundary, REVIEWER, runner, reviewer_prompt(out, public, base), 'reviewer')
    events = trace_events(out / 'reviewer.stdout.jsonl')
    require(result['exit_code'] == 0 and not result['timed_out'] and turn_completed(events),
            'reviewer did not complete the single allowed session')
    path = workspace / 'public/review.json'
    require(path.is_file() and path.resolve() == path and path.stat().st_nlink == 1, 'independent review artifact missing')
    data = read_json(path)
    evidence = data.get('checks', {})
    def has_text(value):
        return isinstance(value, str) and bool(value.strip())

    require(isinstance(evidence, dict) and set(evidence) == set(CHECKS)
            and all(isinstance(row, dict) and row.get('passed') is True and has_text(row.get('evidence'))
                    for row in evidence.values()), 'independent evidence missing or a check failed')
    framework = data.get('framework', {})
    require(isinstance(framework, dict) and framework.get('passed') is True and has_text(framework.get('readback'))
            and has_text(data.get('image_readback')), 'independent product or image readback missing or failed')
    return data


def execute(kit, out, freeze_sha256):
    plan = read_json(out / 'prepared.json')
    require(plan['kit_manifest_sha256'] == freeze_sha256 == sha(kit / 'MANIFEST.json'),
            'prepared kit differs from the authorized frozen candidate digest')
    require(plan['runner_template_sha256'] == sha(TEMPLATE) and plan['probe_sha256'] == sha(Path(__file__)),
            'runner template or probe changed since preparation')
    project, pm, api, boundary = installed(out)
    require(str(project) == plan['project'], 'prepared project must remain in its original isolation directory')
    pre = read_json(out / 'native-preflight.json')
    require(pre['receipts'] == [EXPECTED_BOUNDARY] and pre['exit_code'] == 0, 'local sandbox preflight failure')
    for relative, expected in plan['inputs'].items():
        require(sha(project / relative) == expected, 'synthetic input changed since preparation: ' + relative)
    for path, expected in read_json(kit / 'MANIFEST.json')['files'].items():
        if path.startswith(('matrix/', '.agents/')):
            require(sha(project / path) == expected, 'installed source changed: ' + path)
    binding = pm.team.experts.admission_binding(pm.api(), project, IDENTITY)
    _, manifest = pm.team.experts.read(pm.api(), project, IDENTITY)
    require(manifest['state'] == 'awaiting_validation' and binding == plan['binding'], 'imported candidate changed')
    runner = read_json(project / api.CONFIG)['runners'][RUNNER]
    config = read_json(TEMPLATE)
    require(all(runner.get(key) == value for key, value in config.items() if key not in {'models', 'capabilities'})
            and runner['models'] == {MODEL: MODEL}, 'installed runner configuration changed')
    version = subprocess.check_output([runner['argv'][0], '--version'], text=True).strip()
    require(version == pre['version'], 'CLI version changed since the no-model boundary preflight')
    reserve(LEDGER / 'execution.json', {'out': str(out), 'kit_manifest_sha256': freeze_sha256, 'max_sessions': 2,
                                       'authorization_scope': 'v0.37 repaired candidate-only imported product; fresh author and independent reviewer; no retry'})
    try:
        author, public, base = run_author(pm, project, out, boundary, runner, binding)
        review = run_reviewer(out, project, boundary, runner, author, public, base)
        refs = author['handover']['files']
        require(all(sha(project / path) == expected for path, expected in refs.items()), 'raw author handover changed')
        require(pm.team.experts.admission_binding(pm.api(), project, IDENTITY) == binding, 'adaptation changed after execution')
        report = dict(passed=True, runner=RUNNER, run_id=author['id'], model=MODEL,
                      methods_sha256=binding['methods_sha256'], checks=review['checks'],
                      framework_scenario=dict(reviewer=REVIEWER,
                          readback=review['framework']['readback'] + '\n' + review['image_readback'],
                          contract_sha256=binding['contract_sha256'], mapping_sha256=binding['mapping_sha256'],
                          stage_state=(public / STAGE_STATE).relative_to(project).as_posix()))
        report_ref = 'management/imported-framework-validation.json'
        write_json(project / report_ref, report)
        platform_call(api, project, out, 'expert.validate', dict(IDENTITY, evidence=dict(
            runner=RUNNER, report=report_ref, source_sha256=binding['methods_sha256'])))
        _, final = pm.team.experts.read(pm.api(), project, IDENTITY)
        require(final['state'] == 'validated', 'probe must stop at validated')
        summary = {'state': 'validated', 'model_sessions_reserved': 2, 'expert': IDENTITY, 'run_id': author['id'],
                   'kit_manifest_sha256': freeze_sha256, 'receipt': final['validation']['gate_receipt'],
                   'limit': 'Synthetic P-1 only. The PNG was provided directly to both model sessions; visual attention is assessed from their concrete readback. No human approval, expert enablement, production binding or professional certification.'}
        write_json(out / 'summary.json', summary)
        return summary
    except BaseException as error:
        write_json(out / 'summary.json', {'state': 'stopped', 'reason': str(error), 'error': type(error).__name__,
            'model_sessions_reserved': sum((LEDGER / f'{stage}.json').is_file() for stage in ('author', 'reviewer')),
            'limit': 'No automatic retry, extra session, enablement or production binding.'})
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kit', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    phase = parser.add_mutually_exclusive_group(required=True)
    phase.add_argument('--prepare-only', action='store_true')
    phase.add_argument('--execute', action='store_true')
    parser.add_argument('--freeze-sha256')
    args = parser.parse_args()
    kit, out = args.kit.resolve(), args.out.resolve()
    if args.execute and not args.freeze_sha256:
        parser.error('--execute needs the authorized frozen MANIFEST.json digest')
    result = prepare(kit, out) if args.prepare_only else execute(kit, out, args.freeze_sha256)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
