"""Synthetic project facts and accepted work, without invented business results."""
import importlib.util
import json


def populate(root, case_id):
    tool = next(p for p in [root/'kit/matrix/orchestration/tools/pm_tasks.py', root/'kit/.agents/skills/project-management-agent/scripts/pm_tasks.py'] if p.is_file())
    spec = importlib.util.spec_from_file_location('project_fixture', tool)
    pm = importlib.util.module_from_spec(spec); spec.loader.exec_module(pm)
    n = 0
    def call(op, actor='PM', **kw):
        nonlocal n
        n += 1
        return pm.execute(root, dict(op=op, actor=actor, event_id=f'SIM-{n}', **kw))
    field = 'frontdoor_id' if 'frontdoor_id' in tool.read_text() else 'frontdoor_thread'
    call('init', config=dict(project='Synthetic project', pm_actor='PM', authorization='Synthetic fixture only', max_slots=3, **{field:'SIM'}))
    (root/'brief.md').write_text('Synthetic product: employee suggestion board. Business target: 20 participating employees in week one. No actual adoption data yet; project lead Lin owns the data.\n')
    (root/'accepted.txt').write_text('Synthetic accepted deliverable: suggestion board prototype. No production adoption is evidenced.\n')
    if case_id == 'pm_project_type':
        return
    tids = ['A','B'] if case_id == 'pm_resource_queue' else ['A']
    for tid in tids:
        call('create', task=dict(id=tid, title='Synthetic '+tid, parent=None, owner='PM', executor='PM', checker='QA',
             goal='Deliver prototype', inputs=['brief.md'], outputs=['accepted.txt'], criteria=['prototype checked'],
             next_action='continue', resources=['only-device'] if case_id == 'pm_resource_queue' else []))
    if case_id != 'pm_resource_queue':
        call('update', task_id='A', expected_revision=1, changes={'evidence':['accepted.txt']}, reason='Synthetic historical delivery')
        t = pm.execute(root, {'op':'status'})['tasks'][0]
        call('review', 'QA', task_id='A', expected_revision=t['revision'], outcome='passed', criteria_checked=t['criteria'], evidence=['Synthetic historical check'])
        t = pm.execute(root, {'op':'status'})['tasks'][0]
        call('transition', task_id='A', expected_revision=t['revision'], state='done', reason='Synthetic accepted prototype')
    if case_id == 'pm_project_close':
        (root/'open-items.md').write_text('Known follow-up: delete synthetic test data before real use. No receiving owner is assigned. Business evidence is still missing; do not assume success or claim operational responsibility.\n')
    pm.render(root)
