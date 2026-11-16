"""Validate the matrix-billing/1 JSON format (standard library only)."""
import argparse
import json
from pathlib import Path

KINDS = {
    'pricing': ('amount', 'currency', 'unit', 'eligibility'),
    'charge': ('amount', 'currency', 'trigger', 'duplicate_handling', 'unknown_result'),
    'refund': ('eligibility', 'amount_rule', 'deadline', 'destination_or_exception'),
    'auto_renew': ('trial', 'interval', 'amount', 'currency', 'notice', 'cancel_effect'),
}
COMMON = ('source', 'financial_impact', 'compliance_questions', 'notify', 'review', 'checks')


def text(value):
    return isinstance(value, str) and bool(value.strip())


def validate(data, handoff=False, required_kinds=()):
    if not isinstance(data, dict):
        return ['$：应为 JSON 对象']
    errors = []
    rules = data.get('rules')
    if data.get('schema') != 'matrix-billing/1':
        errors.append('schema：必须为 matrix-billing/1')
    if not isinstance(rules, list) or not rules:
        return errors + ['rules：至少登记一条适用规则']
    if set(data) - {'schema', 'rules'}:
        errors.append('$：只允许 schema 和 rules')
    seen = set()
    present_kinds = set()
    for index, rule in enumerate(rules):
        path = f'rules[{index}]'
        if not isinstance(rule, dict):
            errors.append(f'{path}：应为对象')
            continue
        def error(field, reason):
            errors.append(f'{path}.{field}：{reason}')
        identity = rule.get('id')
        if not text(identity) or identity in seen:
            error('id', '需要非空且唯一的规则编号')
        else:
            seen.add(identity)
        kind = rule.get('kind')
        status = rule.get('status')
        if not isinstance(kind, str) or kind not in KINDS:
            error('kind', '请选择 pricing、charge、refund 或 auto_renew')
            continue
        present_kinds.add(kind)
        if status not in ('draft', 'approved'):
            error('status', '应为 draft 或 approved')
        if rule.get('risk') not in ('F0', 'F1'):
            error('risk', '需标 F1 或由人判定为 F0')
        allowed = {'id', 'kind', 'status', 'risk', 'terms', 'pending', 'approval', *COMMON}
        for key in sorted(set(rule) - allowed):
            error(key, '未知字段')
        for field in COMMON:
            if field not in ('review', 'checks') and not text(rule.get(field)):
                error(field, '请填写具体内容')
        review = rule.get('review')
        if not isinstance(review, dict) or any(not text(review.get(key)) for key in ('owner', 'method')):
            error('review', '填写检验责任方 owner 与检验方式 method')
        checks = rule.get('checks')
        if not isinstance(checks, list) or not checks:
            error('checks', '至少一项带 scenario 和 expected 的可执行检验')
        else:
            for i, check in enumerate(checks):
                if not isinstance(check, dict) or any(not text(check.get(key)) for key in ('scenario', 'expected')):
                    error(f'checks[{i}]', '补齐检验情境 scenario 与预期结果 expected')
        terms = rule.get('terms')
        pending = rule.get('pending')
        if not isinstance(terms, dict):
            error('terms', '应为对象')
            terms = {}
        if not isinstance(pending, dict):
            error('pending', '应为对象，键为待定条款，值为待核实事项')
            pending = {}
        for key in sorted((set(terms) | set(pending)) - set(KINDS[kind])):
            error('terms/pending.' + key, '此类规则没有该条款')
        for key in KINDS[kind]:
            if text(terms.get(key)) == text(pending.get(key)):
                error('terms.' + key, '应在 terms 填写明确条款，或在 pending 列为待定，两处只能填一处')
            elif key in terms and not text(terms[key]) or key in pending and not text(pending[key]):
                error(key, '字段存在时必须是非空字符串')
        if status == 'approved':
            if pending:
                error('pending', '仍有待定条款，不能标为 approved')
            approval = rule.get('approval')
            for field in ('person', 'quote', 'version'):
                if not isinstance(approval, dict) or not text(approval.get(field)):
                    error('approval.' + field, '提供决定人、确认原话和对应规则版本')
        elif 'approval' in rule:
            error('approval', '草案无需填写批准记录')
        if handoff and status != 'approved':
            error('status', '正式研发交接要求 approved，草案可送审')
    for kind in sorted(set(required_kinds) - present_kinds):
        errors.append(f'rules：缺少 {kind} 类规则，请单独登记该类条款')
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('file', type=Path)
    parser.add_argument('--handoff', action='store_true')
    parser.add_argument('--require-kind', choices=sorted(KINDS), action='append', default=[])
    args = parser.parse_args()
    try:
        errors = validate(json.loads(args.file.read_text(encoding='utf-8')), args.handoff, args.require_kind)
    except (OSError, ValueError) as exc:
        errors = [f'{args.file}：无法读取有效 JSON：{exc}']
    if errors:
        parser.exit(1, '\n'.join(errors) + '\n')
    print('计费规则格式校验通过')


if __name__ == '__main__':
    main()
