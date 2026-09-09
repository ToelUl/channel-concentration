#!/usr/bin/env python3
"""Derive the certified L=14 Potts low-rank weight table from sealed evidence.

This program performs no eigensolve or model calculation.  It reads the frozen
spectral-tail receipt, normalizes its outward channel intervals by the frozen
P2 interval, and orders only clusters whose lower endpoint is strictly
positive.  The first fifteen rows are the historical Fig. 7 display set (current manuscript Figure 5).
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import sys


PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / "scripts/cleanroom"))
from common import candidate_run, safe_candidate_path
sys.path.insert(0, str(PROJECT / "repro/vendor/potts_tail"))
from spectral_tail_core import div_nonnegative_down, div_up
DEFAULT_SOURCE = (
    PROJECT
    / "repro/evidence"
    / "potts_tail_calibration"
    / "10_L14_receipt.json"
)
DEFAULT_TABLE = (
    PROJECT / "data" / "reproducibility" / "potts_L14_certified_ranked_weights.csv"
)
DEFAULT_RECEIPT = (
    PROJECT
    / "data"
    / "reproducibility"
    / "potts_L14_certified_ranked_weights_receipt.json"
)
EXPECTED_SOURCE_SHA256 = "04d33a0f9b6eb1a083dbc07bfeff029cf17140e9c38442aaa303a110c306482b"
RUNG = "256"
DISPLAY_COUNT = 15


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path)
    parser.add_argument("--source-contract", choices=("historical", "current"), default="historical")
    parser.add_argument("--source", type=Path)
    parser.add_argument("--evidence-root", type=Path, help="read-only extracted evidence root containing repro/evidence")
    parser.add_argument("--campaign-receipt", type=Path)
    parser.add_argument("--table", type=Path, default=None)
    parser.add_argument("--receipt", type=Path, default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run = candidate_run(args.run_root)
    source = (
        args.source
        or ((args.evidence_root / "repro/evidence/potts_tail_calibration/10_L14_receipt.json" if args.evidence_root else DEFAULT_SOURCE) if args.source_contract == "historical" else run.root / "work/potts/L14_retained_eigenpairs_receipt.json")
    ).resolve()
    table = safe_candidate_path(args.table or run.data / DEFAULT_TABLE.name)
    output_receipt = safe_candidate_path(args.receipt or run.data / DEFAULT_RECEIPT.name)
    if table.parent != run.data or output_receipt.parent != run.data:
        raise ValueError("derived outputs must belong to the selected run data directory")
    source_hash = sha256(source)
    payload = json.loads(source.read_text(encoding="utf-8"))
    campaign_path = None
    campaign_hash = None
    if args.source_contract == "historical":
        if source_hash != EXPECTED_SOURCE_SHA256:
            raise RuntimeError(f"sealed L14 receipt hash mismatch: {source_hash}")
        if payload.get("L") != 14 or payload.get("status") != "CERTIFIED_PASS":
            raise RuntimeError("source is not the sealed passing L=14 receipt")
        rung = payload["rungs"][RUNG]
        p2_lower, p2_upper = payload["ground_and_P2"]["P2_interval"]
    else:
        campaign_path = (args.campaign_receipt or run.receipts / "t3_campaign.json").resolve()
        campaign = json.loads(campaign_path.read_text(encoding="utf-8"))
        campaign_hash = sha256(campaign_path)
        source_record = campaign.get("size_results", {}).get("14", {})
        if source_record.get("receipt_sha256") != source_hash or Path(source_record.get("receipt", "")).resolve() != source:
            raise RuntimeError("current L14 source is not bound by the passing campaign")
        if campaign.get("status") != "PASS" or not campaign.get("all_sizes_fresh_pass"):
            raise RuntimeError("current Potts campaign is not a complete fresh pass")
        if (payload.get("schema") != "potts-retained-eigenpairs-size-receipt/1.1"
                or payload.get("L") != 14
                or payload.get("n_eigenpairs_requested") != 256
                or not all(payload.get("acceptance", {}).values())):
            raise RuntimeError("current source is not the accepted fixed-N L14 receipt")
        rung = payload
        p2_lower, p2_upper = payload["P2_interval"]
    if rung["nominal_N_eig"] != 256 or rung["guard_eigenpairs"] != 1:
        raise RuntimeError("unexpected eigenpair-cutoff semantics")
    if rung["solver_eigenpairs"] != 257 or not rung["grouping_stable"]:
        raise RuntimeError("solver/cluster prerequisite failed")

    if not (0 < p2_lower <= p2_upper < float("inf")):
        raise ValueError("positive finite P2 enclosure required")
    p2_central = 0.5 * (p2_lower + p2_upper)
    positive = []
    zero_inclusive = 0
    for source_index, cluster in enumerate(rung["clusters"]):
        x_lower, x_upper = cluster["channel_x_interval"]
        if x_lower <= 0.0:
            zero_inclusive += 1
            continue
        x_central = 0.5 * (x_lower + x_upper)
        weight_lower = div_nonnegative_down(x_lower, p2_upper)
        weight_central = x_central / p2_central
        weight_upper = div_up(x_upper, p2_lower)
        positive.append(
            {
                "source_cluster_index_zero_based": source_index,
                "rank_slice_start": cluster["rank_slice"][0],
                "rank_slice_stop": cluster["rank_slice"][1],
                "multiplicity": cluster["multiplicity"],
                "mean_gap_lower": cluster["mean_gap_interval"][0],
                "mean_gap_upper": cluster["mean_gap_interval"][1],
                "channel_x_lower": x_lower,
                "channel_x_central": x_central,
                "channel_x_upper": x_upper,
                "weight_lower": weight_lower,
                "weight_central": weight_central,
                "weight_upper": weight_upper,
            }
        )

    positive.sort(key=lambda row: row["weight_central"], reverse=True)
    if len(positive) != 18:
        raise RuntimeError(f"expected 18 positive-lower clusters, found {len(positive)}")
    for rank, row in enumerate(positive, start=1):
        row["channel_rank"] = rank
        row["displayed_in_fig7"] = rank <= DISPLAY_COUNT
        row["L"] = 14
        row["momentum_sector"] = 0
        row["n_eigenpairs_requested"] = rung["nominal_N_eig"]
        row["n_eigenpairs_effective"] = rung["nominal_N_eig"]
        row["n_guard_eigenpairs"] = rung["guard_eigenpairs"]
        row["n_solver_eigenpairs"] = rung["solver_eigenpairs"]
        row["n_grouped_channels"] = len(rung["clusters"])

    for current, following in zip(positive[:DISPLAY_COUNT], positive[1:DISPLAY_COUNT]):
        if not current["weight_lower"] > following["weight_upper"]:
            raise RuntimeError("top-15 certified weight intervals are not strictly ordered")

    fieldnames = [
        "L",
        "momentum_sector",
        "n_eigenpairs_requested",
        "n_eigenpairs_effective",
        "n_guard_eigenpairs",
        "n_solver_eigenpairs",
        "n_grouped_channels",
        "channel_rank",
        "displayed_in_fig7",
        "source_cluster_index_zero_based",
        "rank_slice_start",
        "rank_slice_stop",
        "multiplicity",
        "mean_gap_lower",
        "mean_gap_upper",
        "channel_x_lower",
        "channel_x_central",
        "channel_x_upper",
        "weight_lower",
        "weight_central",
        "weight_upper",
    ]
    table.parent.mkdir(parents=True, exist_ok=True)
    with table.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in positive:
            writer.writerow(
                {
                    key: (format(value, ".17g") if isinstance(value, float) else value)
                    for key, value in row.items()
                }
            )

    receipt = {
        "schema": "potts-certified-ranked-weights/1.0",
        "decision_id": "CC-POTTS-RANKED-L14-R1/DERIVE-1.0",
        "claim_ceiling": (
            "CERTIFIED_L14_LOW_RANK_COMPARATOR_ONLY"
            if args.source_contract == "historical"
            else "CALIBRATED_CURRENT_SOURCE_REPRODUCTION_OF_HISTORICAL_L14_LOW_RANK_COMPARATOR"
        ),
        "source_contract": args.source_contract,
        "source_path": str(source.relative_to(PROJECT)) if source.is_relative_to(PROJECT) else str(source),
        "source_sha256": source_hash,
        "campaign_receipt": str(campaign_path) if campaign_path is not None else None,
        "campaign_receipt_sha256": campaign_hash,
        "source_rung": RUNG,
        "normalization": {
            "formula": "pi_lower=x_lower/P2_upper; pi_central=mid(x)/mid(P2); pi_upper=x_upper/P2_lower",
            "P2_interval": [p2_lower, p2_upper],
        },
        "notation": {
            "momentum": "k",
            "n_eigenpairs_requested": 256,
            "n_eigenpairs_effective": 256,
            "n_guard_eigenpairs": 1,
            "n_solver_eigenpairs": 257,
            "n_grouped_channels": len(rung["clusters"]),
            "legacy_mapping": "k_target=256 -> N_eig^req=256",
        },
        "positive_lower_cluster_count": len(positive),
        "zero_inclusive_cluster_count": zero_inclusive,
        "display_rank_count": DISPLAY_COUNT,
        "top15_strict_interval_order": True,
        "table_path": str(table.relative_to(PROJECT)),
        "table_sha256": sha256(table),
        "scientific_compute_performed": False,
        "fresh_result_is_ladder_certificate": False,
    }
    output_receipt.parent.mkdir(parents=True, exist_ok=True)
    output_receipt.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(receipt, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
