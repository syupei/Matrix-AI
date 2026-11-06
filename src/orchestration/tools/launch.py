#!/usr/bin/env python3
"""Launch command: the PM starts one platform run of an instance (start, check or attend), and the run wrapper records
how it ended. The host command comes from the project's management/runtime/platform.json; nothing is installed.

  launch.py --project . --task T [--purpose start|check|attend] [--tasks T1,T2] [--event-id ID] [--options JSON]
  launch.py --project . --stop LAUNCH-ID --reason TEXT     (stop a run: kills its process group, records the exit)
  launch.py --project . --run LAUNCH-ID                    (internal: the detached wrapper that runs the host command)
"""
import argparse
import gzip
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import uuid

TOOLS = Path(__file__).resolve().parent
PLATFORM = 'management/runtime/platform.json'
LOGS = 'management/runtime/logs/'
# Common search tools skip what .ignore lists: run logs and the task database never come back from a search.
IGNORE = 'runtime/logs/\nruntime/*.sqlite3*\n'
PLACEHOLDERS = {'model', 'session', 'prompt_file', 'prompt', 'instance', 'workspace', 'task', 'write_permissions'}


def load_pm():
    spec = importlib.util.spec_from_file_location('launch_pm_tasks', TOOLS / 'pm_tasks.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def settings(pm, root):
    """The project's platform settings; the host command is a template the person set up (example in START.md)."""
    path = pm.local(root, PLATFORM)
    pm.require(path.is_file(), PLATFORM + ' missing: platform runs are not set up in this project')
    data = json.loads(path.read_text(encoding='utf-8'))
    pm.require(pm.strings(data.get('launch')) and data['launch'], PLATFORM + ': launch must be the host command as a list of strings')
    pm.require(data.get('prompt', 'stdin') in {'stdin', 'arg'}, PLATFORM + ': prompt is stdin or arg')
    pm.require(isinstance(data.get('models', {}), dict), PLATFORM + ': models maps configured model names to host model names')
    pm.require(pm.strings(data.get('write_patterns', [])), PLATFORM + ': write_patterns must be strings with {root}')
    return data


def launch_record(pm, root, rid):
    db = pm.connect(root, readonly=True)
    try:
        return pm.integrity.records(db, 'launch').get(rid)
    finally:
        db.close()


def fill(template, values):
    out = []
    for part in template:
        for key in PLACEHOLDERS:
            part = part.replace('{' + key + '}', str(values.get(key, '')))
        out.append(part)
    return out


def skills(root, profession):
    """Installed skill files of a profession, under the skills folder recorded at installation."""
    receipt = root / 'management/install-receipt.json'
    folders = [json.loads(receipt.read_text(encoding='utf-8')).get('skills_dir')] if receipt.is_file() else []
    folders += ['.agents/skills', '.claude/skills']
    reg = root / 'matrix/professions' / profession / 'profession.json'
    names = json.loads(reg.read_text(encoding='utf-8'))['skills'] if reg.is_file() else ['matrix-' + profession]
    found = []
    for name in names:
        hit = next((f + '/' + name + '/SKILL.md' for f in folders if f and (root / f / name / 'SKILL.md').is_file()), None)
        if hit:
            found.append(hit)
    return found


def bullet(items):
    return '；'.join(items) if items else '—'


def packet(pm, root, rid, purpose, inst, tasks, stops):
    """The task packet the instance reads: who it is, the one job of this run and how to report through the task tool."""
    iid, t = inst['id'], tasks[0]
    regs = pm.team.registries(pm, root)
    profession = regs.get(inst.get('profession'), {}).get('name', inst.get('profession') or inst.get('role'))
    who = iid + '（' + str(profession) + ('，' + inst['level'] if inst.get('level') else '') + ('，master' if inst.get('master') else '') + '）'
    reads = skills(root, inst.get('profession') or inst.get('role')) + ['management/instances/' + iid + '/profile.md']
    head = ['# 任务包 ' + rid + '（平台运行：' + pm.platform.PURPOSES[purpose] + '）', '',
            '你是本项目的 ' + who + '。平台为下面的事拉起你；只做这件事，做完或受阻就结束本次运行。', '',
            '- 工作目录是项目根目录。先读：' + bullet(reads) + '（有几个技能的，按任务所在阶段选用）；其余规则按技能的指引索引用到时再打开。'
            '汇报只用下面写好的命令，不必读任务工具的说明；不搜索项目里的运行记录。',
            '- 只写自己的工作区 management/instances/' + iid + '/workspace/ 与登记的写入范围（' + bullet(inst.get('write_roots', [])) + '），检查点也放在工作区。'
            '不联网，不安装软件，不启动其他 Agent，不改别人的成果与记录。',
            '- 任务工具：python3 matrix/orchestration/tools/pm_tasks.py --project . --command <命令文件>（命令文件写在你的工作区），actor 写 ' + iid + '。'
            '只需查看一项任务时用 {"op":"task","id":"<任务ID>"}。', '']
    body = []
    if purpose == 'start':
        back = t.get('sent_back')
        body += ['## 任务 ' + t['id'] + '：' + t['title'], '', '- 目标：' + t['goal'], '- 输入：' + bullet(t['inputs']), '- 成果：' + bullet(t['outputs']),
                 '- 判据：' + bullet(t['criteria']), '- 下一步：' + t['next_action']]
        if back:
            body.append('- 返工：上次检验没过（原因：' + back['cause'] + '，检验：' + back['checker'] + '）。按检验意见在原任务上改，不另起新任务。')
        body += ['', '## 回报', '',
                 '- 交出（自检完成）：{"op":"hand_over","actor":"' + iid + '","event_id":"' + rid + '-handover","run":"' + rid + '",'
                 '"evidence":["<成果与证据的路径>"],"summary":"<一句话说明>"}',
                 '- 受阻：{"op":"report_blocked","actor":"' + iid + '","event_id":"' + rid + '-blocked","run":"' + rid + '","reason":"<卡在哪、需要谁做什么>"}',
                 '- 要拆给别人做的：按你的任职建子任务（见 matrix/orchestration/TASK-TOOL.md），写一条 report 说明拆分，然后结束本次运行；子任务交出后平台会再拉起你检验。',
                 '- 不写"完成"：交出后由派发者检验、采用。']
    elif purpose == 'check':
        body += ['## 待你检验', '']
        for x in tasks:
            body.append('- ' + x['id'] + '（revision ' + str(x['revision']) + '）：' + x['title'] + '；成果与证据：' + bullet(x['evidence']) + '；判据：' + bullet(x['criteria']))
        body += ['', '逐项按判据检验，每项写一条：{"op":"review","actor":"' + iid + '","event_id":"' + rid + '-review-<任务ID>","task_id":"<任务ID>",'
                 '"expected_revision":<上面的 revision>,"outcome":"passed 或 failed","criteria_checked":[<判据原文>],"evidence":["<检验记录路径>"],'
                 '"cause":"<failed 时写 execution、requirement_clarification、basis_changed 或 other>"}',
                 '你也是派发者的：通过且不需要人审的，采用并关闭（"op":"transition","state":"done","reason":"检验通过，采用"）；需要人审的不关闭。']
    else:
        body += ['## 由你派发、停住了的任务', '']
        for x in tasks:
            s = stops.get(x['id'], {})
            body.append('- ' + x['id'] + '（revision ' + str(x['revision']) + '）：' + x['title'] + '；停因：' + s.get('label', x['state']) + '；状态说明：' + (x.get('reason') or '—'))
        body += ['', '逐项决定，用任务工具记录（见 matrix/orchestration/TEAM-LEAD.md 与 TASK-TOOL.md）：',
                 '- 结束未交出：先看执行者工作区的检查点，再决定重做（transition 回 planned，写原因）或改派（reassign）；',
                 '- 检验没过：安排返工（transition 回 planned）或改派；超过返工、改派上限的，写明情况上报 PM，不再自行返工；',
                 '- 依据已变：按当前的任务与输入重新检验，或回到 planned 重做；',
                 '- 等派发者采用：核对后采用并关闭；受阻或前置未满足：处理能处理的，处理不了的上报。']
    text = '\n'.join(head + body) + '\n'
    path = 'management/instances/' + iid + '/runs/' + rid + '.md'
    pm.atomic(pm.local(root, path), text)
    return path, text


def launch(project, task_id, purpose='start', task_ids=None, event_id=None, options=None, actor=None):
    """Record a run and start it (or leave it for the scheduler to start); actor is the PM, or the scheduler itself."""
    pm, root = load_pm(), Path(project).resolve()
    cfg_platform = settings(pm, root)
    status = pm.execute(root, {'op': 'status'})
    tasks = {t['id']: t for t in status['tasks']}
    ids = task_ids or [task_id]
    pm.require(all(i in tasks for i in ids), 'unknown task')
    t = tasks[ids[0]]
    iid = {'start': t.get('executor'), 'check': t['checker'], 'attend': t['manager']}.get(purpose)
    inst = status['integrity']['instance'].get(iid)
    pm.require(inst, 'the run needs a registered instance; ' + str(iid) + ' is not one')
    pm.require(pm.nonempty(inst.get('model')), iid + ' has no configured model; derive instances from the confirmed instance configuration')
    pm_actor = actor or status['config']['pm_actor']
    rid = 'run-' + (event_id or uuid.uuid4().hex[:12])
    event_id = event_id or rid
    old = launch_record(pm, root, rid)
    if old:
        return {'record': old, 'repeated': True}  # the same launch asked again: never a second process
    stops = pm.execute(root, {'op': 'continue', 'detail': True})['stops'] if purpose == 'attend' else {}
    prompt_file, text = packet(pm, root, rid, purpose, inst, [tasks[i] for i in ids], stops)
    session = str(uuid.uuid4())
    model = cfg_platform.get('models', {}).get(inst['model'], inst['model'])
    write = [p.replace('{root}', r.rstrip('/')) for r in inst.get('write_roots', []) for p in cfg_platform.get('write_patterns', [])]
    values = dict(model=model, session=session, prompt_file=prompt_file, prompt='读取 ' + prompt_file + ' 并按其执行。',
                  instance=iid, workspace='management/instances/' + iid + '/workspace', task=ids[0], write_permissions=','.join(write))
    command = fill(cfg_platform['launch'], values)
    log = LOGS + rid + '.log'
    ignore = pm.local(root, 'management/.ignore')
    if not ignore.is_file():
        ignore.write_text(IGNORE, encoding='utf-8')
    fields = dict(op='launch_start', actor=pm_actor, event_id=event_id, id=rid, purpose=purpose, task_id=ids[0], task_ids=ids,
                  instance=iid, model=model, session=session, command=command, log=log)
    fields.update({k: v for k, v in (options or {}).items() if k in {'rework_reason', 'note', 'attributed_to', 'escalation'}})
    record = pm.execute(root, fields)['record']
    if cfg_platform.get('spawn', 'launcher') == 'scheduler':
        # The host runs the PM in a sandbox whose children cannot reach the network: the scheduler starts the run.
        return {'record': record, 'packet': prompt_file, 'queued': True}
    return {'record': spawn(pm, root, record, pm_actor), 'packet': prompt_file}


def spawn(pm, root, record, actor):
    """Start the detached run wrapper of a recorded run and record its process, or that it did not start."""
    rid = record['id']
    try:
        path = pm.local(root, record['log'])
        path.parent.mkdir(parents=True, exist_ok=True)
        out = open(path, 'ab')
        proc = subprocess.Popen([sys.executable, '-B', str(Path(__file__).resolve()), '--project', str(root), '--run', rid],
                                cwd=root, stdin=subprocess.DEVNULL, stdout=out, stderr=out, start_new_session=True)
    except OSError as error:
        pm.execute(root, dict(op='launch_failed', actor=actor, event_id=rid + '-failed', id=rid, error=type(error).__name__ + ': ' + str(error)))
        raise
    return pm.execute(root, dict(op='launch_started', actor=actor, event_id=rid + '-started', id=rid, pid=proc.pid))['record']


def outcome(path):
    """The final message and the token usage a host printed as JSON lines (as Codex exec --json does); None when it did not."""
    message, usage, seen = None, {'input': 0, 'cached': 0, 'output': 0}, False
    for line in open(path, errors='ignore'):
        line = line.strip()
        if not line.startswith('{'):
            continue
        try:
            e = json.loads(line)
        except ValueError:
            continue
        item = e.get('item') or {}
        if item.get('type') == 'agent_message' and item.get('text'):
            message = item['text']
        if isinstance(e.get('result'), str):
            message = e['result']
        u = e.get('usage') if e.get('type') in {'turn.completed', 'result'} else None
        if isinstance(u, dict):
            seen = True
            usage['input'] += int(u.get('input_tokens', 0))
            usage['cached'] += int(u.get('cached_input_tokens', u.get('cache_read_input_tokens', 0)))
            usage['output'] += int(u.get('output_tokens', 0))
    return message, (usage if seen else None)


def pack(path):
    """Compress a finished log; the compressed file is kept for audits and is not read by searches."""
    with open(path, 'rb') as src, gzip.open(str(path) + '.gz', 'wb') as dst:
        dst.write(src.read())
    Path(path).unlink()


def record_exit(pm, root, rid, op, **fields):
    for attempt in range(20):  # the task database may be busy with another writer
        try:
            actor = pm.platform.LAUNCHER if op == 'launch_exit' else pm.platform.SCHEDULER
            return pm.execute(root, dict(op=op, actor=actor, event_id=rid + '-' + op, id=rid, **fields))
        except Exception as error:
            if 'locked' not in str(error) or attempt == 19:
                raise
            time.sleep(0.5)


def run(project, rid):
    """The detached wrapper: run the host command for one launch and record how it ended."""
    pm, root = load_pm(), Path(project).resolve()
    rec = launch_record(pm, root, rid)
    cfg_platform = settings(pm, root)
    prompt = pm.local(root, 'management/instances/' + rec['instance'] + '/runs/' + rid + '.md').read_text(encoding='utf-8')
    started = time.time()
    try:
        done = subprocess.run(rec['command'], cwd=root, input=prompt if cfg_platform.get('prompt', 'stdin') == 'stdin' else None,
                              text=True, stdout=sys.stdout, stderr=sys.stderr)
        code = done.returncode
    except OSError as error:
        print('launch ' + rid + ': host command failed to run: ' + str(error), file=sys.stderr)
        code = 127
    print('launch ' + rid + ': exited with code ' + str(code) + ' after ' + str(round(time.time() - started)) + ' s', flush=True)
    log = pm.local(root, rec['log'])
    message, usage = outcome(log) if log.is_file() else (None, None)
    result = 'management/instances/' + rec['instance'] + '/runs/' + rid + '-result.md'
    pm.atomic(pm.local(root, result), '# 运行 ' + rid + ' 的结果\n\n- 退出代码：' + str(code) + '\n- 用量（宿主报告）：' + json.dumps(usage) + '\n\n' + (message or '（宿主没有输出结束消息）') + '\n')
    record_exit(pm, root, rid, 'launch_exit', exit_code=code, **({'usage': usage} if usage else {}))
    if log.is_file():
        pack(log)


def stop(project, rid, reason):
    """Stop a run the PM decided not to wait for: end its process group, then record the exit with the reason."""
    pm, root = load_pm(), Path(project).resolve()
    rec = launch_record(pm, root, rid)
    pm.require(rec and rec['state'] in pm.platform.ACTIVE, 'active run required')
    pm.require(pm.nonempty(reason), 'reason required')
    if rec.get('pid'):
        try:
            os.killpg(rec['pid'], signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            pass  # a sandboxed PM may not signal it; the scheduler ends processes of runs no longer active
    return record_exit(pm, root, rid, 'launch_lost', evidence='stopped by the PM: ' + reason)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--project', type=Path, required=True)
    ap.add_argument('--task'); ap.add_argument('--tasks'); ap.add_argument('--purpose', default='start')
    ap.add_argument('--event-id'); ap.add_argument('--options'); ap.add_argument('--run'); ap.add_argument('--stop'); ap.add_argument('--reason')
    a = ap.parse_args()
    try:
        if a.run:
            run(a.project, a.run)
            return 0
        if a.stop:
            result = stop(a.project, a.stop, a.reason)
        else:
            ids = a.tasks.split(',') if a.tasks else None
            result = launch(a.project, a.task or (ids or [None])[0], a.purpose, ids, a.event_id, json.loads(a.options) if a.options else None)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError, KeyError) as error:
        print(json.dumps({'error': str(error)}, ensure_ascii=False))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
