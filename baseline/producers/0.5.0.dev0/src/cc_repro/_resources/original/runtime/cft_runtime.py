"""Original CFT route and required I/O functions, extracted without body changes.

See provenance/RESOURCE_LINEAGE.json. Only module imports and binding path differ.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat
import subprocess
import sys
import tempfile
from typing import Any
import zipfile

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build"
CONTRACT_PATH = ROOT / "repro/config/cft_input_binding.json"

CFT_DATA_FILES = (
    "interacting_benchmarks.csv",
    "interacting_weight_distributions.csv",
    "nnn_tfim_alternative_fit_summary.csv",
    "potts_alternative_fit_summary.csv",
    "tfim_j2_zero_resolution_match.csv",
    "tfim_sector_contrast.csv",
    "xx_pairing_theorem_checks.csv",
)

def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def reject_links(path: Path) -> None:
    for item in (path.absolute(), *path.absolute().parents):
        if item.is_symlink():
            raise ValueError(f"symlink path is not permitted: {item}")


def atomic_write(path: Path, payload: bytes, *, exclusive: bool = False) -> None:
    reject_links(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if exclusive and path.exists():
        raise FileExistsError(f"refusing to overwrite existing artifact: {path}")
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        if exclusive and path.exists():
            raise FileExistsError(f"refusing to overwrite existing artifact: {path}")
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def write_json(path: Path, value: Any, *, exclusive: bool = False) -> None:
    atomic_write(path, canonical_json_bytes(value), exclusive=exclusive)


def command_environment(*, run_root: Path | None = None) -> dict[str, str]:
    environment = os.environ.copy()
    environment.update({
        "OPENBLAS_NUM_THREADS": "1",
        "OMP_NUM_THREADS": "1",
        "MKL_NUM_THREADS": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONNOUSERSITE": "1",
        "MPLCONFIGDIR": str((run_root or BUILD / "cache") / "cache" / "matplotlib"),
        "SOURCE_DATE_EPOCH": "1785542400",
        "TZ": "UTC",
    })
    if run_root is not None:
        environment["CC_RUN_ROOT"] = str(run_root)
    return environment

def _zip_root(archive: zipfile.ZipFile) -> str:
    roots = {PurePosixPath(info.filename).parts[0] for info in archive.infolist() if info.filename}
    if roots != {"cc215"}:
        raise RuntimeError(f"unexpected evidence-vault archive root: {sorted(roots)}")
    return "cc215"


def _safe_zip_payload(archive: zipfile.ZipFile, member: str) -> bytes:
    path = PurePosixPath(member)
    if path.is_absolute() or ".." in path.parts or "\\" in member:
        raise RuntimeError(f"unsafe evidence-vault member: {member}")
    info = archive.getinfo(member)
    mode = (info.external_attr >> 16) & 0o170000
    if mode == stat.S_IFLNK:
        raise RuntimeError(f"evidence-vault symlink rejected: {member}")
    return archive.read(member)


def _vault_mpmath(archive: zipfile.ZipFile) -> tuple[str, str, list[tuple[str, bytes]]]:
    root = _zip_root(archive)
    prefix = f"{root}/repro/evidence/cft/vendor/"
    members = []
    for info in sorted(archive.infolist(), key=lambda item: item.filename):
        if not info.is_dir() and info.filename.startswith(prefix):
            relative = info.filename[len(prefix):]
            members.append((relative, _safe_zip_payload(archive, info.filename)))
    if not members:
        raise RuntimeError("vendored mpmath tree is absent from the evidence vault")
    digest = hashlib.sha256()
    version = ""
    for name, payload in members:
        digest.update(name.encode("utf-8") + b"\0" + hashlib.sha256(payload).digest())
        if name == "mpmath-1.3.0.dist-info/METADATA":
            for line in payload.decode("utf-8").splitlines():
                if line.startswith("Version: "):
                    version = line.split(":", 1)[1].strip()
    return version, digest.hexdigest(), members


def _cft_route(run_root: Path, vault_zip: Path) -> dict[str, Any]:
    sandbox = run_root / "work/cft/sandbox"
    if sandbox.exists():
        raise FileExistsError("CFT sandbox already exists; retry is forbidden")
    producer_dir = sandbox / "work/kf_cft_research/bundle/calculations"
    data_dir = sandbox / "work/kf_cft_rev1c_baseline/Channel_Concentration_rev1c_reproducible_package/data/reproducibility"
    vendor_dir = sandbox / "vendor"
    producer_dir.mkdir(parents=True)
    data_dir.mkdir(parents=True)
    vendor_dir.mkdir(parents=True)
    with zipfile.ZipFile(vault_zip) as archive:
        root = _zip_root(archive)
        producer_member = f"{root}/repro/evidence/cft/compute_cft_kf.py"
        producer_payload = _safe_zip_payload(archive, producer_member)
        if hashlib.sha256(producer_payload).hexdigest() != read_json(CONTRACT_PATH)["immutable_inputs"]["cft_producer_sha256"]:
            raise RuntimeError("CFT producer identity mismatch")
        (producer_dir / "compute_cft_kf.py").write_bytes(producer_payload)
        input_hashes = {}
        for name in CFT_DATA_FILES:
            payload = _safe_zip_payload(archive, f"{root}/data/reproducibility/{name}")
            (data_dir / name).write_bytes(payload)
            input_hashes[name] = hashlib.sha256(payload).hexdigest()
        mpmath_version, mpmath_tree_hash, members = _vault_mpmath(archive)
        for relative, payload in members:
            destination = vendor_dir / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(payload)
    environment = command_environment(run_root=run_root)
    environment.update({
        "PYTHONPATH": str(vendor_dir),
        "PYTHONNOUSERSITE": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "CUDA_VISIBLE_DEVICES": "",
        "NVIDIA_VISIBLE_DEVICES": "void",
    })
    completed = subprocess.run(
        [sys.executable, str(producer_dir / "compute_cft_kf.py")],
        cwd=sandbox,
        env=environment,
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"CFT producer failed: {completed.stderr}")
    current = json.loads(completed.stdout)
    frozen_path = ROOT / "repro/evidence/cft/cft_kf_results.json"
    frozen = read_json(frozen_path)
    d1 = current["delta_results"]["1"]
    dp = current["delta_results"]["4/5"]
    target = frozen["delta_4_over_5"]["K"]
    checks = {
        "delta_1_routes": bool(d1["routes_agree_1e-20"]),
        "delta_4_over_5_routes": bool(dp["routes_agree_1e-20"]),
        "ising_two_thirds_oracle": bool(current["controls"]["ising_oracle"]["passed_1e-30"]),
        "potts_route_a_frozen": dp["beta_integral_hypergeometric_closed_form"]["k"] == target,
        "potts_route_b_frozen": dp["coefficient_recurrence_plus_asymptotic_tail"]["k"] == target,
        "vendored_mpmath": mpmath_version == "1.3.0",
    }
    current_path = run_root / "data/reproducibility/cft_kf_current.json"
    write_json(current_path, current, exclusive=True)
    return {
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "producer_sha256": hashlib.sha256(producer_payload).hexdigest(),
        "frozen_result_sha256": sha256_file(frozen_path),
        "current_result_sha256": sha256_file(current_path),
        "input_sha256s": input_hashes,
        "mpmath_tree_sha256": mpmath_tree_hash,
        "current_result": str(current_path),
    }
