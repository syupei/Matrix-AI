"""Take a local browser screenshot for visual evaluations and identify it in blind materials."""

import argparse
from contextlib import contextmanager
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import hashlib
import json
from pathlib import Path
import os
import shutil
import subprocess
import tempfile
from threading import Thread
from urllib.parse import quote

IMAGE_MAGIC = b'\x89PNG\r\n\x1a\n'


def browser():
    configured = os.environ.get('MATRIX_EVAL_BROWSER')
    candidates = [configured, shutil.which('chromium'), shutil.which('google-chrome'),
                  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome']
    return next((value for value in candidates if value and Path(value).is_file()), None)


@contextmanager
def serve_project(root):
    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(root), **kwargs)

        def do_GET(self):
            if not Path(self.translate_path(self.path)).resolve().is_relative_to(root):
                self.send_error(404)
            else:
                super().do_GET()

        def end_headers(self):
            self.send_header('Content-Security-Policy', "default-src 'self' data: blob:; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; frame-src 'none'; connect-src 'self'; form-action 'none'")
            super().end_headers()

        def log_message(self, *_):
            pass

    with ThreadingHTTPServer(('127.0.0.1', 0), Handler) as server:
        worker=Thread(target=server.serve_forever,kwargs={'poll_interval':0.025},daemon=True)
        worker.start()
        try:
            yield server.server_port
        finally:
            server.shutdown()
            worker.join()


def capture(root, html='design/preview.html', viewport=(1280, 800)):
    root = Path(root).resolve()
    relative = Path(html)
    path = (root / relative).resolve()
    if relative.is_absolute() or not path.is_relative_to(root) or path.suffix != '.html':
        raise ValueError('preview must be local HTML inside the evaluation project')
    executable = browser()
    if not executable:
        return {'status':'browser_unavailable'}
    if not path.is_file():
        return {'status':'preview_missing', 'preview':html}
    target = root / 'visual-evidence'
    if target.is_symlink():
        raise ValueError('unsafe screenshot directory')
    target.mkdir(exist_ok=True)
    image = target/'preview.png'
    # Capture separately from the agent and one isolated browser profile per run.
    with tempfile.TemporaryDirectory(prefix='matrix-browser-') as temporary, serve_project(root) as port:
        staged = Path(temporary) / 'preview.png'
        try:
            subprocess.run([executable, '--headless', '--disable-gpu', '--disable-extensions',
                            '--disable-background-networking', '--disable-sync', '--no-first-run',
                            '--proxy-server=http://127.0.0.1:9',
                            '--proxy-bypass-list=127.0.0.1', '--window-size='+','.join(map(str,viewport)),
                            '--user-data-dir='+str(Path(temporary)/'profile'),
                            '--screenshot='+str(staged), 'http://127.0.0.1:'+str(port)+'/'+quote(str(path.relative_to(root)))], capture_output=True, timeout=45, check=True)
        except (OSError, subprocess.SubprocessError) as error:
            return {'status':'capture_failed','error':type(error).__name__,'preview':html}
        if not staged.is_file() or not staged.read_bytes().startswith(IMAGE_MAGIC):
            return {'status':'capture_failed','preview':html}
        if image.exists() or image.is_symlink():
            raise ValueError('capture target must be new')
        shutil.copyfile(staged,image)
    return {'status':'captured','preview':html,'screenshot':'visual-evidence/preview.png',
            'viewport':list(viewport),'sha256':hashlib.sha256(image.read_bytes()).hexdigest()}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--project',type=Path,required=True)
    p.add_argument('--preview',default='design/preview.html')
    args=p.parse_args()
    result=capture(args.project,args.preview)
    target=args.project/'visual-evidence'
    if target.is_symlink():
        raise ValueError('unsafe screenshot directory')
    target.mkdir(exist_ok=True)
    with (target/'capture.json').open('x',encoding='utf-8') as stream:
        json.dump(result,stream,ensure_ascii=False,indent=2)
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':
    main()
