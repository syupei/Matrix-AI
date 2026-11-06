#!/usr/bin/env python3
"""Timer: keeps the PM-agent's work going. Each check reads the task database (no model call); when there is something
for the PM to do and the PM is not already working, it wakes the PM through the host command in
management/runtime/platform.json. A person starts it (in a terminal, or from a scheduled task they authorized) and
stops it; it is never installed.

  timer.py --project .          check every check_seconds until stopped
  timer.py --project . --once   one check, then exit (for a scheduler)
"""
import argparse
from datetime import datetime, timezone
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
STATE, LOG = 'management/runtime/timer.json', 'management/runtime/timer.log'
DEFAULTS = {'check_seconds': 60, 'patrol_minutes': 60, 'pm_timeout_minutes': 20, 'resume_limit': 20, 'resume_idle_minutes': 60,
            'launch_grace_minutes': 5}
CHILDREN = {}  # PM processes this timer started, polled so they do not linger as zombies


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, TOOLS / file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def now():
    return datetime.now(timezone.utc)


def minutes(stamp):
    try:
        return (now() - datetime.fromisoformat(stamp)).total_seconds() / 60
    except (TypeError, ValueError):
        return 10 ** 6


def alive(pid, mark):
    """The process exists and is still the one started for mark (a launch or PM session id)."""
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
        f.write(now().isoformat(timespec='seconds') + ' ' + text + '\n')


def changes(pm, root, since, pm_actor):
    """Records written after since by anyone but the PM, and records of a person's words whoever wrote them
    (a PM without a front desk takes the person's reply itself); the PM's other records never wake it."""
    db = pm.connect(root, readonly=True)
    try:
        top = db.execute('SELECT COALESCE(MAX(seq),0) FROM events').fetchone()[0]
        rows = db.execute('SELECT actor, command FROM events WHERE seq > ?', (since,)).fetchall()
        return top, sum(1 for r in rows if r['actor'] != pm_actor or json.loads(r['command']).get('op') in pm.platform.HUMAN_OPS)
    finally:
        db.close()


def lost_runs(pm, root, grace):
    """Runs whose wrapper is gone without recording an exit: recorded as lost, which stops their task's run."""
    found = []
    for rec in pm.execute(root, {'op': 'continue'})['active_runs']:
        full = load_launch(pm, root, rec['id'])
        gone = (not full.get('pid') and minutes(full['started_at']) > grace) or (full.get('pid') and not alive(full['pid'], full['id']))
        if gone:
            evidence = 'process ' + str(full['pid']) + ' not found' if full.get('pid') else 'no process recorded within ' + str(grace) + ' minutes'
            pm.execute(root, dict(op='launch_lost', actor=pm.platform.TIMER, event_id=full['id'] + '-lost', id=full['id'], evidence=evidence))
            found.append(full['id'])
    return found


def start_queued(pm, root, launcher):
    """Runs the PM recorded but could not start itself (spawn: timer), and processes of runs already recorded as ended."""
    db = pm.connect(root, readonly=True)
    try:
        runs = pm.integrity.records(db, 'launch')
    finally:
        db.close()
    started = []
    for rec in sorted(runs.values(), key=lambda r: r['started_at']):
        if rec['state'] == 'starting' and not rec.get('pid'):
            launcher.spawn(pm, root, rec, pm.platform.TIMER)
            started.append(rec['id'])
        elif rec['state'] == 'lost' and rec.get('pid') and alive(rec['pid'], rec['id']):
            try:
                os.killpg(rec['pid'], signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                pass
    return started


def load_launch(pm, root, rid):
    db = pm.connect(root, readonly=True)
    try:
        return pm.integrity.records(db, 'launch')[rid]
    finally:
        db.close()


def notify(root, settings, pm, message):
    if not settings.get('notify'):
        return
    command = [part.replace('{message}', message) for part in settings['notify']]
    try:
        subprocess.run(command, cwd=root, timeout=30, capture_output=True)
    except (OSError, subprocess.TimeoutExpired) as error:
        log(root, pm, 'notify failed: ' + str(error))


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
    todo = '；'.join(a['kind'] + ':' + str(a.get('task') or a.get('instance') or a.get('id')) for a in summary['actions'][:12])
    if can_resume:
        session, resumes, template = last['session'], last.get('resumes', 0) + 1, pmc['resume']
        prompt = '任务表有新变化（' + reason + '）。按值班说明再运行一次接续并处理，直到没有可做的事。接续里要做的事：' + todo
    else:
        session, resumes, template = str(uuid.uuid4()), 0, pmc['launch']
        prompt = ('你是本项目的项目管理（PM，actor ' + summary['pm_actor'] + '）。这是平台定时器唤起的一次值班（' + reason + '）。'
                  '先读 matrix/orchestration/PM-DUTY.md，再运行接续（{"op":"continue"}），按值班说明处理，直到没有可做的事，然后结束。'
                  '接续里要做的事：' + todo)
    command = [p.replace('{session}', session).replace('{prompt}', prompt) for p in template]
    path = pm.local(root, 'management/runtime/pm-runs/' + session + '.log')
    path.parent.mkdir(parents=True, exist_ok=True)
    out = open(path, 'ab')
    proc = subprocess.Popen(command, cwd=root, stdin=subprocess.PIPE if settings.get('prompt', 'stdin') == 'stdin' else subprocess.DEVNULL,
                            stdout=out, stderr=out, start_new_session=True)
    if proc.stdin:
        proc.stdin.write(prompt.encode('utf-8'))
        proc.stdin.close()
    CHILDREN[proc.pid] = proc
    state['pm'] = dict(pid=proc.pid, session=session, started_at=now().isoformat(timespec='seconds'), resumes=resumes,
                       wake_seq=state['top'], finished_at=None)
    state.pop('force_new', None)
    log(root, pm, ('resumed' if can_resume else 'started') + ' PM session ' + session + ' (' + reason + ')')


def tick(project):
    """One check; a second timer on the same project waits for the first instead of waking a second PM."""
    root = Path(project).resolve()
    pm = load('timer_pm_tasks', 'pm_tasks.py')
    lock = open(pm.local(root, 'management/runtime/timer.lock'), 'w')
    try:
        import fcntl
        fcntl.flock(lock, fcntl.LOCK_EX)
    except ImportError:
        pass  # no file locks on this system: run one timer per project
    try:
        return checked(root, pm)
    finally:
        lock.close()


def checked(root, pm):
    launcher = load('timer_launch', 'launch.py')
    settings = dict(DEFAULTS, **launcher.settings(pm, root))
    path = pm.local(root, STATE)
    state = json.loads(path.read_text(encoding='utf-8')) if path.is_file() else {'processed_seq': 0}
    cfg = pm.execute(root, {'op': 'status'})['config']
    started = start_queued(pm, root, launcher)
    if started:
        log(root, pm, 'started queued runs: ' + ','.join(started))
    lost = lost_runs(pm, root, settings['launch_grace_minutes'])
    if lost:
        log(root, pm, 'runs gone without an exit record: ' + ','.join(lost))
    last = state.get('pm') or {}
    if last.get('pid'):
        if alive(last['pid'], last['session']):
            if minutes(last['started_at']) <= settings['pm_timeout_minutes']:
                path.write_text(json.dumps(state, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
                return 'pm_working'
            try:
                os.killpg(last['pid'], signal.SIGTERM)
            except ProcessLookupError:
                pass
            state['force_new'] = True
            log(root, pm, 'PM run over ' + str(settings['pm_timeout_minutes']) + ' minutes, stopped; the next wake starts a new session')
        state['processed_seq'] = last.get('wake_seq', state.get('processed_seq', 0))
        state['pm'] = dict(last, pid=None, finished_at=now().isoformat(timespec='seconds'))
    summary = dict(pm.execute(root, {'op': 'continue'}), pm_actor=cfg['pm_actor'])
    state['top'], new = changes(pm, root, state.get('processed_seq', 0), cfg['pm_actor'])
    patrol = minutes(state.get('last_patrol')) >= settings['patrol_minutes']
    result = 'idle'
    if summary['actions'] and (new or patrol or lost):
        wake(root, pm, settings, state, summary, ('巡检' if patrol and not new else str(new) + ' 条新记录'))
        result = 'pm_woken'
    elif not summary['actions']:
        state['processed_seq'] = state['top']
    if patrol:
        state['last_patrol'] = now().isoformat(timespec='seconds')
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
        pm = load('timer_settings_pm', 'pm_tasks.py')
        seconds = dict(DEFAULTS, **json.loads(pm.local(Path(a.project).resolve(), 'management/runtime/platform.json').read_text(encoding='utf-8')))['check_seconds']
        time.sleep(max(5, int(seconds)))


if __name__ == '__main__':
    raise SystemExit(main())
