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
from capture_broker import CaptureBroker, preflight as capture_preflight
from admission_run import admitted_sources

REPO = Path(__file__).resolve().parents[1]
SOURCE = 'https://github.com/syupei/Matrix-AI.git'
SUBDIR = 'src/professions/product/skills/matrix-product'
IDENTITY = {'id': 'imported-product-v037', 'version': '4'}
PROJECT_ID = 'SIM-IMPORTED-PRODUCT-037-ROUND2-REPAIR'
MODEL, EFFORT, RUNNER = 'gpt-6-luna', 'medium', 'codex'
TEMPLATE = REPO / 'docs/platforms/codex-0.167.0.json'
# Fresh user authorization (2026-11-18): one author/checker pair, 1800s each.
# Keep the previous 600s failure and its consumed reservations immutable.
LEDGER = REPO / 'eval-results/v0.37-round2-import-1800-call-ledger'
SESSION_TIMEOUT = 1800
AUTHOR, REVIEWER = 'ADMISSION', 'SIM-INDEPENDENT-REVIEWER'
TASK_ID = 'SIM-ADMISSION-037-REPAIR'
STAGE_STATE = 'product/reviews/P-1-gate.json'
FIT = 'product/reviews/方向贴合.json'
FIT_SCREENSHOT = 'design/fit.png'
FIT_CAPTURE = 'design/fit.png.capture.json'
SCENE = 'design/preview.html'
PREVIEW_SCREENSHOT = 'design/preview.png'
PREVIEW_CAPTURE = 'design/preview.png.capture.json'
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
    path.parent.mkdir(parents=True, exist_ok=True)
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
    template=contract.get('templates',{}).get('tone_contract')
    require(isinstance(template,dict) and template.get('path')=='matrix/base/tone-contract-template.md' and template.get('sha256'),
            'current shared direction template must be declared in the framework contract')
    source = (base / 'source/SKILL.md').read_text(encoding='utf-8')
    require('## 工作流' in source and '## 硬性关卡' in source and 'P-1 需求澄清' in source,
            'pinned product workflow cannot be located')
    known = {
        ('P-1', 'direction_profile'): ('P-1 项目做法档', '以原 P-1 的意图、受众、端、约束和待决项形成范围与事实，按共用模板分活动取证，写各专业的做法、偏离和检验。', '工作流 / P-1 需求澄清'),
        ('P-1', 'tone_contract'): ('P-1 方向合看与留存', '保留原 P-1 确认和成果快照做法。绑定实际简报、场景、预览、样句、截图及项目做法档，记录可定位参照与实际观察、样句的规则后果。使用共用草稿检查工具读回交付回执，合看引用合成记录的原件与精确原话。', '硬性关卡 / 第五条'),
        ('P-1', 'direction_fit'): ('P-1 贴合复核', '由原任务实际独立checker在check运行中读取作者原件与真实截图，覆盖场景、预览、样句及做法档，记录语气、偏离和审前方向摘要；mode=independent，不把作者自检当独审。', None),
        ('P-2', 'tone_contract'): ('P-2 范围接力', '先核对确认的契约版本、范围及未决项，再按原产品方法整理目标、核心模块、首期边界、运行形态与取舍。', '工作流 / P-2 目标与范围'),
    }
    methods = [
        '# 适配的产品方法',
        'P-1按当前框架契约templates.tone_contract读取matrix/base/tone-contract-template.md；共同格式只以该模板为准。',
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
    brief = late_game.BRIEF.split('\n\n', 1)[1].replace(
        '方向批准覆盖上述取舍；没有批准量产素材、实际可玩性、游戏上线或进一步偏离。',
        '上述取舍尚为候选；量产素材、实际可玩性、游戏上线和进一步偏离均须后续审阅。')
    late_game.put(fixture, 'genre-dice.md', '# 合成任务原话\n\n' + business + '\n\n## 已提供的合成澄清\n\n' + brief + '\n')
    original = late_game.INPUTS / 'direction.html'
    require(sha(original) == late_game.FILE_HASHES['direction.html'], 'fixed source HTML changed')
    html = original.read_text(encoding='utf-8')
    require(html.count('已确认方向样张') == 1, 'candidate scene derivation needs the fixed source title')
    html = html.replace('已确认方向样张', 'P-1 待审方向候选')
    html = html.replace('第 3 回合 · 棋子停在岔路', 'P-1 候选待审 · 第 3 回合 · 棋子停在岔路')
    scene = late_game.put(fixture, seed.SCENE, html)
    rendered = capture(fixture, seed.SCENE)
    require(rendered['status'] == 'captured', 'prebuilt synthetic design capture failed: ' + str(rendered))
    shutil.copyfile(fixture / rendered['screenshot'], fixture / seed.SCREENSHOT)
    capture_binding = {'artifacts': [scene], 'pixel_size': [1280, 800], 'viewport': '1280x800', 'scale': 1,
                       'state': 'P-1待审候选，第3回合棋子停在岔路', 'method': 'preparer headless Chrome screenshot',
                       'source': 'synthetic-input/visual-evidence/capture.json'}
    write_json(fixture/seed.CAPTURE, dict(capture_binding, screenshot_sha256=sha(fixture/seed.SCREENSHOT)))
    write_json(fixture / 'visual-evidence/capture.json', dict(
        rendered, delivered_image=seed.SCREENSHOT, preview_sha256=scene['sha256'],
        origin='Pending P-1 synthetic candidate derived from fixed HTML and freshly rendered by the probe preparer',
        derived_from_sha256=sha(original),
        limitation='This static screenshot is input to the author; no author-created design, interaction test or human approval.'))
    write_json(fixture / 'external-references.json', {'references': REFERENCES,
        'observation': 'The preparer located these primary texts. An author who only reads this list has not read the sources or played the games.'})
    shutil.copyfile(Path(seed.__file__), fixture / 'copy_inputs.py')
    shutil.copyfile(REPO/'evals/import_preflight.py',fixture/'import_preflight.py')
    late_game.put(fixture, 'copy-samples.md', '# 合成内容设计样句草稿\n\n' + late_game.sample_lines())
    late_game.put(fixture, 'review-input.md',
                  '# 合成 P-1 审阅输入\n\n仅用于隔离验证，人物与确认均为合成输入。'
                  '此记录不提供完成结果，也不授权实际项目开发、发布或专家启用。\n\n' + QUOTE + '\n')
    seed.seal_inputs(fixture)


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


def instrument_hashes():
    return {name:sha(REPO/'evals'/name) for name in ('imported_framework_probe.py','capture_broker.py',
        'capture_page.mjs','author_capture.py','fixtures/expert_probe_copy_inputs.py','admission_run.py','import_preflight.py')}


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
    public=workspace/'public'
    public.mkdir(parents=True,exist_ok=True)
    with CaptureBroker(public,out/'capture-preflight-events.jsonl'):
        capture_capability=capture_preflight(public,out/'capture-preflight')
    shutil.rmtree(public/'_evaluation')
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
    prepare_author_instances(pm,project,out,boundary)
    source_context=prepare_source_context(pm,project,out,adapted)
    task=prepare_author_task(pm,project,out,boundary,source_context)
    prepared = dict(kit_manifest_sha256=sha(manifest), runner_template_sha256=sha(TEMPLATE), binding=binding,
                    project=str(project), probe_sha256=sha(Path(__file__)),
                    source=provenance, model=MODEL, effort=EFFORT, boundary_script_sha256=sha(script),
                    inputs={file.relative_to(project).as_posix(): sha(file) for file in script.parent.rglob('*') if file.is_file()},
                    capture_capability=capture_capability, instrument_hashes=instrument_hashes(), source_context=source_context, source_context_sha256=sha(out/'source-context.json'), task_preflight=task, task_preflight_sha256=sha(out/'task-create-preflight.json'), model_sessions=0, state='prepared', limit='Candidate-only; no production instance or expert activation.')
    write_json(out / 'prepared.json', prepared)
    return prepared


AUTHOR_SELF = 'product/reviews/作者自检.json'
REVIEW_REPORT = 'review.json'
PUBLIC_FILES = (
    STAGE_STATE, CONTRACT, PROFILE, AUTHOR_SELF, 'product/specs/方向简报.md', SCENE,
    PREVIEW_SCREENSHOT, PREVIEW_CAPTURE, FIT_SCREENSHOT, FIT_CAPTURE, 'content/场内样句.md', seed.REVIEW_OUTPUT,
    'product/reviews/conversation.md', 'product/reviews/截图回读.md',
)


def author_prompt(project):
    source = project / 'synthetic-input'
    copy = shlex.join([sys.executable, str(source / 'copy_inputs.py')])
    check_copy = shlex.join([sys.executable, str(source / 'copy_inputs.py'), '--check'])
    boundary = shlex.join([sys.executable, str(source / 'boundary-probe.py'), 'author'])
    public = project / 'management/instances' / AUTHOR / 'workspace/public'
    direction_check = shlex.join([sys.executable, '-B', str(project / TONE_TOOL),
                                  '--project', str(public), '--contract', CONTRACT, '--draft'])
    capture_command = shlex.join([sys.executable, str(public / '_evaluation/capture_preview.py'),
        '--preview', SCENE, '--output', FIT_SCREENSHOT, '--state', '第3回合候选代表画面',
        '--artifact', SCENE, '--artifact', 'content/场内样句.md', '--artifact', PROFILE])
    return f"""本次是隔离专家准入。业务输入是合成夹具，尚无真人批准。仅本次会话；禁止嵌套模型、子代理和其它CLI会话。
1. 在当前实例工作区实际运行：
   {boundary}
   {copy}
   越界成功即停止。复制命令返回的source/quote只说明固定输入的来源，不能当成对你新成果的批准。输入与方法冲突写进方向简报待决，不修改任何输入副本。
2. 定向读取experts/{IDENTITY['id']}/{IDENTITY['version']}/ENTRY.md、METHODS.md、REVIEW.json的P-1映射，产品profession的P-1及当前DIRECTION-SAMPLE/PRACTICE-PROFILES/STAGE-GATES所需条款。业务见synthetic-input/genre-dice.md；两项外部参照见external-references.json，只读摘要须注明未直接访问。
3. 实际查看附入1280×800 PNG，写截图回读.md具体对象、位置、动作关系与限制。它是准备者从候选HTML真实截图的设计输入，没有证明实际可玩性。自己形成做法档、方向简报、方向契约和至少六条覆盖四时刻的样句（moment/text/consequence）。只交回下列文件：
{chr(10).join('- '+name for name in PUBLIC_FILES)}
固定参照仅在{source/seed.SCENE}、{source/seed.SCREENSHOT}、{source/seed.CAPTURE}，不可写且不复制为作者成果。你自己制作可点{SCENE}；契约scene/preview均为{SCENE}，screenshot为{PREVIEW_SCREENSHOT}。viewport=1280x800，capture_binding必须逐字段取下述真实采图返回值，不另写method/source或手工拼回执。契约不得包含confirmation，禁止声称真人批准。作者自检单独写{AUTHOR_SELF}，不生成独立fit。
4. 可点预览完成后，先亲自采契约图：
   {shlex.join([sys.executable,str(public/'_evaluation/capture_preview.py'),'--preview',SCENE,'--output',PREVIEW_SCREENSHOT,'--state','作者P-1可点首稿代表画面','--artifact',SCENE])}
   将返回的capture_binding原样用于契约，receipt实际生成{PREVIEW_CAPTURE}。四份业务材料完成后，再亲自请求fit新图：
   {capture_command}
scene和preview同文件，artifacts去重合法。回执会生成{FIT_CAPTURE}；不得改body；读取新PNG，在作者自检写实际观察。此采集不代写契约和结论。
5. 单独实际运行（不合并其它命令），保存成功delivery：
   {direction_check}
6. 阶段模板{STAGE_STATE}须role=product,current=P-1,next=P-2,scope=["race"],blockers只写阻止当前P-1业务通过的真实未决；待独审、待控制器合成确认是后续流程，写在作者自检pending，不能作为blockers；业务未决不得藏匿或清空。artifacts和tone_contract绑定真实业务；conversation_check引用现有conversation.md；request/response/tone_fit_review写待独审后控制器补齐的相对路径。P-1 completion关卡将在实际独审之后运行，此时不得补造批准/独审或passed。
先运行只读阶段预检：{shlex.join([sys.executable,str(source/'import_preflight.py'),'--project',str(project),'--author-public',str(public)])}。它不替代独审或最终关卡。
7. 本会话收尾前实际运行 `{check_copy}`，发现差异只报告，不恢复或改写副本。可信控制器随后真实交回并退出，另一实例实际独审。"""


def reviewer_prompt(out, public, source, author, review_run_id, binding, contract):
    requirements = [dict(stage=row['stage'], requirement=row['requirement']) for row in contract['requirements']]
    tested = [row for row in requirements if row['stage'] == 'P-1']
    untested = [row for row in requirements if row['stage'] != 'P-1']
    metadata = dict(runner=RUNNER, run_id=author['id'], review_run_id=review_run_id, model=MODEL,
        methods_sha256=binding['methods_sha256'], tested_requirements=tested, untested_requirements=untested,
        framework_scenario=dict(stage_state=STAGE_STATE, reviewer=REVIEWER,
            author_stage=dict(path=(public/STAGE_STATE).relative_to(public.parents[4]).as_posix(),sha256=sha(public/STAGE_STATE)),
            fit=dict(path='management/instances/'+REVIEWER+'/workspace/public/'+FIT,sha256='写完实际fit后计算该文件摘要，不得照抄此占位'),
            contract_sha256=binding['contract_sha256'], mapping_sha256=binding['mapping_sha256']))
    return f"""你是原任务{author['task_id']}的真实独立checker={REVIEWER}，本次check-run={review_run_id}。一次会话；禁止嵌套模型、其它CLI、子代理，禁止改作者或专家包。
实际读{source}/source/SKILL.md的P-1、METHODS.md/REVIEW.json映射、作者public原件{public}、{out}/author-boundary.json及原shell轨迹（定向读取）。核对方法保留、真实写隔离、待审交回；先查AUTHOR的真实handover摘要。
实际查看附入新fit PNG，并读取其采集回执{public/FIT_CAPTURE}及原方向图，检查四材料的当前hash、动作/规则后果、对象位置、语气和偏离。合成输入/准备者旧截图/作者新采图分清；记录未观察项。
在自己的workspace/public/{FIT}写独立贴合：producer={AUTHOR},checker={REVIEWER},mode=independent,review_task={author['task_id']},binding_mode=pre_confirmation_direction。tone_contract用作者draft的规范direction_binding（排除confirmation），artifacts用scene/preview/samples/practice_profile真实逻辑ref，screenshot引用design/fit.png，viewport必须明确填写1280x800（与作者方向契约同视口），capture_binding精确取作者{FIT_CAPTURE}内容除screenshot_sha256外各字段，并receipt指其逻辑path/sha。不得重写图片或回执。genre_fit/application_drift/copy_fit/capture和outcome按实际填。
在自己的workspace/public/{REVIEW_REPORT}写完整原始准入报告：固定元信息如下（这些不是通过结论）：
{json.dumps(metadata,ensure_ascii=False,indent=2)}
加passed实际bool、checks三个键{CHECKS}各{{passed:bool,evidence:具体观察}}；framework_scenario加readback具体方向/图像/材料及缺口，不改stage_state。tested_requirements仅列真正覆盖的P-1，untested如实列其余；证据不足passed=false。报告与fit结论由你亲自写，控制器不会补passed或改报告。
收尾前实际执行只读fit预检：{shlex.join([sys.executable,str(public.parents[4]/'synthetic-input/import_preflight.py'),'--project',str(public.parents[4]),'--checker-public',str(public.parents[2]/REVIEWER/'workspace/public')])}。预检只核结构/真实当前材料，输出author_stage/fit实际摘要供报告绑定；不写你的文件，不提交review，不跳过最终身份/交回关卡。报告字段不得残留占位。
尚无完整synthetic确认/最终stage，故不声称已通过最终completion关卡；核对作者业务是否已足以供之后合成展示与同一关卡检查。禁止冒充真人批准、启用专家或专业质量认证。控制器将真实review交回你的原fit/report并退出，再派生纯控制view、运行同一gate/validate。"""


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
    images = [Path(arg.removeprefix('--image=')) for arg in command if arg.startswith('--image=')]
    require(images,'actual input image required')
    write_json(out / f'{phase}.command.json', {'argv': command, 'cwd': str(cwd), 'model': MODEL, 'effort': EFFORT,
                                               'timeout_seconds': SESSION_TIMEOUT,
                                               'image_inputs': [{'path':str(image),'sha256':sha(image)} for image in images]})
    with (out / f'{phase}.stdout.jsonl').open('w', encoding='utf-8') as stdout, (out / f'{phase}.stderr.log').open('w', encoding='utf-8') as stderr:
        result = boundary.run(project, iid, [], prompt, timeout=SESSION_TIMEOUT, stdout=stdout, stderr=stderr,
                              started=started, adapter=runner['adapter'], model=MODEL, effort=EFFORT, template=runner)
    write_json(out / f'{phase}.process.json', result)
    return result


def runner_with_image(runner, image):
    require(runner['argv'][-1] == '-' and image.is_file(), 'pinned stdin runner and real image required')
    return dict(runner, argv=[*runner['argv'][:-1], '--image=' + str(image), '-'])


def verify_author_capture(out, public, screenshot=FIT_SCREENSHOT, receipt=FIT_CAPTURE):
    """Only a broker event from this author phase authenticates the new fit image."""
    log=out/'author-capture-events.jsonl'
    require(log.is_file(),'no actual author capture broker event')
    matching=[]
    for line in log.read_text(encoding='utf-8').splitlines():
        row=json.loads(line)
        ref=row.get('capture_binding',{}).get('receipt',{})
        if (row.get('status')=='captured' and row.get('format')=='author-requested-capture/1'
            and row.get('screenshot')==screenshot and row.get('preview')==SCENE
            and row.get('sha256')==sha(public/screenshot)
            and ref.get('path')==receipt and ref.get('sha256')==sha(public/receipt)):
            matching.append(row)
    require(matching,'author fit PNG/receipt do not match an actual broker capture')
    # Identical-input recapture can reproduce identical PNG and receipt bytes.
    # Every match still authenticates the current paths and both current hashes.
    return matching[-1]


def author_handover(pm, project, out, public, run_id, delivery_receipts):
    """Hand back an unconfirmed draft; independent completion follows the checker."""
    paths = verified_files(public)
    seed.check_inputs(project / 'synthetic-input', public)
    gate = pm.admission.load_gate()
    tone = gate.tone.read(public, CONTRACT)
    require(not tone.get('confirmation'), 'author must not prefill confirmation for unseen results')
    require(tone['parts']['scene']['path'] == SCENE, 'undeclared scene output: use ' + SCENE)
    require(tone['parts']['preview']['path'] == SCENE, 'undeclared preview output: use ' + SCENE)
    require(tone['parts']['screenshot']['path'] == PREVIEW_SCREENSHOT, 'use the actual broker-authenticated author screenshot')
    require({ref['source'] for ref in REFERENCES} <= {ref['source'] for ref in tone['references']},
            'name the two actual external game references with their sources')
    state = read_json(public / STAGE_STATE)
    require(state.get('blockers')==[], 'business blockers must be resolved before independent review; retain the unmodified stage')
    require((state.get('role'), state.get('current'), state.get('next'), state.get('scope')) ==
            ('product','P-1','P-2',['race']), 'author stage must retain the bounded P-1 race scenario')
    allowed = set(PUBLIC_FILES)
    refs = [part['path'] for part in tone['parts'].values()] + [item['path'] for item in state['artifacts']]
    refs += [state['tone_contract']['path'], state['conversation_check']]
    require(set(refs) <= allowed, 'undeclared framework output: ' + ', '.join(sorted(set(refs)-allowed)))
    direction_delivery = gate.tone.direction_delivery(tone)
    require(direction_delivery in delivery_receipts, 'no actual author --draft receipt matches the handed direction')
    for ref in [*tone['parts'].values(), *state['artifacts'], state['tone_contract']]:
        gate.tone.evidence.verify_ref(public, ref)
    preview_capture=verify_author_capture(out,public,PREVIEW_SCREENSHOT,PREVIEW_CAPTURE)
    require(tone.get('capture_binding')==preview_capture['capture_binding'], 'contract must use the actual preview capture_binding unchanged')
    verify_author_capture(out,public)
    capture = read_json(public / FIT_CAPTURE)
    observed = [tone['parts'][key] for key in ('scene','preview','samples','practice_profile')]
    expected = {(ref['path'],ref['sha256']) for ref in observed}
    require({(ref['path'],ref['sha256']) for ref in capture['artifacts']} == expected
            and capture['screenshot_sha256'] == sha(public/FIT_SCREENSHOT), 'fit capture must bind the actual four author materials')
    write_json(out / 'author-draft-precheck.json', dict(matching_author_delivery=direction_delivery,
        completion_gate='pending_actual_independent_review', files={path.relative_to(public).as_posix():sha(path) for path in paths}))
    pm_call(pm, project, out, 'hand_over', actor=AUTHOR, run=run_id,
        evidence=[path.relative_to(project).as_posix() for path in paths],
        summary='Unconfirmed author draft; actual independent checker and control projection pending.')
    return paths


def prepare_source_context(pm,project,out,manifest):
    """Explicit isolated synthetic source intake, never installed-rule relabelling."""
    def call(op,by=None,**fields):
        return pm_call(pm,project,out,op,actor=by or 'PM',**fields)
    business=(project/'synthetic-input/genre-dice.md').read_text(encoding='utf-8')
    bounded=author_prompt(project)+'\n\n## Actual bounded synthetic business input\n'+business
    (out/'bounded-source-prompt.md').write_text(bounded,encoding='utf-8')
    context,master=admitted_sources(pm,project,manifest,IDENTITY,MODEL,bounded,'import-probe-p1',call)
    write_json(out/'source-context.json',dict(synthetic=True,source_context=context,source_master=master,
        files={path:sha(project/path) for path in [*context['inputs'],context['stage_transition']]},
        limit='Synthetic controller source readback and upstream source confirmation; no professional quality or production human approval.'))
    return context


def author_task(project,source_context):
    require(isinstance(source_context,dict) and set(source_context)=={'inputs','admitted_inputs','stage_transition'},
        'prepared admitted source_context required; business input cannot become an installed rule')
    public=project/'management/instances'/AUTHOR/'workspace/public'
    return dict(id=TASK_ID,title='SYNTHETIC isolated product admission',owner=AUTHOR,executor=AUTHOR,checker=REVIEWER,
        goal='Complete one bounded P-1 candidate framework exercise; no production activation',**source_context,
        outputs=[(public/name).relative_to(project).as_posix() for name in PUBLIC_FILES],
        practice_stage=dict(role='product',current='P-1',scope=['race']),
        criteria=['Actual artifacts and independent review required'],next_action='Run the bounded admission')


def prepare_author_instances(pm,project,out,boundary):
    with pm.connect(project,readonly=True) as db:
        instances=pm.integrity.records(db,'instance')
    for iid,endpoint in ((AUTHOR,'SIM-isolated-admission'),(REVIEWER,'SIM-isolated-independent-review')):
        workspace=boundary.safe_workspace(project,iid)
        if iid in instances:
            require(instances[iid].get('active',True),'existing admission instance is inactive')
            continue
        pm_call(pm,project,out,'register_instance',id=iid,
            instance=dict(role='product',endpoint=endpoint,write_roots=[workspace.relative_to(project).as_posix()]))


def prepare_author_task(pm,project,out,boundary,source_context):
    prepare_author_instances(pm,project,out,boundary)
    result=pm_call(pm,project,out,'create',task=author_task(project,source_context))
    with pm.connect(project,readonly=True) as db:
        task=pm.task_map(db)[TASK_ID]
    require(task['state']=='planned','source admission preflight must not launch a model')
    write_json(out/'task-create-preflight.json',dict(task=task,model_sessions=0,source_context=source_context))
    return dict(id=TASK_ID,state='planned',source_context=source_context)


def run_author(pm, project, out, boundary, runner, binding, source_context):
    rid = 'import-admission-' + uuid.uuid4().hex
    tid = TASK_ID
    workspace = boundary.safe_workspace(project, AUTHOR)
    public = workspace / 'public'
    expected=author_task(project,source_context)
    with pm.connect(project,readonly=True) as db:
        task=pm.task_map(db).get(tid)
    require(task and task['state']=='planned' and all(task.get(key)==value for key,value in expected.items()),
        'prepared actual admission task or source_context changed before execution')
    runner = runner_with_image(runner, project / 'synthetic-input' / seed.SCREENSHOT)
    command = boundary.command_template(project, workspace, [], runner, MODEL, EFFORT)[0]
    base = project / 'experts' / IDENTITY['id'] / IDENTITY['version']
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
        with CaptureBroker(public, out / 'author-capture-events.jsonl'):
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


def run_reviewer(pm, out, project, boundary, runner, author, public, base, binding):
    workspace = boundary.safe_workspace(project, REVIEWER)
    review_public = workspace / 'public'
    rid = 'import-review-' + uuid.uuid4().hex
    runner = runner_with_image(runner_with_image(runner,project/'synthetic-input'/seed.SCREENSHOT),public/FIT_SCREENSHOT)
    command = boundary.command_template(project, workspace, [], runner, MODEL, EFFORT)[0]
    pm_call(pm, project, out, 'launch_start', id=rid, task_id=author['task_id'], purpose='check', instance=REVIEWER,
        model=MODEL, session=rid, command=command)
    started = False
    exited = False
    def record_start(pid):
        nonlocal started
        pm_call(pm, project, out, 'launch_started', id=rid, pid=pid)
        started = True
    try:
        reserve(LEDGER / 'reviewer.json', dict(out=str(out),author_run=author['id'],run_id=rid,model=MODEL,effort=EFFORT))
        contract = pm.team.experts.framework_contract(pm.api(),project,'product')
        result = run_session(out,project,boundary,REVIEWER,runner,
            reviewer_prompt(out,public,base,author,rid,binding,contract),'reviewer',started=record_start)
        try:
            require(result['exit_code']==0 and not result['timed_out'] and turn_completed(trace_events(out/'reviewer.stdout.jsonl')),
                'reviewer did not complete the single allowed session')
            paths = [review_public/name for name in (FIT,REVIEW_REPORT)]
            require(all(path.is_file() and path.resolve()==path and path.stat().st_nlink==1 for path in paths), 'actual reviewer fit/report missing')
            report = read_json(review_public/REVIEW_REPORT)
            require(report.get('review_run_id')==rid and report.get('run_id')==author['id'], 'review report must bind the actual runs')
            with pm.connect(project,readonly=True) as db:
                task=pm.task_map(db)[author['task_id']]
            pm_call(pm,project,out,'review',actor=REVIEWER,task_id=task['id'],expected_revision=task['revision'],
                outcome='passed' if report.get('passed') is True else 'failed',criteria_checked=task['criteria'],
                evidence=[path.relative_to(project).as_posix() for path in paths],
                **({} if report.get('passed') is True else dict(cause='other',reason='Independent report did not pass')))
        finally:
            pm_call(pm,project,out,'launch_exit',actor='launcher',id=rid,exit_code=result['exit_code'])
            exited=True
    except BaseException as error:
        if not exited:
            pm_call(pm,project,out,'launch_lost' if started else 'launch_failed',
                **(dict(actor='scheduler',id=rid,evidence=type(error).__name__) if started else dict(id=rid,error=type(error).__name__)))
        raise
    require(report.get('passed') is True, 'independent reviewer did not pass; originals retained')
    return pm.team.experts.validation_run(pm.api(),project,rid), review_public/REVIEW_REPORT


def synthetic_direction_attention(pm,project,out,author,reviewer,draft,display,reply,quote,request_id,contract_path=CONTRACT):
    """Use the ordinary PM sample/display API; every new sample task stays planned."""
    with pm.connect(project,readonly=True) as db:
        instances=pm.integrity.records(db,'instance');task=pm.task_map(db)[author['task_id']]
    masters=[row['id'] for row in instances.values() if row.get('active') and row.get('master') and row.get('profession')=='product']
    require(masters,'an already appointed product master is required for the synthetic combined display')
    master=masters[0];require(len({master,author['instance'],reviewer})==3,'actual producer, fit checker and planned-task checker must be distinct')
    require(task.get('admitted_inputs'),'the real admitted brief is required for this one combined display')
    origins=[]
    for source,expected in author['handover']['files'].items():
        logical=(project/source).relative_to(project/'management/instances'/author['instance']/'workspace/public').as_posix()
        target=project/logical
        require(not target.exists() or sha(target)==expected,'synthetic display cannot overwrite another project artifact')
        target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(project/source,target)
        origins.append(dict(source_path=source,display_source=logical,sha256=expected))
    key='SYNTHETIC-P1-'+uuid.uuid4().hex[:16]
    result=pm_call(pm,project,out,'direction_sample',id=key,brief=task['inputs'][0],admitted_inputs=task['admitted_inputs'],
        profile=draft['profile'],person='SYNTHETIC controller fixture',combined_review_authorization='SYNTHETIC isolated P-1 capability display only; no production milestone completion',
        assigned={'product':master,'fit_checker':reviewer,'task_checker':author['instance']})
    sample=result['direction_sample'];compose=project/sample['outputs']['compose'];compose.parent.mkdir(parents=True,exist_ok=True)
    payload=(project/'management/instances'/author['instance']/'workspace/public'/contract_path).read_bytes()
    require(not compose.exists() or compose.read_bytes()==payload,'synthetic compose source cannot replace prior business bytes')
    compose.write_bytes(payload)
    origins.append(dict(source_path=(project/'management/instances'/author['instance']/'workspace/public'/contract_path).relative_to(project).as_posix(),display_source=sample['outputs']['compose'],sha256=sha(compose)))
    scope=[row['id'] for row in pm.admission.load_gate().tone.profile(project,draft)['scopes']]
    display_scope='SYNTHETIC P-1 capability display: '+', '.join(scope)
    pm_call(pm,project,out,'human_attention',id=request_id,kind='confirmation',task_id=key,display=display['path'],scope=display_scope,
        inputs=[row['display_source'] for row in origins])
    pm_call(pm,project,out,'human_attention',id=request_id,response=reply['path'])
    binding=pm.admission.load_gate().tone.direction_binding(contract_path,draft)
    with pm.connect(project) as db:
        receipt=pm.direction.bind_attention(pm.api(),project,db,request_id,person='SYNTHETIC controller fixture',quote=quote,scope=display_scope,
            expected={'direction_sha256':binding['direction_sha256'],'task_id':key})
    with pm.connect(project,readonly=True) as db:
        planned={name:pm.task_map(db)[name]['state'] for name in [key,*sample['tasks']]}
    require(set(planned.values())=={'planned'},'the synthetic display must not complete or launch the PM project tasks')
    write_json(out/'synthetic-display-origin.json',dict(sample_id=key,origin_files=origins,tasks=planned,missing_roles=sample['missing_roles'],
        limit='One synthetic display only. Existing actual author/checker handbacks remain the evidence; no PM milestone closure is claimed.'))
    return receipt


def assemble_scenario(pm, project, out, author, review_run, report_path,
                      contract_path=CONTRACT, stage_template=STAGE_STATE, fit_path=FIT, state_path=STAGE_STATE):
    """Derive six control records from separately trusted real producer handbacks."""
    expert,gate=pm.team.experts,pm.admission.load_gate()
    tone=gate.tone
    report_ref=report_path.relative_to(project).as_posix()
    report=read_json(report_path)
    require(report.get('passed') is True and report.get('review_run_id')==review_run['id'], 'controller cannot create or repair a passing report')
    with pm.connect(project,readonly=True) as db:
        reviewed=expert.independent_review(pm.api(),project,author,report,report_ref,db)
    author_public=project/'management/instances'/author['instance']/'workspace/public'
    review_public=report_path.parent
    view=project/'management/scenario-draft'
    view.mkdir(parents=True,exist_ok=False)
    origins=[]
    for origin,files,public in (('author',author['handover']['files'],author_public),('review',reviewed['files'],review_public)):
        for source,expected in sorted(files.items()):
            source_file=project/source
            require(sha(source_file)==expected, 'raw producer handback changed: '+source)
            logical=source_file.relative_to(public).as_posix()
            if origin=='author' and logical==contract_path: logical='_original/author-direction.md'
            if origin=='author' and logical==stage_template: logical='_original/author-stage.json'
            if source_file==report_path: logical='_original/reviewer-report.json'
            target=view/logical
            require(not target.exists(), 'producer logical paths overlap: '+logical)
            target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source_file,target)
            origins.append(dict(logical_path=logical,source_path=source,sha256=expected,origin=origin))
    draft,outer=expert.contract_content(author_public/contract_path)
    require(not draft.get('confirmation'), 'author draft must remain unconfirmed')
    original=read_json(author_public/stage_template)
    require(original['current']=='P-1', 'synthetic control projection is restricted to P-1')
    binding=tone.direction_binding(contract_path,draft)
    before_fit=sha(view/fit_path)
    material_hashes={draft['parts'][key]['path']:draft['parts'][key]['sha256'] for key in ('scene','preview','samples','practice_profile')}
    def put(path,data):
        target=view/path;target.parent.mkdir(parents=True,exist_ok=True)
        if isinstance(data,dict):write_json(target,data)
        else:target.write_text(data,encoding='utf-8')
        return tone.evidence.ref(view,path)
    display_path='product/reviews/synthetic-display.md'
    reply_path='product/reviews/synthetic-response.md'
    display_text='# SYNTHETIC isolated P-1 display; no production human approval\n\n'+json.dumps(dict(
        direction_binding=binding,author_files=author['handover']['files'],review_files=reviewed['files'],
        independent_report_sha256=sha(report_path),scope=original['scope']),ensure_ascii=False,indent=2)+'\n'
    display=put(display_path,display_text)
    quote='SYNTHETIC isolated exercise only: approve displayed direction '+binding['direction_sha256']+' and display '+display['sha256']+' for '+json.dumps(original['scope'],ensure_ascii=False)+'. No production human approval.'
    reply=put(reply_path,quote+'\n')
    # Root authority records bind this exact display and response, never the draft's old quote.
    for ref in (display,reply):
        destination=project/ref['path'];destination.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(view/ref['path'],destination)
    request_id='SIM-'+uuid.uuid4().hex
    approval=dict(format='matrix-review-binding/1',request_id=request_id,scope=original['scope'],actor='user',
        direction_sha256=binding['direction_sha256'],display=display,
        response=dict(reply,message_sha256=tone.evidence.digest(quote)),person='SYNTHETIC controller fixture',quote=quote,outcome='approved')
    receipt=synthetic_direction_attention(pm,project,out,author,reviewed['reviewer'],draft,display,reply,quote,request_id,contract_path)
    final=dict(draft,confirmation=dict(person=approval['person'],quote=quote,source=reply_path,
        direction_sha256=binding['direction_sha256'],review_receipt=receipt))
    # Preserve markdown outside the one JSON block exactly.
    text=(author_public/contract_path).read_text(encoding='utf-8')
    match=re.search(r'^```tone-contract\s*\n(.*?)^```\s*$',text,re.M|re.S)
    require(match is not None,'one author direction block required')
    final_text=text[:match.start(1)]+json.dumps(final,ensure_ascii=False,indent=2)+'\n'+text[match.end(1):]
    final_ref=put(contract_path,final_text)
    artifacts=[dict(ref,sha256=final_ref['sha256']) if ref['path']==contract_path else ref for ref in original['artifacts']]
    artifact_sha=gate.artifact_digest(view,artifacts)
    request=dict(request_id=request_id,role=original['role'],stage=original['current'],scope=original['scope'],
        artifact_sha256=artifact_sha,display_evidence=display_path,display_sha256=display['sha256'])
    response=dict(request_id=request_id,actor='user',choice='confirm',scope=original['scope'],artifact_sha256=artifact_sha,
        source=reply_path,quote=quote,display_sha256=display['sha256'],message_sha256=approval['response']['message_sha256'])
    request_ref=put('product/reviews/request.json',request);response_ref=put('product/reviews/response.json',response)
    stage=dict(original,artifacts=artifacts,tone_contract=dict(original['tone_contract'],sha256=final_ref['sha256']),
        request=request_ref['path'],response=response_ref['path'],tone_fit_review=fit_path)
    stage_ref=put(state_path,stage)
    controls=[]
    for kind,ref,source,diff in (
        ('contract_confirmation',final_ref,(author_public/contract_path).relative_to(project).as_posix(),expert.control_diff(draft,final)),
        ('stage',stage_ref,(author_public/stage_template).relative_to(project).as_posix(),expert.control_diff(original,stage)),
        ('request',request_ref,None,expert.control_diff({},request)),('response',response_ref,None,expert.control_diff({},response)),
        ('display',display,None,[]),('synthetic_response',reply,None,[])):
        row=dict(kind=kind,logical_path=ref['path'],sha256=ref['sha256'],diff=diff)
        if source:row['source_path']=source
        controls.append(row)
    require(tone.direction_binding(contract_path,final)==binding and sha(view/fit_path)==before_fit,
        'control projection changed independent fit or canonical direction')
    require(all(sha(view/path)==expected for path,expected in material_hashes.items()), 'control projection changed business material')
    context=dict(format='matrix-admission-scenario/1',author_run_id=author['id'],review_run_id=review_run['id'],
        state_path=state_path,origins=origins,control_derivations=controls)
    refs=[tone.evidence.ref(view,file.relative_to(view).as_posix()) for file in view.rglob('*') if file.is_file()]
    local=tone.evidence.seal_bundle(view,refs,context,destination='sealed',follow_refs=False)
    result=dict(local,path=(view/local['path']).relative_to(project).as_posix())
    frozen,_=tone.evidence.verify_bundle(project,result)
    checked=gate.check(frozen,stage,registry_root=project,seal=False)
    completed,required=gate.framework_outputs(frozen,stage,checked,registry_root=project)
    write_json(out/'gate-precheck.json',dict(checked=checked,completed=completed,required_outputs=sorted(required)))
    write_json(out/'scenario-projection.json',dict(scenario_view=result,context=context,canonical_direction=binding,
        author_contract_sha256=sha(author_public/contract_path),projected_contract_sha256=final_ref['sha256'],
        independent_fit_sha256=before_fit,material_hashes=material_hashes,synthetic=True,
        limit='Control view is not author original. No real human approval or controller professional conclusions.'))
    return result


def execute(kit, out, freeze_sha256):
    plan = read_json(out / 'prepared.json')
    require(plan['kit_manifest_sha256'] == freeze_sha256 == sha(kit / 'MANIFEST.json'),
            'prepared kit differs from the authorized frozen candidate digest')
    require(plan['runner_template_sha256'] == sha(TEMPLATE) and plan['probe_sha256'] == sha(Path(__file__)),
            'runner template or probe changed since preparation')
    require(plan.get('instrument_hashes')==instrument_hashes(),'prepared probe or capture instrumentation changed')
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
    author_task(project,plan.get('source_context'))
    require(sha(out/'source-context.json')==plan.get('source_context_sha256')
            and sha(out/'task-create-preflight.json')==plan.get('task_preflight_sha256'),'prepared source context or task preflight record changed')
    source_record=read_json(out/'source-context.json')
    require(source_record.get('synthetic') is True and source_record['source_context']==plan['source_context'], 'explicit synthetic source context changed')
    require(all(sha(project/path)==expected for path,expected in source_record['files'].items()),'prepared admitted source bytes changed')
    reserve(LEDGER / 'execution.json', {'out': str(out), 'kit_manifest_sha256': freeze_sha256, 'max_sessions': 2,
                                       'timeout_seconds': SESSION_TIMEOUT,
                                       'authorization_scope': 'v0.37 repaired candidate-only imported product; fresh author and independent reviewer; no retry'})
    try:
        author, public, base = run_author(pm, project, out, boundary, runner, binding,plan['source_context'])
        review_run,report_path = run_reviewer(pm,out,project,boundary,runner,author,public,base,binding)
        require(pm.team.experts.admission_binding(pm.api(),project,IDENTITY)==binding,'adaptation changed after execution')
        scenario_view=assemble_scenario(pm,project,out,author,review_run,report_path)
        platform_call(api,project,out,'expert.validate',dict(IDENTITY,evidence=dict(runner=RUNNER,
            report=report_path.relative_to(project).as_posix(),source_sha256=binding['methods_sha256'],scenario_view=scenario_view)))
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
