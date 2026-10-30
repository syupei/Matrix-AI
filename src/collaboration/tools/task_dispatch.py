"""Trusted host bridge between the task source, request ledger and real transport.

The host supplies authenticated bindings and send/wake functions. This module
does not launch a daemon, accept model-provided endpoints, or certify tool isolation.
"""
import importlib.util
import json
from pathlib import Path


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Dispatcher:
    def __init__(self, project, skills, send, wake):
        self.root = Path(project).resolve()
        skills = Path(skills)
        self.pm = load('dispatch_pm', skills/'project-management-agent/scripts/pm_tasks.py')
        self.coord = load('dispatch_coord', skills/'professional-agent-collaboration/scripts/coordination.py')
        self.send, self.wake = send, wake

    def task(self, tid):
        return next(t for t in self.pm.execute(self.root, {'op': 'status'})['tasks'] if t['id'] == tid)

    def c(self, op, actor='coordinator', **fields):
        return self.coord.execute(self.root, dict(op=op, actor=actor, **fields))

    def binding_current(self, req, task):
        binding = req['payload']['task_binding']
        appointment = next((a for a in self.pm.execute(self.root, {'op': 'team'})['appointments'] if a['id'] == binding['executor']), None)
        try:
            sources_current = all(self.coord.fingerprint(self.root, name) == sha for name, sha in req['expected_sources'].items())
        except (OSError, ValueError):
            sources_current = False
        return bool(sources_current and task['work_revision'] == binding['work_revision'] and task.get('executor') == binding['executor'] and appointment and appointment['current'] and appointment['revision'] == binding['appointment_revision'])

    def dispatch(self, tid, request_id, sources, authorization):
        """Called after host registered real endpoints and allocated appointments.
        send(endpoint, packet) returns outcome/evidence and optionally started=True
        plus start_evidence. Accepted delivery alone never marks a task running.
        """
        task = self.task(tid)
        previous = next((r for r in self.c('status')['requests'] if r['id'] == request_id), None)
        if previous:
            payload = previous['payload']
            self.pm.require(payload.get('task_binding', {}).get('task_id') == tid and payload['sources'] == sources and payload['authorization'] == authorization, 'dispatch id reused with different task or inputs')
            if previous['state'] != 'ready':
                return {'request': previous, 'sent_now': False}
            self.pm.require(self.binding_current(previous, task), 'dispatch binding changed; reconcile and create a new request')
        self.pm.require(task['ready'], 'task not ready: ' + ','.join(task['readiness_issues']))
        self.pm.require(task.get('executor'), 'actual executor required')
        team = self.pm.execute(self.root, {'op': 'team'})
        appointment = next((a for a in team['appointments'] if a['id'] == task['executor'] and a['current']), None)
        self.pm.require(appointment, 'current execution appointment required')
        request = dict(id=request_id, source=task['manager'], target=task['executor'],
                       question=task['goal'], expected_output=json.dumps({'outputs': task['outputs'], 'criteria': task['criteria']}, ensure_ascii=False),
                       authorization=authorization, sources=sources,
                       write_allowed=[appointment['workspace']+'/workspace'],
                       task_binding={'task_id': tid, 'work_revision': task['work_revision'],
                                     'executor': task['executor'], 'appointment_revision': appointment['revision']})
        req = previous or self.c('request', task['manager'], request=request)
        if req['state'] != 'ready':
            return {'request': req, 'sent_now': False}
        req = self.c('claim', id=request_id)
        if req['state'] != 'dispatching':
            return {'request': req, 'sent_now': False}
        packet = self.c('packet', id=request_id)
        try:
            receipt = self.send(packet['target_role']['endpoint'], packet)
        except Exception as error:
            self.c('receipt', id=request_id, attempt=req['attempt'], outcome='uncertain', evidence='transport raised '+type(error).__name__)
            raise
        req = self.c('receipt', id=request_id, attempt=req['attempt'], outcome=receipt['outcome'], evidence=receipt['evidence'])
        if receipt['outcome'] == 'sent' and receipt.get('started') is True:
            self.mark_started(request_id, receipt.get('start_evidence'))
        return {'request': req, 'sent_now': receipt['outcome'] == 'sent'}

    def mark_started(self, request_id, evidence):
        self.pm.require(isinstance(evidence, str) and evidence.strip(), 'actual start evidence required')
        req = self.c('show', id=request_id)
        self.pm.require(req['state'] in {'inflight', 'answered', 'needs_human'}, 'delivery not confirmed')
        binding = req['payload']['task_binding']; task = self.task(binding['task_id'])
        if req.get('responses'):
            return task  # A late start receipt cannot resurrect returned work.
        self.pm.require(self.binding_current(req, task), 'task, sources or appointment changed after dispatch; stop/reconcile the worker')
        if task['state'] == 'running':
            return task
        return self.pm.execute(self.root, dict(op='transition', actor=task['owner'], event_id=request_id+'-started',
                               task_id=task['id'], expected_revision=task['revision'], state='running',
                               execution_receipt=evidence, reason='actual execution started'))

    def collect(self, request_id):
        """Return and wake, never approve or adopt the professional deliverable.
        wake(endpoint, notification) must deduplicate notification.event_id. A host
        without wake support returns unavailable, preserving the pending return.
        """
        req = self.c('show', id=request_id)
        self.pm.require(req['state'] in {'answered', 'needs_human', 'failed', 'stale'}, 'no completed response to collect')
        self.pm.require(req.get('responses'), 'transport failure is not a professional response')
        binding = req['payload']['task_binding']; task = self.task(binding['task_id'])
        current = self.binding_current(req, task) and task['state'] not in self.pm.TERMINAL
        notification = dict(event_id=request_id+'-returned', request_id=request_id, task_id=task['id'],
                            kind='returned' if current and req['state'] == 'answered' else 'needs_attention',
                            source_current=bool(current), response_state=req['state'])
        if current:
            answer = req['responses'][-1]['answer']
            event_id = request_id+'-return-recorded'
            db = self.pm.connect(self.root, readonly=True)
            try:
                recorded = db.execute('SELECT 1 FROM events WHERE event_id=?', (event_id,)).fetchone()
            finally:
                db.close()
            if not recorded:
                if task['state'] == 'running':
                    self.pm.execute(self.root, dict(op='transition', actor=task['owner'], event_id=request_id+'-yielded',
                                    task_id=task['id'], expected_revision=task['revision'], state='waiting_review' if req['state']=='answered' else 'blocked',
                                    reason='response returned; awaiting owner evaluation', stop_evidence='request '+request_id+' returned and yielded'))
                    task = self.task(task['id'])
                self.pm.execute(self.root, dict(op='report', actor=task['owner'], event_id=event_id, task_id=task['id'],
                                expected_revision=task['revision'], summary=answer['summary'], next_action='responsible lead evaluates returned evidence',
                                impact=req['state'], delivery='received', receipt='request '+request_id, request_id=request_id))
        roles = {r['id']: r for r in self.c('status')['roles']}
        endpoint = roles.get(req['source'], {}).get('endpoint')
        if not endpoint or endpoint['kind'] == 'inline':
            return {'notification': notification, 'wake': {'outcome': 'unavailable', 'reason': 'resume at the active coordination entry'}}
        # Notification never includes a claim of approval or task completion.
        receipt = self.wake(endpoint, notification)
        return {'notification': notification, 'wake': receipt}
