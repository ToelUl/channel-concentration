#!/usr/bin/env python3
"""Derive theory-guided Potts L^(-7/5) finite-size diagnostics.

This script performs deterministic regression on frozen publication data.  It
does not construct a Hamiltonian, diagonalize a matrix, or alter certified
receipts.
"""

from __future__ import annotations

import csv
import hashlib
import itertools
import json
import math
from pathlib import Path
import sys

import numpy as np
from scipy.optimize import least_squares


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/cleanroom"))
from common import candidate_run, safe_candidate_path
DATA = ROOT / "data/reproducibility"
POTTS_FSS = DATA / "potts_outcome_aware_fss.csv"
INTERACTING = DATA / "interacting_benchmarks.csv"
OLD_RECEIPT = DATA / "potts_outcome_aware_fit_receipt.json"
TAIL_RECEIPTS = {
    12: ROOT / "repro/evidence/potts_tail_calibration/06_L12_receipt.json",
    13: ROOT / "repro/evidence/potts_tail_calibration/08_L13_receipt.json",
    14: ROOT / "repro/evidence/potts_tail_calibration/10_L14_receipt.json",
}

OUT_SUMMARY = DATA / "potts_theory_guided_7over5_fit_summary.csv"
OUT_P2 = DATA / "potts_scaled_P2_7over5.csv"
OUT_RECEIPT = DATA / "potts_theory_guided_7over5_receipt.json"

EXPECTED_HASHES = {
    POTTS_FSS: "5becaea8426a1e8b84ffce0300fa4f646d52c8fc4afc28b4a5baaf5afd3a78b3",
    INTERACTING: "ed10ff3be1c5d6829e09850a565cda649c1a480e994ae7864da42f2b7c6d63d9",
    TAIL_RECEIPTS[12]: "08021ba1f5e9f085eefba09dca4dc2ccf3ad1c9b666f3d853efc6fd2f436d161",
    TAIL_RECEIPTS[13]: "c3c28864986adff6c6602461836a5b6d849c3df96909fc497b35f683d1e65e30",
    TAIL_RECEIPTS[14]: "04d33a0f9b6eb1a083dbc07bfeff029cf17140e9c38442aaa303a110c306482b",
}

CFT_TARGET = 0.8514956201179281
POWER_UV = 7.0 / 5.0
POWER_IRR = 4.0 / 5.0
POWER_IRR_SECOND = 8.0 / 5.0
P2_LEADING_POWER = 12.0 / 5.0


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require_inputs() -> None:
    for path, expected in EXPECTED_HASHES.items():
        actual = sha256(path)
        if actual != expected:
            raise RuntimeError(f"identity mismatch for {path}: {actual} != {expected}")
    with OLD_RECEIPT.open(encoding="utf-8") as handle:
        old = json.load(handle)
    if abs(float(old["cft_target"]) - CFT_TARGET) > 1e-15:
        raise RuntimeError("CFT target drifted from the frozen publication value")


def fit_free_intercept(L: np.ndarray, y: np.ndarray, powers: tuple[float, ...]) -> dict[str, object]:
    matrix = np.column_stack([np.ones_like(L)] + [L ** (-power) for power in powers])
    coefficients, _, _, _ = np.linalg.lstsq(matrix, y, rcond=None)
    residual = y - matrix @ coefficients
    rss = float(residual @ residual)
    return {
        "intercept": float(coefficients[0]),
        "amplitudes": [float(value) for value in coefficients[1:]],
        "rss": rss,
        "rmse": math.sqrt(rss / len(L)),
        "max_abs_residual": float(np.max(np.abs(residual))),
        "condition_number": float(np.linalg.cond(matrix)),
    }


def fit_fixed_intercept(
    L: np.ndarray, y: np.ndarray, intercept: float, powers: tuple[float, ...]
) -> dict[str, object]:
    matrix = np.column_stack([L ** (-power) for power in powers])
    coefficients, _, _, _ = np.linalg.lstsq(matrix, y - intercept, rcond=None)
    residual = y - (intercept + matrix @ coefficients)
    rss = float(residual @ residual)
    return {
        "intercept": float(intercept),
        "amplitudes": [float(value) for value in coefficients],
        "rss": rss,
        "rmse": math.sqrt(rss / len(L)),
        "max_abs_residual": float(np.max(np.abs(residual))),
        "condition_number": float(np.linalg.cond(matrix)),
    }


def loocv_free_intercept(L: np.ndarray, y: np.ndarray, powers: tuple[float, ...]) -> float:
    errors = []
    for index in range(len(L)):
        keep = np.arange(len(L)) != index
        fit = fit_free_intercept(L[keep], y[keep], powers)
        prediction = float(fit["intercept"])
        prediction += sum(
            amplitude * L[index] ** (-power)
            for amplitude, power in zip(fit["amplitudes"], powers)
        )
        errors.append(y[index] - prediction)
    return float(np.sqrt(np.mean(np.square(errors))))


def loocv_fixed_intercept(
    L: np.ndarray, y: np.ndarray, intercept: float, powers: tuple[float, ...]
) -> float:
    errors = []
    for index in range(len(L)):
        keep = np.arange(len(L)) != index
        fit = fit_fixed_intercept(L[keep], y[keep], intercept, powers)
        prediction = intercept + sum(
            amplitude * L[index] ** (-power)
            for amplitude, power in zip(fit["amplitudes"], powers)
        )
        errors.append(y[index] - prediction)
    return float(np.sqrt(np.mean(np.square(errors))))


def fit_free_power(L: np.ndarray, y: np.ndarray) -> dict[str, object]:
    initial = np.array([float(y[-1]), -0.04, 1.4])

    def residual(parameters: np.ndarray) -> np.ndarray:
        intercept, amplitude, omega = parameters
        return y - (intercept + amplitude * L ** (-omega))

    result = least_squares(
        residual,
        initial,
        bounds=([-np.inf, -np.inf, 0.05], [np.inf, np.inf, 5.0]),
        xtol=1e-14,
        ftol=1e-14,
        gtol=1e-14,
        max_nfev=200000,
    )
    rss = float(result.fun @ result.fun)
    return {
        "intercept": float(result.x[0]),
        "amplitude": float(result.x[1]),
        "omega": float(result.x[2]),
        "rss": rss,
        "rmse": math.sqrt(rss / len(L)),
        "max_abs_residual": float(np.max(np.abs(result.fun))),
        "jacobian_condition_number": float(np.linalg.cond(result.jac)),
        "success": bool(result.success),
    }


def read_kf() -> tuple[np.ndarray, np.ndarray, list[dict[str, str]]]:
    with POTTS_FSS.open(newline="", encoding="utf-8") as handle:
        rows = [row for row in csv.DictReader(handle) if row["primary_fit"] == "True"]
    rows.sort(key=lambda row: int(row["L"]))
    L = np.array([float(row["L"]) for row in rows])
    values = np.array([float(row["midpoint"]) for row in rows])
    if list(map(int, L)) != list(range(6, 15)):
        raise RuntimeError("the primary Potts K_F sequence must be L=6,...,14")
    return L, values, rows


def read_p2() -> tuple[np.ndarray, np.ndarray, list[dict[str, object]]]:
    with INTERACTING.open(newline="", encoding="utf-8") as handle:
        benchmark = {
            int(row["L"]): float(row["P2"])
            for row in csv.DictReader(handle)
            if row["model"] == "Potts"
        }
    rows: list[dict[str, object]] = []
    for size in range(6, 12):
        rows.append({"L": size, "P2": benchmark[size], "layer": "released_point"})
    for size, path in TAIL_RECEIPTS.items():
        with path.open(encoding="utf-8") as handle:
            receipt = json.load(handle)
        lower, upper = map(float, receipt["ground_and_P2"]["P2_interval"])
        rows.append(
            {
                "L": size,
                "P2": 0.5 * (lower + upper),
                "P2_lower": lower,
                "P2_upper": upper,
                "layer": "certified_interval_midpoint",
            }
        )
    rows.sort(key=lambda row: int(row["L"]))
    L = np.array([float(row["L"]) for row in rows])
    values = np.array([float(row["P2"]) for row in rows])
    return L, values, rows


def endpoint_envelope(kf_rows: list[dict[str, str]], power: float) -> dict[str, object]:
    variable = [row for row in kf_rows if float(row["upper"]) > float(row["lower"])]
    records = []
    for choices in itertools.product(("lower", "upper"), repeat=len(variable)):
        values_by_l = {int(row["L"]): float(row["midpoint"]) for row in kf_rows}
        for row, choice in zip(variable, choices):
            values_by_l[int(row["L"])] = float(row[choice])
        sizes = np.array(sorted(values_by_l), dtype=float)
        values = np.array([values_by_l[int(size)] for size in sizes])
        fit = fit_free_intercept(sizes, values, (power,))
        records.append({"choices": list(choices), "intercept": fit["intercept"]})
    intercepts = [float(record["intercept"]) for record in records]
    return {
        "corner_count": len(records),
        "intercept_min": min(intercepts),
        "intercept_max": max(intercepts),
        "intercept_width": max(intercepts) - min(intercepts),
        "all_corners": records,
    }


def summary_row(
    observable: str,
    model: str,
    minimum_size: int,
    maximum_size: int,
    powers: tuple[float, ...],
    fit: dict[str, object],
    loocv_rmse: float | None,
    evidence_layer: str,
) -> dict[str, object]:
    amplitudes = list(fit.get("amplitudes", []))
    return {
        "observable": observable,
        "model": model,
        "L_min": minimum_size,
        "L_max": maximum_size,
        "powers": "+".join(f"{value:.12g}" for value in powers),
        "intercept": fit.get("intercept", ""),
        "amplitude_1": amplitudes[0] if amplitudes else fit.get("amplitude", ""),
        "amplitude_2": amplitudes[1] if len(amplitudes) > 1 else "",
        "omega_free": fit.get("omega", ""),
        "rmse": fit["rmse"],
        "loocv_rmse": "" if loocv_rmse is None else loocv_rmse,
        "max_abs_residual": fit["max_abs_residual"],
        "condition_number": fit.get("condition_number", fit.get("jacobian_condition_number", "")),
        "evidence_layer": evidence_layer,
    }


def main() -> None:
    global DATA, POTTS_FSS, INTERACTING, OLD_RECEIPT, OUT_SUMMARY, OUT_P2, OUT_RECEIPT, EXPECTED_HASHES
    run = candidate_run()
    frozen_data = DATA
    DATA = run.data
    POTTS_FSS = DATA / POTTS_FSS.name
    INTERACTING = DATA / INTERACTING.name
    OLD_RECEIPT = DATA / OLD_RECEIPT.name
    OUT_SUMMARY = safe_candidate_path(DATA / OUT_SUMMARY.name)
    OUT_P2 = safe_candidate_path(DATA / OUT_P2.name)
    OUT_RECEIPT = safe_candidate_path(DATA / OUT_RECEIPT.name)
    # The expected scientific hashes do not change; only the explicit candidate read location changes.
    EXPECTED_HASHES = {(DATA / path.name if path.parent == frozen_data else path): digest for path, digest in EXPECTED_HASHES.items()}
    require_inputs()
    L, kf, kf_rows = read_kf()
    p2_L, p2, p2_rows = read_p2()
    scaled_p2 = p2 / p2_L ** P2_LEADING_POWER

    summary: list[dict[str, object]] = []
    primary_windows: dict[str, object] = {}
    for minimum_size in range(6, 11):
        use = L >= minimum_size
        fit = fit_free_intercept(L[use], kf[use], (POWER_UV,))
        fit["signed_relative_deviation_percent"] = 100.0 * (
            float(fit["intercept"]) - CFT_TARGET
        ) / CFT_TARGET
        cv = loocv_free_intercept(L[use], kf[use], (POWER_UV,))
        primary_windows[str(minimum_size)] = {**fit, "loocv_rmse": cv}
        summary.append(
            summary_row(
                "K_F",
                "Kinf+b*L^(-7/5)",
                minimum_size,
                14,
                (POWER_UV,),
                fit,
                cv,
                "primary_theory_guided_free_intercept",
            )
        )

    legacy = fit_free_intercept(L, kf, (1.0,))
    summary.append(
        summary_row(
            "K_F", "Kinf+a/L", 6, 14, (1.0,), legacy,
            loocv_free_intercept(L, kf, (1.0,)), "empirical_comparator"
        )
    )
    quadratic = fit_free_intercept(L, kf, (1.0, 2.0))
    summary.append(
        summary_row(
            "K_F", "Kinf+a/L+b/L^2", 6, 14, (1.0, 2.0), quadratic,
            loocv_free_intercept(L, kf, (1.0, 2.0)), "empirical_comparator"
        )
    )

    fixed_models = [
        ("KCFT+b*L^(-7/5)", (POWER_UV,)),
        ("KCFT+a*L^(-4/5)+b*L^(-7/5)", (POWER_IRR, POWER_UV)),
        ("KCFT+c*L^(-8/5)", (POWER_IRR_SECOND,)),
        ("KCFT+d*L^(-2)", (2.0,)),
    ]
    fixed_results = {}
    for name, powers in fixed_models:
        fit = fit_fixed_intercept(L, kf, CFT_TARGET, powers)
        cv = loocv_fixed_intercept(L, kf, CFT_TARGET, powers)
        fixed_results[name] = {**fit, "loocv_rmse": cv}
        summary.append(
            summary_row(
                "K_F", name, 6, 14, powers, fit, cv,
                "fixed_CFT_mechanism_diagnostic"
            )
        )

    p2_fixed = {}
    for name, powers in (
        ("A2+B2*L^(-4/5)", (POWER_IRR,)),
        ("A2+B2*L^(-7/5)", (POWER_UV,)),
        ("A2+B2*L^(-8/5)", (POWER_IRR_SECOND,)),
        ("A2+B2*L^(-2)", (2.0,)),
        ("A2+B1*L^(-4/5)+B2*L^(-7/5)", (POWER_IRR, POWER_UV)),
    ):
        fit = fit_free_intercept(p2_L, scaled_p2, powers)
        cv = loocv_free_intercept(p2_L, scaled_p2, powers)
        p2_fixed[name] = {**fit, "loocv_rmse": cv}
        summary.append(
            summary_row(
                "P2/L^(12/5)", name, 6, 14, powers, fit, cv,
                "scale_correction_diagnostic"
            )
        )

    p2_free_power_windows = {}
    for minimum_size in range(6, 11):
        use = p2_L >= minimum_size
        fit = fit_free_power(p2_L[use], scaled_p2[use])
        p2_free_power_windows[str(minimum_size)] = fit
        summary.append(
            summary_row(
                "P2/L^(12/5)", "A2+B2*L^(-omega)", minimum_size, 14,
                tuple(), fit, None, "exploratory_free_exponent_diagnostic"
            )
        )

    fields = list(summary[0])
    with OUT_SUMMARY.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(summary)

    for row, value in zip(p2_rows, scaled_p2):
        row["scaled_P2"] = float(value)
        row["L_minus_7_over_5"] = float(int(row["L"]) ** (-POWER_UV))
    p2_fields = sorted({key for row in p2_rows for key in row})
    with OUT_P2.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=p2_fields)
        writer.writeheader()
        writer.writerows(p2_rows)

    primary = primary_windows["6"]
    receipt = {
        "schema": "channel-concentration.potts-theory-guided-7over5.v1",
        "decision_id": "POTTS-FSS-7/5-INTEGRATION-R1/OPTION-A",
        "status": "POST_OUTCOME_THEORY_GUIDED_INTEGRATION",
        "scientific_compute_performed": False,
        "input_hashes": {str(path.relative_to(ROOT)): expected for path, expected in EXPECTED_HASHES.items()},
        "theory_contract": {
            "thermal_scaling_dimension": 4.0 / 5.0,
            "response_RG_eigenvalue": 6.0 / 5.0,
            "singular_P2_power": P2_LEADING_POWER,
            "analytic_background_power": 1.0,
            "relative_analytic_background_correction": POWER_UV,
            "claim": "accessible-size analytic-background correction, not unique asymptotic exponent",
        },
        "cft_target": CFT_TARGET,
        "primary_KF_contract": {
            "model": "unweighted_OLS_Kinf_plus_b_L_minus_7_over_5",
            "sizes": list(range(6, 15)),
            "interval_representative": "deterministic_midpoint",
            "fit": primary,
            "window_fits": primary_windows,
            "certified_endpoint_envelope": endpoint_envelope(kf_rows, POWER_UV),
        },
        "scale_diagnostics": {
            "fixed_power_models": p2_fixed,
            "free_power_windows": p2_free_power_windows,
        },
        "fixed_CFT_mechanism_diagnostics": fixed_results,
        "empirical_comparators": {"linear_1_over_L": legacy, "quadratic_1_over_L": quadratic},
        "claim_ceiling": "THEORY_GUIDED_ACCESSIBLE_SIZE_EXTRAPOLATION; NO_UNIQUE_ASYMPTOTIC_EXPONENT",
    }
    with OUT_RECEIPT.open("w", encoding="utf-8") as handle:
        json.dump(receipt, handle, indent=2, sort_keys=True)
        handle.write("\n")

    print(json.dumps({
        "status": "PASS",
        "Kinf_7over5": primary["intercept"],
        "signed_CFT_deviation_percent": primary["signed_relative_deviation_percent"],
        "P2_free_omega_L6_L14": p2_free_power_windows["6"]["omega"],
        "outputs": [str(OUT_SUMMARY.relative_to(ROOT)), str(OUT_P2.relative_to(ROOT)), str(OUT_RECEIPT.relative_to(ROOT))],
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
