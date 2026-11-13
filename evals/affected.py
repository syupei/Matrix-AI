#!/usr/bin/env python3
"""Which cases a change touches: those that read a changed file, and those without a record of what they read.

  affected.py --run <previous run.json> --old <old built kit> --new <new built kit>

Prints the cases to run again and the cases whose previous replies may be carried over (assemble_run.py --reuse).
A case without a verifiable trace-derived read_set must rerun; directory scopes cover new files too.
"""
import argparse
import json
from pathlib import Path
from read_records import record_reads,intersects


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--run', type=Path, required=True); ap.add_argument('--old', type=Path, required=True); ap.add_argument('--new', type=Path, required=True)
    a = ap.parse_args()
    old = json.loads((a.old / 'MANIFEST.json').read_text())['files']
    new = json.loads((a.new / 'MANIFEST.json').read_text())['files']
    changed = {k for k in set(old) | set(new) if old.get(k) != new.get(k)}
    rerun, carry = {}, []
    for case in json.loads(a.run.read_text())['cases']:
        read = record_reads(a.run,case,old)
        hit = intersects(read,changed)
        if hit or not read['complete'] or case.get('read_set')!=read:
            rerun[case['id']] = hit[:5] or ['no record of what it read']
        else:
            carry.append(case['id'])
    print(json.dumps(dict(changed_files=len(changed), rerun=rerun, carry=sorted(carry)), ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
