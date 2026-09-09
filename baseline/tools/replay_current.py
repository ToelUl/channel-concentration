"""Restore bundled committed inputs and call unchanged strict current readers."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from verify_release import BUNDLE, digest, verify


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--analysis', required=True, choices=['nnn-ranked', 'potts-fss', 'potts-ranked', 'potts-7over5', 'projector-enclosures'])
    parser.add_argument('--workspace', required=True, type=Path)
    args = parser.parse_args()
    verify()
    import cc_repro
    from cc_repro.resources import prepare_workspace
    required = '0.5.0.dev0' if args.analysis in ('potts-fss', 'potts-ranked') else '0.5.2.dev0'
    if cc_repro.__version__ != required:
        raise ValueError('This route requires cc-repro ' + required)
    workspace = args.workspace.absolute()
    if workspace == BUNDLE or BUNDLE in workspace.parents:
        raise ValueError('Use a workspace outside the immutable bundle')
    if workspace.exists():
        raise FileExistsError('Use an empty new workspace; existing work is never overwritten')
    for name in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS'):
        os.environ[name] = '1'
    os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
    project, _ = prepare_workspace(workspace)
    model = 'nnn' if args.analysis == 'nnn-ranked' else 'potts'
    source = BUNDLE / 'data' / model / 'runs'
    shutil.copytree(source, project / 'build/runs', dirs_exist_ok=True)
    input_run = 'a1-publication' if model == 'nnn' else 'a1-fixed-grid'
    command = [sys.executable, '-B', '-m', 'cc_repro', 'postprocess', '--workspace', str(workspace),
               '--run-id', 'public-check', '--analysis', args.analysis, '--source', 'current', '--timeout', '600']
    if args.analysis != 'projector-enclosures':
        command += ['--input-run', input_run]
    if args.analysis in ('potts-7over5', 'projector-enclosures'):
        command += ['--ladder-run', 'a1-ladder']
    if args.analysis == 'potts-7over5':
        command += ['--p2-run', 'a1-p2']
    subprocess.run(command, check=True, timeout=660, cwd=workspace)
    names = {
        'nnn-ranked': ['nnn_ranked_distribution_convergence.csv'],
        'potts-fss': ['potts_outcome_aware_fss.csv', 'potts_outcome_aware_fit_audit.csv'],
        'potts-ranked': ['potts_L14_certified_ranked_weights.csv'],
        'potts-7over5': ['potts_theory_guided_7over5_fit_summary.csv', 'potts_scaled_P2_7over5.csv'],
        'projector-enclosures': [],
    }[args.analysis]
    comparisons = []
    for name in names:
        actual = project / 'build/runs/public-check/data/reproducibility' / name
        expected = BUNDLE / 'data/figure-inputs' / name
        if digest(actual) != digest(expected):
            raise ValueError('Numerical output differs from frozen baseline: ' + name)
        comparisons.append({'file': name, 'comparison': 'byte-identical', 'sha256': digest(actual)})
    if args.analysis == 'projector-enclosures':
        actual = json.loads((project / 'build/runs/public-check/projector-response-enclosures.json').read_text())
        expected = json.loads((BUNDLE / 'data/potts-derived/projector-response-enclosures.json').read_text())
        for key in ('sizes', 'L14_ranks', 'premises', 'classification', 'spectral_completeness_independently_proved'):
            if actual[key] != expected[key]:
                raise ValueError('Enclosure result or premise differs: ' + key)
        comparisons.append({'file': 'projector-response-enclosures.json', 'comparison': 'exact numeric structures and premises'})
    # Check restored original inputs after consumption; analysis outputs are separate.
    for original in source.rglob('*'):
        if original.is_file() and digest(original) != digest(project / 'build/runs' / original.relative_to(source)):
            raise ValueError('An original input changed during replay')
    result = {'status': 'PASS', 'analysis': args.analysis, 'no_new_eigensolves': True, 'original_inputs_unchanged': True, 'comparisons': comparisons}
    (workspace / 'public-replay-check.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
