"""Provide capture-only browser requests to isolated evaluation authors."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import uuid
import struct
import stat
from threading import Event, Thread

from visual_evidence import browser


EVALS = Path(__file__).resolve().parent
ROOTS = {'design', 'product', 'content', 'shared', 'engineering'}
QUEUE = '_evaluation/capture-requests'
IMAGE_MAGIC = b'\x89PNG\r\n\x1a\n'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def project_file(root, value, suffix):
    if not isinstance(value, str):
        raise ValueError('project-relative path required')
    relative = Path(value)
    if (relative.is_absolute() or not relative.parts or relative.parts[0] not in ROOTS
            or '..' in relative.parts or relative.suffix not in suffix):
        raise ValueError('unsafe capture path')
    result = root / relative
    if result.resolve() != result:
        raise ValueError('linked capture path')
    return result


def publish_new_file(root, path, content):
    """Create through directory descriptors so symlink races cannot redirect writes."""
    descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
    try:
        for component in path.relative_to(root).parts[:-1]:
            try:
                os.mkdir(component, dir_fd=descriptor)
            except FileExistsError:
                pass
            following = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = following
        staging = '.capture-' + uuid.uuid4().hex + '.png'
        target = os.open(staging, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=descriptor)
        with os.fdopen(target, 'wb') as image:
            image.write(content)
        try:
            os.link(staging, path.name, src_dir_fd=descriptor, dst_dir_fd=descriptor, follow_symlinks=False)
        finally:
            os.unlink(staging, dir_fd=descriptor)
    finally:
        os.close(descriptor)


def read_project(root, relative):
    descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
    try:
        for component in relative.parts[:-1]:
            following = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = following
        file = os.open(relative.name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=descriptor)
        with os.fdopen(file, 'rb') as stream:
            status = os.fstat(stream.fileno())
            if not stat.S_ISREG(status.st_mode) or status.st_nlink != 1:
                raise ValueError('capture asset must be an unlinked regular file')
            data = stream.read(8 * 1024 * 1024 + 1)
        if len(data) > 8 * 1024 * 1024:
            raise ValueError('capture source is too large')
        return data
    finally:
        os.close(descriptor)


def capture_request(root, request):
    if not isinstance(request, dict) or not {'preview', 'output'} <= set(request) or set(request) - {'preview', 'output', 'state', 'artifacts'}:
        raise ValueError('capture accepts only preview, output, state and artifact paths')
    preview = project_file(root, request['preview'], {'.html', '.svg'})
    output = project_file(root, request['output'], {'.png'})
    if not preview.is_file() or output.exists():
        raise ValueError('capture needs an existing preview and a new PNG output')
    state = request.get('state', 'Current visible viewport after page load')
    artifacts = request.get('artifacts', [request['preview']])
    if not isinstance(state, str) or not state.strip() or not isinstance(artifacts, list) or not artifacts:
        raise ValueError('capture needs a representative state and bound artifact paths')
    bound = []
    for name in dict.fromkeys(artifacts):
        artifact = project_file(root, name, {Path(name).suffix})
        bound.append({'path': name, 'sha256': hashlib.sha256(read_project(root, artifact.relative_to(root))).hexdigest()})
    chrome = browser()
    if not chrome or not shutil.which('node'):
        raise ValueError('local Chrome and Node are required')
    preview_before = hashlib.sha256(read_project(root, preview.relative_to(root))).hexdigest()
    with tempfile.TemporaryDirectory(prefix='matrix-author-capture-') as temporary:
        stage = Path(temporary)
        assets = stage/'assets'
        assets.mkdir()
        for folder in ROOTS:
            for source in (root/folder).rglob('*'):
                if not source.is_file():
                    continue
                relative = source.relative_to(root)
                try:
                    data = read_project(root, relative)
                except OSError:
                    continue
                copied = assets/relative
                copied.parent.mkdir(parents=True, exist_ok=True)
                copied.write_bytes(data)
        command = ['node', str(EVALS/'capture_page.mjs'), str(assets), request['preview'], str(stage/'capture.png'),
                   chrome, str(stage/'profile')]
        result = subprocess.run(command, text=True, capture_output=True, timeout=30)
        if result.returncode:
            raise ValueError('isolated browser capture failed: ' + result.stderr[-500:])
        receipt = json.loads(result.stdout)
        content = (stage/'capture.png').read_bytes()
        if (not content.startswith(IMAGE_MAGIC) or receipt.get('status') != 'captured'
                or receipt.get('viewport') != [1280, 800] or receipt.get('sha256') != hashlib.sha256(content).hexdigest()
                or receipt['source_files'].get(request['preview']) != preview_before):
            raise ValueError('browser receipt does not bind the requested page and PNG')
        for name, digest in receipt['source_files'].items():
            if hashlib.sha256(read_project(root, Path(name))).hexdigest() != digest:
                raise ValueError('source changed during capture: ' + name)
        for artifact in bound:
            if hashlib.sha256(read_project(root, Path(artifact['path']))).hexdigest() != artifact['sha256']:
                raise ValueError('bound artifact changed during capture: ' + artifact['path'])
        binding = {'artifacts': bound, 'pixel_size': [1280, 800], 'viewport': '1280x800', 'scale': 1,
                   'method': 'headless Chrome CDP capture through the evaluation broker', 'state': state,
                   'source': request['output']+'.capture.json'}
        capture_file = project_file(root, request['output']+'.capture.json', {'.json'})
        capture_bytes = (json.dumps(dict(binding, screenshot_sha256=receipt['sha256']), ensure_ascii=False, indent=2)+'\n').encode()
        publish_new_file(root, output, content)
        publish_new_file(root, capture_file, capture_bytes)
        binding['receipt'] = {'path': capture_file.relative_to(root).as_posix(), 'sha256': hashlib.sha256(capture_bytes).hexdigest()}
    return dict(receipt, screenshot=request['output'], preview=request['preview'],
                capture_binding=binding,
                format='author-requested-capture/1', requested_by='author_command',
                captured_at=datetime.datetime.now(datetime.timezone.utc).isoformat())


class CaptureBroker:
    def __init__(self, project, log):
        self.root = Path(project).resolve()
        self.log = Path(log)
        self.queue = self.root / QUEUE
        self.stop = Event()
        self.thread = Thread(target=self.serve, daemon=True)

    def __enter__(self):
        self.queue.mkdir(parents=True, exist_ok=False)
        shutil.copyfile(EVALS/'author_capture.py', self.root/'_evaluation/capture_preview.py')
        self.queue_fd = os.open(self.queue, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        self.thread.start()
        return self

    def __exit__(self, *args):
        self.stop.set()
        self.thread.join(timeout=35)
        os.close(self.queue_fd)

    def serve(self):
        seen = set()
        while not self.stop.wait(0.05):
            if self.queue.resolve() != self.queue:
                return
            for path in self.queue.glob('*.request.json'):
                if self.stop.is_set():
                    break
                identity = path.name.removesuffix('.request.json')
                if identity in seen or not re.fullmatch('[0-9a-f]{32}', identity):
                    continue
                seen.add(identity)
                try:
                    descriptor = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=self.queue_fd)
                    with os.fdopen(descriptor, 'rb') as stream:
                        data = stream.read(4097)
                    if len(data) > 4096:
                        raise ValueError('unsafe capture request')
                    request = json.loads(data)
                    result = capture_request(self.root, request)
                except (OSError, ValueError, subprocess.SubprocessError) as error:
                    result = {'status': 'capture_failed', 'error': str(error)}
                record = dict(result, request_id=identity)
                self.log.parent.mkdir(parents=True, exist_ok=True)
                with self.log.open('a', encoding='utf-8') as stream:
                    stream.write(json.dumps(record, ensure_ascii=False) + '\n')
                temporary = identity + '.result.pending'
                try:
                    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                                         0o600, dir_fd=self.queue_fd)
                    with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
                        stream.write(json.dumps(record, ensure_ascii=False)+'\n')
                    os.rename(temporary, identity+'.result.json', src_dir_fd=self.queue_fd, dst_dir_fd=self.queue_fd)
                except OSError:
                    continue


def preflight(project, evidence):
    """Run the exact author command in the native CLI sandbox without a model."""
    root = Path(project).resolve()
    evidence = Path(evidence)
    evidence.mkdir(parents=True, exist_ok=True)
    sample = root/'design/.capture-preflight.html'
    image = root/'design/.capture-preflight.png'
    sample.parent.mkdir(exist_ok=True)
    sample.write_text('<!doctype html><meta charset="utf-8"><body style="background:#193c45;color:#f7c268">'
                      '<h1>Capture preflight</h1><p>1280 × 800</p></body>')
    try:
        command = ['codex', 'sandbox', '-P', ':workspace', '-C', str(root), '--',
                   os.sys.executable, '_evaluation/capture_preview.py', '--preview',
                   'design/.capture-preflight.html', '--output', 'design/.capture-preflight.png', '--state', 'Capture capability preflight']
        result = subprocess.run(command, cwd=root, text=True, capture_output=True, timeout=60)
        (evidence/'stdout.log').write_text(result.stdout)
        (evidence/'stderr.log').write_text(result.stderr)
        receipt = json.loads(result.stdout) if result.returncode == 0 else None
        if (result.returncode or not image.is_file() or not image.read_bytes().startswith(IMAGE_MAGIC)
                or struct.unpack('>II', image.read_bytes()[16:24]) != (1280, 800)
                or receipt['sha256'] != sha(image)):
            raise ValueError('author-side screenshot capability preflight failed')
        shutil.copyfile(image, evidence/'preview.png')
        metadata = {'argv': command, 'exit_code': result.returncode, 'receipt': receipt,
                    'model_sessions': 0, 'png_dimensions': [1280, 800]}
        (evidence/'preflight.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2)+'\n')
        return metadata
    finally:
        sample.unlink(missing_ok=True)
        image.unlink(missing_ok=True)
        (root/'design/.capture-preflight.png.capture.json').unlink(missing_ok=True)
