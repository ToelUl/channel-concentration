#!/usr/bin/env python3
"""Generate a deterministic SHA-256 manifest from an exact Git commit."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

RELEASE_NAME = re.compile(r"^[a-z0-9][a-z0-9.-]+$")


def digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def git(repo: Path, *args: str, input_bytes: bytes | None = None) -> bytes:
    safe = repo.resolve().as_posix()
    result = subprocess.run(
        ["git", "-c", f"safe.directory={safe}", *args],
        cwd=repo,
        input=input_bytes,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode:
        raise ValueError(result.stderr.decode("utf-8", errors="replace").strip())
    return result.stdout


def validate_release_name(value: str) -> str:
    if not RELEASE_NAME.fullmatch(value):
        raise ValueError("Release name must use lowercase letters, digits, dots, and hyphens")
    return value


def resolve_commit(repo: Path, value: str) -> str:
    resolved = git(repo, "rev-parse", "--verify", value + "^{commit}").decode().strip()
    if not re.fullmatch(r"[0-9a-f]{40}", resolved):
        raise ValueError("Git did not resolve a full commit identity")
    return resolved


def tree_entries(repo: Path, commit: str) -> list[dict[str, str]]:
    raw = git(repo, "ls-tree", "-r", "-z", "--full-tree", commit)
    entries = []
    seen = set()
    for record in raw.split(b"\0"):
        if not record:
            continue
        metadata, raw_path = record.split(b"\t", 1)
        mode, kind, object_id = metadata.decode("ascii").split()
        path = raw_path.decode("utf-8")
        if kind != "blob" or mode not in {"100644", "100755"}:
            raise ValueError("Release manifest accepts only regular tracked files: " + path)
        if path in seen or path.startswith("/") or "\\" in path or ".." in Path(path).parts:
            raise ValueError("Unsafe or duplicate tracked path: " + path)
        seen.add(path)
        entries.append({"path": path, "mode": mode, "git_blob": object_id})
    if not entries:
        raise ValueError("The selected commit contains no tracked files")
    return entries


def read_blobs(repo: Path, entries: list[dict[str, str]]) -> list[bytes]:
    request = b"".join(entry["git_blob"].encode("ascii") + b"\n" for entry in entries)
    payload = git(repo, "cat-file", "--batch", input_bytes=request)
    offset = 0
    blobs = []
    for entry in entries:
        line_end = payload.index(b"\n", offset)
        object_id, kind, size_text = payload[offset:line_end].decode("ascii").split()
        size = int(size_text)
        offset = line_end + 1
        content = payload[offset:offset + size]
        offset += size
        if payload[offset:offset + 1] != b"\n":
            raise ValueError("Malformed git cat-file batch output")
        offset += 1
        if object_id != entry["git_blob"] or kind != "blob" or len(content) != size:
            raise ValueError("Git blob identity mismatch: " + entry["path"])
        blobs.append(content)
    if offset != len(payload):
        raise ValueError("Unexpected trailing git cat-file output")
    return blobs


def repository_url(repo: Path) -> str:
    return git(repo, "remote", "get-url", "origin").decode().strip()


def build_manifest(repo: Path, commit_value: str, release_name: str) -> dict:
    repo = repo.resolve()
    release_name = validate_release_name(release_name)
    commit = resolve_commit(repo, commit_value)
    tree = git(repo, "rev-parse", commit + "^{tree}").decode().strip()
    commit_date = git(repo, "show", "-s", "--format=%cI", commit).decode().strip()
    entries = tree_entries(repo, commit)
    blobs = read_blobs(repo, entries)
    files = []
    for entry, content in zip(entries, blobs):
        files.append({**entry, "bytes": len(content), "sha256": digest_bytes(content)})
    return {
        "schema": "channel-concentration-release-content-manifest/1.0",
        "release_name": release_name,
        "repository": repository_url(repo),
        "content_commit": commit,
        "content_tree": tree,
        "content_commit_date": commit_date,
        "files": files,
        "totals": {"files": len(files), "bytes": sum(item["bytes"] for item in files)},
        "scope": "Exact tracked-file bytes at the release content commit; generated release assets are intentionally outside this manifest.",
    }


def output_is_untracked_at_commit(repo: Path, commit: str, output: Path) -> None:
    resolved = output.resolve()
    try:
        relative = resolved.relative_to(repo.resolve()).as_posix()
    except ValueError:
        return
    result = subprocess.run(
        ["git", "-c", f"safe.directory={repo.resolve().as_posix()}", "cat-file", "-e", f"{commit}:{relative}"],
        cwd=repo,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if result.returncode == 0:
        raise ValueError("Output is tracked by the bound commit and would create a circular release asset")


def write_new_json(path: Path, value: dict) -> None:
    if path.exists():
        raise FileExistsError("Refusing to overwrite existing output: " + str(path))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--commit", required=True, help="Exact release content commit or ref")
    parser.add_argument("--release-name", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    manifest = build_manifest(args.repo, args.commit, args.release_name)
    output_is_untracked_at_commit(args.repo.resolve(), manifest["content_commit"], args.output)
    write_new_json(args.output, manifest)
    print(json.dumps({"status": "PASS", "output": args.output.name, **manifest["totals"],
                      "content_commit": manifest["content_commit"]}, indent=2))


if __name__ == "__main__":
    main()
