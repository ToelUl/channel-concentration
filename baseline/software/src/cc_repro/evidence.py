"""Strict, durable evidence bindings shared by A0 adapters; no numerical kernels."""
from hashlib import sha256
import json
from pathlib import Path
from .campaign import atomic_text, environment
from .resources import digest, reject_links


def canonical(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def read(path):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result
    def constant(value):
        raise ValueError(f"nonfinite JSON constant: {value}")
    return json.loads(reject_links(path).read_text(), object_pairs_hook=pairs, parse_constant=constant)


def write(path, value):
    atomic_text(reject_links(path), json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")


def record(path, root):
    path, root = reject_links(path), reject_links(root)
    relative = path.relative_to(root).as_posix()
    return {"path": relative, "bytes": path.stat().st_size, "sha256": digest(path)}


def verify_file(root, entry):
    rel = Path(entry["path"])
    if rel.is_absolute() or ".." in rel.parts or "\\" in entry["path"]:
        raise ValueError("unsafe artifact binding")
    path = reject_links(root / rel)
    if path.stat().st_size != entry["bytes"] or digest(path) != entry["sha256"]:
        raise ValueError(f"artifact identity mismatch: {entry['path']}")
    return path


def context(project, config):
    return {"source_binding_sha256": digest(project.parent / "binding.json"),
            "configuration": config, "configuration_sha256": canonical(config),
            "environment": environment()}


def commit(root, name, payload):
    """Payload first, external seal last. An orphan payload never counts as committed."""
    path = root / (name + ".json")
    seal = root / (name + ".seal.json")
    if path.exists() or seal.exists():
        raise FileExistsError(f"refusing overwrite of evidence {name}")
    write(path, payload)
    write(seal, {"schema": "cc-repro-artifact-seal/1", "artifact": record(path, root)})
    return record(seal, root)


def load_commit(root, seal_record):
    seal = read(verify_file(root, seal_record))
    if seal.get("schema") != "cc-repro-artifact-seal/1":
        raise ValueError("unknown artifact seal")
    return read(verify_file(root, seal["artifact"]))


def require_role(payload, role):
    if payload.get("source_role") != role:
        raise ValueError(f"requires {role} evidence; reference/fixture cannot be promoted")


def verify_keys(actual, expected):
    if len(actual) != len(set(actual)) or set(actual) != set(expected):
        raise ValueError("exact task key set mismatch")
