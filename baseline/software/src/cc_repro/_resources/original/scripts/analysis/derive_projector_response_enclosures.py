#!/usr/bin/env python3
"""Replay conditional response-projector bounds from immutable Potts receipts.

No model, eigensolver, or numerical kernel is imported. All interval operations
use exact rational arithmetic on the archived binary64 endpoints. Only final
JSON endpoints are rounded outwards to binary64. Historical x, x/P2, and low
hybrid estimators remain explicitly distinct from r and Kproj.
"""
from __future__ import annotations

import argparse
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import sys

PROJECT = Path(__file__).resolve().parents[2]
SOURCES = {
    12: ("06_L12_receipt.json", "08021ba1f5e9f085eefba09dca4dc2ccf3ad1c9b666f3d853efc6fd2f436d161"),
    13: ("08_L13_receipt.json", "c3c28864986adff6c6602461836a5b6d849c3df96909fc497b35f683d1e65e30"),
    14: ("10_L14_receipt.json", "04d33a0f9b6eb1a083dbc07bfeff029cf17140e9c38442aaa303a110c306482b"),
}
PREMISES = [
    "True nondegenerate finite-size ground state and positive excitation gaps.",
    "Correct spectral identification, complete retained clusters and mutually orthogonal projectors.",
    "The projector family is complete on the response subspace; omitted weights are nonnegative.",
    "Archived P2, projector-error, numerator and gap intervals enclose their stated exact operands.",
    "Recorded residual and grouping checks support these premises but do not independently prove spectral completeness.",
]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rational(value) -> Fraction:
    """Preserve binary64 endpoints, rejecting bool, strings and nonfinite data."""
    if isinstance(value, bool) or not isinstance(value, (int, float, Fraction)):
        raise ValueError("a finite numeric operand is required")
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("nonfinite operand")
    return Fraction(value)


def interval(value, *, positive=False) -> tuple[Fraction, Fraction]:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError("a two-endpoint interval is required")
    lo, hi = map(rational, value)
    if lo < 0 or lo > hi or (positive and lo <= 0):
        raise ValueError("invalid nonnegative/positive interval")
    return lo, hi


def directed(value: Fraction, *, upper: bool) -> float:
    nearest = float(value)
    if not math.isfinite(nearest):
        raise ValueError("endpoint cannot be represented as finite binary64")
    exact = Fraction(nearest)
    if (upper and exact < value) or (not upper and exact > value):
        nearest = math.nextafter(nearest, math.inf if upper else -math.inf)
    if not math.isfinite(nearest):
        raise ValueError("outward endpoint overflow")
    return nearest


def outward(bounds) -> list[float]:
    lo, hi = bounds
    if lo > hi:
        raise ValueError("reversed derived interval")
    return [directed(lo, upper=False), directed(hi, upper=True)]


def concentration_bounds(p2, retained) -> dict:
    """Plan Eq. 3.3, conditional on the supplied interval and spectral premises."""
    pm, pp = interval(p2, positive=True)
    weights = [interval(w) for w in retained]
    sm = sum((w[0] for w in weights), Fraction())
    sp = sum((w[1] for w in weights), Fraction())
    if sm > pp:
        raise ValueError("retained lower mass exceeds total upper bound")
    qm = sum((w[0] ** 2 for w in weights), Fraction())
    qp = sum((w[1] ** 2 for w in weights), Fraction())
    tail_upper = pp - sm
    lo = qm / pp**2
    hi = min(Fraction(1), (qp + tail_upper**2) / pm**2)
    if lo > hi:
        raise ValueError("inconsistent concentration bounds")
    return {
        "K_projector_interval": outward((lo, hi)),
        "K_projector_interval_width_upper": directed(hi - lo, upper=True),
        "Q_r_interval": outward((qm, qp)),
        "retained_r_mass_interval": outward((sm, sp)),
        "retained_probability_interval": outward((sm / pp, min(Fraction(1), sp / pm))),
        "omitted_r_mass_interval": outward((max(Fraction(), pm - sp), tail_upper)),
        "omitted_probability_interval": outward((max(Fraction(), 1 - sp / pm), 1 - sm / pp)),
    }


def conversion_bounds(individual_gap, mean_gap) -> list[float]:
    dm, dp = interval(individual_gap, positive=True)
    mm, mp = interval(mean_gap, positive=True)
    return outward(((dm / mp)**2, (dp / mm)**2))


def _diagnostics(p2, clusters) -> dict:
    pm, pp = interval(p2, positive=True)
    xs = [interval(c["channel_x_interval"]) for c in clusters]
    sm, sp = (sum((x[i] for x in xs), Fraction()) for i in (0, 1))
    qm, qp = (sum((x[i]**2 for x in xs), Fraction()) for i in (0, 1))
    return {
        "historical_retained_x_mass_interval": outward((sm, sp)),
        "historical_retained_x_over_P2_interval": outward((sm / pp, sp / pm)),
        "historical_hybrid_low_interval": outward((qm / pp**2, qp / pm**2)),
        "historical_self_normalized_x_low_interval": (
            outward((qm / sp**2, min(Fraction(1), qp / sm**2))) if sm > 0 else None
        ),
        "identity": "hybrid_low=sum_R x_a^2/P2^2; self_normalized_x_low=sum_R x_a^2/(sum_R x_a)^2; neither is the full exact-projector concentration",
    }


def validate_rung(payload, rung_name, rung):
    if payload["ground_and_P2"]["minres_info"] != 0:
        raise ValueError("archived solve did not converge")
    interval(payload["ground_and_P2"]["P2_interval"], positive=True)
    if rational(payload["ground_and_P2"]["gap_lower"]) <= 0:
        raise ValueError("positive ground gap premise missing")
    if (rung["nominal_N_eig"] != int(rung_name) or rung["guard_eigenpairs"] != 1
            or rung["solver_eigenpairs"] != int(rung_name) + 1
            or rung["grouping_stable"] is not True):
        raise ValueError("cutoff or stable-grouping metadata failed")
    clusters = rung["clusters"]
    if not clusters:
        raise ValueError("missing retained clusters")
    slices = [c["rank_slice"] for c in clusters]
    if slices != rung["retained_cluster_slices"]:
        raise ValueError("cluster identities differ from retained inventory")
    previous_stop = 1
    for c in clusters:
        start, stop = c["rank_slice"]
        if (type(start) is not int or type(stop) is not int or start != previous_stop
                or stop <= start or stop > int(rung_name)
                or c["multiplicity"] != stop - start):
            raise ValueError("noncontiguous, duplicate or invalid retained group")
        previous_stop = stop
        for key in ("resolvent_r_interval", "channel_x_interval", "numerator_interval"):
            interval(c[key])
        conversion_bounds(c["individual_gap_interval"], c["mean_gap_interval"])
        if rational(c["complement_gap_lower"]) <= 0 or c["dual_accounting_ratio_consistent"] is not True:
            raise ValueError("cluster spectral or dual-accounting premise failed")
    for signature in rung["grouping_signatures"].values():
        if signature != slices:
            raise ValueError("grouping-signature mismatch")


def replay_payload(payload) -> dict:
    size = payload["L"]
    if size not in SOURCES or payload["status"] != "CERTIFIED_PASS":
        raise ValueError("unexpected archival receipt identity/status")
    p2 = payload["ground_and_P2"]["P2_interval"]
    records = []
    for name, rung in sorted(payload["rungs"].items(), key=lambda item: int(item[0])):
        validate_rung(payload, name, rung)
        new = concentration_bounds(p2, [c["resolvent_r_interval"] for c in rung["clusters"]])
        old = interval(rung["K_F_interval"])
        lo, hi = map(Fraction, new["K_projector_interval"])
        midpoint = sum(old) / 2
        new.update({
            "L": size, "rung": name,
            "nominal_N_eig": rung["nominal_N_eig"],
            "guard_eigenpairs": rung["guard_eigenpairs"],
            "solver_eigenpairs": rung["solver_eigenpairs"],
            "retained_cluster_slices": rung["retained_cluster_slices"],
            "grouping_stable_recorded": rung["grouping_stable"],
            "historical_interval": rung["K_F_interval"],
            "historical_width": rung["K_F_interval_width"],
            "historical_interval_identity": "mean-gap numerator with resolvent-P2 denominator and historical converted tail; not silently renamed Kproj",
            "new_interval_contained_in_historical": old[0] <= lo <= hi <= old[1],
            "historical_midpoint": float(midpoint),
            "historical_midpoint_projector_absolute_error_upper": directed(max(abs(midpoint-lo), abs(hi-midpoint)), upper=True),
            "rounding_agreement_decimal_places": [d for d in range(1, 13) if format(float(lo), f".{d}f") == format(float(hi), f".{d}f") == format(float(midpoint), f".{d}f")],
            "retained_conversion_factors": [conversion_bounds(c["individual_gap_interval"], c["mean_gap_interval"]) for c in rung["clusters"]],
            "historical_diagnostics": _diagnostics(p2, rung["clusters"]),
            "status": "CONDITIONAL_ARITHMETIC_ENCLOSURE",
        })
        records.append(new)
    return {"L": size, "P2_interval": p2, "rungs": records}


def ranked_rows(payload, name="256") -> dict:
    rung = payload["rungs"][name]
    validate_rung(payload, name, rung)
    pm, pp = interval(payload["ground_and_P2"]["P2_interval"], positive=True)
    rows = []
    for i, c in enumerate(rung["clusters"]):
        rm, rp = interval(c["resolvent_r_interval"])
        xm, xp = interval(c["channel_x_interval"])
        rows.append({
            "source_cluster_index_zero_based": i, "rank_slice": c["rank_slice"],
            "multiplicity": c["multiplicity"],
            "r_interval": outward((rm, rp)),
            "projector_weight_interval": outward((rm/pp, rp/pm)),
            "projector_weight_midpoint_diagnostic": float((rm+rp)/(pm+pp)),
            "historical_x_interval": c["channel_x_interval"],
            "historical_x_over_P2_interval": outward((xm/pp, xp/pm)),
            "historical_x_over_P2_midpoint": float((xm+xp)/(pm+pp)),
            "retained_x_to_r_factor_interval": conversion_bounds(c["individual_gap_interval"], c["mean_gap_interval"]),
        })
    rows.sort(key=lambda r: (-r["projector_weight_midpoint_diagnostic"], r["source_cluster_index_zero_based"]))
    old_order = sorted(rows, key=lambda r: (-r["historical_x_over_P2_midpoint"], r["source_cluster_index_zero_based"]))
    mass = concentration_bounds(payload["ground_and_P2"]["P2_interval"], [c["resolvent_r_interval"] for c in rung["clusters"]])
    tail_upper = Fraction(mass["omitted_probability_interval"][1])
    for rank, row in enumerate(rows, 1):
        row["midpoint_rank"] = rank
        row["historical_midpoint_rank"] = next(i for i,r in enumerate(old_order,1) if r is row)
        row["historically_displayed_top15"] = row["historical_midpoint_rank"] <= 15
        bounds = list(map(Fraction,row["projector_weight_interval"]))
        point = Fraction(row["historical_x_over_P2_midpoint"])
        row["historical_point_projector_absolute_error_upper"] = directed(max(abs(point-bounds[0]),abs(bounds[1]-point)),upper=True)
        row["rounding_agreement_decimal_places"] = [d for d in range(1,13) if format(float(bounds[0]),f".{d}f")==format(float(bounds[1]),f".{d}f")==format(float(point),f".{d}f")]
    top = rows[:15]
    adjacent = all(a["projector_weight_interval"][0] > b["projector_weight_interval"][1] for a,b in zip(top,top[1:]))
    retained_rest = all(top[-1]["projector_weight_interval"][0] > r["projector_weight_interval"][1] for r in rows[15:])
    tail_excluded = Fraction(top[-1]["projector_weight_interval"][0]) > tail_upper
    r1 = interval(top[0]["r_interval"],positive=True)
    r2 = interval(top[1]["r_interval"],positive=True)
    return {
        "L": payload["L"], "rung": name, "rows": rows,
        "top15_same_cluster_order_as_historical": [r["source_cluster_index_zero_based"] for r in top] == [r["source_cluster_index_zero_based"] for r in old_order[:15]],
        "top15_adjacent_intervals_strictly_ordered": adjacent,
        "top15_separated_from_all_other_retained": retained_rest,
        "top15_separated_from_each_omitted_channel_by_mass_bound": tail_excluded,
        "top15_full_spectrum_rank_certified_conditionally": adjacent and retained_rest and tail_excluded,
        "rank1_over_rank2_interval": outward((r1[0]/r2[1],r1[1]/r2[0])),
        "mass": mass,
        "status": "CONDITIONAL_ARITHMETIC_ENCLOSURE",
    }


def load_sources(evidence_root: Path) -> tuple[list[dict], list[dict]]:
    payloads, bindings = [], []
    for size, (filename, expected) in SOURCES.items():
        relative = Path("repro/evidence/potts_tail_calibration") / filename
        path = evidence_root / relative
        actual = sha256(path)
        if actual != expected:
            raise ValueError(f"immutable source hash mismatch: {relative}")
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload["L"] != size:
            raise ValueError("source size mismatch")
        payloads.append(payload)
        bindings.append({"path":relative.as_posix(),"sha256":actual,"historical_status":payload["status"]})
    return payloads, bindings


def write_run(evidence_root: Path, run_root: Path) -> dict:
    # Validate every source and compute before creating any output.
    evidence_root = evidence_root.resolve(strict=True)
    payloads, bindings = load_sources(evidence_root)
    product = {
        "schema": "projector-response-enclosures/1.0.0",
        "observable": "Kproj=sum_all r_a^2/P2^2; r_a=||Pi_a chi||^2; P2=sum_all r_a",
        "classification": "CONDITIONAL_NUMERICAL_ENCLOSURE",
        "premises": PREMISES, "spectral_completeness_independently_proved": False,
        "model_eigensolves_performed": False, "postprocessing_only": True,
        "arithmetic": "Exact rational operations on archived binary64 endpoints; final bounds rounded outward to binary64",
        "producer": {"path":"scripts/analysis/derive_projector_response_enclosures.py","sha256":sha256(Path(__file__))},
        "sources": bindings,
        "sizes": [replay_payload(p) for p in payloads],
        "L14_ranks": ranked_rows(next(p for p in payloads if p["L"] == 14)),
    }
    # No symlink components, source-tree writes, source-vault writes, or overwrite.
    if ".." in run_root.parts:
        raise ValueError("parent traversal in output path")
    absolute = run_root.absolute()
    if any(p.is_symlink() for p in (absolute, *absolute.parents)):
        raise ValueError("symlink output path")
    output = absolute.resolve()
    if output.is_relative_to(evidence_root) or output.is_relative_to(PROJECT):
        raise ValueError("run must be staging-only outside immutable evidence and canonical source")
    output.mkdir(parents=True, exist_ok=False)
    rendered = json.dumps(product, indent=2, sort_keys=True, allow_nan=False) + "\n"
    with (output/"projector-response-enclosures.json").open("x",encoding="utf-8") as handle:
        handle.write(rendered)
    manifest = {"schema":"projector-response-run-manifest/1.0.0","outputs":[{"path":"projector-response-enclosures.json","sha256":sha256(output/"projector-response-enclosures.json")}],"sources":bindings,"producer":product["producer"]}
    with (output/"manifest.json").open("x",encoding="utf-8") as handle:
        json.dump(manifest,handle,indent=2,sort_keys=True); handle.write("\n")
    return product


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-root",type=Path,required=True,help="read-only historical project containing repro/evidence")
    parser.add_argument("--run-root",type=Path,required=True,help="fresh staging directory outside source and historical evidence")
    args = parser.parse_args()
    result = write_run(args.evidence_root,args.run_root)
    print(json.dumps({"status":result["classification"],"sizes":len(result["sizes"]),"rungs":sum(len(p["rungs"]) for p in result["sizes"]),"model_eigensolves_performed":False}))


if __name__ == "__main__":
    main()
