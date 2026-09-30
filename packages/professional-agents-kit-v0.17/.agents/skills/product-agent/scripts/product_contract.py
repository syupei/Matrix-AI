#!/usr/bin/env python3
"""Local structural checks and derived handoffs; never a product-quality verdict."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys

FORMAT = 'product-contract/0.1'
BASELINE = 'product-baseline/0.1'
RECEIPT = 'product-check/0.1'
STAGES = ['product', 'design', 'implementation', 'post_launch']
METHODS = {
    'product': {'reasoning', 'tool_readback', 'prototype', 'implementation', 'user_test', 'measurement'},
    'design': {'tool_readback', 'prototype', 'user_test'},
    'implementation': {'implementation', 'user_test'},
    'post_launch': {'measurement', 'user_test'},
}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def location(root, name):
    require(nonempty(name), '路径不能为空')
    rel = Path(name)
    require(not rel.is_absolute() and '..' not in rel.parts and str(rel) == name,
            '须使用项目内规范相对路径: ' + name)
    target = root / rel
    require(target.resolve().is_relative_to(root), '路径越过项目边界: ' + name)
    require(not any(p.is_symlink() for p in [target, *target.parents] if p != root),
            '不读取或写入符号链接: ' + name)
    return target


def load_json(path):
    # Reject duplicate keys; silently retaining the last value could hide scope changes.
    def unique(pairs):
        out = {}
        for key, value in pairs:
            require(key not in out, '重复 JSON 字段: ' + key)
            out[key] = value
        return out
    return json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=unique)


def json_text(data):
    return json.dumps(data, ensure_ascii=False, indent=2) + '\n'


def write_new(root, name, text):
    target = location(root, name)
    require(not target.exists(), '输出已存在，请使用新版本路径，保留原件: ' + name)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open('x', encoding='utf-8') as handle:
        handle.write(text)


def parse_document(root, name):
    path = location(root, name)
    require(path.suffix.lower() == '.md', '产品来源须为 Markdown: ' + name)
    raw = path.read_bytes()
    text = raw.decode('utf-8')
    lines = text.splitlines(keepends=True)
    headings, blocks = [], []
    fence = None
    for index, line in enumerate(lines):
        value = line.rstrip('\r\n')
        if fence:
            char, count, start, info = fence
            if re.fullmatch(r' {0,3}' + re.escape(char) + '{' + str(count) + r',}\s*', value):
                if info == 'product-contract':
                    blocks.append((start, index, ''.join(lines[start + 1:index])))
                fence = None
            continue
        opened = re.fullmatch(r' {0,3}(`{3,}|~{3,})([^\r\n]*)', value)
        if opened:
            fence = (opened[1][0], len(opened[1]), index, opened[2].strip())
            continue
        heading = re.fullmatch(r'(#{1,6}) +(.+)', value)
        if heading:
            headings.append((index, len(heading[1]), value))
    require(fence is None, name + ': 存在未闭合代码块')
    require(len(blocks) == 1, name + ': 应有且仅有一个 product-contract JSON 块')
    start, end, block = blocks[0]
    # Use the same duplicate-key behavior for embedded JSON as for other artifacts.
    def pairs(values):
        result = {}
        for key, value in values:
            require(key not in result, name + ': 重复 JSON 字段 ' + key)
            result[key] = value
        return result
    meta = json.loads(block, object_pairs_hook=pairs)
    require(isinstance(meta, dict) and meta.get('format') == FORMAT, name + ': 格式版本错误')
    require(not (meta.keys() - {'format', 'revision', 'items'}), name + ': 未知文档字段')
    require(nonempty(meta.get('revision')), name + ': 缺少正文修订 revision')
    require(isinstance(meta.get('items'), list) and meta['items'], name + ': items 不能为空')
    nodes = {}
    for item in meta['items']:
        require(isinstance(item, dict), name + ': 条目须为对象')
        require(not (item.keys() - {'id', 'kind', 'heading', 'refs', 'audiences', 'verify_at', 'coverage', 'reason'}),
                name + ': 未知条目字段')
        ident = item.get('id')
        require(nonempty(ident) and not any(c.isspace() or c in '#/\\' for c in ident),
                name + ': 无效条目 ID')
        key = name + '#' + ident
        require(key not in nodes, '重复条目: ' + key)
        kind = item.get('kind')
        require(kind in ['context', 'requirement', 'acceptance', 'outcome'], key + ': 未知 kind')
        matches = [h for h in headings if h[2] == item.get('heading')]
        require(len(matches) == 1, key + ': 标题不存在或不唯一')
        first, level, title = matches[0]
        last = next((i for i, depth, _ in headings if i > first and depth <= level), len(lines))
        body = ''.join(line for i, line in enumerate(lines[first:last], start=first)
                       if not start <= i <= end)
        require(bool(''.join(body.splitlines()[1:]).strip()), key + ': 正文为空')
        refs = item.get('refs', [])
        require(isinstance(refs, list) and all(nonempty(r) for r in refs) and len(set(refs)) == len(refs),
                key + ': refs 须为不重复的条目引用列表')
        audiences = item.get('audiences', [])
        require(isinstance(audiences, list) and all(nonempty(r) for r in audiences), key + ': audiences 错误')
        if kind == 'acceptance':
            require(item.get('verify_at') in STAGES[:-1], key + ': 验收须指定 product/design/implementation')
        if kind == 'outcome':
            require(item.get('verify_at') == 'post_launch', key + ': 效果指标只能在 post_launch 核验')
        if kind == 'requirement':
            require(item.get('coverage', 'required') in ['required', 'not_applicable'], key + ': coverage 错误')
            if item.get('coverage') == 'not_applicable':
                require(nonempty(item.get('reason')), key + ': 不适用须给出理由')
        nodes[key] = {'source': name, **item, 'sha256': digest(body.encode()),
                      'line': first + 1, 'body': body}
    return {'path': name, 'revision': meta['revision'], 'sha256': digest(raw)}, nodes


def collect(root, names):
    require(names and len(set(names)) == len(names), '来源不能为空或重复')
    sources, items = [], {}
    for name in names:
        source, nodes = parse_document(root, name)
        sources.append(source)
        items.update(nodes)
    return sources, items


def issue(code, item, message, severity='error'):
    return {'code': code, 'item': item, 'message': message, 'severity': severity}


def structure(items):
    issues = []
    covered = set()
    for key, node in items.items():
        for ref in node.get('refs', []):
            if ref not in items:
                issues.append(issue('missing_reference', key, '引用不在本次交付来源中: ' + ref))
            elif node['kind'] == 'acceptance':
                covered.add(ref)
    for key, node in items.items():
        if node['kind'] == 'requirement' and node.get('coverage', 'required') == 'required' and key not in covered:
            issues.append(issue('uncovered_requirement', key, '缺少直接关联的验收条目；先补产品判据'))
    return issues


def public_items(items):
    return {key: {k: v for k, v in node.items() if k != 'body'} for key, node in items.items()}


def capture(root, sources):
    docs, items = collect(root, sources)
    errors = structure(items)
    require(not errors, json_text(errors))
    return {'format': BASELINE, 'created_at': now(), 'meaning': '交付候选快照；不代表批准或质量通过',
            'sources': docs, 'items': public_items(items)}


def read_baseline(root, name):
    path = location(root, name)
    data = load_json(path)
    require(isinstance(data, dict) and data.get('format') == BASELINE, '基线格式版本错误')
    sources = data.get('sources')
    require(isinstance(sources, list) and sources, '基线来源不能为空')
    require(isinstance(data.get('items'), dict) and data['items'], '基线条目不能为空')
    seen = set()
    for source in sources:
        require(isinstance(source, dict), '无效基线来源')
        name = source.get('path')
        location(root, name)
        require(name not in seen and nonempty(source.get('revision')) and
                bool(re.fullmatch('[0-9a-f]{64}', source.get('sha256', ''))), '无效或重复基线来源')
        seen.add(name)
    for key, item in data['items'].items():
        require(isinstance(item, dict) and item.get('source') in seen and
                key == item['source'] + '#' + str(item.get('id')), '无效基线条目: ' + key)
        require(bool(re.fullmatch('[0-9a-f]{64}', item.get('sha256', ''))), '无效条目指纹: ' + key)
    return data, digest(path.read_bytes())


def draft_receipt(root, baseline):
    data, pin = read_baseline(root, baseline)
    return {'format': RECEIPT, 'baseline': baseline, 'baseline_sha256': pin,
            'checker': '', 'checked_at': '', 'stage': 'product',
            'results': [{'item': key, 'status': 'not_checked', 'method': '', 'evidence': [], 'note': ''}
                        for key, node in data['items'].items() if node['kind'] in ['acceptance', 'outcome']]}


def check_receipt(root, baseline_name, pin, items, receipt_name, stage):
    issues, checked = [], {}
    receipt = load_json(location(root, receipt_name))
    require(isinstance(receipt, dict) and receipt.get('format') == RECEIPT, '核验记录格式错误')
    if receipt.get('baseline') != baseline_name or receipt.get('baseline_sha256') != pin:
        issues.append(issue('stale_receipt', receipt_name, '核验记录对应其它交付快照，须评估采用范围'))
    require(receipt.get('stage') in STAGES, '核验记录阶段无效')
    require(isinstance(receipt.get('results'), list), '核验记录 results 须为列表')
    if any(r.get('status') in ['passed', 'failed'] for r in receipt['results'] if isinstance(r, dict)):
        require(nonempty(receipt.get('checker')) and nonempty(receipt.get('checked_at')), '实际核验须注明检查者与时间')
        datetime.fromisoformat(receipt['checked_at'].replace('Z', '+00:00'))
    for result in receipt['results']:
        require(isinstance(result, dict), '核验结果须为对象')
        key = result.get('item')
        require(nonempty(key), '核验结果缺少条目')
        require(key not in checked, '核验结果重复: ' + key)
        checked[key] = result
        if key not in items or items[key]['kind'] not in ['acceptance', 'outcome']:
            issues.append(issue('unknown_checked_item', key, '核验项不在当前验收/效果范围中'))
            continue
        state = result.get('status')
        require(state in ['passed', 'failed', 'not_checked'], key + ': 核验状态错误')
        if state == 'failed':
            issues.append(issue('failed_check', key, '核验失败；读取专业记录处理'))
        if state != 'passed':
            continue
        due = items[key]['verify_at']
        if STAGES.index(receipt['stage']) < STAGES.index(due) or result.get('method') not in METHODS[due]:
            issues.append(issue('invalid_verification_method', key, '核验阶段或方式不足以支持本条通过'))
        evidence = result.get('evidence')
        if not isinstance(evidence, list) or not evidence:
            issues.append(issue('missing_evidence', key, '声称通过但没有本地可回查的证据记录'))
            continue
        for entry in evidence:
            if not isinstance(entry, dict) or not nonempty(entry.get('path')):
                issues.append(issue('missing_evidence', key, '外部链接须附实际回读或验证记录，URL 本身不是核验'))
                continue
            try:
                path = location(root, entry['path'])
                require(path.is_file(), '证据文件不存在: ' + entry['path'])
                require(digest(path.read_bytes()) == entry.get('sha256'), '证据指纹已变化: ' + entry['path'])
            except (ValueError, OSError) as error:
                issues.append(issue('invalid_evidence', key, str(error)))
    for key, node in items.items():
        if node['kind'] not in ['acceptance', 'outcome']:
            continue
        due = node['verify_at']
        if STAGES.index(due) > STAGES.index(stage):
            issues.append(issue('downstream_verification', key, '待 ' + due + ' 阶段验证', 'info'))
        elif checked.get(key, {}).get('status') != 'passed':
            issues.append(issue('pending_verification', key, '本阶段应核验但尚未通过'))
    return issues


def check(root, baseline_name, stage='product', receipt_name=None):
    require(stage in STAGES, '未知阶段')
    baseline, pin = read_baseline(root, baseline_name)
    issues, current, docs = [], {}, []
    for old in baseline['sources']:
        try:
            source, nodes = parse_document(root, old['path'])
            docs.append(source)
            current.update(nodes)
            if source['sha256'] != old['sha256'] or source['revision'] != old['revision']:
                issues.append(issue('stale_source', old['path'], '正文或声明版本已变化，评估影响后生成新快照'))
        except (ValueError, OSError, UnicodeError) as error:
            issues.append(issue('invalid_source', old['path'], str(error)))
    issues.extend(structure(current))
    before, after = baseline['items'], public_items(current)
    def semantic_node(node):
        return {k: v for k, v in node.items() if k != 'line'} if node else None
    changed = sorted(k for k in before.keys() | after.keys()
                     if semantic_node(before.get(k)) != semantic_node(after.get(k)))
    impacted = set(changed)
    union = {k: set(before.get(k, {}).get('refs', [])) | set(after.get(k, {}).get('refs', []))
             for k in before.keys() | after.keys()}
    while True:
        added = {k for k, refs in union.items() if refs & impacted} - impacted
        if not added:
            break
        impacted.update(added)
    if changed:
        issues.append(issue('changed_items', baseline_name, '条目或结构已变化，见 changed_items / affected_items'))
    if receipt_name:
        issues.extend(check_receipt(root, baseline_name, pin, current, receipt_name, stage))
    else:
        for key, node in current.items():
            if node['kind'] in ['acceptance', 'outcome']:
                due = node['verify_at']
                future = STAGES.index(due) > STAGES.index(stage)
                issues.append(issue('downstream_verification' if future else 'pending_verification', key,
                                    '待 ' + due + ' 阶段验证' if future else '尚未提供当前阶段核验记录',
                                    'info' if future else 'error'))
    return {'format': 'product-report/0.1', 'generated_at': now(), 'stage': stage,
            'baseline': baseline_name, 'baseline_sha256': pin,
            'mechanical_checks_passed': not any(i['severity'] == 'error' for i in issues),
            'meaning': '仅核对登记范围、文件和证据引用；不验证证据真实性、语义质量、范围完整性或人的批准',
            'sources': docs, 'registered_items': len(current), 'changed_items': changed,
            'affected_items': sorted(impacted), 'issues': issues}


def report_markdown(report):
    lines = ['# 产品交付核对', '',
             '机械检查：' + ('未发现阻断项' if report['mechanical_checks_passed'] else '存在待处理项'),
             '阶段：' + report['stage'], '交付快照：' + report['baseline'],
             '生成时间：' + report['generated_at'], '', report['meaning'], '', '## 需要处理或交接的内容', '']
    for finding in report['issues']:
        lines.append('- [' + finding['severity'] + '] ' + finding['item'] + '：' + finding['message'])
    if not report['issues']:
        lines.append('本次登记范围内未发现机械检查问题。')
    lines.extend(['', '## 变更影响', '', '直接变化：' + (', '.join(report['changed_items']) or '无'),
                  '关联回查：' + (', '.join(report['affected_items']) or '无'),
                  '', '以上影响只沿已登记引用传播；不受影响的确认继续保留，实际语义影响由专业角色核对。', ''])
    return '\n'.join(lines)


def handoff(root, baseline_name, role):
    baseline, pin = read_baseline(root, baseline_name)
    docs, items = collect(root, [s['path'] for s in baseline['sources']])
    require(docs == baseline['sources'] and public_items(items) == baseline['items'], '源已变化，不能生成旧快照交接稿')
    require(not structure(items), '交付结构不完整')
    selected = {k for k, node in items.items() if not node.get('audiences') or role in node['audiences']}
    require(selected, '当前没有该接收者的条目: ' + role)
    while True:
        added = {r for key in selected for r in items[key].get('refs', [])} - selected
        if not added:
            break
        selected.update(added)
    lines = ['# ' + role + ' 产品依据阅读稿', '', '只读派生内容；修改返回下列有效源。',
             '生成时间：' + now(), '交付快照：' + baseline_name, '快照指纹：' + pin,
             '生成不表示产品已获批准、接收方已收到或检查已经通过。', '', '## 来源与版本', '']
    lines.extend('- ' + s['path'] + ' · ' + s['revision'] + ' · ' + s['sha256'] for s in docs)
    for key, node in items.items():
        if key in selected:
            lines.extend(['', '---', '', '条目：' + key,
                          '编辑源：' + node['source'] + '（第 ' + str(node['line']) + ' 行）',
                          '验证阶段：' + node.get('verify_at', '按原专业判断'), '', node['body'].rstrip()])
    lines.extend(['', '交付任务、可自决范围、人的确认与待决问题继续读取原交付说明；本稿不新增产品要求。', ''])
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True)
    commands = parser.add_subparsers(dest='command', required=True)
    p = commands.add_parser('capture')
    p.add_argument('--source', action='append', required=True)
    p.add_argument('--output', required=True)
    for command in ['check', 'draft', 'handoff']:
        p = commands.add_parser(command)
        p.add_argument('--baseline', required=True)
        p.add_argument('--output', required=command != 'check')
        if command == 'check':
            p.add_argument('--stage', choices=STAGES, default='product')
            p.add_argument('--receipt')
            p.add_argument('--json', action='store_true')
        if command == 'handoff':
            p.add_argument('--role', required=True)
    args = parser.parse_args()
    try:
        root = Path(args.root).resolve()
        require(root.is_dir(), '项目根目录不存在')
        status = 0
        if args.command == 'capture':
            text = json_text(capture(root, args.source))
        elif args.command == 'draft':
            text = json_text(draft_receipt(root, args.baseline))
        elif args.command == 'handoff':
            text = handoff(root, args.baseline, args.role)
        else:
            report = check(root, args.baseline, args.stage, args.receipt)
            text = json_text(report) if args.json else report_markdown(report)
            status = 0 if report['mechanical_checks_passed'] else 1
        if args.output:
            write_new(root, args.output, text)
            print('已生成：' + args.output)
        else:
            print(text, end='')
        return status
    except (ValueError, OSError, UnicodeError, KeyError, TypeError) as error:
        print('核对未完成：' + str(error), file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
