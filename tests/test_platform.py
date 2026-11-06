"""Platform runs: launch records, stop reasons, limits, the launch command and the timer.
Mechanism tests only: every person, model, run and host command is SIMULATED (stub programs, no model is called)."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

from kit import KIT
TOOLS = KIT / 'matrix/orchestration/tools'
spec = importlib.util.spec_from_file_location('pm_platform_under_test', TOOLS / 'pm_tasks.py')
pm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pm)
CONFIG = {'entries': [
    {'id': 'P-M', 'profession': 'product', 'level': 'T7', 'model': 'SIM-big', 'count': 1, 'master': True},
    {'id': 'P-E', 'profession': 'product', 'level': 'T4', 'model': 'SIM-small', 'count': 3},
    {'id': 'Q-M', 'profession': 'quality-engineering', 'level': 'T7', 'model': 'SIM-big', 'count': 1, 'master': True}]}
# A SIMULATED worker: reads its task packet and acts as stub-plan.json says (handover, block, exit, sleep).
WORKER = r'''
import json, re, subprocess, sys, time
from pathlib import Path
root, text = Path.cwd(), sys.stdin.read()
rid = re.search(r'# 任务包 (\S+?)（', text).group(1)
iid = re.search(r'actor 写 (\S+?)。', text).group(1)
purpose = re.search(r'平台运行：(\S+?)）', text).group(1)
plan = json.loads((root / 'stub-plan.json').read_text())
def call(cmd):
    r = subprocess.run([sys.executable, '-B', TOOLS + '/pm_tasks.py', '--project', '.'], input=json.dumps(cmd), capture_output=True, text=True, cwd=root)
    return json.loads(r.stdout)
def task(tid):
    return next(t for t in call({'op': 'status'})['tasks'] if t['id'] == tid)
if purpose == '执行':
    tid = re.search(r'## 任务 (\S+?)：', text).group(1)
    how = plan.get(tid, 'handover')
    if how == 'sleep':
        time.sleep(30)
    if how == 'handover':
        call({'op': 'transition', 'actor': iid, 'event_id': rid + '-handover', 'task_id': tid, 'expected_revision': task(tid)['revision'],
              'state': 'waiting_review', 'reason': 'SIM done', 'stop_evidence': rid + ' SIM run done', 'evidence': ['SIM result ' + tid]})
'''
# A SIMULATED PM: runs continuation and does what it lists until nothing is left (no judgment beyond that).
PMSTUB = r'''
import json, subprocess, sys, time
from pathlib import Path
root = Path.cwd()
sys.stdin.read()
plan = json.loads((root / 'stub-plan.json').read_text())
if plan.get('pm') == 'hang':
    time.sleep(30)
def call(cmd):
    r = subprocess.run([sys.executable, '-B', TOOLS + '/pm_tasks.py', '--project', '.'], input=json.dumps(cmd), capture_output=True, text=True, cwd=root)
    return json.loads(r.stdout)
n = 0
for _ in range(20):
    s, acted = call({'op': 'continue'}), False
    for a in s['actions']:
        n += 1
        if a['kind'] == 'start':
            subprocess.run([sys.executable, '-B', TOOLS + '/launch.py', '--project', '.', '--task', a['task']], cwd=root, capture_output=True)
        elif a['kind'] == 'pm':
            t = next(x for x in call({'op': 'status'})['tasks'] if x['id'] == a['task'])
            code = s['stops'][a['task']]['code']
            if code == 'review':
                call({'op': 'review', 'actor': 'PM', 'event_id': 'PMSTUB-review-' + str(n) + '-' + t['id'], 'task_id': t['id'], 'expected_revision': t['revision'],
                      'outcome': 'passed', 'criteria_checked': t['criteria'], 'evidence': ['SIM check']})
            elif code == 'adopt':
                call({'op': 'transition', 'actor': 'PM', 'event_id': 'PMSTUB-done-' + str(n) + '-' + t['id'], 'task_id': t['id'],
                      'expected_revision': t['revision'], 'state': 'done', 'reason': 'SIM adopted'})
            else:
                continue
        else:
            continue
        acted = True
        break
    if not acted:
        break
'''


class Project:
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix='pm-platform-simulation-')
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        (self.root / 'management').mkdir()
        self.n = 0
        self.call('init', config=dict(project='SIMULATED', pm_actor='PM', authorization='SIMULATED only', frontdoor_id='SIMULATED', max_slots=3))
        (self.root / 'management/instance-config.json').write_text(json.dumps(CONFIG))
        self.call('confirm_config', person='SIM-owner', quote='SIMULATED: 按这个配置', presented_ref='SIM shown',
                  choices={e['id']: 'acknowledge_unregistered' for e in CONFIG['entries']})
        for entry in ['P-M', 'P-E', 'P-E']:  # product-001 (master), product-002, product-003; P-E has room for one more
            self.call('derive', entry=entry, endpoint='platform')
        (self.root / 'input.md').write_text('SIMULATED input v1')
        self.task('A')
        self.task('B', dependencies=['A'])

    def call(self, op, actor='PM', **kw):
        self.n += 1
        return pm.execute(self.root, dict(op=op, actor=actor, event_id='SIM-' + str(self.n), **kw))

    def task(self, tid, parent=None, actor='PM', **kw):
        data = dict(id=tid, parent=parent, title='SIM ' + tid, owner='product-001', executor='product-001', checker='PM', goal='SIMULATED',
                    inputs=['input.md'], outputs=['SIM output'], criteria=['SIM correct'], next_action='SIM next')
        data.update(kw)
        return self.call('create', actor, task=data)

    def t(self, tid):
        return next(t for t in pm.execute(self.root, {'op': 'status'})['tasks'] if t['id'] == tid)

    def launch(self, tid, rid=None, purpose='start', instance=None, model='SIM-big', **kw):
        rid = rid or 'run-' + tid + '-' + str(self.n)
        instance = instance or self.t(tid)['executor']
        self.call('launch_start', id=rid, purpose=purpose, task_id=tid, instance=instance, model=model, session='SIM-' + rid, command=['SIM-cli'], **kw)
        self.call('launch_started', id=rid, pid=4242)
        return rid

    def hand_over(self, tid):
        t = self.t(tid)
        self.call('transition', t['owner'], task_id=tid, expected_revision=t['revision'], state='waiting_review', reason='SIM handed over',
                  stop_evidence='SIM stopped', evidence=['SIM work ' + tid])

    def exit(self, rid, code=0):
        return self.call('launch_exit', 'launcher', id=rid, exit_code=code)

    def summary(self):
        return pm.execute(self.root, {'op': 'continue'})


class Records(Project, unittest.TestCase):
    def test_a_start_run_moves_the_task_and_an_exit_without_handover_stops_it(self):
        rid = self.launch('A')
        self.assertEqual('running', self.t('A')['state'])
        self.assertEqual('platform run ' + rid, self.t('A')['reason'])
        self.assertEqual(('running', 'product-001'), (self.summary()['stops']['A']['code'], self.summary()['stops']['A']['who']))
        self.exit(rid, 0)
        self.assertEqual('blocked', self.t('A')['state'])
        s = self.summary()
        self.assertEqual('ended', s['stops']['A']['code'])
        self.assertIn({'kind': 'pm', 'task': 'A', 'why': '结束未交出'}, s['actions'])

    def test_a_handover_leaves_the_task_for_its_checker_and_a_repeated_exit_changes_nothing(self):
        rid = self.launch('A')
        self.hand_over('A')
        self.exit(rid)
        self.assertTrue(self.exit(rid)['unchanged'])
        self.assertEqual('waiting_review', self.t('A')['state'])
        self.assertEqual('review', self.summary()['stops']['A']['code'])

    def test_a_failed_start_reverts_the_task_and_retries_are_capped(self):
        for i in range(3):
            rid = 'run-fail-' + str(i)
            self.call('launch_start', id=rid, purpose='start', task_id='A', instance='product-001', model='SIM-big', session='S' + str(i), command=['SIM-cli'])
            self.call('launch_failed', id=rid, error='SIM host command missing')
            self.assertEqual('planned', self.t('A')['state'])
        with self.assertRaisesRegex(pm.TaskError, 'retries for A exhausted'):
            self.launch('A')
        s = self.summary()
        self.assertEqual('launch_failed', s['stops']['A']['code'])
        self.assertEqual('needs_human', s['stop'])

    def test_only_the_launcher_uses_a_launch_to_move_a_task(self):
        rid = self.launch('A')
        with self.assertRaisesRegex(pm.TaskError, 'belongs to its owner'):
            self.call('transition', 'product-002', task_id='A', expected_revision=self.t('A')['revision'], state='blocked', launch_id=rid,
                      reason='SIM', stop_evidence='SIM')

    def test_one_run_per_instance_and_per_task(self):
        self.launch('A')
        self.task('C')
        with self.assertRaisesRegex(pm.TaskError, 'already running'):
            self.launch('C')

    def test_unattended_limit_counts_from_the_persons_last_words(self):
        self.call('configure', limits={'unattended_launches': 2}, person='SIM-owner', quote='SIMULATED: 最多拉起两次')
        for tid in ['A', 'C']:
            if tid == 'C':
                self.task('C', owner='product-002', executor='product-002', parent='A', actor='product-001')
            self.exit(self.launch(tid))
        self.task('D', owner='product-003', executor='product-003', parent='A', actor='product-001')
        with self.assertRaisesRegex(pm.TaskError, 'unattended launch limit reached'):
            self.launch('D')
        self.assertEqual('budget', self.summary()['stops']['D']['code'])
        self.call('inbox', id='IN-1', kind='continue', text='继续', person='SIM-owner', quote='SIMULATED: 继续')
        self.launch('D')

    def test_a_project_pause_stops_launches_until_the_person_resumes(self):
        self.call('pause_project', person='SIM-owner', quote='SIMULATED: 先停一下', reason='SIM 预算复核')
        with self.assertRaisesRegex(pm.TaskError, 'project paused'):
            self.launch('A')
        s = self.summary()
        self.assertEqual(('paused', 'paused'), (s['stops']['A']['code'], s['stop']))
        self.call('resume_project', person='SIM-owner', quote='SIMULATED: 继续吧', reason='SIM 复核完')
        self.launch('A')

    def test_inputs_changed_during_the_run_mark_the_result_for_the_dispatcher(self):
        rid = self.launch('A')
        (self.root / 'input.md').write_text('SIMULATED input v2')
        self.hand_over('A')
        self.exit(rid)
        self.assertEqual('stale', self.summary()['stops']['A']['code'])

    def test_every_open_task_has_one_stop_reason(self):
        self.task('C', owner='product-002', executor=None, parent='A', actor='product-001')
        self.task('D', parent='A', actor='product-001', owner='product-002', executor='product-002', dependencies=['C'])
        s = self.summary()
        open_ids = {t['id'] for t in pm.execute(self.root, {'op': 'status'})['tasks'] if t['state'] not in pm.TERMINAL}
        self.assertEqual(open_ids, set(s['stops']))
        self.assertEqual({'A': 'ready', 'B': 'deps', 'C': 'derive', 'D': 'deps'}, {k: v['code'] for k, v in s['stops'].items()})
        self.assertTrue(all(v['code'] in pm.platform.STOPS for v in s['stops'].values()))
        self.assertEqual([('start', 'A'), ('derive', 'C')], [(a['kind'], a['task']) for a in s['actions']])

    def test_a_configured_profession_is_not_a_missing_expert(self):
        with self.assertRaisesRegex(pm.TaskError, 'in the confirmed instance configuration'):
            self.call('gap_open', task_ids=['A'], domain='quality-engineering', kind='not_set_up', why='SIM 需要验收', qualification='SIM 测试', risk='F2')

    def test_views_link_project_files_relatively(self):
        (self.root / 'result.md').write_text('SIMULATED result')
        self.call('update', 'product-001', task_id='A', expected_revision=self.t('A')['revision'], changes={'evidence': ['result.md']}, reason='SIM')
        pm.render(self.root)
        page = (self.root / 'management/views/tasks/A.md').read_text()
        self.assertIn('](<../../../result.md>)', page)
        self.assertFalse(any(str(self.root) in f.read_text() for f in (self.root / 'management/views').rglob('*.md')))

    def test_inbox_items_stay_actions_until_the_pm_handles_them(self):
        self.call('inbox', 'PM', id='IN-1', kind='request', text='SIM 加一个导出功能', person='SIM-owner', quote='SIMULATED: 加个导出')
        self.assertEqual('inbox', self.summary()['actions'][0]['kind'])
        self.call('inbox_done', id='IN-1', note='SIM 记入需求变更')
        self.assertNotIn('inbox', [a['kind'] for a in self.summary()['actions']])

    def test_rework_past_the_cap_needs_a_person_for_a_pm_task(self):
        for round_ in range(4):  # the first run, then three reworks: the third is past the cap of 2
            if round_:
                t = self.t('A')
                self.call('review', task_id='A', expected_revision=t['revision'], outcome='failed', criteria_checked=t['criteria'], evidence=['SIM'], cause='execution')
                self.call('transition', task_id='A', expected_revision=self.t('A')['revision'], state='planned', reason='SIM 返工')
            if round_ == 3:
                with self.assertRaisesRegex(pm.TaskError, 'exceeds the cap of 2'):
                    self.launch('A', note='SIM 第 3 次')
                self.assertEqual('cap', self.summary()['stops']['A']['code'])
                rid = self.launch('A', note='SIM 第 3 次', escalation={'decided_by': 'SIM-owner', 'note': 'SIM 换做法', 'quote': 'SIMULATED: 再改一次'})
            else:
                rid = self.launch('A', **({'note': 'SIM 返工'} if round_ else {}))
            self.hand_over('A')
            self.exit(rid)
        rework = self.t('A')['rework']
        self.assertEqual((3, 'SIM-owner'), (rework['count'], rework['escalation']['decided_by']))

    def test_reassignment_past_the_cap_needs_someone_above_the_dispatcher(self):
        self.task('C', owner='product-002', executor='product-002', parent='A', actor='product-001')
        for i, to in enumerate(['product-003', 'product-002', 'product-003']):
            fields = dict(task_id='C', expected_revision=self.t('C')['revision'], to=to, reason_kind='executor_unable', note='SIM ' + str(i))
            if i == 2:
                with self.assertRaisesRegex(pm.TaskError, 'reassign 3 exceeds the cap of 2'):
                    self.call('reassign', 'product-001', **fields)
                with self.assertRaisesRegex(pm.TaskError, 'from above the dispatcher'):
                    self.call('reassign', 'product-001', escalation={'decided_by': 'product-001', 'note': 'SIM'}, **fields)
                fields['escalation'] = {'decided_by': 'PM', 'note': 'SIM PM 同意再换一次'}
            self.call('reassign', 'product-001', **fields)
        self.assertEqual(('product-003', 3), (self.t('C')['executor'], self.t('C')['reassigned']))


class Commands(Project, unittest.TestCase):
    def setUp(self):
        super().setUp()
        for name, source in [('stub_worker.py', WORKER), ('stub_pm.py', PMSTUB)]:
            (self.root / name).write_text('TOOLS = ' + repr(str(TOOLS)) + '\n' + source)
        self.plan({})
        py = sys.executable
        (self.root / 'management/runtime/platform.json').write_text(json.dumps({
            'launch': [py, '-B', str(self.root / 'stub_worker.py'), '--session', '{session}', '--model', '{model}'],
            'pm': {'launch': [py, '-B', str(self.root / 'stub_pm.py'), '--session', '{session}'],
                   'resume': [py, '-B', str(self.root / 'stub_pm.py'), '--resume', '{session}']},
            'notify': [py, '-c', 'import sys; open("notified.txt", "a").write(sys.argv[1] + "\\n")', '{message}'],
            'models': {'SIM-big': 'sim-big-host-name'}, 'check_seconds': 5}))

    def plan(self, data):
        (self.root / 'stub-plan.json').write_text(json.dumps(data))

    def tool(self, name, *args):
        r = subprocess.run([sys.executable, '-B', str(TOOLS / name), '--project', str(self.root), *args], capture_output=True, text=True)
        return json.loads(r.stdout.strip().splitlines()[-1] if name == 'timer.py' else r.stdout)

    def records(self):
        db = pm.connect(self.root, readonly=True)
        try:
            return pm.integrity.records(db, 'launch')
        finally:
            db.close()

    def wait(self, condition, seconds=60, tick=None):
        end = time.time() + seconds
        while time.time() < end:
            if tick:
                tick()
            if condition():
                return True
            time.sleep(0.5)
        logs = {str(f.relative_to(self.root)): f.read_text()[-1500:] for f in self.root.glob('management/**/*.log')}
        self.fail('condition not reached in ' + str(seconds) + ' s\n' + json.dumps({'continue': self.summary(), 'logs': logs}, ensure_ascii=False, indent=1)[:6000])

    def test_the_launch_command_runs_the_host_command_and_records_the_exit(self):
        out = self.tool('launch.py', '--task', 'A', '--event-id', 'E1')
        rid = out['record']['id']
        self.assertEqual('sim-big-host-name', out['record']['model'])  # the configured model, as passed to the host
        self.wait(lambda: self.records()[rid]['state'] == 'exited')
        self.assertEqual(('waiting_review', 0), (self.t('A')['state'], self.records()[rid]['exit_code']))
        self.assertTrue((self.root / out['packet']).is_file() and (self.root / self.records()[rid]['log']).is_file())
        self.assertNotIn(str(self.root), (self.root / out['packet']).read_text())  # the packet names project-relative paths only
        again = self.tool('launch.py', '--task', 'A', '--event-id', 'E1')
        self.assertTrue(again['repeated'])
        self.assertEqual(1, len(self.records()))

    def test_stopping_a_run_ends_its_process_and_records_it(self):
        self.plan({'A': 'sleep'})
        rid = self.tool('launch.py', '--task', 'A')['record']['id']
        time.sleep(1)
        self.tool('launch.py', '--stop', rid, '--reason', 'SIM 等太久')
        self.assertEqual('lost', self.records()[rid]['state'])
        self.assertEqual('blocked', self.t('A')['state'])

    def test_the_timer_starts_b_after_a_without_anyone_saying_continue(self):
        def tick():
            self.tool('timer.py', '--once')
        self.wait(lambda: self.t('B')['state'] == 'done', seconds=90, tick=tick)
        self.assertEqual({'A', 'B'}, {r['task_id'] for r in self.records().values()})
        log = (self.root / 'management/runtime/timer.log').read_text()
        self.assertGreaterEqual(log.count('PM session'), 2)
        self.assertEqual('done', self.summary()['stop'])

    def test_the_timer_leaves_a_working_pm_alone_and_stops_a_stuck_one(self):
        self.plan({'pm': 'hang'})
        platform = json.loads((self.root / 'management/runtime/platform.json').read_text())
        platform['pm_timeout_minutes'] = 0.05
        (self.root / 'management/runtime/platform.json').write_text(json.dumps(platform))
        self.assertEqual('pm_woken', self.tool('timer.py', '--once')['result'])
        self.assertEqual('pm_working', self.tool('timer.py', '--once')['result'])
        time.sleep(4)
        self.tool('timer.py', '--once')
        self.assertIn('stopped; the next wake starts a new session', (self.root / 'management/runtime/timer.log').read_text())

    def test_the_timer_tells_the_person_when_work_waits_for_them(self):
        self.call('update', 'product-001', task_id='A', expected_revision=self.t('A')['revision'], changes={'human_required': True}, reason='SIM 需要人审',
                  scope_authorization='SIM')
        def tick():
            self.tool('timer.py', '--once')
        self.wait(lambda: (self.root / 'notified.txt').is_file(), seconds=90, tick=tick)
        self.assertIn('需要你处理', (self.root / 'notified.txt').read_text())


if __name__ == '__main__':
    unittest.main()
