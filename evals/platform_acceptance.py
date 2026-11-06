#!/usr/bin/env python3
"""Real-run acceptance of platform runs: the seven situations of PM-Q-001 in one synthetic project, with the real
timer, PM-agent and launch command running on an actual host command line.

  platform_acceptance.py --source <built kit> --output <new dir> --host codex --model gpt-6-luna [--minutes 75]
  platform_acceptance.py --source <built kit> --output <new dir> --host stub                     (path check only)

Tasks (the PM is the checker of all): A -> B (B needs A adopted); C in parallel with A, needs a person's review;
E needs C; G belongs to an instance whose configured model does not exist, so its runs fail.
Disturbances: two timers run at once; A's first run is killed mid-way; both timers stop and one restarts.
The person's approval of C is SYNTHETIC and recorded as such. Nothing here is an external project or a real person.

Checks: S1 A done -> B starts without anyone saying continue; S2 A and C overlap; S3a the review of C holds only E,
S3b E starts once C is approved (needs a real person's approval: the PM may rightly refuse the synthetic one);
S4 never two runs of one task or one instance at once, with two timers; S5 several PM sessions, each ending and the
next started by changes; S6 the killed run is recorded and redone, and work resumes after the timer restarts;
S7 G stops after three failed starts and the person is told.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time

TOOLS = 'matrix/orchestration/tools'
STUB = r'''
import json, re, subprocess, sys
from pathlib import Path
T = 'matrix/orchestration/tools/'
def call(cmd):
    return json.loads(subprocess.run([sys.executable, '-B', T + 'pm_tasks.py', '--project', '.'], input=json.dumps(cmd), capture_output=True, text=True).stdout)
def task(tid):
    return next(t for t in call({'op': 'status'})['tasks'] if t['id'] == tid)
text = sys.stdin.read()
if sys.argv[1] == 'worker':
    rid, iid = re.search(r'# 任务包 (\S+?)（', text).group(1), re.search(r'actor 写 (\S+?)。', text).group(1)
    if sys.argv[2] == 'missing-model':
        sys.exit(1)
    import time; time.sleep(6)
    tid = re.search(r'## 任务 (\S+?)：', text).group(1)
    call({'op': 'transition', 'actor': iid, 'event_id': rid + '-handover', 'task_id': tid, 'expected_revision': task(tid)['revision'], 'state': 'waiting_review',
          'reason': 'stub done', 'stop_evidence': rid + ' stub run done', 'evidence': ['BRIEF.md']})
else:
    for n in range(40):
        s = call({'op': 'continue'})
        act = next((a for a in s['actions'] if a['kind'] in {'start', 'pm'}), None)
        if not act:
            break
        if act['kind'] == 'start':
            subprocess.run([sys.executable, '-B', T + 'launch.py', '--project', '.', '--task', act['task']], capture_output=True)
            continue
        t, code = task(act['task']), s['stops'][act['task']]['code']
        fields = {'review': dict(op='review', outcome='passed', criteria_checked=t['criteria'], evidence=t['evidence']),
                  'adopt': dict(op='transition', state='done', reason='stub adopted'),
                  'ended': dict(op='transition', state='planned', reason='stub redo')}.get(code)
        if not fields:
            break
        call(dict(fields, actor='PM', event_id='stub-' + code + '-' + str(n) + t['id'], task_id=t['id'], expected_revision=t['revision']))
'''


def host_settings(host, model, root):
    note = ['sh', '-c', 'printf "%s\\n" "$0" >> management/runtime/notified.txt', '{message}']
    if host == 'codex':
        base = 'codex exec --skip-git-repo-check --sandbox workspace-write --json -c \'model_reasoning_effort="medium"\''
        return {'spawn': 'timer',  # commands of a Codex session run sandboxed: the timer starts the runs
                'launch': ['codex', 'exec', '--skip-git-repo-check', '--sandbox', 'workspace-write', '--json',
                           '-c', 'model_reasoning_effort="medium"', '-m', '{model}', '-'],
                'pm': {'launch': ['sh', '-c', base + ' -m ' + model + ' - ; :', 'pm-{session}']},
                'notify': note, 'check_seconds': 15}
    (root / 'stub_host.py').write_text(STUB, encoding='utf-8')
    py = sys.executable
    return {'spawn': 'timer', 'launch': [py, '-B', str(root / 'stub_host.py'), 'worker', '{model}'],
            'pm': {'launch': [py, '-B', str(root / 'stub_host.py'), 'pm', 'pm-{session}']}, 'notify': note, 'check_seconds': 3}


def tool(root, data):
    r = subprocess.run([sys.executable, '-B', TOOLS + '/pm_tasks.py', '--project', '.'], cwd=root, input=json.dumps(data), capture_output=True, text=True)
    out = json.loads(r.stdout)
    if r.returncode:
        raise RuntimeError(json.dumps(data, ensure_ascii=False)[:200] + ': ' + out.get('error', ''))
    return out


def setup(source, root, host, model):
    subprocess.run([sys.executable, '-B', str(source / 'install.py'), '--target', str(root), '--apply'], check=True, capture_output=True)
    n = [0]
    def call(op, actor='PM', **kw):
        n[0] += 1
        return tool(root, dict(op=op, actor=actor, event_id='ACC-' + str(n[0]), **kw))
    (root / 'BRIEF.md').write_text('合成项目：内部意见箱。已确定：员工提交意见、管理员查看列表。未定：是否匿名、附件大小上限。'
                                   '只在自己的工作区写候选，不补未定的规则。', encoding='utf-8')
    call('init', config=dict(project='SYNTHETIC suggestion box', pm_actor='PM', authorization='BRIEF.md', frontdoor_id='ACCEPTANCE', max_slots=3))
    call('configure', frontdesk_actor='DESK')  # the front desk records what the person says
    entries = [{'id': 'P-M', 'profession': 'product', 'level': 'T7', 'model': model, 'count': 1, 'master': True},
               {'id': 'C-M', 'profession': 'content-design', 'level': 'T6', 'model': model, 'count': 1, 'master': True},
               {'id': 'X-M', 'profession': 'experience-design', 'level': 'T7', 'model': 'missing-model', 'count': 1, 'master': True}]
    (root / 'management/instance-config.json').write_text(json.dumps({'entries': entries}), encoding='utf-8')
    call('confirm_config', person='SYNTHETIC-owner', quote='SYNTHETIC: 按这个配置试跑', presented_ref='BRIEF.md',
         choices={e['id']: 'acknowledge_unregistered' for e in entries})
    for e in entries:
        call('derive', entry=e['id'], endpoint='platform')
    common = dict(parent=None, checker='PM', inputs=['BRIEF.md'], criteria=['只用 BRIEF.md 已确定的规则', '未定的列为待人决定'], next_action='制作候选')
    for tid, owner, title, extra in [
            ('A', 'product-001', '意见提交流程候选', {}),
            ('B', 'product-001', '按 A 的流程写验收情境', {'dependencies': ['A']}),
            ('C', 'content-design-001', '提交成功、失败与重试的提示文字', {'human_required': True}),
            ('E', 'content-design-001', '按已审定的提示文字写帮助说明', {'dependencies': ['C']}),
            ('G', 'experience-design-001', '提交页的交互说明', {})]:
        call('create', task=dict(id=tid, title=title, owner=owner, executor=owner, goal=title, outputs=[title + '（工作区内）'], **common, **extra))
    (root / 'management/runtime/platform.json').write_text(json.dumps(host_settings(host, model, root), ensure_ascii=False, indent=1), encoding='utf-8')


def runs(root):
    return tool(root, {'op': 'status'})['integrity']['launch']


def start_timer(root, output, name):
    return subprocess.Popen([sys.executable, '-B', TOOLS + '/timer.py', '--project', '.'], cwd=root, start_new_session=True,
                            stdout=open(output / (name + '.stdout'), 'a'), stderr=subprocess.STDOUT)


def stop(proc):
    if proc and proc.poll() is None:
        os.killpg(proc.pid, signal.SIGTERM)
        proc.wait(timeout=30)


def evaluate(root, marks):
    st = tool(root, {'op': 'status'})
    tasks, launches = {t['id']: t for t in st['tasks']}, sorted(st['integrity']['launch'].values(), key=lambda l: (l['started_at'], l['id']))
    events = tool(root, {'op': 'events', 'after': 0, 'limit': 1000})['events']
    done_at = {}
    for e in events:  # the first time each task was recorded done
        if e['after_data'] and e['after_data'].get('state') == 'done':
            done_at.setdefault(e['task_id'], e['recorded_at'])
    starts = {tid: [l for l in launches if l['task_id'] == tid and l['purpose'] == 'start'] for tid in tasks}
    def span(l):
        return l['started_at'], l.get('finished_at') or '9999'
    def overlap(a, b):
        return span(a)[0] < span(b)[1] and span(b)[0] < span(a)[1]
    approval = marks.get('approval_at', '9999')
    log = (root / 'management/runtime/timer.log').read_text(encoding='utf-8') if (root / 'management/runtime/timer.log').is_file() else ''
    s = {}
    b0 = (starts['B'] or [None])[0]
    s['S1'] = bool(b0 and 'A' in done_at and b0['started_at'] >= done_at['A'] and b0['started_at'] < approval and tasks['B']['state'] == 'done')
    s['S2'] = any(overlap(a, c) for a in starts['A'] for c in starts['C'])
    e0 = (starts['E'] or [None])[0]
    # S3a: while C waits for the person, the independent B finishes and E (which needs C) does not start.
    s['S3a'] = bool(tasks['B']['state'] == 'done' and (not e0 or ('C' in done_at and e0['started_at'] >= done_at['C'])))
    # S3b: E starts once C is approved; a SYNTHETIC approval may rightly be refused by the PM, so this needs a real person.
    s['S3b'] = bool(e0 and 'C' in done_at and e0['started_at'] >= done_at['C'] and tasks['E']['state'] == 'done')
    clash = [(x['id'], y['id']) for i, x in enumerate(launches) for y in launches[i + 1:]
             if (x['task_id'] == y['task_id'] or x['instance'] == y['instance']) and overlap(x, y)]
    s['S4'] = not clash and marks.get('two_timers', False)
    s['S5'] = log.count('PM session') >= 3
    killed = marks.get('killed')
    redo = [l for l in starts['A'] if killed and l['id'] != killed]
    after_restart = [l for l in launches if l['started_at'] > marks.get('restarted_at', '9999')]
    s['S6'] = bool(killed and next((l for l in launches if l['id'] == killed), {}).get('state') == 'lost' and redo and tasks['A']['state'] == 'done' and after_restart)
    notified = (root / 'management/runtime/notified.txt').read_text(encoding='utf-8') if (root / 'management/runtime/notified.txt').is_file() else ''
    stops = tool(root, {'op': 'continue'})['stops']
    # S7: the failures stay bounded (three failed starts stop G, or the PM hands G to a person earlier) and the person is told.
    s['S7'] = (len(starts['G']) <= 3 and stops.get('G', {}).get('code') in {'launch_failed', 'human'}
               and any(line.startswith('需要你处理') and 'G ' in line for line in notified.splitlines()))
    detail = dict(tasks={k: v['state'] for k, v in tasks.items()}, clash=clash, pm_sessions=log.count('PM session'),
                  runs=[dict(id=l['id'], task=l['task_id'], instance=l['instance'], purpose=l['purpose'], model=l['model'], state=l['state'],
                             started=l['started_at'][11:19], finished=(l.get('finished_at') or '')[11:19], exit=l.get('exit_code'),
                             ended_without_handover=l.get('ended_without_handover', False)) for l in launches],
                  stops={k: v['label'] for k, v in stops.items()}, notified=notified.strip().splitlines(), marks=marks)
    return s, detail


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--source', type=Path, required=True); ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--host', choices=['codex', 'stub'], required=True); ap.add_argument('--model', default='gpt-6-luna')
    ap.add_argument('--minutes', type=float, default=75)
    a = ap.parse_args()
    source, output = a.source.resolve(), a.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    root = output / 'project'
    root.mkdir()
    setup(source, root, a.host, a.model)
    marks = {}
    def now():
        return datetime.now(timezone.utc).isoformat(timespec='seconds')
    t1, t2 = start_timer(root, output, 'timer1'), start_timer(root, output, 'timer2')
    marks['two_timers'] = True
    begin, approved_ts = time.time(), None
    end, restarted = begin + a.minutes * 60, False
    try:
        while time.time() < end:
            time.sleep(1 if a.host == 'stub' else 10)
            rs = runs(root)
            a_run = next((l for l in rs.values() if l['task_id'] == 'A' and l['purpose'] == 'start' and l['state'] == 'running'), None)
            if a_run and 'killed' not in marks and a_run.get('pid'):
                time.sleep(1 if a.host == 'stub' else 20)
                try:
                    os.killpg(a_run['pid'], signal.SIGKILL)  # the run's process disappears without recording an exit
                    marks['killed'] = a_run['id']
                except ProcessLookupError:
                    pass
            if marks.get('killed') and not restarted and 'timers_stopped_at' not in marks:
                stop(t1); stop(t2)
                marks['timers_stopped_at'] = now()
                time.sleep(45 if a.host == 'codex' else 5)
                t1 = start_timer(root, output, 'timer3')
                marks['restarted_at'], restarted = now(), True
            summary = tool(root, {'op': 'continue'})
            stops = summary['stops']
            states = {t['id']: t['state'] for t in tool(root, {'op': 'status'})['tasks']}
            if 'approval_at' not in marks and stops.get('C', {}).get('code') == 'human':
                # The person answers once B has moved on while C waited (or after half the time).
                if states['B'] == 'done' or time.time() > begin + a.minutes * 30:
                    c = next(t for t in tool(root, {'op': 'status'})['tasks'] if t['id'] == 'C')
                    tool(root, dict(op='human_review', actor='DESK', event_id='ACC-approval', task_id='C', expected_revision=c['revision'], outcome='approved',
                                    presented_ref='BRIEF.md', source='SYNTHETIC person, not a real reply', quote='SYNTHETIC: 文字可以', scope='C 的提示文字',
                                    person='SYNTHETIC-owner'))
                    tool(root, dict(op='inbox', actor='DESK', event_id='ACC-inbox', id='IN-1', kind='answer', text='C 的文字已审定',
                                    person='SYNTHETIC-owner', quote='SYNTHETIC: 文字可以'))
                    marks['approval_at'], approved_ts = now(), time.time()
            # After the approval the PM gets a few minutes; if C is still not adopted then, the approval was refused.
            refused = 'approval_at' in marks and time.time() - approved_ts > (300 if a.host == 'codex' else 30) and states['C'] != 'done'
            settled = all(states[x] == 'done' for x in 'ABCE') or (states['B'] == 'done' and refused and summary['stop'] in {'needs_human', 'idle'})
            if settled and stops.get('G', {}).get('code') in {'launch_failed', 'human'} and not summary['active_runs']:
                for _ in range(60):  # let the timer tell the person about G
                    note = root / 'management/runtime/notified.txt'
                    if note.is_file() and 'G ' in note.read_text(encoding='utf-8'):
                        break
                    time.sleep(3)
                break
    finally:
        stop(t1); stop(t2)
    checks, detail = evaluate(root, marks)
    shutil.rmtree(root / 'management/install-backups', ignore_errors=True)
    report = dict(host=a.host, model=a.model if a.host == 'codex' else 'stub', checks=checks, passed=sum(checks.values()), detail=detail,
                  limitations=['Synthetic project; the approval of C is SYNTHETIC, not a person.',
                               'Codex sandbox lets a run write the whole project folder; write ranges are held by instruction.',
                               'The PM is the checker of every task, so professional acceptance between instances is not shown.',
                               'One machine; one host; one sample run.'])
    report['evidence'] = {str(p.relative_to(output)): hashlib.sha256(p.read_bytes()).hexdigest() for p in output.rglob('*') if p.is_file() and p.suffix in {'.log', '.md', '.json', '.txt', '.stdout', '.jsonl'}}
    (output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    print(json.dumps(dict(checks=checks, tasks=detail['tasks'], pm_sessions=detail['pm_sessions']), ensure_ascii=False))


if __name__ == '__main__':
    main()
