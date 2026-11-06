"""Same kit as tests/kit.py."""
import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location('matrix_test_kit', Path(__file__).resolve().parents[1] / 'kit.py')
_kit = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_kit)
KIT = _kit.KIT
