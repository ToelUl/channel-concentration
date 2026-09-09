"""Public entrypoints to byte-identical original finite-size controls."""
import csv
import math
from .postprocess import load
from . import evidence

PRODUCERS = {
    "resolution": ("scripts/verification/verify_j2_zero_resolution.py", "tfim_j2_zero_resolution_match.csv"),
    "charge": ("scripts/verification/verify_potts_charge_sector.py", "potts_charge_sector_checks.csv"),
}


def run(project, root, name):
    if name in ("potts-p2", "retained"):
        return potts_legacy_control(project, root, name)
    relative, filename = PRODUCERS[name]
    root.mkdir(parents=True, exist_ok=False)
    module = load(project, relative)
    if name == "resolution":
        rows = module.level_projector_rows()
    else:
        rows, failures = module.run_checks()
        if failures:
            raise ValueError(f"original charge control reports {failures} failures")
    path = root / filename
    with path.open("x", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    passed = bool(rows) and all(row["status"] == "PASS" for row in rows)
    result = {"schema": "cc-repro-controls/1", "source_role": "current", "generation": "solver",
              "status": "PASS" if passed else "FAIL", "control": name, "rows": len(rows),
              "identity": evidence.context(project, {"original_default_control": name}),
              "producer": evidence.record(project / relative, project), "output": evidence.record(path, root),
              "claim_scope": "Original finite-size symmetry/resolution control only"}
    evidence.commit(root, "result", result)
    return 0 if passed else 2


def p2_recipe(project):
    relative = "repro/vendor/potts_tail/simulate_interacting_benchmarks.py"
    return {"producer": relative, "producer_sha256": evidence.digest(project / relative),
            "function": "hybrid_level_projector_kf", "k_low": 96, "tol_eig": 1e-9,
            "tol_group": 1e-7, "rtol_solve": 1e-9, "ncv_factor": 4,
            "g": 1.0, "representation": "k0", "guard_used": 0,
            "historical_invocation_recovered": False,
            "binding_basis": "Unchanged frozen helper defaults; require exact agreement with stored P2 serialization, not inferred interval midpoint",
            "serialization": "Original benchmark .12g P2 point"}


def potts_legacy_control(project, root, name):
    recipe = p2_recipe(project)
    module = load(project, recipe["producer"])
    if recipe["producer_sha256"] != "fef7cd67619a4bc0827cb28e0a5da70b4352dea373fa790f130ce89437d1e104":
        raise ValueError("original legacy benchmark producer mismatch")
    from .resources import files
    import io
    raw = files("cc_repro").joinpath("_resources/historical/cc215/data/reproducibility/interacting_benchmarks.csv").read_bytes()
    reference = {int(r["L"]): r for r in csv.DictReader(io.StringIO(raw.decode())) if r["model"] == "Potts"}
    identity = evidence.context(project, recipe)
    root.mkdir(parents=True, exist_ok=False)
    state = {"schema": "cc-repro-p2-points/1", "source_role": "current", "generation": "solver",
             "recipe": recipe, "identity": identity, "status": "RUNNING", "points": {},
             "comparison_reference_sha256": evidence.sha256(raw).hexdigest(),
             "scope": "Fresh original point solve; historical invocation was not recorded; printed P2 equivalence is checked explicitly"}
    sizes = range(6,12) if name == "potts-p2" else (6,12)
    rows = []
    for L in sizes:
        H,V,dimension = module.build_potts_k0(L,1.0)
        result = module.hybrid_level_projector_kf(H,V,k_low=96,tol_eig=1e-9,tol_group=1e-7,rtol_solve=1e-9,ncv_factor=4)
        point = float(format(result["P2"], ".12g"))
        passed = (result["minres_info"] == 0 and math.isfinite(result["P2"]) and result["P2"] > 0 and point == float(reference[L]["P2"]))
        payload = {"schema": "cc-repro-p2-point/1", "source_role": "current", "generation": "solver", "L":L,
            "status":"PASS" if passed else "FAIL", "identity":identity,"method":"k0-hybrid",
            "P2_semantics":"original_projected_solve_y_dot_y","P2":point,"P2_raw":result["P2"],
            "original_result":{k:v for k,v in result.items() if k != "x"},
            "acceptance":{"minres":result["minres_info"] == 0,"stored_point_serialization":point == float(reference[L]["P2"])},
            "counts":{"requested":96,"solver_returned":min(96,dimension-2),"guard_configured":0,"guard_used":0,"retained_groups":result["n_levels"]},
            "comparison_reference":{"P2":reference[L]["P2"],"usage":"comparison_reference"}}
        state["points"][str(L)] = evidence.commit(root,f"P2-L{L}",payload)
        rows.append({"representation":"k0","L":L,"dimension":dimension,"n_levels":result["n_levels"],"KF":result["KF"],"KF_half":result["KF_half"]})
        if not passed:
            state["status"]="FAIL";evidence.write(root/"p2.json",state);return 2
    if name == "retained":
        H,V=module.build_potts_full(6,1.0);result=module.dense_level_projector_kf(H,V)
        rows.insert(1,{"representation":"full","L":6,"dimension":729,"n_levels":result["n_levels"],"KF":result["KF"],"KF_half":None})
        expected=[(130,45,"0.919949",None),(729,269,"0.919949",None),(44368,47,"0.875126","0.875110")]
        checks=[]
        for row,(dim,n,k,half) in zip(rows,expected):
            checks.append(row["dimension"]==dim and row["n_levels"]==n and format(row["KF"],".6f")==k and (half is None or format(row["KF_half"],".6f")==half))
        state["status"]="PASS" if all(checks) else "FAIL"
        evidence.commit(root,"retained",{"schema":"cc-repro-retained-control/1","source_role":"current","status":state["status"],"identity":identity,"rows":rows,"table_display_checks":checks,"historical_invocation_recovered":False,"scope":"Reconstructed unchanged original invocation; agreement with printed retained table only"})
    else:
        state["status"]="PASS"
    evidence.write(root/"p2.json",state)
    return 0 if state["status"]=="PASS" else 2
