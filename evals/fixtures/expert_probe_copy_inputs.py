"""Copy the prebuilt inputs in the imported-expert probe and print the verbatim quote."""

import json
from pathlib import Path
import shutil


SCENE = 'design/preview.html'
SCREENSHOT = 'design/preview.png'
REVIEW_SOURCE = 'review-input.md'
REVIEW_OUTPUT = 'product/reviews/合成P-1审阅输入.md'
COPIES = ((SCENE, SCENE), (SCREENSHOT, SCREENSHOT), (REVIEW_SOURCE, REVIEW_OUTPUT))


def quote(source):
    """The fixture puts its original confirmation utterance on the last line."""
    return (source / REVIEW_SOURCE).read_bytes().decode('utf-8').splitlines()[-1]


def copy_inputs(source, public):
    for name, relative in COPIES:
        destination = public / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / name, destination)
    return {'source': REVIEW_OUTPUT, 'quote': quote(source)}


if __name__ == '__main__':
    print(json.dumps(copy_inputs(Path(__file__).resolve().parent, Path.cwd() / 'public'), ensure_ascii=False))
