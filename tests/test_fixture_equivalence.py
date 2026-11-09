"""Whether two builds of a fixture project count as the same (evals/fixture_equivalence.py)."""
import importlib.util, sqlite3, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('fixture_equivalence', ROOT / 'evals/fixture_equivalence.py')
fe = importlib.util.module_from_spec(spec); spec.loader.exec_module(fe)


def project(stamp, text='ready'):
    d = Path(tempfile.mkdtemp(prefix='fx-test-'))
    (d / 'kit').mkdir(); (d / 'kit/ignored.md').write_text(stamp)
    (d / 'management').mkdir()
    (d / 'management/view.md').write_text(f'read at {stamp} from {d}/management: {text}')
    con = sqlite3.connect(d / 'management/tasks.sqlite3'); con.execute('create table e(at text, what text)')
    con.execute('insert into e values (?, ?)', (stamp, text)); con.commit(); con.close()
    return d


class FixtureEquivalenceTests(unittest.TestCase):
    def test_builds_differing_only_in_time_and_folder_are_the_same(self):
        self.assertEqual(fe.digest(project('2026-11-05T10:00:00Z')), fe.digest(project('2026-11-09T21:30:05.123+08:00')))

    def test_a_different_project_is_not(self):
        self.assertNotEqual(fe.digest(project('2026-11-05T10:00:00Z')), fe.digest(project('2026-11-05T10:00:00Z', 'blocked')))


if __name__ == '__main__':
    unittest.main()
