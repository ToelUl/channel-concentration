"""Current-input I/O for original fit and enclosure mathematics, with fail-closed lineage."""
import csv
import math
import os
from pathlib import Path
import shutil
from . import evidence, ladder
from .postprocess import load, current_potts


def p2_inputs(project, root):
    """Require separately bound original benchmark point receipts, never infer from intervals."""
    state = evidence.read(root / "p2.json")
    if state.get("schema") != "cc-repro-p2-points/1" or state.get("source_role") != "current" or state.get("status") != "PASS":
        raise ValueError("current accepted original P2 point source required")
    recipe = state["recipe"]
    from .controls import p2_recipe
    if recipe != p2_recipe(project):
        raise ValueError("P2 recipe differs from the reconstructed, point-verified original helper")
    if state.get("identity") != evidence.context(project, recipe):
        raise ValueError("P2 source/configuration/environment mismatch")
    evidence.verify_keys(list(state["points"]), [str(L) for L in range(6, 12)])
    rows = []
    for key, seal in state["points"].items():
        point = evidence.load_commit(root, seal)
        evidence.require_role(point, "current")
        if point.get("identity") != state["identity"] or point.get("L") != int(key) or point.get("status") != "PASS":
            raise ValueError("P2 point identity mismatch")
        if point.get("method") != "k0-hybrid" or point.get("P2_semantics") != "original_projected_solve_y_dot_y":
            raise ValueError("P2 method/point semantics mismatch")
        if set(point.get("acceptance", {})) != {"minres", "stored_point_serialization"} or any(v is not True for v in point["acceptance"].values()):
            raise ValueError("P2 point acceptance missing or failed")
        if type(point["P2"]) not in (int, float) or not math.isfinite(point["P2"]) or point["P2"] <= 0:
            raise ValueError("invalid P2 point")
        rows.append({"model": "Potts", "L": int(key), "P2": point["P2"]})
    return sorted(rows, key=lambda r: r["L"])


def enclosure_product(project, payloads, bindings):
    for payload in payloads:
        evidence.require_role(payload, "current")
    module = load(project, "scripts/analysis/derive_projector_response_enclosures.py")
    # The unchanged math function has an archival-only status gate. This in-memory
    # argument projection occurs AFTER current ladder validation. It is never
    # written as a receipt and does not adopt historical hashes or authority.
    sizes = [module.replay_payload({**p, "status": "CERTIFIED_PASS"}) for p in payloads]
    return {"schema": "projector-response-enclosures/1.0.0", "source_role": "current", "generation": "postprocess",
            "observable": "Kproj=sum_all r_a^2/P2^2; r_a=||Pi_a chi||^2; P2=sum_all r_a",
            "classification": "CONDITIONAL_NUMERICAL_ENCLOSURE", "premises": module.PREMISES,
            "spectral_completeness_independently_proved": False, "model_eigensolves_performed": False,
            "postprocessing_only": True, "sources": bindings, "sizes": sizes,
            "L14_ranks": module.ranked_rows(next(p for p in payloads if p["L"] == 14)),
            "adapter_status_projection": "Original arithmetic API receives its legacy accepted-status token only after fresh source/seal/ground/rung validation; no historical receipt is manufactured",
            "producer": evidence.record(project / "scripts/analysis/derive_projector_response_enclosures.py", project)}


def run(project, root, analysis, input_run, ladder_run, p2_run):
    if not ladder_run:
        raise ValueError("current analysis requires --ladder-run with complete accepted current ladder; historical inputs are not substituted")
    parent = project / "build/runs" / ladder_run
    state, payloads = ladder.accepted(project, parent)
    inputs = [evidence.record(parent / "ladder.json", project.parent)]
    bindings = [{"L": p["L"], "seal": state["sizes"][str(p["L"])]} for p in payloads]
    if analysis == "projector-enclosures":
        product = enclosure_product(project, payloads, bindings)
        root.mkdir(parents=True, exist_ok=False)
        evidence.write(root / "projector-response-enclosures.json", product)
        products = [root / "projector-response-enclosures.json"]
    elif analysis == "potts-7over5":
        if not input_run or not p2_run:
            raise ValueError("current 7/5 requires --input-run fixed campaign and --p2-run original point evidence")
        p2_root = project / "build/runs" / p2_run
        rows = p2_inputs(project, p2_root)
        fixed = project / "build/runs" / input_run
        # Validate full fixed grid before creating output. current_potts rechecks
        # exact plan, per-task hashes and acceptance during the actual export.
        from .campaign import make_plan, result_for
        from types import SimpleNamespace
        fixed_state = evidence.read(fixed / "campaign.json")
        expected = make_plan(SimpleNamespace(model="potts", sizes=list(range(6,15)), j2=None), project)
        if fixed_state.get("plan") != expected or fixed_state.get("status") != "PASS":
            raise ValueError("complete compatible L6-L14 fixed campaign required")
        evidence.verify_keys(list(fixed_state["tasks"]), [t["key"] for t in expected["tasks"]])
        for record in fixed_state["tasks"].values():
            result_for(project, record)
        inputs += [evidence.record(p2_root / "p2.json", project.parent), evidence.record(fixed / "campaign.json", project.parent)]
        from common import candidate_run
        staging = candidate_run(root)
        current_potts(project, fixed, staging)
        fss = load(project, "scripts/cleanroom/regenerate_potts_fss.py")
        import sys
        sys.argv = ["regenerate_potts_fss.py", "--run-root", str(root), "--source", "campaign"]
        fss.main()
        benchmark = staging.data / "interacting_benchmarks.csv"
        with benchmark.open("x", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=["model", "L", "P2"])
            writer.writeheader(); writer.writerows(rows)
        module = load(project, "scripts/analysis/derive_potts_theory_guided_7over5.py")
        frozen_bindings = {str(p.relative_to(project)): h for p,h in module.EXPECTED_HASHES.items()}
        tail_paths = {}
        for payload in payloads:
            p = root / "work/current-ladder" / f"L{payload['L']}.json"
            evidence.write(p, payload)
            tail_paths[payload["L"]] = p
        module.TAIL_RECEIPTS = tail_paths
        # Separate current mode, scoped to this module instance. Source constants
        # and historical mode stay byte-identical. No digest is forged.
        module.EXPECTED_HASHES = {p: evidence.digest(p) for p in [benchmark, staging.data / "potts_outcome_aware_fss.csv", *tail_paths.values()]}
        module.DATA = staging.data
        os.environ["CC_RUN_ROOT"] = str(root)
        module.main()
        evidence.write(root / "input-projection.json", {"source_role": "current", "inputs": inputs,
            "original_historical_bindings_not_adopted": frozen_bindings,
            "legacy_labels": "released_point and certified_interval_midpoint remain original field vocabulary; current lineage is given here"})
        products = [staging.data / n for n in ["potts_theory_guided_7over5_fit_summary.csv", "potts_scaled_P2_7over5.csv", "potts_theory_guided_7over5_receipt.json"]]
    else:
        raise ValueError("unsupported current analysis")
    evidence.commit(root, "postprocess", {"schema": "cc-repro-current-postprocess/1", "status": "PASS",
        "source_role": "current", "generation": "postprocess", "analysis": analysis, "inputs": inputs,
        "outputs": [evidence.record(p, root) for p in products], "model_eigensolves_performed": False,
        "identity": evidence.context(project, {"analysis": analysis}), "claim_scope": "Original conditional mathematics; not spectral completeness or manuscript closure"})
    return 0
