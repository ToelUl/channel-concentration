#!/usr/bin/env python3
"""Verify the Potts full-k0 convention and its charge-neutral response support."""

from __future__ import annotations

import argparse
import csv
import os
import sys
from pathlib import Path

# Stabilize the dense LAPACK reductions used only by this finite-size verifier.
# The acceptance tolerances are unchanged; this makes the recorded CSV portable
# across repeated runs on a threaded BLAS host.
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"

import numpy as np
import scipy.sparse as sp
import scipy.sparse.linalg as spla


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "simulation"))
import simulate_interacting_benchmarks as engine  # noqa: E402


DEFAULT_OUTPUT = ROOT / "data" / "reproducibility" / "potts_charge_sector_checks.csv"
LEAKAGE_TOL = 1.0e-10
ALGEBRA_TOL = 1.0e-11
MOMENT_TOL = 1.0e-10


def add(
    rows: list[dict[str, str]],
    check: str,
    case: str,
    direct: float | int,
    expected: float | int,
    error: float,
    tolerance: float,
    note: str,
) -> int:
    passed = error <= tolerance
    rows.append({
        "check": check,
        "case": case,
        "direct_value": f"{direct:.17g}" if isinstance(direct, float) else str(direct),
        "expected_value": f"{expected:.17g}" if isinstance(expected, float) else str(expected),
        "abs_error": f"{error:.6e}",
        "tolerance": f"{tolerance:.6e}",
        "status": "PASS" if passed else "FAIL",
        "note": note,
    })
    return 0 if passed else 1


def dense_result(H: sp.spmatrix, dH: sp.spmatrix) -> dict:
    return engine.dense_level_projector_kf(H.toarray(), dH.toarray())


def run_checks() -> tuple[list[dict[str, str]], int]:
    rows: list[dict[str, str]] = []
    failures = 0

    # Symmetry algebra, explicit q=0 isometry, and state/response leakage.
    for L in (4, 5, 6, 7, 8):
        H, dH, dim_k0 = engine.build_potts_k0(L)
        color_shift = engine.potts_k0_color_shift(L)
        H_q0, dH_q0, isometry = engine.build_potts_k0_q0(L)
        identity_k0 = sp.identity(dim_k0, format="csr")
        identity_q0 = sp.identity(isometry.shape[1], format="csr")
        algebra_cases = (
            ("color_shift_order", spla.norm(color_shift @ color_shift @ color_shift - identity_k0)),
            ("hamiltonian_commutator", spla.norm(H @ color_shift - color_shift @ H)),
            ("perturbation_commutator", spla.norm(dH @ color_shift - color_shift @ dH)),
            ("q0_isometry", spla.norm(isometry.T @ isometry - identity_q0)),
        )
        for check, error in algebra_cases:
            failures += add(
                rows, check, f"L={L}", float(error), 0.0, float(error), ALGEBRA_TOL,
                "global color shift C=prod_j tau_j; explicit q=0 columns are orthonormal",
            )

        _, evecs = np.linalg.eigh(H.toarray())
        psi0 = evecs[:, 0]
        response = dH @ psi0
        response = response - psi0 * float(psi0 @ response)
        for name, vector in (("ground_charge_leakage", psi0), ("response_charge_leakage", response)):
            leakage = engine.potts_q0_leakage(vector, L)
            failures += add(
                rows, name, f"L={L}", leakage, 0.0, leakage, LEAKAGE_TOL,
                "frozen relative-norm tolerance for support outside q=0",
            )

        result_k0 = engine.dense_level_projector_kf(H.toarray(), dH.toarray())
        result_q0 = engine.dense_level_projector_kf(H_q0.toarray(), dH_q0.toarray())
        for moment in ("P2", "P4", "KF"):
            direct = float(result_k0[moment])
            expected = float(result_q0[moment])
            error = abs(direct - expected)
            failures += add(
                rows, f"k0_q0_{moment}", f"L={L}", direct, expected, error, MOMENT_TOL,
                "full k=0 and explicit (k=0,q=0) level-projector moments agree",
            )

    # Required L=6 three-representation spot comparison.
    L = 6
    H_full, dH_full = engine.build_potts_full(L)
    H_k0, dH_k0, _ = engine.build_potts_k0(L)
    H_q0, dH_q0, _ = engine.build_potts_k0_q0(L)
    results = {
        "full": engine.dense_level_projector_kf(H_full, dH_full),
        "full-k0": dense_result(H_k0, dH_k0),
        "explicit-q0": dense_result(H_q0, dH_q0),
    }
    reference = results["explicit-q0"]
    for representation in ("full", "full-k0"):
        for moment in ("P2", "P4", "KF"):
            direct = float(results[representation][moment])
            expected = float(reference[moment])
            error = abs(direct - expected)
            failures += add(
                rows, f"three_representation_{moment}", f"L=6,{representation}",
                direct, expected, error, MOMENT_TOL,
                "full space, full k=0 block, and explicit q=0 response give identical moments",
            )

    dimensions = {"full": 3**L, "full-k0": H_k0.shape[0], "explicit-q0": H_q0.shape[0]}
    for representation, direct in dimensions.items():
        expected = {"full": 729, "full-k0": 130, "explicit-q0": 46}[representation]
        failures += add(
            rows, "representation_dimension", f"L=6,{representation}", direct, expected,
            float(abs(direct - expected)), 0.0,
            "dimension labels distinguish the diagonalized block from response support",
        )

    return rows, failures


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--no-write", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    rows, failures = run_checks()
    if not args.no_write:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    passed = sum(row["status"] == "PASS" for row in rows)
    print(f"Potts charge sector: {passed} PASS, {failures} FAIL")
    print(f"output: {'not written' if args.no_write else args.output}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
