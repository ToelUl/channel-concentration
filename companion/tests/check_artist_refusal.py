"""Tamper with fresh plot-data exports and require both artist checks to fail."""
import argparse
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from companion.verify_analytic_artists import verify_analytic_artists
from companion.verify_artists import verify_artists


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--plot-dir', type=Path, default=ROOT/'build/companion/plot-data')
args = parser.parse_args()
ORIGINAL = args.plot_dir
DATA = ROOT/'baseline/data/figure-inputs'


def expect_refusal(selector, verifier):
    with tempfile.TemporaryDirectory() as temporary:
        path = Path(temporary)/f'{selector}.json'
        value = json.loads((ORIGINAL/f'{selector}.json').read_text(encoding='utf-8'))
        value[0]['lines'][0]['y'][0] += 0.1
        path.write_text(json.dumps(value), encoding='utf-8')
        try:
            verifier(Path(temporary), DATA, {selector})
        except ValueError:
            return
        raise AssertionError(f'Figure {selector} corrupted coordinates were accepted')


expect_refusal('1', verify_analytic_artists)
expect_refusal('4', verify_artists)
print('PASS: seeded analytic and interacting coordinate changes were refused')
