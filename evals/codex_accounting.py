"""Read usage and sanitized limit windows for existing Codex CLI session traces."""

import argparse
import hashlib
import json
from pathlib import Path
import re


METRICS = ('input_tokens', 'cached_input_tokens', 'uncached_input_tokens',
           'output_tokens', 'reasoning_output_tokens')
THREAD_ID = re.compile(r'[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}\Z')
WINDOW_FIELDS = ('used_percent', 'window_minutes', 'resets_at')


def rows(raw):
    for line in raw.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if isinstance(event, dict):
            yield event


def windows(raw):
    latest = {}
    for event in rows(raw):
        payload = event.get('payload', {})
        limits = payload.get('rate_limits') if isinstance(payload, dict) else None
        timestamp = event.get('timestamp')
        if not isinstance(limits, dict) or not isinstance(timestamp, str):
            continue
        for key in ('primary', 'secondary'):
            value = limits.get(key)
            if isinstance(value, dict) and all(type(value.get(name)) in (int, float) for name in WINDOW_FIELDS):
                latest[value['window_minutes']] = {'timestamp': timestamp, **{name: value[name] for name in WINDOW_FIELDS}}
    return list(latest.values())


def collect(trace, sessions):
    raw = trace.read_bytes()
    events = list(rows(raw))
    threads = {event.get('thread_id') for event in events if event.get('type') == 'thread.started'
               and isinstance(event.get('thread_id'), str) and THREAD_ID.fullmatch(event['thread_id'])}
    completions = [event for event in events if event.get('type') == 'turn.completed']
    usage = []
    for event in completions:
        metrics = event.get('usage')
        if not isinstance(metrics, dict):
            continue
        metrics = {key: metrics[key] for key in METRICS if type(metrics.get(key)) is int and metrics[key] >= 0}
        if 'input_tokens' in metrics and 'cached_input_tokens' in metrics and metrics['cached_input_tokens'] <= metrics['input_tokens']:
            metrics['uncached_input_tokens'] = metrics['input_tokens'] - metrics['cached_input_tokens']
        usage.append(metrics)
    observed = []
    if len(threads) == 1:
        thread = next(iter(threads))
        sources = sorted(sessions.glob(f'*/*/*/*{thread}.jsonl'))
        if len(sources) == 1:
            observed = windows(sources[0].read_bytes())
    return {'trace': str(trace), 'trace_sha256': hashlib.sha256(raw).hexdigest(), 'threads': sorted(threads),
            'turns_started': sum(event.get('type') == 'turn.started' for event in events),
            'turns_completed': len(completions), 'usage_events': len(usage),
            'tokens': {key: sum(metric[key] for metric in usage)
                       if usage and len(usage) == len(completions) and all(key in metric for metric in usage) else None
                       for key in METRICS},
            'native_limit_windows': observed, 'limit_status': 'observed' if observed else 'unknown'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sessions', type=Path, default=Path.home() / '.codex/sessions')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('traces', type=Path, nargs='+')
    args = parser.parse_args()
    result = {'records': [collect(path, args.sessions) for path in args.traces],
              'limitations': ['Missing limits or token fields are unknown.',
                              'Uncached input is input minus cached input. Reasoning output is reported separately.']}
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
