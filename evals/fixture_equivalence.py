#!/usr/bin/env python3
"""Whether a changed fixture still builds the same project for one kit (for carrying an earlier run of that kit).

A fixture file can change for reasons that do not reach a given kit, for example when it picks a field name by the
kit under test. A run made with the earlier fixture may then be carried only if both fixture versions build the same
project for that kit. This builds the project twice in fresh folders, once with each fixture version, and compares
every file outside the kit after normalizing what differs between any two builds: the build folder's own path and
clock times. Task libraries (SQLite) are compared by their dumped content.

  fixture_equivalence.py --kit KIT --cases a,b --out FILE [--repo REPO]

The earlier fixture of each case is the version whose SHA-256 the kit's earlier run recorded; it is taken from the
repository history (all of evals/fixtures/ at that commit, so the modules it imports match it). Writes one result per
case: {case, fixture, old_sha256, new_sha256, old_digest, new_digest, equal}. Exits 1 if any case differs."""
import argparse, hashlib, importlib.util, json, re, shutil, sqlite3, subprocess, sys, tempfile
from pathlib import Path

EVALS = Path(__file__).resolve().parent
CLOCK = re.compile(r'\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:?\d{2})?')


def normalize(text, work):
    for form in {str(work), str(work.resolve())}:
        text = text.replace(form, '<build>')
    return CLOCK.sub('<time>', text)


def digest(work):
    """One hash over every project file outside the kit, normalized."""
    h = hashlib.sha256()
    for p in sorted(x for x in work.rglob('*') if x.is_file() and 'kit' not in x.relative_to(work).parts[:1] and '__pycache__' not in x.parts):
        rel = str(p.relative_to(work))
        if p.suffix in {'.sqlite3', '.db'}:
            con = sqlite3.connect(p)
            body = '\n'.join(con.iterdump())
            con.close()
        else:
            raw = p.read_bytes()
            try:
                body = raw.decode('utf-8')
            except UnicodeDecodeError:
                body = raw.hex()
        h.update(rel.encode() + b'\0' + normalize(body, work).encode() + b'\0')
    return h.hexdigest()


def build(kit, fixture_file, case_id):
    with tempfile.TemporaryDirectory(prefix='matrix-fixture-') as d:
        work = Path(d)
        shutil.copytree(kit, work / 'kit', ignore=shutil.ignore_patterns('__pycache__'))
        spec = importlib.util.spec_from_file_location('fixture_under_check', fixture_file)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.populate(work.resolve(), case_id)
        return digest(work)


def old_fixtures(repo, name, sha, into):
    """The repository's evals/ and src/ at the newest commit whose fixture <name> has this SHA-256, extracted under
    into (an earlier fixture may load modules or tools by paths relative to itself); returns the fixture file."""
    commits = subprocess.run(['git', '-C', str(repo), 'rev-list', 'HEAD', '--', 'evals/fixtures/' + name], capture_output=True, text=True, check=True).stdout.split()
    for c in commits + [c + '^' for c in commits]:
        blob = subprocess.run(['git', '-C', str(repo), 'show', f'{c}:evals/fixtures/{name}'], capture_output=True)
        if blob.returncode == 0 and hashlib.sha256(blob.stdout).hexdigest() == sha:
            archive = subprocess.run(['git', '-C', str(repo), 'archive', c, 'evals', 'src'], capture_output=True, check=True).stdout
            subprocess.run(['tar', '-x', '-C', str(into)], input=archive, check=True)
            return into / 'evals/fixtures' / name
    raise SystemExit(f'no commit has {name} with SHA-256 {sha}')


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--kit', type=Path, required=True); p.add_argument('--cases', required=True); p.add_argument('--out', type=Path, required=True)
    p.add_argument('--run', type=Path, required=True, help="the kit's earlier run.json, whose fixture hashes name the earlier versions")
    p.add_argument('--repo', type=Path, default=EVALS.parent)
    a = p.parse_args()
    suite = {c['id']: c for c in json.loads((EVALS / 'cases/suite.json').read_text(encoding='utf-8'))['cases']}
    earlier = {r['id']: r for r in json.loads(a.run.read_text(encoding='utf-8'))['cases']}
    results = []
    for cid in a.cases.split(','):
        case, record = suite[cid], earlier[cid]
        name = case['fixture'] + '.py'
        new_file = EVALS / 'fixtures' / name
        new_sha = hashlib.sha256(new_file.read_bytes()).hexdigest()
        with tempfile.TemporaryDirectory(prefix='matrix-old-fixtures-') as d:
            old_file = old_fixtures(a.repo, name, record['fixture_sha256'], Path(d))
            old_digest = build(a.kit.resolve(), old_file, cid)
        new_digest = build(a.kit.resolve(), new_file, cid)
        results.append({'case': cid, 'fixture': case['fixture'], 'old_sha256': record['fixture_sha256'], 'new_sha256': new_sha,
                        'old_digest': old_digest, 'new_digest': new_digest, 'equal': old_digest == new_digest})
        print(cid, 'same' if old_digest == new_digest else 'DIFFERENT', flush=True)
    a.out.write_text(json.dumps(results, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    return 0 if all(r['equal'] for r in results) else 1


if __name__ == '__main__':
    raise SystemExit(main())
