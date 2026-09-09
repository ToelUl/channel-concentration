#!/usr/bin/env python3
"""Reproduce the parity PRG and large-size NNN-TFIM diagnostics.

This is the single entry point for the expensive reproducibility path.
It derives pseudo-critical fields from the k=0 odd-even global-spin-flip gap,
computes response-sector channel moments, writes the convergence/sensitivity/
fit diagnostics, and records checkpoint, solver, environment, and checksum
provenance.  Every task is checkpointed atomically and can be resumed without
editing source parameters.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import platform
import resource
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any, Callable

os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")

import numpy as np
import scipy
from scipy.optimize import brentq

import simulate_interacting_benchmarks as engine


SCHEMA_VERSION = "nnn-tfim-expensive-output/1.0.0"
BENCH_FIELDS = [
    "model", "L", "dim", "lambda_or_g", "h", "KF", "KF_half", "P2",
    "P4_low", "Neff", "gap_times_L", "solve_res", "n_levels", "method",
    "seconds", "note",
]
WEIGHT_FIELDS = ["model", "L", "rank", "x", "pi", "source", "KF_of_distribution"]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stable_hash(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def solver_environment() -> dict[str, Any]:
    """Return the numerical environment that controls checkpoint compatibility."""
    blas = np.__config__.CONFIG.get("Build Dependencies", {}).get("blas", {})
    return {
        "python": sys.version.split()[0],
        "python_implementation": platform.python_implementation(),
        "numpy": np.__version__,
        "scipy": scipy.__version__,
        "platform": platform.platform(),
        "machine": platform.machine(),
        "blas": {
            "name": blas.get("name", "unknown"),
            "version": blas.get("version", "unknown"),
            "configuration": blas.get("openblas configuration", ""),
        },
        "thread_environment": {
            key: os.environ.get(key)
            for key in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS")
        },
    }


def atomic_write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def atomic_write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(value)
    temporary.replace(path)


def atomic_write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})
    temporary.replace(path)


def validate_resume_checkpoint_store(
    workdir: Path, engine_hash: str, config_hash: str, environment_hash: str,
) -> None:
    """Fail closed before reuse if the pre-resume checkpoint store is not intact."""
    checkpoint_dir = workdir / "checkpoints"
    manifest_path = workdir / "checkpoint_manifest.json"
    checkpoint_files = sorted(checkpoint_dir.glob("*.json")) if checkpoint_dir.is_dir() else []
    if not checkpoint_files and not manifest_path.exists():
        return
    if not manifest_path.is_file():
        raise RuntimeError("resume checkpoint store has files but no trusted pre-resume manifest")
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("schema_version") != "nnn-tfim-checkpoint-manifest/1.1.0":
        raise RuntimeError("unsupported pre-resume checkpoint manifest schema")
    expected_hashes = {
        "engine_sha256": engine_hash,
        "config_sha256": config_hash,
        "solver_environment_sha256": environment_hash,
    }
    for field, expected in expected_hashes.items():
        if manifest.get(field) != expected:
            raise RuntimeError(f"pre-resume checkpoint manifest {field} mismatch")
    records = manifest.get("checkpoints", [])
    by_name = {str(record.get("path", "")): record for record in records}
    if len(by_name) != len(records) or manifest.get("checkpoint_count") != len(records):
        raise RuntimeError("pre-resume checkpoint manifest has duplicate or inconsistent records")
    actual_names = {path.name for path in checkpoint_files}
    if set(by_name) != actual_names:
        raise RuntimeError(
            "pre-resume checkpoint set mismatch: "
            f"missing={sorted(set(by_name) - actual_names)}, extra={sorted(actual_names - set(by_name))}"
        )
    for name, record in by_name.items():
        path = checkpoint_dir / name
        if sha256_file(path) != record.get("sha256"):
            raise RuntimeError(f"pre-resume checkpoint digest mismatch: {name}")
        payload = json.loads(path.read_text())
        if payload.get("status") != "complete":
            raise RuntimeError(f"pre-resume checkpoint is incomplete: {name}")
        for field, expected in expected_hashes.items():
            if payload.get(field) != expected:
                raise RuntimeError(f"pre-resume checkpoint {field} mismatch: {name}")


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


class EventLog:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.records: list[dict[str, Any]] = []
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("")

    def emit(self, event: str, **fields: Any) -> None:
        record = {
            "elapsed_seconds": fields.pop("elapsed_seconds", None),
            "event": event,
            **fields,
        }
        self.records.append(record)
        # Rewrite the complete in-memory ledger atomically.  This makes every
        # durable generation self-contained and avoids relying on incremental
        # append persistence for the authoritative execution trace.
        atomic_write_text(
            self.path,
            "".join(json.dumps(item, sort_keys=True) + "\n" for item in self.records),
        )
        detail = " ".join(f"{key}={value}" for key, value in fields.items())
        print(f"[{event}] {detail}".rstrip(), flush=True)


def validate_event_ledger(
    path: Path, computed_tasks: int, resumed_tasks: int, *, require_complete: bool,
) -> None:
    """Require the durable event ledger to support the reported task lineage."""
    records = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    by_event = Counter(record.get("event") for record in records)
    expected = {
        "run-start": 1,
        "task-start": computed_tasks,
        "task-complete": computed_tasks,
        "checkpoint-resume": resumed_tasks,
        "run-complete": 1 if require_complete else 0,
    }
    unexpected = set(by_event) - set(expected)
    if unexpected or any(by_event[event] != count for event, count in expected.items()):
        raise RuntimeError(
            f"event ledger count mismatch: expected={expected}, actual={dict(by_event)}, "
            f"unexpected={sorted(unexpected)}"
        )
    starts = Counter(record.get("key") for record in records if record.get("event") == "task-start")
    completes = Counter(record.get("key") for record in records if record.get("event") == "task-complete")
    if starts != completes:
        raise RuntimeError(
            "event ledger task pairing mismatch: "
            f"start_only={dict(starts - completes)}, complete_only={dict(completes - starts)}"
        )
    if require_complete:
        terminal = next(record for record in records if record.get("event") == "run-complete")
        if (
            terminal.get("computed_tasks") != computed_tasks
            or terminal.get("resumed_tasks") != resumed_tasks
        ):
            raise RuntimeError("event ledger terminal lineage mismatch")


class Checkpoints:
    def __init__(self, directory: Path, engine_hash: str, config_hash: str,
                 environment_hash: str, resume: bool, events: EventLog) -> None:
        self.directory = directory
        self.engine_hash = engine_hash
        self.config_hash = config_hash
        self.environment_hash = environment_hash
        self.resume = resume
        self.events = events
        self.resumed_count = 0
        self.computed_count = 0
        directory.mkdir(parents=True, exist_ok=True)

    def run(self, key: str, task: dict[str, Any], function: Callable[[], dict[str, Any]]) -> dict[str, Any]:
        path = self.directory / f"{key}.json"
        task_hash = stable_hash(task)
        if self.resume and path.exists():
            saved = json.loads(path.read_text())
            if (
                saved.get("engine_sha256") == self.engine_hash
                and saved.get("config_sha256") == self.config_hash
                and saved.get("solver_environment_sha256") == self.environment_hash
                and saved.get("task_sha256") == task_hash
                and saved.get("status") == "complete"
            ):
                self.resumed_count += 1
                self.events.emit("checkpoint-resume", key=key)
                resumed_result = dict(saved["result"])
                resumed_result["_task_seconds"] = float(saved["elapsed_seconds"])
                return resumed_result
        self.events.emit("task-start", key=key)
        started = time.perf_counter()
        result = function()
        self.computed_count += 1
        elapsed = time.perf_counter() - started
        record = {
            "schema_version": "nnn-tfim-checkpoint/1.1.0",
            "status": "complete",
            "engine_sha256": self.engine_hash,
            "config_sha256": self.config_hash,
            "solver_environment_sha256": self.environment_hash,
            "task_sha256": task_hash,
            "task": task,
            "elapsed_seconds": elapsed,
            "result": result,
        }
        atomic_write_json(path, record)
        self.events.emit("task-complete", key=key, elapsed_seconds=elapsed)
        returned_result = dict(result)
        returned_result["_task_seconds"] = elapsed
        return returned_result


def key_float(value: float) -> str:
    return f"{value:.12g}".replace("-", "m").replace(".", "p")


def publication_checkpoint_keys(config: dict[str, Any]) -> set[str]:
    """Return the exact preregistered publication task-key set.

    A task may appear in both the primary response grid and a convergence
    table.  Those are two consumers of one numerical result, not two solver
    authorizations.  Field-sensitivity tasks remain distinct because their
    suffix and field differ from the primary task.
    """
    j2_values = [float(value) for value in config["prg"]["j2_values"]]
    sizes = [int(value) for value in config["prg"]["sizes"]]
    response_sizes = [int(value) for value in config["response"]["sizes"]]
    keys = {
        f"prg_j2_{key_float(j2)}_L{size}"
        for j2 in j2_values
        for size in sizes
    }
    for j2 in j2_values:
        for size in response_sizes:
            retained = (
                int(config["response"]["n_low_energy_eigenpairs_L20"][f"{j2:g}"])
                if size == 20
                else int(config["response"]["n_low_energy_eigenpairs_default"])
            )
            keys.add(f"response_j2_{key_float(j2)}_L{size}_neig{retained}")
        for size in (16, 18):
            for retained in config["convergence_scans"]["L16_L18"]:
                keys.add(f"response_j2_{key_float(j2)}_L{size}_neig{int(retained)}")
        for retained in config["convergence_scans"]["L20"][f"{j2:g}"]:
            keys.add(f"response_j2_{key_float(j2)}_L20_neig{int(retained)}")
    sensitivity = config["field_sensitivity"]
    j2 = float(sensitivity["j2"])
    size = int(sensitivity["L"])
    retained = int(sensitivity["n_low_energy_eigenpairs"])
    for shift in sensitivity["shifts"]:
        keys.add(
            f"response_j2_{key_float(j2)}_L{size}_neig{retained}"
            f"_dh_{key_float(float(shift))}"
        )
    return keys


def root_task(L: int, j2: float, bracket: tuple[float, float], config: dict[str, Any]) -> dict[str, Any]:
    prg = config["prg"]
    tol = float(prg["eigensolver_tolerance"])
    components: dict[int, tuple[Any, Any]] = {}
    for size in (L - 2, L):
        components[size] = (
            engine.build_nnn_tfim_sector_components_k0_parity(size, j2, +1),
            engine.build_nnn_tfim_sector_components_k0_parity(size, j2, -1),
        )
    evaluations: dict[float, dict[str, Any]] = {}

    def evaluate(h: float) -> float:
        key = float(h)
        if key not in evaluations:
            small = engine.parity_gap_nnn_from_components(*components[L - 2], key, tol=tol)
            large = engine.parity_gap_nnn_from_components(*components[L], key, tol=tol)
            residual = (L - 2) * small["gap"] - L * large["gap"]
            evaluations[key] = {"h": key, "small": small, "large": large, "prg_residual": residual}
        return float(evaluations[key]["prg_residual"])

    left, right = map(float, bracket)
    f_left, f_right = evaluate(left), evaluate(right)
    if f_left * f_right >= 0.0:
        raise RuntimeError(
            f"PRG bracket does not change sign for J2={j2}, L={L}: "
            f"f({left})={f_left:.6e}, f({right})={f_right:.6e}"
        )
    root = float(brentq(
        evaluate,
        left,
        right,
        xtol=float(prg["root_xtol"]),
        rtol=float(prg["root_rtol"]),
        maxiter=int(prg["maximum_root_iterations"]),
    ))
    evaluate(root)
    final = evaluations[min(evaluations, key=lambda value: abs(value - root))]
    return {
        "lambda_or_g": j2,
        "L": L,
        "h": root,
        "bracket_left": left,
        "bracket_right": right,
        "f_left": f_left,
        "f_right": f_right,
        "evaluation_count": len(evaluations),
        **final,
    }


def response_task(
    L: int, j2: float, h: float, n_low_energy_eigenpairs: int,
    config: dict[str, Any],
) -> dict[str, Any]:
    response = config["response"]
    Hzz, X, dim = engine.build_nnn_tfim_sector_components_k0_parity(L, j2, +1)
    H = (Hzz - h * X).tocsr()
    result = engine.hybrid_level_projector_kf(
        H,
        (-X).tocsr(),
        n_low_energy_eigenpairs=n_low_energy_eigenpairs,
        tol_eig=float(response["eigensolver_tolerance"]),
        tol_group=float(response["level_group_tolerance"]),
        rtol_solve=float(response["projected_solve_rtol"]),
        ncv_factor=int(response["ncv_factor"]),
    )
    if int(result.get("minres_info", -1)) != 0:
        raise RuntimeError(
            f"MINRES failed for J2={j2}, L={L}, "
            f"n_low_energy_eigenpairs={n_low_energy_eigenpairs}: {result['minres_info']}"
        )
    return {
        "lambda_or_g": j2,
        "L": L,
        "h": h,
        "sector_dim": dim,
        "n_low_energy_eigenpairs": n_low_energy_eigenpairs,
        "KF": float(result["KF"]),
        "KF_half": float(result["KF_half"]),
        "P2": float(result["P2"]),
        "P4_low": float(result["P4"]),
        "gap": float(result["gap"]),
        "solve_res": float(result["solve_res"]),
        "minres_info": int(result["minres_info"]),
        "n_levels": int(result["n_levels"]),
        "x": [float(value) for value in np.asarray(result["x"])],
    }


def benchmark_row(result: dict[str, Any]) -> dict[str, Any]:
    L = int(result["L"])
    return {
        "model": "NNN-TFIM",
        "L": L,
        "dim": int(result["sector_dim"]),
        "lambda_or_g": f"{float(result['lambda_or_g']):.12g}",
        "h": f"{float(result['h']):.12g}",
        "KF": f"{float(result['KF']):.12g}",
        "KF_half": f"{float(result['KF_half']):.12g}",
        "P2": f"{float(result['P2']):.12g}",
        "P4_low": f"{float(result['P4_low']):.12g}",
        "Neff": f"{1.0 / float(result['KF']):.12g}",
        "gap_times_L": f"{float(result['gap']) * L:.12g}",
        "solve_res": f"{float(result['solve_res']):.3e}",
        "n_levels": int(result["n_levels"]),
        "method": "parity-PRG-sector-hybrid",
        "seconds": f"{float(result.get('_task_seconds', math.nan)):.3f}",
        "note": "finite-size nonintegrable Ising-line control; producer-derived parity PRG",
    }


def exact_tfim_row(L: int) -> dict[str, Any]:
    result = engine.exact_tfim_critical_result(L)
    return {
        "model": "NNN-TFIM", "L": L, "dim": 1 << L, "lambda_or_g": "0",
        "h": "1", "KF": f"{result['KF']:.12g}", "KF_half": "nan", "P2": "nan",
        "P4_low": "nan", "Neff": f"{1.0 / result['KF']:.12g}",
        "gap_times_L": "nan", "solve_res": "nan", "n_levels": 0,
        "method": "exact-TFIM", "seconds": "0.000",
        "note": "exact critical TFIM NS-sector formula",
    }


def weight_rows(result: dict[str, Any], maximum: int) -> list[dict[str, Any]]:
    total = float(result["P2"])
    return [
        {
            "model": "NNN-TFIM", "L": int(result["L"]), "rank": rank,
            "x": f"{value:.16e}", "pi": f"{value / total:.16e}",
            "source": "parity-PRG-sector-hybrid",
            "KF_of_distribution": f"{float(result['KF']):.12g}",
        }
        for rank, value in enumerate(result["x"][:maximum], start=1)
    ]


def fit_rows(bench_rows: list[dict[str, Any]], maximum_L: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for j2 in (0.0, 0.05, 0.1, 0.2):
        selected = sorted(
            [r for r in bench_rows if float(r["lambda_or_g"]) == j2 and int(r["L"]) <= maximum_L],
            key=lambda row: int(row["L"]),
        )
        Ls = np.array([int(r["L"]) for r in selected], dtype=float)
        values = np.array([float(r["KF"]) for r in selected], dtype=float)
        definitions = [
            ("linear all sizes", np.ones(len(Ls), dtype=bool), 1, None),
            ("linear drop L=6", Ls >= 8, 1, None),
            ("linear L>=10", Ls >= 10, 1, None),
        ]
        if maximum_L >= 20:
            definitions.append(("linear L>=12", Ls >= 12, 1, None))
        definitions.extend([
            ("quadratic all sizes", np.ones(len(Ls), dtype=bool), 2, None),
            ("constrained 2/3 plus a/L", np.ones(len(Ls), dtype=bool), 1, 2.0 / 3.0),
        ])
        for label, mask, degree, constrained in definitions:
            x = 1.0 / Ls[mask]
            y = values[mask]
            if constrained is None:
                coefficients = np.polyfit(x, y, degree)
                prediction = np.polyval(coefficients, x)
                intercept = float(coefficients[-1])
            else:
                slope = float(x @ (y - constrained) / (x @ x))
                coefficients = np.array([slope, constrained])
                prediction = slope * x + constrained
                intercept = constrained
            rmse = float(np.sqrt(np.mean((y - prediction) ** 2)))
            rows.append({
                "lambda_or_g": f"{j2:.12g}", "fit": label,
                "sizes": " ".join(str(int(v)) for v in Ls[mask]),
                "K_inf": f"{intercept:.16g}",
                "deviation_from_2_3": f"{intercept - 2.0 / 3.0:.16g}",
                "rmse": f"{rmse:.16g}",
                "coefficients": json.dumps([float(v) for v in coefficients]),
            })
    return rows


def write_fit_outputs(outdir: Path, bench_rows: list[dict[str, Any]]) -> list[Path]:
    fields = ["lambda_or_g", "fit", "sizes", "K_inf", "deviation_from_2_3", "rmse", "coefficients"]
    rows18 = fit_rows(bench_rows, 18)
    rows20 = fit_rows(bench_rows, 20)
    path18 = outdir / "nnn_tfim_L18_fit_summary.csv"
    path20 = outdir / "nnn_tfim_L20_fit_summary.csv"
    atomic_write_csv(path18, fields, rows18)
    atomic_write_csv(path20, fields, rows20)

    alternative: list[dict[str, Any]] = []
    j2_scan: list[dict[str, Any]] = []
    linear_summary: list[dict[str, Any]] = []
    for j2 in (0.0, 0.05, 0.1, 0.2):
        group = [r for r in rows20 if float(r["lambda_or_g"]) == j2]
        by_fit = {r["fit"]: r for r in group}
        all_linear = by_fit["linear all sizes"]
        large = by_fit["linear L>=12"]
        quadratic = by_fit["quadratic all sizes"]
        constrained = by_fit["constrained 2/3 plus a/L"]
        sizes = all_linear["sizes"]
        alternative.append({
            "lambda_or_g": f"{j2:.12g}",
            "linear_all_Kinf": all_linear["K_inf"], "linear_all_rmse": all_linear["rmse"],
            "linear_L_ge_12_Kinf": large["K_inf"], "linear_L_ge_12_rmse": large["rmse"],
            "quadratic_all_Kinf": quadratic["K_inf"], "quadratic_all_rmse": quadratic["rmse"],
            "constrained_2_3_rmse": constrained["rmse"], "sizes": sizes,
        })
        coefficients = json.loads(all_linear["coefficients"])
        j2_scan.append({
            "lambda_or_g": f"{j2:.12g}", "Kinf_linear": all_linear["K_inf"],
            "slope_linear": f"{coefficients[0]:.16g}", "rmse_linear": all_linear["rmse"],
            "sizes": sizes,
        })
        ccoeff = json.loads(constrained["coefficients"])
        linear_summary.append({
            "J2": f"{j2:.12g}", "Kinf_linear": all_linear["K_inf"],
            "slope_linear": f"{coefficients[0]:.16g}", "rmse_linear": all_linear["rmse"],
            "slope_constrained_Kinf_2_over_3": f"{ccoeff[0]:.16g}",
            "rmse_constrained_Kinf_2_over_3": constrained["rmse"],
            "num_points": len(sizes.split()),
        })
    path_alt = outdir / "nnn_tfim_alternative_fit_summary.csv"
    path_scan = outdir / "nnn_tfim_j2_scan_diagnostics.csv"
    path_linear = outdir / "nnn_tfim_linear_fit_summary.csv"
    atomic_write_csv(path_alt, list(alternative[0]), alternative)
    atomic_write_csv(path_scan, list(j2_scan[0]), j2_scan)
    atomic_write_csv(path_linear, list(linear_summary[0]), linear_summary)
    return [path18, path20, path_alt, path_scan, path_linear]


def comparison_rows(config: dict[str, Any], roots: dict[tuple[float, int], dict[str, Any]],
                    responses: dict[tuple[float, int, int], dict[str, Any]]) -> list[dict[str, Any]]:
    tolerances = config["comparison_tolerances"]
    rows: list[dict[str, Any]] = []
    for reference in config["archived_reference"]["prg"]:
        j2, L = float(reference["lambda_or_g"]), int(reference["L"])
        generated = float(roots[(j2, L)]["h"])
        error = abs(generated - float(reference["h"]))
        tolerance = float(tolerances["h_absolute"])
        rows.append({
            "artifact": "prg", "lambda_or_g": j2, "L": L, "metric": "h",
            "archived": f"{float(reference['h']):.16g}", "regenerated": f"{generated:.16g}",
            "error": f"{error:.6e}", "tolerance": f"{tolerance:.6e}",
            "comparison": "absolute", "status": "PASS" if error <= tolerance else "FAIL",
        })
    for reference in config["archived_reference"]["response"]:
        j2, L = float(reference["lambda_or_g"]), int(reference["L"])
        candidates = [
            value for (candidate_j2, size, _), value in responses.items()
            if candidate_j2 == j2 and size == L
        ]
        generated_row = max(
            candidates,
            key=lambda value: int(value["n_low_energy_eigenpairs"]),
        )
        for metric in ("KF", "P2", "P4_low"):
            archived = float(reference[metric])
            generated = float(generated_row[metric])
            if metric == "KF":
                error = abs(generated - archived)
                tolerance = float(tolerances["KF_absolute"])
                comparison = "absolute"
            else:
                error = abs(generated - archived) / max(abs(archived), 1e-300)
                tolerance = float(tolerances[f"{metric[:2]}_relative"])
                comparison = "relative"
            rows.append({
                "artifact": "response", "lambda_or_g": j2, "L": L, "metric": metric,
                "archived": f"{archived:.16g}", "regenerated": f"{generated:.16g}",
                "error": f"{error:.6e}", "tolerance": f"{tolerance:.6e}",
                "comparison": comparison, "status": "PASS" if error <= tolerance else "FAIL",
            })
    return rows


def main() -> None:
    project_root = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(project_root / "scripts/cleanroom"))
    from common import candidate_run, safe_candidate_path
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=project_root / "repro/config/nnn_tfim_expensive_reproduction.json")
    parser.add_argument("--outdir", type=Path)
    parser.add_argument("--run-root", type=Path)
    parser.add_argument("--paths-only", action="store_true")
    parser.add_argument("--workdir", type=Path)
    parser.add_argument("--mode", choices=["smoke", "publication"], default="publication")
    parser.add_argument("--resume", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument(
        "--require-empty-workdir", action="store_true",
        help="fail unless the work directory is absent or empty before a no-resume run",
    )
    args = parser.parse_args()
    args.config = args.config.resolve()
    run = candidate_run(args.run_root)
    args.outdir = safe_candidate_path(args.outdir or run.data)
    args.workdir = safe_candidate_path(args.workdir or run.root / "work/nnn_tfim_expensive")
    if args.outdir != run.data or not args.workdir.is_relative_to(run.root):
        raise ValueError("NNN output and work directory must belong to the selected candidate run")
    if args.paths_only:
        print(json.dumps({"run_root": str(run.root), "output_data": str(args.outdir), "workdir": str(args.workdir), "scientific_compute": "NONE"}, indent=2))
        return

    if args.require_empty_workdir and args.resume:
        raise ValueError("--require-empty-workdir is only valid with --no-resume")
    workdir_empty_at_start = not args.workdir.exists() or not any(args.workdir.iterdir())
    if args.require_empty_workdir and not workdir_empty_at_start:
        raise RuntimeError(f"required empty work directory is not empty: {args.workdir}")

    started_wall = time.perf_counter()
    config = json.loads(args.config.read_text())
    if config.get("schema_version") != "nnn-tfim-expensive-reproduction/1.0.0":
        raise ValueError("unsupported expensive-reproduction config schema")
    engine_hash = stable_hash({
        "producer": sha256_file(Path(__file__)),
        "engine": sha256_file(Path(engine.__file__)),
    })
    config_hash = sha256_file(args.config)
    environment = solver_environment()
    environment_hash = stable_hash(environment)
    if args.resume:
        validate_resume_checkpoint_store(
            args.workdir, engine_hash, config_hash, environment_hash,
        )
    args.outdir.mkdir(parents=True, exist_ok=True)
    args.workdir.mkdir(parents=True, exist_ok=True)
    event_kind = "resume" if args.resume else "fresh"
    event_path = args.workdir / f"run_{time.time_ns()}_{event_kind}_events.jsonl"
    events = EventLog(event_path)
    checkpoints = Checkpoints(
        args.workdir / "checkpoints", engine_hash, config_hash, environment_hash, args.resume, events,
    )
    events.emit(
        "run-start", mode=args.mode, resume=args.resume, engine_sha256=engine_hash,
        config_sha256=config_hash, solver_environment_sha256=environment_hash,
        workdir_empty_at_start=workdir_empty_at_start,
    )

    if args.mode == "smoke":
        j2_values = [0.2]
        sizes = [6, 8]
    else:
        j2_values = [float(value) for value in config["prg"]["j2_values"]]
        sizes = [int(value) for value in config["prg"]["sizes"]]

    roots: dict[tuple[float, int], dict[str, Any]] = {}
    for j2 in j2_values:
        bracket = tuple(float(value) for value in config["prg"]["brackets"][f"{j2:g}"])
        for L in sizes:
            task = {"kind": "parity-prg", "lambda_or_g": j2, "L": L, "bracket": bracket}
            key = f"prg_j2_{key_float(j2)}_L{L}"
            roots[(j2, L)] = checkpoints.run(
                key, task,
                lambda L=L, j2=j2, bracket=bracket: root_task(L, j2, bracket, config),
            )

    if args.mode == "smoke":
        smoke = {
            "schema_version": SCHEMA_VERSION,
            "mode": "smoke",
            "roots": [roots[key] for key in sorted(roots)],
            "engine_sha256": engine_hash,
            "config_sha256": config_hash,
            "solver_environment": environment,
            "solver_environment_sha256": environment_hash,
            "elapsed_seconds": time.perf_counter() - started_wall,
        }
        atomic_write_json(args.workdir / "smoke_result.json", smoke)
        events.emit(
            "run-complete", mode="smoke", elapsed_seconds=time.perf_counter() - started_wall,
            computed_tasks=checkpoints.computed_count, resumed_tasks=checkpoints.resumed_count,
        )
        validate_event_ledger(
            event_path, checkpoints.computed_count, checkpoints.resumed_count, require_complete=True,
        )
        return

    root_rows: list[dict[str, Any]] = []
    diagnostic_rows: list[dict[str, Any]] = []
    for j2 in j2_values:
        for L in sizes:
            value = roots[(j2, L)]
            root_rows.append({"lambda_or_g": f"{j2:.12g}", "L": L, "h": f"{value['h']:.12g}", "source": "parity-sector-PRG-produced"})
            small, large = value["small"], value["large"]
            diagnostic_rows.append({
                "lambda_or_g": f"{j2:.12g}", "L": L, "h": f"{value['h']:.16g}",
                "gap_L_minus_2": f"{small['gap']:.16g}", "gap_L": f"{large['gap']:.16g}",
                "scaled_gap_residual": f"{value['prg_residual']:.6e}",
                "energy_even_L": f"{large['energy_even']:.16g}", "energy_odd_L": f"{large['energy_odd']:.16g}",
                "residual_even_L": f"{large['residual_even']:.6e}", "residual_odd_L": f"{large['residual_odd']:.6e}",
                "dim_even_L": int(large["dim_even"]), "dim_odd_L": int(large["dim_odd"]),
                "bracket_left": f"{value['bracket_left']:.12g}", "bracket_right": f"{value['bracket_right']:.12g}",
                "f_left": f"{value['f_left']:.6e}", "f_right": f"{value['f_right']:.6e}",
                "evaluation_count": int(value["evaluation_count"]),
                "seconds": f"{float(value['_task_seconds']):.6f}",
            })
    prg_path = args.outdir / "nnn_tfim_prg_fields_L20.csv"
    diag_path = args.outdir / "nnn_tfim_prg_solver_diagnostics.csv"
    atomic_write_csv(prg_path, ["lambda_or_g", "L", "h", "source"], root_rows)
    atomic_write_csv(diag_path, list(diagnostic_rows[0]), diagnostic_rows)

    # L=18 compatibility table is an explicit subset of the same producer run.
    atomic_write_csv(
        args.outdir / "nnn_tfim_prg_fields_L18.csv",
        ["lambda_or_g", "L", "h", "source"],
        [row for row in root_rows if int(row["L"]) <= 18],
    )

    confirmation: list[dict[str, Any]] = []
    for j2 in j2_values:
        lower = np.array([14.0, 16.0, 18.0])
        h_lower = np.array([roots[(j2, int(L))]["h"] for L in lower])
        prediction = float(np.polyval(np.polyfit(lower ** -3, h_lower, 1), 20.0 ** -3))
        confirmed = float(roots[(j2, 20)]["h"])
        confirmation.append({
            "lambda_or_g": f"{j2:.12g}", "L": 20,
            "h_extrapolated_previous": f"{prediction:.12g}", "h_prg_confirmed": f"{confirmed:.12g}",
            "delta_h": f"{confirmed - prediction:.6e}",
            "confirmation_sector": "k=0 even/odd spin-flip parity gap",
            "note": "L20 PRG crossing regenerated from Hamiltonian parameters",
        })
    confirmation_path = args.outdir / "nnn_tfim_L20_prg_confirmation.csv"
    atomic_write_csv(confirmation_path, list(confirmation[0]), confirmation)

    responses: dict[tuple[float, int, int], dict[str, Any]] = {}
    response_cache: dict[tuple[float, int, int, float, str], dict[str, Any]] = {}
    response_sizes = [int(value) for value in config["response"]["sizes"]]

    def get_response(
        j2: float, L: int, n_low_energy_eigenpairs: int,
        h: float | None = None, suffix: str = "",
    ) -> dict[str, Any]:
        field = float(roots[(j2, L)]["h"] if h is None else h)
        cache_key = (j2, L, n_low_energy_eigenpairs, field, suffix)
        if cache_key in response_cache:
            return response_cache[cache_key]
        task = {
            "kind": "response", "lambda_or_g": j2, "L": L, "h": field,
            "n_low_energy_eigenpairs": n_low_energy_eigenpairs, "suffix": suffix,
        }
        key = f"response_j2_{key_float(j2)}_L{L}_neig{n_low_energy_eigenpairs}{suffix}"
        value = checkpoints.run(
            key, task,
            lambda: response_task(L, j2, field, n_low_energy_eigenpairs, config),
        )
        response_cache[cache_key] = value
        if suffix == "":
            responses[(j2, L, n_low_energy_eigenpairs)] = value
        return value

    primary: dict[tuple[float, int], dict[str, Any]] = {}
    for j2 in j2_values:
        for L in response_sizes:
            if L == 20:
                n_low_energy_eigenpairs = int(
                    config["response"]["n_low_energy_eigenpairs_L20"][f"{j2:g}"]
                )
            else:
                n_low_energy_eigenpairs = int(
                    config["response"]["n_low_energy_eigenpairs_default"]
                )
            primary[(j2, L)] = get_response(j2, L, n_low_energy_eigenpairs)

    convergence_16_18: list[dict[str, Any]] = []
    for j2 in j2_values:
        for L in (16, 18):
            for n_low_energy_eigenpairs in [int(value) for value in config["convergence_scans"]["L16_L18"]]:
                value = get_response(j2, L, n_low_energy_eigenpairs)
                convergence_16_18.append({key: value[key] for key in (
                    "lambda_or_g", "L", "h", "sector_dim", "n_low_energy_eigenpairs", "KF", "KF_half", "P2",
                    "P4_low", "n_levels", "solve_res",
                )} | {"seconds": f"{float(value['_task_seconds']):.6f}"})
    conv18_path = args.outdir / "nnn_tfim_L16_L18_retained_eigenpair_convergence.csv"
    atomic_write_csv(conv18_path, list(convergence_16_18[0]), convergence_16_18)

    convergence_20: list[dict[str, Any]] = []
    for j2 in j2_values:
        for n_low_energy_eigenpairs in [int(value) for value in config["convergence_scans"]["L20"][f"{j2:g}"]]:
            value = get_response(j2, 20, n_low_energy_eigenpairs)
            convergence_20.append({
                "lambda_or_g": value["lambda_or_g"], "L": 20, "h": value["h"],
                "n_low_energy_eigenpairs": n_low_energy_eigenpairs,
                "KF": value["KF"], "P2": value["P2"], "P4_low": value["P4_low"],
                "solve_res": value["solve_res"], "gap": value["gap"], "n_levels": value["n_levels"],
                "note": "producer retained-eigenpair convergence at parity PRG field",
            })
    conv20_path = args.outdir / "nnn_tfim_L20_retained_eigenpair_convergence.csv"
    atomic_write_csv(conv20_path, list(convergence_20[0]), convergence_20)

    sensitivity_config = config["field_sensitivity"]
    j2_sensitivity = float(sensitivity_config["j2"])
    L_s = int(sensitivity_config["L"])
    h0 = float(roots[(j2_sensitivity, L_s)]["h"])
    sensitivity: list[dict[str, Any]] = []
    for shift in [float(value) for value in sensitivity_config["shifts"]]:
        value = get_response(j2_sensitivity, L_s, int(sensitivity_config["n_low_energy_eigenpairs"]), h=h0 + shift,
                             suffix=f"_dh_{key_float(shift)}")
        sensitivity.append({
            "lambda_or_g": j2_sensitivity, "L": L_s, "h": f"{h0 + shift:.12g}", "delta_h": f"{shift:+.1e}",
            "n_low_energy_eigenpairs": int(sensitivity_config["n_low_energy_eigenpairs"]),
            "KF": value["KF"], "P2": value["P2"],
            "P4_low": value["P4_low"], "solve_res": value["solve_res"],
            "note": "producer field-sensitivity check around parity PRG field",
        })
    sensitivity_path = args.outdir / "nnn_tfim_L20_h_sensitivity.csv"
    atomic_write_csv(sensitivity_path, list(sensitivity[0]), sensitivity)

    old_benchmark = read_csv(args.outdir / "interacting_benchmarks.csv")
    potts_rows = [row for row in old_benchmark if row.get("model") == "Potts"]
    nnn_rows = [exact_tfim_row(L) for L in response_sizes]
    nnn_rows.extend(benchmark_row(primary[(j2, L)]) for j2 in j2_values for L in response_sizes)
    benchmark_rows = potts_rows + nnn_rows
    benchmark_path = args.outdir / "interacting_benchmarks.csv"
    atomic_write_csv(benchmark_path, BENCH_FIELDS, benchmark_rows)
    atomic_write_csv(
        args.outdir / "interacting_benchmarks_nnn_L18_sector.csv", BENCH_FIELDS,
        [row for row in nnn_rows if int(row["L"]) <= 18],
    )
    atomic_write_csv(args.outdir / "interacting_benchmarks_nnn_L20_sector.csv", BENCH_FIELDS, nnn_rows)

    old_weights = read_csv(args.outdir / "interacting_weight_distributions.csv")
    potts_weights = [row for row in old_weights if row.get("model") == "Potts"]
    weights_l12 = [row for j2 in j2_values for row in weight_rows(primary[(j2, 12)], 80)]
    atomic_write_csv(args.outdir / "interacting_weight_distributions.csv", WEIGHT_FIELDS, potts_weights + weights_l12)
    weights_l18 = [row for j2 in j2_values for row in weight_rows(primary[(j2, 18)], int(config["response"]["maximum_weight_ranks"]))]
    weights_l20 = [row for j2 in j2_values for row in weight_rows(primary[(j2, 20)], int(config["response"]["maximum_weight_ranks"]))]
    atomic_write_csv(args.outdir / "interacting_weights_nnn_L18_sector.csv", WEIGHT_FIELDS, weights_l18)
    atomic_write_csv(args.outdir / "interacting_weights_nnn_L20_sector.csv", WEIGHT_FIELDS, weights_l20)

    fit_paths = write_fit_outputs(args.outdir, benchmark_rows)
    comparisons = comparison_rows(config, roots, responses)
    comparison_path = args.outdir / "nnn_tfim_archived_vs_regenerated.csv"
    atomic_write_csv(comparison_path, list(comparisons[0]), comparisons)
    failures = [row for row in comparisons if row["status"] != "PASS"]
    if failures:
        raise RuntimeError(f"{len(failures)} archived-versus-regenerated comparisons exceed tolerance")
    validate_event_ledger(
        event_path, checkpoints.computed_count, checkpoints.resumed_count, require_complete=False,
    )

    produced = [
        prg_path, args.outdir / "nnn_tfim_prg_fields_L18.csv", diag_path, confirmation_path,
        conv18_path, conv20_path, sensitivity_path, benchmark_path,
        args.outdir / "interacting_benchmarks_nnn_L18_sector.csv",
        args.outdir / "interacting_benchmarks_nnn_L20_sector.csv",
        args.outdir / "interacting_weight_distributions.csv",
        args.outdir / "interacting_weights_nnn_L18_sector.csv",
        args.outdir / "interacting_weights_nnn_L20_sector.csv",
        *fit_paths, comparison_path,
    ]
    elapsed = time.perf_counter() - started_wall
    checkpoint_files = sorted((args.workdir / "checkpoints").glob("*.json"))
    expected_keys = publication_checkpoint_keys(config)
    actual_keys = {path.stem for path in checkpoint_files}
    if actual_keys != expected_keys:
        raise RuntimeError(
            "publication checkpoint set differs from the preregistered 69-task set: "
            f"missing={sorted(expected_keys - actual_keys)}, "
            f"extra={sorted(actual_keys - expected_keys)}"
        )
    if (
        not args.resume
        and args.require_empty_workdir
        and (checkpoints.computed_count != len(expected_keys) or checkpoints.resumed_count != 0)
    ):
        raise RuntimeError(
            "fresh publication execution did not consume exactly one authorization "
            f"per unique task: expected={len(expected_keys)}, "
            f"computed={checkpoints.computed_count}, resumed={checkpoints.resumed_count}"
        )
    checkpoint_manifest = {
        "schema_version": "nnn-tfim-checkpoint-manifest/1.1.0",
        "engine_sha256": engine_hash,
        "config_sha256": config_hash,
        "solver_environment_sha256": environment_hash,
        "checkpoint_count": len(checkpoint_files),
        "preregistered_unique_task_count": len(expected_keys),
        "checkpoints": [{"path": path.name, "sha256": sha256_file(path)} for path in checkpoint_files],
    }
    checkpoint_manifest_path = args.workdir / "checkpoint_manifest.json"
    atomic_write_json(checkpoint_manifest_path, checkpoint_manifest)

    metadata_path = args.outdir / "nnn_tfim_expensive_run_metadata.json"
    prior_fresh_reference: dict[str, Any] | None = None
    if metadata_path.exists():
        try:
            prior_metadata = json.loads(metadata_path.read_text())
            if (
                prior_metadata.get("engine_sha256") == engine_hash
                and prior_metadata.get("config_sha256") == config_hash
                and prior_metadata.get("solver_environment_sha256") == environment_hash
            ):
                prior_fresh_reference = prior_metadata.get("fresh_run_resource_reference")
        except (OSError, json.JSONDecodeError):
            prior_fresh_reference = None
    invocation_resources = {
        "elapsed_seconds": elapsed,
        "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "computed_tasks": checkpoints.computed_count,
        "resumed_tasks": checkpoints.resumed_count,
        "solver_environment": environment,
        "solver_environment_sha256": environment_hash,
    }
    if checkpoints.computed_count > 0:
        fresh_reference = dict(invocation_resources)
    elif prior_fresh_reference is not None:
        fresh_reference = prior_fresh_reference
    else:
        fresh_reference = None
    metadata = {
        "schema_version": SCHEMA_VERSION,
        "mode": "publication",
        "command": " ".join([
            "python3 scripts/simulation/reproduce_nnn_tfim_expensive.py",
            f"--mode {args.mode}",
            "--resume" if args.resume else "--no-resume",
            *( ["--require-empty-workdir"] if args.require_empty_workdir else [] ),
            f"--workdir {args.workdir.relative_to(project_root)}",
            f"--outdir {args.outdir.relative_to(project_root)}",
        ]),
        "config_path": str(args.config.relative_to(project_root)),
        "config_sha256": config_hash,
        "engine_sha256": engine_hash,
        "python": environment["python"],
        "numpy": environment["numpy"],
        "scipy": environment["scipy"],
        "platform": environment["platform"],
        "machine": environment["machine"],
        "logical_cpus": os.cpu_count(),
        "thread_environment": environment["thread_environment"],
        "solver_environment_sha256": environment_hash,
        "computation_environment": (
            environment if checkpoints.computed_count > 0
            else (fresh_reference or {}).get("solver_environment")
        ),
        "validation_environment": environment,
        "lineage": {
            "resume_requested": args.resume,
            "require_empty_workdir": args.require_empty_workdir,
            "workdir_empty_at_start": workdir_empty_at_start,
            "computed_tasks": checkpoints.computed_count,
            "resumed_tasks": checkpoints.resumed_count,
            "mode": (
                "fresh-compute" if not args.resume and checkpoints.resumed_count == 0
                else "checkpoint-resume" if checkpoints.computed_count == 0
                else "mixed"
            ),
        },
        "invocation_resources": invocation_resources,
        "fresh_run_resource_reference": fresh_reference,
        "event_log": str(event_path.relative_to(project_root)),
        "checkpoint_manifest": str(checkpoint_manifest_path.relative_to(project_root)),
        "comparison_status": "PASS",
        "outputs": [{"path": str(path.relative_to(project_root)), "sha256": sha256_file(path)} for path in produced],
    }
    atomic_write_json(metadata_path, metadata)
    checksum_path = args.outdir / "nnn_tfim_expensive_output_sha256sums.txt"
    checksum_lines = [f"{sha256_file(path)}  {path.relative_to(project_root)}" for path in [*produced, metadata_path]]
    atomic_write_text(checksum_path, "\n".join(checksum_lines) + "\n")
    events.emit(
        "run-complete", mode="publication", elapsed_seconds=elapsed,
        output_count=len(produced) + 2,
        peak_rss_kib=invocation_resources["peak_rss_kib"],
        computed_tasks=checkpoints.computed_count,
        resumed_tasks=checkpoints.resumed_count,
    )
    validate_event_ledger(
        event_path, checkpoints.computed_count, checkpoints.resumed_count, require_complete=True,
    )


if __name__ == "__main__":
    main()
