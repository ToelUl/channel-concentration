#!/usr/bin/env python3
"""One-attempt fixed-retained-eigenpair Potts reproduction for one size."""
from __future__ import annotations

import argparse
import ast
import importlib.util
import json
import os
import resource
import sys
import time
from pathlib import Path

os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"


HERE = Path(__file__).resolve()
PROJECT = HERE.parents[2]
VENDOR = PROJECT / "repro/vendor/potts_tail"
sys.path.insert(0, str(VENDOR))

from common import candidate_run, canonical_hash, environment_receipt, read_json, require, sha256, write_json, project_config, safe_candidate_path, reject_symlinks  # noqa: E402

MODEL_SHA256 = "fef7cd67619a4bc0827cb28e0a5da70b4352dea373fa790f130ce89437d1e104"
TAIL_CORE_SHA256 = "f5155139141d5495cf628a91dfc36561f921d5a29dfb22ed2c11cc17f1a3a310"



def dependency_preflight(project: Path = PROJECT) -> dict:
    """Zero-compute dependency check. Does not import solver code or touch a ledger."""
    vendor = project / "repro/vendor/potts_tail"
    config_path = project / "repro/config/potts_retained_eigenpairs_cleanroom.json"
    required = [config_path, vendor / "simulate_interacting_benchmarks.py",
                vendor / "spectral_tail_core.py", vendor / "spectral_tail_runner.py"]
    errors = []
    for path in required:
        try:
            reject_symlinks(path)
        except ValueError:
            errors.append(f"unsafe dependency link: {path.relative_to(project)}")
            continue
        if not path.is_file():
            errors.append(f"missing/unsafe dependency: {path.relative_to(project)}")
        elif path.suffix == ".py":
            try:
                ast.parse(path.read_text(encoding="utf-8"))
            except (SyntaxError, UnicodeError) as error:
                errors.append(f"invalid dependency syntax: {path.name}: {error}")
    if not errors:
        if sha256(vendor / "simulate_interacting_benchmarks.py") != MODEL_SHA256:
            errors.append("frozen model hash mismatch")
        if sha256(vendor / "spectral_tail_core.py") != TAIL_CORE_SHA256:
            errors.append("frozen tail-core hash mismatch")
        try:
            config = read_json(config_path)
            if config["active_sizes"] != list(range(6, 15)) or config["n_eigenpairs_requested"] != 256:
                errors.append("retained-eigenpair domain contract mismatch")
        except (KeyError, ValueError) as error:
            errors.append(f"invalid config: {error}")
    for name in ("numpy", "scipy"):
        if importlib.util.find_spec(name) is None:
            errors.append(f"required installed module missing: {name}")
    return {"schema": "cc-t3-dependency-preflight/1.0", "status": "PASS" if not errors else "FAIL",
            "project_root": str(project.resolve()), "errors": errors,
            "solver_started": False, "ledger_touched": False,
            "scope": "dependency and frozen-source checks only; not execution authority or environment qualification"}


def initialize_solver_runtime() -> None:
    global np, la, GROUP_TOLS, PRIMARY_GROUP_TOL, frozen_group_slices, ground_and_p2_context, run_rung
    import numpy as np
    import scipy.linalg as la
    from spectral_tail_core import GROUP_TOLS, PRIMARY_GROUP_TOL, frozen_group_slices
    from spectral_tail_runner import ground_and_p2_context, run_rung

def load_model():
    source = VENDOR / "simulate_interacting_benchmarks.py"
    require(sha256(source) == MODEL_SHA256, "frozen Potts model hash mismatch")
    require(sha256(VENDOR / "spectral_tail_core.py") == TAIL_CORE_SHA256, "frozen tail-core hash mismatch")
    spec = importlib.util.spec_from_file_location("cleanroom_frozen_potts", source)
    require(spec is not None and spec.loader is not None, "cannot load frozen Potts source")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def reference_value(entry: dict) -> float:
    if entry["kind"] == "released_scalar":
        return float(entry["value"])
    return 0.5 * (float(entry["lower"]) + float(entry["upper"]))


def dense_full_sector(module, L: int, H, V) -> dict:
    evals, evecs = la.eigh(H.toarray())
    residuals = np.linalg.norm(H @ evecs - evecs * evals[np.newaxis, :], axis=0)
    signatures = {
        f"{tol:.1e}": frozen_group_slices(evals, tol)
        for tol in GROUP_TOLS
    }
    primary = signatures[f"{PRIMARY_GROUP_TOL:.1e}"]
    stable = all(signature == primary for signature in signatures.values())
    psi = evecs[:, 0]
    b = V @ psi
    b = b - float(psi @ b) * psi
    amps2 = np.abs(evecs.T @ b) ** 2
    weights = module.group_level_weights(evals, amps2, float(evals[0]), PRIMARY_GROUP_TOL)
    p2 = float(np.sum(weights))
    p4 = float(np.sum(weights * weights))
    kf = p4 / (p2 * p2)
    return {
        "method": "complete-sector-dense",
        "n_eigenpairs_effective": int(len(evals)),
        "K_F": kf,
        "K_F_interval": [kf, kf],
        "K_F_interval_width": 0.0,
        "P2": p2,
        "P4": p4,
        "solve_residual_abs": 0.0,
        "max_eigenpair_residual_abs": float(np.max(residuals)),
        "complete_cluster": bool(primary and primary[-1][1] == len(evals)),
        "grouping_stable": bool(stable),
        "grouping_signatures": {
            key: [list(item) for item in signature] for key, signature in signatures.items()
        },
    }


def sparse_retained_eigenpairs(H, V, L: int, n_eigenpairs_requested: int) -> dict:
    ground = ground_and_p2_context(H, V, L)
    rung = run_rung(H, ground, n_eigenpairs_requested)
    lower, upper = map(float, rung["K_F_interval"])
    return {
        "method": "calibrated-retained-eigenpair-spectral-tail",
        "n_eigenpairs_effective": int(n_eigenpairs_requested),
        "K_F": 0.5 * (lower + upper),
        "K_F_interval": [lower, upper],
        "K_F_interval_width": float(upper - lower),
        "P2_interval": ground["P2_interval"],
        "solve_residual_abs": float(ground["solve_residual_abs"]),
        "max_eigenpair_residual_abs": float(rung["max_eigenpair_residual_abs"]),
        "complete_cluster": bool(rung["retained_cluster_slices"]),
        "grouping_stable": bool(rung["grouping_stable"]),
        "retained_cluster_slices": rung["retained_cluster_slices"],
        "grouping_signatures": rung["grouping_signatures"],
        "tail_resolvent_upper": rung["tail_resolvent_upper"],
        "nominal_N_eig": int(rung["nominal_N_eig"]),
        "guard_eigenpairs": int(rung["guard_eigenpairs"]),
        "solver_eigenpairs": int(rung["solver_eigenpairs"]),
        "clusters": rung["clusters"],
        "raw_rung_sha256": rung["raw_rung_sha256"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument("--run-root", type=Path)
    parser.add_argument("--L", type=int)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--route-authority", type=Path)
    args = parser.parse_args()
    preflight = dependency_preflight()
    if args.preflight_only:
        print(json.dumps(preflight, indent=2))
        return 0 if preflight["status"] == "PASS" else 1
    require(preflight["status"] == "PASS", "T3 dependency preflight failed")
    require(project_config()["authority"]["new_scientific_compute"] != "NONE", "current candidate grants no T3 compute authority")
    require(args.run_root is not None and args.L is not None and args.output is not None and args.route_authority is not None,
            "execution requires run-root/L/output/route-authority")
    run = candidate_run(args.run_root)
    args.output = safe_candidate_path(args.output)
    args.route_authority = safe_candidate_path(args.route_authority)
    expected_output = run.root / f"work/potts/L{args.L}_retained_eigenpairs_receipt.json"
    require(args.output == expected_output, "size output must use the selected run's exact Potts path")
    require(args.route_authority == run.receipts / "potts.route-authority.json",
            "route authority must belong to the selected run")
    authority = read_json(args.route_authority)
    require(authority.get("schema") == "channel-concentration-route-authority/1.0", "route authority schema mismatch")
    require(authority.get("route") == "potts" and authority.get("role") in {"primary", "replicate"},
            "route authority role/route mismatch")
    matching_tasks = [task for task in authority.get("tasks", []) if task.get("task_id") == f"potts-L{args.L}"]
    require(matching_tasks == [{"task_id": f"potts-L{args.L}", "L": args.L, "n_eigenpairs_requested": 256}],
            "size is not uniquely preauthorized at N=256")
    context = read_json(run.root / "context.json")
    require(authority.get("source_tree_sha256") == context.get("source_tree_sha256"),
            "route authority source binding mismatch")
    initialize_solver_runtime()
    require(not args.output.exists(), "output exists; same-size retry/overwrite forbidden")
    config = read_json(PROJECT / "repro/config/potts_retained_eigenpairs_cleanroom.json")
    require(args.L in config["active_sizes"], "size is not authorized")
    require(args.L not in config["forbidden_sizes"], "forbidden size")
    n_eigenpairs_requested = int(config["n_eigenpairs_requested"])
    require(n_eigenpairs_requested == 256, "retained-eigenpair request contract mismatch")
    started = time.monotonic()
    receipt = {
        "schema": "potts-retained-eigenpairs-size-receipt/1.1",
        "decision_id": config["decision_id"],
        "L": args.L,
        "status": "RUNNING",
        "n_eigenpairs_requested": n_eigenpairs_requested,
        "legacy_field_mapping": "k_target -> n_eigenpairs_requested",
        "same_size_retry_forbidden": True,
        "fresh_result_is_ladder_certificate": False,
        "role": authority["role"],
        "route_authority_sha256": sha256(args.route_authority),
        "source_tree_sha256": context["source_tree_sha256"],
    }
    write_json(args.output, receipt)
    try:
        module = load_model()
        H, V, dimension = module.build_potts_k0(args.L, config["coupling_g"])
        H, V = H.tocsr(), V.tocsr()
        receipt["sector_dimension"] = int(dimension)
        if dimension <= n_eigenpairs_requested + config["guard_eigenpairs"]:
            result = dense_full_sector(module, args.L, H, V)
        else:
            result = sparse_retained_eigenpairs(H, V, args.L, n_eigenpairs_requested)
        receipt.update(result)
        ref_entry = config["reference"][str(args.L)]
        ref = reference_value(ref_entry)
        delta = abs(float(result["K_F"]) - ref)
        checks = {
            "complete_cluster": bool(result["complete_cluster"]),
            "solve_residual": float(result["solve_residual_abs"]) <= config["solve_residual_ceiling"],
            "eigenpair_residual": float(result["max_eigenpair_residual_abs"]) <= config["eigenpair_residual_ceiling"],
            "grouping_stability_same_eigenpairs": bool(result["grouping_stable"]),
            "absolute_reference_agreement": delta <= config["reference_agreement_ceiling"],
        }
        receipt["reference"] = ref_entry
        receipt["reference_value"] = ref
        receipt["absolute_reference_difference"] = delta
        receipt["acceptance"] = checks
        receipt["status"] = config["fresh_campaign_success_label"] if all(checks.values()) else "RETAINED_EIGENPAIR_REPRODUCTION_INCONCLUSIVE"
        receipt["resources"] = environment_receipt(started)
        receipt["receipt_content_sha256"] = canonical_hash(receipt)
        write_json(args.output, receipt)
        return 0 if all(checks.values()) else 2
    except Exception as error:
        receipt["status"] = "EXECUTION_FAILURE"
        receipt["error_type"] = type(error).__name__
        receipt["error"] = str(error)
        receipt["resources"] = environment_receipt(started)
        receipt["receipt_content_sha256"] = canonical_hash(receipt)
        write_json(args.output, receipt)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
