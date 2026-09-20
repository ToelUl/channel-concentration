#!/usr/bin/env python3
"""Run bounded, baseline-external scientific checks for the public companion.

This verifies selected formulas, symmetry representations, and archived-record
semantics. It does not rerun interacting campaigns, alter baseline/, or prove
thermodynamic convergence.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'baseline/data/figure-inputs'
BASELINE = ROOT / 'baseline'
os.environ['OPENBLAS_NUM_THREADS'] = '1'
os.environ['OMP_NUM_THREADS'] = '1'
os.environ['MKL_NUM_THREADS'] = '1'

# Registered ceilings for the finite grids below. The S3 reference run gave
# 0.001089 (Fig. 2, L=2048), 0.000114 (Fig. 3 anisotropy, L=16384), and
# 6.48e-9 (Fig. 3 field, L=16384). These relaxed regression guards are not
# general asymptotic error bounds or manuscript uncertainty estimates.
FIG2_MAX_ERROR_2048 = 0.0025
FIG3_ANISOTROPY_MAX_ERROR_16384 = 0.00025
FIG3_FIELD_MAX_ERROR_16384 = 1e-7


def read_json(path: Path):
    return json.loads(path.read_text(encoding='utf-8'))


def read_csv(path: Path):
    with path.open(newline='', encoding='utf-8') as handle:
        return list(csv.DictReader(handle))


def digest(path: Path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition: bool, name: str):
    if not condition:
        raise ValueError('Scientific contract failed: ' + name)


def near(actual: float, expected: float, tolerance: float, name: str):
    require(math.isfinite(actual) and abs(actual - expected) <= tolerance, name)


def renderer():
    sys.path.insert(0, str(ROOT / 'companion'))
    import run

    run.verify()
    return run.renderer()[0]


def tfim_critical_closed_moments(size: int) -> tuple[float, float, float]:
    """Manuscript NS half-grid P2, P4, and P6, independently of mode sums."""
    p2 = size * (size - 1) / 32
    p4 = size * (size - 1) * (size*size + size - 3) / 1536
    p6 = (size * (size - 1) *
          (2*size**4 + 2*size**3 - 8*size**2 - 8*size + 15) / 122880)
    return p2, p4, p6


def analytic_contracts() -> list[dict]:
    import numpy as np
    from scipy.special import zeta

    mod = renderer()
    checks = []

    # Figure 1: sums from the frozen free-fermion route versus closed forms.
    for size in (16, 32, 64):
        momenta = mod.ns_momenta(size)
        tfim = mod.channel_weights(1.0, 1.0, momenta, 1.0, 0.0)
        xx = mod.channel_weights(0.0, 0.0, momenta, 0.0, 1.0)
        tfim_p2 = size * (size - 1) / 32
        tfim_p4 = size * (size - 1) * (size*size + size - 3) / 1536
        xx_p2 = size * (size - 2) / 16
        xx_p4 = size * (size - 2) * (size*size + 2*size - 12) / 768
        for title, actual, expected in (
            ('TFIM P2', float(np.sum(tfim)), tfim_p2),
            ('TFIM P4', float(np.sum(tfim*tfim)), tfim_p4),
            ('XX P2', float(np.sum(xx)), xx_p2),
            ('XX P4', float(np.sum(xx*xx)), xx_p4),
        ):
            near(actual, expected, 2e-9 * max(1, abs(expected)), f'Fig1 {title} L={size}')
        half = mod.channel_weights(1.0, 1.0, mod.ns_momenta(size//2), 1.0, 0.0)
        xx_prob = np.sort(xx / np.sum(xx))
        half_prob = half / np.sum(half)
        duplicated = np.sort(np.repeat(half_prob/2, 2))
        require(np.allclose(xx_prob, duplicated, rtol=2e-12, atol=2e-12),
                f'Fig1 XX half-size distribution L={size}')
    checks.append({'contract': 'Fig1 closed moments and distribution half-size identity',
                   'cases': 3})

    # Figure 2: exact endpoint, independent finite odd-ladder sums, and the
    # direction of lattice-to-scaling convergence at a fixed small mu grid.
    near(float(mod.KFcrit_p(2.0)), 2/3, 2e-12, 'Fig2 exact envelope p=2')
    near(float(mod.Phi(0.0, nmax=50000)), 2/3, 2e-5,
         'Fig2 finite Phi helper approximates exact endpoint')
    odd = np.arange(1, 200000, 2, dtype=float)
    for power in (1.5, 2.0, 3.0):
        weights = odd**(-power)
        sum_p = float(np.sum(weights))
        sum_2p = float(np.sum(weights*weights))
        first_missing = float(2*len(odd)+1)
        tail_p = first_missing**(-power) + first_missing**(1-power)/(2*(power-1))
        tail_2p = first_missing**(-2*power) + first_missing**(1-2*power)/(2*(2*power-1))
        lower = sum_2p/(sum_p+tail_p)**2
        upper = (sum_2p+tail_2p)/sum_p**2
        closed = float(mod.KFcrit_p(power))
        require(lower-1e-10 <= closed <= upper+1e-10,
                f'Fig2 odd ladder p={power} lies in finite-sum tail bounds')
    errors = []
    for size in (512, 2048):
        observed = [mod.KF_point(1 + mu*math.pi/size, 1.0, (1.0, 0.0), size)
                    for mu in (-2.0, 0.0, 2.0)]
        expected = [float(mod.Phi(mu, nmax=50000)) for mu in (-2.0, 0.0, 2.0)]
        errors.append(max(abs(a-b) for a, b in zip(observed, expected)))
    require(errors[1] < errors[0], 'Fig2 lattice-to-scaling error decreases')
    require(errors[1] < FIG2_MAX_ERROR_2048,
            'Fig2 L=2048 absolute scaling error ceiling')
    checks.append({'contract': 'Fig2 envelope and selected scaling convergence',
                   'errors': errors, 'largest_size_error_ceiling': FIG2_MAX_ERROR_2048})

    # Figure 3: the normalized field response is undefined at the singular
    # exact point, even though a punctured scaling limit exists.
    odd_lambda = lambda power: float((1-2**(-power)) * zeta(power, 1))
    psi_zero = odd_lambda(12)/odd_lambda(6)**2
    near(float(mod.Psi(0.0, nmax=50000)), psi_zero, 2e-5,
         'Fig3 exact Psi endpoint')
    momenta = mod.ns_momenta(64)
    exact_field = mod.channel_weights(1.0, 0.0, momenta, 1.0, 0.0)
    require(float(np.sum(exact_field)) == 0.0,
            'Fig3 exact Lifshitz field P2 vanishes')
    errors = []
    anisotropy_errors = []
    field_errors = []
    for size in (4096, 16384):
        anisotropy_pair = []
        field_pair = []
        for w in (0.5, 2.0):
            gamma = w*math.pi/size
            anisotropy_pair.append(abs(mod.KF_point(1.0, gamma, (0.0, 1.0), size)
                                       - float(mod.Phi(2*w, nmax=50000))))
            field_pair.append(abs(mod.KF_point(1.0, gamma, (1.0, 0.0), size)
                                  - float(mod.Psi(w, nmax=50000))))
        anisotropy_errors.append(max(anisotropy_pair))
        field_errors.append(max(field_pair))
        errors.append(max(anisotropy_errors[-1], field_errors[-1]))
    require(errors[1] < errors[0], 'Fig3 directional scaling error decreases')
    require(anisotropy_errors[1] < FIG3_ANISOTROPY_MAX_ERROR_16384,
            'Fig3 L=16384 anisotropy absolute scaling error ceiling')
    require(field_errors[1] < FIG3_FIELD_MAX_ERROR_16384,
            'Fig3 L=16384 field absolute scaling error ceiling')
    checks.append({'contract': 'Fig3 punctured endpoint and directional scaling',
                   'errors': errors, 'anisotropy_errors': anisotropy_errors,
                   'field_errors': field_errors,
                   'largest_size_error_ceilings': {
                       'anisotropy': FIG3_ANISOTROPY_MAX_ERROR_16384,
                       'field': FIG3_FIELD_MAX_ERROR_16384}})

    # Figure 6: compare the publication grid with a separately archived scan,
    # and test the underlying function, not a mirrored polar drawing.
    archived = read_csv(DATA/'xy_directional_scan.csv')
    require(len(archived) == 241, 'Fig6 archived tangent inventory')
    observed = [mod.KF_point(0.8, 0.5, (math.cos(float(row['phi'])),
                                            math.sin(float(row['phi']))), 2000)
                for row in archived]
    require(np.allclose(observed, [float(row['K_F']) for row in archived],
                        rtol=3e-12, atol=3e-12), 'Fig6 archived full curve')
    for angle in (0.17, 0.83, 1.37):
        y = (math.cos(angle), math.sin(angle))
        base = mod.KF_point(0.8, 0.5, y, 128)
        for candidate in ((3*y[0], 3*y[1]), (-y[0], -y[1]),
                          (math.cos(angle+math.pi), math.sin(angle+math.pi))):
            near(mod.KF_point(0.8, 0.5, candidate, 128), base, 2e-14,
                 'Fig6 tangent scale/sign/period invariant')
    checks.append({'contract': 'Fig6 archived curve and tangent invariants',
                   'archived_points': len(archived)})

    # S1: Bernoulli counting, normalized weak-quench weights, and the
    # critical quadratic-drift coefficient from frozen finite-size moments.
    size = 256
    k = mod.ns_momenta(size)
    x = mod.channel_weights(1.0, 1.0, k, 1.0, 0.0)
    p2, p4, p6 = float(np.sum(x)), float(np.sum(x*x)), float(np.sum(x*x*x))
    closed_p2, closed_p4, closed_p6 = tfim_critical_closed_moments(size)
    for title, actual, expected in (('P2', p2, closed_p2),
                                    ('P4', p4, closed_p4),
                                    ('P6', p6, closed_p6)):
        near(actual, expected, 2e-9 * max(1, abs(expected)),
             f'S1 critical closed {title} L={size}')
    kf = closed_p4/closed_p2**2
    c2 = 6*kf*(closed_p4/closed_p2 - closed_p6/closed_p4)
    c2_direct = 6*(p4/p2**2)*(p4/p2 - p6/p4)
    near(c2_direct, c2, 2e-9 * max(1, abs(c2)),
         f'S1 critical closed c2 L={size}')
    errors = []
    for delta in (0.002, 0.001, 0.0005):
        probabilities = mod.weak_quench_probabilities_h(1.0, 1.0, delta, size)
        mean = float(np.sum(probabilities))
        variance = float(np.sum(probabilities*(1-probabilities)))
        near(mean-variance, float(np.sum(probabilities**2)), 2e-14,
             'S1 Bernoulli counting identity')
        distribution = probabilities/mean
        require(np.max(np.abs(distribution - x/p2)) < 0.003,
                'S1 normalized distribution approaches channel weights')
        stable = float(np.sum(probabilities**2)/mean**2)
        errors.append(abs((stable-kf)/delta**2 - c2))
    require(errors[-1] < errors[0] and errors[-1] < 0.002*abs(c2),
            f'S1 critical quadratic-drift coefficient c2={c2:.8g} errors={errors}')
    checks.append({'contract': 'S1 weak-quench counting and quadratic drift',
                   'closed_coefficient': c2, 'direct_coefficient': c2_direct,
                   'errors': errors})
    return checks


def potts_rank_contract(enclosure: dict) -> dict:
    ranks = enclosure['L14_ranks']
    rows = ranks['rows']
    omitted_upper = float(ranks['mass']['omitted_probability_interval'][1])
    require(len(rows) >= 15 and [row['midpoint_rank'] for row in rows[:15]]
            == list(range(1, 16)), 'Potts retained rank inventory')
    tenth_lower = float(rows[9]['projector_weight_interval'][0])
    eleventh_lower = float(rows[10]['projector_weight_interval'][0])
    require(tenth_lower > omitted_upper,
            'Potts first ten protected against omitted channels')
    require(eleventh_lower <= omitted_upper,
            'Potts rank 11 is not upgraded to full-spectrum certification')
    return {'contract': 'Potts retained versus omitted rank boundary',
            'rank10_lower': tenth_lower, 'rank11_lower': eleventh_lower,
            'omitted_upper': omitted_upper}


def nnn_record_contract(config: dict, prg: list[dict], bench: list[dict]) -> dict:
    expected = {(float(j2), int(size)) for j2 in config['prg']['j2_values']
                for size in config['prg']['sizes']}
    roots = {(float(row['lambda_or_g']), int(row['L'])): row for row in prg}
    require(len(prg) == len(expected) and set(roots) == expected,
            'NNN PRG complete J2/L inventory')
    records = [row for row in bench if row['model'] == 'NNN-TFIM'
               and float(row['lambda_or_g']) in config['prg']['j2_values']]
    responses = {(float(row['lambda_or_g']), int(row['L'])): row for row in records}
    require(len(records) == len(expected) and set(responses) == expected,
            'NNN response complete J2/L inventory')
    for key in expected:
        root, response = roots[key], responses[key]
        require(abs(float(root['scaled_gap_residual']))
                <= config['prg']['maximum_scaled_gap_residual'],
                f'NNN PRG residual {key}')
        for field in ('residual_even_L', 'residual_odd_L'):
            require(float(root[field]) <= config['prg']['maximum_eigenpair_residual'],
                    f'NNN {field} {key}')
        require(float(response['solve_res'])
                <= config['response']['maximum_solve_residual'],
                f'NNN projected response residual {key}')
        require(abs(float(response['h'])-float(root['h'])) < 1e-9,
                f'NNN response uses PRG field {key}')
    return {'contract': 'NNN frozen PRG and response thresholds', 'pairs': len(expected)}


def load_engine():
    path = BASELINE / ('producers/0.5.1.dev0/src/cc_repro/_resources/original/'
                       'scripts/simulation/simulate_interacting_benchmarks.py')
    spec = importlib.util.spec_from_file_location('bounded_nnn_engine', path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def nnn_small_sector_contract() -> dict:
    import numpy as np
    import scipy.sparse as sp

    engine = load_engine()
    size, j2, field = 6, 0.2, 1.3
    full_zz, full_x = engine.build_nnn_tfim_components(size, j2)
    maps = engine._binary_translation_parity_maps(size)
    states = np.arange(1 << size)
    maximum = 0.0
    for parity in (+1, -1):
        if parity == +1:
            counts, indices, signs = maps[1], maps[2], np.ones(1 << size)
        else:
            counts, indices, signs = maps[4], maps[5], maps[6]
        valid = indices >= 0
        basis = sp.coo_matrix(
            (signs[valid]/np.sqrt(counts[indices[valid]]),
             (states[valid], indices[valid])),
            shape=(1 << size, len(counts))).tocsr()
        reduced_zz, reduced_x, dimension = (
            engine.build_nnn_tfim_sector_components_k0_parity(size, j2, parity))
        require(dimension == basis.shape[1], 'NNN sector basis dimension')
        for projected, assembled in ((basis.T @ full_zz @ basis, reduced_zz),
                                     (basis.T @ full_x @ basis, reduced_x),
                                     (basis.T @ (full_zz-field*full_x) @ basis,
                                      reduced_zz-field*reduced_x)):
            difference = np.asarray((projected-assembled).todense())
            maximum = max(maximum, float(np.max(np.abs(difference))))
    require(maximum < 2e-12, 'NNN nonzero-J2 full-space/parity projection')
    return {'contract': 'NNN nonzero-J2 full-space versus parity projection',
            'L': size, 'J2': j2, 'max_abs_error': maximum}


def interacting_contracts() -> list[dict]:
    checks = []
    exponent = float(read_json(DATA/'potts_theory_guided_7over5_receipt.json')
                     ['theory_contract']['relative_analytic_background_correction'])
    near(exponent, 7/5, 1e-14, 'Potts frozen 7/5 exponent versus renderer label')
    checks.append({'contract': 'Potts exponent/label consistency', 'exponent': exponent})
    charge_script = BASELINE / ('producers/0.5.0.dev0/src/cc_repro/_resources/original/'
                                'scripts/verification/verify_potts_charge_sector.py')
    charge = subprocess.run([sys.executable, '-B', str(charge_script), '--no-write'],
                            cwd=ROOT, capture_output=True, text=True, timeout=90)
    require(charge.returncode == 0 and '0 FAIL' in charge.stdout,
            'Potts bounded fresh charge-sector control')
    checks.append({'contract': 'Potts bounded charge-sector control',
                   'result': charge.stdout.splitlines()[0]})
    checks.append(potts_rank_contract(
        read_json(BASELINE/'data/potts-derived/projector-response-enclosures.json')))

    config_path = BASELINE / ('producers/0.5.1.dev0/src/cc_repro/_resources/original/'
                              'repro/config/nnn_tfim_expensive_reproduction.json')
    metadata = read_json(BASELINE/('data/nnn/runs/a1-publication/data/reproducibility/'
                                   'nnn_tfim_expensive_run_metadata.json'))
    require(digest(config_path) == metadata['config_sha256'],
            'NNN archived config identity')
    config = read_json(config_path)
    checks.append(nnn_record_contract(config,
                  read_csv(DATA/'nnn_tfim_prg_solver_diagnostics.csv'),
                  read_csv(DATA/'interacting_benchmarks.csv')))
    checks.append(nnn_small_sector_contract())
    mid = read_csv(DATA/'nnn_tfim_L16_L18_retained_eigenpair_convergence.csv')
    mid_expected = {(float(j2), size, cutoff)
                    for j2 in config['prg']['j2_values'] for size in (16, 18)
                    for cutoff in config['convergence_scans']['L16_L18']}
    require({(float(row['lambda_or_g']), int(row['L']),
              int(row['n_low_energy_eigenpairs'])) for row in mid} == mid_expected
            and len(mid) == len(mid_expected), 'NNN L16/L18 convergence inventory')
    large = read_csv(DATA/'nnn_tfim_L20_retained_eigenpair_convergence.csv')
    large_expected = {(float(j2), 20, cutoff)
                      for j2, cutoffs in config['convergence_scans']['L20'].items()
                      for cutoff in cutoffs}
    require({(float(row['lambda_or_g']), int(row['L']),
              int(row['n_low_energy_eigenpairs'])) for row in large} == large_expected
            and len(large) == len(large_expected), 'NNN L20 convergence inventory')
    sensitivity = read_csv(DATA/'nnn_tfim_L20_h_sensitivity.csv')
    expected_shifts = set(config['field_sensitivity']['shifts'])
    require(len(sensitivity) == len(expected_shifts) and
            {round(float(row['delta_h']), 8) for row in sensitivity}
            == {round(float(value), 8) for value in expected_shifts},
            'NNN field-sensitivity inventory')
    for row in mid + large + sensitivity:
        require(math.isfinite(float(row['solve_res'])) and
                float(row['solve_res']) <= config['response']['maximum_solve_residual'],
                'NNN archived scan projected-solve residual')
    checks.append({'contract': 'NNN convergence and sensitivity inventories',
                   'rows': len(mid)+len(large)+len(sensitivity)})
    return checks


def refinement_contracts() -> list[dict]:
    """Run the independent standard-library R3 interval checker."""
    script = ROOT/'r3_support/verify_refinement_budgets.py'
    receipt = ROOT/'r3_support/expected_bound_enclosures.json'
    check = subprocess.run([sys.executable, '-B', str(script)], cwd=ROOT,
                           capture_output=True, text=True, timeout=120)
    require(check.returncode == 0 and
            'PASS; reviewed receipt matched expected_bound_enclosures.json' in check.stdout,
            'R3 conditional refinement budgets and reviewed receipt')
    return [{'contract': 'R3 conditional refinement budgets',
             'receipt_sha256': digest(receipt),
             'scope': 'CFT reference families and finite rational examples; '
                      'lattice matching and fine-channel support remain premises'}]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scope', choices=('analytic', 'interacting', 'refinement', 'all'),
                        default='all')
    args = parser.parse_args()
    try:
        baseline_check = subprocess.run(
            [sys.executable, '-B', str(BASELINE/'tools/verify_release.py')],
            cwd=ROOT, capture_output=True, text=True, timeout=120)
        require(baseline_check.returncode == 0 and '"status": "PASS"' in baseline_check.stdout,
                'immutable numerical baseline identity')
        checks = []
        if args.scope in ('analytic', 'all'):
            checks.extend(analytic_contracts())
        if args.scope in ('interacting', 'all'):
            checks.extend(interacting_contracts())
        if args.scope in ('refinement', 'all'):
            checks.extend(refinement_contracts())
        print(json.dumps({'status': 'PASS', 'scope': args.scope, 'checks': checks,
                          'claim_ceiling': 'Selected bounded contracts; no large campaign, '
                                           'thermodynamic convergence, or manuscript proof.'},
                         indent=2, allow_nan=False))
    except (ValueError, KeyError, IndexError, FileNotFoundError, subprocess.TimeoutExpired) as error:
        parser.exit(1, str(error)+'\n')


if __name__ == '__main__':
    main()
