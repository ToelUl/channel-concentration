#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
import platform
import resource
import sys
import time
from pathlib import Path
from typing import Any

PROJECT = Path(__file__).resolve().parents[2]
BUILD = PROJECT / "build"
RECEIPTS = BUILD / "receipts"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_hash(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return hashlib.sha256(raw).hexdigest()


def write_json(path: Path, value: Any) -> None:
    if path.resolve().is_relative_to(PROJECT.resolve()):
        safe_candidate_path(path)
    atomic_bytes(path, (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode("utf-8"))


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def environment_receipt(started: float) -> dict[str, Any]:
    usage = resource.getrusage(resource.RUSAGE_SELF)
    return {
        "python": sys.version,
        "platform": platform.platform(),
        "numpy_threads": {
            key: os.environ.get(key)
            for key in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS")
        },
        "wall_seconds": time.monotonic() - started,
        "max_rss_kib": int(usage.ru_maxrss),
        "cpu_visible": os.cpu_count(),
        "network_authorized": False,
        "gpu_authorized": False,
    }


# Project-coherence support: metadata and filesystem operations only.
# Numerical kernels and independent verification oracles do not use this layer.
import csv
import dataclasses
import re
import shutil
import tempfile
import tomllib

GENERATED_METADATA = frozenset({
    "SHA256SUMS.txt", "metadata/PACKAGE_MANIFEST.json",
    "metadata/manifests/source_manifest.json", "metadata/manifests/lineage.csv",
})
POST_EXECUTION_METADATA = frozenset({
    "provenance/artifact-graph.json",
    "provenance/claim-data-map.json",
    "provenance/provenance.lock.json",
    "repro/qualification/closure_summary.json",
})
RUNTIME_QUALIFICATION_KEYS = frozenset({
    "successor_environment",
    "primary",
    "replicate",
    "cross_role_equivalence",
})


def project_config(project: Path = PROJECT) -> dict[str, Any]:
    with (project / "project.toml").open("rb") as handle:
        config = tomllib.load(handle)
    if config.get("packaging", {}).get("schema") != "channel-concentration-packaging-policy/1.0":
        raise ValueError("unsupported current packaging policy schema")
    return config


def reject_symlinks(path: Path) -> None:
    """Reject existing symlink components, including a symlinked final file."""
    path = path.absolute()
    for part in (path, *path.parents):
        if part.is_symlink():
            raise ValueError(f"symlink path is not permitted: {part}")


def safe_candidate_path(path: Path, project: Path = PROJECT) -> Path:
    """All live candidate writes are confined to this project's build directory."""
    path = Path(path).expanduser()
    if ".." in path.parts:
        raise ValueError("parent traversal is not permitted for candidate output")
    path = path if path.is_absolute() else project / path
    reject_symlinks(path)
    resolved = path.resolve()
    build = (project / "build").resolve()
    if resolved == build or not resolved.is_relative_to(build):
        raise ValueError(f"candidate output must be below {build}: {path}")
    if resolved.is_file() and resolved.stat().st_nlink != 1:
        raise ValueError("refusing to write a hard-linked candidate file")
    return resolved


def atomic_bytes(path: Path, payload: bytes) -> None:
    """Replace one file atomically, using a unique temporary file on its filesystem."""
    reject_symlinks(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def source_inventory(project: Path = PROJECT) -> dict[str, str]:
    """Scientific source identity, excluding output and post-execution status.

    The complete package still hash-binds every excluded closure record.  This
    narrower identity prevents the acceptance receipt from invalidating the
    exact scientific source that it accepts.
    """
    result = {}
    for path in sorted(project.rglob("*")):
        relative = path.relative_to(project)
        if relative.parts[0] in {"build", "dist", "work"} or "__pycache__" in relative.parts:
            continue
        relative_text = relative.as_posix()
        if relative_text in GENERATED_METADATA or relative_text in POST_EXECUTION_METADATA:
            continue
        if path.is_symlink():
            raise ValueError(f"source symlink: {relative}")
        if path.is_file():
            if relative_text == "project.toml":
                config = tomllib.loads(path.read_text(encoding="utf-8"))
                qualification = dict(config.get("qualification", {}))
                missing = RUNTIME_QUALIFICATION_KEYS - set(qualification)
                if missing:
                    raise ValueError(f"project.toml lacks runtime qualification keys: {sorted(missing)}")
                for key in RUNTIME_QUALIFICATION_KEYS:
                    qualification[key] = "<POST_EXECUTION_STATUS>"
                config["qualification"] = qualification
                result[relative_text] = canonical_hash(config)
            else:
                result[relative_text] = sha256(path)
    return result


@dataclasses.dataclass(frozen=True)
class CandidateRun:
    root: Path
    data: Path
    receipts: Path
    figures: Path
    documents: Path
    arxiv: Path


def candidate_run(run_root: Path | None = None, *, project: Path = PROJECT) -> CandidateRun:
    """Create a source-bound data COPY, never a hardlink or a fallback to frozen data."""
    value = run_root or os.environ.get("CC_RUN_ROOT") or project / "build/runs/default"
    root = safe_candidate_path(Path(value), project)
    runs = (project / "build/runs").resolve()
    if not root.is_relative_to(runs) or root.parent != runs:
        raise ValueError("run root must be one direct child of build/runs")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", root.name):
        raise ValueError("invalid run identifier")
    source_hash = canonical_hash(source_inventory(project))
    config = project_config(project)
    context_path = root / "context.json"
    if root.exists():
        reject_symlinks(context_path)
        if not context_path.is_file():
            raise ValueError("existing run has no context; use a fresh run identifier")
        record = read_json(context_path)
        if record.get("schema") != "cc-candidate-run/1.0" or record.get("source_tree_sha256") != source_hash:
            raise ValueError("run context is stale or unsupported; use a new run identifier")
        if record.get("project_root") != str(project.resolve()) or record.get("run_root") != str(root):
            raise ValueError("run context location mismatch")
        for name in ("data/reproducibility", "receipts", "figures", "documents", "arxiv"):
            path = safe_candidate_path(root / name, project)
            if not path.is_dir():
                raise ValueError(f"incomplete existing run: {name}")
            for entry in path.rglob("*"):
                reject_symlinks(entry)
                if entry.is_file() and entry.stat().st_nlink != 1:
                    raise ValueError("candidate contains hard-linked files")
    else:
        frozen = project / "data/reproducibility"
        for source_root in (frozen,):
            reject_symlinks(source_root)
            for entry in source_root.rglob("*"):
                reject_symlinks(entry)
        root.parent.mkdir(parents=True, exist_ok=True)
        stage = Path(tempfile.mkdtemp(prefix=".run-init-", dir=root.parent))
        try:
            shutil.copytree(frozen, stage / "data/reproducibility", copy_function=shutil.copyfile)
            (stage / "figures").mkdir()  # Public profile: no frozen artwork dependency.
            for name in ("receipts", "documents", "arxiv"):
                (stage / name).mkdir()
            frozen_hashes = {p.relative_to(frozen).as_posix(): sha256(p) for p in sorted(frozen.rglob("*")) if p.is_file()}
            record = {
                "schema": "cc-candidate-run/1.0", "project_root": str(project.resolve()),
                "run_root": str(root), "source_tree_sha256": source_hash,
                "input_archive": config["lineage"]["immediate_parent"],
                "frozen_data_initial_sha256": canonical_hash(frozen_hashes),
                "frozen_data_initial_files": frozen_hashes,
                "initial_figures_source": "none; public computation profile excludes frozen artwork",
                "candidate_data": str(root / "data/reproducibility"),
                "profile": "cc-repro-public-computation", "python_observed": sys.version,
                "pinned_environment_qualification": config["authority"]["pinned_environment_qualification"],
                "canonical_write_requested": False, "canonical_write_authorized": False,
                "t3_ledger_touched": False,
                "new_scientific_compute": config["authority"]["new_scientific_compute"],
                "stage_roots": {n: str(root / p) for n,p in {
                    "data": "data/reproducibility", "receipts": "receipts", "figures": "figures",
                    "documents": "documents", "arxiv": "arxiv/source"}.items()},
            }
            atomic_bytes(stage / "context.json", (json.dumps(record, indent=2, sort_keys=True, allow_nan=False)+"\n").encode())
            if root.exists():
                raise FileExistsError("run identifier was concurrently initialized")
            stage.rename(root)
        finally:
            if stage.exists():
                shutil.rmtree(stage)
    return CandidateRun(root, root / "data/reproducibility", root / "receipts", root / "figures", root / "documents", root / "arxiv/source")


def historical_evidence_path(value: str, project: Path = PROJECT) -> Path:
    """Relocation of one known historical prefix; not proof of source equivalence."""
    rel = Path(value)
    prefix = "reproducibility_evidence/nnn_tfim_publication_run/"
    if rel.is_absolute() or ".." in rel.parts or "\\" in value or not value.startswith(prefix):
        raise ValueError(f"unrecognized historical evidence path: {value}")
    tail = value[len(prefix):]
    if not tail or Path(tail).is_absolute():
        raise ValueError("empty historical evidence suffix")
    path = project / "repro/evidence/nnn_tfim_publication_run" / tail
    reject_symlinks(path)
    if not path.is_file():
        raise FileNotFoundError(path)
    return path


def read_dataset(key: str, data_dir: Path, *, project: Path = PROJECT) -> list[dict[str, str]]:
    """Read a declared CSV and translate only the exact approved legacy schema.

    When both names exist, a known stale frozen clone is explicitly superseded
    by current output. Any other conflicting pair is rejected, not guessed.
    """
    matches = [d for d in project_config(project).get("datasets", []) if d["key"] == key]
    if len(matches) != 1:
        raise ValueError(f"dataset key is not unique/declared: {key}")
    spec = matches[0]
    primary = data_dir / spec["candidate_path"]
    legacy = data_dir / spec["frozen_path"]
    for path in {primary, legacy}:
        reject_symlinks(path)
    if primary != legacy and primary.is_file() and legacy.is_file():
        if sha256(legacy) != spec["frozen_sha256"]:
            raise ValueError("ambiguous current and modified legacy dataset coexist")
    selected = primary if primary.is_file() else legacy
    if selected == legacy and legacy.name not in spec.get("legacy_filenames", []) and primary != legacy:
        raise ValueError("undeclared legacy filename")
    with selected.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        header = reader.fieldnames
        is_legacy = (selected.name in spec.get("legacy_filenames", [])
                     and header == spec["legacy_header"] and spec["legacy_header"] != spec["header"])
        if selected == legacy and primary != legacy and header != spec["legacy_header"]:
            raise ValueError("legacy filename requires its complete declared legacy schema")
        expected = spec["legacy_header"] if is_legacy else spec["header"]
        if header != expected:
            raise ValueError(f"dataset header mismatch ({key}): {header}")
        rows = list(reader)
    if any(None in row or any(value is None for value in row.values()) for row in rows):
        raise ValueError(f"ragged dataset rows: {key}")
    aliases = spec.get("legacy_columns", {}) if is_legacy else {}
    rows = [{aliases.get(name, name): value for name, value in row.items()} for row in rows]
    for row in rows:
        if "n_low_energy_eigenpairs" in row:
            number = int(row["n_low_energy_eigenpairs"])
            if number <= 0:
                raise ValueError("retained-eigenpair count must be a positive integer")
        if "L" in row and int(row["L"]) <= 0:
            raise ValueError("size must be a positive integer")
    return rows


def fresh_output_directory(path: Path, *, project: Path = PROJECT) -> Path:
    """Reserve a new candidate directory before computation; never reuse data paths."""
    target = safe_candidate_path(path, project=project)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.mkdir(exist_ok=False)
    return target
