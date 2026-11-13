#!/usr/bin/env python3
"""Reference macOS write boundary. Kernel policy applies to every descendant/tool.

Only the instance workspace and its temporary runtime cache are writable. This is
not read confidentiality, network isolation, or protection from a hostile host.
Other operating systems must provide an equivalent runner and conformance evidence.
"""
import argparse
import json
import os
from pathlib import Path
import platform
import re
import signal
import subprocess
import tempfile
import time


def safe_workspace(root, iid):
    import re
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,63}', iid):
        raise ValueError('simple instance id required')
    path = root / 'management/instances' / iid / 'workspace'
    if any(p.is_symlink() for p in [path,*path.parents] if p != root and root in p.parents):
        raise ValueError('symlink workspace rejected')
    path.mkdir(parents=True, exist_ok=True)
    if not path.resolve().is_relative_to(root):
        raise ValueError('workspace escapes project')
    # Existing hardlinks permit writes into a protected source inode.
    for p in path.rglob('*'):
        if p.is_symlink() or (p.is_file() and p.stat().st_nlink != 1):
            raise ValueError('workspace links rejected')
    for name in ('private','public'):
        (path/name).mkdir(exist_ok=True)
    return path


def policy(workspace):
    if platform.system() != 'Darwin' or not Path('/usr/bin/sandbox-exec').exists():
        raise ValueError('reference write isolation unsupported on this system')
    # link creation is denied even inside workspace: do not introduce a writable alias
    # to a protected inode. Symlink writes remain subject to the resolved kernel path.
    return ('(version 1)\n(allow default)\n(deny file-write*)\n'
            '(allow file-write* (subpath '+json.dumps(str(workspace))+'))\n'
            '(allow file-write-data (literal "/dev/null") (literal "/dev/tty"))\n'
            '(deny file-link)\n')


def command_template(root, workspace, argv, template, model=None, effort=None):
    """Expand only trusted controller configuration; no shell or task-supplied argv."""
    cfg = template or {}
    args = cfg.get('argv', argv)
    if not isinstance(args, list) or not args or not all(isinstance(x, str) for x in args) or not args[0]:
        raise ValueError('registered runner argv required')
    values = {'project': str(root), 'workspace': str(workspace), 'instance': workspace.parent.name,
              'state': str(workspace / 'private/runner-state'), 'log': str(workspace / 'private/runner-log'),
              'model': model, 'effort': effort}
    def expand(text):
        if not isinstance(text, str):
            raise ValueError('template values must be strings')
        def replace(match):
            key = match[1]
            if key not in values or not isinstance(values[key], str) or not values[key]:
                raise ValueError('missing or unknown template value: ' + key)
            return values[key]
        return re.sub(r'\{([A-Za-z_][A-Za-z0-9_]*)\}', replace, text)
    cwd = Path(expand(cfg.get('cwd', '{project}')))
    if not cwd.is_absolute():
        cwd = root / cwd
    cwd = cwd.resolve()
    if not cwd.is_dir() or not cwd.is_relative_to(root):
        raise ValueError('runner cwd must be an existing project directory')
    unset = cfg.get('unset_env', [])
    if not isinstance(unset, list) or not all(isinstance(x, str) and re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', x) for x in unset):
        raise ValueError('unset_env must contain environment variable names')
    prefix = cfg.get('prepend_paths', False)
    if type(prefix) is not bool:
        raise ValueError('prepend_paths must be boolean')
    return [expand(x) for x in args], cwd, unset, prefix


def run(project, iid, argv, prompt='', timeout=180, stdout=None, stderr=None, started=None, cancelled=None,
        adapter='kernel', model=None, effort=None, template=None):
    root = Path(project).resolve()
    workspace = safe_workspace(root, iid)
    if adapter not in {'kernel', 'command-template'}:
        raise ValueError('unknown isolation adapter')
    if adapter == 'command-template' and not isinstance(template, dict):
        raise ValueError('command-template adapter requires trusted runner configuration')
    command, cwd, unset, prefix = command_template(root, workspace, argv, template, model, effort)
    if prefix:
        prompt = 'Project root for reading and project-relative evidence paths: ' + str(root) + '\nYour writable workspace: ' + str(workspace) + '\n' + prompt
    with tempfile.TemporaryDirectory(prefix='.runtime-', dir=workspace / 'private') as cache:
        if adapter == 'kernel':
            profile = Path(cache) / 'boundary.sb'
            profile.write_text(policy(workspace), encoding='utf-8')
            command = ['/usr/bin/sandbox-exec', '-f', str(profile), *command]
        # A command-template adapter relies on the configured host's tested native boundary.
        env = dict(os.environ, TMPDIR=cache, TMP=cache, TEMP=cache)
        for name in unset:
            env.pop(name, None)
        proc = subprocess.Popen(command, cwd=cwd,
                                stdin=subprocess.PIPE,stdout=stdout or subprocess.PIPE,stderr=stderr or subprocess.PIPE,
                                text=True,env=env,start_new_session=True)
        try:
            if started:
                started(proc.pid)
            end = time.monotonic() + timeout
            first = True
            while True:
                if cancelled and cancelled():
                    raise subprocess.TimeoutExpired(argv, timeout)
                left = end - time.monotonic()
                if left <= 0:
                    raise subprocess.TimeoutExpired(argv, timeout)
                try:
                    out,err=proc.communicate(prompt if first else None,timeout=min(left,0.5))
                    break
                except subprocess.TimeoutExpired:
                    first = False
            try:
                os.killpg(proc.pid,signal.SIGKILL)  # descendants cannot outlive the reported exit
            except ProcessLookupError:
                pass
            return {'exit_code':proc.returncode,'stdout':out,'stderr':err,'pid':proc.pid,'stopped':True,'timed_out':False}
        except (subprocess.TimeoutExpired,KeyboardInterrupt):
            try:
                os.killpg(proc.pid,signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                out,err=proc.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid,signal.SIGKILL)
                out,err=proc.communicate()
            # The parent may exit promptly while a descendant ignores TERM
            # and closes its inherited pipes. Reap that group before declaring
            # the run stopped, even when communicate() has already returned.
            try:
                os.killpg(proc.pid,signal.SIGKILL)
            except ProcessLookupError:
                pass
            return {'exit_code':proc.returncode,'stdout':out,'stderr':err,'pid':proc.pid,'stopped':True,'timed_out':True}
        except BaseException:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            proc.communicate()
            raise


def main():
    p=argparse.ArgumentParser();p.add_argument('--project',required=True);p.add_argument('--instance',required=True)
    p.add_argument('--timeout',type=int,default=180);p.add_argument('argv',nargs=argparse.REMAINDER)
    a=p.parse_args()
    import sys
    argv=a.argv[1:] if a.argv[:1]==['--'] else a.argv
    if not argv:p.error('runner argv required')
    result=run(a.project,a.instance,argv,sys.stdin.read(),a.timeout)
    print(json.dumps(result,ensure_ascii=False))
    return 0 if result['exit_code']==0 else 1


if __name__=='__main__':raise SystemExit(main())
