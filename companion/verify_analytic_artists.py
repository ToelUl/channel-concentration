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

    def finite_kf(h, gamma, yh, yg, size):
        """Direct NS-mode response from the analytic gradient, outside renderer."""
        momenta = (2*np.arange(size//2, dtype=float)+1)*math.pi/size
        sine, gap = np.sin(momenta), h-np.cos(momenta)
        denominator = gap*gap+(gamma*sine)**2
        response = (yh*(-gamma*sine)+yg*(gap*sine))**2/(4*denominator**2)
        return float(np.sum(response*response)/np.sum(response)**2)

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
        n = np.arange(5, dtype=float)
        ladder = (8/math.pi**2)/(2*n+1)**2
        check('Fig1 TFIM and two XX soft-ladder bar heights',
              [bar['height'] for bar in axes[1]['bars']],
              np.concatenate((ladder, ladder/2, ladder/2)))

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
        mu_grid = np.linspace(-6.0, 6.0, 61)
        for index, size in enumerate((512, 2048, 8192, 32768), start=2):
            markers = axes[0]['lines'][index]
            check(f'Fig2 L={size} marker mu grid', markers['x'], mu_grid)
            check(f'Fig2 L={size} finite-size marker series', markers['y'],
                  [finite_kf(1+mu*math.pi/size, 1.0, 1.0, 0.0, size)
                   for mu in mu_grid])

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
        w_grid = np.array((0.25, 0.5, 1.0, 2.0, 4.0, 8.0, 15.0, 25.0, 45.0))
        for index, size in enumerate((4096, 16384, 65536)):
            field_markers, anisotropy_markers = axes[1]['lines'][3+2*index:5+2*index]
            check(f'Fig3 L={size} field marker w grid', field_markers['x'], w_grid)
            check(f'Fig3 L={size} anisotropy marker w grid',
                  anisotropy_markers['x'], w_grid)
            check(f'Fig3 L={size} field finite-size marker series',
                  field_markers['y'],
                  [finite_kf(1.0, w*math.pi/size, 1.0, 0.0, size)
                   for w in w_grid])
            check(f'Fig3 L={size} anisotropy finite-size marker series',
                  anisotropy_markers['y'],
                  [finite_kf(1.0, w*math.pi/size, 0.0, 1.0, size)
                   for w in w_grid])

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
        half_angles = np.linspace(0, math.pi, 241)
        near_values = np.array([finite_kf(1.05, 0.05, math.cos(angle),
                                          math.sin(angle), 2000)
                                for angle in half_angles])
        near_normalized = near_values/np.max(near_values)
        near_angles = np.r_[half_angles[:-1], half_angles[:-1]+math.pi, 0.0]
        near_radii = np.r_[near_normalized[:-1], near_normalized[:-1],
                           near_normalized[0]]
        check('Fig6 near-Lifshitz full polar angle grid', axes[1]['lines'][0]['x'],
              near_angles)
        check('Fig6 near-Lifshitz full polar radius', axes[1]['lines'][0]['y'],
              near_radii)

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
        weights = (np.sin(momenta)/(2*(1-np.cos(momenta))**2
                   +2*np.sin(momenta)**2))**2
        # The expression above is the critical-field derivative weight,
        # algebraically independent of the renderer's theta-gradient helper.
        check('FigS1 normalized quadratic weight series',
              axes[0]['lines'][0]['y'], (weights/np.sum(weights))[:100])
        for line, delta in zip(axes[0]['lines'][1:], (0.0005, 0.0015, 0.003)):
            final = np.arctan2(np.sin(momenta), 1+delta-np.cos(momenta))
            probability = np.sin((final-initial)/2)**2
            check(f'FigS1 delta={delta} normalized excitation weight series',
                  line['y'], (probability/np.sum(probability))[:100])

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
