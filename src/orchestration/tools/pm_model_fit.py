"""Evidence freshness and read-only performance signals, never automatic regrading."""
from datetime import datetime, timezone
import json

METRICS = ('review_failed', 'rework', 'escalation', 'ended_without_handover')
TAGS = ('long_horizon', 'complex_dispatch', 'deep_reasoning')


def when(value):
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return parsed.astimezone(timezone.utc) if parsed.tzinfo else None
    except (AttributeError, TypeError, ValueError):
        return None


def performance(pm, db, since=None):
    """Replay assignments and runs so later relevels/models do not rewrite history."""
    cutoff = when(since) if since else None
    pm.require(since is None or cutoff is not None, 'since requires a timezone-aware ISO timestamp')
    fallback = pm.integrity.records(db, 'instance')
    instances, runs, rows, seen, tasks = {}, {}, {}, set(), {}
    for event in db.execute('SELECT * FROM events ORDER BY seq'):
        cmd = json.loads(event['command'])
        result = json.loads(event['result'])
        before = json.loads(event['before_data']) if event['before_data'] else {}
        after = json.loads(event['after_data']) if event['after_data'] else {}
        if after.get('id'):
            tasks[after['id']] = after
        record = result.get('record') or {}
        op = cmd.get('op')
        if op in {'derive', 'register_instance', 'relevel_instance', 'retire_instance', 'rename_instance'} and record.get('id'):
            instances[record['id']] = record
        if op in {'launch_started', 'launch_exit', 'launch_lost'} and record.get('running_at'):
            for tid in record.get('task_ids') or [record.get('task_id')]:
                runs[(tid, record['instance'])] = record
        if cutoff and (when(event['occurred_at']) or datetime.min.replace(tzinfo=timezone.utc)) <= cutoff:
            continue
        signals = []
        producer = (before or after).get('executor') or (before or after).get('owner')
        if op == 'review' and (after.get('review') or {}).get('outcome') == 'failed':
            signals.append(('review_failed', producer, None))
        rw, old = after.get('rework') or {}, before.get('rework') or {}
        if rw.get('count', 0) > old.get('count', 0):
            signals.append(('rework', rw.get('attributed_to') or producer, None))
        # Nested launch commands also carry escalation; count the task mutation once.
        if after.get('id') and (cmd.get('escalation') or (op == 'report' and cmd.get('delivery') in {'sent', 'received'})):
            signals.append(('escalation', producer, None))
        if op in {'launch_exit', 'launch_lost'} and record.get('ended_without_handover'):
            signals.append(('ended_without_handover', record.get('instance'), record))
        for metric, iid, run in signals:
            task = before or after
            tid = record.get('task_id') if run else event['task_id']
            if run:
                task = tasks.get(tid, {})
            inst = instances.get(iid, fallback.get(iid, {}))
            run = run or runs.get((tid, iid), {})
            model = inst.get('model', 'unknown')
            version = run.get('reported_model') or run.get('model', model)
            key = (model, version, inst.get('profession') or inst.get('role', 'unknown'), task.get('difficulty') or 'unknown')
            unique = (metric, record.get('id')) if metric == 'ended_without_handover' else (metric, event['seq'])
            if unique in seen:
                continue
            seen.add(unique)
            row = rows.setdefault(key, dict(model=key[0], model_version=key[1], profession=key[2], level=key[3],
                                            **dict.fromkeys(METRICS, 0), signals=[]))
            row[metric] += 1
            row['signals'].append(dict(metric=metric, task=tid, instance=iid, event_seq=event['seq'],
                                       version_source='host_report' if run.get('reported_model') else ('launch_selection' if run else 'configuration'),
                                       cause=(after.get('review') or {}).get('cause') if metric == 'review_failed' else rw.get('reason')))
    return {'rows': sorted(rows.values(), key=lambda r: (r['model'], r['model_version'], r['profession'], r['level'])),
            'since': since, 'limitation': 'Recorded signals, not causal proof or automatic demotion; missing runs use configuration and are labelled.'}


def reasons(pm, db, assessment):
    if not assessment:
        return ['assessment_missing']
    out = []
    evaluated, deadline = when(assessment.get('evaluated_at')), when(assessment.get('review_after'))
    if (assessment.get('basis') not in {'trial', 'performance', 'human', 'host'} or
            not pm.strings(assessment.get('evidence')) or not assessment.get('evidence') or
            not pm.nonempty(assessment.get('model_version')) or evaluated is None or deadline is None or
            (evaluated and deadline and deadline <= evaluated)):
        out.append('assessment_evidence_incomplete')
    now = when(pm.now())
    if evaluated and evaluated > now:
        out.append('assessment_in_future')
    if deadline and now >= deadline:
        out.append('review_time_reached')
    conditions = assessment.get('review_conditions')
    if not isinstance(conditions, dict) or any(k not in METRICS or type(v) is not int or v < 0 for k, v in (conditions or {}).items()):
        out.append('review_conditions_invalid')
        conditions = {}
    if db is None:
        return out
    instances = pm.integrity.records(db, 'instance')
    latest = {}
    for run in pm.integrity.records(db, 'launch').values():
        inst = instances.get(run.get('instance'), {})
        at = when(run.get('running_at'))
        if not run.get('reported_model') or inst.get('model') != assessment.get('model') or at is None or (evaluated and at < evaluated):
            continue
        iid = inst['id']
        if iid not in latest or at >= latest[iid][0]:
            latest[iid] = (at, run['reported_model'])
    versions = sorted({v for _, v in latest.values() if v != assessment.get('model_version')}, key=str)
    if versions:
        out.append('model_version_changed:' + ','.join(map(str, versions)))
    if evaluated and conditions:
        counts = dict.fromkeys(METRICS, 0)
        for row in performance(pm, db, assessment['evaluated_at'])['rows']:
            if row['model'] == assessment['model']:
                for metric in METRICS:
                    counts[metric] += row[metric]
        for metric, limit in conditions.items():
            if counts[metric] > limit:
                out.append('performance:' + metric + ':' + str(counts[metric]) + '>' + str(limit))
    return out


def required(reg, requested):
    capabilities = list(reg.get('model_capabilities', []))
    for floor, tags in reg.get('levels', {}).get('capabilities', {}).items():
        if int(requested[1]) >= int(floor[1]):
            capabilities.extend(tags)
    return list(dict.fromkeys(capabilities))
