"""Private, subprocess-only bridge to frozen original producers.

This module adds I/O and acceptance reporting, never numerical kernels.
Historical campaign authorization records are neither changed nor fabricated.
"""
import argparse
import importlib
import json
from pathlib import Path
import runpy
import sys


def emit(run_root, result):
    run_root.mkdir(parents=True, exist_ok=True)
    (run_root / "result.json").write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(json.dumps(result, indent=2, allow_nan=False))
    return 0 if result["status"] == "PASS" else 2


def potts(project, L):
    sys.path.insert(0, str(project / "scripts/cleanroom"))
    original = importlib.import_module("retained_eigenpairs_potts")
    preflight = original.dependency_preflight()
    if preflight["status"] != "PASS":
        raise RuntimeError(str(preflight))
    cfg = json.loads((project / "repro/config/potts_retained_eigenpairs_cleanroom.json").read_text())
    original.initialize_solver_runtime()
    model = original.load_model()
    H, V, dimension = model.build_potts_k0(L, cfg["coupling_g"])
    H, V = H.tocsr(), V.tocsr()
    count = int(cfg["n_eigenpairs_requested"])
    if dimension <= count + cfg["guard_eigenpairs"]:
        result = original.dense_full_sector(model, L, H, V)
    else:
        result = original.sparse_retained_eigenpairs(H, V, L, count)
    reference = original.reference_value(cfg["reference"][str(L)])
    checks = {
        "complete_cluster": bool(result["complete_cluster"]),
        "solve_residual": result["solve_residual_abs"] <= cfg["solve_residual_ceiling"],
        "eigenpair_residual": result["max_eigenpair_residual_abs"] <= cfg["eigenpair_residual_ceiling"],
        "grouping_stability_same_eigenpairs": bool(result["grouping_stable"]),
        "absolute_reference_agreement": abs(result["K_F"] - reference) <= cfg["reference_agreement_ceiling"],
    }
    return {"L": L, "sector_dimension": int(dimension), "result": result,
            "original_reference": reference, "acceptance": checks,
            "status": "PASS" if all(checks.values()) else "FAIL",
            "scope": "original fixed-retained diagnostic; conditional interval, not a new spectral certificate"}


def nnn_point(project, L, j2):
    sys.path.insert(0, str(project / "scripts/simulation"))
    original = importlib.import_module("reproduce_nnn_tfim_expensive")
    cfg = json.loads((project / "repro/config/nnn_tfim_expensive_reproduction.json").read_text())
    root = original.root_task(L, j2, tuple(cfg["prg"]["brackets"][str(j2)]), cfg)
    n = cfg["response"]["n_low_energy_eigenpairs_default"]
    if L == 20:
        n = cfg["response"]["n_low_energy_eigenpairs_L20"][str(j2)]
    response = original.response_task(L, j2, root["h"], n, cfg)
    checks = {
        "prg_residual": abs(root["prg_residual"]) <= cfg["prg"]["maximum_scaled_gap_residual"],
        "eigenpair_residual": all(root[size][key] <= cfg["prg"]["maximum_eigenpair_residual"]
                                 for size in ("small", "large") for key in ("residual_even", "residual_odd")),
        "solve_residual": response["solve_res"] <= cfg["response"]["maximum_solve_residual"],
        "minres": response["minres_info"] == 0,
    }
    return {"root": root, "response": response, "acceptance": checks,
            "status": "PASS" if all(checks.values()) else "FAIL"}


def script(project, relative, arguments):
    path = project / relative
    sys.path.insert(0, str(path.parent))
    sys.argv = [str(path), *arguments]
    runpy.run_path(str(path), run_name="__main__")
    return 0


def main():
    p = argparse.ArgumentParser()
    p.add_argument("route")
    p.add_argument("--project", type=Path, required=True)
    p.add_argument("--vault", type=Path, required=True)
    p.add_argument("--run-root", type=Path, required=True)
    p.add_argument("--mode")
    p.add_argument("--analysis")
    p.add_argument("--source")
    p.add_argument("--input-run")
    p.add_argument("--ladder-run")
    p.add_argument("--p2-run")
    p.add_argument("--control")
    p.add_argument("--fig", nargs="+")
    p.add_argument("--L", type=int)
    p.add_argument("--j2", type=float)
    p.add_argument("--resume", action="store_true")
    p.add_argument("--stop-after", type=int)
    a = p.parse_args()
    sys.path.insert(0, str(a.project))
    if a.route == "postprocess":
        if a.source == "current" and a.analysis in ("potts-7over5", "projector-enclosures"):
            from .current_analysis import run
            return run(a.project, a.run_root, a.analysis, a.input_run, a.ladder_run, a.p2_run)
        from .postprocess import run
        return run(a.project, a.vault, a.run_root, a.analysis, a.source, a.input_run)
    if a.route == "ladder":
        from .ladder import run
        return run(a.project, a.run_root, a.resume, a.stop_after)
    if a.route == "controls":
        from .controls import run
        return run(a.project, a.run_root, a.control)
    if a.route == "render":
        from .render import run
        return run(a.project, a.vault, a.run_root, a.source, a.mode, a.fig)
    if a.route == "potts":
        return emit(a.run_root, potts(a.project, a.L))
    if a.route == "nnn-point":
        return emit(a.run_root, nnn_point(a.project, a.L, a.j2))
    if a.route == "cft":
        sys.path.insert(0, str(a.project / "runtime"))
        from cft_runtime import _cft_route
        return emit(a.run_root, _cft_route(a.run_root, a.vault))
    if a.route == "exact":
        return script(a.project, "scripts/reproducibility/reproduce_numerics.py",
                      ["--mode", a.mode, "--run-root", str(a.run_root)])
    if a.route == "nnn":
        from .checkpoint_bridge import run
        return run(a.project, a.run_root, a.mode, a.resume, a.stop_after)
    if a.route == "figures":
        from .figure_map import check
        return emit(a.run_root, check(a.project))
    raise ValueError(f"unknown route: {a.route}")


if __name__ == "__main__":
    raise SystemExit(main())
