"""Explicit source routing for unchanged original postprocessing programs."""
from hashlib import sha256
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import sys
import tempfile
from types import SimpleNamespace
import zipfile
from .resources import digest, reject_links
from .campaign import atomic_text, locked, make_plan, result_for

ANALYSES = {
    "potts-fss": "scripts/cleanroom/regenerate_potts_fss.py",
    "potts-7over5": "scripts/analysis/derive_potts_theory_guided_7over5.py",
    "projector-enclosures": "scripts/analysis/derive_projector_response_enclosures.py",
    "potts-ranked": "scripts/analysis/derive_potts_certified_ranked_weights.py",
    "nnn-ranked": "scripts/analysis/derive_nnn_ranked_distribution_convergence.py",
}
CURRENT = {"potts-fss", "potts-ranked", "nnn-ranked"}


def verified_nnn(project, root):
    """Verify the complete current original publication checkpoint identity, not just count."""
    from . import evidence
    from .checkpoint_bridge import commit_context
    work = root / "work/nnn_tfim_expensive"
    metadata = root / "data/reproducibility/nnn_tfim_expensive_run_metadata.json"
    m = evidence.read(metadata)
    if m.get("comparison_status") != "PASS" or m.get("mode") != "publication":
        raise ValueError("current NNN requires an accepted full publication run")
    if evidence.read(work / "cc_repro_commit_context.json") != commit_context(project, "publication"):
        raise ValueError("current NNN adapter/source/environment binding mismatch")
    original = load(project, "scripts/simulation/reproduce_nnn_tfim_expensive.py")
    config_path = project / "repro/config/nnn_tfim_expensive_reproduction.json"
    config = evidence.read(config_path)
    expected = original.publication_checkpoint_keys(config)
    entries = evidence.read(work / "checkpoint_manifest.json")
    evidence.verify_keys([Path(r["path"]).stem for r in entries["checkpoints"]], expected)
    engine_hash = digest(project / "scripts/simulation/simulate_interacting_benchmarks.py")
    env_hash = original.stable_hash(original.solver_environment())
    original.validate_resume_checkpoint_store(work, engine_hash, digest(config_path), env_hash)
    for field, expected_hash in (("engine_sha256", engine_hash), ("config_sha256", digest(config_path)), ("solver_environment_sha256", env_hash)):
        if m.get(field) != expected_hash:
            raise ValueError("NNN metadata identity mismatch")
    for item in m["outputs"]:
        path = reject_links(project / item["path"])
        if ".." in Path(item["path"]).parts or not path.is_relative_to(root) or digest(path) != item["sha256"]:
            raise ValueError("NNN output source/hash mismatch")
    for key in expected:
        p = evidence.read(work / "checkpoints" / (key + ".json"))
        if p["task_sha256"] != original.stable_hash(p["task"]):
            raise ValueError("NNN checkpoint task hash mismatch")
    counts = evidence.read(work / "response-counts-manifest.json")
    if counts["context"] != commit_context(project, "publication"):
        raise ValueError("NNN response count context mismatch")
    response_keys = {k for k in expected if k.startswith("response_")}
    evidence.verify_keys([Path(r["path"]).stem for r in counts["files"]], response_keys)
    for r in counts["files"]:
        payload = evidence.read(evidence.verify_file(work, r))
        if payload["context"] != counts["context"] or payload["task_key"] != Path(r["path"]).stem:
            raise ValueError("NNN response count task binding mismatch")
        checkpoint = evidence.read(work / "checkpoints" / (payload["task_key"] + ".json"))
        if payload["task"] != checkpoint["task"]:
            raise ValueError("NNN response count configuration differs from checkpoint")
    return metadata, work / "checkpoint_manifest.json"


def historical_evidence(workspace, vault):
    """Expand only data/evidence, with archive-bound byte verification on reuse."""
    root = reject_links(workspace / "inputs/postprocess-evidence")
    with zipfile.ZipFile(vault) as archive:
        selected = {}
        for info in archive.infolist():
            name = info.filename
            if info.is_dir() or not name.startswith(("cc215/data/reproducibility/", "cc215/repro/evidence/")):
                continue
            rel = PurePosixPath(name).relative_to("cc215")
            if ".." in rel.parts or "\\" in name or ((info.external_attr >> 16) & 0o170000) == 0o120000:
                raise ValueError("unsafe historical evidence member")
            if str(rel) in selected:
                raise ValueError("duplicate historical evidence member")
            selected[str(rel)] = archive.read(info)
    if not selected:
        raise ValueError("historical evidence is absent")
    with locked(workspace, "postprocess-evidence"):
        if not root.exists():
            stage = Path(tempfile.mkdtemp(prefix="evidence-", dir=root.parent))
            try:
                for rel, blob in selected.items():
                    p = stage / rel
                    p.parent.mkdir(parents=True, exist_ok=True)
                    p.write_bytes(blob)
                stage.rename(root)
            finally:
                if stage.exists():
                    shutil.rmtree(stage)
        actual = set()
        for path in root.rglob("*"):
            reject_links(path)
            if path.is_file():
                actual.add(path.relative_to(root).as_posix())
        if actual != set(selected):
            raise ValueError("historical evidence inventory mismatch")
        for rel, blob in selected.items():
            if digest(root / rel) != sha256(blob).hexdigest():
                raise ValueError(f"historical evidence hash mismatch: {rel}")
    return root, [{"path": rel, "sha256": sha256(blob).hexdigest()} for rel, blob in sorted(selected.items())]


def load(project, relative):
    path = project / relative
    sys.path.insert(0, str(path.parent))
    sys.path.insert(0, str(project / "scripts/cleanroom"))
    spec = importlib.util.spec_from_file_location("original_postprocessor", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def current_potts(project, source_root, run, *, allow_previous=False):
    """Export consumer-compatible result records only from a complete accepted grid."""
    state = json.loads((source_root / "campaign.json").read_text())
    expected = make_plan(SimpleNamespace(model="potts", sizes=list(range(6, 15)), j2=None), project)
    if allow_previous:
        from .receipt_compat import input_identity
        expected = input_identity(state.get("plan"), expected)
    if state.get("status") != "PASS" or state.get("plan") != expected:
        raise ValueError("current Potts analysis requires the complete compatible L6-L14 PASS grid")
    keys = {task["key"] for task in expected["tasks"]}
    if set(state["tasks"]) != keys:
        raise ValueError("current Potts task inventory mismatch")
    required = {"complete_cluster", "solve_residual", "eigenpair_residual",
                "grouping_stability_same_eigenpairs", "absolute_reference_agreement"}
    verified = []
    for task in expected["tasks"]:
        record = state["tasks"][task["key"]]
        if record["status"] != "PASS":
            raise ValueError("current Potts task is not PASS")
        data = result_for(project, record)
        if data["L"] != task["L"] or set(data["acceptance"]) != required:
            raise ValueError("current Potts task identity/acceptance mismatch")
        verified.append((task, record, data))
    cfg = json.loads((project / "repro/config/potts_retained_eigenpairs_cleanroom.json").read_text())
    result = {"status": "PASS", "all_sizes_fresh_pass": True,
              "active_data_source": "fresh_complete_L6_L14", "closure_ceiling": cfg["fresh_campaign_success_label"],
              "adapter_export": "derived from cc-repro grid; not a historical authority or qualification receipt",
              "source_campaign_sha256": digest(source_root / "campaign.json"), "size_results": {}}
    for task, record, data in verified:
        L = task["L"]
        output = run.root / f"work/potts/L{L}_retained_eigenpairs_receipt.json"
        converted = {**data["result"], "schema": "potts-retained-eigenpairs-size-receipt/1.1",
                     "L": L, "n_eigenpairs_requested": 256, "acceptance": data["acceptance"],
                     "status": cfg["fresh_campaign_success_label"],
                     "adapter_export": True, "original_point_result_sha256": record["result_sha256"]}
        atomic_text(output, json.dumps(converted, indent=2, allow_nan=False) + "\n")
        result["size_results"][str(L)] = {"receipt": str(output), "receipt_sha256": digest(output)}
    path = run.receipts / "t3_campaign.json"
    atomic_text(path, json.dumps(result, indent=2) + "\n")
    return path


def run(project, vault, run_root, analysis, source, input_run):
    if source == "current" and (analysis not in CURRENT or not input_run):
        raise ValueError("this analysis requires historical inputs, or --input-run is missing")
    if source == "historical" and input_run:
        raise ValueError("historical mode cannot accept --input-run")
    module = load(project, ANALYSES[analysis])
    from common import candidate_run
    inputs = []
    evidence = None
    if source == "historical":
        evidence, inputs = historical_evidence(project.parent, vault)
    src = project / "build/runs" / input_run if input_run else None
    if src == run_root:
        raise ValueError("input and output run must differ")
    # Refuse insufficient current data before creating a plausible output run.
    if source == "current":
        if analysis.startswith("potts"):
            state = json.loads((src / "campaign.json").read_text())
            expected = make_plan(SimpleNamespace(model="potts", sizes=list(range(6, 15)), j2=None), project)
            if state.get("status") != "PASS" or state.get("plan") != expected:
                raise ValueError("current Potts analysis requires the complete compatible L6-L14 PASS grid")
        else:
            metadata, manifest = verified_nnn(project, src)
        inputs = [{"path": str(src / "campaign.json"), "sha256": digest(src / "campaign.json")}] if analysis.startswith("potts") else [{"path": str(p), "sha256": digest(p)} for p in (metadata, manifest)]
    staging = candidate_run(run_root)
    arguments = ["--run-root", str(run_root)]
    product = None
    if analysis == "potts-fss":
        if source == "current":
            current_potts(project, src, staging)
        arguments += ["--source", "frozen" if source == "historical" else "campaign"]
        products = [staging.data / name for name in ("potts_outcome_aware_fss.csv", "potts_outcome_aware_fit_audit.csv", "potts_outcome_aware_fit_receipt.json")]
    elif analysis == "potts-7over5":
        # Only rebase original input paths; expected scientific digests remain unchanged.
        mapping = {old: run_root / "work/evidence" / old.relative_to(project) for old in module.TAIL_RECEIPTS.values()}
        for old, new in mapping.items():
            new.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(evidence / old.relative_to(project), new)
        module.TAIL_RECEIPTS = {L: mapping[path] for L, path in module.TAIL_RECEIPTS.items()}
        module.EXPECTED_HASHES = {mapping.get(path, path): value for path, value in module.EXPECTED_HASHES.items()}
        for name in ("potts_outcome_aware_fss.csv", "interacting_benchmarks.csv", "potts_outcome_aware_fit_receipt.json"):
            shutil.copyfile(evidence / "data/reproducibility" / name, staging.data / name)
        os.environ["CC_RUN_ROOT"] = str(run_root)
        arguments = []
        products = [staging.data / name for name in ("potts_theory_guided_7over5_fit_summary.csv", "potts_scaled_P2_7over5.csv", "potts_theory_guided_7over5_receipt.json")]
    elif analysis == "projector-enclosures":
        external = reject_links(project.parent / "postprocessing" / run_root.name)
        product = module.write_run(evidence, external)
        products = [external / "projector-response-enclosures.json", external / "manifest.json"]
    elif analysis == "potts-ranked":
        arguments += ["--source-contract", source]
        if source == "historical":
            arguments += ["--evidence-root", str(evidence)]
        else:
            campaign = current_potts(project, src, staging)
            arguments += ["--campaign-receipt", str(campaign)]
        products = [staging.data / name for name in ("potts_L14_certified_ranked_weights.csv", "potts_L14_certified_ranked_weights_receipt.json")]
    else:
        arguments += ["--source-contract", source]
        if source == "historical":
            arguments += ["--evidence-root", str(evidence)]
        else:
            arguments += ["--benchmarks", str(src / "data/reproducibility/interacting_benchmarks.csv"),
                          "--manifest", str(manifest), "--run-metadata", str(metadata),
                          "--checkpoint-dir", str(src / "work/nnn_tfim_expensive/checkpoints")]
        products = [staging.data / name for name in ("nnn_ranked_distribution_convergence.csv", "nnn_ranked_distribution_convergence_receipt.json")]
    if analysis != "projector-enclosures":
        sys.argv = [str(project / ANALYSES[analysis]), *arguments]
        module.main()
    receipt = {"schema": "cc-repro-postprocess/1", "status": "PASS", "analysis": analysis,
               "source": source, "input_run": input_run,
               "producer": ANALYSES[analysis], "producer_sha256": digest(project / ANALYSES[analysis]),
               "inputs": inputs, "outputs": [{"path": str(p), "sha256": digest(p)} for p in products],
               "model_eigensolves_performed": False,
               "scope": "original postprocessing acceptance only; historical replay is not fresh large computation"}
    atomic_text(run_root / "postprocess.json", json.dumps(receipt, indent=2) + "\n")
    print(json.dumps({"status": "PASS", "analysis": analysis, "source": source, "receipt": str(run_root / "postprocess.json")}))
    return 0
