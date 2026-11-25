"""Print-only service plans and read-only heartbeat diagnosis. Never installs a service."""
import base64
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import plistlib
import shlex
import sys

HEARTBEAT = 'management/runtime/scheduler-heartbeat.json'


def health(root, now=None):
    path = Path(root) / HEARTBEAT
    if not path.is_file():
        return {'state': 'unknown', 'message': '未记录调度器心跳，不能确认是否运行'}
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        interval = data['check_seconds']
        if type(interval) is not int or interval < 5:
            raise ValueError('invalid interval')
        at = datetime.fromisoformat(data['checked_at'])
        if at.tzinfo is None:
            raise ValueError('missing timezone')
        age = ((now or datetime.now(timezone.utc)) - at).total_seconds()
        if age < -5:
            raise ValueError('heartbeat is in the future')
    except (ValueError, TypeError, KeyError, OSError):
        return {'state': 'unknown', 'message': '调度器心跳无效，核对记录与系统时间'}
    state = 'stale' if age > 2 * interval else 'error' if data.get('result') == 'error' else 'recent'
    message = {'stale': '调度器可能已停，按 START.md 重启',
               'error': '调度器最近检查出错，查看 scheduler.log 与运行输出',
               'recent': '近期有调度器检查记录；不代表任务或实例正在执行'}[state]
    return dict(state=state, message=message, checked_at=data['checked_at'], check_seconds=interval,
                age_seconds=round(age), result=data.get('result'))


def unit_arg(value):
    # systemd ExecStart has its own quoting, % specifiers and $ expansion; it is not a shell command.
    return '"' + str(value).replace('\\', '\\\\').replace('"', '\\"').replace('%', '%%').replace('$', '$$') + '"'


def plan(project, service, seconds=60):
    root = Path(project).resolve()
    if service not in {'launchd', 'systemd', 'cron'}:
        raise ValueError('unknown service')
    if type(seconds) is not int or seconds < 5:
        raise ValueError('interval must be an integer >= 5')
    argv = [sys.executable, '-B', str(Path(__file__).with_name('scheduler.py').resolve()), '--project', str(root)]
    if any(any(c in value for c in '\n\r\x00') for value in argv):
        raise ValueError('service paths cannot contain line breaks or null bytes')
    label = 'matrix-scheduler-' + hashlib.sha256(str(root).encode()).hexdigest()[:12]
    home = Path.home()
    files, start, stop = {}, [], []
    if service == 'launchd':
        target = home / 'Library/LaunchAgents' / (label + '.plist')
        files[str(target)] = plistlib.dumps(dict(Label=label, ProgramArguments=argv + ['--interval', str(seconds)],
            WorkingDirectory=str(root), RunAtLoad=True, KeepAlive=True, ThrottleInterval=10,
            StandardOutPath=str(root / 'management/runtime/scheduler-service.log'),
            StandardErrorPath=str(root / 'management/runtime/scheduler-service.log'))).decode()
        domain = 'gui/$(id -u)'
        start = ['launchctl bootstrap ' + domain + ' ' + shlex.quote(str(target))]
        stop = ['launchctl bootout ' + domain + ' ' + shlex.quote(str(target))]
    elif service == 'systemd':
        target = home / '.config/systemd/user' / (label + '.service')
        # No WorkingDirectory is needed: --project is absolute and subprocesses set their cwd explicitly.
        files[str(target)] = ('[Unit]\nDescription=Project scheduler\n\n[Service]\nType=simple\nExecStart=' +
            ' '.join(unit_arg(x) for x in argv + ['--interval', str(seconds)]) +
            '\nRestart=always\nRestartSec=10\n\n[Install]\nWantedBy=default.target\n')
        start = ['systemctl --user daemon-reload', 'systemctl --user enable --now ' + label + '.service']
        stop = ['systemctl --user disable --now ' + label + '.service']
    else:
        # Cron is minute-granular; encode arbitrary project paths instead of exposing them to cron's % parser.
        seconds = 60
        encoded = base64.b64encode(json.dumps(argv + ['--once', '--interval', '60']).encode()).decode()
        program = 'import base64,json,os;a=json.loads(base64.b64decode(' + repr(encoded) + '));os.execv(a[0],a)'
        line = '* * * * * ' + shlex.join([sys.executable, '-c', program]).replace('%', '\\%') + ' # ' + label
        files[str(root / 'management/runtime' / (label + '.cron'))] = line + '\n'
        start = ['crontab -e  # append the generated line; preserve all other entries']
        stop = ['crontab -e  # remove only the line ending with ' + label]
    # Commands are text for a person to review and run. Producing this plan never executes them.
    write = 'from pathlib import Path; files=' + repr(files) + '; ' + \
            '[(Path(p).parent.mkdir(parents=True,exist_ok=True),Path(p).write_text(s,encoding="utf-8")) for p,s in files.items()]'
    return dict(service=service, label=label, project=str(root), check_seconds=seconds, files=files,
                install_commands=[shlex.join([sys.executable, '-c', write])] + start, stop_commands=stop,
                note='只输出，不安装、不启动；先确认项目已初始化、平台命令可非交互运行。用户服务依赖登录会话；运行环境和凭证需由使用者配置。停止服务不等于停止已启动的任务。')
