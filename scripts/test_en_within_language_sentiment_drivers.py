#!/usr/bin/env python3
"""
WL-EN: within-English Google review sentiment driver tests.

Analyzes English-language Fukui Google reviews to test whether sentiment scores
(VADER compound score) and sentiment prevalence (positive/neutral/negative category)
are associated with review content indicators: friction evidence, enjoyment evidence,
recommendation evidence, and positive evidence. Also examines convergent validity
(whether text sentiment tracks with star rating) and descriptive differences across
POI categories. All statistical tests are row-level (reviews nested in venues) with
p-values reported descriptively; no clustered model is applied.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.provenance import repo_relative
from scripts.within_language_sentiment_common import (
    COMMON_WITHIN_CAVEATS,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_REVIEW_INPUT_PATH,
    apply_bh,
    binary_event_row,
    default_command,
    generated_at as generated_at_now,
    kruskal_row,
    load_csv_fail_loud,
    parse_args,
    score_by_binary_row,
    sha256_file,
    spearman_row,
    write_csv,
    write_manifest,
)

SCRIPT_NAME = "test_en_within_language_sentiment_drivers.py"
OUTPUT_CSV = "en_within_language_sentiment_drivers.csv"
OUTPUT_MANIFEST = "en_within_language_sentiment_manifest.json"
LANGUAGE = "english"
LANGUAGE_LABEL = "English-language Fukui Google reviews"
SCORE_COLUMN = "sentiment_score"
REQUIRED_COLUMNS = {
    "language_group",
    "sentiment_score",
    "sentiment_category",
    "any_friction",
    "any_enjoyment_evidence",
    "any_recommendation_evidence",
    "any_positive_evidence",
    "review_rating",
    "poi_category",
    "poi_id",
    "text_length_chars",
}
CAVEATS = COMMON_WITHIN_CAVEATS + [
    "English sentiment_score is VADER compound and is interpreted within English only; it is not compared as a raw scale to oseti or SnowNLP.",
    "Google review rows are nested in POIs; row-level p-values are descriptive without a clustered model.",
]


def _repo_relative_path(path: Path) -> Path:
    return Path(repo_relative(path))


def build_en_within_language_sentiment_drivers(
    input_path: Path = DEFAULT_REVIEW_INPUT_PATH,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    command: str | None = None,
) -> dict:
    """
    Parse English-language reviews, run sentiment driver tests, and write outputs.

    Filters the input CSV to Fukui prefecture and English-language reviews, then
    invokes a series of statistical tests to examine associations between sentiment
    and review content indicators.
    """
    # Load the CSV and validate required columns
    df = load_csv_fail_loud(input_path, REQUIRED_COLUMNS, "make sentiment-analysis")
    # Normalize language_group to lowercase for consistent comparison
    df["language_group"] = df["language_group"].astype(str).str.lower()
    # Filter to Fukui prefecture if the column is present
    if "prefecture_normalized" in df.columns:
        df = df[df["prefecture_normalized"].astype(str).eq("Fukui")].copy()
    # Filter to English-language reviews only
    df = df[df["language_group"].eq(LANGUAGE)].copy()
    command = command or default_command(SCRIPT_NAME)
    generated = generated_at_now()
    source_hash = sha256_file(input_path)
    caveat = "; ".join(CAVEATS)

    rows = _review_rows(df, _repo_relative_path(input_path), source_hash, command, generated, caveat)
    out = pd.DataFrame(rows)
    output_csv = output_dir / OUTPUT_CSV
    output_manifest = output_dir / OUTPUT_MANIFEST
    write_csv(out, output_csv)
    manifest = write_manifest(
        kind="within_language_sentiment_drivers_en",
        command=command,
        generated=generated,
        input_path=_repo_relative_path(input_path),
        output_csv=output_csv,
        manifest_path=output_manifest,
        filters={"prefecture": "Fukui", "language_group": LANGUAGE},
        metrics={
            "analysis_family": "WL-EN",
            "primary_unit": "one Fukui English-language Google review row",
            "denominators": {"english": int(len(df))},
            "score": "VADER compound via sentiment_score, interpreted within English only",
            "multiple_testing": "Benjamini-Hochberg FDR within evidence predictors.",
        },
        caveats=CAVEATS,
        input_role="ignored_scored_review_audit_file",
    )
    return {"csv": str(output_csv), "manifest": str(output_manifest), "rows": len(out), "provenance": manifest}


def _review_rows(df: pd.DataFrame, input_path: Path, source_hash: str, command: str, generated: str, caveat: str) -> list[dict]:
    """
    Run statistical tests on English-language review sentiment and its drivers.

    Tests are grouped into families for multiple-testing correction (Benjamini-Hochberg FDR):
    - Evidence predictors: friction, enjoyment, recommendation, positive evidence
    - Convergent validity: text sentiment vs. star rating
    - Descriptive diagnostics: POI category differences (not FDR-corrected globally)
    """
    # WL-EN-1: Does friction evidence predict lower sentiment?
    rows = [
        # Mann-Whitney U test: VADER sentiment score when friction present vs. absent
        score_by_binary_row(
            df=df,
            analysis_id="WL-EN-1",
            research_question="Do English-language Google reviews with friction evidence show lower VADER sentiment?",
            language_source_group=LANGUAGE_LABEL,
            outcome=SCORE_COLUMN,
            predictor="any_friction",
            expected_direction="lower when true",
            unit="one English-language Fukui Google review row",
            source_input_path=input_path,
            source_input_sha256=source_hash,
            command=command,
            generated=generated,
            caveat=caveat,
            multiple_testing_family="english_evidence_predictors",
        ),
        # Chi-square/Fisher test: positive sentiment category when friction present vs. absent
        binary_event_row(
            df=df,
            analysis_id="WL-EN-1",
            research_question="Do English-language Google reviews with friction evidence have lower positive sentiment prevalence?",
            language_source_group=LANGUAGE_LABEL,
            outcome="sentiment_category",
            predictor="any_friction",
            positive_event="positive",
            unit="one English-language Fukui Google review row",
            source_input_path=input_path,
            source_input_sha256=source_hash,
            command=command,
            generated=generated,
            caveat=caveat,
            multiple_testing_family="english_evidence_predictors",
        ),
    ]
    # WL-EN-2: Do enjoyment, recommendation, and positive evidence each predict higher sentiment?
    for predictor in ["any_enjoyment_evidence", "any_recommendation_evidence", "any_positive_evidence"]:
        rows.append(score_by_binary_row(
            df=df,
            analysis_id="WL-EN-2",
            research_question=f"Do English-language Google reviews with {predictor} show higher VADER sentiment?",
            language_source_group=LANGUAGE_LABEL,
            outcome=SCORE_COLUMN,
            predictor=predictor,
            expected_direction="higher when true",
            unit="one English-language Fukui Google review row",
            source_input_path=input_path,
            source_input_sha256=source_hash,
            command=command,
            generated=generated,
            caveat=caveat,
            multiple_testing_family="english_evidence_predictors",
        ))
        rows.append(binary_event_row(
            df=df,
            analysis_id="WL-EN-2",
            research_question=f"Do English-language Google reviews with {predictor} have higher positive sentiment prevalence?",
            language_source_group=LANGUAGE_LABEL,
            outcome="sentiment_category",
            predictor=predictor,
            positive_event="positive",
            unit="one English-language Fukui Google review row",
            source_input_path=input_path,
            source_input_sha256=source_hash,
            command=command,
            generated=generated,
            caveat=caveat,
            multiple_testing_family="english_evidence_predictors",
        ))
    # WL-EN-3: Convergent validity - Spearman correlation between text sentiment and star rating
    rows.append(spearman_row(
        df=df,
        analysis_id="WL-EN-3",
        research_question="Does English-language text sentiment track Google star rating?",
        language_source_group=LANGUAGE_LABEL,
        score_column=SCORE_COLUMN,
        predictor="review_rating",
        unit="one English-language Fukui Google review row",
        source_input_path=input_path,
        source_input_sha256=source_hash,
        command=command,
        generated=generated,
        caveat=caveat,
    ))
    # WL-EN-4: Descriptive - Kruskal-Wallis test for differences in sentiment across POI categories
    rows.append(kruskal_row(
        df=df,
        analysis_id="WL-EN-4",
        research_question="Do English-language POI categories differ in VADER sentiment?",
        language_source_group=LANGUAGE_LABEL,
        score_column=SCORE_COLUMN,
        predictor="poi_category",
        unit="one English-language Fukui Google review row",
        min_group_n=3,
        source_input_path=input_path,
        source_input_sha256=source_hash,
        command=command,
        generated=generated,
        caveat=caveat,
        family="english_poi_category_global",
    ))
    # Apply Benjamini-Hochberg False Discovery Rate correction to evidence predictors
    apply_bh(rows, "english_evidence_predictors")
    return rows


def main() -> None:
    args = parse_args(__doc__ or "Run WL-EN within-language sentiment drivers.", DEFAULT_REVIEW_INPUT_PATH)
    print(json.dumps(build_en_within_language_sentiment_drivers(args.input, args.output_dir), indent=2))


if __name__ == "__main__":
    main()
