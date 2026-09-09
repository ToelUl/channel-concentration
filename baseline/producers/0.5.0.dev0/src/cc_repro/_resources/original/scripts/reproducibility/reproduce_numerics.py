#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
reproduce_numerics.py
=====================

Numerical reproducibility script for

    Channel concentration of quantum-geometric criticality
    in Ising and XY chains

This script collects the non-plotting numerical calculations used by the
manuscript.  It is intentionally independent of matplotlib and of the figure
production script.  Running it regenerates machine-readable tables and a short
text summary in the data/ directory.

The script covers

  1. TFIM Neveu--Schwarz finite-size channel concentration.
  2. Ramond-sector contrast with the zero mode excluded.
  3. Dirichlet-lambda envelope predictions, including Table-II values.
  4. Ising and Lifshitz scaling-function benchmarks Phi(0) and Psi(0).
  5. XY-plane directional K_F scan at the manuscript benchmark point.
  6. Weak one-sided quench finite-delta error budget and fixed-u feasibility.
  7. Equivalent multi-cone free-fermion counting rule.

No interacting ED is performed here.

Usage
-----
From the project root:

    python reproduce_numerics.py

For a faster diagnostic run:

    python reproduce_numerics.py --mode fast

To write outputs elsewhere:

    python reproduce_numerics.py --output-dir data/repro_check

Dependencies
------------
Python >= 3.9, numpy, scipy.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
import sys
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
from scipy.special import zeta


# -----------------------------------------------------------------------------
# Basic data containers
# -----------------------------------------------------------------------------

@dataclass(frozen=True)
class SectorRow:
    L: int
    KF_NS_numeric: float
    KF_NS_exact: float
    KF_NS_minus_two_thirds: float
    KF_R_exact: float
    KF_R_minus_two_fifths: float


@dataclass(frozen=True)
class EnvelopeRow:
    label: str
    P2_size_exponent: float
    p_env: float
    y_O: Optional[float]
    scaling_regime: str
    KF_env: float
    status: str


@dataclass(frozen=True)
class WeakQuenchRow:
    delta: float
    mean_N: float
    var_N: float
    R_delta: float
    abs_R_minus_KF: float


@dataclass(frozen=True)
class FixedUFeasibilityRow:
    L: int
    u: float
    delta: float
    KF_geom: float
    mean_N: float
    F2: float
    F3: float
    F4: float
    VarY: float
    rare_pair_variance_ratio: float
    M_10pct: float
    abs_R_minus_KF: float


@dataclass(frozen=True)
class MultiConeRow:
    p: float
    n_cones: int
    KF_single_cone: float
    KF_n_cones: float
    N_eff_n_cones: float


@dataclass(frozen=True)
class XYDirectionRow:
    phi: float
    K_F: float
    P2: float
    P4: float


# -----------------------------------------------------------------------------
# Free-fermion geometry
# -----------------------------------------------------------------------------

def ns_momenta(L: int) -> np.ndarray:
    """Positive Neveu--Schwarz momenta: k_n=(2n+1)pi/L, n=0,...,L/2-1."""
    if L <= 0 or L % 2 != 0:
        raise ValueError("L must be a positive even integer.")
    n = np.arange(L // 2, dtype=float)
    return (2.0 * n + 1.0) * np.pi / float(L)


def ramond_nonzero_momenta(L: int) -> np.ndarray:
    """Positive nonzero Ramond momenta with zero and pi modes omitted."""
    if L <= 2 or L % 2 != 0:
        raise ValueError("L must be an even integer larger than 2.")
    n = np.arange(1, L // 2, dtype=float)
    return 2.0 * np.pi * n / float(L)


def theta_grads(h: float, gamma: float, k: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """Return partial_h theta_k and partial_gamma theta_k for the XY block."""
    X = h - np.cos(k)
    Y = gamma * np.sin(k)
    lam2 = X * X + Y * Y
    dh = -gamma * np.sin(k) / lam2
    dg = X * np.sin(k) / lam2
    return dh, dg


def channel_weights(h: float, gamma: float, k: np.ndarray, yh: float, yg: float) -> np.ndarray:
    """Per-mode channel weights x_k(y)=1/4 (y^h d_h theta + y^gamma d_gamma theta)^2."""
    dh, dg = theta_grads(h, gamma, k)
    return 0.25 * (yh * dh + yg * dg) ** 2


def KF_from_weights(x: np.ndarray) -> Tuple[float, float, float]:
    """Return K_F, P2, P4 from nonnegative channel weights."""
    P2 = float(np.sum(x))
    P4 = float(np.sum(x * x))
    if P2 <= 0.0:
        return float("nan"), P2, P4
    return P4 / (P2 * P2), P2, P4


def KF_point(h: float, gamma: float, y: Tuple[float, float], L: int) -> Tuple[float, float, float]:
    k = ns_momenta(L)
    x = channel_weights(h, gamma, k, y[0], y[1])
    return KF_from_weights(x)


def tfim_ns_kf_exact(L: int) -> float:
    """Exact critical NS-sector TFIM value used in the manuscript."""
    if L <= 1:
        raise ValueError("L must be larger than 1.")
    return (2.0 / 3.0) * (L * L + L - 3.0) / (L * (L - 1.0))


def tfim_ramond_kf_exact(L: int) -> float:
    """Exact critical Ramond-sector contrast with the zero mode excluded."""
    if L <= 2:
        raise ValueError("L must be larger than 2.")
    return 2.0 * (L * L + 3.0 * L - 13.0) / (5.0 * (L - 1.0) * (L - 2.0))


# -----------------------------------------------------------------------------
# Envelope and scaling functions
# -----------------------------------------------------------------------------

def dirichlet_lambda(s: float) -> float:
    return float((1.0 - 2.0 ** (-s)) * zeta(s))


def KFcrit_p(p: float | np.ndarray) -> float | np.ndarray:
    """Odd-ladder critical envelope value lambda_D(2p)/lambda_D(p)^2."""
    p_arr = np.asarray(p, dtype=float)
    numer = (1.0 - 2.0 ** (-2.0 * p_arr)) * zeta(2.0 * p_arr)
    denom = ((1.0 - 2.0 ** (-p_arr)) * zeta(p_arr)) ** 2
    out = numer / denom
    return float(out) if np.ndim(p) == 0 else out


def _odd_sequence(nmax: int) -> np.ndarray:
    return np.arange(1.0, 2.0 * nmax, 2.0, dtype=float)


def Phi(mu: float | np.ndarray, nmax: int = 50000) -> float | np.ndarray:
    """Ising finite-size scaling function Phi(mu), with Phi(0)=2/3."""
    kappa = _odd_sequence(nmax)
    mu_arr = np.atleast_1d(np.asarray(mu, dtype=float))
    out = np.empty_like(mu_arr)
    for i, m in enumerate(mu_arr):
        d = kappa * kappa + m * m
        denom = np.sum((kappa * kappa) / (d * d))
        numer = np.sum((kappa ** 4) / (d ** 4))
        out[i] = numer / (denom * denom)
    return out[0] if np.ndim(mu) == 0 else out


def Psi(w: float | np.ndarray, nmax: int = 50000) -> float | np.ndarray:
    """Lifshitz relevant-direction scaling function Psi(w)."""
    kappa = _odd_sequence(nmax)
    w_arr = np.atleast_1d(np.asarray(w, dtype=float))
    out = np.empty_like(w_arr)
    for i, ww in enumerate(w_arr):
        d = kappa * kappa + 4.0 * ww * ww
        denom = np.sum((kappa ** -2) / (d * d))
        numer = np.sum((kappa ** -4) / (d ** 4))
        out[i] = numer / (denom * denom)
    return out[0] if np.ndim(w) == 0 else out


# -----------------------------------------------------------------------------


# -----------------------------------------------------------------------------
# Weak one-sided quench helpers
# -----------------------------------------------------------------------------

def theta_angle(h: float, gamma: float, k: np.ndarray) -> np.ndarray:
    return np.arctan2(gamma * np.sin(k), h - np.cos(k))


def weak_quench_probabilities_h(h0: float, gamma: float, delta: float, L: int) -> np.ndarray:
    k = ns_momenta(L)
    theta_i = theta_angle(h0, gamma, k)
    theta_f = theta_angle(h0 + delta, gamma, k)
    return np.sin(0.5 * (theta_f - theta_i)) ** 2


def R_from_probabilities(p: np.ndarray) -> Tuple[float, float, float]:
    mean_N = float(np.sum(p))
    var_N = float(np.sum(p * (1.0 - p)))
    # Evaluate the variance deficit as sum(p_k^2), rather than subtracting two
    # nearly equal rare-event quantities.  The expressions are algebraically
    # identical for independent Bernoulli channels, but the direct form is
    # numerically stable in the weak-quench window.
    variance_deficit = float(np.sum(p * p))
    return variance_deficit / (mean_N * mean_N), mean_N, var_N


def factorial_moments_from_probabilities(
    p: np.ndarray,
) -> Tuple[float, float, float, float]:
    """Return F2, F3, F4, and Var[Y] for Y=N(N-1).

    The channels are independent Bernoulli variables with probabilities p_k.
    Power-sum identities evaluate the factorial moments without enumerating
    the Poisson-binomial distribution.  The exact identity
    Y^2=(N)_4+4(N)_3+2(N)_2 then gives Var[Y].
    """
    probabilities = np.asarray(p, dtype=float)
    if np.any(probabilities < 0.0) or np.any(probabilities > 1.0):
        raise ValueError("Bernoulli probabilities must lie in [0, 1].")
    s1 = float(np.sum(probabilities))
    s2 = float(np.sum(probabilities**2))
    s3 = float(np.sum(probabilities**3))
    s4 = float(np.sum(probabilities**4))
    F2 = s1**2 - s2
    F3 = s1**3 - 3.0 * s1 * s2 + 2.0 * s3
    F4 = (
        s1**4
        - 6.0 * s1**2 * s2
        + 3.0 * s2**2
        + 8.0 * s1 * s3
        - 6.0 * s4
    )
    VarY = F4 + 4.0 * F3 + 2.0 * F2 - F2**2
    return F2, F3, F4, VarY


# -----------------------------------------------------------------------------
# Numerical jobs
# -----------------------------------------------------------------------------

def compute_sector_rows(L_values: Sequence[int]) -> List[SectorRow]:
    rows: List[SectorRow] = []
    for L in L_values:
        ns_numeric, _, _ = KF_point(1.0, 1.0, (1.0, 0.0), int(L))
        ns_exact = tfim_ns_kf_exact(int(L))
        r_exact = tfim_ramond_kf_exact(int(L))
        rows.append(SectorRow(
            L=int(L),
            KF_NS_numeric=ns_numeric,
            KF_NS_exact=ns_exact,
            KF_NS_minus_two_thirds=ns_exact - 2.0 / 3.0,
            KF_R_exact=r_exact,
            KF_R_minus_two_fifths=r_exact - 2.0 / 5.0,
        ))
    return rows


def compute_envelope_table() -> List[EnvelopeRow]:
    # In single-scale rows, P2_size_exponent=p_env=2*y_O.  The Lifshitz field
    # direction is explicitly two-scale: P2 grows as L^4 while its normalized
    # small-w envelope has p_env=6, so no literal y_O is assigned.  Interacting
    # entries are IDEAL soft-ladder references, not spectrum predictions.
    specs = [
        ("Ising / TFIM mass", 2.0, 2.0, 1.0, "single-scale", "proved free-fermion NS result"),
        ("3-state Potts energy", 2.4, 2.4, 6.0 / 5.0, "single-scale", "ideal soft-ladder reference (not interacting prediction)"),
        ("Tricritical Ising energy-like", 3.6, 3.6, 9.0 / 5.0, "single-scale", "ideal soft-ladder reference (not interacting prediction)"),
        ("Gaussian / mean-field", 4.0, 4.0, 2.0, "single-scale", "ideal soft-ladder reference / free-field benchmark"),
        ("Lifshitz anisotropy direction", 2.0, 2.0, 1.0, "single-scale", "demonstrated free-fermion result"),
        ("Lifshitz field direction", 4.0, 6.0, None, "two-scale", "demonstrated free-fermion result; punctured normalized limit"),
    ]
    rows: List[EnvelopeRow] = []
    for label, p2_exp, p_env, yO, regime, status in specs:
        rows.append(EnvelopeRow(
            label=label,
            P2_size_exponent=float(p2_exp),
            p_env=float(p_env),
            y_O=None if yO is None else float(yO),
            scaling_regime=regime,
            KF_env=float(KFcrit_p(p_env)),
            status=status,
        ))
    return rows


def compute_xy_direction_scan(h: float, gamma: float, L: int, n_phi: int) -> List[XYDirectionRow]:
    rows: List[XYDirectionRow] = []
    for phi in np.linspace(0.0, np.pi, n_phi):
        y = (math.cos(float(phi)), math.sin(float(phi)))
        KF, P2, P4 = KF_point(h, gamma, y, L)
        rows.append(XYDirectionRow(phi=float(phi), K_F=KF, P2=P2, P4=P4))
    return rows


def compute_weak_quench_rows(h0: float, gamma: float, L: int, deltas: Sequence[float]) -> Tuple[float, List[WeakQuenchRow]]:
    KF_geom, _, _ = KF_point(h0, gamma, (1.0, 0.0), L)
    rows: List[WeakQuenchRow] = []
    for delta in deltas:
        p = weak_quench_probabilities_h(h0, gamma, float(delta), L)
        R, mean_N, var_N = R_from_probabilities(p)
        rows.append(WeakQuenchRow(
            delta=float(delta),
            mean_N=mean_N,
            var_N=var_N,
            R_delta=R,
            abs_R_minus_KF=abs(R - KF_geom),
        ))
    return KF_geom, rows


def fit_delta_error(KF_geom: float, rows: Sequence[WeakQuenchRow]) -> Dict[str, float]:
    d = np.array([row.delta for row in rows], dtype=float)
    err = np.array([row.R_delta - KF_geom for row in rows], dtype=float)
    # Include both linear and quadratic terms to check that the quadratic term dominates.
    X = np.stack([d, d * d], axis=1)
    coeff, *_ = np.linalg.lstsq(X, err, rcond=None)
    coeff2_only = float(np.dot(d * d, err) / np.dot(d * d, d * d))
    return {
        "linear_coefficient": float(coeff[0]),
        "quadratic_coefficient": float(coeff[1]),
        "quadratic_only_coefficient": coeff2_only,
    }


def compute_fixed_u_feasibility_rows(
    L_values: Sequence[int], u_values: Sequence[float]
) -> List[FixedUFeasibilityRow]:
    """Evaluate the critical TFIM quench at fixed scaling amplitude u=delta L."""
    rows: List[FixedUFeasibilityRow] = []
    for u in u_values:
        for L in L_values:
            delta = float(u) / float(L)
            p = weak_quench_probabilities_h(1.0, 1.0, delta, int(L))
            R, mean_N, _ = R_from_probabilities(p)
            KF_geom, _, _ = KF_point(1.0, 1.0, (1.0, 0.0), int(L))
            F2, F3, F4, VarY = factorial_moments_from_probabilities(p)
            rows.append(FixedUFeasibilityRow(
                L=int(L),
                u=float(u),
                delta=delta,
                KF_geom=KF_geom,
                mean_N=mean_N,
                F2=F2,
                F3=F3,
                F4=F4,
                VarY=VarY,
                rare_pair_variance_ratio=VarY / F2,
                M_10pct=100.0 * VarY / F2**2,
                abs_R_minus_KF=abs(R - KF_geom),
            ))
    return rows


def compute_multicone_rows(p_values: Sequence[float], n_cones_values: Sequence[int]) -> List[MultiConeRow]:
    rows: List[MultiConeRow] = []
    for p in p_values:
        k_single = float(KFcrit_p(float(p)))
        for nc in n_cones_values:
            k_nc = k_single / float(nc)
            rows.append(MultiConeRow(
                p=float(p),
                n_cones=int(nc),
                KF_single_cone=k_single,
                KF_n_cones=k_nc,
                N_eff_n_cones=1.0 / k_nc,
            ))
    return rows


# -----------------------------------------------------------------------------
# IO helpers
# -----------------------------------------------------------------------------

def write_csv(path: Path, rows: Sequence[object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        return
    dict_rows = [
        {key: ("NA" if value is None else value) for key, value in asdict(row).items()}
        for row in rows
    ]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(dict_rows[0].keys()))
        writer.writeheader()
        writer.writerows(dict_rows)


def write_text_summary(path: Path, summary: Dict, sector_rows: Sequence[SectorRow],
                       envelope_rows: Sequence[EnvelopeRow], weak_rows: Sequence[WeakQuenchRow],
                       fixed_u_rows: Sequence[FixedUFeasibilityRow],
                       multicone_rows: Sequence[MultiConeRow], xy_rows: Sequence[XYDirectionRow]) -> None:
    xy_max = max(xy_rows, key=lambda r: r.K_F)
    xy_min = min(xy_rows, key=lambda r: r.K_F)
    with path.open("w", encoding="utf-8") as f:
        f.write("Numerical reproducibility summary\n")
        f.write("=================================\n\n")
        f.write("1. Scaling-function checks\n")
        f.write("--------------------------\n")
        f.write(f"Phi(0) = {summary['Phi(0)']:.15g}\n")
        f.write(f"KFcrit_p(2) = {summary['KFcrit_p(2)']:.15g}\n")
        f.write(f"Psi(0) = {summary['Psi(0)']:.15g}\n")
        f.write(f"Ramond envelope zeta(4)/zeta(2)^2 = {summary['Ramond envelope']:.15g}\n\n")

        f.write("2. TFIM sector contrast\n")
        f.write("-----------------------\n")
        f.write("L, K_NS_exact, K_NS-2/3, K_R_exact, K_R-2/5\n")
        for r in sector_rows:
            f.write(f"{r.L}, {r.KF_NS_exact:.15g}, {r.KF_NS_minus_two_thirds:.15g}, "
                    f"{r.KF_R_exact:.15g}, {r.KF_R_minus_two_fifths:.15g}\n")
        f.write("\n")

        f.write("3. Envelope table\n")
        f.write("-----------------\n")
        for r in envelope_rows:
            yO_text = "NA" if r.y_O is None else f"{r.y_O:.10g}"
            f.write(f"{r.label}: P2_size_exponent={r.P2_size_exponent:.10g}, "
                    f"p_env={r.p_env:.10g}, y_O={yO_text}, "
                    f"scaling_regime={r.scaling_regime}, "
                    f"K_env={r.KF_env:.10g}, status={r.status}\n")
        f.write("\n")

        f.write("4. XY directional scan\n")
        f.write("----------------------\n")
        f.write(f"max K_F = {xy_max.K_F:.15g} at phi = {xy_max.phi:.15g}\n")
        f.write(f"min K_F = {xy_min.K_F:.15g} at phi = {xy_min.phi:.15g}\n")
        f.write(f"anisotropy ratio max/min = {xy_max.K_F / xy_min.K_F:.15g}\n")
        f.write("\n")

        f.write("5. Weak-quench finite-delta error budget\n")
        f.write("----------------------------------------\n")
        f.write(f"Geometric K_F = {summary['weak_quench_KF_geom']:.15g}\n")
        f.write("delta, mean_N, var_N, R(delta), |R-K_F|\n")
        for r in weak_rows:
            f.write(f"{r.delta:.15g}, {r.mean_N:.15g}, {r.var_N:.15g}, "
                    f"{r.R_delta:.15g}, {r.abs_R_minus_KF:.15g}\n")
        f.write(f"linear coefficient in err ~ a delta + b delta^2: {summary['delta_fit']['linear_coefficient']:.15g}\n")
        f.write(f"quadratic coefficient in err ~ a delta + b delta^2: {summary['delta_fit']['quadratic_coefficient']:.15g}\n")
        f.write(f"quadratic-only coefficient: {summary['delta_fit']['quadratic_only_coefficient']:.15g}\n\n")

        f.write("6. Fixed-u weak-quench feasibility\n")
        f.write("----------------------------------\n")
        f.write("L, u, delta, mean_N, F2, F3, F4, VarY, VarY/F2, M_10pct, |R-K_F|\n")
        for r in fixed_u_rows:
            f.write(f"{r.L}, {r.u:.10g}, {r.delta:.15g}, {r.mean_N:.15g}, "
                    f"{r.F2:.15g}, {r.F3:.15g}, {r.F4:.15g}, "
                    f"{r.VarY:.15g}, {r.rare_pair_variance_ratio:.15g}, "
                    f"{r.M_10pct:.15g}, "
                    f"{r.abs_R_minus_KF:.15g}\n")
        f.write("\n")

        f.write("7. Equivalent multi-cone rule\n")
        f.write("-----------------------------\n")
        f.write("p, n_cones, K_single, K_n_cones, N_eff_n_cones\n")
        for r in multicone_rows:
            f.write(f"{r.p:.10g}, {r.n_cones}, {r.KF_single_cone:.15g}, "
                    f"{r.KF_n_cones:.15g}, {r.N_eff_n_cones:.15g}\n")


sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts/cleanroom"))
from common import candidate_run, safe_candidate_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Regenerate non-plotting numerical diagnostics for the channel-concentration paper.")
    parser.add_argument("--mode", choices=["fast", "publication"], default="publication",
                        help="publication reproduces the manuscript diagnostics; fast uses coarser grids.")
    parser.add_argument("--output-dir", default=None,
                        help="Directory for CSV/JSON/TXT outputs. Default: current candidate run data; frozen output is forbidden.")
    parser.add_argument("--run-root", type=Path)
    parser.add_argument("--paths-only", action="store_true", help="show candidate paths without scientific calculation")
    parser.add_argument("--no-write", action="store_true", help="Print the summary but do not write output files.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    project_root = Path(__file__).resolve().parents[2]
    run = candidate_run(args.run_root)
    outdir = safe_candidate_path(Path(args.output_dir)) if args.output_dir else run.data
    if outdir != run.data:
        raise ValueError("output must equal the selected run's candidate data directory")
    if args.paths_only:
        print(json.dumps({"run_root": str(run.root), "output_data": str(outdir), "scientific_compute": "NONE"}, indent=2))
        return

    if args.mode == "publication":
        params = {
            "nmax": 50000,
            "sector_Ls": [16, 24, 32, 48, 64, 96, 128, 192, 256, 384, 512, 768, 1024],
            "xy_L": 2000,
            "xy_point": (0.8, 0.5),
            "xy_n_phi": 241,
            "weak_L": 256,
            "weak_deltas": [1e-4, 2e-4, 5e-4, 1e-3, 2e-3],
            "fixed_u_Ls": [64, 128, 256],
            "fixed_u_values": [0.128, 0.256],
        }
    else:
        params = {
            "nmax": 15000,
            "sector_Ls": [16, 24, 32, 48, 64, 96, 128, 192, 256],
            "xy_L": 512,
            "xy_point": (0.8, 0.5),
            "xy_n_phi": 121,
            "weak_L": 128,
            "weak_deltas": [2e-4, 5e-4, 1e-3, 2e-3],
            "fixed_u_Ls": [64, 128, 256],
            "fixed_u_values": [0.128, 0.256],
        }

    sector_rows = compute_sector_rows(params["sector_Ls"])
    envelope_rows = compute_envelope_table()
    xy_h, xy_gamma = params["xy_point"]
    xy_rows = compute_xy_direction_scan(xy_h, xy_gamma, params["xy_L"], params["xy_n_phi"])
    weak_KF, weak_rows = compute_weak_quench_rows(1.0, 1.0, params["weak_L"], params["weak_deltas"])
    delta_fit = fit_delta_error(weak_KF, weak_rows)
    fixed_u_rows = compute_fixed_u_feasibility_rows(
        params["fixed_u_Ls"], params["fixed_u_values"]
    )
    multicone_rows = compute_multicone_rows([2.0, 6.0], [1, 2, 3, 4])

    summary = {
        "mode": args.mode,
        "Phi(0)": float(Phi(0.0, nmax=params["nmax"])),
        "KFcrit_p(2)": float(KFcrit_p(2.0)),
        "Psi(0)": float(Psi(0.0, nmax=params["nmax"])),
        "Ramond envelope": float(zeta(4.0) / (zeta(2.0) ** 2)),
        "weak_quench_KF_geom": weak_KF,
        "delta_fit": delta_fit,
        "parameters": params,
    }

    # Console summary.
    xy_max = max(xy_rows, key=lambda r: r.K_F)
    xy_min = min(xy_rows, key=lambda r: r.K_F)
    print("Numerical reproducibility diagnostics")
    print("=====================================")
    print(f"mode = {args.mode}")
    print(f"Phi(0) = {summary['Phi(0)']:.15g}")
    print(f"KFcrit_p(2) = {summary['KFcrit_p(2)']:.15g}")
    print(f"Psi(0) = {summary['Psi(0)']:.15g}")
    print(f"Ramond envelope = {summary['Ramond envelope']:.15g}")
    print(f"TFIM NS K_F at largest L = {sector_rows[-1].KF_NS_exact:.15g} for L={sector_rows[-1].L}")
    print(f"TFIM R  K_F at largest L = {sector_rows[-1].KF_R_exact:.15g} for L={sector_rows[-1].L}")
    print(f"XY max/min K_F = {xy_max.K_F:.15g} / {xy_min.K_F:.15g}; ratio = {xy_max.K_F / xy_min.K_F:.15g}")
    print(f"weak-quench K_F = {weak_KF:.15g}")
    print(f"quadratic-only delta-fit coefficient = {delta_fit['quadratic_only_coefficient']:.15g}")

    if not args.no_write:
        outdir.mkdir(parents=True, exist_ok=True)
        write_csv(outdir / "tfim_sector_contrast.csv", sector_rows)
        write_csv(outdir / "envelope_predictions_table.csv", envelope_rows)
        write_csv(outdir / "xy_directional_scan.csv", xy_rows)
        write_csv(outdir / "weak_quench_delta_budget.csv", weak_rows)
        write_csv(outdir / "weak_quench_fixed_u_feasibility.csv", fixed_u_rows)
        write_csv(outdir / "multicone_examples.csv", multicone_rows)
        with (outdir / "numerical_reproducibility_summary.json").open("w", encoding="utf-8") as f:
            json.dump({
                "summary": summary,
                "sector_rows": [asdict(r) for r in sector_rows],
                "envelope_rows": [asdict(r) for r in envelope_rows],
                "weak_quench_rows": [asdict(r) for r in weak_rows],
                "fixed_u_feasibility_rows": [asdict(r) for r in fixed_u_rows],
                "multicone_rows": [asdict(r) for r in multicone_rows],
            }, f, indent=2)
        write_text_summary(outdir / "numerical_reproducibility_summary.txt",
                           summary, sector_rows, envelope_rows, weak_rows,
                           fixed_u_rows, multicone_rows, xy_rows)
        print(f"\nwrote outputs to {outdir}")


if __name__ == "__main__":
    main()
