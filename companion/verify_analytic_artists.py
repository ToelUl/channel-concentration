"""Bind selected analytic figure coordinates to independent finite-size oracles."""
from __future__ import annotations

import csv
import argparse
import json
import math
from pathlib import Path

import numpy as np
from scipy.special import zeta


def verify_analytic_artists(plot_dir: Path, data: Path, selectors=None) -> dict:
    selected = {'1', '2', '3', '6', 'S1'} if selectors is None else (
        set(selectors) & {'1', '2', '3', '6', 'S1'})
    checks = []

    def read(selector):
        return json.loads((plot_dir/f'{selector}.json').read_text(encoding='utf-8'))

    def check(name, actual, expected, *, rtol=2e-11, atol=2e-11):
        left, right = np.asarray(actual, dtype=float), np.asarray(expected, dtype=float)
        passed = left.shape == right.shape and bool(np.allclose(left, right,
                                                               rtol=rtol, atol=atol))
        checks.append({'check': name, 'count': int(left.size), 'passed': passed})

    def phi(mu):
        odd = np.arange(1, 100001, 2, dtype=float)
        denom = np.sum(odd**2/(odd**2+mu*mu)**2)
        numer = np.sum(odd**4/(odd**2+mu*mu)**4)
        return float(numer/denom**2)

    def psi(w):
        odd = np.arange(1, 100001, 2, dtype=float)
        denom = np.sum(odd**(-2)/(odd**2+4*w*w)**2)
        numer = np.sum(odd**(-4)/(odd**2+4*w*w)**4)
        return float(numer/denom**2)

    if '1' in selected:
        axes = read('1')
        total, concentration = axes[0]['lines'], axes[2]['lines']
        sizes = np.asarray(total[0]['x'], dtype=float)
        tfim_p2 = sizes*(sizes-1)/32
        tfim_p4 = sizes*(sizes-1)*(sizes*sizes+sizes-3)/1536
        xx_p2 = sizes*(sizes-2)/16
        xx_p4 = sizes*(sizes-2)*(sizes*sizes+2*sizes-12)/768
        check('Fig1 TFIM closed P2 coordinates', total[0]['y'], tfim_p2)
        check('Fig1 XX closed P2 coordinates', total[1]['y'], xx_p2)
        check('Fig1 TFIM closed K coordinates', concentration[0]['y'], tfim_p4/tfim_p2**2)
        check('Fig1 XX closed K coordinates', concentration[1]['y'], xx_p4/xx_p2**2)

    if '2' in selected:
        axes = read('2')
        scaling = axes[0]['lines'][0]
        envelope = axes[1]['lines'][0]
        indices = (0, len(scaling['x'])//2, len(scaling['x'])-1)
        check('Fig2 Phi curve selected coordinates',
              [scaling['y'][i] for i in indices],
              [phi(scaling['x'][i]) for i in indices])
        indices = (0, len(envelope['x'])//2, len(envelope['x'])-1)
        powers = [envelope['x'][i] for i in indices]
        expected = [float((1-2**(-2*p))*zeta(2*p, 1) /
                          ((1-2**(-p))*zeta(p, 1))**2) for p in powers]
        check('Fig2 odd-ladder envelope selected coordinates',
              [envelope['y'][i] for i in indices], expected)

    if '3' in selected:
        axes = read('3')
        anisotropy, field = axes[1]['lines'][:2]
        indices = (0, len(anisotropy['x'])//2, len(anisotropy['x'])-1)
        check('Fig3 anisotropy scaling selected coordinates',
              [anisotropy['y'][i] for i in indices],
              [phi(2*anisotropy['x'][i]) for i in indices])
        check('Fig3 field scaling selected coordinates',
              [field['y'][i] for i in indices],
              [psi(field['x'][i]) for i in indices])

    if '6' in selected:
        axes = read('6')
        with (data/'xy_directional_scan.csv').open(newline='', encoding='utf-8') as handle:
            archived = list(csv.DictReader(handle))
        if len(archived) != 241:
            raise ValueError('Fig6 archived scan must contain 241 samples')
        curve = axes[0]['lines'][0]
        check('Fig6 archived full semicircle angle coordinates', curve['x'][:241],
              [float(row['phi']) for row in archived], atol=1e-14)
        maximum = max(float(row['K_F']) for row in archived)
        check('Fig6 archived full semicircle radius coordinates', curve['y'][:241],
              [float(row['K_F'])/maximum for row in archived])

    if 'S1' in selected:
        axes = read('S1')
        ratio = axes[1]['lines'][0]
        size = 256
        momenta = (2*np.arange(size//2)+1)*math.pi/size
        initial = np.arctan2(np.sin(momenta), 1-np.cos(momenta))
        indices = (0, len(ratio['x'])//2, len(ratio['x'])-1)
        expected = []
        for i in indices:
            final = np.arctan2(np.sin(momenta), 1+ratio['x'][i]-np.cos(momenta))
            probability = np.sin((final-initial)/2)**2
            expected.append(float(np.sum(probability**2)/np.sum(probability)**2))
        check('FigS1 weak-quench selected ratio coordinates',
              [ratio['y'][i] for i in indices], expected, rtol=2e-9, atol=2e-9)

    if not all(row['passed'] for row in checks):
        raise ValueError('Analytic rendered coordinates differ from independent oracles: '
                         + json.dumps(checks))
    return {'status': 'PASS', 'checked_figures': sorted(selected), 'checks': checks,
            'scope': 'Selected analytic coordinates against closed forms, archived scan, '
                     'or independent finite-mode formulas; not a proof or artwork approval.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plot-dir', type=Path, required=True)
    parser.add_argument('--data-root', type=Path,
                        default=Path(__file__).resolve().parents[1]/'baseline/data/figure-inputs')
    parser.add_argument('--fig', nargs='+', choices=('1', '2', '3', '6', 'S1'))
    args = parser.parse_args()
    try:
        print(json.dumps(verify_analytic_artists(args.plot_dir, args.data_root,
                                                 args.fig), indent=2))
    except (ValueError, FileNotFoundError, IndexError, KeyError) as error:
        parser.exit(1, str(error)+'\n')
