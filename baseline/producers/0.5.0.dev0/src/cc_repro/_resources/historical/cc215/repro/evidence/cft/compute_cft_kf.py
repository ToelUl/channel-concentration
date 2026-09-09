#!/usr/bin/env python3
"""Verification-first calculations for KF-CFT-2026-001.

The program is deliberately read-only with respect to the rev1c package and prints a
JSON record to stdout.  It implements two independent infinite-sum routes:

1. mpmath's convergence-accelerated direct sum of the CFT spectral coefficients;
2. Laplace/hypergeometric integral representations of the same two moments.

It also runs exact Ising, deliberately wrong-coefficient, cutoff-scaling, Potts-data,
split/merge, Ramond, and XX retained-evidence controls frozen in TST-001--TST-009.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
from fractions import Fraction
from pathlib import Path

import mpmath as mp
import numpy as np


ROOT = Path(__file__).resolve().parents[4]
PACKAGE = (
    ROOT
    / "work"
    / "kf_cft_rev1c_baseline"
    / "Channel_Concentration_rev1c_reproducible_package"
)
DATA = PACKAGE / "data" / "reproducibility"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def coefficient(delta: mp.mpf, n: mp.mpf) -> mp.mpf:
    return (mp.rf(delta, n) / mp.gamma(n + 1)) ** 2


def weight(delta: mp.mpf, n: mp.mpf) -> mp.mpf:
    return coefficient(delta, n) / (delta + 2 * n) ** 2


def bernoulli_numbers(order: int) -> list[Fraction]:
    """Conventional Bernoulli numbers with B_1=-1/2."""
    values = [Fraction(1)]
    for m in range(1, order + 1):
        subtotal = sum(
            Fraction(math.comb(m + 1, k)) * values[k] for k in range(m)
        )
        values.append(-subtotal / Fraction(m + 1))
    return values


def bernoulli_polynomial(
    order: int, x: Fraction, bernoulli: list[Fraction]
) -> Fraction:
    return sum(
        Fraction(math.comb(order, k)) * bernoulli[k] * x ** (order - k)
        for k in range(order + 1)
    )


def asymptotic_weight_coefficients(
    delta_fraction: Fraction, order: int, squared: bool
) -> tuple[mp.mpf, list[mp.mpf]]:
    """Return exponent and coefficients in w_n^(1 or 2) ~ n^-exponent sum c_k/n^k."""
    delta = mp.mpf(delta_fraction.numerator) / delta_fraction.denominator
    bernoulli = bernoulli_numbers(order + 1)
    log_coefficients = [mp.mpf(0)] * (order + 1)
    for k in range(1, order + 1):
        b_delta = bernoulli_polynomial(k + 1, delta_fraction, bernoulli)
        b_one = bernoulli_polynomial(k + 1, Fraction(1), bernoulli)
        ratio_fraction = (
            Fraction((-1) ** (k + 1), k * (k + 1)) * (b_delta - b_one)
        )
        denominator_fraction = (
            -2
            * Fraction((-1) ** (k + 1), k)
            * (delta_fraction / 2) ** k
        )
        log_fraction = 2 * ratio_fraction + denominator_fraction
        log_coefficients[k] = (
            mp.mpf(log_fraction.numerator) / log_fraction.denominator
        )

    multiplier = 2 if squared else 1
    log_coefficients = [multiplier * item for item in log_coefficients]
    leading = (1 / (4 * mp.gamma(delta) ** 2)) ** multiplier
    coefficients = [leading] + [mp.mpf(0)] * order
    # If C(x)=exp(L(x)), then n*c_n=sum_{k=1}^n k*l_k*c_{n-k}.
    for n in range(1, order + 1):
        coefficients[n] = (
            sum(
                k * log_coefficients[k] * coefficients[n - k]
                for k in range(1, n + 1)
            )
            / n
        )
    exponent = multiplier * (4 * delta * 0 + (4 - 2 * delta))
    return exponent, coefficients


def recurrence_tail_moments(
    delta_fraction: Fraction, cutoff: int = 1000, order: int = 30
) -> tuple[mp.mpf, mp.mpf]:
    """Coefficient recurrence plus a Bernoulli/Hurwitz-zeta asymptotic tail."""
    delta = mp.mpf(delta_fraction.numerator) / delta_fraction.denominator
    a_n = mp.mpf(1)
    s1 = mp.mpf(0)
    s2 = mp.mpf(0)
    for n in range(cutoff):
        w_n = a_n / (delta + 2 * n) ** 2
        s1 += w_n
        s2 += w_n**2
        a_n *= ((delta + n) / (n + 1)) ** 2

    exponent_1, coefficients_1 = asymptotic_weight_coefficients(
        delta_fraction, order, squared=False
    )
    exponent_2, coefficients_2 = asymptotic_weight_coefficients(
        delta_fraction, order, squared=True
    )
    tail_1 = sum(
        coefficient_k * mp.zeta(exponent_1 + k, cutoff)
        for k, coefficient_k in enumerate(coefficients_1)
    )
    tail_2 = sum(
        coefficient_k * mp.zeta(exponent_2 + k, cutoff)
        for k, coefficient_k in enumerate(coefficients_2)
    )
    return s1 + tail_1, s2 + tail_2


def beta_integral_hypergeometric_moments(
    delta_fraction: Fraction,
) -> tuple[mp.mpf, mp.mpf]:
    """Analytic evaluation of the registered Laplace integrals at unit argument."""
    delta = mp.mpf(delta_fraction.numerator) / delta_fraction.denominator
    half = delta / 2
    s1 = (
        mp.hyper(
            [delta, delta, half, half],
            [1, half + 1, half + 1],
            1,
        )
        / delta**2
    )
    s2 = (
        mp.hyper(
            [delta, delta, delta, delta, half, half, half, half],
            [1, 1, 1, half + 1, half + 1, half + 1, half + 1],
            1,
        )
        / delta**4
    )
    return s1, s2


def _s1_integrand(u: mp.mpf, delta: mp.mpf) -> mp.mpf:
    if u == 0:
        if delta == 1:
            return mp.mpf("0.5")
        return mp.mpf("0")
    if delta == 1:
        # hyp2f1(1,1;1;e^-2u)=1/(1-e^-2u), written without cancellation.
        return u / (2 * mp.sinh(u))
    z = mp.exp(-2 * u)
    if z == 1:
        # At finite working precision this can occur only at quadrature nodes
        # exponentially closer to the endpoint than the requested accuracy.
        return mp.mpf("0")
    return u * mp.exp(-delta * u) * mp.hyp2f1(delta, delta, 1, z)


def _s2_integrand(u: mp.mpf, delta: mp.mpf) -> mp.mpf:
    if u == 0:
        return mp.mpf("0")
    if delta == 1:
        # hyper([1]^4;[1]^3;e^-2u)=1/(1-e^-2u).
        return u**3 / (12 * mp.sinh(u))
    z = mp.exp(-2 * u)
    if z == 1:
        return mp.mpf("0")
    return (
        u**3
        * mp.exp(-delta * u)
        * mp.hyper([delta, delta, delta, delta], [1, 1, 1], z)
        / 6
    )


def integral_moments(delta: mp.mpf) -> tuple[mp.mpf, mp.mpf]:
    # Splits resolve the integrable endpoint singularity at u=0 and exponential tail.
    intervals = [0, mp.mpf("1e-8"), mp.mpf("1e-5"), mp.mpf("1e-3"),
                 mp.mpf("0.05"), mp.mpf("0.5"), mp.mpf("3"), mp.inf]
    s1 = mp.quad(lambda u: _s1_integrand(u, delta), intervals)
    s2 = mp.quad(lambda u: _s2_integrand(u, delta), intervals)
    return s1, s2


def mp_text(value: mp.mpf, digits: int = 60) -> str:
    return mp.nstr(value, digits)


def exact_and_failure_controls() -> dict:
    delta = mp.mpf(1)
    s1, s2 = recurrence_tail_moments(Fraction(1))
    exact_s1 = mp.pi**2 / 8
    exact_s2 = mp.pi**4 / 96
    exact_k = mp.mpf(2) / 3

    potts_delta = mp.mpf(4) / 5
    wrong_s1 = mp.nsum(
        lambda n: 1 / (potts_delta + 2 * n) ** 2, [0, mp.inf]
    )
    wrong_s2 = mp.nsum(
        lambda n: 1 / (potts_delta + 2 * n) ** 4, [0, mp.inf]
    )
    return {
        "ising_oracle": {
            "s1_error": mp_text(abs(s1 - exact_s1)),
            "s2_error": mp_text(abs(s2 - exact_s2)),
            "k_error": mp_text(abs(s2 / s1**2 - exact_k)),
            "passed_1e-30": bool(
                abs(s1 - exact_s1) < mp.mpf("1e-30")
                and abs(s2 - exact_s2) < mp.mpf("1e-30")
                and abs(s2 / s1**2 - exact_k) < mp.mpf("1e-30")
            ),
        },
        "wrong_flat_coefficient_delta_4_5": {
            "s1": mp_text(wrong_s1),
            "s2": mp_text(wrong_s2),
            "k": mp_text(wrong_s2 / wrong_s1**2),
            "purpose": "planned failure probe: omitting the Pochhammer coefficient",
        },
    }


def compute_delta(delta_text: str) -> dict:
    delta_fraction = Fraction(delta_text)
    delta = mp.mpf(delta_fraction.numerator) / delta_fraction.denominator
    direct_s1, direct_s2 = recurrence_tail_moments(delta_fraction)
    integral_s1, integral_s2 = beta_integral_hypergeometric_moments(
        delta_fraction
    )
    direct_k = direct_s2 / direct_s1**2
    integral_k = integral_s2 / integral_s1**2
    return {
        "delta": mp_text(delta),
        "coefficient_recurrence_plus_asymptotic_tail": {
            "s1": mp_text(direct_s1),
            "s2": mp_text(direct_s2),
            "k": mp_text(direct_k),
        },
        "beta_integral_hypergeometric_closed_form": {
            "s1": mp_text(integral_s1),
            "s2": mp_text(integral_s2),
            "k": mp_text(integral_k),
        },
        "absolute_differences": {
            "s1": mp_text(abs(direct_s1 - integral_s1)),
            "s2": mp_text(abs(direct_s2 - integral_s2)),
            "k": mp_text(abs(direct_k - integral_k)),
        },
        "routes_agree_1e-20": bool(
            abs(direct_s1 - integral_s1) < mp.mpf("1e-20")
            and abs(direct_s2 - integral_s2) < mp.mpf("1e-20")
            and abs(direct_k - integral_k) < mp.mpf("1e-20")
        ),
    }


def truncated_k_series(delta: float, cutoffs: list[int]) -> dict:
    max_n = max(cutoffs)
    a = 1.0
    s1 = 0.0
    s2 = 0.0
    by_n: dict[int, float] = {}
    cutoff_set = set(cutoffs)
    for n in range(max_n):
        w = a / (delta + 2.0 * n) ** 2
        s1 += w
        s2 += w * w
        if n + 1 in cutoff_set:
            by_n[n + 1] = s2 / (s1 * s1)
        a *= ((delta + n) / (n + 1.0)) ** 2

    x = np.log(np.asarray(cutoffs[-4:], dtype=float))
    y = np.log(np.asarray([by_n[n] for n in cutoffs[-4:]], dtype=float))
    slope = float(np.polyfit(x, y, 1)[0])
    if math.isclose(delta, 1.75):
        transformed = np.asarray(
            [by_n[n] / math.log(n) for n in cutoffs[-4:]], dtype=float
        )
        transformed_slope = float(np.polyfit(x, np.log(transformed), 1)[0])
    elif math.isclose(delta, 1.5):
        transformed = np.asarray(
            [by_n[n] * math.log(n) ** 2 for n in cutoffs[-4:]], dtype=float
        )
        transformed_slope = float(np.polyfit(x, np.log(transformed), 1)[0])
    else:
        transformed_slope = None
    return {
        "delta": delta,
        "p": 4.0 - 2.0 * delta,
        "cutoff_k": {str(n): by_n[n] for n in cutoffs},
        "raw_log_slope_last_four": slope,
        "transformed_log_slope_last_four": transformed_slope,
    }


def cutoff_controls() -> list[dict]:
    cutoffs = [1000, 3000, 10000, 30000, 100000, 300000, 1000000]
    return [
        truncated_k_series(delta, cutoffs)
        for delta in [1.4, 1.5, 1.6, 1.75, 1.9]
    ]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def retained_evidence(potts_k: float) -> dict:
    interacting = read_csv(DATA / "interacting_benchmarks.csv")
    potts_rows = [row for row in interacting if row["model"] == "Potts"]
    potts_values = [float(row["KF"]) for row in potts_rows]
    potts_sizes = [int(row["L"]) for row in potts_rows]
    fits = read_csv(DATA / "potts_alternative_fit_summary.csv")
    fit_values = [float(row["K_infty"]) for row in fits]
    pure_tail = float(
        mp.nsum(lambda n: 1 / (2 * n + 1) ** (mp.mpf(24) / 5), [0, mp.inf])
        / mp.nsum(lambda n: 1 / (2 * n + 1) ** (mp.mpf(12) / 5), [0, mp.inf])
        ** 2
    )

    nnn_fits = read_csv(DATA / "nnn_tfim_alternative_fit_summary.csv")
    zero_match = read_csv(DATA / "tfim_j2_zero_resolution_match.csv")
    xx_checks = read_csv(DATA / "xx_pairing_theorem_checks.csv")
    sector = read_csv(DATA / "tfim_sector_contrast.csv")
    weight_rows = [
        row
        for row in read_csv(DATA / "interacting_weight_distributions.csv")
        if row["model"] == "Potts" and int(row["L"]) == 12
    ]

    # Full CFT probabilities and partial concentration values.  The recurrence
    # uses the independently evaluated infinite S1 only for normalization.
    delta = 0.8
    a_n = 1.0
    cft_raw: list[float] = []
    for n in range(20):
        cft_raw.append(a_n / (delta + 2.0 * n) ** 2)
        a_n *= ((delta + n) / (n + 1.0)) ** 2
    cft_s1 = float(
        beta_integral_hypergeometric_moments(Fraction(4, 5))[0]
    )
    cft_pi = [value / cft_s1 for value in cft_raw]
    shape_comparison = []
    for index, row in enumerate(weight_rows[:5]):
        ed_ratio = float(row["x"]) / float(weight_rows[0]["x"])
        cft_ratio = cft_raw[index] / cft_raw[0]
        shape_comparison.append(
            {
                "rank": index + 1,
                "ed_pi": float(row["pi"]),
                "cft_pi": cft_pi[index],
                "ed_raw_ratio_to_rank_1": ed_ratio,
                "cft_raw_ratio_to_rank_1": cft_ratio,
                "relative_ratio_error": (
                    0.0 if index == 0 else ed_ratio / cft_ratio - 1.0
                ),
            }
        )

    partial_k = {}
    partial_s1 = 0.0
    partial_s2 = 0.0
    for index, value in enumerate(cft_raw[:10], start=1):
        partial_s1 += value
        partial_s2 += value * value
        partial_k[str(index)] = partial_s2 / partial_s1**2

    def fixed_one_power_rmse(exponent: float, start_index: int = 0) -> float:
        sizes = np.asarray(potts_sizes[start_index:], dtype=float)
        values = np.asarray(potts_values[start_index:], dtype=float)
        x = sizes ** (-exponent)
        a_fit = float(np.dot(x, values - potts_k) / np.dot(x, x))
        residual = values - (potts_k + a_fit * x)
        return float(np.sqrt(np.mean(residual**2)))

    def fixed_two_power_rmse(start_index: int = 0) -> float:
        sizes = np.asarray(potts_sizes[start_index:], dtype=float)
        values = np.asarray(potts_values[start_index:], dtype=float)
        design = np.column_stack([sizes ** (-0.8), sizes ** (-2.0)])
        coefficients = np.linalg.lstsq(
            design, values - potts_k, rcond=None
        )[0]
        residual = values - (potts_k + design @ coefficients)
        return float(np.sqrt(np.mean(residual**2)))

    exact_xx_rows = [
        row
        for row in xx_checks
        if row["status"] == "PASS" and row["check"] != "leading_correction"
    ]
    recorded_xx_rows = [row for row in xx_checks if row["status"] == "RECORDED"]
    return {
        "hashes": {
            "interacting_benchmarks.csv": sha256(DATA / "interacting_benchmarks.csv"),
            "potts_alternative_fit_summary.csv": sha256(
                DATA / "potts_alternative_fit_summary.csv"
            ),
            "nnn_tfim_alternative_fit_summary.csv": sha256(
                DATA / "nnn_tfim_alternative_fit_summary.csv"
            ),
        },
        "potts": {
            "sizes": potts_sizes,
            "kf": potts_values,
            "fixed_cft_delta_4_5": potts_k,
            "pure_tail_odd_power": pure_tail,
            "alternative_fit_range": [min(fit_values), max(fit_values)],
            "distance_cft_to_fit_interval": (
                0.0
                if min(fit_values) <= potts_k <= max(fit_values)
                else min(abs(potts_k - min(fit_values)), abs(potts_k - max(fit_values)))
            ),
            "distance_tail_to_fit_interval": (
                0.0
                if min(fit_values) <= pure_tail <= max(fit_values)
                else min(
                    abs(pure_tail - min(fit_values)),
                    abs(pure_tail - max(fit_values)),
                )
            ),
            "last_size_residual_to_cft": potts_values[-1] - potts_k,
            "last_size_residual_to_tail": potts_values[-1] - pure_tail,
            "l12_weight_shape": shape_comparison,
            "partial_cft_k_by_number_of_levels": partial_k,
            "fixed_cft_correction_rmse": {
                "Kcft+aL^-0.8_L6-12": fixed_one_power_rmse(0.8),
                "Kcft+aL^-1.0_L6-12": fixed_one_power_rmse(1.0),
                "Kcft+aL^-1.2_L6-12": fixed_one_power_rmse(1.2),
                "Kcft+aL^-1.5_L6-12": fixed_one_power_rmse(1.5),
                "Kcft+aL^-0.8+bL^-2_L6-12": fixed_two_power_rmse(0),
                "Kcft+aL^-0.8+bL^-2_L8-12": fixed_two_power_rmse(2),
                "Kcft+aL^-0.8+bL^-2_L9-12": fixed_two_power_rmse(3),
            },
        },
        "nnn_tfim_fit_ceiling": nnn_fits,
        "j2_zero_projector_match": {
            "rows": len(zero_match),
            "all_pass": all(row["status"] == "PASS" for row in zero_match),
            "max_kf_abs_error": max(float(row["KF_abs_error"]) for row in zero_match),
        },
        "xx_exact_checks": {
            "rows": len(xx_checks),
            "assertion_rows": len(exact_xx_rows),
            "recorded_diagnostic_rows": len(recorded_xx_rows),
            "all_assertions_pass": all(
                row["status"] == "PASS"
                for row in xx_checks
                if row["status"] != "RECORDED"
            ),
            "max_exact_assertion_abs_error": max(
                float(row["abs_error"])
                for row in exact_xx_rows
                if row["abs_error"] not in {"", "NA", "nan"}
            ),
            "leading_correction_residual": float(
                next(
                    row["abs_error"]
                    for row in xx_checks
                    if row["check"] == "leading_correction"
                )
            ),
        },
        "sector_contrast": {
            "last_L": int(sector[-1]["L"]),
            "last_NS": float(sector[-1]["KF_NS_exact"]),
            "last_R_excluded": float(sector[-1]["KF_R_exact"]),
            "limits": {"NS": 2.0 / 3.0, "R_excluded": 2.0 / 5.0},
        },
    }


def grouping_controls() -> dict:
    p = np.asarray([0.7, 0.2, 0.1], dtype=float)
    k = float(np.sum(p**2))
    split = np.concatenate([p / 2, p / 2])
    merged = split[:3] + split[3:]
    return {
        "base_k": k,
        "two_equal_split_k": float(np.sum(split**2)),
        "merged_k": float(np.sum(merged**2)),
        "split_equals_base_over_two": bool(
            abs(np.sum(split**2) - k / 2) < 1e-15
        ),
        "merge_returns_base": bool(abs(np.sum(merged**2) - k) < 1e-15),
    }


def main() -> None:
    mp.mp.dps = 80
    delta_1 = compute_delta("1")
    delta_potts = compute_delta("0.8")
    potts_k = float(
        mp.mpf(delta_potts["beta_integral_hypergeometric_closed_form"]["k"])
    )
    record = {
        "schema": "kf-cft-calculation/1.0.0",
        "research_id": "KF-CFT-2026-001",
        "mpmath_dps": mp.mp.dps,
        "formula": {
            "A_n": "((Delta)_n/n!)^2",
            "w_n": "A_n/(Delta+2n)^2",
            "K": "sum(w_n^2)/sum(w_n)^2",
        },
        "delta_results": {"1": delta_1, "4/5": delta_potts},
        "controls": exact_and_failure_controls(),
        "cutoff_scaling": cutoff_controls(),
        "grouping": grouping_controls(),
        "retained_evidence": retained_evidence(potts_k),
    }
    print(json.dumps(record, indent=2, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
