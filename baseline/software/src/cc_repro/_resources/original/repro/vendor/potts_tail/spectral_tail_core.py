#!/usr/bin/env python3
"""Pure ST0--ST6 interval and cluster primitives.

This module contains no model builder, target locator, authority writer, network,
or subprocess path.  All finite-precision bounds use explicit binary64 outward
rounding with ``numpy.nextafter``.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Iterable, Sequence

import numpy as np


ABS_WIDTH = 1.0e-8
GROUP_TOLS = (5.0e-8, 1.0e-7, 2.0e-7)
PRIMARY_GROUP_TOL = 1.0e-7
MANDATORY_N_EIG = (128, 192, 256)
CONDITIONAL_N_EIG = 384
GUARD_EIGENPAIRS = 1


def down(value: float) -> float:
    return float(np.nextafter(float(value), -np.inf))


def up(value: float) -> float:
    return float(np.nextafter(float(value), np.inf))


def add_down(a: float, b: float) -> float:
    return down(float(a) + float(b))


def add_up(a: float, b: float) -> float:
    return up(float(a) + float(b))


def sub_down(a: float, b: float) -> float:
    return down(float(a) - float(b))


def sub_up(a: float, b: float) -> float:
    return up(float(a) - float(b))


def mul_down(a: float, b: float) -> float:
    return down(float(a) * float(b))


def mul_up(a: float, b: float) -> float:
    return up(float(a) * float(b))


def div_down(a: float, b: float) -> float:
    if b <= 0.0:
        raise ValueError("outward division requires a positive denominator")
    return down(float(a) / float(b))


def div_up(a: float, b: float) -> float:
    if b <= 0.0:
        raise ValueError("outward division requires a positive denominator")
    return up(float(a) / float(b))


def nonnegative_down(value: float) -> float:
    """Outward lower rounding on the closed nonnegative domain.

    Zero is an exact boundary of the mathematical domain.  Stepping from an
    exact or underflowed zero toward negative infinity would enlarge the real
    line interval outside that domain and is therefore forbidden here.  This
    is a domain-aware rounding rule, not clipping of computed data.
    """
    value = float(value)
    if not math.isfinite(value) or value < 0.0:
        raise ValueError("nonnegative outward lower rounding requires a finite nonnegative value")
    if value == 0.0:
        return 0.0
    rounded = down(value)
    if rounded < 0.0:
        raise RuntimeError("nonnegative outward lower rounding crossed the domain boundary")
    return rounded


def add_nonnegative_down(a: float, b: float) -> float:
    a = float(a)
    b = float(b)
    if a < 0.0 or b < 0.0:
        raise ValueError("nonnegative addition received a negative input; no clipping")
    return nonnegative_down(a + b)


def mul_nonnegative_down(a: float, b: float) -> float:
    a = float(a)
    b = float(b)
    if a < 0.0 or b < 0.0:
        raise ValueError("nonnegative multiplication received a negative input; no clipping")
    return nonnegative_down(a * b)


def div_nonnegative_down(a: float, b: float) -> float:
    a = float(a)
    b = float(b)
    if a < 0.0:
        raise ValueError("nonnegative division received a negative numerator; no clipping")
    if b <= 0.0:
        raise ValueError("nonnegative outward division requires a positive denominator")
    return nonnegative_down(a / b)


def sum_down(values: Iterable[float]) -> float:
    total = 0.0
    for value in values:
        total = add_down(total, float(value))
    return total


def sum_nonnegative_down(values: Iterable[float]) -> float:
    total = 0.0
    for value in values:
        total = add_nonnegative_down(total, float(value))
    return total


def sum_up(values: Iterable[float]) -> float:
    total = 0.0
    for value in values:
        total = add_up(total, float(value))
    return total


@dataclass(frozen=True)
class Interval:
    lower: float
    upper: float

    def __post_init__(self) -> None:
        if not (math.isfinite(self.lower) and math.isfinite(self.upper)):
            raise ValueError("interval endpoints must be finite")
        if self.lower > self.upper:
            raise ValueError("interval lower endpoint exceeds upper endpoint")

    @property
    def width(self) -> float:
        return up(self.upper - self.lower)

    def as_list(self) -> list[float]:
        return [float(self.lower), float(self.upper)]


def square_nonnegative(interval: Interval) -> Interval:
    if interval.lower < 0.0:
        raise ValueError("negative lower endpoint is forbidden; no clipping")
    return Interval(mul_nonnegative_down(interval.lower, interval.lower), mul_up(interval.upper, interval.upper))


def intersect(intervals: Sequence[Interval]) -> Interval:
    if not intervals:
        raise ValueError("at least one interval is required")
    lower = max(item.lower for item in intervals)
    upper = min(item.upper for item in intervals)
    if lower > upper:
        raise ValueError("empty all-rung interval intersection")
    return Interval(lower, upper)


def tail_enclosure(
    p2: Interval,
    channel_intervals: Sequence[Interval],
    resolvent_intervals: Sequence[Interval],
    c_upper: float,
) -> dict:
    """ST4 outward enclosure with separate x_a and r_a accounting."""
    if p2.lower <= 0.0 or c_upper < 1.0:
        raise ValueError("invalid P2 or tail ratio factor")
    if len(channel_intervals) != len(resolvent_intervals):
        raise ValueError("channel/resolvent interval cardinality mismatch")
    if any(item.lower < 0.0 for item in list(channel_intervals) + list(resolvent_intervals)):
        raise ValueError("negative weights are forbidden; no clipping")

    q_lower = sum_nonnegative_down(mul_nonnegative_down(item.lower, item.lower) for item in channel_intervals)
    q_upper = sum_up(mul_up(item.upper, item.upper) for item in channel_intervals)
    r_lower = sum_nonnegative_down(item.lower for item in resolvent_intervals)
    r_upper = sum_up(item.upper for item in resolvent_intervals)
    tail_upper = sub_up(p2.upper, r_lower)
    if tail_upper < 0.0 or r_lower > p2.upper or r_upper < 0.0:
        raise ValueError("inconsistent retained resolvent mass and full P2")

    lower = div_nonnegative_down(q_lower, mul_up(p2.upper, p2.upper))
    tail_square = mul_up(tail_upper, tail_upper)
    c_square = mul_up(c_upper, c_upper)
    numerator_upper = add_up(q_upper, mul_up(c_square, tail_square))
    upper_raw = div_up(numerator_upper, mul_nonnegative_down(p2.lower, p2.lower))
    # The min is an intersection with the independently frozen normalized
    # level-projector theorem K_F<=1, not data clipping.  A raw overshoot beyond
    # a tiny enclosure allowance is reported separately by the caller.
    upper = min(1.0, upper_raw)
    interval = Interval(lower, upper)
    return {
        "interval": interval,
        "q_interval": Interval(q_lower, q_upper),
        "retained_resolvent_interval": Interval(r_lower, r_upper),
        "tail_resolvent_upper": tail_upper,
        "tail_ratio_factor_upper": float(c_upper),
        "upper_before_normalization_intersection": float(upper_raw),
    }


def frozen_group_slices(eigenvalues: Sequence[float], tolerance: float) -> tuple[tuple[int, int], ...]:
    """Replicate the frozen grouping rule: compare every member to group first."""
    values = np.asarray(eigenvalues, dtype=float)
    if values.ndim != 1 or len(values) == 0 or np.any(np.diff(values) < 0.0):
        raise ValueError("ordered one-dimensional eigenvalues are required")
    groups: list[tuple[int, int]] = []
    start = 0
    while start < len(values):
        end = start + 1
        while end < len(values) and values[end] - values[start] <= tolerance:
            end += 1
        groups.append((start, end))
        start = end
    return tuple(groups)


def complete_retained_slices(
    eigenvalues: Sequence[float], nominal_n_eig: int, tolerance: float = PRIMARY_GROUP_TOL
) -> tuple[tuple[int, int], ...]:
    """Return complete excited groups certified by at least one guard eigenpair."""
    if len(eigenvalues) < nominal_n_eig + GUARD_EIGENPAIRS:
        raise ValueError("missing guard eigenpair")
    groups = frozen_group_slices(eigenvalues, tolerance)
    retained: list[tuple[int, int]] = []
    for start, end in groups:
        if start == 0:
            continue
        if end <= nominal_n_eig:
            retained.append((start, end))
    return tuple(retained)


def grouping_signature(eigenvalues: Sequence[float], nominal_n_eig: int, tolerance: float) -> tuple[tuple[int, int], ...]:
    return complete_retained_slices(eigenvalues, nominal_n_eig, tolerance)


def nested_prefix(previous: Sequence[tuple[int, int]], current: Sequence[tuple[int, int]]) -> bool:
    return len(previous) <= len(current) and tuple(previous) == tuple(current[: len(previous)])


def canonical_hash(payload: object) -> str:
    data = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def adjudicate_intervals(intervals: Sequence[Interval]) -> dict:
    combined = intersect(intervals)
    return {
        "all_rung_interval": combined.as_list(),
        "absolute_width": combined.width,
        "width_ceiling": ABS_WIDTH,
        "width_pass": combined.width <= ABS_WIDTH,
    }


def p2_backward_interval(y_norm: float, effective_residual: float, inverse_lower: float) -> Interval:
    """ST6 norm enclosure for P2=||y||^2."""
    if y_norm < 0.0 or effective_residual < 0.0 or inverse_lower <= 0.0:
        raise ValueError("invalid ST6 inputs")
    y_error = div_up(effective_residual, inverse_lower)
    lower_norm = max(0.0, sub_down(y_norm, y_error))
    upper_norm = add_up(y_norm, y_error)
    return Interval(mul_nonnegative_down(lower_norm, lower_norm), mul_up(upper_norm, upper_norm))
