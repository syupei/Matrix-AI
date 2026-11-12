"""Explicit synthetic resource and configured-planning premises; no live approvals or hosts."""
import importlib.util
from pathlib import Path

def populate(root, case_id):
    path=Path(__file__).with_name('project_outcomes.py')
    spec=importlib.util.spec_from_file_location('boundary_seed',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    resource=case_id.startswith('pm_resource_')
    module.populate(root,'pm_resource_queue' if resource else 'pm_project_type')
    (root/'FIXTURE.md').write_text('Isolated synthetic fixture. The seeded PM identity, frontdoor SIM and task store are explicit test configuration, not a live host or actual human approval. No worker instances or sending channels exist. Do not launch agents.\n')
    if not resource:
        (root/'brief.md').write_text('Synthetic mobile turn-based board game. Scripted user confirms product baseline and design review A. Design is entering asset work; engineering intake may be planned in parallel. Runtime workers and live channels are not configured.\n')
        (root/'accepted.txt').unlink()
        for folder,text in [('product','Synthetic product baseline for turn-based mobile board game; confirmed only as stated in scripted user input. Detailed game rules remain outside this planning probe.'),('design','Synthetic review A structure/core interaction source, confirmed only as stated in scripted user input. Asset production is pending; no final visual approval.')]:
            (root/folder).mkdir(exist_ok=True)
            (root/folder/'baseline.md').write_text(text+'\n')
