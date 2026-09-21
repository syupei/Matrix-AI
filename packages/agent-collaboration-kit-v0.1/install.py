#!/usr/bin/env python3
"""Add local collaboration runtime without replacing professional skills/baselines."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile

sys.dont_write_bytecode = True
PACKAGE = Path(__file__).resolve().parent
SKILL = Path('.agents/skills/professional-agent-collaboration')
sys.path.insert(0, str(PACKAGE / SKILL / 'scripts'))
from coordination import execute, local, CoordinationError

START = '<!-- professional-agent-collaboration:begin -->'
END = '<!-- professional-agent-collaboration:end -->'
BLOCK = START + '''
## 专业 Agent 协作接力

本项目发生已授权的跨专业问询或后续 Agent 需要前置补充时，使用
[professional-agent-collaboration](.agents/skills/professional-agent-collaboration/SKILL.md)
及 [运行入口](collaboration/RUNTIME.md)。具体问题按需委派独立专业子Agent，复用已登记的真实实例并唤醒接续；可自行回答则直接交流，不能确定则由当前主任务统一向人提问，真实回复后重唤责任角色。
普通授权内问答无需用户逐条搬运。角色路由和请求状态由本地账本记录；文件记录不等于消息已发送。遵守原专业授权与阶段边界，不因安装而批准候选、启动后续研发或持续监测。
''' + END + '\n'


def atomic_write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.collaboration-install-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as handle:
            handle.write(data)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)  # This invocation's private staging file only.


def install(target, config):
    root = Path(target).resolve()
    if not root.is_dir():
        raise CoordinationError('target project does not exist')
    if not isinstance(config.get('authorization'), str) or not config['authorization'].strip() or not isinstance(config.get('frontdoor'), dict) or not config['frontdoor'].get('thread_id'):
        raise CoordinationError('actual user authorization and frontdoor task id required')
    cfg = dict(config)
    cfg.setdefault('protocol', 'professional-collaboration/0.1')
    cfg.setdefault('max_rounds', 3)
    cfg.setdefault('max_attempts', 3)
    if cfg['protocol'] != 'professional-collaboration/0.1':
        raise CoordinationError('unsupported protocol')
    for key in ('max_rounds', 'max_attempts'):
        if not isinstance(cfg[key], int) or not 1 <= cfg[key] <= 10:
            raise CoordinationError(key + ' must be 1..10')
    plans, preserved = [], []
    # Validate every intended destination before changing files. Existing custom
    # runtime files conflict instead of silently replacing an installed edition.
    for parent in (PACKAGE / SKILL, PACKAGE / 'collaboration'):
        for src in sorted(parent.rglob('*')):
            if not src.is_file() or '__pycache__' in src.parts or src.suffix == '.pyc':
                continue
            rel = src.relative_to(PACKAGE)
            dest = local(root, str(rel))
            data = src.read_bytes()
            if dest.exists():
                if not dest.is_file():
                    raise CoordinationError('destination is not a file: ' + str(rel))
                if dest.read_bytes() != data:
                    if rel.parts[0] == 'collaboration' and rel.name != 'RUNTIME.md':
                        preserved.append(str(rel))
                        continue  # Project professional protocol remains authoritative.
                    raise CoordinationError('existing runtime differs; review before upgrade: ' + str(rel))
            else:
                plans.append((dest, data))
    role_specs = []
    for role_id, skill_name, owned in [('engineering-intake', 'engineering-intake-agent', ['engineering/intake']), ('product', 'product-agent', ['product']), ('experience-design', 'experience-design-agent', ['design'])]:
        path = '.agents/skills/' + skill_name + '/SKILL.md'
        if local(root, path).is_file():
            for prefix in owned:
                if local(root, prefix) == root:
                    raise CoordinationError('role cannot own the whole project')
            role_specs.append({'id': role_id, 'skill': path, 'write_roots': owned, 'endpoint': {'kind': 'inline', 'id': cfg['frontdoor']['thread_id'], 'session': cfg['frontdoor']['thread_id']} if role_id == 'engineering-intake' else None})
    if not {'engineering-intake', 'product'}.issubset({x['id'] for x in role_specs}):
        raise CoordinationError('install existing product-agent and engineering-intake-agent first')
    db = local(root, 'collaboration/runtime/state.sqlite3')
    registered = {}
    if db.exists():
        status = execute(root, {'op': 'status'})
        if status['config'] != cfg:
            raise CoordinationError('live configuration differs; do not overwrite task routes')
        registered = {x['id']: x for x in status['roles']}
    agents = local(root, 'AGENTS.md')
    if agents != root / 'AGENTS.md':
        raise CoordinationError('AGENTS.md must not redirect to another file')
    original_bytes = agents.read_bytes() if agents.exists() else b''
    before = original_bytes.decode('utf-8')
    if START in before or END in before:
        if before.count(START) != 1 or before.count(END) != 1 or before.index(START) > before.index(END):
            raise CoordinationError('malformed existing managed block; manual review required')
        after = before[:before.index(START)] + BLOCK.rstrip('\n') + before[before.index(END) + len(END):]
    else:
        after = before + ('\n\n' if before else '') + BLOCK
    if after != before:
        if agents.exists():
            sha = hashlib.sha256(original_bytes).hexdigest()[:16]
            backup = local(root, 'collaboration/runtime/install-backups/AGENTS.' + sha + '.md')
            if backup.exists():
                if not backup.is_file() or backup.read_bytes() != original_bytes:
                    raise CoordinationError('existing AGENTS backup does not match original bytes')
            else:
                plans.append((backup, original_bytes))
        plans.append((agents, after.encode()))
    # Check all future parents before the first write, including the database.
    for dest in [p for p, _ in plans] + [db]:
        for parent in dest.parents:
            if parent == root:
                break
            if parent.exists() and not parent.is_dir():
                raise CoordinationError('destination parent is not a directory: ' + str(parent))
    for dest, data in plans:
        atomic_write(dest, data)
    # Per-file atomic installation is rerunnable after an interruption; not a
    # project-wide transaction and never a rollback of professional documents.
    execute(root, {'op': 'init', 'config': cfg})
    for spec in role_specs:
        if spec['id'] not in registered:
            execute(root, {'op': 'register', 'actor': 'coordinator', 'role': spec})
    return {'installed': True, 'project': str(root), 'files_written': [str(p.relative_to(root)) for p, _ in plans], 'preserved_project_protocol': preserved, 'frontdoor': cfg['frontdoor'], 'professional_files_modified': False, 'transport_started': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target', required=True)
    parser.add_argument('--config', required=True, help='JSON config with actual user authorization/frontdoor')
    args = parser.parse_args()
    try:
        print(json.dumps(install(args.target, json.loads(Path(args.config).read_text())), ensure_ascii=False, indent=2))
    except (ValueError, OSError, KeyError) as exc:
        print(json.dumps({'error': str(exc)}, ensure_ascii=False))
        sys.exit(1)
