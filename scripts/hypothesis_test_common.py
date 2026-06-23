#!/usr/bin/env python3
"""Shared helpers for aggregate-only JP/EN hypothesis test scripts."""

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
    if not path.exists():
        raise MissingInputError(
            f"Required scored review input not found: {path}\n"
            "Run `make sentiment-analysis` first. These scripts have no demo mode."
        )
    df = pd.read_csv(path)
    missing = sorted(set(required_columns) - set(df.columns))
    if missing:
        raise MissingColumnsError(f"Required columns missing from {path}: {', '.join(missing)}")
    df = df.copy()
    df["language_group"] = df["language_group"].astype(str).str.lower()
    present = set(df["language_group"].dropna())
    missing_groups = sorted(set(DEFAULT_GROUPS) - present)
    if missing_groups:
        raise MissingGroupError(
            f"Required language_group values missing from {path}: {', '.join(missing_groups)}"
        )
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
    return {
        language: int((df["language_group"] == language).sum())
        for language in DEFAULT_GROUPS
    }


def holm_adjust(p_values: list[float | None]) -> list[float | None]:
    indexed = [
        (index, float(value))
        for index, value in enumerate(p_values)
        if value is not None and not pd.isna(value)
    ]
    adjusted: list[float | None] = [None] * len(p_values)
    if not indexed:
        return adjusted
    indexed.sort(key=lambda item: item[1])
    m = len(indexed)
    running = 0.0
    for rank, (index, p_value) in enumerate(indexed):
        value = min(1.0, (m - rank) * p_value)
        running = max(running, value)
        adjusted[index] = running
    return adjusted


def benjamini_hochberg(p_values: list[float | None]) -> list[float | None]:
    indexed = [
        (index, float(value))
        for index, value in enumerate(p_values)
        if value is not None and not pd.isna(value)
    ]
    adjusted: list[float | None] = [None] * len(p_values)
    if not indexed:
        return adjusted
    indexed.sort(key=lambda item: item[1], reverse=True)
    m = len(indexed)
    running = 1.0
    for reverse_rank, (index, p_value) in enumerate(indexed):
        rank = m - reverse_rank
        running = min(running, (p_value * m) / rank)
        adjusted[index] = min(1.0, running)
    return adjusted


def safe_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
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
    path.parent.mkdir(parents=True, exist_ok=True)
    assert_safe_aggregate(df, str(path))
    df.to_csv(path, index=False)
