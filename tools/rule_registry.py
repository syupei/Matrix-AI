#!/usr/bin/env python3
"""Factory-only rule inventory. Never package decisions or raw evaluation evidence."""
import argparse
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def version(label):
    match = re.match(r'^(?:v)?(\d+)\.(\d+)(?:\D|$)', label)
    return tuple(map(int, match.groups())) if match else None


def inspect_registry(registry, source, suite):
    criteria = {key for case in suite['cases'] for key in case['criteria']}
    report = {'broken': [], 'unchecked': [], 'latest_failures': [],
              'no_evidence_three_versions': [], 'history_insufficient': []}
    rules = registry['rules']
    versions = sorted({version(key) for rule in rules for key in rule['evidence']} - {None})
    seen = set()
    for rule in rules:
        rid = rule['id']
        if rid in seen:
            report['broken'].append(f'{rid}: duplicate rule ID')
        seen.add(rid)
        path = (source / rule['file']).resolve()
        if not path.is_relative_to(source.resolve()) or not path.is_file():
            report['broken'].append(f'{rid}: source file missing or outside source')
        elif not re.search(r'^#+\s*' + re.escape(rule['section']) + r'\s*$',
                           path.read_text(encoding='utf-8'), re.M):
            report['broken'].append(f'{rid}: section missing: {rule["section"]}')
        for key in rule['check']['criteria']:
            if key not in criteria:
                report['broken'].append(f'{rid}: unknown criterion: {key}')
        if not rule['check']['criteria'] and not rule['check']['tools']:
            report['unchecked'].append(rid)
        entries = rule['evidence']
        if entries:
            label = next(reversed(entries))
            if entries[label].get('candidate_zeros'):
                report['latest_failures'].append({'rule': rid, 'evidence': label,
                                                  'failures': entries[label]['candidate_zeros']})
        since = version(rule.get('registered_in', ''))
        history = [v for v in versions if since and v >= since]
        if len(history) < 3:
            report['history_insufficient'].append(rid)
        elif all(not any(version(label) == v and evidence.get('items', 0) > 0
                         for label, evidence in entries.items()) for v in history[-3:]):
            report['no_evidence_three_versions'].append(rid)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--registry', type=Path, required=True)
    parser.add_argument('--comparison', type=Path)
    parser.add_argument('--version')
    args = parser.parse_args()
    registry = json.loads(args.registry.read_text(encoding='utf-8'))
    suite = json.loads((ROOT / 'evals/cases/suite.json').read_text(encoding='utf-8'))
    report = inspect_registry(registry, ROOT / 'src', suite)
    if report['broken']:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1
    if args.comparison:
        # A first-pass score dump or a partial/waived run must not become full evidence.
        import production
        if not args.version:
            parser.error('--comparison requires --version')
        current = json.loads((ROOT / 'package.json').read_text())['package'].split('/')[1]
        if args.version != current:
            parser.error('--version must name the current candidate')
        production.check_evidence(args.comparison.resolve(), production.source_files())
        data = json.loads(args.comparison.read_text(encoding='utf-8'))
        digest = hashlib.sha256(args.comparison.read_bytes()).hexdigest()
        for rule in registry['rules']:
            items = [(cid, key) for cid, case in data['cases'].items()
                     for key in rule['check']['criteria'] if key in case['candidate']]
            rule['evidence'][args.version] = {
                'items': len(items), 'source': str(args.comparison), 'sha256': digest,
                'candidate_hash': data['candidate_hash'], 'kind': 'full-gate-validated',
                **{side + '_pass': sum(data['cases'][cid][side][key] for cid, key in items)
                   for side in ('baseline', 'candidate')},
                'candidate_zeros': [f'{cid}/{key}' for cid, key in items
                                    if data['cases'][cid]['candidate'][key] == 0]}
        args.registry.write_text(json.dumps(registry, ensure_ascii=False, indent=2) + '\n')
        report = inspect_registry(registry, ROOT / 'src', suite)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
