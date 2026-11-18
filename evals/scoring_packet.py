"""Freeze the complete selected business materials and image inputs for one scoring batch."""
import base64
import hashlib
import json
from pathlib import Path


TEXT = {'.md', '.txt', '.html', '.svg', '.css', '.js', '.json', '.py'}
LATE_IMAGES = {
    'late_core_skeleton': ['design/direction/sample.png', 'engineering/skeleton/skeleton.png'],
    'late_asset_anchors': ['design/direction/sample.png', 'visual-evidence/preview.png'],
    'late_implementation_walkthrough': ['design/direction/sample.png', 'engineering/increment/i-1.png'],
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def section(text, name):
    start, end = f'<!-- {name}:start -->', f'<!-- {name}:end -->'
    if text.count(start) != 1 or text.count(end) != 1 or text.index(start) >= text.index(end):
        raise ValueError('scoring guide anchor missing, duplicated or out of order: ' + name)
    return text.split(start, 1)[1].split(end, 1)[0].strip()


def prepare(work, ids, suite_path, readme_path, recheck=None):
    suite = json.loads(suite_path.read_bytes())
    selected = [case for case in suite['cases'] if case['id'] in ids]
    if {case['id'] for case in selected} != set(ids):
        raise ValueError('unknown scoring packet case')
    readme = readme_path.read_text(encoding='utf-8')
    guides = {name: section(readme, name) for name in ('scoring-core', 'scoring-case-notes')}
    sources = {'suite': {'path': str(suite_path), 'sha256': sha(suite_path.read_bytes())},
               'guide': {'path': str(readme_path), 'sha256': sha(readme_path.read_bytes())}}
    identity = sha(json.dumps({'ids': sorted(ids), 'recheck': recheck, 'sources': sources}, sort_keys=True).encode())[:20]
    folder = work/'packets'/identity
    folder.mkdir(parents=True, exist_ok=True)
    inventory, texts, images = [], [], []
    for case in selected:
        cid = case['id']
        for side in ('X', 'Y'):
            root = work/'ws'/cid/side
            artifacts = root/(cid+'-artifacts')
            if not root.is_dir():
                raise ValueError('blind case materials missing: ' + str(root))
            for path in sorted(root.rglob('*')):
                if path.is_symlink():
                    raise ValueError('linked scoring material: ' + str(path))
                if not path.is_file():
                    continue
                relative = path.relative_to(root).as_posix()
                data = path.read_bytes()
                inventory.append({'case': cid, 'side': side, 'path': str(path), 'sha256': sha(data), 'bytes': len(data)})
                business = path.is_relative_to(artifacts) and not path.relative_to(artifacts).parts[0].startswith('_evaluation')
                reply_or_operation = path.parent == root and (path.suffix == '.md' or path.name.endswith('.operation.json'))
                if path.suffix in TEXT and (business or reply_or_operation):
                    texts.append(f'\nFile {path}\nSHA-256 {sha(data)}\n\n{data.decode("utf-8")}\n')
            required = list(LATE_IMAGES.get(cid, []))
            if case.get('visual_preview') and 'visual-evidence/preview.png' not in required:
                receipt = artifacts/'visual-evidence/capture.json'
                if receipt.is_file() and json.loads(receipt.read_bytes()).get('status') == 'captured':
                    required.append('visual-evidence/preview.png')
            for name in required:
                path = artifacts/name
                if not path.is_file():
                    if name == 'visual-evidence/preview.png':
                        receipt = artifacts/'visual-evidence/capture.json'
                        if receipt.is_file() and json.loads(receipt.read_bytes()).get('status') != 'captured':
                            continue
                    raise ValueError('required scoring image missing: ' + str(path))
                images.append({'case': cid, 'side': side, 'path': str(path), 'sha256': sha(path.read_bytes())})
    subset = folder/'suite.selected.json'
    subset.write_text(json.dumps({'rubric_revision': suite.get('rubric_revision'), 'cases': selected}, ensure_ascii=False, indent=2)+'\n')
    guide = folder/'guide.selected.md'
    guide.write_text('\n\n'.join(f'## {name}\n\n{body}' for name, body in guides.items())+'\n')
    material = folder/'business-materials.txt'
    material.write_text(''.join(texts), encoding='utf-8')
    manifest = {'format': 'scoring-packet/1', 'sources': sources, 'rubric_revision': suite.get('rubric_revision'),
                'cases': [case['id'] for case in selected], 'recheck': recheck,
                'files': inventory, 'images': images,
                'selected_suite': {'path': str(subset), 'sha256': sha(subset.read_bytes())},
                'selected_guide': {'path': str(guide), 'sha256': sha(guide.read_bytes())},
                'business_materials': {'path': str(material), 'sha256': sha(material.read_bytes())}}
    packet = folder/'packet.json'
    packet.write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n')
    return packet, manifest


def verify_received_images(folder, packet, sessions=None):
    """Require the expected PNG bytes in the scorer's actual native input stream."""
    expected = {item['sha256'] for item in packet['images']}
    if not expected:
        return {'status': 'no_visual_inputs_required', 'expected': [], 'received': []}
    logs = (folder/'run.log').read_bytes()
    ids = []
    for line in logs.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if event.get('type') == 'thread.started':
            ids.append(event['thread_id'])
    if len(ids) != 1:
        raise ValueError('scoring session identity missing or ambiguous')
    roots = sessions or Path.home()/'.codex/sessions'
    files = list(roots.glob('*/*/*/*'+ids[0]+'.jsonl'))
    if len(files) != 1:
        raise ValueError('native image receipt unavailable for scorer')
    received, kept, proof = set(), [], []

    def image_values(value):
        if isinstance(value, dict):
            if value.get('type') in {'input_image', 'image'}:
                url = value.get('image_url') or value.get('url')
                if isinstance(url, str) and url.startswith('data:image/'):
                    yield url
            for nested in value.values():
                if isinstance(nested, (dict, list)):
                    yield from image_values(nested)
        elif isinstance(value, list):
            for nested in value:
                yield from image_values(nested)

    for number, line in enumerate(files[0].read_bytes().splitlines(keepends=True), 1):
        try:
            event = json.loads(line)
        except ValueError:
            continue
        hashes = {sha(base64.b64decode(url.split(',', 1)[1], validate=True)) for url in image_values(event)}
        if hashes & expected:
            received.update(hashes)
            kept.append(line)
            proof.append({'line': number, 'sha256': sha(line), 'image_hashes': sorted(hashes)})
    missing = expected - received
    result = {'status': 'incomplete' if missing else 'received', 'expected': sorted(expected),
              'received': sorted(expected & received), 'missing': sorted(missing),
              'native_source_name': files[0].name, 'native_source_sha256': sha(files[0].read_bytes()), 'lines': proof}
    (folder/'visual-input.raw.jsonl').write_bytes(b''.join(kept))
    (folder/'visual-input.json').write_text(json.dumps(result, indent=2)+'\n')
    if missing:
        raise ValueError('visual judgment incomplete: scorer did not receive required image bytes')
    return result
