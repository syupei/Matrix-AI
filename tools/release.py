#!/usr/bin/env python3
"""Build verified packages and synchronously publish immutable version assets."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
REPO = 'syupei/Matrix-AI'
CATALOG = ROOT / 'releases.json'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def command(args, *, cwd=None, check=True):
    result = subprocess.run(args, cwd=ROOT if cwd is None else cwd, text=True, capture_output=True)
    if check and result.returncode:
        raise RuntimeError(f'{args[0]} failed: {result.stderr.strip() or result.stdout.strip()}')
    return result


def safe_path(base, name):
    rel = Path(name)
    if rel.is_absolute() or '..' in rel.parts or not name:
        raise ValueError('Unsafe package path: ' + name)
    path = base / rel
    if not path.resolve().is_relative_to(base.resolve()):
        raise ValueError('Path leaves package: ' + name)
    for node in [path, *path.parents]:
        if node.is_symlink():
            raise ValueError('Symlink in package path: ' + name)
        if node == base:
            break
    if any(p in rel.parts for p in ['.git', 'memory', '__pycache__']) or rel.name in ['MEMORY.md', '.env', '.DS_Store']:
        raise ValueError('Private/cache file in package: ' + name)
    return path


def package_files(source):
    source = Path(source).resolve()
    if (source / 'MANIFEST.json').is_file():
        manifest = 'MANIFEST.json'
        data = json.loads((source / manifest).read_text())
        expected = data.get('files', data)
    elif (source / 'MANIFEST.sha256').is_file():
        manifest = 'MANIFEST.sha256'
        expected = {}
        for line in (source / manifest).read_text().splitlines():
            if line.strip():
                digest, name = line.split(maxsplit=1)
                expected[name.lstrip('*')] = digest
    else:
        raise ValueError('A verified file manifest is required')
    expected = dict(expected)
    for name, digest in expected.items():
        if not isinstance(digest, str) or not re.fullmatch('[0-9a-f]{64}', digest):
            raise ValueError('Invalid digest: ' + name)
        path = safe_path(source, name)
        if not path.is_file() or sha(path) != digest:
            raise ValueError('Manifest mismatch: ' + name)
    expected[manifest] = sha(source / manifest)
    if len(expected) != len({name.casefold() for name in expected}):
        raise ValueError('Case-insensitive path collision')
    return expected


def verify_archive(archive, name, expected):
    with zipfile.ZipFile(archive) as z:
        if z.testzip() is not None:
            raise ValueError('Corrupt ZIP')
        actual = {}
        for item in z.infolist():
            if item.is_dir():
                continue
            prefix = name + '/'
            if not item.filename.startswith(prefix):
                raise ValueError('Unexpected ZIP root: ' + item.filename)
            rel = item.filename[len(prefix):]
            if rel in actual or Path(rel).is_absolute() or '..' in Path(rel).parts:
                raise ValueError('Unsafe or duplicate ZIP member')
            actual[rel] = hashlib.sha256(z.read(item)).hexdigest()
        if actual != expected:
            raise ValueError('ZIP content differs from verified source')


def build_archive(source, archive):
    source, archive = Path(source).resolve(), Path(archive).resolve()
    expected = package_files(source)
    archive.parent.mkdir(parents=True, exist_ok=True)
    if not archive.exists():
        with tempfile.TemporaryDirectory(dir=archive.parent) as tmp:
            candidate = Path(tmp) / 'package.zip'
            with zipfile.ZipFile(candidate, 'w', zipfile.ZIP_DEFLATED) as z:
                for rel in sorted(expected):
                    info = zipfile.ZipInfo(source.name + '/' + rel, (2026, 1, 1, 0, 0, 0))
                    info.compress_type = zipfile.ZIP_DEFLATED
                    info.external_attr = 0o100644 << 16
                    z.writestr(info, (source / rel).read_bytes())
            verify_archive(candidate, source.name, expected)
            os.replace(candidate, archive)
    verify_archive(archive, source.name, expected)
    return expected


def copy_snapshot(source, destination, expected):
    if destination.exists():
        actual = {str(p.relative_to(destination)): sha(p) for p in destination.rglob('*') if p.is_file() and '__pycache__' not in p.parts}
        if actual != expected:
            raise ValueError('Existing published snapshot differs; use a new version')
        return
    for rel in expected:
        target = destination / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source / rel, target)


def api(endpoint):
    result = command(['gh', 'api', endpoint], check=False)
    if result.returncode:
        if 'HTTP 404' in result.stderr:
            return None
        raise RuntimeError(result.stderr)
    return json.loads(result.stdout)


def release_info(tag):
    found = api(f'repos/{REPO}/releases/tags/{tag}')
    if found is not None:
        return found
    # GitHub's tag endpoint omits drafts; find a partially uploaded release
    # before attempting creation so an interrupted publish is resumable.
    page = 1
    while True:
        releases = api(f'repos/{REPO}/releases?per_page=100&page={page}')
        for item in releases:
            if item['tag_name'] == tag:
                return item
        if len(releases) < 100:
            return None
        page += 1


def publish(entry, asset_dir):
    asset_dir = Path(asset_dir).resolve()
    tag = entry['tag']
    assets = entry['assets']
    for asset in assets:
        local = Path(asset_dir) / asset['name']
        if not local.is_file() or sha(local) != asset['sha256']:
            raise ValueError('Local release asset changed: ' + asset['name'])
    remote = release_info(tag)
    if remote is None:
        command(['gh', 'release', 'create', tag, '--repo', REPO, '--verify-tag', '--draft', '--title', entry['title'], '--notes-file', str(ROOT / entry['notes'])])
        remote = release_info(tag)
    if remote is None:
        raise RuntimeError('Created release is not yet visible; retry the same command')
    by_name = {a['name']: a for a in remote['assets']}
    for asset in assets:
        local = Path(asset_dir) / asset['name']
        existing = by_name.get(asset['name'])
        if existing:
            if existing['size'] != local.stat().st_size:
                raise ValueError('Remote asset differs: ' + asset['name'])
            digest = existing.get('digest')
            if digest:
                if digest != 'sha256:' + asset['sha256']:
                    raise ValueError('Remote asset digest differs: ' + asset['name'])
            else:
                with tempfile.TemporaryDirectory() as tmp:
                    command(['gh', 'release', 'download', tag, '--repo', REPO, '--pattern', asset['name'], '--dir', tmp])
                    if sha(Path(tmp) / asset['name']) != asset['sha256']:
                        raise ValueError('Remote download differs: ' + asset['name'])
        else:
            command(['gh', 'release', 'upload', tag, str(local), '--repo', REPO])
    remote = api(f"repos/{REPO}/releases/{remote['id']}")
    for asset in assets:
        match = next(a for a in remote['assets'] if a['name'] == asset['name'])
        if match['size'] != (Path(asset_dir) / asset['name']).stat().st_size or (match.get('digest') and match['digest'] != 'sha256:' + asset['sha256']):
            raise ValueError('Uploaded asset verification failed')
    if remote['draft']:
        command(['gh', 'release', 'edit', tag, '--repo', REPO, '--draft=false', '--latest=' + str(bool(entry.get('latest'))).lower()])
        remote = api(f"repos/{REPO}/releases/{remote['id']}")
        if remote['draft']:
            raise RuntimeError('Release remains draft; retry the same command')
    print('PUBLISHED ' + remote['html_url'], flush=True)


def git(*args, check=True):
    return command(['git', *args], check=check)


def pending_paths():
    # NUL records preserve Unicode, spaces, quotes and newlines without Git's
    # human-readable quoting. Renames/copies include a second source path.
    records = iter(git('status', '--porcelain', '-z', '--untracked-files=all').stdout.split('\0'))
    paths = []
    for record in records:
        if not record:
            continue
        paths.append(record[3:])
        if 'R' in record[:2] or 'C' in record[:2]:
            source = next(records, '')
            if not source:
                raise ValueError('Incomplete Git rename/copy status')
            paths.append(source)
    return paths


def build_and_publish(source, notes, latest=False):
    source = Path(source).resolve()
    if not re.fullmatch(r'[a-z0-9-]+-v\d+(?:\.\d+)+', source.name):
        raise ValueError('Package directory must have a versioned name')
    if not notes.is_file():
        raise ValueError('Release notes are required')
    catalog = json.loads(CATALOG.read_text())
    entry = next((e for e in catalog['releases'] if e['tag'] == source.name), None)
    archive = source.with_name(source.name + '.zip')
    expected = build_archive(source, archive)
    # Validate executable package checks before publishing a new version.
    if entry is None:
        tests = source / 'tests'
        if tests.is_dir():
            command([sys.executable, '-m', 'unittest', 'discover', '-s', str(tests), '-q'], cwd=source)
    remote = git('remote', 'get-url', 'origin').stdout.strip()
    if remote not in [f'https://github.com/{REPO}.git', f'https://github.com/{REPO}', f'git@github.com:{REPO}.git']:
        raise ValueError('Unexpected publishing remote')
    if entry:
        if entry['assets'][0]['sha256'] != sha(archive):
            raise ValueError('Published version cannot be replaced; use a new version')
    else:
        if git('status', '--porcelain').stdout.strip():
            raise ValueError('Publishing checkout must be clean before importing a new version')
        copy_snapshot(source, ROOT / 'packages' / source.name, expected)
        note_path = ROOT / 'release-notes' / (source.name + '.md')
        note_path.parent.mkdir(exist_ok=True)
        note_path.write_text(notes.read_text())
        entry = {'tag': source.name, 'title': source.name, 'source': 'packages/' + source.name, 'notes': str(note_path.relative_to(ROOT)), 'latest': latest, 'archive_origin': 'build', 'assets': [{'name': archive.name, 'sha256': sha(archive), 'bytes': archive.stat().st_size}]}
        if latest:
            for item in catalog['releases']:
                item['latest'] = False
            catalog['latest'] = source.name
            readme = ROOT / 'README.md'
            text = readme.read_text()
            text = re.sub(r'目前推荐 \*\*[^\n]+', f'目前推荐 **{source.name}**，使用说明见 [START](packages/{source.name}/START.md)。安装不等于启动 Agent 或批准业务成果；具体能力、限制及实际验证以各版说明为准。', text, count=1)
            readme.write_text(text)
        catalog['releases'].append(entry)
        CATALOG.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + '\n')
        checksum = ROOT / 'SHA256SUMS'
        checksum.write_text(''.join(f"{a['sha256']}  {a['name']}\n" for e in catalog['releases'] for a in e['assets']))
    copy_snapshot(source, ROOT / entry['source'], expected)
    allowed = [entry['source'], entry['notes'], 'releases.json', 'SHA256SUMS', 'README.md']
    pending = pending_paths()
    if any(not any(path == p or path.startswith(p + '/') for p in allowed) for path in pending):
        raise ValueError('Unrelated changes in publishing checkout; leave them uncommitted')
    if pending:
        git('add', '--', *allowed)
        if git('diff', '--cached', '--quiet', check=False).returncode:
            git('commit', '-m', 'Release ' + source.name)
    if git('show-ref', '--verify', '--quiet', 'refs/tags/' + source.name, check=False).returncode:
        git('tag', source.name)
    # A failed upload remains retryable; never report a local ZIP as remote success.
    git('push', 'origin', 'HEAD:main')
    git('push', 'origin', 'refs/tags/' + source.name)
    publish(entry, archive.parent)


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest='action', required=True)
    build = sub.add_parser('build')
    build.add_argument('source', type=Path)
    build.add_argument('--notes', required=True, type=Path)
    build.add_argument('--latest', action='store_true')
    sync = sub.add_parser('sync')
    sync.add_argument('--assets', required=True, type=Path)
    sync.add_argument('--tag')
    sub.add_parser('verify')
    args = parser.parse_args()
    if args.action == 'build':
        build_and_publish(args.source, args.notes, args.latest)
    elif args.action == 'sync':
        for entry in json.loads(CATALOG.read_text())['releases']:
            if args.tag is None or args.tag == entry['tag']:
                publish(entry, args.assets)
    else:
        for entry in json.loads(CATALOG.read_text())['releases']:
            package_files(ROOT / entry['source'])
        print('All released source manifests verified')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, RuntimeError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
