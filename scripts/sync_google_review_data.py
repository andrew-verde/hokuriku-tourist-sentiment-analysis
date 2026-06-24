#!/usr/bin/env python3
"""
Sync local Google review artifacts from the source english-fukui-tourism repo.

This copies only Google review collection checkpoints and multilingual review
analysis outputs. It intentionally skips official survey outputs.
"""

from __future__ import annotations

import argparse
import os
import shutil
from pathlib import Path

from src.provenance import file_record, research_manifest, sha256_file, write_json

# This script pulls pre-processed Google review data (checkpoints and multilingual
# analysis outputs) from a sibling repository and copies them locally. It then
# records the sync metadata (file hashes, counts, lineage) into a manifest JSON
# so the analysis pipeline can trace where its input data came from.

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
    # Determine where the source repository lives. First check for an environment
    # variable override, then try known local paths, defaulting to the first option.
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
    return sha256_file(path)


def _manifest_path(path: Path, base: Path) -> str:
    try:
        return str(path.relative_to(base))
    except ValueError:
        return str(path)


def _copy_dir(src: Path, dst: Path, manifest_base: Path) -> list[dict[str, object]]:
    # Copy the entire directory tree from source to destination, then compute
    # and record file metadata (size, SHA256 hash) for each copied file so the
    # manifest can verify data integrity later.
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
    # Copy the designated review-analysis folders from the source repo and build
    # a provenance manifest that records what was synced, from where, and the
    # integrity hash of every file so downstream steps can verify the data.
    source_repo = source_repo or default_source_repo()
    copied_files: list[dict[str, object]] = []
    manifest_base = output_root.parent
    for relative_dir in SYNC_DIRS:
        copied_files.extend(_copy_dir(
            source_repo / relative_dir,
            output_root / relative_dir.name,
            manifest_base,
        ))

    # Build the manifest that documents this sync operation for the research record.
    manifest = {
        "schema_version": "google_review_sync_manifest.v2",
        "source_repo": str(source_repo),
        "synced_dirs": [str(path) for path in SYNC_DIRS],
        "skipped": ["output/official_fukui", "output/hokuriku_merged", "survey outputs"],
        "files": copied_files,
    }
    # Attach provenance metadata so every output traces back to its source data.
    manifest["provenance"] = research_manifest(
        kind="google_review_sync",
        command=None,
        inputs=[
            file_record(source_repo / relative_dir, f"source_{relative_dir.as_posix()}", required=True)
            for relative_dir in SYNC_DIRS
        ],
        outputs=[
            file_record(output_root / relative_dir.name, f"synced_{relative_dir.name}", required=True)
            for relative_dir in SYNC_DIRS
        ],
        metrics={
            "files_synced": len(copied_files),
            "synced_dirs": [str(path) for path in SYNC_DIRS],
        },
        caveats=[
            "Only Google review checkpoints and multilingual review analysis outputs are synced.",
            "Official survey outputs are skipped.",
        ],
    )
    # Write the manifest to a JSON file for inspection and downstream verification.
    manifest_path = output_root / "google_review_sync_manifest.json"
    write_json(manifest_path, manifest)
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
