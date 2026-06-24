#!/usr/bin/env python3
"""Shared helpers for aggregate-only JP/EN hypothesis test scripts.

This module provides utilities for hypothesis testing comparing English-language
and Japanese-language Google reviews from Fukui. It includes data loading,
multiple-comparison corrections (Holm and Benjamini-Hochberg), effect size
calculations, and provenance tracking for reproducibility.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from importlib import metadata
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INPUT_PATH = ROOT / "output" / "sentiment_row_level" / "google_reviews_fukui_japanese-english.csv"
DEFAULT_OUTPUT_DIR = ROOT / "output" / "hypothesis_tests"
DEFAULT_GROUPS = ("english", "japanese")

FORBIDDEN_AGGREGATE_COLUMNS = {
    "review_text",
    "text_content",
    "review_author",
    "author",
    "author_url",
    "note_url",
    "source_url",
    "url",
    "place_id",
    "poi_id",
    "review_id",
    "source_review_id",
    "source_record_id",
}

COMMON_CAVEATS = [
    "Group labels describe review language, not reviewer nationality.",
    "Fukui Google review rows are nested in POIs; row-level p-values are descriptive without a clustered model.",
    "English-language and Japanese-language review counts may be imbalanced.",
    "Outputs are aggregate-only and omit row-level text, author fields, URLs, source IDs, review IDs, place IDs, and POI IDs.",
]


class HypothesisTestError(RuntimeError):
    """Base error for hypothesis scripts."""


class MissingInputError(HypothesisTestError):
    """Raised when a required input file is absent."""


class MissingColumnsError(HypothesisTestError):
    """Raised when a required input column is absent."""


class MissingGroupError(HypothesisTestError):
    """Raised when English/Japanese groups are absent after load."""


def default_command(script_name: str) -> str:
    if sys.argv and Path(sys.argv[0]).name == script_name:
        return " ".join(sys.argv)
    return f".venv/bin/python3 scripts/{script_name}"


def parse_common_args(description: str) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT_PATH)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args()


def load_scored_reviews(path: Path, required_columns: Iterable[str]) -> pd.DataFrame:
    """Load and validate the scored review CSV; filter to English and Japanese rows only.

    Checks that the input file exists, contains all required columns, and has both
    English and Japanese reviews. Standardizes language_group to lowercase.
    """
    if not path.exists():
        raise MissingInputError(
            f"Required scored review input not found: {path}\n"
            "Run `make sentiment-analysis` first. These scripts have no demo mode."
        )
    df = pd.read_csv(path)
    # Verify that all required columns are present in the CSV
    missing = sorted(set(required_columns) - set(df.columns))
    if missing:
        raise MissingColumnsError(f"Required columns missing from {path}: {', '.join(missing)}")
    df = df.copy()
    # Standardize language_group to lowercase for consistent comparison
    df["language_group"] = df["language_group"].astype(str).str.lower()
    # Verify both English and Japanese groups are present
    present = set(df["language_group"].dropna())
    missing_groups = sorted(set(DEFAULT_GROUPS) - present)
    if missing_groups:
        raise MissingGroupError(
            f"Required language_group values missing from {path}: {', '.join(missing_groups)}"
        )
    # Return only rows with English or Japanese language_group
    return df[df["language_group"].isin(DEFAULT_GROUPS)].copy()


def sha256_file(path: Path) -> str:
    from src.provenance import sha256_file as _sha256_file

    return _sha256_file(path)


def generated_at() -> str:
    from src.provenance import utc_now_iso

    return utc_now_iso()


def dependency_versions() -> dict[str, str]:
    versions = {}
    for package in ["pandas", "numpy", "scipy"]:
        try:
            versions[package] = metadata.version(package)
        except metadata.PackageNotFoundError:
            versions[package] = "missing"
    return versions


def assert_safe_aggregate(df: pd.DataFrame, context: str) -> None:
    from src.provenance import ProvenanceError, assert_no_forbidden_columns

    try:
        assert_no_forbidden_columns(df.columns, FORBIDDEN_AGGREGATE_COLUMNS, context)
    except ProvenanceError as error:
        raise HypothesisTestError(str(error)) from error


def group_denominators(df: pd.DataFrame) -> dict[str, int]:
    """Count the number of reviews in each language group (English and Japanese).

    These counts are the sample sizes (denominators) used throughout the analyses.
    """
    return {
        language: int((df["language_group"] == language).sum())
        for language in DEFAULT_GROUPS
    }


def holm_adjust(p_values: list[float | None]) -> list[float | None]:
    """Apply Holm step-down multiple-comparison correction to a list of p-values.

    The Holm method controls the family-wise error rate by sequentially adjusting
    p-values in order, starting with the smallest. It is more powerful than
    Bonferroni while maintaining strong control. Missing or None values are
    preserved in their original positions.
    """
    indexed = [
        (index, float(value))
        for index, value in enumerate(p_values)
        if value is not None and not pd.isna(value)
    ]
    adjusted: list[float | None] = [None] * len(p_values)
    if not indexed:
        return adjusted
    # Sort p-values in ascending order, keeping track of original indices
    indexed.sort(key=lambda item: item[1])
    m = len(indexed)
    running = 0.0
    # Apply Holm correction: multiply each p-value by (m - rank), enforcing monotonicity
    for rank, (index, p_value) in enumerate(indexed):
        value = min(1.0, (m - rank) * p_value)
        running = max(running, value)
        adjusted[index] = running
    return adjusted


def benjamini_hochberg(p_values: list[float | None]) -> list[float | None]:
    """Apply Benjamini-Hochberg False Discovery Rate (FDR) correction.

    This method controls the expected proportion of false positives among
    rejected hypotheses (FDR) rather than the family-wise error rate. It is
    less conservative than Holm when testing many hypotheses. Missing or None
    values are preserved in their original positions.
    """
    indexed = [
        (index, float(value))
        for index, value in enumerate(p_values)
        if value is not None and not pd.isna(value)
    ]
    adjusted: list[float | None] = [None] * len(p_values)
    if not indexed:
        return adjusted
    # Sort p-values in descending order for FDR adjustment (processed from largest to smallest)
    indexed.sort(key=lambda item: item[1], reverse=True)
    m = len(indexed)
    running = 1.0
    # Apply Benjamini-Hochberg correction: multiply each p-value by m/rank, enforcing monotonicity
    for reverse_rank, (index, p_value) in enumerate(indexed):
        rank = m - reverse_rank
        running = min(running, (p_value * m) / rank)
        adjusted[index] = min(1.0, running)
    return adjusted


def safe_float(value: object) -> float | None:
    """Safely convert a value to float, returning None if conversion fails or result is NaN/Inf.

    Handles type errors, value errors, and invalid numbers gracefully.
    """
    if value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    # Exclude NaN and infinity from results
    if math.isnan(result) or math.isinf(result):
        return None
    return result


def write_manifest(
    *,
    kind: str,
    command: str,
    generated: str,
    input_path: Path,
    output_csv: Path,
    manifest_path: Path,
    metrics: dict,
    caveats: list[str],
) -> dict:
    from src.provenance import file_record, research_manifest, write_json

    manifest = research_manifest(
        kind=kind,
        command=command,
        generated_at=generated,
        filters={"prefecture": "Fukui", "groups": list(DEFAULT_GROUPS)},
        inputs=[file_record(input_path, "ignored_scored_review_audit_file", required=True)],
        outputs=[file_record(output_csv, "tracked_hypothesis_test_csv", required=True)],
        metrics=metrics,
        caveats=caveats,
        extra={"dependency_versions": dependency_versions()},
    )
    write_json(manifest_path, manifest)
    return manifest


def write_csv(df: pd.DataFrame, path: Path) -> None:
    """Write a DataFrame to CSV, ensuring no forbidden (non-aggregate) columns are present.

    Forbidden columns include review text, author info, URLs, and IDs that would
    violate data privacy/aggregation policies.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    # Verify the DataFrame contains only aggregate-safe columns before writing
    assert_safe_aggregate(df, str(path))
    df.to_csv(path, index=False)
