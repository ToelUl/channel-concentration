"""Verify readable public resources and copy them into a writable workspace."""
from hashlib import sha256
from importlib.resources import files
from pathlib import Path, PurePosixPath
import io
import json
import shutil
import tempfile
import zipfile


def digest(path):
    with Path(path).open("rb") as stream:
        h = sha256()
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def reject_links(path):
    path = Path(path).absolute()
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError(f"symlink path is not supported: {path}")
    return path


def manifest():
    return json.loads(files("cc_repro").joinpath("_data/manifest.json").read_text())


def _inventory(root):
    """Enumerate Traversable files, rejecting local symlinks before traversal."""
    found = set()
    def visit(node, prefix):
        for child in node.iterdir():
            if isinstance(child, Path):
                reject_links(child)
            name = prefix + child.name
            if child.is_dir():
                visit(child, name + "/")
            elif child.is_file():
                found.add(name)
            else:
                raise ValueError(f"unsupported resource: {name}")
    visit(root, "")
    return found


def _member(name):
    path = PurePosixPath(name)
    if not name or path.is_absolute() or ".." in path.parts or "\\" in name or path.as_posix() != name:
        raise ValueError(f"unsafe resource member: {name}")
    return path


def packaged_resources(expected):
    """All distributed resource bytes must match the explicit public profile."""
    if expected.get("schema") != "cc-public-resources/1.0":
        raise ValueError("unsupported public resource manifest")
    result = {}
    for group in ("original", "historical"):
        root = files("cc_repro").joinpath("_resources", group)
        records = expected[group]
        names = [r["path"] for r in records]
        if len(names) != len(set(names)) or _inventory(root) != set(names):
            raise ValueError(f"packaged {group} resource inventory mismatch")
        blobs = {}
        for record in records:
            name = record["path"]
            rel = _member(name)
            blob = root.joinpath(*rel.parts).read_bytes()
            if len(blob) != record["bytes"] or sha256(blob).hexdigest() != record["sha256"]:
                raise ValueError(f"packaged {group} resource hash mismatch: {name}")
            blobs[name] = blob
        result[group] = blobs
    return result


def evidence_archive(blobs):
    """Deterministic selected-evidence ZIP for the unchanged original CFT reader.

    The wheel contains readable files, not the old full historical archive.
    ZIP_STORED makes the workspace archive identity independent of zlib versions.
    """
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, blob in sorted(blobs.items()):
            _member(name)
            info = zipfile.ZipInfo(name, (2026, 9, 8, 0, 0, 0))
            info.external_attr = 0o100644 << 16
            info.compress_type = zipfile.ZIP_STORED
            archive.writestr(info, blob)
    return buffer.getvalue()


def verify_workspace(workspace):
    workspace = reject_links(workspace)
    expected = manifest()
    packaged_resources(expected)
    if json.loads((workspace / "binding.json").read_text()) != expected:
        raise ValueError("workspace binding does not match this package")
    project = workspace / "project"
    known = {r["path"] for r in expected["original"]}
    for record in expected["original"]:
        path = reject_links(project / record["path"])
        if digest(path) != record["sha256"]:
            raise ValueError(f"original source hash mismatch: {record['path']}")
    for path in project.rglob("*"):
        reject_links(path)
        relative = path.relative_to(project)
        if path.is_file() and relative.parts[0] != "build" and relative.as_posix() not in known:
            raise ValueError(f"unexpected file in original source: {relative}")
    vault = reject_links(workspace / "inputs/historical.zip")
    if digest(vault) != expected["historical_zip_sha256"]:
        raise ValueError("historical selected-evidence hash mismatch")
    reject_links(workspace / "logs")
    return project, vault


def prepare_workspace(workspace):
    """Create from selected resources, or verify an existing version-bound copy."""
    workspace = reject_links(workspace)
    installed = Path(__file__).resolve().parent
    if workspace == installed or installed in workspace.parents:
        raise ValueError("workspace must be outside the installed package")
    if workspace.exists():
        return verify_workspace(workspace)
    expected = manifest()
    payloads = packaged_resources(expected)
    vault = evidence_archive(payloads["historical"])
    if sha256(vault).hexdigest() != expected["historical_zip_sha256"]:
        raise ValueError("selected evidence archive identity mismatch")
    workspace.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix="cc-init-", dir=workspace.parent))
    try:
        for name, blob in payloads["original"].items():
            target = stage / "project" / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(blob)
        (stage / "inputs").mkdir()
        (stage / "inputs/historical.zip").write_bytes(vault)
        (stage / "binding.json").write_text(json.dumps(expected, indent=2) + "\n")
        verify_workspace(stage)
        stage.rename(workspace)
    finally:
        if stage.exists():
            shutil.rmtree(stage)
    return verify_workspace(workspace)
