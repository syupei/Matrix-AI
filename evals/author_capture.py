"""An author command requesting one capture from the evaluation-only local broker."""
import argparse
import json
from pathlib import Path
import time
import uuid


def request(root, preview, output, state, artifacts=None, timeout=60):
    queue = root / '_evaluation/capture-requests'
    if not queue.is_dir():
        raise ValueError('the evaluation capture broker is unavailable')
    identity = uuid.uuid4().hex
    destination = queue / (identity + '.request.json')
    pending = queue / (identity + '.request.pending')
    with pending.open('x') as stream:
        stream.write(json.dumps({'preview': preview, 'output': output, 'state': state,
                                 'artifacts': artifacts or [preview]}) + '\n')
    pending.replace(destination)
    result = queue / (identity + '.result.json')
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if result.is_file():
            return json.loads(result.read_bytes())
        time.sleep(0.1)
    raise TimeoutError('capture broker did not respond before the deadline')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--preview', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--state', required=True, help='the representative state the author is requesting')
    parser.add_argument('--artifact', action='append', help='additional current artifact to bind, repeat as needed')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    receipt = request(root, args.preview, args.output, args.state, args.artifact)
    print(json.dumps(receipt, ensure_ascii=False))
    return 0 if receipt.get('status') == 'captured' else 1


if __name__ == '__main__':
    raise SystemExit(main())
