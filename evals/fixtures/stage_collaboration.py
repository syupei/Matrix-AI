"""Synthetic stage and human-routing records; no real approvals or workers."""
import importlib.util
import json


def populate(root, case_id):
    tool = next(p for p in [root / 'kit/matrix/orchestration/tools/pm_tasks.py',
                            root / 'kit/.agents/skills/project-management-agent/scripts/pm_tasks.py'] if p.is_file())
    spec = importlib.util.spec_from_file_location('probe_pm', tool)
    pm = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(pm)
    n = 0

    def call(op, **kw):
        nonlocal n
        n += 1
        return pm.execute(root, dict(op=op, actor='PM', event_id=f'fixture-{n}', **kw))

    frontdoor = 'frontdoor_id' if 'frontdoor_id' in tool.read_text() else 'frontdoor_thread'
    call('init', config=dict(project='Synthetic board', pm_actor='PM', authorization='Synthetic evaluation',
                             max_slots=3, **{frontdoor: 'synthetic'}))
    roster = root / pm.ROSTER
    roster.parent.mkdir(parents=True, exist_ok=True)
    roster.write_text(json.dumps({'people': [
        {'id': 'lin', 'name': '林', 'decides': ['project']},
        {'id': 'chen', 'name': '陈', 'decides': ['product'], 'masters': ['product']},
        {'id': 'zhou', 'name': '周', 'decides': ['engineering'], 'masters': ['code-engineering']},
        {'id': 'zhang', 'name': '张', 'decides': []}]}))
    for tid, title, dependencies in [('P', '产品', []), ('D', '设计', ['P']), ('E', '研发', ['P'])]:
        call('create', task=dict(id=tid, title=title, kind='stage', parent=None, owner='PM', executor='PM', checker='QA',
                                goal=title, inputs=['brief.md'], outputs=['result.md'], criteria=['accepted'],
                                dependencies=dependencies, next_action='核对阶段成果'))
    (root / 'brief.md').write_text('Synthetic board with an export feature; no live workers.\n')
    t = next(t for t in pm.execute(root, {'op': 'status'})['tasks'] if t['id'] == 'P')
    call('transition', task_id='P', expected_revision=t['revision'], state='running', reason='Synthetic work underway',
         execution_receipt='SIMULATED start receipt, not a real worker')
    pm.render(root)
    (root / 'FIXTURE.md').write_text('Synthetic fixture. PM is the manager. P is running; D and E are planned, both depend on P. No actual workers or human responses may be invented.\n')
