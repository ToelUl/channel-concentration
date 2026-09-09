#!/usr/bin/env python3
"""Small exact-diagonalization checks for operator dependence of channel concentration.

The script is intentionally conservative.  It is not a precision CFT extraction;
it checks the hierarchy emphasized in the manuscript:

    scaling dimension / RG eigenvalue -> leading scaling of P2,
    normalized form-factor distribution -> K_F.

It writes two files in a new staged directory below build/ by default:

    operator_dependence_benchmarks.csv
    operator_dependence_summary.txt

Examples
--------
python simulate_operator_dependence.py
python simulate_operator_dependence.py --tfim-Ls 6,8,10,12 --potts-Ls 4,5,6,7,8
"""
from __future__ import annotations

import argparse
import csv
import math
import time
import uuid
from pathlib import Path

import numpy as np
import scipy.sparse as sp

from simulate_interacting_benchmarks import (
    build_potts_k0,
    hybrid_level_projector_kf,
    _translate_base3,
)


def parse_Ls(text: str) -> list[int]:
    return [int(x) for x in text.split(',') if x.strip()]


def loglog_slope(Ls: list[int], vals: list[float]) -> tuple[float, float]:
    x = np.log(np.asarray(Ls, dtype=float))
    y = np.log(np.asarray(vals, dtype=float))
    A = np.vstack([np.ones_like(x), x]).T
    coeff, *_ = np.linalg.lstsq(A, y, rcond=None)
    yfit = A @ coeff
    rmse = float(np.sqrt(np.mean((y - yfit) ** 2)))
    return float(coeff[1]), rmse


# ---------------------------------------------------------------------------
# TFIM in the real-space convention H=-sum ZZ - h sum X.
# ---------------------------------------------------------------------------

def build_tfim_with_operator(L: int, operator: str, h: float = 1.0) -> tuple[sp.csr_matrix, sp.csr_matrix]:
    dim = 1 << L
    states = np.arange(dim, dtype=np.int64)

    zz_diag = np.zeros(dim, dtype=float)
    z_diag = np.zeros(dim, dtype=float)
    for i in range(L):
        zi = 1 - 2 * ((states >> i) & 1)
        zj = 1 - 2 * ((states >> ((i + 1) % L)) & 1)
        zz_diag += zi * zj
        z_diag += zi

    rows = []
    cols = []
    for i in range(L):
        rows.append(states)
        cols.append(states ^ (1 << i))
    Xsum = sp.coo_matrix(
        (np.ones(L * dim), (np.concatenate(rows), np.concatenate(cols))),
        shape=(dim, dim),
    ).tocsr()

    H = (sp.diags(-zz_diag, format='csr') - h * Xsum).tocsr()
    if operator == 'energy_h':
        dH = (-Xsum).tocsr()
    elif operator == 'energy_J':
        dH = (-sp.diags(zz_diag, format='csr')).tocsr()
    elif operator == 'spin_Z':
        dH = (-sp.diags(z_diag, format='csr')).tocsr()
    else:
        raise ValueError(f'unknown TFIM operator {operator!r}')
    return H, dH


# ---------------------------------------------------------------------------
# Potts in the standard clock/shift convention used in the manuscript:
# H=-sum(tau+tau^dagger)-g sum(sigma^dagger sigma_next + h.c.).
# The imported build_potts_k0 returns the Hamiltonian and the thermal dH/dg.
# ---------------------------------------------------------------------------

def potts_k0_order_operator(L: int) -> sp.csr_matrix:
    """Uniform order-field operator -sum_j (sigma_j + sigma_j^dagger) in k=0.

    In the clock basis this is diagonal with entries -2 sum_j cos(2 pi m_j/3).
    Since the uniform operator is translation invariant, the same diagonal value
    is assigned to each translation orbit representative.
    """
    dim_full = 3 ** L
    states = np.arange(dim_full, dtype=np.int64)
    rep = states.copy()
    translated = states.copy()
    for _ in range(L - 1):
        translated = _translate_base3(translated, L)
        rep = np.minimum(rep, translated)
    reps = np.unique(rep)
    nrep = len(reps)
    digits = np.zeros((nrep, L), dtype=np.int8)
    tmp = reps.copy()
    for i in range(L):
        digits[:, i] = tmp % 3
        tmp //= 3
    values = np.zeros(nrep, dtype=float)
    for i in range(L):
        values += 2.0 * np.cos(2.0 * np.pi * digits[:, i] / 3.0)
    return (-sp.diags(values, format='csr')).tocsr()


def run_one(model: str, operator: str, L: int, n_low_energy_eigenpairs: int) -> dict:
    t0 = time.time()
    if model == 'TFIM':
        H, dH = build_tfim_with_operator(L, operator)
        dim = 1 << L
        sector = 'full'
    elif model == 'Potts':
        H, thermal_dH, dim = build_potts_k0(L, 1.0)
        dH = thermal_dH if operator == 'thermal' else potts_k0_order_operator(L)
        sector = 'translation k=0'
    else:
        raise ValueError(model)
    result = hybrid_level_projector_kf(
        H, dH, n_low_energy_eigenpairs=n_low_energy_eigenpairs, max_solve_residual=1e-8,
    )
    seconds = time.time() - t0
    return {
        'model': model,
        'operator': operator,
        'L': L,
        'dim': dim,
        'sector': sector,
        'P2': result['P2'],
        'P4_low': result['P4'],
        'KF_low': result['KF'],
        'KF_half': result.get('KF_half', math.nan),
        'gap': result['gap'],
        'solve_res': result['solve_res'],
        'n_levels': result['n_levels'],
        'minres_info': result['minres_info'],
        'nominal_eigenpairs': result['nominal_eigenpairs'],
        'solver_eigenpairs': result['solver_eigenpairs'],
        'guard_eigenpairs': result['guard_eigenpairs'],
        'seconds': seconds,
    }


METADATA = {
    ('TFIM', 'energy_h'): ('Ising energy epsilon / transverse-field tuning', 1.0, 1.0, 2.0),
    ('TFIM', 'energy_J'): ('Ising energy epsilon / interaction tuning', 1.0, 1.0, 2.0),
    ('TFIM', 'spin_Z'): ('Ising spin sigma', 1.0 / 8.0, 15.0 / 8.0, 15.0 / 4.0),
    ('Potts', 'thermal'): ('Potts thermal field epsilon', 4.0 / 5.0, 6.0 / 5.0, 12.0 / 5.0),
    ('Potts', 'order'): ('Potts order field sigma + sigma^dagger', 2.0 / 15.0, 28.0 / 15.0, 56.0 / 15.0),
}


def main() -> None:
    project_root = Path(__file__).resolve().parents[2]
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--tfim-Ls', default='6,8,10,12')
    ap.add_argument('--potts-Ls', default='4,5,6,7,8')
    ap.add_argument(
        '--n-low-energy-eigenpairs', '--k-low',
        dest='n_low_energy_eigenpairs', type=int, default=96,
        help='retained low-energy eigenpair count; --k-low is a legacy alias',
    )
    ap.add_argument('--outdir', type=Path, default=None)
    args = ap.parse_args()

    from simulate_interacting_benchmarks import fresh_output_directory
    if args.n_low_energy_eigenpairs < 2:
        raise ValueError("at least two nominal eigenpairs are required")
    tfim_sizes, potts_sizes = parse_Ls(args.tfim_Ls), parse_Ls(args.potts_Ls)
    if not tfim_sizes or not potts_sizes or any(L < 4 or L > 12 or L % 2 for L in tfim_sizes) or any(L < 3 or L > 8 for L in potts_sizes):
        raise ValueError("operator diagnostics require even TFIM L=4..12 and Potts L=3..8")
    args.outdir = fresh_output_directory(args.outdir or project_root / 'build' / ('operator-' + uuid.uuid4().hex))
    csv_path = args.outdir / 'operator_dependence_benchmarks.csv'
    summary_path = args.outdir / 'operator_dependence_summary.txt'

    rows: list[dict] = []
    for operator in ['energy_h', 'energy_J', 'spin_Z']:
        for L in parse_Ls(args.tfim_Ls):
            row = run_one('TFIM', operator, L, args.n_low_energy_eigenpairs)
            rows.append(row)
            print(f"TFIM {operator:8s} L={L:2d} P2={row['P2']:.6g} KF={row['KF_low']:.6f} res={row['solve_res']:.1e}", flush=True)
    for operator in ['thermal', 'order']:
        for L in parse_Ls(args.potts_Ls):
            row = run_one('Potts', operator, L, args.n_low_energy_eigenpairs)
            rows.append(row)
            print(f"Potts {operator:7s} L={L:2d} P2={row['P2']:.6g} KF={row['KF_low']:.6f} res={row['solve_res']:.1e}", flush=True)

    fields = [
        'model', 'operator', 'L', 'dim', 'sector', 'CFT_field', 'Delta_O', 'y_O',
        'expected_P2_exponent', 'P2', 'P4_low', 'KF_low', 'KF_half', 'gap',
        'solve_res', 'n_levels', 'minres_info', 'nominal_eigenpairs', 'solver_eigenpairs', 'guard_eigenpairs', 'seconds', 'note',
    ]
    with csv_path.open('x', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for row in rows:
            field, delta, y, expected = METADATA[(row['model'], row['operator'])]
            out = dict(row)
            out.update({
                'CFT_field': field,
                'Delta_O': f'{delta:.12g}',
                'y_O': f'{y:.12g}',
                'expected_P2_exponent': f'{expected:.12g}',
                'P2': f"{row['P2']:.12g}",
                'P4_low': f"{row['P4_low']:.12g}",
                'KF_low': f"{row['KF_low']:.12g}",
                'KF_half': f"{row['KF_half']:.12g}",
                'gap': f"{row['gap']:.12g}",
                'solve_res': f"{row['solve_res']:.3e}",
                'seconds': f"{row['seconds']:.3f}",
                'note': 'finite-size operator-dependence check; K_F uses low-level P4',
            })
            w.writerow(out)

    lines = []
    lines.append('Operator-dependence benchmark summary')
    lines.append('====================================')
    lines.append('These finite-size fits use P2 from a projected linear solve. K_F is included as a channel-shape diagnostic, not as a precision thermodynamic extrapolation.')
    lines.append('')
    for key in METADATA:
        model, operator = key
        subset = [r for r in rows if r['model'] == model and r['operator'] == operator]
        Ls = [int(r['L']) for r in subset]
        P2s = [float(r['P2']) for r in subset]
        slope, rmse = loglog_slope(Ls, P2s)
        field, delta, y, expected = METADATA[key]
        last = subset[-1]
        lines.append(
            f"{model:5s} {operator:8s}: field={field}; Delta_O={delta:.6g}; "
            f"expected P2 exponent={expected:.6g}; fitted exponent={slope:.6g}; "
            f"log-fit RMSE={rmse:.3e}; last KF_low={last['KF_low']:.6g} at L={last['L']}."
        )
    lines.append('')
    lines.append('Interpretation: the fitted exponents distinguish energy and spin/order perturbations even at small L. The concentration K_F changes with the normalized channel distribution and should not be read as a function of Delta_O alone.')
    summary_path.write_text('\n'.join(lines) + '\n')

    print(f'wrote {csv_path}')
    print(f'wrote {summary_path}')


if __name__ == '__main__':
    main()
