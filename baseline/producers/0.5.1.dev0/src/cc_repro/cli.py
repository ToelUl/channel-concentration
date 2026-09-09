"""Small command surface; all numerical work runs in original-source subprocesses."""
import argparse
import json
import math
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time
import uuid
from . import __version__
from .resources import prepare_workspace, reject_links, digest


def run_id(value):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", value):
        raise argparse.ArgumentTypeError("run-id must be 1–80 letters, digits, dots, underscores or hyphens; start with a letter/digit")
    return value


def positive_seconds(value):
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError("timeout must be positive and finite")
    return number


def positive_integer(value):
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return number


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="route", required=True)
    for route, help_text in {
        "postprocess": "Run original analysis with explicit historical or current inputs",
        "campaign": "Run and resume a selected original Potts or NNN point grid",
        "init": "Create or verify a workspace with selected public resources",
        "exact": "Run original free-chain/XY/CFT-envelope numerics",
        "cft": "Run original high-precision CFT dual-route checks",
        "potts": "Run one original fixed-retained Potts size",
        "nnn": "Run original NNN campaign (smoke by default)",
        "nnn-point": "Run original NNN PRG and response at one point",
        "figures": "Check seven renderer/data mappings (no manuscript validation or rendering)",
        "ladder": "Run the original mandatory Potts ladder with new per-size evidence commits",
        "controls": "Run hash-bound original resolution or charge verification",
        "render": "Render original figures with explicit analytic or historical input identity",
    }.items():
        q = sub.add_parser(route, help=help_text)
        q.add_argument("--workspace", type=Path, required=True)
        if route == "init":
            continue
        q.add_argument("--run-id", type=run_id, required=True)
        q.add_argument("--timeout", type=positive_seconds, default=1800,
                       help="wall seconds; terminate the process group on timeout")
        if route in ("campaign", "nnn", "ladder"):
            q.add_argument("--stop-after", type=positive_integer, help="pause after this many newly committed tasks")
        if route == "campaign":
            q.add_argument("--model", choices=("potts", "nnn"), required=True)
            q.add_argument("--sizes", nargs="+", type=int)
            q.add_argument("--j2", nargs="+", type=float, choices=(0.05, 0.1, 0.2))
            q.add_argument("--resume", action="store_true")
        if route == "postprocess":
            from .postprocess import ANALYSES
            q.add_argument("--analysis", choices=tuple(ANALYSES), required=True)
            q.add_argument("--source", choices=("historical", "current"), required=True)
            q.add_argument("--input-run", type=run_id)
            q.add_argument("--ladder-run", type=run_id)
            q.add_argument("--p2-run", type=run_id)
        if route == "ladder":
            q.add_argument("--resume", action="store_true")
        if route == "controls":
            q.add_argument("--control", choices=("resolution", "charge", "potts-p2", "retained"), required=True)
        if route == "render":
            q.add_argument("--source", choices=("analytic", "historical"), required=True)
            q.add_argument("--mode", choices=("fast", "publication"), default="publication")
            q.add_argument("--fig", nargs="+", choices=("1", "2", "3", "4", "5", "6", "S1"))
        if route == "exact":
            q.add_argument("--mode", choices=("fast", "publication"), default="publication")
        if route == "nnn":
            q.add_argument("--mode", choices=("smoke", "publication"), default="smoke")
            q.add_argument("--resume", action="store_true", help="reuse original verified checkpoints")
        if route == "potts":
            q.add_argument("--L", type=int, choices=range(6, 15), required=True)
        if route == "nnn-point":
            q.add_argument("--L", type=int, choices=range(6, 21, 2), required=True)
            q.add_argument("--j2", type=float, choices=(0.05, 0.1, 0.2), default=0.2)
    return p


def execute(args):
    project, vault = prepare_workspace(args.workspace)
    workspace = project.parent
    if args.route == "init":
        print(json.dumps({"status": "VERIFIED", "workspace": str(workspace)}))
        return 0
    from .campaign import locked, run
    with locked(workspace, args.run_id):
        if args.route == "campaign":
            return run(args, project)
        return execute_single(args, project, vault)


def execute_single(args, project, vault):
    workspace = project.parent
    run_root = reject_links(project / "build/runs" / args.run_id)
    resume = getattr(args, "resume", False)
    if run_root.exists() and not resume:
        raise FileExistsError(f"run exists; choose a fresh run-id: {run_root}")
    if resume and not run_root.is_dir():
        raise FileNotFoundError("--resume requires an existing run")
    logdir = workspace / "logs" / f"{args.run_id}-{uuid.uuid4().hex[:12]}"
    logdir.mkdir(parents=True)
    command = [sys.executable, "-B", "-m", "cc_repro.worker", args.route,
               "--project", str(project), "--vault", str(vault), "--run-root", str(run_root)]
    for key in ("mode", "L", "j2", "analysis", "source", "input_run", "ladder_run", "p2_run", "control"):
        if getattr(args, key, None) is not None:
            command.extend(["--" + key.replace("_", "-"), str(getattr(args, key))])
    if getattr(args, "fig", None):
        command.extend(["--fig", *args.fig])
    if getattr(args, "stop_after", None) is not None:
        command.extend(["--stop-after", str(args.stop_after)])
    if resume:
        command.append("--resume")
    env = os.environ.copy()
    env.update({"PYTHONPATH": str(Path(__file__).resolve().parent.parent),
                "PYTHONNOUSERSITE": "1", "PYTHONDONTWRITEBYTECODE": "1",
                "MPLBACKEND": "Agg", "OPENBLAS_NUM_THREADS": "1",
                "OMP_NUM_THREADS": "1", "MKL_NUM_THREADS": "1"})
    started = time.monotonic()
    receipt = {"schema": "cc-repro-execution/1", "package_version": __version__,
               "route": args.route, "command": command, "run_root": str(run_root),
               "binding_sha256": digest(workspace / "binding.json"),
               "timeout_seconds": args.timeout, "status": "RUNNING"}
    path = logdir / "execution.json"
    path.write_text(json.dumps(receipt, indent=2) + "\n")
    with (logdir / "stdout.txt").open("w") as out, (logdir / "stderr.txt").open("w") as err:
        child = subprocess.Popen(command, cwd=project, env=env, stdout=out, stderr=err, start_new_session=True)
        try:
            code = child.wait(timeout=args.timeout)
            receipt["status"] = "PASS" if code == 0 else "PAUSED" if code == 75 else "FAIL"
        except (subprocess.TimeoutExpired, KeyboardInterrupt) as error:
            os.killpg(child.pid, signal.SIGKILL)
            child.wait()
            code = 124 if isinstance(error, subprocess.TimeoutExpired) else 130
            receipt["status"] = "TIMEOUT" if code == 124 else "INTERRUPTED"
    receipt.update(returncode=code, elapsed_seconds=time.monotonic() - started)
    receipt["logs"] = {name: digest(logdir / name) for name in ("stdout.txt", "stderr.txt")}
    path.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps({"status": receipt["status"], "receipt": str(path), "run_root": str(run_root)}))
    if code:
        print((logdir / "stderr.txt").read_text()[-4000:], file=sys.stderr)
    return code


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        return execute(args)
    except (OSError, ValueError, RuntimeError) as error:
        print(f"cc-repro: {error}", file=sys.stderr)
        return 2
