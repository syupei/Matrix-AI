#!/usr/bin/env python3
"""Versioned JSON facade. Invoke from a trusted controller with an authenticated principal.

The principal is a transport argument, never a request field. Operating-system
isolation must prevent workers from invoking this controller or changing its config.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import sqlite3
import subprocess
import threading

TOOLS = Path(__file__).resolve().parent
SPEC = 'matrix-platform/1'
CONFIG = 'management/runtime/platform-access.json'
READS = {'capabilities', 'inspect', 'validate', 'tasks.query', 'actions.plan', 'runs.query', 'scripts.inspect'}
WRITES = {'tasks.command', 'actions.claim', 'runs.event', 'runs.cancel', 'runtime.configure', 'scripts.request',
          'expert.prepare', 'expert.adapt', 'expert.validate', 'expert.enable', 'expert.disable'}
OPERATIONS = READS | WRITES
# The host SQLite build can fail with SQLITE_IOERR_LOCK/EBADF when this
# process opens/closes read-only connections during a concurrent write.
# Serialize facade transactions, not model processes; SQLite still arbitrates
# separate controller processes. Keep one imported facade per controller.
TRANSACTIONS = threading.RLock()


def load(name):
    spec = importlib.util.spec_from_file_location('facade_' + name, TOOLS / (name + '.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


pm = load('pm_tasks')
contract = load('platform_contract')


class ProtocolError(ValueError):
    def __init__(self, code, message, retryable=False):
        super().__init__(message)
        self.code, self.retryable = code, retryable


def need(ok, code, message, retryable=False):
    if not ok:
        raise ProtocolError(code, message, retryable)


def access(root, principal):
    data = json.loads(pm.local(root, CONFIG).read_text(encoding='utf-8'))
    need(data.get('schema') == SPEC, 'INVALID_CONFIG', 'platform access schema mismatch')
    who = data.get('principals', {}).get(principal)
    need(isinstance(who, dict) and who.get('active') is True and pm.nonempty(who.get('actor')), 'UNAUTHORIZED', 'principal is not active')
    return data, who


def owner(db):
    return pm.integrity.records(db, 'runtime_owner').get('project', {'id':'project', 'mode':'local', 'generation':0})


def revision(db):
    return db.execute('SELECT COALESCE(MAX(seq),0) FROM events').fetchone()[0]


def capabilities(cfg):
    names = ('launch','cancel','scripts','timers','write_isolation','session_resume','usage','model_selection')
    out = {}
    for rid, r in cfg.get('runners', {}).items():
        caps = {}
        for name in names:
            item = r.get('capabilities', {}).get(name, {})
            state = item.get('state', 'unknown')
            need(state in {'supported','unsupported','unknown'}, 'INVALID_CONFIG', 'invalid capability state')
            need(state != 'supported' or pm.nonempty(item.get('evidence')), 'INVALID_CONFIG', 'supported capability requires evidence')
            caps[name] = dict(state=state, evidence=item.get('evidence'))
        out[rid] = {'version':r.get('version'), 'capabilities':caps, 'models':r.get('models', {})}
    return {'protocol':SPEC, 'operations':sorted(OPERATIONS), 'runners':out}


def plan(root, db):
    data = pm.execute(root, {'op':'continue','detail':True}, _db=db)
    actions = []
    for a in data['actions']:
        if a.get('by') != 'scheduler':
            continue
        raw = json.dumps(a, sort_keys=True, ensure_ascii=False)
        actions.append(dict(a, action_id=hashlib.sha256(raw.encode()).hexdigest()[:24]))
    return dict(revision=revision(db), owner=owner(db), actions=actions, attention=[a for a in data['actions'] if a.get('by') != 'scheduler'], stop=data['stop'])


def runner(cfg, inst):
    rid = inst.get('runner','default')
    r = cfg.get('runners', {}).get(rid)
    need(isinstance(r, dict), 'UNSUPPORTED', 'instance runner is not configured')
    caps = capabilities(cfg)['runners'][rid]['capabilities']
    need(all(caps[x]['state'] == 'supported' for x in ('launch','write_isolation','model_selection')), 'UNSUPPORTED', 'automatic execution requires launch, model selection and enforced write isolation')
    need(inst['model'] in r.get('models', {}), 'UNSUPPORTED', 'configured model has no runner mapping')
    return rid, r


def command(root, db, who, request, params):
    cmd = dict(params)
    need('actor' not in cmd and 'event_id' not in cmd, 'INVALID_REQUEST', 'actor/event_id are supplied by the trusted transport')
    need(cmd.get('op') in who.get('task_ops', []), 'UNAUTHORIZED', 'task operation is outside principal scope')
    cmd.update(actor=who['actor'], event_id=request['event_id'])
    return pm.execute(root, cmd, _db=db)


def claim(root, db, cfg, who, request, p):
    own = owner(db)
    need(own['mode'] in {'local','external'} and own.get('principal') == request['_principal'], 'OWNER_MISMATCH', 'configured runtime owner required')
    current = plan(root, db)
    need(p.get('expected_revision') == current['revision'], 'STALE_REVISION', 'reload action plan', True)
    a = next((a for a in current['actions'] if a['action_id'] == p.get('action_id')), None)
    need(a is not None, 'NOT_READY', 'action is no longer ready')
    inst = pm.integrity.records(db,'instance')[a['instance']]
    expert = pm.team.experts.entry(pm.api(), root, inst)  # verifies package immutability and preset
    rid, r = runner(cfg, inst)
    ids = a.get('tasks') or [a['task']]
    run = 'run-' + hashlib.sha256((request['project_id'] + ':' + request['event_id']).encode()).hexdigest()[:24]
    data = dict(op='launch_start', actor=pm.platform.SCHEDULER, event_id=request['event_id'], id=run,
                task_id=ids[0], task_ids=ids, purpose=a['kind'], instance=inst['id'], model=r['models'][inst['model']],
                session=run, command=['external',rid], runtime_generation=own['generation'], runtime_principal=own['principal'])
    data.update(a.get('options', {}))
    rec = pm.execute(root, data, _db=db)['record']
    rec.update(runtime_owner=own, runner=rid, expert=inst.get('expert', {'id':'builtin','version':'installed'}),
               instance_revision=inst['revision'], instance_binding={k:inst.get(k) for k in ('active','model','runner','expert','level','master','write_roots')}, config_sha256=pm.team.read(pm.api(), root, CONFIG)[1], signal='claimed')
    pm.integrity.save(pm.api(), db, 'launch', rec)
    tasks = pm.task_map(db)
    launcher = load('launch')
    stops = pm.platform.stops(pm.api(), root, db, pm.config(db), tasks)[0] if a['kind']=='attend' else {}
    packet, text = launcher.packet(pm, root, run, a['kind'], inst, [tasks[i] for i in ids], stops, tasks, managed=True)
    return dict(record=rec, packet=packet, instance=inst, entry=expert, prompt=text)


def event(root, db, request, p):
    rec = pm.integrity.records(db,'launch').get(p.get('run_id'))
    need(rec and rec.get('runtime_owner', {}).get('principal') == request['_principal'], 'OWNER_MISMATCH', 'run belongs to another runtime')
    need(p.get('expected_revision') == rec['revision'], 'STALE_REVISION', 'reload run', True)
    kind = p.get('kind')
    allowed = {'accepted','started','heartbeat','unknown','failed','finished','stopped','handover','blocked','commands'}
    need(kind in allowed, 'INVALID_REQUEST', 'unknown run event')
    need(rec['state'] in pm.platform.ACTIVE, 'RUN_CLOSED', 'late event cannot modify a closed run')
    inst = pm.integrity.records(db,'instance').get(rec['instance'])
    valid = (inst and inst.get('active') and {k:inst.get(k) for k in rec.get('instance_binding', {})} == rec.get('instance_binding')
             and pm.team.read(pm.api(), root, CONFIG)[1] == rec.get('config_sha256'))
    if valid:
        try:
            pm.team.experts.entry(pm.api(), root, inst)
        except (ValueError, OSError):
            valid = False
    need(valid or kind in {'stopped','failed','finished','unknown'}, 'AUTHORIZATION_CHANGED', 'run authorization changed; stop and reconcile')
    if kind in {'accepted','heartbeat','unknown'}:
        need(pm.nonempty(p.get('receipt')), 'INVALID_REQUEST', 'runtime receipt required')
        rec.update(signal=kind, receipt=p['receipt'], revision=rec['revision']+1, last_event_at=pm.now())
        # Unknown remains active: never release ownership merely because a heartbeat expired.
        pm.integrity.save(pm.api(), db, 'launch', rec)
        return {'record':rec}
    if kind == 'commands':
        need(not rec.get('cancel_requested') and rec.get('signal') != 'unknown', 'RUN_STOPPING', 'run is stopping or unknown')
        commands = p.get('commands')
        need(isinstance(commands,list) and 0 < len(commands) <= 20, 'INVALID_REQUEST', 'bounded command list required')
        results = []
        for n, item in enumerate(commands):
            need(isinstance(item,dict) and not {'actor','event_id'} & item.keys(), 'INVALID_REQUEST', 'controller supplies command identity')
            need(item.get('op') in {'create','update','report','review','transition','reassign','handoff'}, 'UNAUTHORIZED', 'run cannot issue configuration or human approval commands')
            tasks = pm.task_map(db)
            tid = (item.get('task') or {}).get('parent') if item.get('op')=='create' else item.get('task_id')
            need(pm.team.within(tid, rec.get('task_ids') or [rec['task_id']], tasks), 'UNAUTHORIZED', 'command is outside run task scope')
            results.append(pm.execute(root, dict(item, actor=rec['instance'], event_id=request['event_id']+':'+str(n)), _db=db))
        rec.update(signal=kind, revision=rec['revision']+1, last_event_at=pm.now())
        pm.integrity.save(pm.api(),db,'launch',rec)
        return {'record':rec,'results':results}
    cmd = dict(id=rec['id'], event_id=request['event_id'])
    if kind == 'started':
        need(p.get('model') == rec['model'], 'MODEL_MISMATCH', 'selected model differs from claimed model')
        need(pm.nonempty(p.get('receipt')), 'INVALID_REQUEST', 'launch receipt required')
        cmd.update(op='launch_started', actor=pm.platform.SCHEDULER, pid=p.get('pid'))
    elif kind in {'handover','blocked'}:
        need(not rec.get('cancel_requested') and rec.get('signal') != 'unknown', 'RUN_STOPPING', 'run is stopping or unknown; reconcile first')
        cmd.update(op='hand_over' if kind=='handover' else 'report_blocked', actor=rec['instance'], run=rec['id'])
        cmd.update({k:p[k] for k in ('evidence','summary','reason') if k in p})
    elif kind == 'failed' and rec['state'] == 'starting':
        cmd.update(op='launch_failed', actor=pm.platform.SCHEDULER, error=p.get('receipt'))
    else:
        need(pm.nonempty(p.get('receipt')) and type(p.get('exit_code')) is int, 'INVALID_REQUEST', 'actual stop/exit receipt and exit code required')
        cmd.update(op='launch_exit', actor=pm.platform.LAUNCHER, exit_code=p['exit_code'])
        if 'usage' in p:
            cmd['usage'] = p['usage']
    if 'reported_model' in p:
        need(kind in {'started','finished','stopped','failed'}, 'INVALID_REQUEST', 'model report requires start or exit receipt')
        cmd['reported_model'] = p['reported_model']
    result = pm.execute(root, cmd, _db=db)
    latest = pm.integrity.records(db,'launch')[rec['id']]
    latest.update(signal=kind, receipt=p.get('receipt'), last_event_at=pm.now())
    if kind in {'handover','blocked'}:
        latest['revision'] += 1
    pm.integrity.save(pm.api(), db, 'launch', latest)
    return dict(result, record=latest)


def dispatch(root, db, cfg, who, request):
    op, p = request['op'], request['params']
    if op == 'capabilities':
        return capabilities(cfg)
    if op in {'inspect','validate'}:
        return dict(owner=owner(db), capabilities=capabilities(cfg), revision=revision(db))
    if op == 'tasks.query':
        need(p.get('op','status') in {'status','task','team','find','continue','project','resolve_instance','model_performance'}, 'INVALID_REQUEST', 'unsupported task query')
        return pm.execute(root, dict(p, op=p.get('op','status')), _db=db)
    if op == 'tasks.command':
        return command(root, db, who, request, p)
    if op == 'actions.plan':
        return plan(root, db)
    if op == 'actions.claim':
        return claim(root, db, cfg, who, request, p)
    if op == 'runs.query':
        records = pm.integrity.records(db,'launch')
        return {'runs': [records[p['run_id']]] if p.get('run_id') in records else list(records.values()) if 'run_id' not in p else []}
    if op == 'runs.event':
        return event(root, db, request, p)
    if op == 'runs.cancel':
        rec = pm.integrity.records(db,'launch').get(p.get('run_id'))
        need(rec and rec['state'] in pm.platform.ACTIVE, 'RUN_CLOSED', 'active run required')
        need(rec.get('runtime_owner',{}).get('principal') == request['_principal'], 'OWNER_MISMATCH', 'run belongs to another runtime')
        need(p.get('expected_revision') == rec['revision'], 'STALE_REVISION', 'reload run', True)
        need(pm.nonempty(p.get('reason')), 'INVALID_REQUEST', 'cancellation reason required')
        rec.update(cancel_requested=p['reason'], revision=rec['revision']+1)
        pm.integrity.save(pm.api(), db, 'launch', rec)
        return {'record':rec, 'stopped':False}
    if op == 'runtime.configure':
        before = owner(db)
        need(p.get('expected_generation') == before['generation'], 'STALE_REVISION', 'reload runtime owner', True)
        need(not pm.platform.active(pm.api(), db), 'RUNS_ACTIVE', 'stop and reconcile active runs before switching owner')
        need(p.get('mode') in {'local','external'}, 'INVALID_REQUEST', 'mode must be local or external')
        value = dict(id='project', mode=p['mode'], principal=request['_principal'], generation=before['generation']+1)
        pm.integrity.save(pm.api(), db, 'runtime_owner', value)
        return value
    if op.startswith('expert.'):
        return getattr(pm.team.experts, op.split('.')[1])(pm.api(), root, p)
    if op == 'scripts.inspect':
        return {'scripts':cfg.get('scripts',{})}
    if op == 'scripts.request':
        script = cfg.get('scripts',{}).get(p.get('id'))
        need(isinstance(script,dict) and pm.strings(script.get('argv')) and script['argv'], 'UNSUPPORTED', 'registered argv script required')
        need(not p.get('args'), 'INVALID_REQUEST', 'only the exact registered argv is allowed')
        need(pm.nonempty(script.get('permissions')) and pm.nonempty(script.get('effect')), 'INVALID_CONFIG', 'script permissions and side effects required')
        value = dict(id=request['event_id'], script=p['id'], argv=script['argv'], state='requested', principal=request['_principal'])
        pm.integrity.save(pm.api(), db, 'script_request', value)
        return value
    raise ProtocolError('INVALID_REQUEST','unknown operation')


def handle(project, request, principal):
    with TRANSACTIONS:
        return handle_transaction(project, request, principal)


def handle_transaction(project, request, principal):
    root, db = Path(project).resolve(), None
    rid = request.get('request_id') if isinstance(request,dict) else None
    try:
        need(isinstance(request,dict) and set(request) <= {'protocol','request_id','project_id','op','params','event_id'}, 'INVALID_REQUEST','unknown request fields')
        need(request.get('protocol') == SPEC, 'UNSUPPORTED_PROTOCOL','use '+SPEC)
        need(all(pm.nonempty(request.get(k)) for k in ('request_id','project_id','op')) and isinstance(request.get('params',{}),dict), 'INVALID_REQUEST','request id, project id, operation and object params required')
        cfg, who = access(root,principal)
        need(cfg.get('project_id') == request['project_id'], 'PROJECT_MISMATCH','project id mismatch')
        op = request['op']
        need(op in OPERATIONS, 'INVALID_REQUEST','unknown operation')
        need(op in who.get('operations', []), 'UNAUTHORIZED','operation is outside principal scope')
        try:
            contract.validate(op, request.get('params', {}))
        except ValueError as error:
            raise ProtocolError('INVALID_REQUEST', str(error))
        write = op in WRITES
        need(not write or pm.nonempty(request.get('event_id')), 'INVALID_REQUEST','mutation event_id required')
        # A managed project is already initialized. Do not execute schema DDL on
        # every concurrent request before acquiring its transaction lock.
        database = pm.local(root, 'management/runtime/tasks.sqlite3')
        need(database.is_file(), 'INVALID_CONFIG', 'initialize the task database before platform access')
        db = sqlite3.connect(database.as_uri() + ('?mode=rw' if write else '?mode=ro'), uri=True, timeout=20, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute('BEGIN IMMEDIATE' if write else 'BEGIN')
        payload = dict(request, params=request.get('params',{}), _principal=principal)
        token = hashlib.sha256(pm.canon(payload).encode()).hexdigest()
        if write:
            old = pm.integrity.records(db,'api_request').get(rid)
            if old:
                need(old['sha256'] == token, 'IDEMPOTENCY_CONFLICT','request id reused with different contents')
                db.commit()
                return old['response']
            events = pm.integrity.records(db,'api_event')
            old = events.get(request['event_id'])
            if old:
                semantic = dict(payload); semantic.pop('request_id')
                need(old['sha256'] == hashlib.sha256(pm.canon(semantic).encode()).hexdigest(), 'IDEMPOTENCY_CONFLICT','event id reused with different contents')
                db.commit()
                return dict(old['response'], request_id=rid)
        result = dispatch(root,db,cfg,who,payload)
        response = dict(protocol=SPEC, request_id=rid, ok=True, result=result, revision=revision(db))
        if write:
            semantic = dict(payload); semantic.pop('request_id')
            pm.integrity.save(pm.api(),db,'api_request',dict(id=rid, sha256=token, response=response))
            pm.integrity.save(pm.api(),db,'api_event',dict(id=request['event_id'], sha256=hashlib.sha256(pm.canon(semantic).encode()).hexdigest(), response=response))
        db.commit()
        return response
    except subprocess.SubprocessError:
        if db:
            db.rollback()
        return dict(protocol=SPEC, request_id=rid, ok=False, error=dict(code='SOURCE_UNAVAILABLE', message='Git source retrieval failed or timed out; no source scripts were executed', retryable=True))
    except sqlite3.OperationalError as error:
        if db:
            db.rollback()
        return dict(protocol=SPEC, request_id=rid, ok=False, error=dict(code='STORAGE_BUSY' if 'locked' in str(error) else 'STORAGE_ERROR', message=str(error), retryable='locked' in str(error)))
    except (ValueError, OSError, KeyError, TypeError) as error:
        if db:
            db.rollback()
        return dict(protocol=SPEC, request_id=rid, ok=False, error=dict(code=getattr(error,'code','REJECTED'), message=str(error), retryable=getattr(error,'retryable',False)))
    finally:
        if db:
            db.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--project', required=True)
    parser.add_argument('--principal', required=True, help='authenticated identity supplied by trusted transport, not worker input')
    parser.add_argument('--request', help='JSON file; stdin when omitted')
    args = parser.parse_args()
    try:
        request = json.loads(Path(args.request).read_text(encoding='utf-8') if args.request else sys.stdin.read())
        response = handle(args.project, request, args.principal)
    except (ValueError,OSError) as error:
        response = dict(protocol=SPEC, ok=False, error=dict(code='INVALID_JSON', message=str(error), retryable=False))
    print(json.dumps(response, ensure_ascii=False))
    return 0 if response['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
