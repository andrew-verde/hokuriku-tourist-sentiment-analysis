#!/usr/bin/env python3
"""
Sync local Google review artifacts from the source english-fukui-tourism repo.

This copies only Google review collection checkpoints and multilingual review
analysis outputs. It intentionally skips official survey outputs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE_REPO_CANDIDATES = (
    Path("/Users/andrewgreen/Repositories/andrew-verde/english-fukui-tourism"),
    Path("/Users/andrewgreen/Repositories/andrew-verde/america-fukui-tourism"),
)
DEFAULT_OUTPUT_ROOT = ROOT / "output"

SYNC_DIRS = (
    Path("output/checkpoints"),
    Path("output/multilingual_review_analysis"),
)


class SyncInputError(RuntimeError):
    pass


def default_source_repo() -> Path:
    # Prefer an explicit override, then the known local repo paths.
    override = os.environ.get("ENGLISH_FUKUI_TOURISM_DIR")
    if override:
        return Path(override)
    for candidate in SOURCE_REPO_CANDIDATES:
        if candidate.is_dir():
            return candidate
    return SOURCE_REPO_CANDIDATES[0]


def _require_dir(path: Path) -> None:
    # Fail loudly if a required source folder is missing.
    if not path.is_dir():
        raise SyncInputError(f"Required Google review source directory not found: {path}")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _manifest_path(path: Path, base: Path) -> str:
    try:
        return str(path.relative_to(base))
    except ValueError:
        return str(path)


def _copy_dir(src: Path, dst: Path, manifest_base: Path) -> list[dict[str, object]]:
    # Copy the directory tree, then record file metadata for the manifest.
    _require_dir(src)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, dst, dirs_exist_ok=True)

    copied = []
    for path in sorted(dst.rglob("*")):
        if path.is_file():
            copied.append({
                "path": _manifest_path(path, manifest_base),
                "bytes": path.stat().st_size,
                "sha256": _sha256(path),
            })
    return copied


def sync_google_review_data(
    source_repo: Path | None = None,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
) -> dict[str, object]:
    # Only sync the review-analysis folders that this repo actually consumes.
    source_repo = source_repo or default_source_repo()
    copied_files: list[dict[str, object]] = []
    manifest_base = output_root.parent
    for relative_dir in SYNC_DIRS:
        copied_files.extend(_copy_dir(
            source_repo / relative_dir,
            output_root / relative_dir.name,
            manifest_base,
        ))

    manifest = {
        "source_repo": str(source_repo),
        "synced_dirs": [str(path) for path in SYNC_DIRS],
        "skipped": ["output/official_fukui", "output/hokuriku_merged", "survey outputs"],
        "files": copied_files,
    }
    manifest_path = output_root / "google_review_sync_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-repo", type=Path, default=None)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        manifest = sync_google_review_data(args.source_repo, args.output_root)
    except SyncInputError as error:
        print(error)
        return 1
    print(f"Synced {len(manifest['files'])} Google review files from {manifest['source_repo']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
