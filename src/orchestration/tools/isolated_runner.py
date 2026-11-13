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


def run(project, iid, argv, prompt='', timeout=180, stdout=None, stderr=None, started=None, cancelled=None, adapter='kernel', model=None):
    root = Path(project).resolve()
    workspace = safe_workspace(root,iid)
    with tempfile.TemporaryDirectory(prefix='.runtime-',dir=workspace/'private') as cache:
        profile = Path(cache)/'boundary.sb'
        if adapter == 'kernel':
            profile.write_text(policy(workspace),encoding='utf-8')
            command = ['/usr/bin/sandbox-exec','-f',str(profile),*argv]
            cwd = root
        elif adapter == 'codex-native':
            if not isinstance(model,str) or not model:
                raise ValueError('native adapter requires a pinned model')
            command = ['codex','exec','--ephemeral','--ignore-user-config','--ignore-rules','--skip-git-repo-check',
                       '--sandbox','workspace-write','--json','-C',str(workspace),'-m',model,
                       '--disable','apps','--disable','plugins','--disable','hooks','--disable','browser_use',
                       '--disable','browser_use_external','--disable','computer_use','--disable','multi_agent',
                       '--enable','skip_host_skill_discovery','-c','mcp_servers={}',
                       '-c','model_reasoning_effort="medium"','-c','approval_policy="never"',
                       '-c','project_doc_max_bytes=0','-c','skills.bundled.enabled=false',
                       '-c','sandbox_workspace_write.writable_roots=[]','-c','sandbox_workspace_write.exclude_tmpdir_env_var=true',
                       '-c','sandbox_workspace_write.exclude_slash_tmp=true','-c','shell_environment_policy.ignore_default_excludes=false','-']
            cwd = workspace
            prompt = 'Project root for reading and project-relative evidence paths: '+str(root)+'\nYour writable workspace: '+str(workspace)+'\n'+prompt
        else:
            raise ValueError('unknown isolation adapter')
        env = dict(os.environ, TMPDIR=cache, TMP=cache, TEMP=cache)
        # Do not attach an independent worker to the parent application's control pipe.
        for name in ('CODEX_APP_TOOLS_PIPE_PATH','CODEX_APP_RUNTIME_CLI_PATH','CODEX_INTERNAL_ORIGINATOR_OVERRIDE',
                     'CODEX_SESSION_ID','CODEX_THREAD_ID','CODEX_TOOL_CALL_ID','CODEX_PERMISSION_PROFILE',
                     'CODEX_TASK_WORKSPACE_VERIFYING_IDENTITY','CODEX_TECTONIC_PATH'):
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
