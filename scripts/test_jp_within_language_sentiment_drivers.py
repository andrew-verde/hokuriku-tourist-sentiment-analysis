#!/usr/bin/env python3
"""
WL-JP: within-Japanese Google review sentiment driver tests.

Mirrors the English-language analysis (WL-EN) but applies it to Japanese-language
Fukui Google reviews using the oseti sentiment score instead of VADER. Examines
associations between sentiment and evidence indicators (friction, enjoyment,
recommendation, positive) and convergent validity with star rating. All tests are
row-level with descriptive p-values (no clustered model).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.provenance import repo_relative
from scripts.within_language_sentiment_common import DEFAULT_OUTPUT_DIR, DEFAULT_REVIEW_INPUT_PATH, parse_args
from scripts.test_en_within_language_sentiment_drivers import CAVEATS as EN_CAVEATS
from scripts.test_en_within_language_sentiment_drivers import REQUIRED_COLUMNS, _review_rows
from scripts.within_language_sentiment_common import (
    COMMON_WITHIN_CAVEATS,
    default_command,
    generated_at as generated_at_now,
    load_csv_fail_loud,
    sha256_file,
    write_csv,
    write_manifest,
)

SCRIPT_NAME = "test_jp_within_language_sentiment_drivers.py"
OUTPUT_CSV = "jp_within_language_sentiment_drivers.csv"
OUTPUT_MANIFEST = "jp_within_language_sentiment_manifest.json"
LANGUAGE = "japanese"
LANGUAGE_LABEL = "Japanese-language Fukui Google reviews"
CAVEATS = COMMON_WITHIN_CAVEATS + [
    "Japanese sentiment_score is oseti document score and is interpreted within Japanese only; it is not compared as a raw scale to VADER or SnowNLP.",
    "Google review rows are nested in POIs; row-level p-values are descriptive without a clustered model.",
]


def _repo_relative_path(path: Path) -> Path:
    return Path(repo_relative(path))


def build_jp_within_language_sentiment_drivers(
    input_path: Path = DEFAULT_REVIEW_INPUT_PATH,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    command: str | None = None,
) -> dict:
    """
    Parse Japanese-language reviews and run sentiment driver tests.

    Reuses the English test logic (_review_rows from the EN script) but adapts
    analysis IDs, labels, and testing families to Japanese. Sentiment is measured
    via oseti (Japanese-specific tool), not VADER.
    """
    # Load and filter to Japanese-language Fukui reviews
    df = load_csv_fail_loud(input_path, REQUIRED_COLUMNS, "make sentiment-analysis")
    df["language_group"] = df["language_group"].astype(str).str.lower()
    if "prefecture_normalized" in df.columns:
        df = df[df["prefecture_normalized"].astype(str).eq("Fukui")].copy()
    df = df[df["language_group"].eq(LANGUAGE)].copy()
    command = command or default_command(SCRIPT_NAME)
    generated = generated_at_now()
    source_hash = sha256_file(input_path)
    caveat = "; ".join(CAVEATS)

    # Run tests using shared logic from English module, then adapt labels for Japanese
    rows = _review_rows(df, _repo_relative_path(input_path), source_hash, command, generated, caveat)
    for row in rows:
        # Replace WL-EN with WL-JP to mark this as a Japanese analysis
        row["analysis_id"] = row["analysis_id"].replace("WL-EN", "WL-JP")
        row["language_source_group"] = LANGUAGE_LABEL
        # Update research question text to reference Japanese and oseti instead of English and VADER
        row["research_question"] = row["research_question"].replace("English-language", "Japanese-language").replace("VADER", "oseti")
        row["unit"] = "one Japanese-language Fukui Google review row"
        # Update testing family names to track that these are Japanese predictors
        row["multiple_testing_family"] = row["multiple_testing_family"].replace("english", "japanese")
        if isinstance(row.get("effect_size_label"), str):
            row["effect_size_label"] = row["effect_size_label"].replace("expected", "expected")
    from scripts.within_language_sentiment_common import apply_bh

    # Apply Benjamini-Hochberg correction within the Japanese evidence predictors family
    apply_bh(rows, "japanese_evidence_predictors")
    out = pd.DataFrame(rows)
    output_csv = output_dir / OUTPUT_CSV
    output_manifest = output_dir / OUTPUT_MANIFEST
    write_csv(out, output_csv)
    manifest = write_manifest(
        kind="within_language_sentiment_drivers_jp",
        command=command,
        generated=generated,
        input_path=_repo_relative_path(input_path),
        output_csv=output_csv,
        manifest_path=output_manifest,
        filters={"prefecture": "Fukui", "language_group": LANGUAGE},
        metrics={
            "analysis_family": "WL-JP",
            "primary_unit": "one Fukui Japanese-language Google review row",
            "denominators": {"japanese": int(len(df))},
            "score": "oseti document score via sentiment_score, interpreted within Japanese only",
            "multiple_testing": "Benjamini-Hochberg FDR within evidence predictors.",
        },
        caveats=CAVEATS,
        input_role="ignored_scored_review_audit_file",
    )
    return {"csv": str(output_csv), "manifest": str(output_manifest), "rows": len(out), "provenance": manifest}


def main() -> None:
    args = parse_args(__doc__ or "Run WL-JP within-language sentiment drivers.", DEFAULT_REVIEW_INPUT_PATH)
    print(json.dumps(build_jp_within_language_sentiment_drivers(args.input, args.output_dir), indent=2))


if __name__ == "__main__":
    main()
