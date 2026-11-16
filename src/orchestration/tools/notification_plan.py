"""Build notification drafts from explicit action assignments and summary items."""
import argparse
import json
from pathlib import Path


def plan(items):
    if not isinstance(items, list) or not items:
        raise ValueError('需要非空事项数组')
    groups = {}
    summary = []
    pending = []
    seen = set()
    for index, item in enumerate(items, 1):
        if not isinstance(item, dict):
            raise ValueError(f'第 {index} 项需要对象')
        identity = item.get('id')
        title = item.get('title')
        action = item.get('action')
        if any(not isinstance(v, str) or not v.strip() for v in (identity, title)):
            raise ValueError(f'第 {index} 项缺编号或标题')
        if identity in seen:
            raise ValueError(f'重复事项编号：{identity}')
        seen.add(identity)
        if type(action) is not bool:
            raise ValueError(f'{identity} 缺少布尔字段 action')
        if not action:
            summary.append({'id': identity, 'title': title})
            continue
        recipient = item.get('recipient')
        if not isinstance(recipient, str) or not recipient.strip():
            pending.append({'id': identity, 'title': title, 'reason': '待核实行动人'})
            continue
        groups.setdefault(recipient.strip(), []).append({
            'id': identity, 'title': title, 'blocked': item.get('blocked')
        })
    for actions in groups.values():
        actions.sort(key=lambda item: not bool(item['blocked']))
    return {'direct_actions': groups, 'group_summary': summary, 'pending_recipient': pending}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('items', type=Path)
    args = parser.parse_args()
    try:
        result = plan(json.loads(args.items.read_text(encoding='utf-8')))
    except (OSError, ValueError) as exc:
        parser.exit(1, str(exc) + '\n')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
