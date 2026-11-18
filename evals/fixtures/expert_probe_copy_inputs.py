"""Copy the prebuilt inputs in the imported-expert probe and print the verbatim quote."""

import json
import argparse
import hashlib
from pathlib import Path
import shutil


SCENE = 'design/preview.html'
SCREENSHOT = 'design/preview.png'
CAPTURE = 'design/preview.capture.json'
REVIEW_SOURCE = 'review-input.md'
REVIEW_OUTPUT = 'product/reviews/合成P-1审阅输入.md'
COPIES = ((SCENE, SCENE), (SCREENSHOT, SCREENSHOT), (CAPTURE, CAPTURE), (REVIEW_SOURCE, REVIEW_OUTPUT))


def quote(source):
    """The fixture puts its original synthetic scenario utterance on the last line."""
    return (source / REVIEW_SOURCE).read_bytes().decode('utf-8').splitlines()[-1]


def copy_inputs(source, public):
    for name, relative in COPIES:
        destination = public / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / name, destination)
    return check_inputs(source, public)


def check_inputs(source, public):
    """Check the copies in-place without repairing an author's changed input."""
    files = {}
    for name, relative in COPIES:
        target = public / relative
        if not target.is_file() or target.is_symlink() or target.read_bytes() != (source / name).read_bytes():
            raise ValueError('copied synthetic input changed: ' + relative)
        files[relative] = hashlib.sha256(target.read_bytes()).hexdigest()
    return {'source': REVIEW_OUTPUT, 'quote': quote(source), 'copied_inputs': files, 'unchanged': True}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    operation = check_inputs if args.check else copy_inputs
    print(json.dumps(operation(Path(__file__).resolve().parent, Path.cwd() / 'public'), ensure_ascii=False))
