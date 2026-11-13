"""Synthetic project for gap_pm_tax: the shared team project in its plain state.

It is built by team_project.py (same synthetic people, instances and task library, no withdrawal or tax work yet).
The hash of team_project.py is pinned here, so a change there cannot silently change this case.
"""
import hashlib
import importlib.util
from pathlib import Path

TEAM = Path(__file__).resolve().with_name('team_project.py')
TEAM_SHA256 = '141df320809afcee2103443a9390cf0f46c77cc120ae5e2a6982bd3ad0f62969'


def populate(root, case_id):
    if case_id != 'gap_pm_tax':
        raise ValueError('unknown gap fixture case: ' + case_id)
    if hashlib.sha256(TEAM.read_bytes()).hexdigest() != TEAM_SHA256:
        raise ValueError('team_project.py changed; update gap_project.py and the suite')
    spec = importlib.util.spec_from_file_location('team_project_fixture', TEAM)
    team = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(team)
    team.populate(root, 'base_level_answer_code')
