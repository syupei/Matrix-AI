#!/usr/bin/env python3
"""Scheduler: carries out what the task database already decided, and wakes the PM-agent only for decisions.

Each check reads the task database (no model call). It starts the runs whose decision is recorded (a ready task's
executor, the checker of a handed-over task, the dispatcher of a stopped one), rebuilds the views, records runs whose
process is gone, and wakes the PM through the host command in management/runtime/platform.json when something needs
the PM's judgment and the PM is not already working. A person starts it (in a terminal, or from a scheduled task they
authorized) and stops it; it is never installed.

  scheduler.py --project .          check every check_seconds until stopped
  scheduler.py --project . --once   one check, then exit (for a scheduler of the system)
"""
import argparse
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import time
import uuid

TOOLS = Path(__file__).resolve().parent
STATE, LOG, LOGS = 'management/runtime/scheduler.json', 'management/runtime/scheduler.log', 'management/runtime/logs/'
DEFAULTS = {'check_seconds': 60, 'patrol_minutes': 60, 'pm_timeout_minutes': 20, 'resume_limit': 20, 'resume_idle_minutes': 60,
            'launch_grace_minutes': 5, 'settle_seconds': 60, 'max_wait_seconds': 300, 'pm_session_flag': 500000}
CHILDREN = {}  # PM processes this scheduler started, polled so they do not linger as zombies


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, TOOLS / file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def now():
    return datetime.now(timezone.utc)


def stamp():
    return now().isoformat(timespec='seconds')


def minutes(at):
    try:
        return (now() - datetime.fromisoformat(at)).total_seconds() / 60
    except (TypeError, ValueError):
        return 10 ** 6


def alive(pid, mark):
    """The process exists and is still the one started for mark (a run or PM session id)."""
    if not pid:
        return False
    proc = CHILDREN.get(pid)
    if proc is not None and proc.poll() is not None:
        CHILDREN.pop(pid, None)
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    try:
        command = subprocess.run(['ps', '-o', 'command=', '-p', str(pid)], capture_output=True, text=True).stdout
    except OSError:
        return True
    return mark in command if command.strip() else False


def log(root, pm, text):
    with open(pm.local(root, LOG), 'a', encoding='utf-8') as f:
        f.write(stamp() + ' ' + text + '\n')


def changes(pm, root, since, pm_actor):
    """Records after since by anyone but the PM, and records of a person's words whoever wrote them; with the times of the
    newest and oldest of them and whether a person spoke (a PM without a front desk takes the person's reply itself)."""
    db = pm.connect(root, readonly=True)
    try:
        top = db.execute('SELECT COALESCE(MAX(seq),0) FROM events').fetchone()[0]
        rows = db.execute('SELECT actor, command, recorded_at FROM events WHERE seq > ?', (since,)).fetchall()
    finally:
        db.close()
    new = [(r['recorded_at'], json.loads(r['command']).get('op') in pm.platform.HUMAN_OPS) for r in rows
           if r['actor'] != pm_actor or json.loads(r['command']).get('op') in pm.platform.HUMAN_OPS]
    return dict(top=top, count=len(new), newest=max((a for a, _ in new), default=None), oldest=min((a for a, _ in new), default=None),
                person=any(h for _, h in new))


def records(pm, root, kind):
    db = pm.connect(root, readonly=True)
    try:
        return pm.integrity.records(db, kind)
    finally:
        db.close()


def start_queued(pm, root, launcher):
    """Runs recorded but not started yet (spawn: scheduler, and the scheduler's own), and processes of runs recorded as lost."""
    started = []
    for rec in sorted(records(pm, root, 'launch').values(), key=lambda r: r['started_at']):
        if rec['state'] == 'starting' and not rec.get('pid'):
            launcher.spawn(pm, root, rec, pm.platform.SCHEDULER)
            started.append(rec['id'])
        elif rec['state'] == 'lost' and rec.get('pid') and alive(rec['pid'], rec['id']):
            try:
                os.killpg(rec['pid'], signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                pass
    return started


def lost_runs(pm, root, grace):
    """Runs whose wrapper is gone without recording an exit: recorded as lost, which stops their task's run."""
    found = []
    for rec in records(pm, root, 'launch').values():
        if rec['state'] not in pm.platform.ACTIVE:
            continue
        gone = (not rec.get('pid') and minutes(rec['started_at']) > grace) or (rec.get('pid') and not alive(rec['pid'], rec['id']))
        if gone:
            evidence = 'process ' + str(rec['pid']) + ' not found' if rec.get('pid') else 'no process recorded within ' + str(grace) + ' minutes'
            pm.execute(root, dict(op='launch_lost', actor=pm.platform.SCHEDULER, event_id=rec['id'] + '-lost', id=rec['id'], evidence=evidence))
            found.append(rec['id'])
    return found


def carry_out(pm, root, launcher, summary):
    """Start the runs the records already decide: who executes, checks or attends a task is written on it."""
    started = []
    for a in summary['actions']:
        if a.get('by') != 'scheduler':
            continue
        try:
            if a['kind'] == 'start':
                out = launcher.launch(root, a['task'], 'start', None, 'sched-' + uuid.uuid4().hex[:10], None, pm.platform.SCHEDULER)
            else:
                out = launcher.launch(root, a['tasks'][0], a['kind'], a['tasks'], 'sched-' + uuid.uuid4().hex[:10], None, pm.platform.SCHEDULER)
            started.append(a['kind'] + ':' + (a.get('task') or ','.join(a['tasks'])) + '=' + out['record']['id'])
        except (ValueError, OSError) as error:
            log(root, pm, 'could not start ' + a['kind'] + ' ' + str(a.get('task') or a.get('tasks')) + ': ' + str(error)[:200])
    return started


def notify(root, settings, pm, message):
    if not settings.get('notify'):
        return
    command = [part.replace('{message}', message) for part in settings['notify']]
    try:
        subprocess.run(command, cwd=root, timeout=30, capture_output=True)
    except (OSError, subprocess.TimeoutExpired) as error:
        log(root, pm, 'notify failed: ' + str(error))


def finish_pm(root, pm, launcher, settings, state, stopped=False):
    """A PM session ended: record its usage (as the host reported it) and keep its log compressed."""
    last = state['pm']
    path = pm.local(root, LOGS + 'pm-' + last['session'] + '.log')
    message, usage = launcher.outcome(path) if path.is_file() else (None, None)
    pm.execute(root, dict(op='pm_session', actor=pm.platform.SCHEDULER, event_id='pm-session-' + last['session'] + '-' + str(last.get('resumes', 0)),
                          id=last['session'] + ('-' + str(last['resumes']) if last.get('resumes') else ''), reason=last.get('reason'),
                          started_at=last['started_at'], finished_at=stamp(), usage=usage, stopped=stopped))
    if usage and usage['input'] > settings['pm_session_flag']:
        log(root, pm, 'PM session ' + last['session'] + ' used ' + str(usage['input']) + ' input tokens, over ' + str(settings['pm_session_flag']))
    if path.is_file() and not (settings.get('pm') or {}).get('resume'):
        launcher.pack(path)  # a resumable session keeps writing to the same log


def wake(root, pm, settings, state, summary, reason):
    """Start the PM: resume its session while it is recent, otherwise a new one."""
    pmc = settings.get('pm') or {}
    pm.require(pm.strings(pmc.get('launch')) and pmc['launch'], 'platform.json: pm.launch (the host command for the PM) required')
    for name in ['launch', 'resume']:
        # The session id in the command line is how a later check knows the process is still this PM run.
        pm.require(name not in pmc or any('{session}' in part for part in pmc[name]), 'platform.json: pm.' + name + ' must pass {session}')
    last = state.get('pm') or {}
    can_resume = (pm.strings(pmc.get('resume')) and last.get('session') and not state.get('force_new')
                  and last.get('resumes', 0) < settings['resume_limit'] and minutes(last.get('finished_at')) < settings['resume_idle_minutes'])
    todo = '；'.join(a['kind'] + ':' + str(a.get('task') or a.get('id')) for a in summary['actions'][:12])
    if can_resume:
        session, resumes, template = last['session'], last.get('resumes', 0) + 1, pmc['resume']
        prompt = '任务表有新变化（' + reason + '）。按值班说明再运行一次接续并处理，直到没有可做的事。要做的事：' + todo
    else:
        session, resumes, template = str(uuid.uuid4()), 0, pmc['launch']
        prompt = ('你是本项目的项目管理（PM，actor ' + summary['pm_actor'] + '）。这是调度器唤起的一次值班（' + reason + '）。'
                  '先读 matrix/orchestration/PM-DUTY.md，再运行接续（{"op":"continue"}），按值班说明处理，直到没有可做的事，然后结束。'
                  '要做的事：' + todo)
    command = [p.replace('{session}', session).replace('{prompt}', prompt) for p in template]
    path = pm.local(root, LOGS + 'pm-' + session + '.log')
    path.parent.mkdir(parents=True, exist_ok=True)
    out = open(path, 'ab')
    proc = subprocess.Popen(command, cwd=root, stdin=subprocess.PIPE if settings.get('prompt', 'stdin') == 'stdin' else subprocess.DEVNULL,
                            stdout=out, stderr=out, start_new_session=True)
    if proc.stdin:
        proc.stdin.write(prompt.encode('utf-8'))
        proc.stdin.close()
    CHILDREN[proc.pid] = proc
    state['pm'] = dict(pid=proc.pid, session=session, started_at=stamp(), resumes=resumes, wake_seq=state['top'], finished_at=None, reason=reason)
    state.pop('force_new', None)
    log(root, pm, ('resumed' if can_resume else 'started') + ' PM session ' + session + ' (' + reason + ')')


def tick(project):
    """One check; a second scheduler on the same project waits for the first instead of waking a second PM."""
    root = Path(project).resolve()
    pm = load('scheduler_pm_tasks', 'pm_tasks.py')
    lock = open(pm.local(root, 'management/runtime/scheduler.lock'), 'w')
    try:
        import fcntl
        fcntl.flock(lock, fcntl.LOCK_EX)
    except ImportError:
        pass  # no file locks on this system: run one scheduler per project
    try:
        return checked(root, pm)
    finally:
        lock.close()


def checked(root, pm):
    launcher = load('scheduler_launch', 'launch.py')
    settings = dict(DEFAULTS, **launcher.settings(pm, root))
    path = pm.local(root, STATE)
    state = json.loads(path.read_text(encoding='utf-8')) if path.is_file() else {'processed_seq': 0}
    cfg = pm.execute(root, {'op': 'status'})['config']
    started = start_queued(pm, root, launcher)
    lost = lost_runs(pm, root, settings['launch_grace_minutes'])
    if lost:
        log(root, pm, 'runs gone without an exit record: ' + ','.join(lost))
    last, pm_working = state.get('pm') or {}, False
    if last.get('pid'):
        pm_working = alive(last['pid'], last['session'])
        if pm_working and minutes(last['started_at']) > settings['pm_timeout_minutes']:
            try:
                os.killpg(last['pid'], signal.SIGTERM)
            except ProcessLookupError:
                pass
            pm_working, state['force_new'] = False, True
            log(root, pm, 'PM run over ' + str(settings['pm_timeout_minutes']) + ' minutes, stopped; the next wake starts a new session')
        if not pm_working:
            finish_pm(root, pm, launcher, settings, state, stopped=state.get('force_new', False))
            state['processed_seq'] = last.get('wake_seq', state.get('processed_seq', 0))
            state['pm'] = dict(last, pid=None, finished_at=stamp())
    summary = pm.execute(root, {'op': 'continue', 'detail': True})
    if not summary['paused']:
        done = carry_out(pm, root, launcher, summary)
        if done:
            started += start_queued(pm, root, launcher)
            log(root, pm, 'started: ' + '；'.join(done))
            summary = pm.execute(root, {'op': 'continue', 'detail': True})
    elif started:
        log(root, pm, 'started queued runs: ' + ','.join(started))
    seen = changes(pm, root, state.get('processed_seq', 0), cfg['pm_actor'])
    state['top'] = seen['top']
    if seen['top'] > state.get('rendered_seq', -1):
        pm.render(root)  # the views follow the records; no model needed
        state['rendered_seq'] = seen['top']
    if pm_working:
        path.write_text(json.dumps(state, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
        return 'pm_working'
    decisions = [a for a in summary['actions'] if a.get('by') != 'scheduler']
    patrol = minutes(state.get('last_patrol')) >= settings['patrol_minutes']
    settled = seen['person'] or minutes(seen['newest']) * 60 >= settings['settle_seconds'] or minutes(seen['oldest']) * 60 >= settings['max_wait_seconds']
    result = 'idle'
    if decisions and ((seen['count'] and settled) or patrol or lost):
        wake(root, pm, settings, state, dict(summary, actions=decisions, pm_actor=cfg['pm_actor']),
             '巡检' if patrol and not seen['count'] else str(seen['count']) + ' 条新记录')
        result = 'pm_woken'
    elif decisions and seen['count']:
        result = 'settling'  # more changes may follow; the PM gets them together
    elif not decisions:
        state['processed_seq'] = seen['top']
    if patrol:
        state['last_patrol'] = stamp()
    stop = summary['stop']
    items = '；'.join(h['task'] + ' ' + h['why'] for h in summary['human_items'][:5])
    if stop in {'needs_human', 'paused', 'idle'} and str(stop) + '|' + items != state.get('last_stop'):
        notify(root, settings, pm, {'needs_human': '需要你处理：' + items, 'paused': '项目已暂停', 'idle': '项目停住了：没有可做的事，也没有在运行的任务'}[stop])
        log(root, pm, 'stop ' + stop + (': ' + items if items else ''))
    state['last_stop'] = str(stop) + '|' + items
    path.write_text(json.dumps(state, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--project', type=Path, required=True)
    ap.add_argument('--once', action='store_true')
    a = ap.parse_args()
    while True:
        try:
            result = tick(a.project)
        except (ValueError, OSError, KeyError) as error:
            print(json.dumps({'error': str(error)}, ensure_ascii=False), flush=True)
            if a.once:
                return 1
            result = 'error'
        if a.once:
            print(json.dumps({'result': result}), flush=True)
            return 0
        pm = load('scheduler_settings_pm', 'pm_tasks.py')
        seconds = dict(DEFAULTS, **json.loads(pm.local(Path(a.project).resolve(), 'management/runtime/platform.json').read_text(encoding='utf-8')))['check_seconds']
        time.sleep(max(5, int(seconds)))


if __name__ == '__main__':
    raise SystemExit(main())
