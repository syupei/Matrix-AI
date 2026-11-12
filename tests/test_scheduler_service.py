"""Print-only service generation and heartbeat boundaries. No system service is installed."""
from datetime import datetime, timedelta, timezone
import importlib.util
import json
from pathlib import Path
import plistlib
import shlex
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from kit import KIT

TOOLS = KIT / 'matrix/orchestration/tools'
def load(name):
    s = importlib.util.spec_from_file_location(name, TOOLS / (name + '.py'))
    m = importlib.util.module_from_spec(s); s.loader.exec_module(m)
    return m
service, scheduler, pm = load('scheduler_service'), load('scheduler'), load('pm_tasks')


class ServiceTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve() / 'project with space % $ 雨'

    def test_generation_writes_nothing(self):
        for kind in ['launchd', 'systemd', 'cron']:
            data = service.plan(self.root, kind)
            self.assertTrue(data['files']); self.assertTrue(data['stop_commands'])
        self.assertFalse(self.root.exists())

    def test_launchd_roundtrips_argument_paths(self):
        data = service.plan(self.root, 'launchd', 15)
        plist = plistlib.loads(next(iter(data['files'].values())).encode())
        args = plist['ProgramArguments']
        self.assertEqual(args[args.index('--project') + 1], str(self.root))
        self.assertEqual(plist['WorkingDirectory'], str(self.root))
        self.assertTrue(plist['KeepAlive']); self.assertTrue(plist['RunAtLoad'])

    def test_systemd_escapes_specifiers_and_environment_expansion(self):
        unit = next(iter(service.plan(self.root, 'systemd')['files'].values()))
        self.assertIn('%%', unit); self.assertIn('$$', unit)
        self.assertIn('Restart=always', unit)
        self.assertIn('"--project"', unit)

    def test_cron_encodes_project_path_and_sets_real_interval(self):
        data = service.plan(self.root, 'cron', 5)
        line = next(iter(data['files'].values()))
        self.assertNotIn(str(self.root), line)
        self.assertEqual(data['check_seconds'], 60)
        # Execute only the generated Python decoder with os.execv replaced, never the scheduler.
        cmd = line.split(' ', 5)[5].split(' # ')[0]
        argv = shlex.split(cmd)
        seen = []
        with patch('os.execv', side_effect=lambda exe, args: seen.append(args)):
            exec(argv[2], {})
        self.assertIn(str(self.root), seen[0])
        self.assertEqual(seen[0][-3:], ['--once', '--interval', '60'])

    def test_generated_writer_is_valid_python_and_shell_quoted(self):
        for kind in ['launchd', 'systemd', 'cron']:
            args = shlex.split(service.plan(self.root, kind)['install_commands'][0])
            self.assertEqual(args[1], '-c'); compile(args[2], '<generated>', 'exec')

    def test_distinct_projects_have_distinct_service_ids(self):
        self.assertNotEqual(service.plan(self.root, 'cron')['label'], service.plan(self.root / 'other', 'cron')['label'])

    def test_invalid_intervals_and_linebreak_paths_rejected(self):
        for value in [0, 4, True, '60']:
            with self.assertRaises(ValueError): service.plan(self.root, 'launchd', value)
        with self.assertRaises(ValueError): service.plan(self.root / 'bad\npath', 'systemd')

    def test_cli_service_needs_no_database_and_does_not_create_project(self):
        p = subprocess.run([sys.executable, str(TOOLS / 'scheduler.py'), '--project', str(self.root), '--service', 'launchd'], capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr); self.assertEqual(json.loads(p.stdout)['service'], 'launchd')
        self.assertFalse(self.root.exists())

    def heartbeat(self, age, result='idle', interval=60):
        at = datetime.now(timezone.utc)
        path = self.root / service.HEARTBEAT; path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(dict(checked_at=(at - timedelta(seconds=age)).isoformat(), check_seconds=interval, result=result)))
        return service.health(self.root, at)

    def test_missing_heartbeat_is_unknown(self):
        self.assertEqual(service.health(self.root)['state'], 'unknown')

    def test_expiry_is_strictly_more_than_two_intervals(self):
        self.assertEqual(self.heartbeat(120)['state'], 'recent')
        self.assertEqual(self.heartbeat(121)['state'], 'stale')
        self.assertIn('可能', self.heartbeat(121)['message'])

    def test_error_and_invalid_heartbeat_are_distinguished(self):
        self.assertEqual(self.heartbeat(2, result='error')['state'], 'error')
        self.assertEqual(self.heartbeat(-60)['state'], 'unknown')
        self.assertEqual(self.heartbeat(3, interval=False)['state'], 'unknown')

    def test_tick_records_success_and_failure_without_real_processes(self):
        self.root.mkdir()
        pm.execute(self.root, dict(op='init', actor='PM', event_id='init', config=dict(project='SIM', pm_actor='PM', authorization='SIM', frontdoor_id='SIM', max_slots=1)))
        (self.root / 'management/runtime/platform.json').write_text('{"launch":["SIM-never-run"]}')
        with patch.object(scheduler, 'advance', return_value='idle'):
            scheduler.tick(self.root, 10)
        self.assertEqual(service.health(self.root)['result'], 'idle')
        with patch.object(scheduler, 'advance', side_effect=ValueError('SIM failure')):
            with self.assertRaises(ValueError): scheduler.tick(self.root, 10)
        self.assertEqual(service.health(self.root)['state'], 'error')

    def test_read_and_refresh_show_stale_without_mutating_tasks(self):
        self.root.mkdir()
        pm.execute(self.root, dict(op='init', actor='PM', event_id='init', config=dict(project='SIM', pm_actor='PM', authorization='SIM', frontdoor_id='SIM', max_slots=1)))
        self.heartbeat(130)
        before = pm.execute(self.root, {'op': 'status'})['revision']
        self.assertEqual(pm.execute(self.root, {'op': 'continue'})['scheduler_health']['state'], 'stale')
        pm.render(self.root)
        self.assertIn('调度器可能已停', (self.root / 'management/views/project.md').read_text())
        self.assertEqual(pm.execute(self.root, {'op': 'status'})['revision'], before)
