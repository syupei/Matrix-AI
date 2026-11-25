#!/usr/bin/env python3
"""Product entry for the tone contract checker shared with stage transitions."""

from pathlib import Path
import runpy


if __name__ == '__main__':
    relative = Path('matrix/base/tools/tone_contract.py')
    for directory in Path(__file__).resolve().parents:
        tool = directory / relative
        if tool.is_file():
            runpy.run_path(str(tool), run_name='__main__')
            break
    else:
        raise SystemExit('matrix/base/tools/tone_contract.py is missing from the installed package')
