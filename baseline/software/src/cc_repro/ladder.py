"""New local authority and durable per-size commits around unchanged Potts ladder math.

Safe pause/resume occurs at size boundaries. An interrupted/uncommitted size is
preserved and refused, rather than mixing ground contexts or silently retrying.
"""
import importlib.util
from pathlib import Path
import resource
import sys
import time
from . import evidence

SIZES = (12, 13, 14)
RUNGS = (128, 192, 256)


def numerical_modules(project):
    directory = project / "repro/vendor/potts_tail"
    sys.path.insert(0, str(directory))
    spec = importlib.util.spec_from_file_location("original_a0_ladder", directory / "spectral_tail_runner.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    from .postprocess import load
    fixed = load(project, "scripts/cleanroom/retained_eigenpairs_potts.py")
    fixed.initialize_solver_runtime()
    model = fixed.load_model()
    return module, model, directory / "simulate_interacting_benchmarks.py"


def config():
    return {"profile": "P-LADDER", "sizes": list(SIZES), "rungs": list(RUNGS),
            "g": 1.0, "k_mom": 0, "guard": 1, "width_ceiling": 1e-8,
            "conditional384": False, "resume_boundary": "committed_size"}


def validate_payload(project, payload, identity, predecessor, *, role="current"):
    from .postprocess import load
    evidence.require_role(payload, role)
    if payload.get("identity") != identity or payload.get("predecessor") != predecessor:
        raise ValueError("ladder source/environment/predecessor mismatch")
    if payload.get("L") not in SIZES or payload.get("status") != "PASS":
        raise ValueError("unaccepted ladder size")
    evidence.verify_keys(list(payload["rungs"]), [str(n) for n in RUNGS])
    validator = load(project, "scripts/analysis/derive_projector_response_enclosures.py")
    module, _, _ = numerical_modules(project)
    ground_fields = {"E0", "E0_interval", "ground_residual_abs", "first_excited_residual_abs", "gap_lower",
                     "ground_projector_error", "b_norm", "rhs_error_bound", "alpha", "minres_info",
                     "solve_residual_abs", "operator_error_bound", "effective_residual_bound", "y_norm", "y_error_bound", "P2_interval"}
    if set(payload["ground_and_P2"]) != ground_fields:
        raise ValueError("incomplete or unexpected serialized ground context")
    evidence.canonical(payload)  # Reject nonfinite values throughout the payload.
    previous = ()
    intervals = []
    for n in RUNGS:
        rung = payload["rungs"][str(n)]
        validator.validate_rung(payload, str(n), rung)
        raw = {k: v for k, v in rung.items() if k not in ("raw_rung_sha256", "nested_with_previous")}
        if evidence.canonical(raw) != rung["raw_rung_sha256"]:
            raise ValueError("raw rung hash mismatch")
        slices = tuple(tuple(s) for s in rung["retained_cluster_slices"])
        if rung["nested_with_previous"] is not True or (previous and not module.nested_prefix(previous, slices)) or not module._rung_nonwidth_checks(rung):
            raise ValueError("ladder nonwidth/nesting check failed")
        intervals.append(module.Interval(*rung["K_F_interval"]))
        previous = slices
    outcome = module.adjudicate_intervals(intervals)
    if not outcome["width_pass"] or payload["outcome"] != outcome:
        raise ValueError("ladder adjudication mismatch")
    return payload


def accepted(project, root, *, complete=True, allow_previous=False):
    state = evidence.read(root / "ladder.json")
    identity = evidence.context(project, config())
    if allow_previous:
        if not complete:
            raise ValueError("previous producers are read-only complete inputs; not resumable")
        from .receipt_compat import input_identity
        identity = input_identity(state.get("identity"), identity)
    if state.get("schema") != "cc-repro-ladder/1" or state.get("identity") != identity or state.get("source_role") != "current":
        raise ValueError("incompatible ladder source identity")
    keys = list(state["sizes"])
    if keys != [str(L) for L in SIZES[:len(keys)]]:
        raise ValueError("ladder committed sizes are not a prefix")
    if complete and (state.get("status") != "PASS" or len(keys) != 3):
        raise ValueError("complete accepted current ladder required")
    result, predecessor = [], None
    for key, binding in state["sizes"].items():
        payload = evidence.load_commit(root, binding)
        if payload["L"] != int(key):
            raise ValueError("ladder size identity mismatch")
        validate_payload(project, payload, identity, predecessor)
        result.append(payload)
        predecessor = binding
    return state, result


def compute_size(project, L, identity, predecessor):
    module, model, _ = numerical_modules(project)
    started = time.monotonic()
    H, V, dimension = model.build_potts_k0(L, 1.0)
    H, V = H.tocsr(), V.tocsr()
    ground = module.ground_and_p2_context(H, V, L)
    payload = {"schema": "cc-repro-ladder-size/1", "source_role": "current", "generation": "solver",
               "L": L, "dimension": dimension, "identity": identity, "predecessor": predecessor,
               "ground_and_P2": {k: v for k, v in ground.items() if k not in ("psi", "b")},
               "rungs": {}, "counts": {}, "spectral_completeness_independently_proved": False}
    previous, intervals, nonwidth = (), [], True
    for nominal in RUNGS:
        rung = module.run_rung(H, ground, nominal)
        slices = tuple(tuple(s) for s in rung["retained_cluster_slices"])
        rung["nested_with_previous"] = bool(not previous or module.nested_prefix(previous, slices))
        nonwidth = nonwidth and rung["nested_with_previous"] and module._rung_nonwidth_checks(rung)
        payload["rungs"][str(nominal)] = rung
        payload["counts"][str(nominal)] = {"requested": nominal, "solver_returned": rung["solver_eigenpairs"],
            "guard_configured": 1, "guard_used": rung["guard_eigenpairs"],
            "retained_excited_states": sum(stop-start for start, stop in slices), "retained_groups": len(slices)}
        intervals.append(module.Interval(*rung["K_F_interval"]))
        previous = slices
    payload["outcome"] = module.adjudicate_intervals(intervals)
    payload["status"] = "PASS" if nonwidth and payload["outcome"]["width_pass"] else "INCONCLUSIVE"
    payload["resource"] = {"elapsed_seconds": time.monotonic()-started, "max_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
    return payload


def run(project, root, resume=False, stop_after=None):
    identity = evidence.context(project, config())
    if resume:
        state, _ = accepted(project, root, complete=False)
        if state["status"] not in ("PAUSED", "PASS"):
            raise ValueError("uncommitted/interrupted size cannot be silently retried; preserve run")
    else:
        root.mkdir(parents=True, exist_ok=False)
        state = {"schema": "cc-repro-ladder/1", "source_role": "current", "identity": identity, "status": "RUNNING", "sizes": {}}
        evidence.write(root / "ladder.json", state)
    computed = 0
    for L in SIZES:
        if str(L) in state["sizes"]:
            continue
        state.update(status="RUNNING", active_size=L)
        evidence.write(root / "ladder.json", state)
        predecessor = next(reversed(state["sizes"].values())) if state["sizes"] else None
        payload = compute_size(project, L, identity, predecessor)
        if payload["status"] != "PASS":
            evidence.commit(root, f"L{L}-inconclusive", payload)
            state["status"] = "INCONCLUSIVE"
            evidence.write(root / "ladder.json", state)
            return 2
        validate_payload(project, payload, identity, predecessor)
        state["sizes"][str(L)] = evidence.commit(root, f"L{L}", payload)
        computed += 1
        state.update(status="PASS" if L == 14 else "PAUSED", active_size=None)
        evidence.write(root / "ladder.json", state)
        from .campaign import checkpoint_backup
        checkpoint_backup(project.parent)
        if stop_after is not None and computed >= stop_after and L != 14:
            return 75
    return 0
