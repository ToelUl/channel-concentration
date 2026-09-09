#!/usr/bin/env python3
"""Prospective Potts ST0--ST6 spectral-tail calibration/target runner."""
from __future__ import annotations

import os
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")

import argparse
import gc
import hashlib
import importlib.util
import json
import math
import platform
import resource
import sys
import time
from pathlib import Path

import numpy as np
import scipy
import scipy.sparse as sp
import scipy.sparse.linalg as spla

from spectral_tail_core import (
    ABS_WIDTH,
    CONDITIONAL_N_EIG,
    GROUP_TOLS,
    GUARD_EIGENPAIRS,
    MANDATORY_N_EIG,
    PRIMARY_GROUP_TOL,
    Interval,
    add_up,
    adjudicate_intervals,
    canonical_hash,
    complete_retained_slices,
    div_down,
    div_nonnegative_down,
    div_up,
    down,
    frozen_group_slices,
    grouping_signature,
    intersect,
    mul_nonnegative_down,
    mul_up,
    nested_prefix,
    p2_backward_interval,
    sub_down,
    sub_up,
    sum_down,
    sum_up,
    tail_enclosure,
    up,
)


ACTION_ID = "DEC-KF-CFT-POTTS-FSS-SPECTRAL-TAIL-CERTIFICATE-ZERO-ENDPOINT-RECOVERY-001/A"
VENDOR_SHA256 = "fef7cd67619a4bc0827cb28e0a5da70b4352dea373fa790f130ce89437d1e104"
RAM_CAP_GIB = 20
PROJECTED_RSS_GATE_GIB = 18.0
SCRATCH_CAP_GIB = 2.0
EIG_TOL = 1.0e-12
SOLVE_RTOL = 1.0e-12


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, sort_keys=True, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def deterministic_v0(dimension: int) -> np.ndarray:
    grid = np.arange(1, dimension + 1, dtype=float)
    vector = np.cos(0.6180339887498949 * grid) + 0.5 * np.sin(0.4142135623730950 * grid)
    return vector / np.linalg.norm(vector)


def load_vendor(root: Path):
    source = root / "vendor" / "simulate_interacting_benchmarks.py"
    if sha256(source) != VENDOR_SHA256:
        raise RuntimeError("frozen vendor hash mismatch")
    spec = importlib.util.spec_from_file_location("frozen_potts_model", source)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot create frozen vendor import specification")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, source


def source_hashes(root: Path) -> dict[str, str]:
    names = [
        "spectral_tail_core.py",
        "spectral_tail_runner.py",
        "spectral_tail_selftest.py",
        "static_acceptance.py",
        "packaged_selftest.py",
        "stage_authority.py",
        "vendor/simulate_interacting_benchmarks.py",
    ]
    return {name: sha256(root / name) for name in names}


def environment_receipt(root: Path) -> dict:
    return {
        "python": sys.version,
        "platform": platform.platform(),
        "numpy": np.__version__,
        "scipy": scipy.__version__,
        "thread_env": {key: os.environ.get(key) for key in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS")},
        "cpu_visible": os.cpu_count(),
        "source_hashes": source_hashes(root),
        "vendor_sha256": VENDOR_SHA256,
        "network_allowed": False,
        "gpu_count": 0,
    }


def ground_and_p2_context(H: sp.csr_matrix, V: sp.csr_matrix, L: int) -> dict:
    dimension = H.shape[0]
    v0 = deterministic_v0(dimension)
    ncv = min(dimension - 1, 96)
    eigenvalues, eigenvectors = spla.eigsh(H, k=2, which="SA", tol=EIG_TOL, ncv=ncv, v0=v0)
    order = np.argsort(eigenvalues)
    eigenvalues = np.asarray(eigenvalues[order], dtype=float)
    eigenvectors = np.asarray(eigenvectors[:, order], dtype=float)
    residuals = [float(np.linalg.norm(H @ eigenvectors[:, index] - eigenvalues[index] * eigenvectors[:, index])) for index in range(2)]
    e0 = float(eigenvalues[0])
    psi = eigenvectors[:, 0]
    gap_lower = down((eigenvalues[1] - residuals[1]) - (eigenvalues[0] + residuals[0]))
    if gap_lower <= 0.0:
        raise RuntimeError("ground-state gap lower bound is nonpositive")
    projector_error = min(1.0, up(2.0 * residuals[0] / gap_lower))

    b = V @ psi
    b = b - float(psi @ b) * psi
    b_norm = float(np.linalg.norm(b))
    operator_norm_bound = float(2 * L)
    rhs_error = up((1.0 + math.sqrt(2.0)) * operator_norm_bound * projector_error)

    alpha = max(float(eigenvalues[1] - eigenvalues[0]), 1.0e-6)
    shifted = (H - e0 * sp.identity(dimension, format="csr")).tocsr()
    augmented = spla.LinearOperator(
        (dimension, dimension),
        matvec=lambda vector: shifted @ vector + alpha * psi * float(psi @ vector),
        dtype=float,
    )
    y, info = spla.minres(augmented, b, rtol=SOLVE_RTOL, maxiter=100000)
    y = y - float(psi @ y) * psi
    y_norm = float(np.linalg.norm(y))
    solve_residual_abs = float(np.linalg.norm(augmented @ y - b))
    operator_error = up(residuals[0] + alpha * projector_error)
    effective_residual = up(solve_residual_abs + operator_error * y_norm + rhs_error)
    inverse_lower = min(alpha, gap_lower)
    y_error = up(effective_residual / inverse_lower)
    p2 = p2_backward_interval(y_norm, effective_residual, inverse_lower)
    if p2.lower <= 0.0 or info != 0:
        raise RuntimeError("P2 backward enclosure failed")
    return {
        "E0": e0,
        "E0_interval": [down(e0 - residuals[0]), up(e0 + residuals[0])],
        "ground_residual_abs": residuals[0],
        "first_excited_residual_abs": residuals[1],
        "gap_lower": gap_lower,
        "ground_projector_error": projector_error,
        "b_norm": b_norm,
        "rhs_error_bound": rhs_error,
        "alpha": alpha,
        "minres_info": int(info),
        "solve_residual_abs": solve_residual_abs,
        "operator_error_bound": operator_error,
        "effective_residual_bound": effective_residual,
        "y_norm": y_norm,
        "y_error_bound": y_error,
        "P2_interval": p2.as_list(),
        "psi": psi,
        "b": b,
    }


def _cluster_receipt(
    H: sp.csr_matrix,
    eigenvalues: np.ndarray,
    eigenvectors: np.ndarray,
    residuals: np.ndarray,
    group: tuple[int, int],
    ground: dict,
) -> dict:
    start, end = group
    lower_values = eigenvalues - residuals
    upper_values = eigenvalues + residuals
    previous_upper = upper_values[start - 1]
    next_lower = lower_values[end]
    group_lower = float(np.min(lower_values[start:end]))
    group_upper = float(np.max(upper_values[start:end]))
    complement_gap = down(min(group_lower - previous_upper, next_lower - group_upper))
    if complement_gap <= 0.0:
        raise RuntimeError("cluster complement gap is not certified")
    block_residual = up(float(np.linalg.norm(residuals[start:end])))
    projector_error = min(1.0, up(2.0 * block_residual / complement_gap))
    coefficients = eigenvectors[:, start:end].T @ ground["b"]
    projected_norm = float(np.linalg.norm(coefficients))
    projected_norm_error = up(projector_error * ground["b_norm"] + ground["rhs_error_bound"])
    norm_lower = max(0.0, sub_down(projected_norm, projected_norm_error))
    norm_upper = add_up(projected_norm, projected_norm_error)
    numerator = Interval(mul_nonnegative_down(norm_lower, norm_lower), mul_up(norm_upper, norm_upper))

    e0_lower, e0_upper = ground["E0_interval"]
    mean_lower = div_down(sum_down(lower_values[start:end]), float(end - start))
    mean_upper = div_up(sum_up(upper_values[start:end]), float(end - start))
    mean_gap = Interval(down(mean_lower - e0_upper), up(mean_upper - e0_lower))
    individual_gap = Interval(down(group_lower - e0_upper), up(group_upper - e0_lower))
    if mean_gap.lower <= 0.0 or individual_gap.lower <= 0.0:
        raise RuntimeError("nonpositive excited gap interval")

    channel = Interval(
        div_nonnegative_down(numerator.lower, mul_up(mean_gap.upper, mean_gap.upper)),
        div_up(numerator.upper, mul_nonnegative_down(mean_gap.lower, mean_gap.lower)),
    )
    resolvent = Interval(
        div_nonnegative_down(numerator.lower, mul_up(individual_gap.upper, individual_gap.upper)),
        div_up(numerator.upper, mul_nonnegative_down(individual_gap.lower, individual_gap.lower)),
    )
    c_upper = mul_up(
        div_up(individual_gap.upper, mean_gap.lower),
        div_up(individual_gap.upper, mean_gap.lower),
    )
    ratio_consistent = channel.upper <= mul_up(c_upper, resolvent.upper)
    return {
        "rank_slice": [int(start), int(end)],
        "multiplicity": int(end - start),
        "complement_gap_lower": complement_gap,
        "block_residual_bound": block_residual,
        "projector_error_bound": projector_error,
        "projected_norm": projected_norm,
        "projected_norm_error_bound": projected_norm_error,
        "numerator_interval": numerator.as_list(),
        "mean_gap_interval": mean_gap.as_list(),
        "individual_gap_interval": individual_gap.as_list(),
        "channel_x_interval": channel.as_list(),
        "resolvent_r_interval": resolvent.as_list(),
        "channel_to_resolvent_factor_upper": c_upper,
        "dual_accounting_ratio_consistent": bool(ratio_consistent),
    }


def run_rung(H: sp.csr_matrix, ground: dict, nominal_n_eig: int) -> dict:
    started = time.monotonic()
    dimension = H.shape[0]
    total = nominal_n_eig + GUARD_EIGENPAIRS
    if total >= dimension:
        raise RuntimeError("rung exceeds sparse-eigensolver dimension")
    ncv = min(dimension - 1, max(80, 4 * total + 1))
    v0 = deterministic_v0(dimension)
    eigenvalues, eigenvectors = spla.eigsh(H, k=total, which="SA", tol=EIG_TOL, ncv=ncv, v0=v0)
    order = np.argsort(eigenvalues)
    eigenvalues = np.asarray(eigenvalues[order], dtype=float)
    eigenvectors = np.asarray(eigenvectors[:, order], dtype=float)
    residuals = np.empty(total, dtype=float)
    for index in range(total):
        residuals[index] = np.linalg.norm(H @ eigenvectors[:, index] - eigenvalues[index] * eigenvectors[:, index])

    signatures = {f"{tol:.1e}": grouping_signature(eigenvalues, nominal_n_eig, tol) for tol in GROUP_TOLS}
    primary_key = f"{PRIMARY_GROUP_TOL:.1e}"
    retained = signatures[primary_key]
    grouping_stable = all(value == retained for value in signatures.values())
    if not retained:
        raise RuntimeError("no complete retained excited cluster")
    clusters = [_cluster_receipt(H, eigenvalues, eigenvectors, residuals, group, ground) for group in retained]
    last_end = retained[-1][1]
    if last_end >= len(eigenvalues):
        raise RuntimeError("guard eigenpair did not leave an unretained tail")
    tail_gap_lower = down((eigenvalues[last_end] - residuals[last_end]) - ground["E0_interval"][1])
    if tail_gap_lower <= 0.0:
        raise RuntimeError("tail gap lower bound is nonpositive")
    c_tail_base = up(1.0 + PRIMARY_GROUP_TOL / tail_gap_lower)
    c_tail_upper = mul_up(c_tail_base, c_tail_base)
    channel_intervals = [Interval(*item["channel_x_interval"]) for item in clusters]
    resolvent_intervals = [Interval(*item["resolvent_r_interval"]) for item in clusters]
    enclosure = tail_enclosure(Interval(*ground["P2_interval"]), channel_intervals, resolvent_intervals, c_tail_upper)
    normalization_raw_ok = enclosure["upper_before_normalization_intersection"] <= 1.0 + 1.0e-10
    interval = enclosure["interval"]
    elapsed = time.monotonic() - started
    receipt = {
        "nominal_N_eig": int(nominal_n_eig),
        "guard_eigenpairs": GUARD_EIGENPAIRS,
        "solver_eigenpairs": int(total),
        "ncv": int(ncv),
        "retained_cluster_slices": [list(group) for group in retained],
        "grouping_signatures": {key: [list(group) for group in value] for key, value in signatures.items()},
        "grouping_stable": bool(grouping_stable),
        "tail_gap_lower": tail_gap_lower,
        "tail_ratio_factor_upper": c_tail_upper,
        "clusters": clusters,
        "K_F_interval": interval.as_list(),
        "K_F_interval_width": interval.width,
        "q_interval": enclosure["q_interval"].as_list(),
        "retained_resolvent_interval": enclosure["retained_resolvent_interval"].as_list(),
        "tail_resolvent_upper": enclosure["tail_resolvent_upper"],
        "upper_before_normalization_intersection": enclosure["upper_before_normalization_intersection"],
        "normalization_raw_ok": bool(normalization_raw_ok),
        "max_eigenpair_residual_abs": float(np.max(residuals)),
        "elapsed_seconds": float(elapsed),
        "max_rss_kib": int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss),
    }
    receipt["raw_rung_sha256"] = canonical_hash(receipt)
    del eigenvectors, eigenvalues, residuals
    gc.collect()
    return receipt


def _rung_nonwidth_checks(rung: dict) -> bool:
    dual_ok = all(cluster["dual_accounting_ratio_consistent"] for cluster in rung["clusters"])
    return bool(rung["grouping_stable"] and rung["normalization_raw_ok"] and rung["tail_resolvent_upper"] >= 0.0 and dual_ok)


def _projected_384_rss_gib(rung256: dict) -> float:
    current = rung256["max_rss_kib"] / (1024.0**2)
    ncv384 = 4 * (CONDITIONAL_N_EIG + GUARD_EIGENPAIRS) + 1
    return float(current * ncv384 / rung256["ncv"])


def verify_authority(root: Path, authority_path: Path, L: int) -> dict:
    authority = json.loads(authority_path.read_text(encoding="utf-8"))
    if authority.get("decision_id") != ACTION_ID or L not in authority.get("authorized_sizes", []):
        raise RuntimeError("authority identity or size mismatch")
    if authority.get("new_target_attempts_authorized", 0) < 1 or authority.get("no_retry") is not True:
        raise RuntimeError("authority attempt semantics mismatch")
    if authority.get("source_hashes") != source_hashes(root):
        raise RuntimeError("authority source hashes mismatch")
    predecessor = authority.get("predecessor")
    if L == 12 and predecessor is not None:
        raise RuntimeError("L12 authority must not contain a predecessor")
    if L > 12:
        if not isinstance(predecessor, dict) or predecessor.get("L") != L - 1 or predecessor.get("status") != "CERTIFIED_PASS":
            raise RuntimeError("predecessor status binding missing")
        predecessor_path = root / "evidence" / predecessor.get("receipt_name", "")
        predecessor_seal = root / "evidence" / predecessor.get("seal_name", "")
        if not predecessor_path.is_file() or not predecessor_seal.is_file():
            raise RuntimeError("predecessor receipt/seal missing")
        if sha256(predecessor_path) != predecessor.get("receipt_sha256") or sha256(predecessor_seal) != predecessor.get("seal_sha256"):
            raise RuntimeError("predecessor receipt/seal hash mismatch")
    if L == 15 and not authority.get("L15_k256_projected_rss_below_18_gib", False):
        raise RuntimeError("L15 resource projection gate missing")
    return authority


def write_seal(output: Path, seal_path: Path, receipt: dict) -> None:
    classifications = {
        "context": canonical_hash(receipt["context"]),
        "ground_and_P2": canonical_hash(receipt["ground_and_P2"]),
        "rungs": canonical_hash(receipt["rungs"]),
        "clusters": canonical_hash({key: value["clusters"] for key, value in receipt["rungs"].items()}),
        "outcome": canonical_hash(receipt["outcome"]),
        "resource": canonical_hash(receipt["resource"]),
    }
    payload = {
        "schema": "potts-spectral-tail-size-seal/1.0",
        "decision_id": ACTION_ID,
        "L": receipt["L"],
        "receipt_path": output.name,
        "receipt_sha256": sha256(output),
        "classification_hashes": classifications,
    }
    payload["seal_content_sha256"] = canonical_hash(payload)
    atomic_json(seal_path, payload)


def run_size(args: argparse.Namespace, module, vendor_source: Path) -> int:
    root = args.root.resolve()
    authority = verify_authority(root, args.authority.resolve(), args.L)
    context = {
        "decision_id": ACTION_ID,
        "L": int(args.L),
        "momentum_sector": "k_mom=0",
        "N_eig_mandatory": list(MANDATORY_N_EIG),
        "N_eig_conditional": CONDITIONAL_N_EIG,
        "grouping_tolerances": list(GROUP_TOLS),
        "primary_grouping_tolerance": PRIMARY_GROUP_TOL,
        "absolute_width_ceiling": ABS_WIDTH,
        "vendor_source_sha256": sha256(vendor_source),
        "authority_sha256": sha256(args.authority.resolve()),
        "attempt_consumed": True,
        "no_retry": True,
    }
    receipt = {
        "schema": "potts-spectral-tail-size-receipt/1.0",
        "stage": "PROSPECTIVE_CALIBRATION" if args.L == 12 else "CONDITIONAL_TARGET",
        "status": "RUNNING",
        "L": int(args.L),
        "context": context,
        "environment": environment_receipt(root),
        "ground_and_P2": {},
        "rungs": {},
        "outcome": {},
        "resource": {},
    }
    atomic_json(args.output, receipt)
    started = time.monotonic()
    try:
        H, V, dimension = module.build_potts_k0(args.L, 1.0)
        H = H.tocsr()
        V = V.tocsr()
        receipt["dimension"] = int(dimension)
        ground = ground_and_p2_context(H, V, args.L)
        receipt["ground_and_P2"] = {key: value for key, value in ground.items() if key not in ("psi", "b")}
        atomic_json(args.output, receipt)

        intervals: list[Interval] = []
        previous_slices: tuple[tuple[int, int], ...] = ()
        all_nonwidth = True
        for nominal in MANDATORY_N_EIG:
            rung = run_rung(H, ground, nominal)
            receipt["rungs"][str(nominal)] = rung
            atomic_json(args.output, receipt)
            current_slices = tuple(tuple(item) for item in rung["retained_cluster_slices"])
            nested_ok = not previous_slices or nested_prefix(previous_slices, current_slices)
            rung["nested_with_previous"] = bool(nested_ok)
            all_nonwidth = all_nonwidth and nested_ok and _rung_nonwidth_checks(rung)
            intervals.append(Interval(*rung["K_F_interval"]))
            previous_slices = current_slices
            atomic_json(args.output, receipt)

        mandatory_adjudication = adjudicate_intervals(intervals)
        terminal_label = "256"
        conditional_384_invoked = False
        conditional_384_resource_blocked = False
        projected_384 = _projected_384_rss_gib(receipt["rungs"]["256"])
        if not mandatory_adjudication["width_pass"] and all_nonwidth:
            if args.L < 15 and projected_384 < PROJECTED_RSS_GATE_GIB:
                conditional_384_invoked = True
                rung = run_rung(H, ground, CONDITIONAL_N_EIG)
                receipt["rungs"][str(CONDITIONAL_N_EIG)] = rung
                atomic_json(args.output, receipt)
                current_slices = tuple(tuple(item) for item in rung["retained_cluster_slices"])
                nested_ok = nested_prefix(previous_slices, current_slices)
                rung["nested_with_previous"] = bool(nested_ok)
                all_nonwidth = all_nonwidth and nested_ok and _rung_nonwidth_checks(rung)
                intervals.append(Interval(*rung["K_F_interval"]))
                terminal_label = "384"
                atomic_json(args.output, receipt)
            else:
                conditional_384_resource_blocked = True
                all_nonwidth = False

        final_adjudication = adjudicate_intervals(intervals)
        if all_nonwidth and final_adjudication["width_pass"]:
            status = "CERTIFIED_PASS"
        elif conditional_384_resource_blocked:
            status = "RESOURCE_LIMITED_INCONCLUSIVE"
        elif not all_nonwidth:
            status = "NUMERICAL_ENCLOSURE_INCONCLUSIVE"
        else:
            status = "TRUNCATION_TAIL_INCONCLUSIVE"
        receipt["outcome"] = {
            "status": status,
            "mandatory_adjudication": mandatory_adjudication,
            "final_adjudication": final_adjudication,
            "terminal_N_eig": int(terminal_label),
            "conditional_384_invoked": conditional_384_invoked,
            "conditional_384_resource_blocked": conditional_384_resource_blocked,
            "projected_384_peak_rss_gib": projected_384,
            "physical_claim_promotion": False,
            "fig6_rebuild_authorized": False,
            "manuscript_mutation_authorized": False,
        }
        receipt["resource"] = {
            "elapsed_seconds": float(time.monotonic() - started),
            "max_rss_kib": int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss),
            "ram_cap_gib": RAM_CAP_GIB,
            "scratch_cap_gib": SCRATCH_CAP_GIB,
            "rss_below_cap": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss < RAM_CAP_GIB * 1024**2,
        }
        receipt["status"] = status
        receipt["receipt_content_sha256"] = canonical_hash(receipt)
        atomic_json(args.output, receipt)
        write_seal(args.output, args.seal_output, receipt)
        return 0 if status == "CERTIFIED_PASS" else 2
    except Exception as error:
        receipt["status"] = "EXECUTION_FAILURE"
        receipt["outcome"] = {
            "status": "EXECUTION_FAILURE",
            "error_type": type(error).__name__,
            "error": str(error),
            "physical_claim_promotion": False,
            "fig6_rebuild_authorized": False,
            "manuscript_mutation_authorized": False,
        }
        receipt["resource"] = {
            "elapsed_seconds": float(time.monotonic() - started),
            "max_rss_kib": int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss),
        }
        receipt["receipt_content_sha256"] = canonical_hash(receipt)
        atomic_json(args.output, receipt)
        write_seal(args.output, args.seal_output, receipt)
        return 2


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--authority", type=Path, required=True)
    parser.add_argument("--L", type=int, choices=(12, 13, 14, 15), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seal-output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.seal_output.exists():
        parser.error("output or seal already exists; no retry/overwrite")
    limit = RAM_CAP_GIB * 1024**3
    resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
    module, source = load_vendor(args.root.resolve())
    return run_size(args, module, source)


if __name__ == "__main__":
    raise SystemExit(main())
