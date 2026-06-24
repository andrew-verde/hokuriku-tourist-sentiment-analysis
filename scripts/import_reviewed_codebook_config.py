#!/usr/bin/env python3
"""Promote completed reviewed JP/EN codebook rows into runtime YAML config."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.reviewed_codebook import (
    ReviewedCodebookError,
    build_runtime_config,
    load_reviewed_codebook_rows,
    validation_status,
)

# This script reads the reviewed codebook spreadsheet (a human-edited Excel file
# with JP/EN keyword decisions), validates it, and exports a YAML config file
# that the sentiment analysis pipeline will consume at runtime.


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SOURCE = ROOT / "docs" / "codebook_reviews" / "source" / "multilingual_keyword_codebook_review.xlsx"
DEFAULT_OUTPUT = ROOT / "config" / "reviewed_jp_en_codebook.yaml"


def parse_languages(raw: str) -> list[str]:
    # Parse comma-separated language names and validate that at least one is provided.
    languages = [part.strip() for part in raw.split(",") if part.strip()]
    if not languages:
        raise ReviewedCodebookError("--languages must name at least one language")
    return languages


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--languages", default="Japanese,English")
    parser.add_argument(
        "--status-only",
        action="store_true",
        help="Print review-completion counts without writing runtime config.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        languages = parse_languages(args.languages)
        # Load rows from the source spreadsheet (Excel or CSV); filter by requested languages.
        rows = load_reviewed_codebook_rows(args.source, sheet_names=languages)
        if args.status_only:
            # User requested a validation report instead of writing the runtime config.
            print(json.dumps(validation_status(rows, languages), ensure_ascii=False, indent=2, sort_keys=True))
            return 0
        # Validate all rows and assemble them into a structured config for runtime use.
        config = build_runtime_config(
            rows,
            source_path=args.source,
            languages=languages,
            command=" ".join(sys.argv),
        )
    except ReviewedCodebookError as error:
        print(error, file=sys.stderr)
        return 1

    # Write the validated config to YAML format for the sentiment analysis pipeline.
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(yaml.safe_dump(config, allow_unicode=True, sort_keys=False), encoding="utf-8")
    print(f"Wrote reviewed codebook runtime config: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
