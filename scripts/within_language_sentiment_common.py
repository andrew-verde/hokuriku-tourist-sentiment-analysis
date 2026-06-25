#!/usr/bin/env python3
"""
Shared helpers for aggregate-only within-language sentiment driver scripts.

This module provides reusable statistical analysis functions and data-handling
utilities for within-language sentiment analysis across English, Japanese, and
Chinese reviews. It runs Mann-Whitney U tests (nonparametric comparison of
sentiment scores between two groups), chi-square and Fisher's exact tests
(for categorical sentiment outcomes), Spearman rank correlation (sentiment
vs. rating), and Kruskal-Wallis tests (comparing sentiment across multiple
categories). All outputs are aggregated at the review-level or above with
no row-level text or identifiers exposed.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd
from scipy import stats

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_REVIEW_INPUT_PATH = ROOT / "output" / "sentiment_row_level" / "google_reviews_fukui_japanese-english.csv"
DEFAULT_CHINESE_INPUT_PATH = ROOT / "output" / "chinese_social_media_analysis" / "tagged_chinese_social_posts.csv"
DEFAULT_OUTPUT_DIR = ROOT / "output" / "within_language_sentiment"
CATEGORY_ORDER = ["negative", "neutral", "positive"]
TRUE_VALUES = {"true", "1", "yes", "y", "t"}

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
    "title",
}

COMMON_WITHIN_CAVEATS = [
    "Group labels describe content language/source, not author or reviewer nationality.",
    "Raw sentiment scores are interpreted only within one tool, language, and source.",
    "Outputs are aggregate-only and omit row-level text, author fields, URLs, source IDs, review IDs, place IDs, and POI IDs.",
]


class WithinLanguageError(RuntimeError):
    """Base error for within-language sentiment scripts."""


class MissingInputError(WithinLanguageError):
    """Raised when required input file is absent."""


class MissingColumnsError(WithinLanguageError):
    """Raised when required input columns are absent."""


def default_command(script_name: str) -> str:
    if sys.argv and Path(sys.argv[0]).name == script_name:
        return " ".join(sys.argv)
    return f".venv/bin/python3 scripts/{script_name}"


def parse_args(description: str, default_input: Path) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--input", type=Path, default=default_input)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args()


def load_csv_fail_loud(path: Path, required_columns: Iterable[str], producer: str) -> pd.DataFrame:
    if not path.exists():
        raise MissingInputError(
            f"Required within-language sentiment input not found: {path}\n"
            f"Run `{producer}` first. These scripts have no demo mode."
        )
    df = pd.read_csv(path)
    missing = sorted(set(required_columns) - set(df.columns))
    if missing:
        raise MissingColumnsError(f"Required columns missing from {path}: {', '.join(missing)}")
    return df.copy()


def sha256_file(path: Path) -> str:
    from src.provenance import sha256_file as _sha256_file

    return _sha256_file(path)


def generated_at() -> str:
    from src.provenance import utc_now_iso

    return utc_now_iso()


def dependency_versions() -> dict[str, str]:
    from scripts.hypothesis_test_common import dependency_versions as _dependency_versions

    return _dependency_versions()


def assert_safe_aggregate(df: pd.DataFrame, context: str) -> None:
    from src.provenance import ProvenanceError, assert_no_forbidden_columns

    try:
        assert_no_forbidden_columns(df.columns, FORBIDDEN_AGGREGATE_COLUMNS, context)
    except ProvenanceError as error:
        raise WithinLanguageError(str(error)) from error


def write_csv(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    assert_safe_aggregate(df, str(path))
    df.to_csv(path, index=False)


def write_manifest(
    *,
    kind: str,
    command: str,
    generated: str,
    input_path: Path,
    output_csv: Path,
    manifest_path: Path,
    filters: dict,
    metrics: dict,
    caveats: list[str],
    input_role: str,
) -> dict:
    from src.provenance import file_record, research_manifest, write_json

    manifest = research_manifest(
        kind=kind,
        command=command,
        generated_at=generated,
        filters=filters,
        inputs=[file_record(input_path, input_role, required=True)],
        outputs=[file_record(output_csv, "tracked_within_language_sentiment_csv", required=True)],
        metrics=metrics,
        caveats=caveats,
        extra={"dependency_versions": dependency_versions()},
    )
    write_json(manifest_path, manifest)
    return manifest


def bool_series(series: pd.Series) -> pd.Series:
    if series.dtype == bool:
        return series.fillna(False)
    return series.fillna(False).astype(str).str.strip().str.lower().isin(TRUE_VALUES)


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


def benjamini_hochberg(p_values: list[float | None]) -> list[float | None]:
    from scripts.hypothesis_test_common import benjamini_hochberg as _benjamini_hochberg

    return _benjamini_hochberg(p_values)


def numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def cliffs_delta(left: np.ndarray, right: np.ndarray) -> float | None:
    if len(left) == 0 or len(right) == 0:
        return None
    greater = 0
    less = 0
    for value in left:
        greater += int(np.sum(value > right))
        less += int(np.sum(value < right))
    return float((greater - less) / (len(left) * len(right)))


def score_by_binary_row(
    *,
    df: pd.DataFrame,
    analysis_id: str,
    research_question: str,
    language_source_group: str,
    outcome: str,
    predictor: str,
    expected_direction: str,
    unit: str,
    source_input_path: Path,
    source_input_sha256: str,
    command: str,
    generated: str,
    caveat: str,
    multiple_testing_family: str,
) -> dict:
    """
    Run a Mann-Whitney U test comparing sentiment scores between two groups.

    Tests whether sentiment scores differ between rows where a binary predictor
    is true vs. false (e.g., does "friction present" predict lower sentiment?).
    The Mann-Whitney U is a nonparametric rank test suitable for non-normal
    sentiment distributions.
    """
    present_mask = bool_series(df[predictor])
    scores = numeric(df[outcome])
    # Drop missing values for a clean comparison
    work = pd.DataFrame({"present": present_mask, "score": scores}).dropna()
    present = work.loc[work["present"], "score"].to_numpy(dtype=float)
    absent = work.loc[~work["present"], "score"].to_numpy(dtype=float)
    base = _base_row(
        analysis_id,
        research_question,
        outcome,
        predictor,
        unit,
        language_source_group,
        source_input_path,
        source_input_sha256,
        command,
        generated,
        caveat,
        multiple_testing_family,
    )
    row = {
        **base,
        "analysis_type": "score_by_binary_predictor",
        "test_name": "mann_whitney_u_sentiment_score",
        "n": int(len(work)),
        "group_a": f"{predictor}=true",
        "group_b": f"{predictor}=false",
        "group_a_n": int(len(present)),
        "group_b_n": int(len(absent)),
        "group_a_score_mean": safe_float(np.mean(present)) if len(present) else None,
        "group_b_score_mean": safe_float(np.mean(absent)) if len(absent) else None,
        "group_a_score_median": safe_float(np.median(present)) if len(present) else None,
        "group_b_score_median": safe_float(np.median(absent)) if len(absent) else None,
        "group_a_event_count": None,
        "group_b_event_count": None,
        "group_a_event_pct": None,
        "group_b_event_pct": None,
        "statistic": None,
        "p_value": None,
        "p_value_bh_fdr": None,
        "effect_size": None,
        "effect_size_label": f"mean_score_difference_true_minus_false; expected {expected_direction}",
        "ci_95_lower": None,
        "ci_95_upper": None,
        "min_expected_count": None,
        "sparse_cell_warning": None,
        "details_json": json.dumps({"score_scale": "within-tool only"}, ensure_ascii=False),
    }
    if len(present) == 0 or len(absent) == 0:
        row["status"] = "skipped"
        row["details_json"] = json.dumps({"reason": "predictor has fewer than two observed groups"})
        return row
    # Perform Mann-Whitney U test (nonparametric test comparing two independent groups).
    # Null hypothesis: the distributions of sentiment scores are equal for both groups.
    # A low p-value indicates the predictor is associated with meaningful sentiment differences.
    result = stats.mannwhitneyu(present, absent, alternative="two-sided")
    row.update({
        "status": "ok",
        "statistic": safe_float(result.statistic),
        "p_value": safe_float(result.pvalue),
        "effect_size": safe_float(np.mean(present) - np.mean(absent)),
        "details_json": json.dumps({
            "effect": "mean score for predictor=true minus predictor=false",
            "cliffs_delta_true_vs_false": cliffs_delta(present, absent),
            "score_scale": "within-tool only",
        }, ensure_ascii=False),
    })
    return row


def binary_event_row(
    *,
    df: pd.DataFrame,
    analysis_id: str,
    research_question: str,
    language_source_group: str,
    outcome: str,
    predictor: str,
    positive_event: str,
    unit: str,
    source_input_path: Path,
    source_input_sha256: str,
    command: str,
    generated: str,
    caveat: str,
    multiple_testing_family: str,
) -> dict:
    """
    Test whether a binary predictor is associated with a categorical outcome.

    For example, is the presence of "friction evidence" associated with lower
    positive sentiment prevalence? Uses chi-square test (when cell counts are
    adequate, n >= 5) or Fisher's exact test (when counts are sparse).
    """
    predictor_present = bool_series(df[predictor])
    event = df[outcome].astype(str).str.lower().eq(positive_event)
    # Create a 2x2 contingency table (predictor: true/false vs. outcome: event present/absent)
    work = pd.DataFrame({"present": predictor_present, "event": event}).dropna()
    table = pd.crosstab(work["present"], work["event"]).reindex(index=[True, False], columns=[True, False], fill_value=0)
    base = _base_row(
        analysis_id,
        research_question,
        f"{outcome}={positive_event}",
        predictor,
        unit,
        language_source_group,
        source_input_path,
        source_input_sha256,
        command,
        generated,
        caveat,
        multiple_testing_family,
    )
    true_n = int(table.loc[True].sum())
    false_n = int(table.loc[False].sum())
    true_events = int(table.loc[True, True])
    false_events = int(table.loc[False, True])
    row = {
        **base,
        "analysis_type": "category_event_by_binary_predictor",
        "test_name": "fisher_exact_sentiment_event" if min(true_n, false_n) else "sentiment_event_by_binary_predictor",
        "n": int(len(work)),
        "group_a": f"{predictor}=true",
        "group_b": f"{predictor}=false",
        "group_a_n": true_n,
        "group_b_n": false_n,
        "group_a_score_mean": None,
        "group_b_score_mean": None,
        "group_a_score_median": None,
        "group_b_score_median": None,
        "group_a_event_count": true_events,
        "group_b_event_count": false_events,
        "group_a_event_pct": round(true_events / true_n, 6) if true_n else None,
        "group_b_event_pct": round(false_events / false_n, 6) if false_n else None,
        "statistic": None,
        "p_value": None,
        "p_value_bh_fdr": None,
        "effect_size": None,
        "effect_size_label": "risk_difference_true_minus_false",
        "ci_95_lower": None,
        "ci_95_upper": None,
        "min_expected_count": None,
        "sparse_cell_warning": None,
        "details_json": json.dumps({"observed": table.to_dict()}, ensure_ascii=False),
    }
    if true_n == 0 or false_n == 0:
        row["status"] = "skipped"
        row["details_json"] = json.dumps({"reason": "predictor has fewer than two observed groups"})
        return row
    # Check expected cell frequencies for test appropriateness
    chi2, chi_p, _, expected = stats.chi2_contingency(table)
    min_expected = float(np.min(expected))
    row["min_expected_count"] = min_expected
    row["sparse_cell_warning"] = bool(min_expected < 5)
    # Choose appropriate test: if any expected cell count is below 5, use Fisher's exact test.
    # Otherwise use chi-square test. Both test the null hypothesis that the two variables
    # (predictor and outcome) are independent.
    if min_expected < 5:
        odds_ratio, p_value = stats.fisher_exact(table, alternative="two-sided")
        row["test_name"] = "fisher_exact_sentiment_event"
        row["statistic"] = safe_float(odds_ratio)
        row["p_value"] = safe_float(p_value)
    else:
        row["test_name"] = "chi_square_sentiment_event"
        row["statistic"] = safe_float(chi2)
        row["p_value"] = safe_float(chi_p)
    row["status"] = "ok"
    row["effect_size"] = (true_events / true_n) - (false_events / false_n)
    row["details_json"] = json.dumps({
        "observed": table.to_dict(),
        "expected": np.round(expected, 6).tolist(),
        "event": positive_event,
    }, ensure_ascii=False)
    return row


def spearman_row(
    *,
    df: pd.DataFrame,
    analysis_id: str,
    research_question: str,
    language_source_group: str,
    score_column: str,
    predictor: str,
    unit: str,
    source_input_path: Path,
    source_input_sha256: str,
    command: str,
    generated: str,
    caveat: str,
) -> dict:
    """
    Compute Spearman rank correlation between a continuous outcome and predictor.

    Tests whether two numeric variables are monotonically related (e.g., does
    sentiment score track with star rating?). Spearman's rho is the correlation
    of ranks, making it robust to outliers and nonlinearity.
    """
    # Drop rows where either variable is missing, then convert both to numeric
    work = pd.DataFrame({"score": numeric(df[score_column]), "predictor": numeric(df[predictor])}).dropna()
    base = _base_row(
        analysis_id,
        research_question,
        score_column,
        predictor,
        unit,
        language_source_group,
        source_input_path,
        source_input_sha256,
        command,
        generated,
        caveat,
        "rating_validity_global",
    )
    row = {
        **base,
        "analysis_type": "association",
        "test_name": "spearman_score_rating",
        "status": "skipped",
        "n": int(len(work)),
        "group_a": None,
        "group_b": None,
        "group_a_n": None,
        "group_b_n": None,
        "group_a_score_mean": None,
        "group_b_score_mean": None,
        "group_a_score_median": None,
        "group_b_score_median": None,
        "group_a_event_count": None,
        "group_b_event_count": None,
        "group_a_event_pct": None,
        "group_b_event_pct": None,
        "statistic": None,
        "p_value": None,
        "p_value_bh_fdr": None,
        "effect_size": None,
        "effect_size_label": "spearman_rho",
        "ci_95_lower": None,
        "ci_95_upper": None,
        "min_expected_count": None,
        "sparse_cell_warning": None,
        "details_json": json.dumps({"reason": "fewer than 3 paired values"}),
    }
    if len(work) < 3 or work["score"].nunique() < 2 or work["predictor"].nunique() < 2:
        return row
    # Perform Spearman rank correlation. Null hypothesis: rho = 0 (no rank correlation).
    # A low p-value indicates a significant monotonic relationship.
    result = stats.spearmanr(work["score"], work["predictor"], nan_policy="omit")
    row.update({
        "status": "ok",
        "statistic": safe_float(result.statistic),
        "p_value": safe_float(result.pvalue),
        "effect_size": safe_float(result.statistic),
        "details_json": json.dumps({"interpretation": "within-language convergent validity check"}),
    })
    return row


def kruskal_row(
    *,
    df: pd.DataFrame,
    analysis_id: str,
    research_question: str,
    language_source_group: str,
    score_column: str,
    predictor: str,
    unit: str,
    min_group_n: int,
    source_input_path: Path,
    source_input_sha256: str,
    command: str,
    generated: str,
    caveat: str,
    family: str,
) -> dict:
    """
    Run a Kruskal-Wallis test comparing sentiment scores across multiple groups.

    Tests whether sentiment differs significantly across categories (e.g., do POI
    types or themes differ in sentiment?). Kruskal-Wallis is the nonparametric
    extension of Mann-Whitney U to 3+ groups.
    """
    work = pd.DataFrame({"score": numeric(df[score_column]), "group": df[predictor].astype(str)}).dropna()
    # Select only groups with adequate sample size to avoid spurious findings from sparse categories
    groups = [
        group["score"].to_numpy(dtype=float)
        for _, group in work.groupby("group")
        if len(group) >= min_group_n and group["score"].nunique() > 0
    ]
    group_counts = work.groupby("group").size().sort_values(ascending=False).to_dict()
    base = _base_row(
        analysis_id,
        research_question,
        score_column,
        predictor,
        unit,
        language_source_group,
        source_input_path,
        source_input_sha256,
        command,
        generated,
        caveat,
        family,
    )
    row = {
        **base,
        "analysis_type": "score_by_multicategory_predictor",
        "test_name": "kruskal_wallis_score_by_group",
        "status": "skipped",
        "n": int(len(work)),
        "group_a": None,
        "group_b": None,
        "group_a_n": None,
        "group_b_n": None,
        "group_a_score_mean": None,
        "group_b_score_mean": None,
        "group_a_score_median": None,
        "group_b_score_median": None,
        "group_a_event_count": None,
        "group_b_event_count": None,
        "group_a_event_pct": None,
        "group_b_event_pct": None,
        "statistic": None,
        "p_value": None,
        "p_value_bh_fdr": None,
        "effect_size": None,
        "effect_size_label": "epsilon_squared",
        "ci_95_lower": None,
        "ci_95_upper": None,
        "min_expected_count": None,
        "sparse_cell_warning": None,
        "details_json": json.dumps({"group_counts": group_counts, "reason": "fewer than two groups meet minimum n"}),
    }
    combined = np.concatenate(groups) if groups else np.array([])
    if len(groups) < 2:
        return row
    if len(np.unique(combined)) < 2:
        row["details_json"] = json.dumps({"group_counts": group_counts, "reason": "all retained scores are identical"})
        return row
    # Perform Kruskal-Wallis H test. Null hypothesis: the k groups have equal distributions.
    # A low p-value indicates at least one group differs significantly from the others.
    result = stats.kruskal(*groups)
    n = sum(len(group) for group in groups)
    k = len(groups)
    # Compute epsilon-squared effect size (nonparametric analogue of eta-squared)
    epsilon = (float(result.statistic) - k + 1) / (n - k) if n > k else None
    row.update({
        "status": "ok",
        "statistic": safe_float(result.statistic),
        "p_value": safe_float(result.pvalue),
        "effect_size": safe_float(epsilon),
        "details_json": json.dumps({"group_counts": group_counts, "min_group_n": min_group_n}, ensure_ascii=False),
    })
    return row


def apply_bh(rows: list[dict], family: str) -> None:
    # Apply Benjamini-Hochberg False Discovery Rate (FDR) correction within a testing family.
    # Adjusts p-values to control the expected proportion of false discoveries when running
    # multiple tests (e.g., multiple predictors tested in the same analysis family).
    indexes = [index for index, row in enumerate(rows) if row.get("multiple_testing_family") == family]
    adjusted = benjamini_hochberg([rows[index].get("p_value") for index in indexes])
    for index, p_adjusted in zip(indexes, adjusted):
        rows[index]["p_value_bh_fdr"] = p_adjusted


def _base_row(
    analysis_id: str,
    research_question: str,
    outcome: str,
    predictor: str,
    unit: str,
    language_source_group: str,
    source_input_path: Path,
    source_input_sha256: str,
    command: str,
    generated: str,
    caveat: str,
    multiple_testing_family: str,
) -> dict:
    from src.provenance import repo_relative

    return {
        "analysis_id": analysis_id,
        "research_question": research_question,
        "outcome": outcome,
        "predictor": predictor,
        "unit": unit,
        "language_source_group": language_source_group,
        "n": None,
        "multiple_testing_family": multiple_testing_family,
        "source_input_path": repo_relative(source_input_path),
        "source_input_sha256": source_input_sha256,
        "command": command,
        "generated_at": generated,
        "caveat": caveat,
    }
