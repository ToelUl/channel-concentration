#!/usr/bin/env python3
"""Bind a fixed release commit to frozen manuscript, artwork, and receipts."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess

from generate_release_manifest import (
    build_manifest,
    digest,
    digest_bytes,
    git,
    output_is_untracked_at_commit,
    resolve_commit,
    validate_release_name,
    write_new_json,
)


def artifact(path: Path, name: str) -> dict:
    if not path.is_file() or path.is_symlink():
        raise ValueError("Missing or linked artifact: " + name)
    return {"name": name, "bytes": path.stat().st_size, "sha256": digest(path)}


def path_under(root: Path, name: str) -> Path:
    """Resolve a slash-delimited artifact name without allowing root escape."""
    if not name or name.startswith("/") or "\\" in name:
        raise ValueError("Unsafe artifact name: " + name)
    parts = name.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise ValueError("Unsafe artifact name: " + name)
    candidate = root.joinpath(*parts)
    try:
        candidate.resolve().relative_to(root.resolve())
    except ValueError as error:
        raise ValueError("Artifact escapes its declared root: " + name) from error
    return candidate


def read_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Expected a JSON object: " + path.name)
    return value


def read_commit_json(repo: Path, commit: str, path: str) -> tuple[dict, bytes]:
    """Read JSON bytes from the bound commit, never from the working tree."""
    raw = git(repo, "show", f"{commit}:{path}")
    value = json.loads(raw.decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Expected a JSON object in release content: " + path)
    return value, raw


def tag_ref_status(repo: Path, tag: str, expected_commit: str) -> str:
    result = subprocess.run(
        ["git", "-c", f"safe.directory={repo.resolve().as_posix()}",
         "rev-parse", "--verify", f"refs/tags/{tag}^{{commit}}"],
        cwd=repo,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
        text=True,
    )
    if result.returncode:
        return "NOT_PRESENT_LOCALLY"
    return "PRESENT_MATCH" if result.stdout.strip() == expected_commit else "PRESENT_MISMATCH"


def parse_receipt(value: str) -> tuple[str, Path]:
    if "=" not in value:
        raise ValueError("Verification receipts use NAME=PATH")
    name, raw_path = value.split("=", 1)
    if not name.strip() or not raw_path.strip():
        raise ValueError("Verification receipts use non-empty NAME=PATH")
    return name.strip(), Path(raw_path)


def build_binding(
    repo: Path,
    commit_value: str,
    release_name: str,
    manuscript_root: Path,
    build_root: Path,
    release_manifest_path: Path,
    receipts: list[tuple[str, Path]],
) -> dict:
    repo = repo.resolve()
    manuscript_root = manuscript_root.resolve()
    build_root = build_root.resolve()
    release_name = validate_release_name(release_name)
    commit = resolve_commit(repo, commit_value)
    release_manifest = read_json(release_manifest_path)
    regenerated = build_manifest(repo, commit, release_name)
    if release_manifest != regenerated:
        raise ValueError("Release manifest does not reproduce from the selected content commit")

    figure_map, figure_map_bytes = read_commit_json(
        repo, commit, "companion/FIGURE_MAP.json"
    )
    artwork_record, artwork_bytes = read_commit_json(
        repo, commit, "companion/ARTWORK.json"
    )
    inputs, _ = read_commit_json(repo, commit, "companion/INPUTS.json")
    manuscript_target, manuscript_target_bytes = read_commit_json(
        repo, commit, "release/MANUSCRIPT_TARGET.json"
    )

    figure_source_hashes = {
        row["path"]: row["sha256"] for row in figure_map["source_documents"]
    }
    target_source_hashes = {
        row["name"]: row["sha256"] for row in manuscript_target["sources"]
    }
    if len(target_source_hashes) != 3 or target_source_hashes != figure_source_hashes:
        raise ValueError("Manuscript target and figure-map source identities differ")

    sources = []
    for name, expected_hash in target_source_hashes.items():
        item = artifact(path_under(manuscript_root, name), name)
        if item["sha256"] != expected_hash:
            raise ValueError("Manuscript source differs from frozen target: " + name)
        sources.append(item)

    target_pdf_hashes = {
        row["name"]: row["sha256"] for row in manuscript_target["pdfs"]
    }
    if len(target_pdf_hashes) != 3:
        raise ValueError("Manuscript target must identify exactly three PDFs")
    pdfs = []
    for name, expected_hash in target_pdf_hashes.items():
        item = artifact(path_under(build_root, name), name)
        if item["sha256"] != expected_hash:
            raise ValueError("Manuscript PDF differs from frozen target: " + name)
        pdfs.append(item)

    label_checks = []
    for row in figure_map["figures"]:
        source = path_under(manuscript_root, row["tex_source"])
        text = source.read_text(encoding="utf-8")
        label_count = text.count("\\label{" + row["tex_label"] + "}")
        include_count = text.count("{" + row["output_stem"] + ".pdf}")
        status = "PASS" if label_count == include_count == 1 else "FAIL"
        if status != "PASS":
            raise ValueError("Figure label or include mapping failed: " + row["selector"])
        label_checks.append({
            "selector": row["selector"],
            "tex_source": row["tex_source"],
            "tex_label": row["tex_label"],
            "output_stem": row["output_stem"],
            "label_count": label_count,
            "include_count": include_count,
            "status": status,
        })

    exact_count = 0
    expected_pdfs = {row["selector"]: row for row in artwork_record["figures"]}
    mapped_selectors = {row["selector"] for row in figure_map["figures"]}
    if len(expected_pdfs) != 7 or len(mapped_selectors) != 7 or set(expected_pdfs) != mapped_selectors:
        raise ValueError("Figure Map and artwork must identify the same seven unique figures")
    for row in figure_map["figures"]:
        rendered = path_under(
            build_root / "figures", row["output_stem"] + ".pdf"
        )
        expected = expected_pdfs[row["selector"]]
        if rendered.name != expected["pdf"] or digest(rendered) != expected["pdf_sha256"]:
            raise ValueError("Final manuscript artwork differs from approved identity: " + row["selector"])
        exact_count += 1

    receipt_records = []
    seen_receipts = set()
    for name, path in receipts:
        if name in seen_receipts:
            raise ValueError("Duplicate verification receipt name: " + name)
        seen_receipts.add(name)
        payload = read_json(path)
        if payload.get("status") != "PASS":
            raise ValueError("Verification receipt is not PASS: " + name)
        record = {"name": name, "sha256": digest(path), "status": "PASS"}
        if isinstance(payload.get("schema"), str):
            record["receipt_schema"] = payload["schema"]
        receipt_records.append(record)
    if not receipt_records:
        raise ValueError("At least one PASS verification receipt is required")

    baseline_commit = artwork_record["numerical_baseline_commit"]
    if inputs["commit"] != baseline_commit:
        raise ValueError("Inputs and artwork identify different numerical baselines")
    resolve_commit(repo, baseline_commit)
    return {
        "schema": "channel-concentration-manuscript-binding/1.0",
        "release_name": release_name,
        "release_content": {
            "repository": release_manifest["repository"],
            "commit": commit,
            "tree": release_manifest["content_tree"],
            "manifest_sha256": digest(release_manifest_path),
        },
        "numerical_baseline": {
            "tag": inputs["tag"],
            "commit": baseline_commit,
            "manifest_sha256": inputs["baseline_manifest_sha256"],
            "tag_ref_status": tag_ref_status(repo, inputs["tag"], baseline_commit),
        },
        "manuscript": {
            "target_sha256": digest_bytes(manuscript_target_bytes),
            "sources": sources,
            "pdfs": pdfs,
        },
        "figure_mapping": {
            "figure_map_sha256": digest_bytes(figure_map_bytes),
            "source_validation": figure_map["source_validation"],
            "figures": label_checks,
            "status": "PASS",
        },
        "artwork": {
            "identity_sha256": digest_bytes(artwork_bytes),
            "version": artwork_record["version"],
            "human_review_status": artwork_record["human_review"]["status"],
            "exact_pdf_count": exact_count,
            "status": "PASS",
        },
        "verification_receipts": receipt_records,
        "scope": "Binds exact release content, frozen manuscript sources/PDFs, figure mapping, approved artwork, numerical baseline, and named PASS receipts; the binding asset is not part of its content commit.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--commit", required=True)
    parser.add_argument("--release-name", required=True)
    parser.add_argument("--manuscript-root", required=True, type=Path)
    parser.add_argument("--build-root", required=True, type=Path)
    parser.add_argument("--release-manifest", required=True, type=Path)
    parser.add_argument("--verification-receipt", action="append", default=[], metavar="NAME=PATH")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    binding = build_binding(
        args.repo,
        args.commit,
        args.release_name,
        args.manuscript_root,
        args.build_root,
        args.release_manifest,
        [parse_receipt(value) for value in args.verification_receipt],
    )
    output_is_untracked_at_commit(args.repo.resolve(), binding["release_content"]["commit"], args.output)
    write_new_json(args.output, binding)
    print(json.dumps({
        "status": "PASS",
        "output": args.output.name,
        "release_content_commit": binding["release_content"]["commit"],
        "sources": len(binding["manuscript"]["sources"]),
        "pdfs": len(binding["manuscript"]["pdfs"]),
        "figures": len(binding["figure_mapping"]["figures"]),
        "receipts": len(binding["verification_receipts"]),
    }, indent=2))


if __name__ == "__main__":
    main()
