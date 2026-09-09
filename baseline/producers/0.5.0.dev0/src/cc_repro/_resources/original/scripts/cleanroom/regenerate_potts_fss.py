#!/usr/bin/env python3
"""Outcome-aware L6--L14 FSS assembly with all-fresh or all-frozen selection."""
from __future__ import annotations

import csv
import argparse
import itertools
import json
import math
import time
from pathlib import Path

import numpy as np

from common import PROJECT, canonical_hash, environment_receipt, read_json, sha256, write_json, candidate_run, safe_candidate_path

CFT_TARGET = 0.851495620117928174862536635272317552459042013784975737930313


def fit(x: np.ndarray, y: np.ndarray, degree: int = 1) -> dict:
    coeff = np.polyfit(x, y, degree)
    predicted = np.polyval(coeff, x)
    result = {"intercept": float(coeff[-1]), "rss": float(np.sum((y - predicted) ** 2)), "max_abs_residual": float(np.max(np.abs(y - predicted)))}
    if degree == 1:
        result["amplitude"] = float(coeff[0])
    else:
        result["a_1_over_L"] = float(coeff[-2])
        result["b_1_over_L2"] = float(coeff[0])
    return result


def frozen_rows(data_dir: Path) -> list[dict]:
    source = data_dir / "potts_outcome_aware_fss.csv"
    with source.open(newline="", encoding="utf-8") as handle:
        rows = [row for row in csv.DictReader(handle) if int(row["L"]) <= 14]
    return [{
        "L": int(row["L"]), "lower": float(row["lower"]), "upper": float(row["upper"]),
        "midpoint": float(row["midpoint"]), "width": float(row["width"]),
        "status": row["status"], "primary_fit": True, "certificate": row["certificate"],
    } for row in rows]


def fresh_rows(run, campaign: dict) -> list[dict]:
    rows = []
    for L in range(6, 15):
        result = campaign["size_results"][str(L)]
        semantic_path = Path(result["receipt"]).resolve()
        expected_path = (run.root / f"work/potts/L{L}_retained_eigenpairs_receipt.json").resolve()
        if semantic_path != expected_path or sha256(semantic_path) != result["receipt_sha256"]:
            raise RuntimeError(f"fresh Potts L={L} receipt identity/location mismatch")
        receipt = read_json(semantic_path)
        lower, upper = map(float, receipt["K_F_interval"])
        rows.append({
            "L": L, "lower": lower, "upper": upper, "midpoint": float(receipt["K_F"]),
            "width": upper - lower, "status": receipt["status"], "primary_fit": True,
            "certificate": "fresh_calibrated_retained_eigenpairs_256_complete_sector" if receipt["method"] == "complete-sector-dense" else "fresh_calibrated_retained_eigenpairs_256",
        })
    return rows


def endpoint_envelope(rows: list[dict]) -> dict:
    uncertain = [row for row in rows if row["L"] in (12, 13, 14)]
    all_corners = []
    for choices in itertools.product(("lower", "upper"), repeat=3):
        y = np.array([next(float(row[choice]) for row in uncertain if row["L"] == L) if L >= 12 else next(float(row["midpoint"]) for row in rows if row["L"] == L) for L, choice in zip(range(6, 15), ["midpoint"] * 6 + list(choices))])
        current = fit(1.0 / np.arange(6, 15, dtype=float), y)
        all_corners.append({"choices": list(choices), "intercept": current["intercept"]})
    values = [item["intercept"] for item in all_corners]
    return {"all_corners": all_corners, "corner_count": 8, "intercept_min": min(values), "intercept_max": max(values), "intercept_width": max(values) - min(values)}


def main() -> int:
    started = time.monotonic()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path)
    parser.add_argument("--source", choices=("campaign", "frozen"), default="campaign")
    parser.add_argument("--paths-only", action="store_true")
    args = parser.parse_args()
    run = candidate_run(args.run_root)
    campaign_path = run.receipts / "t3_campaign.json"
    if args.paths_only:
        print(json.dumps({"run_root": str(run.root), "input_data": str(run.data), "output_data": str(run.data), "source_mode": args.source, "scientific_compute": "NONE"}, indent=2))
        return 0
    if args.source == "campaign":
        campaign = read_json(campaign_path)
    else:
        # Explicit frozen selection is not represented as a successful T3 campaign.
        config = read_json(PROJECT / "repro/config/potts_retained_eigenpairs_cleanroom.json")
        campaign = {"all_sizes_fresh_pass": False, "active_data_source": "frozen_complete_L6_L14", "closure_ceiling": config["fallback_label"]}
    use_fresh = campaign["all_sizes_fresh_pass"] is True
    rows = fresh_rows(run, campaign) if use_fresh else frozen_rows(run.data)
    if [row["L"] for row in rows] != list(range(6, 15)):
        raise RuntimeError("active Potts rows must be complete L6--L14")
    if any(row["L"] == 15 for row in rows):
        raise RuntimeError("L15 is forbidden in active FSS")
    x = 1.0 / np.array([row["L"] for row in rows], dtype=float)
    y = np.array([row["midpoint"] for row in rows], dtype=float)
    primary = fit(x, y)
    primary["signed_relative_deviation_percent"] = 100.0 * (primary["intercept"] - CFT_TARGET) / CFT_TARGET
    audits = {
        "linear_L8_L14": fit(x[2:], y[2:]),
        "linear_L10_L14": fit(x[4:], y[4:]),
        "linear_L11_L14": fit(x[5:], y[5:]),
        "quadratic_L6_L14": fit(np.column_stack((x, x * x))[:, 0], y, 2),
        "power_4_over_5_L6_L14": fit(np.array([row["L"] ** (-0.8) for row in rows]), y),
    }
    out = run.data
    csv_path = out / "potts_outcome_aware_fss.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["L", "lower", "upper", "midpoint", "width", "status", "primary_fit", "certificate"])
        writer.writeheader()
        writer.writerows(rows)
    audit_path = out / "potts_outcome_aware_fit_audit.csv"
    with audit_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["audit", "intercept", "amplitude", "a_1_over_L", "b_1_over_L2", "rss", "max_abs_residual"])
        for name, item in audits.items():
            writer.writerow([name, item["intercept"], item.get("amplitude", ""), item.get("a_1_over_L", ""), item.get("b_1_over_L2", ""), item["rss"], item["max_abs_residual"]])
    receipt = {
        "schema": "kf-cft.potts-fss.cleanroom.v1",
        "decision_id": "DEC-KF-CFT-REPRODUCIBLE-PROJECT-CLEANROOM-REBUILD-001/A-R1",
        "active_data_source": campaign["active_data_source"],
        "closure_ceiling": campaign["closure_ceiling"],
        "partial_fresh_selection": False,
        "scientific_compute_performed": False,
        "cft_target": CFT_TARGET,
        "primary_contract": {
            "model": "unweighted_OLS_K0_plus_a_over_L", "sizes": list(range(6, 15)),
            "interval_representative": "deterministic_midpoint", "certified_interval_sizes": [12, 13, 14],
            "fit": primary, "certified_endpoint_envelope": endpoint_envelope(rows),
        },
        "fit_audits": audits,
        "l15_active": False,
        "visible_potts_error_bars": False,
        "machine_readable_enclosures_retained": True,
        "inputs": {"t3_campaign_sha256": sha256(campaign_path) if args.source == "campaign" else None, "source_mode": args.source},
        "outputs": {"fss_csv_sha256": sha256(csv_path), "audit_csv_sha256": sha256(audit_path)},
    }
    receipt["receipt_content_sha256"] = canonical_hash(receipt)
    source_receipt = out / "potts_outcome_aware_fit_receipt.json"
    write_json(source_receipt, receipt)
    execution = {
        "schema": "kf-cft.potts-fss.cleanroom-execution.v1",
        "status": "PASS",
        "source_receipt_sha256": sha256(source_receipt),
        "resources": environment_receipt(started),
    }
    execution["receipt_content_sha256"] = canonical_hash(execution)
    write_json(run.receipts / "potts_fss.json", execution)
    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
