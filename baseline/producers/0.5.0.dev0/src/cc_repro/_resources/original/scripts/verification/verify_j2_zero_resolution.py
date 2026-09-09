#!/usr/bin/env python3
"""Match the J2=0 level-projector ED resolution to the exact TFIM channels.

The main benchmark plots the exact NS momentum-block result at J2=0.  This
check follows the interacting path instead: it diagonalizes the k=0,
spin-flip-even orbit-sector Hamiltonian, groups each degenerate many-body level
into one projector, and compares P2, P4, and K_F with the exact momentum-block
formulas.  A tolerance scan verifies that the match is not an artifact of the
chosen degeneracy threshold.
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import numpy as np
import scipy.linalg as la


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "simulation"))

from simulate_interacting_benchmarks import (  # noqa: E402
    build_nnn_tfim_sector_k0_even,
    group_level_weights,
)


SIZES = (6, 8, 10, 12)
GROUP_TOLS = (1e-10, 1e-8, 1e-7, 1e-6)
PRIMARY_GROUP_TOL = 1e-7
ABS_TOL = 5e-12


def exact_moments(L: int) -> tuple[float, float, float]:
    """Return exact critical NS momentum-block P2, P4, and K_F."""
    p2 = L * (L - 1.0) / 32.0
    p4 = L * (L - 1.0) * (L * L + L - 3.0) / 1536.0
    kf = (2.0 / 3.0) * (L * L + L - 3.0) / (L * (L - 1.0))
    return p2, p4, kf


def level_projector_rows() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for L in SIZES:
        H, dH, dim = build_nnn_tfim_sector_k0_even(L, h=1.0, j2=0.0)
        evals, evecs = la.eigh(H.toarray())
        e0 = float(evals[0])
        psi0 = evecs[:, 0]
        source = dH @ psi0
        source = source - float(psi0 @ source) * psi0
        amplitudes2 = np.abs(evecs.T @ source) ** 2
        p2_exact, p4_exact, kf_exact = exact_moments(L)

        kf_scan: list[float] = []
        pending: list[dict[str, object]] = []
        for group_tol in GROUP_TOLS:
            weights = group_level_weights(evals, amplitudes2, e0, group_tol)
            p2 = float(np.sum(weights))
            p4 = float(np.sum(weights**2))
            kf = p4 / p2**2
            kf_scan.append(kf)
            pending.append({
                "L": L,
                "sector_dimension": dim,
                "group_tolerance": f"{group_tol:.0e}",
                "is_primary_tolerance": group_tol == PRIMARY_GROUP_TOL,
                "n_level_projectors": len(weights),
                "P2_projector": f"{p2:.16g}",
                "P2_exact": f"{p2_exact:.16g}",
                "P2_abs_error": f"{abs(p2 - p2_exact):.3e}",
                "P4_projector": f"{p4:.16g}",
                "P4_exact": f"{p4_exact:.16g}",
                "P4_abs_error": f"{abs(p4 - p4_exact):.3e}",
                "KF_projector": f"{kf:.16g}",
                "KF_exact": f"{kf_exact:.16g}",
                "KF_abs_error": f"{abs(kf - kf_exact):.3e}",
            })

        scan_spread = max(kf_scan) - min(kf_scan)
        for row in pending:
            errors = (
                float(row["P2_abs_error"]),
                float(row["P4_abs_error"]),
                float(row["KF_abs_error"]),
            )
            passed = max(errors) < ABS_TOL and scan_spread < ABS_TOL
            row["KF_tolerance_scan_spread"] = f"{scan_spread:.3e}"
            row["status"] = "PASS" if passed else "FAIL"
            rows.append(row)
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "data" / "reproducibility" / "tfim_j2_zero_resolution_match.csv",
    )
    parser.add_argument("--no-write", action="store_true")
    args = parser.parse_args()

    rows = level_projector_rows()
    fields = list(rows[0])
    if not args.no_write:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
        print(f"wrote {args.output}")

    for row in rows:
        if row["is_primary_tolerance"]:
            print(
                f"L={row['L']:>2} dim={row['sector_dimension']:>3} "
                f"K_F(ED)={row['KF_projector']} K_F(exact)={row['KF_exact']} "
                f"error={row['KF_abs_error']} scan={row['KF_tolerance_scan_spread']} "
                f"{row['status']}"
            )
    if any(row["status"] != "PASS" for row in rows):
        raise SystemExit("J2=0 matched-resolution calibration failed")


if __name__ == "__main__":
    main()
