"""Discriminating I/O and reader tests; synthetic values are fixture-only."""
from copy import deepcopy
from pathlib import Path
import csv
import pytest
from cc_repro import evidence, receipt_compat
from cc_repro.current_analysis import replace_initial_benchmark


def fixture_seed(tmp_path):
    project = tmp_path / "project"
    seed = project / "data/reproducibility/interacting_benchmarks.csv"
    seed.parent.mkdir(parents=True); seed.write_bytes(b"original fixture seed\n")
    root = project / "build/runs/FIXTURE"
    benchmark = root / "data/reproducibility/interacting_benchmarks.csv"
    benchmark.parent.mkdir(parents=True); benchmark.write_bytes(seed.read_bytes())
    evidence.write(root / "context.json", {"frozen_data_initial_files": {seed.name: evidence.digest(seed)}})
    rows = [{"model": "Potts", "L": L, "P2": float(L)} for L in range(6, 12)]
    return project, root, benchmark, rows


def test_seed_is_preserved_and_current_points_replace_it(tmp_path):
    project, root, benchmark, rows = fixture_seed(tmp_path)
    with pytest.raises(FileExistsError):
        benchmark.open("x")  # The exact 0.5.0 failure.
    before = benchmark.read_bytes()
    projection = replace_initial_benchmark(project, root, benchmark, rows)
    assert evidence.verify_file(root, projection["preserved_initial_seed"]).read_bytes() == before
    with benchmark.open() as handle:
        assert [int(r["L"]) for r in csv.DictReader(handle)] == list(range(6, 12))
    with pytest.raises(ValueError, match="initial seed"):
        replace_initial_benchmark(project, root, benchmark, rows)


@pytest.mark.parametrize("damage", ["content", "context", "incomplete", "nonfinite", "symlink", "existing-backup"])
def test_seed_rejects_untrusted_or_incomplete_input(tmp_path, damage):
    project, root, benchmark, rows = fixture_seed(tmp_path)
    if damage == "content": benchmark.write_text("tampered\n")
    if damage == "context": evidence.write(root / "context.json", {"frozen_data_initial_files": {benchmark.name: "0"*64}})
    if damage == "incomplete": rows.pop()
    if damage == "nonfinite": rows[0]["P2"] = float("nan")
    if damage == "symlink":
        benchmark.unlink(); benchmark.symlink_to(project / "data/reproducibility/interacting_benchmarks.csv")
    if damage == "existing-backup":
        saved = root / "work/seed-reference/interacting_benchmarks.csv"
        saved.parent.mkdir(parents=True); saved.write_bytes(b"preserve me")
    before = benchmark.read_bytes()
    with pytest.raises((ValueError, FileExistsError)):
        replace_initial_benchmark(project, root, benchmark, rows)
    assert benchmark.read_bytes() == before


def identities():
    current = {"source_binding_sha256": "fixture-binding", "configuration": {"fixture": True}, "environment": evidence.environment()}
    previous = deepcopy(current)
    sources = evidence.read(Path(receipt_compat.__file__).parent / "_data/previous_producers.json")["producers"]["0.5.0.dev0"]
    previous["environment"].update(package_version="0.5.0.dev0", adapter_sources=sources)
    return current, previous


def test_known_previous_identity_is_read_only():
    current, previous = identities(); before = deepcopy(previous)
    assert receipt_compat.input_identity(current, current) == current
    assert receipt_compat.input_identity(previous, current) == previous
    assert previous == before and previous != current


@pytest.mark.parametrize("damage", ["version", "adapter", "dependency", "binding", "config"])
def test_previous_identity_rejects_drift(damage):
    current, previous = identities()
    if damage == "version": previous["environment"]["package_version"] = "0.4.0.dev0"
    if damage == "adapter": previous["environment"]["adapter_sources"]["current_analysis.py"] = "0"*64
    if damage == "dependency": previous["environment"]["numpy"] = "unknown"
    if damage == "binding": previous["source_binding_sha256"] = "different"
    if damage == "config": previous["configuration"]["fixture"] = False
    with pytest.raises(ValueError): receipt_compat.input_identity(previous, current)
