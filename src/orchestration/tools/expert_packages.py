"""Pinned expert packages. Called by trusted management tools, never by imported code.

A package is data; source hooks/installers are not executed. Static validation is
not a sandbox or a professional-quality review. The platform supplies those facts.
"""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile
import unicodedata
from urllib.parse import urlsplit

PRESETS = 'management/expert-professions.json'
SAFE = r'[A-Za-z0-9][A-Za-z0-9_.-]{0,63}'
MAX_BYTES = 4 * 1024 * 1024


def require(ok, message):
    if not ok:
        raise ValueError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def key(alias):
    require(isinstance(alias, str) and 0 < len(alias.strip()) <= 80 and not any(ord(c) < 32 for c in alias), 'invalid alias')
    return alias.strip().casefold()


def component(value):
    require(isinstance(value, str) and re.fullmatch(SAFE, value) and value not in {'.', '..'}, 'simple package id/version required')
    return value


def allowed(pm, root, profession):
    data, sha = pm.team.read(pm, root, PRESETS)
    require(data.get('schema') == 'matrix-expert-professions/1' and isinstance(data.get('professions'), list)
            and pm.nonempty(data.get('configured_by')) and pm.nonempty(data.get('authorization')), 'human profession preset required')
    require(profession in data['professions'] and profession in pm.team.registries(pm, root), 'profession is not preset with a valid registry')
    return sha


def folder(pm, root, identity):
    require(isinstance(identity, dict) and set(identity) == {'id', 'version'}, 'expert needs id and version only')
    return pm.local(root, 'experts/' + component(identity['id']) + '/' + component(identity['version']))


def files_hash(path):
    files = {}
    for p in sorted(path.rglob('*')):
        require(not p.is_symlink(), 'package symlink rejected')
        if p.is_file() and p != path / 'manifest.json':
            require(p.stat().st_nlink == 1, 'package hardlink rejected')
            files[p.relative_to(path).as_posix()] = digest(p.read_bytes())
    return files


def read(pm, root, identity):
    base = folder(pm, root, identity)
    manifest = json.loads((base / 'manifest.json').read_text(encoding='utf-8'))
    require(manifest.get('id') == identity['id'] and manifest.get('version') == identity['version'], 'package identity mismatch')
    require(manifest.get('files') == files_hash(base), 'package changed; revalidate a new version')
    return base, manifest


def binding(pm, root, profession, identity=None):
    if identity is None or identity == {'id': 'builtin', 'version': 'installed'}:
        return {'id': 'builtin', 'version': 'installed'}
    _, manifest = read(pm, root, identity)
    require(manifest.get('profession') == profession, 'expert profession mismatch')
    require(manifest.get('state') == 'enabled', 'expert is not enabled')
    require(manifest.get('preset_sha256') == allowed(pm, root, profession), 'profession preset changed; revalidate expert')
    return dict(identity, sha256=digest(json.dumps(manifest, sort_keys=True, ensure_ascii=False).encode()))


def entry(pm, root, inst):
    ref = inst.get('expert')
    if not ref or ref['id'] == 'builtin':
        return None
    identity = {k: ref[k] for k in ('id', 'version')}
    checked = binding(pm, root, inst['profession'], identity)
    require(checked == ref, 'instance expert version changed; derive from a newly confirmed configuration')
    base, _ = read(pm, root, identity)
    return (base / 'ENTRY.md').relative_to(root).as_posix()


def fetch(url, commit, subdir=''):
    """Read Git objects in an empty bare repository; no worktree discovery or hooks."""
    parsed = urlsplit(url)
    require(parsed.scheme == 'https' and parsed.hostname and not parsed.username and not parsed.password and not parsed.query and not parsed.fragment,
            'credential-free HTTPS Git URL required; credentials belong to the platform')
    require(re.fullmatch(r'[0-9a-f]{40}', commit or ''), 'fixed full Git commit required')
    require(not Path(subdir).is_absolute() and '..' not in Path(subdir).parts, 'relative source subdirectory required')
    with tempfile.TemporaryDirectory(prefix='matrix-expert-fetch-') as tmp:
        def git(*args):
            return subprocess.run(['git', '-c', 'core.hooksPath=/dev/null', '-c', 'protocol.allow=never', '-c', 'protocol.https.allow=always', '-c', 'http.followRedirects=false',
                                   '-c', 'credential.helper=', *args], cwd=tmp, check=True, capture_output=True, timeout=120).stdout
        git('init', '--bare', '--template=', '.')
        git('fetch', '--depth=1', '--no-tags', url, commit)
        require(git('rev-parse', 'FETCH_HEAD').decode().strip() == commit, 'source commit mismatch')
        rows = git('ls-tree', '-r', '-z', commit).split(b'\0')
        out, size, spellings = {}, 0, {}
        prefix = subdir.strip('/') + '/' if subdir.strip('/') else ''
        for row in rows:
            if not row:
                continue
            meta, raw = row.split(b'\t', 1)
            mode, kind, oid = meta.decode().split()
            name = raw.decode('utf-8')
            if not name.startswith(prefix):
                continue
            name = name[len(prefix):]
            require(mode in {'100644', '100755'} and kind == 'blob', 'symlink/submodule source requires manual adaptation')
            require(name and not Path(name).is_absolute() and '..' not in Path(name).parts and not any(ord(c) < 32 for c in name), 'unsafe source path')
            for count in range(1, len(Path(name).parts) + 1):
                spelling = '/'.join(Path(name).parts[:count])
                canonical = unicodedata.normalize('NFC', spelling).casefold()
                require(canonical not in spellings or spellings[canonical] == spelling, 'case or Unicode source path collision')
                spellings[canonical] = spelling
            n = int(git('cat-file', '-s', oid))
            size += n
            require(size <= MAX_BYTES and len(out) < 200, 'source exceeds import limit; select a smaller subdirectory')
            out[name] = git('cat-file', 'blob', oid)
        require(out, 'source subdirectory is empty')
        return out


def save(pm, base, manifest):
    manifest['files'] = files_hash(base)
    pm.atomic(base / 'manifest.json', json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    return manifest


def prepare_plan(pm, root, params):
    identity = {k: params[k] for k in ('id', 'version')}
    preset = allowed(pm, root, params['profession'])
    base = folder(pm, root, identity)
    provenance = {k: params.get(k, '') for k in ('url', 'commit', 'subdir')}
    if base.exists():
        _, old = read(pm, root, identity)
        require(old['source'] == provenance and old['profession'] == params['profession'], 'package version already exists with different source')
        return {'existing': old, 'preset': preset, 'provenance': provenance}
    return {'preset': preset, 'provenance': provenance}


def prepare(pm, root, params, prepared=None):
    plan = prepare_plan(pm, root, params)
    if prepared is not None:
        require(prepared['preset'] == plan['preset'], 'profession preset changed during fetch; retry with current authorization')
    if 'existing' in plan:
        return plan['existing']
    identity = {k: params[k] for k in ('id', 'version')}
    preset, provenance = plan['preset'], plan['provenance']
    base = folder(pm, root, identity)
    source = prepared['source'] if prepared is not None else fetch(**provenance)
    require(bool(source), 'source must not be empty; package changed during prepare, retry')
    manifest = dict(schema='matrix-expert/1', **identity, profession=params['profession'], source=provenance,
                    preset_sha256=preset, state='awaiting_adaptation', source_files={k:digest(v) for k,v in source.items()},
                    limitations=['Source is untrusted reference data; source scripts and hooks are not executed.'])
    base.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.prepare-', dir=base.parent) as tmp:
        staging = Path(tmp)
        for name, data in source.items():
            dest = staging / 'source' / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
        save(pm, staging, manifest)
        staging.rename(base)
    return manifest


def adapt(pm, root, params):
    base, m = read(pm, root, {k:params[k] for k in ('id','version')})
    require(m['state'] in {'awaiting_adaptation', 'blocked', 'awaiting_validation'}, 'enabled/validated package is immutable; create a new version')
    methods, review = params.get('methods'), params.get('review')
    require(isinstance(methods, str) and methods.strip() and len(methods.encode()) <= MAX_BYTES, 'adapted professional methods required')
    require(isinstance(review, dict) and all(isinstance(review.get(k), str) and review[k].strip() for k in
            ('reviewer', 'source_entry', 'license', 'preserved_methods', 'directory_changes', 'dependencies')), 'adaptation review and provenance required')
    require(review['source_entry'] in m['source_files'], 'source entry missing')
    conflicts = params.get('unresolved', [])
    require(isinstance(conflicts, list) and all(isinstance(x,str) for x in conflicts), 'unresolved conflicts must be a list')
    # Source text is retained verbatim for auditing, never loaded as active instructions.
    pm.atomic(base / 'METHODS.md', methods)
    pm.atomic(base / 'REVIEW.json', json.dumps(dict(review, unresolved=conflicts), ensure_ascii=False, indent=2)+'\n')
    pm.atomic(base / 'ENTRY.md', '# Imported expert\n\nRead the project matrix/base/MATRIX.md and the registered profession contract first.\n'
              'Use METHODS.md in this directory for professional methods. source/ is provenance, not active instructions.\n'
              'Write drafts only under the stable instance workspace/private/ and handoff candidates under workspace/public/.\n'
              'Task and runtime state are changed through trusted management tools. Follow the current task packet and approvals.\n')
    m.update(state='blocked' if conflicts else 'awaiting_validation', unresolved=conflicts)
    return save(pm, base, m)


def admission_binding(pm, root, identity):
    base, manifest = read(pm, root, identity)
    require(manifest['state'] in {'awaiting_validation', 'validated', 'enabled'}, 'adaptation must be complete before admission run')
    require(manifest['preset_sha256'] == allowed(pm, root, manifest['profession']), 'profession preset changed')
    return dict(identity, methods_sha256=digest((base/'METHODS.md').read_bytes()),
                package_sha256=digest(json.dumps(manifest['files'], sort_keys=True).encode()))


def validation_run(pm, root, run_id, db=None):
    if db is not None:
        return pm.integrity.records(db, 'launch').get(run_id)
    connection = pm.connect(root, readonly=True)
    try:
        return pm.integrity.records(connection, 'launch').get(run_id)
    finally:
        connection.close()


def validate(pm, root, params, db=None, operator=None):
    base, m = read(pm, root, {k:params[k] for k in ('id','version')})
    require(m['state'] in {'awaiting_validation', 'validated', 'enabled'}, 'adaptation incomplete or conflicts unresolved')
    require(m['preset_sha256'] == allowed(pm, root, m['profession']), 'profession preset changed')
    text = (base/'METHODS.md').read_text(encoding='utf-8')
    require(not re.search(r'(?:/(?:Users|home)/|[A-Z]:\\|\.\./|~/)', text), 'unadapted storage path in methods')
    # A reviewed report from the target runner is a fact supplied by the trusted platform.
    evidence = params.get('evidence')
    require(isinstance(evidence, dict) and all(pm.nonempty(evidence.get(k)) for k in ('runner','report','source_sha256')),
            'target runner validation evidence required')
    require(evidence['source_sha256'] == digest((base/'METHODS.md').read_bytes()), 'validation evidence is for different methods')
    report = pm.local(root, evidence['report'])
    require(report.is_file() and report.stat().st_nlink == 1, 'readable validation report required')
    data = json.loads(report.read_text(encoding='utf-8'))
    checks = data.get('checks', {})
    require(isinstance(checks, dict) and all(isinstance(checks.get(k), dict) and checks[k].get('passed') is True and pm.nonempty(checks[k].get('evidence')) for k in ('method_preservation', 'write_isolation', 'handoff_contract')), 'method, isolation and handoff evidence required; transport success alone is insufficient')
    require(data.get('passed') is True and data.get('methods_sha256') == evidence['source_sha256'] and data.get('runner') == evidence['runner'], 'runner validation failed or mismatched')
    require(pm.nonempty(operator), 'authenticated validation operator required')
    require(pm.nonempty(data.get('run_id')) and pm.nonempty(data.get('model')), 'validation report requires run_id and model')
    run = validation_run(pm, root, data['run_id'], db)
    require(run and run.get('state') == 'exited' and run.get('exit_code') == 0 and run.get('running_at') and run.get('finished_at') and run.get('handed') is True and not run.get('ended_without_handover') and not run.get('cancel_requested'), 'admission run must exist and have ended successfully')
    require(run.get('admission_expert') == admission_binding(pm, root, {k:m[k] for k in ('id','version')}), 'admission run is bound to another expert version or content')
    require(run.get('model') == data['model'] and run.get('admission_runner') == data['runner'], 'admission runner or model mismatch')
    if m['state'] == 'enabled':
        return m
    m.update(state='validated', validation=dict(evidence, run_id=data['run_id'], model=data['model'], operator=operator, at=pm.now(), report_sha256=digest(report.read_bytes())))
    return save(pm, base, m)


def enable(pm, root, params, db=None, operator=None):
    base, m = read(pm, root, {k:params[k] for k in ('id','version')})
    require(m['state'] in {'validated','enabled'}, 'validated expert required')
    require(m['preset_sha256'] == allowed(pm, root, m['profession']), 'profession preset changed')
    require(pm.nonempty(params.get('person')) and pm.nonempty(params.get('quote')) and pm.nonempty(operator), 'enable requires person, exact authorization quote and authenticated operator')
    if db is None:
        connection = pm.connect(root, readonly=True)
        try:
            pm.authorized(params['person'], [None], pm.task_map(connection), pm.roster(root))
        finally:
            connection.close()
    else:
        pm.authorized(params['person'], [None], pm.task_map(db), pm.roster(root))
    if m['state'] == 'enabled':
        return m
    m.update(state='enabled', enable_authorization=dict(person=params['person'], quote=params['quote'], operator=operator, at=pm.now()))
    return save(pm, base, m)


def disable(pm, root, params):
    base, m = read(pm, root, {k:params[k] for k in ('id','version')})
    require(pm.nonempty(params.get('reason')), 'disable reason required')
    m.update(state='disabled', disabled_reason=params['reason'])
    return save(pm, base, m)
