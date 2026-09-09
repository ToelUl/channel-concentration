"""Bounded end-to-end checks of actual original producers and durable control."""
from pathlib import Path
import csv
import hashlib
import json
import os
import subprocess
import sys
from types import SimpleNamespace
import pytest
import cc_repro
from cc_repro.resources import prepare_workspace
from cc_repro.campaign import locked, run as campaign_run


def invoke(workspace, *args, expected=0):
    env = os.environ.copy()
    env.update(PYTHONPATH=str(Path(cc_repro.__file__).parent.parent), PYTHONDONTWRITEBYTECODE="1",
               OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1", MKL_NUM_THREADS="1")
    result = subprocess.run([sys.executable, "-B", "-m", "cc_repro", args[0],
                             "--workspace", str(workspace), *args[1:]],
                            cwd=workspace.parent, env=env, capture_output=True, text=True, timeout=120)
    assert result.returncode == expected, result.stdout + result.stderr
    return result


@pytest.mark.parametrize("model,sizes", [("potts", [6, 7]), ("nnn", [6, 8])])
def test_campaign_pause_resume_and_refusals(tmp_path, model, sizes):
    workspace = tmp_path / "workspace"
    args = ["campaign", "--model", model, "--run-id", "grid", "--sizes", *map(str, sizes)]
    invoke(workspace, *args, "--stop-after", "1", expected=75)
    root = workspace / "project/build/runs/grid"
    state = json.loads((root / "campaign.json").read_text())
    assert state["status"] == "PAUSED"
    records = list(state["tasks"].values())
    assert [r["status"] for r in records] == ["PASS", "PENDING"]
    first_hash = records[0]["result_sha256"]
    invoke(workspace, *args, "--resume")
    complete = json.loads((root / "campaign.json").read_text())
    assert complete["status"] == "PASS"
    assert list(complete["tasks"].values())[0]["result_sha256"] == first_hash
    rows = list(csv.DictReader((root / "summary.csv").open()))
    expected = [0.91994933624515, 0.9066642727045653] if model == "potts" else [0.9041064567710609, 0.8482778793520019]
    assert [float(r["K_F"]) for r in rows] == pytest.approx(expected, abs=1e-10, rel=1e-10)
    assert all(r["status"] == "PASS" for r in rows)
    assert rows[1]["P2"] == "" if model == "potts" else rows[1]["P4"] == ""
    summary = (root / "summary.csv").read_bytes()
    result = invoke(workspace, *args, "--resume")
    assert '"computed": 0' in result.stdout
    assert (root / "summary.csv").read_bytes() == summary
    invoke(workspace, "campaign", "--model", model, "--run-id", "grid", "--sizes", str(sizes[0]), "--resume", expected=2)
    state_bytes = (root / "campaign.json").read_bytes()
    complete["plan"]["environment"]["numpy"] = "incompatible"
    (root / "campaign.json").write_text(json.dumps(complete))
    invoke(workspace, *args, "--resume", expected=2)
    (root / "campaign.json").write_bytes(state_bytes)
    # Detect changed committed numerical evidence, without replacing it.
    first = list(complete["tasks"].values())[0]
    output = workspace / "project/build/runs" / first["run_id"] / "result.json"
    output.write_bytes(output.read_bytes() + b" ")
    invoke(workspace, *args, "--resume", expected=2)


def test_nnn_native_checkpoint_pause_resume(tmp_path):
    workspace = tmp_path / "workspace"
    args = ["nnn", "--mode", "smoke", "--run-id", "native"]
    invoke(workspace, *args, "--stop-after", "1", expected=75)
    work = workspace / "project/build/runs/native/work/nnn_tfim_expensive"
    manifest = json.loads((work / "checkpoint_manifest.json").read_text())
    assert manifest["checkpoint_count"] == 1
    record = manifest["checkpoints"][0]
    first = work / "checkpoints" / record["path"]
    assert hashlib.sha256(first.read_bytes()).hexdigest() == record["sha256"]
    before = first.read_bytes()
    invoke(workspace, *args, "--resume")  # original native validator must accept partial manifest
    assert first.read_bytes() == before
    final = json.loads((work / "smoke_result.json").read_text())
    assert [x["h"] for x in final["roots"]] == pytest.approx([1.3362834266313166, 1.329057106952854], abs=1e-10, rel=1e-10)
    assert json.loads((work / "checkpoint_manifest.json").read_text())["checkpoint_count"] == 2
    invoke(workspace, *args, "--resume")
    invoke(workspace, "nnn", "--mode", "publication", "--run-id", "native", "--resume", expected=1)
    # A checkpoint not in the committed inventory must not be adopted on restart.
    extra = work / "checkpoints/uncommitted.json"
    extra.write_bytes(first.read_bytes())
    invoke(workspace, *args, "--resume", expected=1)
    extra.unlink()
    first.write_bytes(before + b" ")
    invoke(workspace, *args, "--resume", expected=1)


def test_failure_stops_grid_without_numeric_rows(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    project, _ = prepare_workspace(workspace)
    args = SimpleNamespace(model="potts", sizes=[6, 7], j2=None, run_id="failed",
                           resume=False, stop_after=None, timeout=120)
    monkeypatch.setattr("cc_repro.cli.execute", lambda args: 2)
    assert campaign_run(args, project) == 2
    root = project / "build/runs/failed"
    rows = list(csv.DictReader((root / "summary.csv").open()))
    assert [r["status"] for r in rows] == ["FAIL", "PENDING"]
    assert all(r["K_F"] == "" for r in rows)
    args.resume = True
    with pytest.raises(ValueError, match="silently retried"):
        campaign_run(args, project)


def test_lock_excludes_concurrent_writer(tmp_path):
    with locked(tmp_path, "grid"):
        with pytest.raises(BlockingIOError):
            with locked(tmp_path, "grid"):
                pass
