"""I/O-only synthetic stores. No fixture constitutes numerical evidence."""
from copy import deepcopy
from pathlib import Path
import pytest
from cc_repro import evidence, postprocess, receipt_compat
from cc_repro.checkpoint_bridge import commit_context
from cc_repro.resources import prepare_workspace


def fixture_store(tmp_path, previous=False, terminal=False):
    project, _ = prepare_workspace(tmp_path / "workspace")
    root = project / "build/runs/FIXTURE_ONLY"
    work = root / "work/nnn_tfim_expensive"
    original = postprocess.load(project, "scripts/simulation/reproduce_nnn_tfim_expensive.py")
    context = commit_context(project, "publication")
    if previous:
        registry = evidence.read(Path(receipt_compat.__file__).parent / "_data/previous_producers.json")
        context["adapter_environment"].update(package_version="0.5.1.dev0", adapter_sources=registry["producers"]["0.5.1.dev0"])
    evidence.write(work / "cc_repro_commit_context.json", context)
    # Independently obtain precisely the identity constructed by the original producer.
    hashes = {"engine_sha256": original.stable_hash({"producer": original.sha256_file(Path(original.__file__)), "engine": original.sha256_file(Path(original.engine.__file__))}),
              "config_sha256": evidence.digest(project / "repro/config/nnn_tfim_expensive_reproduction.json"),
              "solver_environment_sha256": original.stable_hash(original.solver_environment())}
    key = "fixture-not-a-scientific-task"
    task = {"kind": "fixture-only-no-physics"}
    checkpoint = work / "checkpoints" / (key + ".json")
    evidence.write(checkpoint, {"status": "complete", **hashes, "task": task, "task_sha256": original.stable_hash(task), "result": {"fixture_only": True}})
    manifest = {"schema_version": "nnn-tfim-checkpoint-manifest/1.1.0", **hashes, "checkpoint_count": 1,
                "checkpoints": [{"path": checkpoint.name, "sha256": evidence.digest(checkpoint)}]}
    if not terminal: manifest["cc_repro_commit"] = context
    evidence.write(work / "checkpoint_manifest.json", manifest)
    evidence.write(work / "response-counts-manifest.json", {"context": context, "files": []})
    metadata = root / "data/reproducibility/nnn_tfim_expensive_run_metadata.json"
    evidence.write(metadata, {"fixture_only": True, "comparison_status": "PASS", "mode": "publication", **hashes, "outputs": []})
    return project, root, work, original, key


@pytest.mark.parametrize("previous", [False, True])
@pytest.mark.parametrize("terminal", [False, True])
def test_original_composite_hash_and_preserved_context(tmp_path, previous, terminal):
    project, root, work, original, key = fixture_store(tmp_path, previous, terminal)
    before = (work / "cc_repro_commit_context.json").read_bytes()
    actual = postprocess.verify_nnn_checkpoint_identity(project, work)
    assert actual["engine_sha256"] != evidence.digest(project / "scripts/simulation/simulate_interacting_benchmarks.py")
    assert actual["producer_context"] == evidence.read(work / "cc_repro_commit_context.json")
    assert (work / "cc_repro_commit_context.json").read_bytes() == before


def test_full_reader_composes_original_hash_verifier_and_task_gate(tmp_path, monkeypatch):
    project, root, work, original, key = fixture_store(tmp_path, previous=True, terminal=True)
    # This one-key catalog is explicitly mocked; it is not a 69-task acceptance test.
    monkeypatch.setattr(original, "publication_checkpoint_keys", lambda config: {key})
    monkeypatch.setattr(postprocess, "load", lambda project, path: original)
    metadata, manifest = postprocess.verified_nnn(project, root)
    assert evidence.read(metadata)["fixture_only"] is True
    assert manifest == work / "checkpoint_manifest.json"
    # Restore the real catalog and require refusal even with fixture PASS metadata.
    monkeypatch.undo()
    with pytest.raises(ValueError, match="task key set"):
        postprocess.verified_nnn(project, root)


@pytest.mark.parametrize("damage", ["single-hash", "producer", "dependency", "bridge", "checkpoint", "context-extension"])
def test_reader_rejects_identity_or_content_drift(tmp_path, damage):
    project, root, work, original, key = fixture_store(tmp_path, previous=True)
    if damage == "single-hash":
        path = work / "checkpoint_manifest.json"; payload = evidence.read(path)
        payload["engine_sha256"] = evidence.digest(project / "scripts/simulation/simulate_interacting_benchmarks.py"); evidence.write(path, payload)
    elif damage == "checkpoint":
        path = work / "checkpoints" / (key + ".json"); path.write_bytes(path.read_bytes() + b" ")
    elif damage == "context-extension":
        path = work / "checkpoint_manifest.json"; payload = evidence.read(path)
        payload["cc_repro_commit"]["mode"] = "smoke"; evidence.write(path, payload)
    else:
        path = work / "cc_repro_commit_context.json"; payload = evidence.read(path)
        if damage == "producer": payload["adapter_environment"]["adapter_sources"]["postprocess.py"] = "0" * 64
        if damage == "dependency": payload["adapter_environment"]["numpy"] = "unknown"
        if damage == "bridge": payload["bridge_sha256"] = "0" * 64
        evidence.write(path, payload)
    with pytest.raises((ValueError, RuntimeError)):
        postprocess.verify_nnn_checkpoint_identity(project, work)
