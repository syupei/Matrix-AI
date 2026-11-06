"""The kit under test: MATRIX_TEST_KIT (set by tools/production.py), else a package built from src/ into a temporary folder.

The source is grouped by layer and differs from the package layout, so tests always read the package layout."""
import importlib.util, os, tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def _kit():
    if os.environ.get('MATRIX_TEST_KIT'):
        return Path(os.environ['MATRIX_TEST_KIT'])
    spec = importlib.util.spec_from_file_location('matrix_production', REPO / 'tools/production.py')
    prod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(prod)
    package, _, _ = prod.build(Path(tempfile.mkdtemp(prefix='matrix-kit-')))
    os.environ['MATRIX_TEST_KIT'] = str(package)
    return package


KIT = _kit()
