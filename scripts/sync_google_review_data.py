#!/usr/bin/env python3
"""
Validate local Google review artifacts from sibling platform-review-scraper.

This does not copy data. It checks required checkpoint and multilingual review
inputs in the sibling checkout, records provenance hashes, and fails loudly on
missing inputs.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from src.provenance import file_record, research_manifest, sha256_file, write_json
from src.platform_review_inputs import (
    PlatformReviewInputError,
    platform_review_required_inputs,
    require_platform_review_inputs,
    resolve_platform_review_paths,
)

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_ROOT = ROOT / "output"


def validate_platform_review_data(
    scraper_dir: Path | None = None,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
) -> dict[str, object]:
    # Read-only validation. Source files remain in platform-review-scraper.
    paths = resolve_platform_review_paths(scraper_dir=scraper_dir)
    require_platform_review_inputs(paths)
    output_root.mkdir(parents=True, exist_ok=True)

    required_inputs = platform_review_required_inputs(paths)
    validated_files = []
    for role, path in required_inputs.items():
        validated_files.append({
            "role": role,
            "path": str(path),
            "exists": path.exists(),
            "bytes": path.stat().st_size if path.is_file() else None,
            "sha256": sha256_file(path) if path.is_file() else None,
        })

    manifest = {
        "schema_version": "google_review_input_validation.v1",
        "platform_review_scraper_dir": str(paths.scraper_dir),
        "project_dir": str(paths.project_dir),
        "validated_files": validated_files,
    }
    manifest_path = output_root / "google_review_input_validation.json"
    manifest["provenance"] = research_manifest(
        kind="google_review_input_validation",
        command=None,
        inputs=[
            file_record(path, role, required=True)
            for role, path in required_inputs.items()
        ],
        outputs=[
            file_record(manifest_path, "google_review_input_validation_manifest"),
        ],
        metrics={
            "files_validated": len(validated_files),
            "platform_review_scraper_dir": str(paths.scraper_dir),
        },
        caveats=[
            "No Google review data copied into Hokuriku repo.",
            "Source files remain read-only in platform-review-scraper.",
        ],
    )
    write_json(manifest_path, manifest)
    return manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform-review-scraper-dir", type=Path, default=None)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        manifest = validate_platform_review_data(args.platform_review_scraper_dir, args.output_root)
    except PlatformReviewInputError as error:
        print(error)
        return 1
    print(
        f"Validated {len(manifest['validated_files'])} Google review inputs from "
        f"{manifest['platform_review_scraper_dir']}"
    )
    return 0


sync_google_review_data = validate_platform_review_data


if __name__ == "__main__":
    raise SystemExit(main())
