#!/usr/bin/env python3
"""Live platform probe: installs a built kit into a new synthetic project, sets up a small team and lets the real
timer, PM and launch command run it with an actual host command line. Nothing is simulated except the project.

  team_live.py --source <built kit> --output <new dir> --host claude [--minutes 40]
  team_live.py --source <built kit> --output <new dir> --host stub      (path check without model calls)

Scenario (the scheduler starts the runs; the PM decides): A (product master) and C (content-design master) start in parallel; B (product master) depends on A and
starts only after the PM checked and adopted A. The PM is the checker of all three. No external project, real person, approval or isolation
is claimed; the receipt records every run, its model, its exit and the timer's log.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

TOOLS = 'matrix/orchestration/tools'
CONFIG = {'entries': [{'id': 'P-M', 'profession': 'product', 'level': 'T7', 'model': 'sonnet', 'count': 1, 'master': True},
                      {'id': 'C-M', 'profession': 'content-design', 'level': 'T6', 'model': 'haiku', 'count': 1, 'master': True}]}
PERMIT = 'Read,Glob,Grep,{write},Bash(python3 ' + TOOLS + '/pm_tasks.py:*)'


def host_settings(host, root):
    if host == 'claude':
        deny = ['--disallowedTools', 'WebFetch,WebSearch']
        worker = PERMIT.replace('{write}', '{write_permissions}')
        pm = PERMIT.replace('{write}', 'Edit(management/runtime/pm/**),Write(management/runtime/pm/**)') + ',Bash(python3 ' + TOOLS + '/launch.py:*)'
        return {'launch': ['claude', '-p', '--model', '{model}', '--session-id', '{session}', '--permission-mode', 'dontAsk', '--allowedTools', worker, *deny],
                'write_patterns': ['Edit({root}/**)', 'Write({root}/**)'],
                'pm': {'launch': ['claude', '-p', '--model', 'sonnet', '--session-id', '{session}', '--permission-mode', 'dontAsk', '--allowedTools', pm, *deny],
                       'resume': ['claude', '-p', '--resume', '{session}', '--permission-mode', 'dontAsk', '--allowedTools', pm, *deny]},
                'check_seconds': 20}
    stub = root / 'stub_host.py'
    stub.write_text(STUB, encoding='utf-8')
    return {'launch': [sys.executable, '-B', str(stub), 'worker', '--session', '{session}'],
            'pm': {'launch': [sys.executable, '-B', str(stub), 'pm', '--session', '{session}'],
                   'resume': [sys.executable, '-B', str(stub), 'pm', '--resume', '{session}']}, 'check_seconds': 5}


# Path check only: a worker that hands over, and a PM that does what continuation lists (start, check, adopt).
STUB = r'''
import json, re, subprocess, sys
from pathlib import Path
T = 'matrix/orchestration/tools/'
def call(cmd):
    return json.loads(subprocess.run([sys.executable, '-B', T + 'pm_tasks.py', '--project', '.'], input=json.dumps(cmd), capture_output=True, text=True).stdout)
text = sys.stdin.read()
if sys.argv[1] == 'worker':
    rid, iid = re.search(r'# 任务包 (\S+?)（', text).group(1), re.search(r'actor 写 (\S+?)。', text).group(1)
    tid = re.search(r'## 任务 (\S+?)：', text).group(1)
    out = 'management/instances/' + iid + '/workspace/' + tid + '.md'
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text('STUB result of ' + tid)
    call({'op': 'hand_over', 'actor': iid, 'event_id': rid + '-handover', 'run': rid, 'evidence': [out], 'summary': 'stub done'})
else:
    for n in range(30):  # the PM's own decisions only; the scheduler starts the runs
        act = next((a for a in call({'op': 'continue'})['actions'] if a['kind'] == 'pm' and a['code'] in {'review', 'adopt'}), None)
        if not act:
            break
        cmd = json.loads(act['command'])
        if act['code'] == 'review':
            cmd.update(outcome='passed', evidence=['BRIEF.md']); cmd.pop('cause')
        call(cmd)
'''


def run(*args, cwd=None, data=None):
    r = subprocess.run([sys.executable, '-B', *args], cwd=cwd, input=json.dumps(data) if data is not None else None, capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(' '.join(args[:2]) + ': ' + (r.stdout + r.stderr)[-800:])
    return json.loads(r.stdout) if r.stdout.strip().startswith('{') else r.stdout


def setup(source, root, host):
    run(str(source / 'install.py'), '--target', str(root), '--skills-dir', '.claude/skills', '--entry', 'CLAUDE.md', '--apply')
    n = 0
    def call(op, actor='PM', **kw):
        nonlocal n
        n += 1
        return run(TOOLS + '/pm_tasks.py', '--project', '.', cwd=root, data=dict(op=op, actor=actor, event_id='LIVE-' + str(n), **kw))
    (root / 'BRIEF.md').write_text('合成项目：内部意见箱。已确定：员工提交意见、管理员查看列表。未定：是否匿名、附件大小上限。'
                                   '只在自己的工作区写候选，不补未定的规则。', encoding='utf-8')
    call('init', config=dict(project='SYNTHETIC suggestion box', pm_actor='PM', authorization='BRIEF.md', frontdoor_id='LIVE-PROBE', max_slots=3))
    (root / 'management/instance-config.json').write_text(json.dumps(CONFIG), encoding='utf-8')
    call('confirm_config', person='SYNTHETIC-owner', quote='SYNTHETIC: 按这个配置试跑', presented_ref='BRIEF.md',
         choices={e['id']: 'acknowledge_unregistered' for e in CONFIG['entries']})
    for entry in ['P-M', 'C-M']:
        call('derive', entry=entry, endpoint='platform')
    common = dict(checker='PM', inputs=['BRIEF.md'], criteria=['只用 BRIEF.md 已确定的规则', '未定的列为待人决定'], next_action='制作候选')
    call('create', task=dict(id='A', parent=None, title='意见提交流程候选', owner='product-001', executor='product-001', goal='写意见提交的主流程与异常',
                             outputs=['流程候选（工作区内）'], **common))
    call('create', task=dict(id='C', parent=None, title='提交成功与失败的提示文字候选', owner='content-design-001', executor='content-design-001',
                             goal='写提交成功、失败与重试时的提示文字', outputs=['文字候选（工作区内）'], **common))
    call('create', task=dict(id='B', parent=None, title='验收情境候选', owner='product-001', executor='product-001', goal='按 A 的流程写验收情境',
                             outputs=['验收情境候选（工作区内）'], dependencies=['A'], **common))
    (root / 'management/runtime/platform.json').write_text(json.dumps(host_settings(host, root), ensure_ascii=False, indent=1), encoding='utf-8')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--source', type=Path, required=True); ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--host', choices=['claude', 'stub'], required=True); ap.add_argument('--minutes', type=float, default=40)
    a = ap.parse_args()
    source, output = a.source.resolve(), a.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    with tempfile.TemporaryDirectory(prefix='matrix-live-platform-') as temporary:
        root = Path(temporary)
        setup(source, root, a.host)
        timer = subprocess.Popen([sys.executable, '-B', TOOLS + '/scheduler.py', '--project', '.'], cwd=root,
                                 stdout=open(output / 'timer.stdout', 'w'), stderr=subprocess.STDOUT)
        end, status = time.time() + a.minutes * 60, {}
        try:
            while time.time() < end:
                status = run(TOOLS + '/pm_tasks.py', '--project', '.', cwd=root, data={'op': 'continue', 'detail': True})
                if status['stop'] in {'done', 'needs_human', 'idle'} and not status['active_runs']:
                    break
                time.sleep(10)
        finally:
            timer.terminate()
            timer.wait(timeout=30)
        shutil.copytree(root / 'management', output / 'management', ignore=shutil.ignore_patterns('install-backups'))
        tasks = run(TOOLS + '/pm_tasks.py', '--project', '.', cwd=root, data={'op': 'status'})
        receipt = dict(host=a.host, cli=subprocess.run(['claude', '--version'], capture_output=True, text=True).stdout.strip() if a.host == 'claude' else 'stub',
                       final_stop=status.get('stop'), tasks={t['id']: t['state'] for t in tasks['tasks']},
                       runs=sorted(tasks['integrity']['launch'].values(), key=lambda l: (l['started_at'], l['id'])),
                       limitations=['Synthetic project and synthetic person; no real approval.', 'One machine; instances share the project folder.',
                                    'The PM is the checker, so professional acceptance is not shown.'])
        receipt['evidence'] = {str(p.relative_to(output)): hashlib.sha256(p.read_bytes()).hexdigest() for p in output.rglob('*') if p.is_file()}
        (output / 'receipt.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print(json.dumps({'final_stop': receipt['final_stop'], 'tasks': receipt['tasks'], 'output': str(output)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
