"""Immutable evidence bundles and display/response bindings shared by consumer tools.

These checks bind bytes and scope; host authentication still establishes who acted.
"""
import hashlib
import json
from pathlib import Path
import re
import struct
import tempfile
import os
import fcntl
import zlib
import contextvars
import contextlib
import sqlite3
import sys
from types import ModuleType

# Several consumer tools load this helper by file path. Share read tracking across those
# module instances so a nested gate cannot silently escape its caller's snapshot.
_shared = sys.modules.setdefault('_matrix_evidence_reads', ModuleType('_matrix_evidence_reads'))
if not hasattr(_shared, 'collectors'):
    _shared.collectors = contextvars.ContextVar('matrix_evidence_reads', default=())


@contextlib.contextmanager
def track_reads():
    reads = {}
    token = _shared.collectors.set((*_shared.collectors.get(), reads))
    try:
        yield reads
    finally:
        _shared.collectors.reset(token)


def note_read(path):
    path = Path(path).resolve()
    for collector in _shared.collectors.get():
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
        old = collector.setdefault(path, sha)
        require(old == sha, 'evidence changed while the gate was reading it: ' + str(path))


def require(ok, message):
    if not ok:
        raise ValueError(message)


def digest(data):
    return hashlib.sha256(json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def file(root, name):
    root = Path(root).resolve()
    require(isinstance(name, str) and name.strip(), 'project file path required')
    rel = Path(name)
    require(not rel.is_absolute() and '..' not in rel.parts, 'project-relative path required: ' + name)
    path = root / rel
    require(path.resolve().is_relative_to(root) and path.is_file()
            and not any(p.is_symlink() for p in [path, *path.parents] if p != root and root in p.parents)
            and path.stat().st_nlink == 1, 'missing or unsafe project file: ' + name)
    note_read(path)
    return path


def ref(root, name):
    return {'path': name, 'sha256': hashlib.sha256(file(root, name).read_bytes()).hexdigest()}


def publish_immutable(root, name, payload):
    """Atomically publish complete bytes; concurrent same-byte publishers never rewrite."""
    root=Path(root).resolve()
    require(isinstance(name,str) and name.strip(),'project file path required')
    rel=Path(name)
    require(not rel.is_absolute() and '..' not in rel.parts,'project-relative path required: '+name)
    require(isinstance(payload,(bytes,str)),'immutable publication needs bytes or text')
    payload=payload.encode('utf-8') if isinstance(payload,str) else payload
    target=root/rel;parent=target.parent
    require(parent.resolve().is_relative_to(root) and not any(p.is_symlink() for p in [parent,*parent.parents]
            if p!=root and root in p.parents),'unsafe immutable publication directory')
    parent.mkdir(parents=True,exist_ok=True)
    lock=parent/('.'+target.name+'.publish.lock')
    descriptor=os.open(lock,os.O_CREAT|os.O_RDWR|getattr(os,'O_NOFOLLOW',0),0o600)
    with os.fdopen(descriptor,'r+b') as guard:
        require(os.fstat(guard.fileno()).st_nlink==1,'unsafe immutable publication lock')
        fcntl.flock(guard.fileno(),fcntl.LOCK_EX)
        if target.exists() or target.is_symlink():
            require(file(root,name).read_bytes()==payload,'immutable file differs: '+name)
            return ref(root,name)
        temporary=None
        try:
            with tempfile.NamedTemporaryFile(prefix='.'+target.name+'-',suffix='.publish',dir=parent,delete=False) as stream:
                temporary=Path(stream.name)
                stream.write(payload);stream.flush();os.fsync(stream.fileno())
            # The stable per-destination lock serializes all framework publishers.
            # The target becomes visible only after its complete temporary file exists.
            os.replace(temporary,target)
            temporary=None
        finally:
            if temporary is not None:temporary.unlink(missing_ok=True)
    return ref(root,name)


def verify_ref(root, value):
    require(isinstance(value, dict), 'artifact reference must include path and sha256')
    path = file(root, value.get('path'))
    require(value.get('sha256') == hashlib.sha256(path.read_bytes()).hexdigest(), 'stale artifact: ' + value['path'])
    return path


def references(value):
    if isinstance(value, dict):
        if isinstance(value.get('path'), str) and isinstance(value.get('sha256'), str):
            yield value
        for key, child in value.items():
            if key != 'bundle' and not (key=='tool' and value.get('format')=='direction-tool-receipt/1'):
                yield from references(child)
    elif isinstance(value, list):
        for child in value:
            yield from references(child)


def closure(root, refs):
    """Follow explicit file references, including JSON records and tone-contract blocks."""
    pending, found = list(refs), {}
    while pending:
        value = pending.pop()
        path = verify_ref(root, value)
        name = value['path']
        if name in found:
            require(found[name] == value['sha256'], 'conflicting evidence versions: ' + name)
            continue
        found[name] = value['sha256']
        try:
            source = path.read_text(encoding='utf-8')
            data = json.loads(source) if path.suffix == '.json' else None
            match = re.search(r'^```tone-contract\s*\n(.*?)^```\s*$', source, re.M | re.S)
            if match:
                data = json.loads(match[1])
            if not (isinstance(data,dict) and data.get('format') == 'matrix-evidence-bundle/1'):
                pending.extend(references(data))
        except (UnicodeDecodeError, json.JSONDecodeError):
            pass
    return found


def seal_bundle(root, refs, context, destination=None, *, follow_refs=True, source_roots=None):
    root = Path(root).resolve()
    source_roots=source_roots or {}
    require(not source_roots or not follow_refs, 'alternate immutable sources require explicit members')
    files = closure(root, refs) if follow_refs else {value['path']: ref(source_roots.get(value['path'],root), value['path'])['sha256'] for value in refs}
    if not follow_refs:
        for value in refs:verify_ref(source_roots.get(value['path'],root), value)
    manifest = {'format': 'matrix-evidence-bundle/1', 'context': context,
                'files': [{'logical_path': name, 'sha256': sha} for name, sha in sorted(files.items())]}
    token = digest(manifest)
    destination = destination or 'management/evidence/' + token
    rel = Path(destination)
    require(not rel.is_absolute() and '..' not in rel.parts, 'safe bundle destination required')
    base = root / rel
    require(base.resolve().is_relative_to(root) and not any(p.is_symlink() for p in [base, *base.parents]
            if p != root and root in p.parents), 'unsafe bundle destination')
    manifest_path = (rel / 'manifest.json').as_posix()
    if base.exists():
        existing = ref(root, manifest_path)
        view, checked = verify_bundle(root, existing)
        require(checked == manifest, 'evidence bundle is immutable')
        return existing
    base.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.evidence-',dir=base.parent) as temporary:
        staging=Path(temporary)
        for name,expected in files.items():
            payload=file(source_roots.get(name,root),name).read_bytes()
            require(hashlib.sha256(payload).hexdigest() == expected, 'source changed during evidence sealing: ' + name)
            target=staging/'files'/name
            target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes(payload)
        (staging/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,sort_keys=True,indent=2)+'\n',encoding='utf-8')
        try:
            staging.rename(base)
        except OSError:
            require(base.is_dir(), 'cannot publish immutable evidence bundle')
            existing=ref(root,manifest_path)
            _,checked=verify_bundle(root,existing)
            require(checked == manifest, 'evidence bundle is immutable')
            return existing
    result=ref(root,manifest_path)
    verify_bundle(root,result)
    return result


def verify_bundle(root, value):
    path = verify_ref(root, value)
    manifest = json.loads(path.read_text(encoding='utf-8'))
    require(isinstance(manifest, dict) and manifest.get('format') == 'matrix-evidence-bundle/1' and isinstance(manifest.get('context'), dict)
            and isinstance(manifest.get('files'), list) and manifest['files'], 'evidence bundle manifest required')
    view = path.parent / 'files'
    seen = set()
    for row in manifest['files']:
        require(isinstance(row, dict) and set(row) == {'logical_path', 'sha256'} and row['logical_path'] not in seen,
                'invalid or duplicate evidence bundle member')
        seen.add(row['logical_path'])
        verify_ref(view, {'path': row['logical_path'], 'sha256': row['sha256']})
    actual = {p.relative_to(view).as_posix() for p in view.rglob('*') if p.is_file()}
    require(actual == seen, 'evidence bundle member set changed')
    return view, manifest


def register_stage_receipt(root, bundle):
    """Publish only after the caller has successfully replayed the frozen stage."""
    _, manifest = verify_bundle(root, bundle)
    context = manifest['context']
    require(all(context.get(key) for key in ('role', 'stage', 'state_path')), 'stage receipt context required')
    name = 'management/stage-receipts/' + bundle['sha256'] + '.json'
    body = {'bundle': bundle, 'role': context['role'], 'stage': context['stage'], 'state_path': context['state_path']}
    return publish_immutable(root,name,json.dumps(body,ensure_ascii=False,sort_keys=True))


def stage_receipt(root, bundle):
    """A self-consistent bundle alone is not evidence that its stage ever passed."""
    view, manifest = verify_bundle(root, bundle)
    name = 'management/stage-receipts/' + bundle['sha256'] + '.json'
    stored = json.loads(file(root, name).read_text())
    context = manifest['context']
    require(stored == {'bundle': bundle, 'role': context.get('role'), 'stage': context.get('stage'),
                       'state_path': context.get('state_path')}, 'unregistered or substituted stage evidence')
    return view, manifest


def record_origin(root, record, requirement, scope):
    """Return the successful frozen state that actually carried this exact record ref."""
    _,record_manifest=verify_bundle(root,record.get('bundle'))
    producer=record_manifest['context']
    for path in sorted((Path(root) / 'management/stage-receipts').glob('*.json')):
        receipt = json.loads(file(root, path.relative_to(root).as_posix()).read_text())
        view, manifest = stage_receipt(root, receipt['bundle'])
        state = json.loads(file(view, manifest['context']['state_path']).read_text())
        candidate = state.get('practice_evidence', {}).get(requirement, {}).get(scope)
        if candidate == record and all(manifest['context'].get(key)==producer.get(key) for key in ('role','stage')):
            return view, manifest, state
    raise ValueError('historical evidence is not from a successful registered stage: ' + requirement)


def response_message(root, source, response_id=None):
    """Select a whole stable message; never extract an approval substring."""
    path = file(root, source)
    raw = path.read_text(encoding='utf-8')
    if response_id is None:
        return raw.strip()
    data = json.loads(raw)
    messages = data.get('messages', [])
    selected = [row for row in messages if row.get('id') == response_id]
    require(len(selected) == 1 and isinstance(selected[0].get('text'), str), 'response id must locate one complete message')
    return selected[0]['text'].strip()


def check_review_binding(binding, *, direction_sha256=None, scope=None, person=None, quote=None):
    require(isinstance(binding, dict) and binding.get('format') == 'matrix-review-binding/1'
            and all(binding.get(key) for key in ('request_id', 'scope', 'display', 'response', 'person', 'quote')),
            'displayed request and complete response binding required')
    require(binding.get('outcome') == 'approved', 'explicit human approval required')
    for expected, key in ((direction_sha256, 'direction_sha256'), (person, 'person'), (quote, 'quote')):
        require(expected is None or binding.get(key) == expected, 'review binding differs: ' + key)
    require(scope is None or binding['scope'] == scope, 'review binding scope differs')
    require(binding['response'].get('message_sha256') == digest(binding['quote']), 'complete response message binding changed')
    return binding


def review_receipt(root, binding):
    check_review_binding(binding)
    response = binding['response']
    message = response_message(root, response['path'], response.get('response_id'))
    require(message == binding['quote'].strip(), 'confirmation quote must equal the complete response message')
    require(digest(message) == response['message_sha256'], 'response message changed')
    # Stable message ids disambiguate separate replies with identical wording. With a raw
    # text reply there is no such evidence, so renaming/copying it cannot create new authority.
    identity = {'message': response['message_sha256'], 'id': response.get('response_id')}
    registration = Path(root) / 'management/review-bindings' / (digest(identity) + '.json')
    authority = {key: binding.get(key) for key in ('display', 'scope', 'direction_sha256')}
    if registration.exists():
        require(json.loads(file(root, registration.relative_to(root).as_posix()).read_text()) == authority,
                'the same response is already bound to another display, scope or direction')
    # A failed display/hash check must not consume the person's real reply. The
    # content-addressed bundle is harmless until registration succeeds atomically.
    bundle = seal_bundle(root, [binding['display'], {'path': response['path'], 'sha256': response['sha256']}], binding, follow_refs=False)
    publish_immutable(root, registration.relative_to(root).as_posix(),
                      json.dumps(authority, ensure_ascii=False, sort_keys=True))
    return bundle


def verify_response_registration(root, binding):
    identity = {'message': binding['response']['message_sha256'], 'id': binding['response'].get('response_id')}
    name = 'management/review-bindings/' + digest(identity) + '.json'
    registered = json.loads(file(root, name).read_text())
    require(registered == {key: binding.get(key) for key in ('display', 'scope', 'direction_sha256')},
            'response authority was rebound to another display, scope or direction')
    return binding


@contextlib.contextmanager
def authority_connection(root, authority_db=None):
    database = (Path(root) / 'management/runtime/tasks.sqlite3').resolve()
    if authority_db is not None:
        locations = {Path(row[2]).resolve() for row in authority_db.execute('PRAGMA database_list') if row[1] == 'main' and row[2]}
        require(database in locations, 'authority connection must belong to this project PM database')
        yield authority_db
    else:
        with sqlite3.connect(database.as_uri() + '?mode=ro', uri=True) as db:
            yield db


def verify_human_receipt(root, receipt, *, artifacts=None, direction_sha256=None, authority_db=None):
    """A PM human observation must be a receipt of its actual answered attention record."""
    view, manifest = verify_bundle(root, receipt)
    binding = check_review_binding(manifest['context'], direction_sha256=direction_sha256)
    wanted = {(row['path'], row['sha256']) for row in artifacts or ()}
    shown = {(row['path'], row['sha256']) for row in binding.get('artifacts', ())}
    require(not wanted or wanted <= shown, 'human observation does not cover the current artifacts')
    database = Path(root) / 'management/runtime/tasks.sqlite3'
    if database.is_file():
        with authority_connection(root, authority_db) as db:
            rows = [(kind, json.loads(raw)) for kind, raw in db.execute('SELECT kind,data FROM pm_records')]
            tasks = [json.loads(raw) for (raw,) in db.execute('SELECT data FROM tasks')]
        attention = next((row for kind, row in rows if kind == 'human_attention'
                          and row.get('id') == binding['request_id']), {})
        require(attention.get('seconds') is not None and attention.get('response_message') == binding['quote']
                and attention.get('context', {}).get('scope') == binding['scope'],
                'human receipt must come from the actual answered PM human_attention')
        receipts = list(attention.get('review_receipts', ()))
        receipts += [row.get('confirmation_receipt') for kind, row in rows if kind == 'direction_sample']
        receipts += [(task.get('human_review') or {}).get('review_receipt') for task in tasks]
        require(receipt in receipts, 'human receipt has no trusted PM binding operation')
        _, displayed = verify_bundle(root, attention['display_bundle'])
        _, replied = verify_bundle(root, attention['response_bundle'])
        require(binding['display']['path'] == attention['display']
                and any(row['logical_path'] == binding['display']['path'] and row['sha256'] == binding['display']['sha256']
                        for row in displayed['files'])
                and any(row['logical_path'] == binding['response']['path'] and row['sha256'] == binding['response']['sha256']
                        for row in replied['files']), 'human receipt differs from the real display or response')
    return binding


def png_dimensions(path):
    """Decode PNG chunk checksums and the decompressed scanline structure, without dependencies."""
    raw = path.read_bytes()
    require(raw.startswith(b'\x89PNG\r\n\x1a\n'), 'actual decodable PNG screenshot required')
    offset, chunks, payload, header, ended, palette = 8, [], bytearray(), None, False, None
    while offset < len(raw):
        require(offset + 12 <= len(raw), 'truncated PNG chunk')
        size = int.from_bytes(raw[offset:offset+4], 'big')
        kind, data = raw[offset+4:offset+8], raw[offset+8:offset+8+size]
        require(re.fullmatch(b'[A-Za-z]{4}',kind) and 65 <= kind[2] <= 90, 'invalid PNG chunk type')
        require(offset + size + 12 <= len(raw), 'truncated PNG data')
        crc = int.from_bytes(raw[offset+8+size:offset+12+size], 'big')
        require(zlib.crc32(kind + data) & 0xffffffff == crc, 'PNG checksum mismatch')
        if not chunks:
            require(kind == b'IHDR' and size == 13, 'PNG IHDR required')
            header = struct.unpack('>IIBBBBB', data)
        require(kind != b'IHDR' or not chunks, 'duplicate PNG IHDR')
        require(not 65 <= kind[0] <= 90 or kind in {b'IHDR',b'PLTE',b'IDAT',b'IEND'}, 'unsupported PNG critical chunk')
        if kind == b'PLTE':
            require(palette is None and b'IDAT' not in chunks and 3 <= size <= 768 and size % 3 == 0, 'invalid PNG palette')
            palette = size // 3
        if kind == b'IDAT':
            require(b'IDAT' not in chunks or chunks[-1] == b'IDAT', 'PNG pixel chunks must be consecutive')
            payload.extend(data)
        if kind == b'IEND':
            require(size == 0 and offset + 12 == len(raw), 'invalid PNG ending')
            ended = True
        chunks.append(kind)
        offset += size + 12
    require(header and ended and payload, 'complete PNG screenshot required')
    width, height, depth, color, compression, filtering, interlace = header
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}.get(color)
    allowed = {0: (1,2,4,8,16), 2: (8,16), 3: (1,2,4,8), 4: (8,16), 6: (8,16)}
    require(width and height and width * height <= 100_000_000 and channels and depth in allowed[color]
            and compression == filtering == 0 and interlace in (0,1), 'unsupported or invalid PNG pixels')
    require(color != 3 or palette is not None and palette <= 2**depth, 'indexed PNG requires a valid palette')
    require(color not in (0,4) or palette is None, 'grayscale PNG cannot have a palette')
    decoder = zlib.decompressobj()
    limit = width * height * channels * 2 + height * 8 + 1024
    try:
        pixels = decoder.decompress(bytes(payload), limit + 1)
    except zlib.error as error:
        raise ValueError('invalid PNG pixel stream') from error
    require(decoder.eof and not decoder.unused_data and len(pixels) <= limit, 'invalid PNG pixel stream')
    passes = [(0,0,1,1)] if interlace == 0 else [(0,0,8,8),(4,0,8,8),(0,4,4,8),(2,0,4,4),(0,2,2,4),(1,0,2,2),(0,1,1,2)]
    at = 0
    for x,y,dx,dy in passes:
        w, h = max(0,(width-x+dx-1)//dx), max(0,(height-y+dy-1)//dy)
        if not w or not h:
            continue
        stride = (w * channels * depth + 7)//8
        previous = bytearray(stride)
        for _ in range(h):
            require(at + stride + 1 <= len(pixels) and pixels[at] <= 4, 'invalid PNG scanline')
            if color == 3:
                filtering = pixels[at]
                row = bytearray(pixels[at+1:at+1+stride])
                for index in range(stride):
                    left = row[index-1] if index else 0
                    up = previous[index]
                    corner = previous[index-1] if index else 0
                    if filtering == 1:predictor=left
                    elif filtering == 2:predictor=up
                    elif filtering == 3:predictor=(left+up)//2
                    elif filtering == 4:
                        estimate=left+up-corner
                        distances=[abs(estimate-left),abs(estimate-up),abs(estimate-corner)]
                        predictor=(left,up,corner)[distances.index(min(distances))]
                    else:predictor=0
                    row[index]=(row[index]+predictor)&255
                indices=[(row[(index*depth)//8] >> (8-depth-(index*depth)%8)) & ((1<<depth)-1) for index in range(w)]
                require(all(index < palette for index in indices), 'PNG pixel index is outside its palette')
                previous=row
            at += stride + 1
    require(at == len(pixels), 'PNG decoded size mismatch')
    return width, height


def main():
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project',type=Path,required=True)
    parser.add_argument('--review-binding',required=True,help='project-relative JSON with the actual displayed request and complete human response')
    args=parser.parse_args()
    try:
        binding=json.loads(file(args.project,args.review_binding).read_text(encoding='utf-8'))
        if binding.get('direction_sha256'):
            import importlib.util
            spec=importlib.util.spec_from_file_location('review_direction',Path(__file__).with_name('tone_contract.py'))
            tone=importlib.util.module_from_spec(spec);spec.loader.exec_module(tone)
            draft=binding.get('direction_draft')
            require(isinstance(draft,dict),'direction binding needs direction_draft:{path,sha256} from tool_receipt.contract; correct the binding without changing the actual display or reply')
            verify_ref(args.project,draft)
            data=tone.validate(args.project,draft['path'],confirmed=False,_pending_human=True)
            binding['scope']=tone.check_direction_scope(args.project,data,binding.get('scope'))
            expected=tone.direction_binding(tone.DEFAULT_PATH,data)['direction_sha256']
            require(binding['direction_sha256']==expected,'direction digest differs from the current draft; correct the binding before retrying')
            shown=verify_ref(args.project,binding['display']).read_text(encoding='utf-8')
            require(expected in shown,'display record lacks this direction digest; if it was absent from the actual display, show the draft with its digest and obtain the actual reply; do not backfill an old display')
            binding['response']['message_sha256']=digest(response_message(args.project,binding['response']['path'],binding['response'].get('response_id')))
        result={'allowed':True,'review_receipt':review_receipt(args.project,binding),
                'limitation':'Binds recorded bytes and scope; does not authenticate the human or establish professional quality.'}
    except (ValueError,OSError,KeyError,TypeError,AttributeError) as error:
        print(json.dumps({'allowed':False,'error':str(error)},ensure_ascii=False));return 1
    print(json.dumps(result,ensure_ascii=False));return 0


if __name__=='__main__':
    raise SystemExit(main())
