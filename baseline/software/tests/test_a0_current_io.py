"""Bounded I/O tests. Frozen large-size values are fixtures, never fresh evidence."""
import csv
import importlib
import json
from pathlib import Path
import shutil
import sys
import pytest
from cc_repro import evidence, checkpoint_bridge, current_analysis
from cc_repro.resources import prepare_workspace, digest
from cc_repro.postprocess import historical_evidence


def test_original_response_counts_survive_checkpoint_projection(tmp_path, monkeypatch):
    project, _ = prepare_workspace(tmp_path / "workspace")
    sys.path.insert(0, str(project / "scripts/simulation"))
    original = importlib.import_module("reproduce_nnn_tfim_expensive")
    config_path = project / "repro/config/nnn_tfim_expensive_reproduction.json"
    config = evidence.read(config_path)
    root = project / "build/runs/fixture-bounded-response"
    work = root / "work/nnn_tfim_expensive"
    task = {"kind": "bounded_test_response", "L": 6, "J2": .2, "h": 1.3362834266313166, "requested": 6}
    key = "response_fixture_L6_neig6"

    def bounded_main():
        events = original.EventLog(work / "events.jsonl")
        store = original.Checkpoints(work / "checkpoints", digest(project / "scripts/simulation/simulate_interacting_benchmarks.py"), digest(config_path), original.stable_hash(original.solver_environment()), "--resume" in sys.argv, events)
        store.run(key, task, lambda: original.response_task(6, .2, task["h"], 6, config))

    monkeypatch.setattr(original, "main", bounded_main)
    monkeypatch.setattr(sys, "argv", [])
    assert checkpoint_bridge.run(project, root, "smoke", False) == 0
    path = work / "response-counts" / (key + ".json")
    before = path.read_bytes()
    payload = evidence.read(path)
    assert payload["counts"]["requested"] == 6
    assert payload["counts"]["solver_returned"] >= payload["counts"]["nominal_eigenpairs"]
    assert payload["counts"]["retained_groups"] > 0
    assert checkpoint_bridge.run(project, root, "smoke", True) == 0
    assert path.read_bytes() == before
    path.write_bytes(before + b" ")
    with pytest.raises(ValueError, match="identity mismatch"):
        checkpoint_bridge.run(project, root, "smoke", True)


def test_current_fit_io_with_explicit_frozen_fixtures(tmp_path, monkeypatch):
    project, vault = prepare_workspace(tmp_path / "workspace")
    history, _ = historical_evidence(project.parent, vault)
    base = history / "data/reproducibility"
    # Production uses a new subprocess per workspace; mirror that module isolation.
    monkeypatch.delitem(sys.modules, "common", raising=False)
    monkeypatch.syspath_prepend(str(project / "scripts/cleanroom"))
    from common import candidate_run
    root = project / "build/runs/FIXTURE-fit-plumbing"
    staging = candidate_run(root)
    for name in ["potts_outcome_aware_fss.csv", "potts_outcome_aware_fit_receipt.json"]:
        shutil.copyfile(base / name, staging.data / name)
    benchmark = staging.data / "interacting_benchmarks.csv"
    shutil.copyfile(base / "interacting_benchmarks.csv", benchmark)
    module = current_analysis.load(project, "scripts/analysis/derive_potts_theory_guided_7over5.py")
    original_hashes = dict(module.EXPECTED_HASHES)
    paths = {}
    for L, name in [(12, "06_L12_receipt.json"), (13, "08_L13_receipt.json"), (14, "10_L14_receipt.json")]:
        p = root / "work/fixture-ladder" / f"L{L}.json"
        payload = evidence.read(history / "repro/evidence/potts_tail_calibration" / name)
        payload["source_role"] = "fixture"
        evidence.write(p, payload)
        paths[L] = p
    module.TAIL_RECEIPTS = paths
    module.EXPECTED_HASHES = {p: digest(p) for p in [benchmark, staging.data / "potts_outcome_aware_fss.csv", *paths.values()]}
    module.DATA = staging.data
    monkeypatch.setenv("CC_RUN_ROOT", str(root))
    module.main()
    result = evidence.read(staging.data / "potts_theory_guided_7over5_receipt.json")
    assert result["primary_KF_contract"]["fit"]["intercept"] == pytest.approx(.8475891059181018, abs=1e-13)
    assert result["scale_diagnostics"]["free_power_windows"]["6"]["omega"] == pytest.approx(1.4511, abs=.00005)
    assert all(digest(p) == h for p, h in module.EXPECTED_HASHES.items())
    assert original_hashes != module.EXPECTED_HASHES
    # Arithmetic accepts fixtures for this test; the production entrypoint does not.
    with pytest.raises(ValueError, match="requires current"):
        current_analysis.enclosure_product(project, [evidence.read(p) for p in paths.values()], [])
