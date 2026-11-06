#!/usr/bin/env python3
"""Where the tokens of a platform run went: per PM session and per instance run, the host's token usage and the size
of what each command returned, by kind (search, rule reading, task tool reads and writes, launches).

  run_usage.py <project folder>          reads the run and PM logs under management/runtime/logs/ (plain or compressed),
                                         and the older places management/runtime/pm-runs/ and management/instances/*/runs/

The logs are the host's JSON event streams (Codex `exec --json`); other hosts may need another reader.
"""
import gzip
import json
from pathlib import Path
import re
import sys

READS = ('continue', 'status', 'task', 'tasks_for', 'events', 'team', 'audit', 'query')


def kind(command):
    c = command.replace(' ', '').replace('\\"', '"')
    if 'pm_tasks.py' in command:
        if '--render' in command:
            return 'tool:render'
        op = re.search(r'"op":"(\w+)"', c)
        return 'tool:' + (op.group(1) if op else 'other') + (':read' if op and op.group(1) in READS else '')
    if 'launch.py' in command:
        return 'launch'
    if re.search(r'\b(rg|grep|find|fd)\b', command):
        return 'search'
    if re.search(r'\b(cat|sed|head|tail|nl|less|wc)\b', command):
        return 'read'
    return 'other'


def session(path):
    usage, commands = [0, 0, 0], []
    for line in (gzip.open(path, 'rt', errors='ignore') if path.suffix == '.gz' else open(path, errors='ignore')):
        line = line.strip()
        if not line.startswith('{'):
            continue
        try:
            e = json.loads(line)
        except ValueError:
            continue
        item = e.get('item') or {}
        if e.get('type') == 'item.completed' and item.get('type') == 'command_execution':
            commands.append((kind(item.get('command', '')), len(item.get('aggregated_output') or ''), item.get('command', '')[:100]))
        if e.get('type') == 'turn.completed':
            u = e.get('usage') or {}
            usage = [usage[0] + u.get('input_tokens', 0), usage[1] + u.get('cached_input_tokens', 0), usage[2] + u.get('output_tokens', 0)]
    return usage, commands


def main():
    root = Path(sys.argv[1])
    logs = [('PM', p) for p in sorted(root.glob('management/runtime/pm-runs/*.log')) + sorted(root.glob('management/runtime/logs/pm-*.log*'))] + \
           [('RUN', p) for p in sorted(root.glob('management/instances/*/runs/*.log')) + sorted(root.glob('management/runtime/logs/run-*.log*'))]
    totals, by_kind, out = [0, 0, 0], {}, []
    for who, path in logs:
        usage, commands = session(path)
        if not usage[0]:
            continue
        totals = [a + b for a, b in zip(totals, usage)]
        kinds = {}
        for k, n, _ in commands:
            kinds[k] = kinds.get(k, 0) + n
            by_kind[k] = by_kind.get(k, 0) + n
        out.append(dict(who=who, log=path.name, input=usage[0], cached=usage[1], output=usage[2], commands=len(commands),
                        returned=sum(n for _, n, _ in commands), by_kind=dict(sorted(kinds.items(), key=lambda x: -x[1])),
                        largest=[dict(chars=n, kind=k, command=c) for k, n, c in sorted(commands, key=lambda x: -x[1])[:3]]))
    print(json.dumps(dict(input=totals[0], cached=totals[1], output=totals[2],
                          pm_sessions=[s['input'] for s in out if s['who'] == 'PM'], runs=[s['input'] for s in out if s['who'] == 'RUN'],
                          returned_by_kind=dict(sorted(by_kind.items(), key=lambda x: -x[1])), sessions=out), ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
