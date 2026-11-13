"""Pinned pre-model-fit producer for old kits; no live calls or consumer runtime dependency.

The old baseline was prepared by candidate tools, not its own task tool. Merely removing
new JSON fields still changes confirmation records/profiles. Keep that producer fixed
and require fixture_equivalence before carrying any old reply.
"""
import importlib.util
from pathlib import Path
import subprocess
import tempfile

PRODUCER = '733523e092ec61dae844ae7b6eaa96232f1f23cd'
_PACKAGE = None


def package():
    global _PACKAGE
    if _PACKAGE is None:
        repo = Path(__file__).resolve().parents[2]
        root = Path(tempfile.mkdtemp(prefix='matrix-old-producer-'))
        archive = subprocess.run(['git', '-C', str(repo), 'archive', PRODUCER,
                                  'src', 'tools', 'docs', 'package.json'], capture_output=True, check=True).stdout
        subprocess.run(['tar', '-x', '-C', str(root)], input=archive, check=True)
        spec = importlib.util.spec_from_file_location('old_fixture_production', root / 'tools/production.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _PACKAGE, _, _ = module.build(root / 'build')
    return _PACKAGE
