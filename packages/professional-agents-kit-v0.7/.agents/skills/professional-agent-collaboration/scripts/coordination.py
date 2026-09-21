#!/usr/bin/env python3
"""Local request ledger. Host tools, not this script, start/wake agents.

Python 3.9+; JSON command from --input FILE or stdin. No network calls.
Actor labels and human-message evidence are cooperative assertions, not authentication.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import time
import uuid


class CoordinationError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise CoordinationError(message)


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def digest(value):
    return hashlib.sha256(encoded(value).encode()).hexdigest()


def local(root, relative):
    require(isinstance(relative, str) and relative and not Path(relative).is_absolute(), 'use a project-relative path')
    path = (root / relative).resolve()
    require(path == root or root in path.parents, 'path escapes project')
    return path


def leased(request):
    return request.get('lease_active', request['state'] in {'dispatching', 'inflight'})


def same_endpoint(a, b):
    if a is None or b is None:
        return False
    keys = ('kind', 'id') if a.get('kind') == 'thread' else ('kind', 'id', 'session')
    return all(a.get(k) == b.get(k) for k in keys)


def fingerprint(root, relative):
    path = local(root, relative)
    require(path.is_file(), 'missing source file: ' + relative)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def execute(project, command):
    root = Path(project).resolve()
    require(root.is_dir(), 'project does not exist')
    op = command.get('op')
    folder = local(root, 'collaboration/runtime')
    dbpath = local(root, 'collaboration/runtime/state.sqlite3')
    if op == 'init':
        folder.mkdir(parents=True, exist_ok=True)
    require(dbpath.exists() or op == 'init', 'runtime not initialized')
    con = sqlite3.connect(dbpath, timeout=15)
    con.row_factory = sqlite3.Row
    try:
        con.execute('PRAGMA busy_timeout=15000')
        con.execute('BEGIN IMMEDIATE')
        if op == 'init':
            con.execute('CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)')
            con.execute('CREATE TABLE IF NOT EXISTS roles (id TEXT PRIMARY KEY, body TEXT NOT NULL)')
            con.execute('CREATE TABLE IF NOT EXISTS requests (id TEXT PRIMARY KEY, body TEXT NOT NULL)')
            con.execute('CREATE TABLE IF NOT EXISTS events (seq INTEGER PRIMARY KEY AUTOINCREMENT, at REAL NOT NULL, request_id TEXT, kind TEXT NOT NULL, body TEXT NOT NULL)')

        def event(rid, kind, body):
            con.execute('INSERT INTO events(at,request_id,kind,body) VALUES(?,?,?,?)', (time.time(), rid, kind, encoded(body)))

        def role(name):
            row = con.execute('SELECT body FROM roles WHERE id=?', (name,)).fetchone()
            require(row is not None, 'role not registered: ' + str(name))
            return json.loads(row['body'])

        def all_requests():
            return [json.loads(row['body']) for row in con.execute('SELECT body FROM requests ORDER BY rowid')]

        def save(request, kind):
            request['updated_at'] = time.time()
            con.execute('INSERT OR REPLACE INTO requests VALUES(?,?)', (request['id'], encoded(request)))
            event(request['id'], kind, {'state': request['state'], 'round': request['round'], 'actor': command.get('actor')})
            return request

        if op == 'init':
            cfg = command['config']
            require(cfg.get('protocol') == 'professional-collaboration/0.1', 'unsupported professional protocol')
            require(isinstance(cfg.get('authorization'), str) and cfg['authorization'].strip(), 'authorization required')
            require(cfg.get('frontdoor', {}).get('thread_id'), 'real human-facing task id required')
            require(isinstance(cfg.get('max_rounds', 3), int) and 1 <= cfg.get('max_rounds', 3) <= 10, 'max_rounds must be 1..10')
            require(isinstance(cfg.get('max_attempts', 3), int) and 1 <= cfg.get('max_attempts', 3) <= 10, 'max_attempts must be 1..10')
            old = con.execute("SELECT value FROM meta WHERE key='config'").fetchone()
            if old:
                require(json.loads(old['value']) == cfg, 'configuration already exists; do not overwrite live routes')
            else:
                con.execute('INSERT INTO meta VALUES(?,?)', ('config', encoded(cfg)))
                event(None, 'initialized', cfg)
            con.commit()
            return {'initialized': True, 'config': cfg}

        cfg = json.loads(con.execute("SELECT value FROM meta WHERE key='config'").fetchone()['value'])
        actor = command.get('actor')
        if op == 'status':
            result = {'config': cfg, 'roles': [json.loads(x['body']) for x in con.execute('SELECT body FROM roles')], 'requests': all_requests()}
            con.commit()
            return result
        require(actor, 'actor required')
        if op == 'register':
            require(actor == 'coordinator', 'only coordinator registers routes')
            spec = command['role']
            require(spec.get('id') and spec.get('skill'), 'role id and skill required')
            require(local(root, spec['skill']).is_file(), 'role skill missing')
            for prefix in spec.get('write_roots', []):
                require(prefix not in {'', '.', './'}, 'role may not own entire project')
                require(local(root, prefix) != root, 'role may not own entire project')
            endpoint = spec.get('endpoint')
            require(endpoint is None or endpoint.get('kind') in {'subagent', 'thread', 'inline'}, 'invalid endpoint')
            if endpoint is not None:
                require(endpoint.get('id') and endpoint.get('session'), 'actual endpoint id and session required')
            oldrow = con.execute('SELECT body FROM roles WHERE id=?', (spec['id'],)).fetchone()
            if oldrow:
                oldspec = json.loads(oldrow['body'])
                active = [x for x in all_requests() if (x['target'] == spec['id'] or x['source'] == spec['id']) and leased(x)]
                require(not active or oldspec == spec, 'cannot replace an active role endpoint')
            con.execute('INSERT OR REPLACE INTO roles VALUES(?,?)', (spec['id'], encoded(spec)))
            event(None, 'role_registered', spec)
            con.commit()
            return spec

        if op == 'request':
            payload = command['request']
            require(actor == payload.get('source'), 'source must equal actor')
            src, target = role(actor), role(payload.get('target'))
            require(actor != target['id'], 'same-role self-call is not a collaboration request')
            require(payload.get('question') and payload.get('expected_output') and payload.get('authorization'), 'question/output/authorization required')
            require(payload.get('sources'), 'provide actual baseline source paths')
            for prefix in payload.get('write_allowed', []):
                p = local(root, prefix)
                require(any(local(root, owned) == p or local(root, owned) in p.parents for owned in target.get('write_roots', [])), 'requested write scope exceeds target ownership')
            rid = payload.get('id') or 'REQ-' + uuid.uuid4().hex[:12]
            previous = con.execute('SELECT body FROM requests WHERE id=?', (rid,)).fetchone()
            ph = digest(payload)
            if previous:
                result = json.loads(previous['body'])
                require(result['payload_hash'] == ph, 'same request id with different payload')
                con.commit()
                return result
            # Detect pending wait cycles across role boundaries, including nested requests.
            open_states = {'ready', 'dispatching', 'inflight', 'needs_human', 'answered'}
            graph = {}
            for old in all_requests():
                if old['state'] in open_states:
                    graph.setdefault(old['source'], set()).add(old['target'])
            todo, seen = [target['id']], set()
            while todo:
                node = todo.pop()
                require(node != actor, 'cyclic wait: answer existing request or let coordinator resolve')
                if node not in seen:
                    seen.add(node)
                    todo.extend(graph.get(node, []))
            sources = {p: fingerprint(root, p) for p in payload['sources']}
            result = save({'id': rid, 'source': actor, 'target': target['id'], 'payload': payload, 'payload_hash': ph,
                           'sources': sources, 'expected_sources': sources, 'state': 'ready', 'round': 1,
                           'attempts': [], 'responses': [], 'human_answers': [], 'created_at': time.time()}, 'request_created')
            con.commit()
            return result

        row = con.execute('SELECT body FROM requests WHERE id=?', (command.get('id'),)).fetchone()
        require(row is not None, 'unknown request')
        req = json.loads(row['body'])
        require(actor in {'coordinator', req['source'], req['target']}, 'actor not part of request')

        def check_sources(expected):
            for name, sha in expected.items():
                try:
                    if fingerprint(root, name) != sha:
                        return False
                except CoordinationError:
                    return False
            return True

        def check_token():
            require(req.get('attempt') == command.get('attempt'), 'stale or missing dispatch attempt token')

        if op == 'show':
            con.commit()
            return req
        if op == 'packet':
            require(actor == 'coordinator' and req['state'] == 'dispatching', 'claim before constructing dispatch packet')
            result = {'protocol': cfg['protocol'], 'project_root': str(root), 'request': req, 'source_role': role(req['source']), 'target_role': role(req['target']), 'frontdoor': cfg['frontdoor'],
                      'instruction': 'Read the target role skill and collaboration runtime skill. Process only this request; use respond with this attempt token. Do not ask the human directly. Do not assume business facts or expand authorization.'}
            con.commit()
            return result
        if op == 'claim':
            require(actor == 'coordinator' and req['state'] == 'ready', 'only coordinator can claim a ready request')
            require(req['round'] <= cfg.get('max_rounds', 3), 'round limit reached; summarize remaining decision')
            target_spec = role(req['target'])
            endpoint = target_spec.get('endpoint')
            require(not same_endpoint(endpoint, role(req['source']).get('endpoint')), 'cannot dispatch different roles to the same live endpoint')
            roots = [local(root, p) for p in target_spec.get('write_roots', [])]
            for active in all_requests():
                if not leased(active):
                    continue
                other = role(active['target'])
                overlap = any(a == b or a in b.parents or b in a.parents for a in roots for b in [local(root, p) for p in other.get('write_roots', [])])
                require(active['target'] != req['target'] and not same_endpoint(endpoint, other.get('endpoint')) and not overlap, 'active request holds target, endpoint or overlapping write ownership; confirm worker stopped before release')
            if not check_sources(req['expected_sources']):
                req['state'] = 'stale'
                result = save(req, 'input_changed_before_dispatch')
            else:
                endpoint = role(req['target']).get('endpoint')
                require(endpoint is not None, 'bind a real role endpoint before claim; use on-demand bootstrap handshake')
                require(endpoint['kind'] != 'thread' or endpoint['id'] != cfg['frontdoor']['thread_id'], 'cannot send to the current frontdoor task; bind an independent subagent or process inline without self-message')
                require(endpoint['kind'] != 'inline', 'inline roles answer directly; cannot dispatch a self-call')
                req['attempt'] = uuid.uuid4().hex
                req['state'] = 'dispatching'
                req['lease_active'] = True
                req['attempts'].append({'token': req['attempt'], 'round': req['round'], 'endpoint': endpoint, 'at': time.time()})
                result = save(req, 'dispatch_claimed')
        elif op == 'receipt':
            require(actor == 'coordinator', 'only coordinator records delivery')
            check_token()
            require(command.get('evidence'), 'actual host tool result reference required')
            outcome = command.get('outcome')
            require(outcome in {'sent', 'uncertain', 'not_sent'}, 'invalid outcome')
            if req['state'] in {'answered', 'needs_human', 'closed'}:
                event(req['id'], 'late_delivery_receipt', {'outcome': outcome, 'evidence': command['evidence']})
                result = req
            else:
                require(req['state'] in {'dispatching', 'inflight'}, 'request no longer dispatchable')
                require(not (req['state'] == 'inflight' and outcome != 'sent'), 'cannot retract confirmed delivery')
                req['delivery'] = {'outcome': outcome, 'evidence': command['evidence']}
                req['lease_active'] = outcome != 'not_sent'
                req['state'] = {'sent': 'inflight', 'uncertain': 'dispatching', 'not_sent': 'failed'}[outcome]
                result = save(req, 'delivery_' + outcome)
        elif op == 'retry':
            require(actor == 'coordinator' and req['state'] == 'failed', 'only a confirmed not-sent failure can retry automatically')
            require(req.get('delivery', {}).get('outcome') == 'not_sent', 'responded/unavailable requests require new evidence, not transport retry')
            require(len(req['attempts']) < cfg.get('max_attempts', 3), 'delivery retry limit reached')
            req['state'] = 'ready'
            result = save(req, 'retry_prepared')
        elif op == 'respond':
            require(actor == req['target'], 'only target role responds')
            check_token()
            answer = command['response']
            ah = digest(answer)
            old = [x for x in req['responses'] if x['attempt'] == req['attempt']]
            if old:
                require(old[-1]['hash'] == ah, 'conflicting duplicate response')
                con.commit()
                return req
            require(req['state'] in {'dispatching', 'inflight'}, 'request cancelled, stale or not running')
            require(answer.get('kind') in {'explanation', 'decision', 'needs_human', 'unavailable'}, 'invalid response kind; proposals needing approval use needs_human')
            require(answer.get('summary') and answer.get('evidence'), 'response must include conclusion and evidence/limits')
            expected = dict(req['expected_sources'])
            owned = role(actor).get('write_roots', [])
            for path, after_sha in answer.get('updated_sources', {}).items():
                require(path in expected, 'updated source must be part of request baseline')
                p = local(root, path)
                require(any(local(root, prefix) == p or local(root, prefix) in p.parents for prefix in owned), 'target cannot claim edits to another role source')
                require(any(local(root, prefix) == p or local(root, prefix) in p.parents for prefix in req['payload'].get('write_allowed', [])), 'source change outside this request write scope')
                require(answer.get('change_authorization'), 'upstream source change requires authority reference')
                require(fingerprint(root, path) == after_sha, 'declared updated hash does not match source')
                expected[path] = after_sha
            record = {'attempt': req['attempt'], 'round': req['round'], 'hash': ah, 'answer': answer, 'at': time.time()}
            req['responses'].append(record)
            req['lease_active'] = False
            req['expected_sources'] = expected
            if not check_sources(expected):
                req['state'] = 'stale'
            elif answer['kind'] == 'needs_human':
                question = answer.get('question', {})
                require(question.get('prompt') and question.get('why') and question.get('scope'), 'human question needs prompt, why and scope')
                req['question'] = question
                req['question_hash'] = digest({'request': req['id'], 'round': req['round'], 'question': question, 'sources': expected})
                req.pop('presented', None)
                req['state'] = 'needs_human'
            elif answer['kind'] == 'unavailable':
                req['state'] = 'failed'
                req['delivery'] = {'outcome': 'responded_unavailable'}
            else:
                if answer['kind'] == 'decision':
                    require(answer.get('decision_authorization'), 'professional decision needs existing delegated authority')
                req['state'] = 'answered'
            result = save(req, 'response_recorded')
        elif op == 'presented':
            require(actor == 'coordinator' and req['state'] == 'needs_human', 'only frontdoor presents human questions')
            require(command.get('question_hash') == req['question_hash'], 'question changed')
            require(command.get('evidence'), 'actual conversation display evidence required')
            if req.get('presented'):
                con.commit()
                return req
            req['presented'] = {'hash': req['question_hash'], 'evidence': command['evidence'], 'at': time.time()}
            result = save(req, 'human_question_presented')
        elif op == 'human_answer':
            require(actor == 'coordinator' and req['state'] == 'needs_human', 'only coordinator records a real human response')
            require(req.get('presented') and command.get('question_hash') == req['question_hash'], 'must answer the actually presented question revision')
            ev = command.get('evidence', {})
            require(ev.get('kind') == 'user_message' and ev.get('thread_id') == cfg['frontdoor']['thread_id'] and ev.get('quote'), 'real frontdoor user-message evidence required; no timeout/default/agent consent')
            require(command.get('answer'), 'human answer missing')
            if not check_sources(req['expected_sources']):
                req['state'] = 'stale'
                result = save(req, 'input_changed_before_human_answer')
            else:
                req['human_answers'].append({'question_hash': req['question_hash'], 'question': req['question'], 'answer': command['answer'], 'evidence': ev})
                req['round'] += 1
                req['state'] = 'ready' if req['round'] <= cfg.get('max_rounds', 3) else 'failed'
                result = save(req, 'human_answer_recorded_for_owner')
        elif op == 'accept':
            require(actor == req['source'] and req['state'] == 'answered', 'only requesting role accepts an answered request')
            require(command.get('result'), 'record actual adoption/result before closing')
            if check_sources(req['expected_sources']):
                req['state'] = 'closed'
                req['adoption'] = command['result']
            else:
                req['state'] = 'stale'
            result = save(req, 'request_processed')
        elif op == 'settle_cancel':
            require(actor == 'coordinator' and req['state'] == 'cancelled', 'only coordinator settles a cancelled worker')
            check_token()
            require(command.get('evidence') and command.get('outcome') in {'stopped', 'completed', 'not_sent'}, 'actual host stop/completion/non-delivery proof required')
            require(not (req.get('delivery', {}).get('outcome') == 'sent' and command['outcome'] == 'not_sent'), 'cannot retract confirmed delivery; obtain stop/completion evidence')
            req['lease_active'] = False
            req['stop_receipt'] = {'outcome': command['outcome'], 'evidence': command['evidence']}
            result = save(req, 'cancelled_worker_settled')
        elif op == 'cancel':
            require(actor in {'coordinator', req['source']}, 'target cannot cancel requester work')
            require(req['state'] != 'closed', 'closed request is immutable; create a new revision')
            require(command.get('reason'), 'cancel reason required')
            req['lease_active'] = leased(req)
            req['state'] = 'cancelled'
            req['cancel_reason'] = command['reason']
            result = save(req, 'cancelled')
        else:
            raise CoordinationError('unknown operation: ' + str(op))
        con.commit()
        return result
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', required=True)
    parser.add_argument('--input', help='JSON command file; otherwise read stdin')
    args = parser.parse_args()
    try:
        command = json.loads(Path(args.input).read_text() if args.input else sys.stdin.read())
        print(json.dumps(execute(args.project, command), ensure_ascii=False, indent=2))
    except (CoordinationError, KeyError, ValueError, OSError, sqlite3.Error) as exc:
        print(json.dumps({'error': str(exc)}, ensure_ascii=False))
        sys.exit(1)


if __name__ == '__main__':
    main()
