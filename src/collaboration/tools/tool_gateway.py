"""Host-side capability gateway. Keep this object, its database and credentials
outside worker access. A shared writable filesystem is NOT an isolation boundary.
Adapters are trusted host code: they must honor connection/resource/operation and
must not expose arbitrary script, URL, credentials or alternate resource arguments.
"""
import hashlib
import json
import os
from pathlib import Path
import secrets
import sqlite3
import time


class Denied(ValueError):
    pass


def require(ok, message):
    if not ok:
        raise Denied(message)


def encoded(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'))


class Gateway:
    """Only call() is worker-facing. All other methods require trusted host access.

    live_check receives instance/task/run/baseline identity and must reject revoked,
    closed, reassigned or stale work. True is required; absence fails closed.
    Adapter errors are uncertain: never retry external writes automatically.
    """
    def __init__(self, database, grants, adapters, live_check):
        self.path = Path(database)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        require(not self.path.is_symlink(), 'unsafe gateway database')
        self.grants = json.loads(encoded(grants))
        self.adapters = dict(adapters)
        self.live_check = live_check
        with self.db() as db:
            db.executescript('''
              CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY, body TEXT NOT NULL, active INTEGER NOT NULL);
              CREATE TABLE IF NOT EXISTS revoked(grant_id TEXT PRIMARY KEY);
              CREATE TABLE IF NOT EXISTS calls(token TEXT, id TEXT, request TEXT, state TEXT, response TEXT,
                grant_id TEXT, lock_key TEXT, PRIMARY KEY(token,id));
            ''')
        os.chmod(self.path, 0o600)

    def db(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        return db

    @staticmethod
    def key(token):
        return hashlib.sha256(token.encode()).hexdigest()

    def open_run(self, instance, task, run, baseline, grant_ids, expires_at):
        require(instance and task and run and baseline and grant_ids, 'explicit execution binding required')
        require(expires_at > time.time(), 'run already expired')
        body = dict(instance=instance, task=task, run=run, baseline=baseline, grants=grant_ids, grant_fingerprints={}, expires_at=expires_at)
        for gid in grant_ids:
            g = self.grants[gid]
            require(type(g.get('revision')) is int and g['revision'] > 0, 'positive authorization revision required')
            body['grant_fingerprints'][gid] = hashlib.sha256(encoded(g).encode()).hexdigest()
            require(g['instance'] == instance and task in g['tasks'], 'grant belongs to another instance/task')
            require(g['expires_at'] >= expires_at, 'run outlives authorization')
        require(self.live_check(body) is True, 'execution not current')
        token = secrets.token_urlsafe(32)
        with self.db() as db:
            db.execute('INSERT INTO sessions VALUES (?,?,1)', (self.key(token), encoded(body)))
        return token  # Delivered only to this worker through its host channel.

    def revoke_run(self, token):
        with self.db() as db:
            db.execute('UPDATE sessions SET active=0 WHERE token=?', (self.key(token),))

    def revoke_grant(self, gid):
        with self.db() as db:
            db.execute('INSERT OR IGNORE INTO revoked VALUES (?)', (gid,))

    def call(self, token, call_id, grant_id, operation, resource, parameters):
        require(isinstance(call_id, str) and call_id and isinstance(parameters, dict), 'call id and object parameters required')
        key = self.key(token)
        request = encoded(dict(grant=grant_id, operation=operation, resource=resource, parameters=parameters))
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM sessions WHERE token=?', (key,)).fetchone()
            require(row and row['active'], 'unknown or revoked execution')
            session = json.loads(row['body'])
            require(session['expires_at'] > time.time() and self.live_check(session) is True, 'expired, stopped or stale execution')
            require(grant_id in session['grants'] and grant_id in self.grants, 'tool grant not assigned to this execution')
            g = self.grants[grant_id]
            require(session.get('grant_fingerprints', {}).get(grant_id) == hashlib.sha256(encoded(g).encode()).hexdigest(), 'authorization changed; open a new run after review')
            require(not db.execute('SELECT 1 FROM revoked WHERE grant_id=?', (grant_id,)).fetchone(), 'tool authorization revoked')
            require(g['expires_at'] > time.time() and g['instance'] == session['instance'] and session['task'] in g['tasks'], 'authorization binding changed')
            require(operation in g['operations'] and resource in g['resources'], 'operation or resource outside grant')
            adapter = self.adapters.get(g['connection'])
            require(adapter is not None, 'authorized connection unavailable; no implicit fallback')
            adapter.validate(operation, resource, parameters)
            old = db.execute('SELECT * FROM calls WHERE token=? AND id=?', (key, call_id)).fetchone()
            if old:
                require(old['request'] == request, 'call id reused with different request')
                require(old['state'] == 'completed', 'call pending or uncertain; reconcile before retry')
                return json.loads(old['response'])
            require(type(g['max_calls']) is int and g['max_calls'] > 0, 'explicit positive tool quota required')
            count = db.execute('SELECT COUNT(*) FROM calls WHERE grant_id=?', (grant_id,)).fetchone()[0]
            require(count < g['max_calls'], 'tool quota exhausted')
            # Host chooses the actual session lock, not the model or the grant author.
            lock_key = adapter.lock_key(resource)
            require(isinstance(lock_key, str) and lock_key, 'adapter must declare a session/resource lock')
            require(not db.execute("SELECT 1 FROM calls WHERE lock_key=? AND state IN ('executing','uncertain')", (lock_key,)).fetchone(), 'tool session/resource busy or uncertain')
            db.execute('INSERT INTO calls VALUES (?,?,?,?,?,?,?)', (key, call_id, request, 'executing', None, grant_id, lock_key))
        try:
            # The adapter has host-owned credentials. No credentials enter model context.
            result = adapter.invoke(operation, resource, json.loads(encoded(parameters)))
            response = encoded(dict(result=result, instance=session['instance'], task=session['task'],
                                    run=session['run'], grant=grant_id, authorization_revision=g['revision'],
                                    operation=operation, resource=resource))
        except BaseException:
            with self.db() as db:
                db.execute("UPDATE calls SET state='uncertain' WHERE token=? AND id=?", (key, call_id))
            raise
        with self.db() as db:
            db.execute("UPDATE calls SET state='completed',response=? WHERE token=? AND id=?", (response, key, call_id))
        return json.loads(response)

    def settle(self, token, call_id, result, evidence):
        """Trusted host reconciles actual outcome after checking remote service.
        Never clears a reservation merely because a timeout elapsed.
        """
        require(isinstance(evidence, str) and evidence.strip(), 'actual reconciliation evidence required')
        with self.db() as db:
            row = db.execute('SELECT state FROM calls WHERE token=? AND id=?', (self.key(token), call_id)).fetchone()
            require(row and row['state'] in {'executing', 'uncertain'}, 'only unsettled operations may be reconciled')
            db.execute("UPDATE calls SET state='completed',response=? WHERE token=? AND id=?",
                       (encoded({'result': result, 'reconciliation_evidence': evidence}), self.key(token), call_id))


class FileArtifactAdapter:
    """Reference adapter for host-owned candidate artifacts, not a general filesystem.
    Workers must not have direct access to the protected root. External adapters use
    the same validate/lock_key/invoke contract and need their own isolation tests.
    """
    def __init__(self, root, resources):
        self.root = Path(root).resolve()
        self.resources = dict(resources)

    def target(self, resource):
        require(resource in self.resources, 'unknown artifact resource')
        ref = Path(self.resources[resource])
        require(not ref.is_absolute() and '..' not in ref.parts and str(ref) not in {'.', ''}, 'unsafe artifact mapping')
        p = self.root / ref
        require(p.resolve().is_relative_to(self.root) and not any(x.is_symlink() for x in [p, *p.parents] if x != self.root and self.root in x.parents), 'artifact path escapes protected root')
        return p

    def validate(self, operation, resource, parameters):
        self.target(resource)
        require(operation in {'read', 'write'}, 'unsupported artifact operation')
        require(set(parameters) == ({'content'} if operation == 'write' else set()), 'unexpected adapter parameters')
        if operation == 'write':
            require(isinstance(parameters['content'], str) and len(parameters['content'].encode()) <= 2_000_000, 'artifact content must be bounded text')

    def lock_key(self, resource):
        return 'artifact:' + str(self.target(resource))

    def invoke(self, operation, resource, parameters):
        self.validate(operation, resource, parameters)
        p = self.target(resource)
        if operation == 'read':
            return {'content': p.read_text()}
        p.parent.mkdir(parents=True, exist_ok=True)
        temporary = p.with_name('.artifact-' + secrets.token_hex(12))
        try:
            temporary.write_text(parameters['content'])
            os.replace(temporary, p)
        finally:
            temporary.unlink(missing_ok=True)
        return {'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}
