#!/usr/bin/env python3
"""Derive ranked NNN-TFIM distribution-convergence evidence.

This deterministic postprocessing program reads the hash-sealed response
checkpoints from the publication run.  It performs no Hamiltonian
construction, eigensolve, response solve, or fit.  For each released scalar
benchmark it selects the highest-retained-level checkpoint reproducing that
benchmark, forms ``pi_r = x_r / P2``, and compares the decreasingly ranked
weights with the exact finite-size TFIM distribution.  Any response weight not
represented by the retained ``x`` vector remains explicit as one unresolved
tail bin in the ranked total-variation distance.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import sys
from typing import Iterable

import numpy as np


PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / "scripts/cleanroom"))
from common import candidate_run, safe_candidate_path
DATA = PROJECT / "data" / "reproducibility"
EVIDENCE = PROJECT / "repro/evidence" / "nnn_tfim_publication_run"
DEFAULT_BENCHMARKS = DATA / "interacting_benchmarks.csv"
DEFAULT_MANIFEST = EVIDENCE / "checkpoint_manifest.json"
DEFAULT_CHECKPOINT_DIR = EVIDENCE / "checkpoints"
DEFAULT_TABLE = DATA / "nnn_ranked_distribution_convergence.csv"
DEFAULT_RECEIPT = DATA / "nnn_ranked_distribution_convergence_receipt.json"

EXPECTED_BENCHMARKS_SHA256 = (
    "ed10ff3be1c5d6829e09850a565cda649c1a480e994ae7864da42f2b7c6d63d9"
)
EXPECTED_MANIFEST_SHA256 = (
    "e09472261c18e25e03b7945d7bb1982dcbc3d4aae19919a5173592508f13b5e1"
)
COUPLINGS = (0.05, 0.10, 0.20)
SIZES = tuple(range(6, 21, 2))
KF_MATCH_TOLERANCE = 5.0e-10
MASS_TOLERANCE = 1.0e-8


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def relative(path: Path) -> str:
    resolved = path.resolve()
    return str(resolved.relative_to(PROJECT)) if resolved.is_relative_to(PROJECT) else str(resolved)


def coupling_tag(coupling: float) -> str:
    return {0.05: "0p05", 0.10: "0p1", 0.20: "0p2"}[coupling]


def exact_tfim_weights(size: int) -> np.ndarray:
    if size < 4 or size % 2:
        raise ValueError("the exact NS TFIM reference requires even L >= 4")
    ranks = np.arange(size // 2, dtype=float)
    momenta = (2.0 * ranks + 1.0) * np.pi / size
    weights = 0.0625 / np.tan(0.5 * momenta) ** 2
    return weights / weights.sum()


def exact_tfim_kf(size: int) -> float:
    return (2.0 / 3.0) * (size * size + size - 3.0) / (size * (size - 1.0))


def validate_descending(values: np.ndarray, *, name: str) -> None:
    if values.ndim != 1 or len(values) == 0:
        raise RuntimeError(f"{name} is not a nonempty one-dimensional vector")
    if not np.all(np.isfinite(values)) or np.any(values < 0.0):
        raise RuntimeError(f"{name} contains a negative or nonfinite weight")
    if np.any(values[1:] > values[:-1] + 1.0e-14 * np.maximum(1.0, values[:-1])):
        raise RuntimeError(f"{name} is not decreasingly ranked")


def ranked_total_variation(
    retained_weights: np.ndarray,
    exact_weights: np.ndarray,
    unresolved_mass: float,
) -> float:
    validate_descending(retained_weights, name="retained ranked weights")
    validate_descending(exact_weights, name="exact ranked weights")
    if unresolved_mass < -MASS_TOLERANCE:
        raise RuntimeError("unresolved response mass is materially negative")
    unresolved_mass = max(0.0, unresolved_mass)
    count = max(len(retained_weights), len(exact_weights))
    retained = np.zeros(count, dtype=float)
    reference = np.zeros(count, dtype=float)
    retained[: len(retained_weights)] = retained_weights
    reference[: len(exact_weights)] = exact_weights
    return 0.5 * (
        float(np.sum(np.abs(retained - reference))) + unresolved_mass
    )


def selftest() -> None:
    for size in SIZES:
        exact = exact_tfim_weights(size)
        if abs(float(exact.sum()) - 1.0) > 5.0e-15:
            raise RuntimeError("exact TFIM normalization oracle failed")
        if abs(float(exact @ exact) - exact_tfim_kf(size)) > 5.0e-14:
            raise RuntimeError("exact TFIM K_F oracle failed")
        if ranked_total_variation(exact, exact, 0.0) > 1.0e-15:
            raise RuntimeError("identical-distribution oracle failed")
    if abs(ranked_total_variation(np.array([0.8]), np.array([1.0]), 0.2) - 0.2) > 1e-15:
        raise RuntimeError("unresolved-tail oracle failed")
    try:
        validate_descending(np.array([0.6, 0.1, 0.3]), name="seeded unsorted vector")
    except RuntimeError:
        pass
    else:
        raise RuntimeError("seeded rank-order failure probe was not rejected")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path)
    parser.add_argument("--source-contract", choices=("historical", "current"), default="historical")
    parser.add_argument("--benchmarks", type=Path, default=None)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--evidence-root", type=Path, help="read-only extracted historical project")
    parser.add_argument("--checkpoint-dir", type=Path)
    parser.add_argument("--run-metadata", type=Path)
    parser.add_argument("--table", type=Path, default=None)
    parser.add_argument("--receipt", type=Path, default=None)
    parser.add_argument("--selftest-only", action="store_true")
    return parser.parse_args()


def read_benchmarks(path: Path) -> dict[tuple[float, int], dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = [
            row
            for row in csv.DictReader(handle)
            if row["model"] == "NNN-TFIM"
            and float(row["lambda_or_g"]) in COUPLINGS
        ]
    selected = {(float(row["lambda_or_g"]), int(row["L"])): row for row in rows}
    expected = {(coupling, size) for coupling in COUPLINGS for size in SIZES}
    if set(selected) != expected:
        raise RuntimeError("released NNN-TFIM benchmark grid is incomplete or duplicated")
    return selected


def read_manifest(path: Path) -> dict[str, str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    entries = payload.get("checkpoints", [])
    mapping = {str(entry["path"]): str(entry["sha256"]) for entry in entries}
    if payload.get("checkpoint_count") != len(mapping):
        raise RuntimeError("checkpoint manifest count is inconsistent")
    return mapping


def checkpoint_candidates(
    checkpoint_dir: Path,
    manifest: dict[str, str],
    coupling: float,
    size: int,
) -> Iterable[tuple[Path, dict[str, object]]]:
    pattern = f"response_j2_{coupling_tag(coupling)}_L{size}_*.json"
    for path in sorted(checkpoint_dir.glob(pattern)):
        expected_hash = manifest.get(path.name)
        if expected_hash is None:
            raise RuntimeError(f"checkpoint is absent from the sealed manifest: {path.name}")
        actual_hash = sha256(path)
        if actual_hash != expected_hash:
            raise RuntimeError(f"checkpoint identity mismatch: {path.name}")
        payload = json.loads(path.read_text(encoding="utf-8"))
        task = payload.get("task", {})
        result = payload.get("result", {})
        if payload.get("status") != "complete" or task.get("kind") != "response":
            continue
        if task.get("suffix", "") != "":
            continue
        if int(task.get("L", -1)) != size or abs(float(task.get("lambda_or_g")) - coupling) > 1e-15:
            raise RuntimeError(f"checkpoint task identity mismatch: {path.name}")
        if int(result.get("L", -1)) != size or abs(float(result.get("lambda_or_g")) - coupling) > 1e-15:
            raise RuntimeError(f"checkpoint result identity mismatch: {path.name}")
        yield path, payload


def select_checkpoint(
    checkpoint_dir: Path,
    manifest: dict[str, str],
    benchmark: dict[str, str],
    coupling: float,
    size: int,
) -> tuple[Path, dict[str, object]]:
    target_kf = float(benchmark["KF"])
    matches = []
    for path, payload in checkpoint_candidates(
        checkpoint_dir, manifest, coupling, size
    ):
        result = payload["result"]
        difference = abs(float(result["KF"]) - target_kf)
        if difference <= KF_MATCH_TOLERANCE:
            retained_count = int(
                result.get("n_low_energy_eigenpairs", result.get("k_low", 0))
            )
            matches.append((retained_count, -difference, path, payload))
    if not matches:
        raise RuntimeError(f"no sealed checkpoint reproduces J2={coupling}, L={size}")
    _, _, path, payload = max(matches, key=lambda item: (item[0], item[1]))
    return path, payload


def main() -> None:
    args = parse_args()
    selftest()
    if args.selftest_only:
        print("selftest: PASS")
        return

    run = candidate_run(args.run_root)
    evidence_root = (args.evidence_root or PROJECT).resolve()
    benchmarks_path = (args.benchmarks or (evidence_root / "data/reproducibility" / DEFAULT_BENCHMARKS.name if args.source_contract == "historical" else run.data / DEFAULT_BENCHMARKS.name)).resolve()
    if args.source_contract == "historical":
        manifest_path = (args.manifest or evidence_root / DEFAULT_MANIFEST.relative_to(PROJECT)).resolve()
        checkpoint_dir = (args.checkpoint_dir or evidence_root / DEFAULT_CHECKPOINT_DIR.relative_to(PROJECT)).resolve()
        metadata_path = None
    else:
        manifest_path = (args.manifest or run.root / "work/nnn_tfim_expensive/checkpoint_manifest.json").resolve()
        checkpoint_dir = (args.checkpoint_dir or run.root / "work/nnn_tfim_expensive/checkpoints").resolve()
        metadata_path = (args.run_metadata or run.data / "nnn_tfim_expensive_run_metadata.json").resolve()
    table_path = safe_candidate_path(args.table or run.data / DEFAULT_TABLE.name)
    receipt_path = safe_candidate_path(args.receipt or run.data / DEFAULT_RECEIPT.name)
    if table_path.parent != run.data or receipt_path.parent != run.data:
        raise ValueError("derived outputs must belong to the selected run data directory")
    metadata_hash = None
    if args.source_contract == "historical":
        if sha256(benchmarks_path) != EXPECTED_BENCHMARKS_SHA256:
            raise RuntimeError("released interacting benchmark identity mismatch")
        if sha256(manifest_path) != EXPECTED_MANIFEST_SHA256:
            raise RuntimeError("sealed checkpoint manifest identity mismatch")
    else:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        metadata_hash = sha256(metadata_path)
        output_hashes = {str(item["path"]): str(item["sha256"]) for item in metadata.get("outputs", [])}
        if output_hashes.get(relative(benchmarks_path)) != sha256(benchmarks_path):
            raise RuntimeError("current benchmark is not bound by the current run metadata")
        manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest_payload.get("checkpoint_count") != 69 or manifest_payload.get("preregistered_unique_task_count") != 69:
            raise RuntimeError("current checkpoint manifest is not the preregistered 69-task set")
        for field in ("engine_sha256", "config_sha256", "solver_environment_sha256"):
            if manifest_payload.get(field) != metadata.get(field):
                raise RuntimeError(f"current manifest/metadata {field} mismatch")

    benchmarks = read_benchmarks(benchmarks_path)
    manifest = read_manifest(manifest_path)
    table_rows: list[dict[str, object]] = []
    summaries: list[dict[str, object]] = []
    selected_sources: dict[str, str] = {}

    for size in SIZES:
        exact = exact_tfim_weights(size)
        exact_p2 = size * (size - 1.0) / 32.0
        for rank, weight in enumerate(exact, start=1):
            table_rows.append(
                {
                    "model": "exact-TFIM",
                    "J2": 0.0,
                    "L": size,
                    "rank": rank,
                    "x": weight * exact_p2,
                    "pi": weight,
                    "n_low_energy_eigenpairs": "analytic",
                    "P2": exact_p2,
                    "KF": exact_tfim_kf(size),
                    "retained_mass": 1.0,
                    "unresolved_mass": 0.0,
                    "D_TV_ranked": 0.0,
                    "source_checkpoint": "analytic NS momentum-block formula",
                    "source_sha256": "analytic",
                }
            )

    for coupling in COUPLINGS:
        coupling_summaries = []
        for size in SIZES:
            benchmark = benchmarks[(coupling, size)]
            path, payload = select_checkpoint(
                checkpoint_dir, manifest, benchmark, coupling, size
            )
            result = payload["result"]
            x_values = np.asarray(result["x"], dtype=float)
            validate_descending(x_values, name=f"J2={coupling}, L={size} x")
            p2 = float(result["P2"])
            weights = x_values / p2
            retained_mass = float(weights.sum())
            unresolved_mass = max(0.0, 1.0 - retained_mass)
            if retained_mass > 1.0 + MASS_TOLERANCE:
                raise RuntimeError(f"retained response mass exceeds unity at J2={coupling}, L={size}")
            distance = ranked_total_variation(
                weights, exact_tfim_weights(size), unresolved_mass
            )
            checkpoint_hash = sha256(path)
            selected_sources[relative(path)] = checkpoint_hash
            for rank, (x_value, weight) in enumerate(
                zip(x_values, weights), start=1
            ):
                table_rows.append(
                    {
                        "model": "NNN-TFIM",
                        "J2": coupling,
                        "L": size,
                        "rank": rank,
                        "x": float(x_value),
                        "pi": float(weight),
                        "n_low_energy_eigenpairs": int(
                            result.get("n_low_energy_eigenpairs", result.get("k_low"))
                        ),
                        "P2": p2,
                        "KF": float(result["KF"]),
                        "retained_mass": retained_mass,
                        "unresolved_mass": unresolved_mass,
                        "D_TV_ranked": distance,
                        "source_checkpoint": relative(path),
                        "source_sha256": checkpoint_hash,
                    }
                )
            coupling_summaries.append(
                {
                    "L": size,
                    "n_low_energy_eigenpairs": int(
                        result.get("n_low_energy_eigenpairs", result.get("k_low"))
                    ),
                    "rank_count": len(weights),
                    "retained_mass": retained_mass,
                    "unresolved_mass": unresolved_mass,
                    "D_TV_ranked": distance,
                    "checkpoint": relative(path),
                    "checkpoint_sha256": checkpoint_hash,
                }
            )
        distances = [float(item["D_TV_ranked"]) for item in coupling_summaries]
        summaries.append(
            {
                "J2": coupling,
                "sizes": coupling_summaries,
                "endpoint_contraction": distances[-1] < distances[0],
                "endpoint_contraction_factor": distances[0] / distances[-1],
                "strictly_monotone_nonincreasing": all(
                    following <= current
                    for current, following in zip(distances, distances[1:])
                ),
            }
        )

    fieldnames = [
        "model",
        "J2",
        "L",
        "rank",
        "x",
        "pi",
        "n_low_energy_eigenpairs",
        "P2",
        "KF",
        "retained_mass",
        "unresolved_mass",
        "D_TV_ranked",
        "source_checkpoint",
        "source_sha256",
    ]
    table_path.parent.mkdir(parents=True, exist_ok=True)
    with table_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in table_rows:
            writer.writerow(
                {
                    key: format(value, ".17g") if isinstance(value, float) else value
                    for key, value in row.items()
                }
            )

    receipt = {
        "schema": "nnn-ranked-distribution-convergence/1.0",
        "decision_id": "FIG7-ISING-DISTRIBUTION-CONVERGENCE-R1/OPTION-A",
        "claim_ceiling": (
            "OVERALL_ENDPOINT_CONTRACTION_AND_L20_PROXIMITY_UNDER_THE_MATCHED_"
            "RANKED_LEVEL_PROJECTOR_CONTRACT;_NO_STRICT_MONOTONICITY_OR_"
            "UNIVERSALITY_PROOF"
        ),
        "source_contract": {
            "mode": args.source_contract,
            "benchmarks": relative(benchmarks_path),
            "benchmarks_sha256": sha256(benchmarks_path),
            "checkpoint_manifest": relative(manifest_path),
            "checkpoint_manifest_sha256": sha256(manifest_path),
            "selected_checkpoint_sha256s": dict(sorted(selected_sources.items())),
            "run_metadata": relative(metadata_path) if metadata_path is not None else None,
            "run_metadata_sha256": metadata_hash,
        },
        "observable_contract": {
            "rank_order": "decreasing projector response weight",
            "lattice_weight": "pi_r=x_r/P2 without retained-spectrum renormalization",
            "exact_reference": "finite-size critical NS TFIM momentum-block distribution",
            "distance": (
                "D_TV_ranked=0.5*(sum_r|pi_r_NNN-pi_r_TFIM|+unresolved_mass), "
                "with absent ranks padded by zero"
            ),
            "unresolved_tail": "one explicit aggregate bin of mass 1-sum_r pi_r",
        },
        "couplings": list(COUPLINGS),
        "sizes": list(SIZES),
        "summaries": summaries,
        "all_endpoint_contractions": all(
            bool(item["endpoint_contraction"]) for item in summaries
        ),
        "strict_monotonicity_claimed": False,
        "table_path": relative(table_path),
        "table_sha256": sha256(table_path),
        "selftests": {
            "exact_normalization": "PASS",
            "exact_KF_closed_form": "PASS",
            "identity_distance": "PASS",
            "unresolved_tail": "PASS",
            "seeded_unsorted_vector_rejected": "PASS",
        },
        "scientific_compute_performed": False,
        "postprocessing_only": True,
    }
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(receipt, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
