"""Sequential campaign control around the unchanged original single-point routes."""
from contextlib import contextmanager
import csv
import fcntl
from hashlib import sha256
from importlib.metadata import version
import io
import json
from pathlib import Path
import platform
import tempfile
from types import SimpleNamespace
import os
from . import __version__
from .resources import digest, reject_links


@contextmanager
def locked(workspace, run_id):
    directory = reject_links(workspace / "logs/locks")
    directory.mkdir(parents=True, exist_ok=True)
    path = reject_links(directory / (run_id + ".lock"))
    with path.open("a") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def atomic_text(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix="commit-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if Path(temporary).exists():
            Path(temporary).unlink()


def checkpoint_backup(workspace):
    """Synchronous isolated backup hook supplied only by the local job manager."""
    script = os.environ.get("CC_JOB_CONTROL_SCRIPT")
    job = os.environ.get("CC_JOB_ID")
    if script or job:
        if not script or not job:
            raise ValueError("incomplete local job backup binding")
        import subprocess
        import sys
        subprocess.run([sys.executable, "-B", script, "checkpoint", job], cwd=workspace, check=True)


def environment():
    import numpy as np
    return {"python": platform.python_version(), "platform": platform.platform(),
            "numpy": version("numpy"), "scipy": version("scipy"),
            "blas": np.__config__.CONFIG.get("Build Dependencies", {}).get("blas", {}),
            "blas_threads": 1, "package_version": __version__,
            "adapter_sources": {p.name: digest(p) for p in sorted(Path(__file__).parent.glob("*.py"))}}


def make_plan(args, project):
    model = args.model
    filename = "potts_retained_eigenpairs_cleanroom.json" if model == "potts" else "nnn_tfim_expensive_reproduction.json"
    path = project / "repro/config" / filename
    config = json.loads(path.read_text())
    sizes = args.sizes if args.sizes is not None else ([6, 7] if model == "potts" else [6, 8])
    allowed = config["active_sizes"] if model == "potts" else config["response"]["sizes"]
    if not sizes or len(set(sizes)) != len(sizes) or any(L not in allowed for L in sizes):
        raise ValueError(f"sizes must be unique members of {allowed}")
    if model == "potts" and args.j2 is not None:
        raise ValueError("--j2 applies only to NNN")
    couplings = [None] if model == "potts" else (args.j2 or [0.2])
    if len(set(couplings)) != len(couplings):
        raise ValueError("duplicate J2 values")
    tasks = [{"key": f"{model}-L{L}" + ("" if j is None else f"-j{j:g}"),
              "L": L, "j2": j} for j in sorted(couplings, key=str) for L in sorted(sizes)]
    return {"model": model, "tasks": tasks, "original_config_sha256": digest(path),
            "source_binding_sha256": digest(project.parent / "binding.json"),
            "environment": environment(),
            "scope": "selected point grid; no fit, ladder certificate or complete manuscript closure"}


def result_for(project, record):
    path = reject_links(project / "build/runs" / record["run_id"] / "result.json")
    if digest(path) != record["result_sha256"]:
        raise ValueError("campaign result hash mismatch")
    result = json.loads(path.read_text())
    if result.get("status") != "PASS" or not result.get("acceptance") or not all(v is True for v in result["acceptance"].values()):
        raise ValueError("campaign checkpoint is not accepted")
    return result


def summary_text(project, state):
    fields = ["task", "status", "L", "j2", "K_F", "K_F_lower", "K_F_upper", "P2",
              "P2_lower", "P2_upper", "P4", "P4_low", "h", "result_sha256"]
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=fields)
    writer.writeheader()
    for task in state["plan"]["tasks"]:
        record = state["tasks"][task["key"]]
        row = {"task": task["key"], "L": task["L"], "j2": task["j2"], "status": record["status"]}
        if record["status"] == "PASS":
            d = result_for(project, record)
            if state["plan"]["model"] == "potts":
                m = d["result"]
                row.update(K_F=m["K_F"], K_F_lower=m["K_F_interval"][0], K_F_upper=m["K_F_interval"][1])
                for key in ("P2", "P4"):
                    if key in m:
                        row[key] = m[key]
                if "P2_interval" in m:
                    row.update(P2_lower=m["P2_interval"][0], P2_upper=m["P2_interval"][1])
            else:
                m = d["response"]
                row.update(K_F=m["KF"], P2=m["P2"], P4_low=m["P4_low"], h=m["h"])
            row["result_sha256"] = record["result_sha256"]
        writer.writerow(row)
    return stream.getvalue()


def save(root, project, state):
    # The manifest is authoritative. The CSV is a derived view, rebuilt on resume.
    atomic_text(root / "campaign.json", json.dumps(state, indent=2, allow_nan=False) + "\n")
    atomic_text(root / "summary.csv", summary_text(project, state))


def run(args, project):
    from .cli import execute
    plan = make_plan(args, project)
    root = reject_links(project / "build/runs" / args.run_id)
    if args.resume:
        state = json.loads((root / "campaign.json").read_text())
        if state.get("schema") != "cc-repro-campaign/1" or state.get("plan") != plan:
            raise ValueError("campaign plan, source or environment mismatch")
        if set(state["tasks"]) != {t["key"] for t in plan["tasks"]}:
            raise ValueError("campaign task inventory mismatch")
        for record in state["tasks"].values():
            if record["status"] == "PASS":
                result_for(project, record)
            elif record["status"] != "PENDING":
                raise ValueError("failed or uncommitted task cannot be silently retried; preserve this campaign")
    else:
        root.mkdir(parents=True, exist_ok=False)
        prefix = args.run_id[:30] + "-" + sha256(args.run_id.encode()).hexdigest()[:10]
        state = {"schema": "cc-repro-campaign/1", "plan": plan, "status": "RUNNING",
                 "tasks": {t["key"]: {"status": "PENDING", "run_id": prefix + "-" + t["key"]} for t in plan["tasks"]}}
    computed = 0
    state["status"] = "RUNNING"
    save(root, project, state)
    for task in plan["tasks"]:
        record = state["tasks"][task["key"]]
        if record["status"] == "PASS":
            continue
        record["status"] = "RUNNING"
        save(root, project, state)
        child = SimpleNamespace(route="potts" if args.model == "potts" else "nnn-point",
                                workspace=project.parent, run_id=record["run_id"], L=task["L"], timeout=args.timeout)
        if args.model == "nnn":
            child.j2 = task["j2"]
        try:
            code = execute(child)
            record["returncode"] = code
            if code != 0:
                raise RuntimeError(f"task failed with exit {code}")
            path = project / "build/runs" / record["run_id"] / "result.json"
            record["result_sha256"] = digest(path)
            result_for(project, record)
        except (OSError, ValueError, RuntimeError) as error:
            record.update(status="FAIL", error=str(error))
            state["status"] = "FAIL"
            save(root, project, state)
            print(json.dumps({"status": "FAIL", "campaign": str(root), "error": str(error)}))
            return 2
        record["status"] = "PASS"
        computed += 1
        save(root, project, state)
        checkpoint_backup(project.parent)
        remaining = any(x["status"] != "PASS" for x in state["tasks"].values())
        if args.stop_after is not None and computed >= args.stop_after and remaining:
            state["status"] = "PAUSED"
            save(root, project, state)
            print(json.dumps({"status": "PAUSED", "campaign": str(root), "computed": computed}))
            return 75
    state["status"] = "PASS"
    save(root, project, state)
    print(json.dumps({"status": "PASS", "campaign": str(root), "computed": computed,
                      "reused": len(plan["tasks"]) - computed, "scope": plan["scope"]}))
    return 0
