"""Synthetic stopped scheduler; no worker is running and no startup is authorized."""
import importlib.util
import json


def populate(root, case_id):
    tool = next(p for p in [root/'kit/matrix/orchestration/tools/pm_tasks.py',
                            root/'kit/.agents/skills/project-management-agent/scripts/pm_tasks.py'] if p.is_file())
    spec = importlib.util.spec_from_file_location('health_fixture', tool)
    pm = importlib.util.module_from_spec(spec); spec.loader.exec_module(pm)
    frontdoor = 'frontdoor_id' if 'frontdoor_id' in tool.read_text() else 'frontdoor_thread'
    pm.execute(root, dict(op='init', actor='PM', event_id='SIM-init', config=dict(project='Synthetic board',
               pm_actor='PM', authorization='Synthetic fixture only', max_slots=1, **{frontdoor: 'SIM'})))
    pm.execute(root, dict(op='create', actor='PM', event_id='SIM-task', task=dict(id='P', title='产品规则',
               parent=None, owner='PM', executor='PM', checker='QA', goal='Define product', inputs=['brief.md'],
               outputs=['product.md'], criteria=['checked'], next_action='PM安排执行')))
    (root/'brief.md').write_text('Synthetic project. No workers are live.\n')
    path = root/'management/runtime/scheduler-heartbeat.json'
    path.write_text(json.dumps(dict(checked_at='2000-01-01T00:00:00+00:00', check_seconds=60, result='idle')))
    (root/'management/runtime/platform.json').write_text('{"launch":["SIM-not-a-live-runner"]}')
    pm.render(root)
