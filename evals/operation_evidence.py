"""Check product completion claims against project snapshots and observed readback."""
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import unquote

from scoring import audit_records

CLAIMS = {
    'draft': re.compile(r'已(?:生成|形成|保存|写(?:入|好|成)|落盘|交付)[^\n。；]{0,24}(?:草稿|草案|规格)|(?:草稿|草案)[^\n。；]{0,12}已(?:保存|落盘|生成)'),
    'feedback': re.compile(r'已(?:记录|登记|记下)|已(?:将|把)[^\n。；]{0,70}(?:登记|写入|记入|记录在)'),
}
LINK = re.compile(r'(?<!!)\[[^\]\n]+\]\(\s*(?:<([^>\n]+)>|([^\s)]+))\s*\)')


def snapshot(root):
    files = {}
    for folder in ('product', 'shared'):
        project_folder = root / folder
        if project_folder.is_symlink():
            continue
        for path in project_folder.rglob('*'):
            relative = path.relative_to(root)
            if not any((root / p).is_symlink() for p in [relative, *relative.parents]) and path.is_file():
                files[relative.as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return files


def project_path(target, root):
    path = Path(unquote(target).split('#', 1)[0])
    if path.is_absolute():
        # macOS traces mix /var with /private/var for the same sandbox.
        try:
            path = path.resolve().relative_to(root.resolve())
        except ValueError:
            return None
    if not path.parts or '..' in path.parts or path.parts[0] not in {'product', 'shared'}:
        return None
    return path.as_posix()


def observed_receipts(events, after):
    """Accept a successful checker call whose returned digest matches final bytes."""
    receipts = {}
    for record, output, _ in audit_records(events):
        command = record.get('command') or ''
        if (record.get('error') or record.get('status') in {'error', 'unobserved'}
                or record.get('exit_code', 0) != 0
                or 'product_contract.py' not in command or 'reply-receipt' not in command):
            continue
        if isinstance(output, list):
            output = '\n'.join(block.get('text', '') for block in output if isinstance(block, dict))
        if not isinstance(output, str):
            continue
        decoder = json.JSONDecoder()
        for match in re.finditer(r'(?m)^\{', output):
            try:
                receipt, _ = decoder.raw_decode(output[match.start():])
            except ValueError:
                continue
            if (isinstance(receipt, dict) and receipt.get('format') == 'product-reply-receipt/1'
                    and isinstance(receipt.get('path'), str)
                    and receipt.get('sha256') and after.get(receipt.get('path')) == receipt['sha256']):
                receipts[receipt['path']] = receipt
    return receipts


def check(root, kind, reply, events, before, after):
    links = [p for left, right in LINK.findall(reply) if (p := project_path(left or right, root))]
    receipts = observed_receipts(events, after)
    changed = {p for p, digest in after.items() if before.get(p) != digest}
    relevant = [p for p in links if p.startswith('product/specs/') == (kind == 'draft')]
    claims = [m.group() for m in CLAIMS[kind].finditer(reply)]
    matching = sorted(p for p in changed if p in receipts and receipts[p].get('kind') == kind)
    errors = [f'成果链接不存在: {p}' for p in links if p not in after]
    if (claims or relevant) and not matching:
        errors.append('缺本轮写入与对应文件的成功回读回执')
    for path in relevant:
        if path in changed and path not in matching:
            errors.append(f'链接指向已变更成果，但无对应回读回执: {path}')
    return {'claims': claims, 'links': links, 'changed': sorted(changed),
            'receipts': receipts, 'errors': errors}
