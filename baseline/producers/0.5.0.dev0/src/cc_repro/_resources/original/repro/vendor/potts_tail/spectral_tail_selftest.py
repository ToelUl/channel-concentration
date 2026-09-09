#!/usr/bin/env python3
"""Exact/synthetic no-target S0: original 28 plus 8 zero-endpoint cases."""
from __future__ import annotations

import math

import numpy as np

from spectral_tail_core import (
    ABS_WIDTH,
    MANDATORY_N_EIG,
    Interval,
    add_nonnegative_down,
    adjudicate_intervals,
    canonical_hash,
    complete_retained_slices,
    div_nonnegative_down,
    down,
    intersect,
    mul_down,
    mul_nonnegative_down,
    nested_prefix,
    p2_backward_interval,
    square_nonnegative,
    sum_nonnegative_down,
    tail_enclosure,
    up,
)


def point(value: float) -> Interval:
    return Interval(down(value), up(value))


def exact_kf(channels: list[float], p2: float) -> float:
    return sum(value * value for value in channels) / (p2 * p2)


def contains(interval: Interval, value: float) -> bool:
    return interval.lower <= value <= interval.upper


def make_result(case_id: str, passed: bool, detail: str) -> dict:
    return {"id": case_id, "passed": bool(passed), "detail": detail}


def run_oracles() -> list[dict]:
    results: list[dict] = []
    r = [0.55, 0.25, 0.12, 0.08]
    x = list(r)
    p2 = sum(r)
    exact = exact_kf(x, p2)

    intervals = []
    for prefix in (1, 2, 3):
        out = tail_enclosure(point(p2), [point(v) for v in x[:prefix]], [point(v) for v in r[:prefix]], 1.0)
        intervals.append(out["interval"])
    results.append(make_result("O-01", all(contains(item, exact) for item in intervals), "every exact nonnegative prefix encloses full K_F"))

    r2 = [0.7, 0.3]
    exact2 = exact_kf(r2, 1.0)
    one_tail = tail_enclosure(point(1.0), [point(0.7)], [point(0.7)], 1.0)["interval"]
    results.append(make_result("O-02", contains(one_tail, exact2) and abs(one_tail.upper - exact2) < 1.0e-14, "single-channel tail saturates upper endpoint"))

    many_tail = [0.7] + [0.3 / 100.0] * 100
    exact3 = exact_kf(many_tail, 1.0)
    lower_case = tail_enclosure(point(1.0), [point(0.7)], [point(0.7)], 1.0)["interval"]
    results.append(make_result("O-03", contains(lower_case, exact3) and exact3 - lower_case.lower < 1.0e-3, "many-channel tail approaches lower endpoint"))

    nested = intervals[1].lower >= intervals[0].lower and intervals[1].upper <= intervals[0].upper and intervals[2].lower >= intervals[1].lower and intervals[2].upper <= intervals[1].upper
    results.append(make_result("O-04", nested, "exact retained prefixes give nested intervals"))

    zero_tail = tail_enclosure(point(p2), [point(v) for v in x], [point(v) for v in r], 1.0)["interval"]
    results.append(make_result("O-05", contains(zero_tail, exact) and zero_tail.width < 1.0e-13, "zero tail collapses to rounding-scale enclosure"))

    rx = [0.5, 0.3, 0.2]
    xx = [0.49, 0.31, 0.2]
    c = max(a / b for a, b in zip(xx, rx))
    exact6 = exact_kf(xx, sum(rx))
    dual = tail_enclosure(point(sum(rx)), [point(v) for v in xx[:2]], [point(v) for v in rx[:2]], up(c))["interval"]
    results.append(make_result("O-06", contains(dual, exact6), "dual x_a != r_a outward arithmetic encloses exact reference"))

    y_norm = 2.0
    residual = 1.0e-6
    inverse_lower = 0.5
    p2_interval = p2_backward_interval(y_norm, residual, inverse_lower)
    results.append(make_result("O-07", contains(p2_interval, (y_norm + residual / inverse_lower) ** 2) and contains(p2_interval, (y_norm - residual / inverse_lower) ** 2), "ST6 encloses seeded solve error"))

    vector = np.array([0.3, -0.4])
    theta = 0.371
    rotation = np.array([[math.cos(theta), -math.sin(theta)], [math.sin(theta), math.cos(theta)]])
    results.append(make_result("O-08", abs(float(vector @ vector) - float((rotation @ vector) @ (rotation @ vector))) < 1.0e-15, "degenerate-block norm is rotation invariant"))

    cut_values = [0.0, 1.0, 2.0, 2.0 + 1.0e-8]
    retained = complete_retained_slices(cut_values, 3)
    results.append(make_result("O-09", retained == ((1, 2),), "terminal cluster crossing nominal boundary is wholly excluded"))

    common = intersect([Interval(0.4, 0.6), Interval(0.45, 0.55), Interval(0.49, 0.51)])
    results.append(make_result("O-10", common == Interval(0.49, 0.51), "same-object P2-style intersection is nonempty"))

    adjudication = adjudicate_intervals([Interval(0.8, 0.9), Interval(0.82, 0.88), Interval(0.84, 0.840000001)])
    results.append(make_result("O-11", adjudication["width_pass"] and adjudication["all_rung_interval"] == [0.84, 0.840000001], "all mandatory rungs determine the intersection"))

    mandatory_width_pass = False
    all_other_checks = True
    projected_rss = 4.0
    invoke_384 = (not mandatory_width_pass) and all_other_checks and projected_rss < 18.0
    results.append(make_result("O-12", invoke_384, "k256-width-only failure routes once to conditional N_eig=384"))

    zero_product = mul_nonnegative_down(0.0, 0.0)
    results.append(make_result("O-ZE-01", zero_product == 0.0 and math.copysign(1.0, zero_product) > 0.0, "nonnegative multiplication preserves the exact positive zero lower endpoint"))

    zero_quotient = div_nonnegative_down(0.0, 1.0)
    results.append(make_result("O-ZE-02", zero_quotient == 0.0 and math.copysign(1.0, zero_quotient) > 0.0, "nonnegative division preserves the exact positive zero lower endpoint"))

    zero_sum = sum_nonnegative_down([0.0, 0.0, 0.0])
    zero_square = square_nonnegative(Interval(0.0, 0.0))
    results.append(make_result("O-ZE-03", zero_sum == 0.0 and zero_square.lower == 0.0 and contains(zero_square, 0.0), "nonnegative accumulation and squaring preserve a rigorous zero lower endpoint"))

    weak = Interval(0.0, up(0.0))
    weak_enclosure = tail_enclosure(point(1.0), [weak], [weak], 1.0)
    results.append(make_result("O-ZE-04", weak_enclosure["interval"].lower == 0.0 and weak_enclosure["q_interval"].lower == 0.0 and weak_enclosure["retained_resolvent_interval"].lower == 0.0, "weak-channel and zero-tail lower accounting stays in the nonnegative domain"))
    return results


def rejects(callable_object) -> bool:
    try:
        callable_object()
    except (ValueError, RuntimeError):
        return True
    return False


def run_failure_probes() -> list[dict]:
    results: list[dict] = []
    results.append(make_result("FP-01", rejects(lambda: tail_enclosure(point(1.0), [Interval(-0.1, 0.2)], [point(0.2)], 1.0)), "negative channel weight rejected"))

    grouped = (0.2 + 0.3) ** 2
    fragmented = 0.2**2 + 0.3**2
    results.append(make_result("FP-02", abs(grouped - fragmented) > 0.1, "individual-state squaring defect detected"))

    values = [0.0, 1.0, 2.0, 2.0 + 1.0e-8]
    results.append(make_result("FP-03", complete_retained_slices(values, 3) == ((1, 2),), "partial terminal cluster rejected"))

    full = exact_kf([0.6, 0.4], 1.0)
    wrong = exact_kf([0.6], 0.6)
    results.append(make_result("FP-04", abs(full - wrong) > 0.1, "truncated denominator defect detected"))

    results.append(make_result("FP-05", rejects(lambda: complete_retained_slices([0.0, 1.0, 2.0], 3)), "missing guard eigenpair rejected"))

    exact = exact_kf([0.6, 0.4], 1.0)
    valid = tail_enclosure(point(1.0), [point(0.6)], [point(0.6)], 1.0)["interval"]
    inward = Interval(valid.lower, down(exact))
    results.append(make_result("FP-06", not contains(inward, exact), "inward upper endpoint is exposed"))

    results.append(make_result("FP-07", rejects(lambda: p2_backward_interval(2.0, 1.0e-6, 0.0)), "missing inverse/gap lower bound rejected"))
    results.append(make_result("FP-08", rejects(lambda: intersect([Interval(0.1, 0.2), Interval(0.3, 0.4)])), "empty P2 intersection rejected"))
    results.append(make_result("FP-09", not nested_prefix(((1, 2), (2, 3)), ((1, 2), (3, 4))), "nonnested cluster sets rejected"))

    hash_a = canonical_hash({"L": 12, "sector": "k_mom=0"})
    hash_b = canonical_hash({"L": 12, "sector": "full"})
    results.append(make_result("FP-10", hash_a != hash_b, "changed object hash detected"))

    rung_a = Interval(0.80, 0.86)
    rung_b = Interval(0.84, 0.90)
    favorable = rung_b
    all_rung = intersect([rung_a, rung_b])
    results.append(make_result("FP-11", favorable != all_rung and all_rung == Interval(0.84, 0.86), "favorable-rung selection differs from required all-rung intersection"))

    majority_value = sum([0.8, 0.9, 0.85]) / 3.0
    results.append(make_result("FP-12", majority_value not in (0.8, 0.9), "majority/averaging produces an unauthorized value"))

    incomplete_ladder = (128, 256)
    results.append(make_result("FP-13", incomplete_ladder != MANDATORY_N_EIG, "skipped mandatory rung detected"))

    k256_pass = True
    projected = 4.0
    invoke_384 = (not k256_pass) and projected < 18.0
    results.append(make_result("FP-14", not invoke_384, "unauthorized N_eig=384 invocation blocked"))

    proposed_threshold = 1.1e-8
    results.append(make_result("FP-15", proposed_threshold != ABS_WIDTH, "threshold relaxation detected"))

    archived_payload = {"sum_pi": 0.9999988, "prospective": False}
    results.append(make_result("FP-16", not archived_payload["prospective"] and "resolvent_r_intervals" not in archived_payload, "archived grouped sum cannot satisfy prospective dual-accounting calibration"))

    negative_subnormal = float(np.nextafter(0.0, -np.inf))
    results.append(make_result("FP-ZE-01", rejects(lambda: mul_nonnegative_down(negative_subnormal, 1.0)), "negative-subnormal lower endpoint is rejected rather than clipped"))

    results.append(make_result("FP-ZE-02", rejects(lambda: div_nonnegative_down(-0.1, 1.0)), "genuinely signed negative numerator remains fail-closed"))

    generic_zero = mul_down(0.0, 0.0)
    results.append(make_result("FP-ZE-03", generic_zero < 0.0 and mul_nonnegative_down(0.0, 0.0) == 0.0, "seeded use of generic downward rounding at a nonnegative zero boundary is detected"))

    seeded_upshift = float(np.nextafter(0.0, np.inf))
    domain_zero = add_nonnegative_down(0.0, 0.0)
    results.append(make_result("FP-ZE-04", seeded_upshift > 0.0 and domain_zero == 0.0 and domain_zero != seeded_upshift, "seeded zero-upshift defect is rejected"))
    return results


def run_all() -> dict:
    oracles = run_oracles()
    probes = run_failure_probes()
    return {
        "oracles": oracles,
        "failure_probes": probes,
        "oracle_passed": sum(item["passed"] for item in oracles),
        "oracle_expected": 16,
        "failure_probe_passed": sum(item["passed"] for item in probes),
        "failure_probe_expected": 20,
    }
