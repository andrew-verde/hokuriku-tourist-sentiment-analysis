#!/usr/bin/env python3
"""
Build JP-EN Google review sentiment outputs.

This script:
1. Loads multilingual reviews from a CSV file
2. Scores each review's text sentiment using VADER (English) or oseti (Japanese)
3. Extracts reviewed keyword evidence from both languages
4. Aggregates row-level scores into group-level summaries (counts, means, percentages)
5. Runs statistical tests (chi-square, Mann-Whitney, t-tests, bootstrap confidence intervals)
6. Writes outputs: row-level scores (ignored), aggregate summaries/tests (tracked), and readiness markdown

Row-level scored reviews are written under ignored output paths. Tracked
aggregate outputs contain counts, tests, hashes, dependency versions, and
readiness notes only.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd
import yaml
from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.utils.logger import setup_logger
from src.provenance import (
    ProvenanceError,
    assert_no_forbidden_columns,
    file_record,
    research_manifest,
    sha256_file,
    write_json,
)
from src.scope import (
    MissingScopeColumnsError,
    MissingScopeInputError,
    load_poi_scope_metadata,
    scope_reviews_by_poi_prefecture,
)

logger = setup_logger(__name__)

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_REVIEWS_PATH = ROOT / "output" / "multilingual_review_analysis" / "reviews_multilingual.csv"
DEFAULT_POI_METADATA_PATH = ROOT / "output" / "checkpoints" / "poi_metadata.json"
DEFAULT_ROW_OUTPUT_DIR = ROOT / "output" / "sentiment_row_level"
DEFAULT_AGG_OUTPUT_DIR = ROOT / "output" / "sentiment_aggregates"
DEFAULT_REVIEWED_CODEBOOK_PATH = ROOT / "config" / "reviewed_jp_en_codebook.yaml"
SENTIMENT_LOCK_PATH = ROOT / "requirements-sentiment.lock.txt"
SENTIMENT_ENV_DOC_PATH = ROOT / "docs" / "sentiment_environment.md"

PRIMARY_BAND = 0.05
SENSITIVITY_BANDS = {"neutral_0_10": 0.10, "neutral_0_20": 0.20}
BOOTSTRAP_SEED = 20260618
BOOTSTRAP_ITERATIONS = 2000

REQUIRED_COLUMNS = {
    "city",
    "language_group",
    "review_text",
    "review_rating",
}

OPTIONAL_ROW_COLUMNS = [
    "review_id",
    "city",
    "prefecture_normalized",
    "municipality",
    "poi_id",
    "poi_category",
    "review_date",
    "review_rating",
    "language_group",
]

FORBIDDEN_AGGREGATE_COLUMNS = {
    "review_text",
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
}


class SentimentPipelineError(RuntimeError):
    pass


class MissingInputError(SentimentPipelineError):
    pass


class MissingColumnsError(SentimentPipelineError):
    pass


class MissingGroupError(SentimentPipelineError):
    pass


class MissingDependencyError(SentimentPipelineError):
    pass


@dataclass(frozen=True)
class PipelinePaths:
    """File and directory locations used by the sentiment pipeline."""
    reviews_path: Path = DEFAULT_REVIEWS_PATH
    poi_metadata_path: Path = DEFAULT_POI_METADATA_PATH
    reviewed_codebook_path: Path = DEFAULT_REVIEWED_CODEBOOK_PATH
    row_output_dir: Path = DEFAULT_ROW_OUTPUT_DIR
    aggregate_output_dir: Path = DEFAULT_AGG_OUTPUT_DIR


EVIDENCE_COLUMNS = [
    "reviewed_positive_terms_matched",
    "reviewed_negative_terms_matched",
    "reviewed_recommendation_terms_matched",
    "reviewed_friction_terms_matched",
    "reviewed_enjoyment_terms_matched",
]

BINARY_EVIDENCE_COLUMNS = [
    "any_friction",
    "any_enjoyment_evidence",
    "any_recommendation_evidence",
    "any_positive_evidence",
]


def sentiment_category(score: float, band: float = PRIMARY_BAND) -> str:
    # Convert a numeric sentiment score into the coarse category used in reports.
    # Scores above +band -> "positive", below -band -> "negative", in between -> "neutral"
    # The band parameter allows sensitivity analysis: wider bands (0.10, 0.20) create stricter positives/negatives
    if pd.isna(score):
        return "missing"
    if score >= band:
        return "positive"
    if score <= -band:
        return "negative"
    return "neutral"


def parse_groups(value: str) -> list[str]:
    # Normalize the comma-separated CLI input (e.g., "japanese,english") and reject an empty request.
    groups = [part.strip().lower() for part in value.split(",") if part.strip()]
    if not groups:
        raise SentimentPipelineError("--groups must name at least one language_group")
    return groups


def dependency_versions() -> dict[str, str]:
    # Record the installed package versions that shape the analysis results.
    # These versions are stored in the provenance manifest so results can be reproduced.
    packages = [
        "pandas",
        "numpy",
        "scipy",
        "vaderSentiment",
        "oseti",
        "mecab-python3",
        "bunkai",
        "unidic-lite",
        "ipadic",
        "emoji",
    ]
    versions = {}
    for package in packages:
        try:
            versions[package] = metadata.version(package)
        except metadata.PackageNotFoundError:
            versions[package] = "missing"
    return versions


def load_poi_metadata(path: Path) -> pd.DataFrame:
    # Load POI (point-of-interest) metadata to map reviews to geographic locations.
    # Used for prefecture-level filtering: reviews have poi_id, metadata maps poi_id -> prefecture.
    try:
        return load_poi_scope_metadata(path)
    except MissingScopeInputError as error:
        raise MissingInputError(
            f"Required POI metadata not found: {path}\n"
            "Generate or sync it first with `make multilingual-reviews`. "
            "Prefecture filtering requires checkpoint POI metadata."
        ) from error
    except MissingScopeColumnsError as error:
        raise MissingColumnsError(str(error)) from error


def require_dependency(module_name: str, package_name: str | None = None):
    # Delay imports until the scorer is used. That lets tests inject fake
    # scorers without requiring every sentiment package to be installed.
    try:
        return __import__(module_name, fromlist=["*"])
    except ImportError as error:
        install_name = package_name or module_name
        raise MissingDependencyError(
            f"Required dependency not importable: {module_name}. "
            f"Install it with `.venv/bin/pip install {install_name}`."
        ) from error


def score_english_text(text: str, analyzer=None) -> dict[str, float]:
    # Score English review text using VADER (Valence Aware Dictionary and sEntiment Reasoner).
    # VADER returns four component scores: negative, neutral, positive proportions, and a compound score (-1 to +1).
    # We store all components but use "sentiment_score" (compound) as the main comparable score.
    if analyzer is None:
        vader = require_dependency("vaderSentiment.vaderSentiment", "vaderSentiment")
        analyzer = vader.SentimentIntensityAnalyzer()
    scores = analyzer.polarity_scores(text or "")
    return {
        "vader_neg": float(scores["neg"]),
        "vader_neu": float(scores["neu"]),
        "vader_pos": float(scores["pos"]),
        "sentiment_score": float(scores["compound"]),  # Main score: -1 (negative) to +1 (positive)
    }


def _sum_polarity_counts(raw_counts: object) -> tuple[int, int]:
    # oseti may return either one dict or a list of dicts depending on version.
    positive = 0
    negative = 0
    items = raw_counts if isinstance(raw_counts, list) else [raw_counts]
    for item in items:
        if not isinstance(item, dict):
            continue
        positive += int(item.get("positive", item.get("p", item.get("pos", 0))) or 0)
        negative += int(item.get("negative", item.get("n", item.get("neg", 0))) or 0)
    return positive, negative


def score_japanese_text(text: str, analyzer=None) -> dict[str, object]:
    # Score Japanese review text using oseti (a morphological analyzer-based sentiment scorer for Japanese).
    # oseti analyzes sentence by sentence, so we average sentence-level scores to get a document (review) score.
    # The mean score is stored as "sentiment_score" to match the structure of English scoring.
    if analyzer is None:
        oseti = require_dependency("oseti", "oseti")
        try:
            ipadic = require_dependency("ipadic", "ipadic")
            mecab_args = f"-r /dev/null -d {ipadic.DICDIR}"
        except MissingDependencyError:
            mecab_args = "-r /dev/null"
        analyzer = oseti.Analyzer(mecab_args=mecab_args)
    sentence_scores = [float(score) for score in analyzer.analyze(text or "")]
    # Use the mean of sentence-level scores as the document-level score.
    doc_score = float(np.mean(sentence_scores)) if sentence_scores else 0.0
    positive_count = 0
    negative_count = 0
    if hasattr(analyzer, "count_polarity"):
        positive_count, negative_count = _sum_polarity_counts(analyzer.count_polarity(text or ""))
    return {
        "oseti_sentence_scores": json.dumps(sentence_scores, ensure_ascii=False),
        "oseti_doc_score": doc_score,
        "oseti_positive_count": positive_count,
        "oseti_negative_count": negative_count,
        "sentiment_score": doc_score,  # Main score: mean of sentence-level oseti scores
    }


def load_reviews(
    path: Path,
    groups: list[str],
    city: str | None = None,
    prefecture: str | None = None,
    poi_metadata_path: Path = DEFAULT_POI_METADATA_PATH,
) -> pd.DataFrame:
    # Load the multilingual reviews CSV and filter to requested language groups and geography.
    if not path.exists():
        raise MissingInputError(
            f"Required input not found: {path}\n"
            "Generate it first with `make multilingual-reviews`. This pipeline has no demo mode."
        )
    df = pd.read_csv(path)

    # Enforce the minimum shape needed for the downstream filtering and scoring steps.
    missing = sorted(REQUIRED_COLUMNS - set(df.columns))
    if missing:
        raise MissingColumnsError(f"Required columns missing from {path}: {', '.join(missing)}")

    # Check that requested language groups (e.g., "japanese", "english") are present in the data.
    present_groups = set(df["language_group"].dropna().astype(str).str.lower())
    missing_groups = sorted(set(groups) - present_groups)
    if missing_groups:
        raise MissingGroupError(
            f"Requested language_group not present in input: {', '.join(missing_groups)}"
        )

    # Filter to selected language groups.
    filtered = df[df["language_group"].astype(str).str.lower().isin(groups)].copy()
    # `copy()` avoids pandas "view versus copy" ambiguity before we add/convert
    # columns later in this function.

    # If prefecture filter is requested, look up poi_id in metadata to check each review's location.
    if prefecture:
        metadata = load_poi_metadata(poi_metadata_path)
        try:
            filtered = scope_reviews_by_poi_prefecture(filtered, metadata, prefecture)
        except MissingScopeColumnsError as error:
            raise MissingColumnsError(str(error)) from error

    # If city filter is requested, keep only rows with matching city value.
    if city:
        filtered = filtered[filtered["city"].astype(str) == city].copy()

    filtered["language_group"] = filtered["language_group"].astype(str).str.lower()
    if filtered.empty:
        raise MissingGroupError(
            f"No rows after filters: city == {city!r}, prefecture == {prefecture!r}, "
            f"language_group in {groups!r}"
        )

    # Convert review_rating to numeric (coerce invalid values to NaN).
    filtered["review_rating"] = pd.to_numeric(filtered["review_rating"], errors="coerce")
    return filtered


def load_reviewed_evidence_codebook(path: Path) -> dict[str, dict[str, list[str]]]:
    # Load the manually-reviewed codebook (YAML format) that lists keywords for each evidence family.
    # Evidence families: friction, positive sentiment, negative sentiment, recommendation intent, enjoyment.
    # Returns a nested dict: language -> evidence_column -> list of keywords
    if not path.exists():
        raise MissingInputError(
            f"Required reviewed JP/EN codebook config not found: {path}\n"
            "Generate it with `make reviewed-codebook-config` after manual review is complete."
        )
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    languages = raw.get("languages")
    if not isinstance(languages, dict):
        raise MissingColumnsError(f"Reviewed codebook config missing languages object: {path}")

    evidence: dict[str, dict[str, list[str]]] = {}
    for language, language_config in languages.items():
        key = str(language).lower()
        evidence[key] = {column: [] for column in EVIDENCE_COLUMNS}
        codes = language_config.get("codes", {}) if isinstance(language_config, dict) else {}

        # Extract keywords from each code and organize by family/type.
        for code, entry in codes.items():
            if not isinstance(entry, dict):
                continue
            keywords = [str(keyword).strip() for keyword in entry.get("keywords", []) if str(keyword).strip()]
            family = str(entry.get("code_family", "")).lower()
            code_name = str(code)

            # Sort keywords into the appropriate evidence columns based on code family/name.
            if family == "friction":
                evidence[key]["reviewed_friction_terms_matched"].extend(keywords)
            if code_name == "positive_sentiment":
                evidence[key]["reviewed_positive_terms_matched"].extend(keywords)
                evidence[key]["reviewed_enjoyment_terms_matched"].extend(keywords)
            elif code_name == "negative_sentiment":
                evidence[key]["reviewed_negative_terms_matched"].extend(keywords)
            elif code_name == "recommendation_intent":
                evidence[key]["reviewed_recommendation_terms_matched"].extend(keywords)
                evidence[key]["reviewed_enjoyment_terms_matched"].extend(keywords)

        for column, keywords in evidence[key].items():
            # Deduplicate while preserving reviewed order; some keywords can legitimately appear in multiple families.
            evidence[key][column] = list(dict.fromkeys(keywords))
    return evidence


def _match_reviewed_terms(text: str, keywords: list[str], language: str) -> list[str]:
    if not text or not keywords:
        return []
    if language == "english":
        haystack = text.casefold()
        return [keyword for keyword in keywords if keyword.casefold() in haystack]
    return [keyword for keyword in keywords if keyword in text]


def reviewed_evidence_for_text(
    text: str,
    language: str,
    codebook: dict[str, dict[str, list[str]]] | None,
) -> dict[str, object]:
    language_key = str(language).lower()
    language_terms = (codebook or {}).get(language_key, {})
    evidence = {
        column: "|".join(_match_reviewed_terms(text, language_terms.get(column, []), language_key))
        for column in EVIDENCE_COLUMNS
    }
    evidence["any_friction"] = bool(evidence["reviewed_friction_terms_matched"])
    evidence["any_enjoyment_evidence"] = bool(evidence["reviewed_enjoyment_terms_matched"])
    evidence["any_recommendation_evidence"] = bool(evidence["reviewed_recommendation_terms_matched"])
    evidence["any_positive_evidence"] = bool(evidence["reviewed_positive_terms_matched"])
    return evidence


def score_reviews(
    reviews: pd.DataFrame,
    english_scorer: Callable[[str], dict[str, object]] | None = None,
    japanese_scorer: Callable[[str], dict[str, object]] | None = None,
    reviewed_codebook: dict[str, dict[str, list[str]]] | None = None,
) -> pd.DataFrame:
    # Score each review's text by language and extract reviewed keyword evidence.
    # Returns a DataFrame with one row per review, including all original columns plus sentiment scores and evidence columns.

    if english_scorer is None:
        # Build the VADER analyzer once and reuse it for every English row.
        # MeCab/oseti startup is expensive, so we build them once too.
        vader = require_dependency("vaderSentiment.vaderSentiment", "vaderSentiment")
        english_analyzer = vader.SentimentIntensityAnalyzer()
        english_scorer = lambda text: score_english_text(text, analyzer=english_analyzer)

    if japanese_scorer is None:
        # Build the Japanese analyzer once. MeCab startup is expensive enough
        # that per-row initialization would be wasteful and harder to reproduce.
        oseti = require_dependency("oseti", "oseti")
        try:
            ipadic = require_dependency("ipadic", "ipadic")
            mecab_args = f"-r /dev/null -d {ipadic.DICDIR}"
        except MissingDependencyError:
            mecab_args = "-r /dev/null"
        japanese_analyzer = oseti.Analyzer(mecab_args=mecab_args)
        japanese_scorer = lambda text: score_japanese_text(text, analyzer=japanese_analyzer)

    rows = []
    for _, row in reviews.iterrows():
        # For each review, preserve original columns and add sentiment + evidence outputs.
        language = row["language_group"]
        text = "" if pd.isna(row["review_text"]) else str(row["review_text"])
        base = {column: row[column] if column in reviews.columns else None for column in OPTIONAL_ROW_COLUMNS}

        # Store text length as metadata (safe to include, not the full text).
        base["text_length_chars"] = len(text)

        # Score the review text using the appropriate language scorer.
        if language == "english":
            scored = english_scorer(text)
        elif language == "japanese":
            scored = japanese_scorer(text)
        else:
            raise MissingGroupError(f"Scoring not implemented for language_group: {language}")

        base.update(scored)  # Add VADER/oseti scores

        # Match reviewed keywords against the review text.
        base.update(reviewed_evidence_for_text(text, str(language), reviewed_codebook))

        # Create coarse sentiment category (negative/neutral/positive) based on score.
        base["sentiment_category"] = sentiment_category(float(base["sentiment_score"]))

        # For sensitivity analysis, create additional categories using wider neutral bands.
        # Shows whether conclusions change when the neutral threshold is stricter (0.10, 0.20).
        for label, band in SENSITIVITY_BANDS.items():
            base[f"sentiment_category_{label}"] = sentiment_category(float(base["sentiment_score"]), band)

        rows.append(base)

    return pd.DataFrame(rows)


def source_group_series(df: pd.DataFrame) -> pd.Series:
    # Use the source platform when available; otherwise group all Google rows together.
    if "source_platform" in df.columns:
        values = df["source_platform"].fillna("").astype(str).str.strip()
        return values.mask(values == "", "google_reviews")
    return pd.Series(["google_reviews"] * len(df), index=df.index)


def build_summary(scored: pd.DataFrame, source_groups: pd.Series) -> pd.DataFrame:
    # Aggregate row-level sentiment scores into group-level summary statistics.
    # This function is the tracked aggregate layer: counts, means, medians, percentages, and rating distributions only.
    # Output: one row per source/language/prefecture/city combination with aggregate metrics.
    work = scored.copy()
    work["source_group"] = source_groups.values
    rows = []
    category_order = ["negative", "neutral", "positive"]
    group_columns = ["source_group", "language_group"]
    if "prefecture_normalized" in work.columns:
        group_columns.append("prefecture_normalized")
    group_columns.append("city")

    for keys, chunk in work.groupby(group_columns, dropna=False):
        # Each output row is one source/language/prefecture/city bucket.
        key_map = dict(zip(group_columns, keys))
        total = len(chunk)
        rating = pd.to_numeric(chunk["review_rating"], errors="coerce")
        row = {
            "source_group": key_map["source_group"],
            "language_group": key_map["language_group"],
            "prefecture_normalized": key_map.get("prefecture_normalized"),
            "city": key_map["city"],
            "n_reviews": total,
            "n_scored": int(chunk["sentiment_score"].notna().sum()),
            "mean_sentiment_score": round(float(chunk["sentiment_score"].mean()), 6),
            "median_sentiment_score": round(float(chunk["sentiment_score"].median()), 6),
            "mean_review_rating": round(float(rating.mean()), 6) if rating.notna().any() else np.nan,
            "n_review_rating_present": int(rating.notna().sum()),
        }
        for category in category_order:
            # Category percentages are stored as fractions (0..1) so downstream
            # chart code can format them consistently.
            count = int((chunk["sentiment_category"] == category).sum())
            row[f"{category}_count"] = count
            row[f"{category}_pct"] = round(count / total, 6) if total else np.nan
        for label in SENSITIVITY_BANDS:
            for category in category_order:
                count = int((chunk[f"sentiment_category_{label}"] == category).sum())
                row[f"{label}_{category}_count"] = count
                row[f"{label}_{category}_pct"] = round(count / total, 6) if total else np.nan
        for column in BINARY_EVIDENCE_COLUMNS:
            count = int(chunk[column].fillna(False).astype(bool).sum()) if column in chunk.columns else 0
            row[f"{column}_count"] = count
            row[f"{column}_pct"] = round(count / total, 6) if total else np.nan
        positive_or_recommend = (
            chunk["any_positive_evidence"].fillna(False).astype(bool)
            | chunk["any_recommendation_evidence"].fillna(False).astype(bool)
            if {"any_positive_evidence", "any_recommendation_evidence"} <= set(chunk.columns)
            else pd.Series(False, index=chunk.index)
        )
        library_positive = chunk["sentiment_category"] == "positive"
        disagreement = library_positive != positive_or_recommend
        row["library_vs_reviewed_positive_disagreement_count"] = int(disagreement.sum())
        row["library_vs_reviewed_positive_disagreement_pct"] = (
            round(float(disagreement.mean()), 6) if total else np.nan
        )
        rating_counts = rating.value_counts(dropna=True).sort_index()
        # JSON keeps the whole star-rating distribution inside one CSV cell.
        row["rating_distribution_json"] = json.dumps(
            {str(k): int(v) for k, v in rating_counts.items()},
            ensure_ascii=False,
            sort_keys=True,
        )
        rows.append(row)
    return pd.DataFrame(rows).sort_values(["source_group", "language_group", "prefecture_normalized", "city"])


def _bootstrap_diff(
    left: np.ndarray,
    right: np.ndarray,
    reducer: Callable[[np.ndarray], float],
    seed: int = BOOTSTRAP_SEED,
    iterations: int = BOOTSTRAP_ITERATIONS,
) -> tuple[float, float, float]:
    # Compute bootstrap confidence intervals for the difference between two groups.
    # reducer is a function (e.g., np.mean or np.median) that summarizes an array into a single number.
    # Returns: (observed difference, lower 95% CI, upper 95% CI)
    rng = np.random.default_rng(seed)
    observed = float(reducer(left) - reducer(right))

    # Standard row-level bootstrap: resample each side independently with replacement.
    diffs = []
    for _ in range(iterations):
        # Resampling with replacement simulates rerunning the study on another sample of the same size.
        sample_left = rng.choice(left, size=len(left), replace=True)
        sample_right = rng.choice(right, size=len(right), replace=True)
        diffs.append(float(reducer(sample_left) - reducer(sample_right)))

    # Extract the 95% confidence interval from the bootstrap distribution.
    lower, upper = np.percentile(diffs, [2.5, 97.5])
    return observed, float(lower), float(upper)


def _cluster_bootstrap_mean_diff(
    scored: pd.DataFrame,
    left_name: str,
    right_name: str,
    seed: int = BOOTSTRAP_SEED,
    iterations: int = BOOTSTRAP_ITERATIONS,
) -> tuple[float, float, float, int, int]:
    # Cluster bootstrap for mean differences: resample POI clusters (not individual reviews).
    # Resamples POIs with replacement, keeping all reviews within each POI together.
    # This preserves the within-POI clustering structure in the confidence interval.
    # Returns: (observed mean diff, lower 95% CI, upper 95% CI, left n_POIs, right n_POIs)

    work = scored[["language_group", "poi_id", "sentiment_score"]].dropna().copy()
    work["poi_id"] = work["poi_id"].astype(str)

    # Organize reviews by POI and language.
    grouped = {
        # Each list item is all review sentiment scores for one POI.
        language: [
            cluster["sentiment_score"].to_numpy()
            for _, cluster in chunk.groupby("poi_id")
        ]
        for language, chunk in work.groupby("language_group")
    }

    left_clusters = grouped.get(left_name, [])
    right_clusters = grouped.get(right_name, [])

    if not left_clusters or not right_clusters:
        return np.nan, np.nan, np.nan, len(left_clusters), len(right_clusters)

    left_values = np.concatenate(left_clusters)
    right_values = np.concatenate(right_clusters)
    observed = float(np.mean(left_values) - np.mean(right_values))

    rng = np.random.default_rng(seed)
    diffs = []
    for _ in range(iterations):
        # Sample POIs with replacement, then concatenate all reviews within sampled POIs.
        # This keeps within-POI clustering visible in the uncertainty estimate.
        sampled_left = [left_clusters[index] for index in rng.integers(0, len(left_clusters), len(left_clusters))]
        sampled_right = [
            right_clusters[index] for index in rng.integers(0, len(right_clusters), len(right_clusters))
        ]
        diffs.append(float(np.mean(np.concatenate(sampled_left)) - np.mean(np.concatenate(sampled_right))))

    lower, upper = np.percentile(diffs, [2.5, 97.5])
    return observed, float(lower), float(upper), len(left_clusters), len(right_clusters)


def _poi_level_scores(scored: pd.DataFrame) -> pd.DataFrame:
    if "poi_id" not in scored.columns:
        return pd.DataFrame(columns=["language_group", "poi_id", "mean_sentiment_score", "n_reviews"])
    work = scored[["language_group", "poi_id", "sentiment_score"]].dropna().copy()
    work["poi_id"] = work["poi_id"].astype(str)
    # Collapse review rows to a single mean score per POI before sensitivity checks.
    return (
        work.groupby(["language_group", "poi_id"], as_index=False)
        .agg(mean_sentiment_score=("sentiment_score", "mean"), n_reviews=("sentiment_score", "size"))
    )


def _cramers_v(table: pd.DataFrame) -> float:
    # Cramer's V turns the chi-square result into a bounded effect size.
    chi2, _, _, _ = stats.chi2_contingency(table)
    n = float(table.to_numpy().sum())
    if n == 0:
        return np.nan
    r, k = table.shape
    denom = n * (min(k - 1, r - 1))
    return float(np.sqrt(chi2 / denom)) if denom else np.nan


def _numeric_group_arrays(
    df: pd.DataFrame,
    value_column: str,
    languages: list[str],
) -> dict[str, np.ndarray]:
    arrays = {}
    for language in languages:
        values = pd.to_numeric(
            df.loc[df["language_group"] == language, value_column],
            errors="coerce",
        ).dropna()
        arrays[language] = values.to_numpy(dtype=float)
    return arrays


def _welch_anova(groups: list[np.ndarray]) -> tuple[float, float, float, float]:
    # Welch ANOVA keeps unequal group variances/sample sizes explicit.
    usable = [group for group in groups if len(group) >= 2 and np.var(group, ddof=1) > 0]
    if len(usable) < 2:
        return np.nan, np.nan, np.nan, np.nan
    k = len(usable)
    n = np.array([len(group) for group in usable], dtype=float)
    means = np.array([np.mean(group) for group in usable], dtype=float)
    variances = np.array([np.var(group, ddof=1) for group in usable], dtype=float)
    weights = n / variances
    weight_sum = float(np.sum(weights))
    weighted_mean = float(np.sum(weights * means) / weight_sum)
    df1 = float(k - 1)
    adjustment_terms = ((1.0 - (weights / weight_sum)) ** 2) / (n - 1.0)
    adjustment_sum = float(np.sum(adjustment_terms))
    numerator = float(np.sum(weights * ((means - weighted_mean) ** 2)) / df1)
    denominator = 1.0 + ((2.0 * (k - 2.0)) / ((k**2) - 1.0)) * adjustment_sum
    f_stat = numerator / denominator
    df2 = float(((k**2) - 1.0) / (3.0 * adjustment_sum)) if adjustment_sum else np.inf
    p_value = float(stats.f.sf(f_stat, df1, df2)) if np.isfinite(df2) else np.nan
    return float(f_stat), p_value, df1, df2


def _append_raw_score_parametric_skip(rows: list[dict], comparison: str) -> None:
    rows.append({
        "test_name": "raw_score_parametric_tests_not_run",
        "comparison": comparison,
        "status": "skipped",
        "statistic": np.nan,
        "p_value": np.nan,
        "effect": np.nan,
        "details_json": json.dumps({
            "reason": "VADER compound and oseti document scores are different tool-specific scales",
            "recommended_parametric_path": "Welch t-test/ANOVA only on common-scale Google review_rating, or later on validated codebook-derived common outcomes",
            "text_sentiment_path": "category-share tests plus distribution/bootstrap sensitivity with explicit non-equivalence caveat",
        }),
    })


def build_tests(scored: pd.DataFrame) -> pd.DataFrame:
    # Run a suite of statistical tests comparing language groups (Japanese vs. English reviews).
    # Returns one row per test (chi-square, Mann-Whitney, t-tests, bootstrap CIs, etc.)
    # Each test row includes: test_name, comparison, status (ok/skipped), statistic, p_value, effect size, details_json.
    rows = []
    languages = sorted(scored["language_group"].dropna().unique())
    if len(languages) != 2:
        rows.append({
            "test_name": "jp_en_required",
            "comparison": ",".join(languages),
            "status": "skipped",
            "statistic": np.nan,
            "p_value": np.nan,
            "effect": np.nan,
            "details_json": json.dumps({"reason": "exactly two groups required"}),
        })
        return pd.DataFrame(rows)

    left_name, right_name = languages
    # Extract sentiment scores for each language group (drop NaN values).
    left = scored.loc[scored["language_group"] == left_name, "sentiment_score"].dropna().to_numpy()
    right = scored.loc[scored["language_group"] == right_name, "sentiment_score"].dropna().to_numpy()
    # `left` and `right` are plain NumPy arrays because scipy functions expect numeric array-like inputs.

    comparison = f"{left_name}_vs_{right_name}"
    score_scale_details = {
        "left": left_name,
        "right": right_name,
        "measurement_scale": "tool_specific_non_equivalent",
        "interpretation": (
            "Descriptive score-distribution sensitivity only; do not interpret as "
            "a raw VADER-vs-oseti mean-scale comparison."
        ),
    }

    # Test 1: Chi-square test on sentiment category independence (negative/neutral/positive).
    # Create a contingency table: rows=languages, columns=sentiment categories.
    table = pd.crosstab(scored["language_group"], scored["sentiment_category"])
    # crosstab counts how many negative/neutral/positive rows each language has.

    # Ensure all expected categories are present (even if 0 count).
    for category in ["negative", "neutral", "positive"]:
        if category not in table.columns:
            table[category] = 0
    table = table[["negative", "neutral", "positive"]]
    table = table.loc[:, table.sum(axis=0) > 0]  # Keep only non-empty categories.

    # Skip if fewer than 2x2 contingency (need both languages AND at least 2 categories).
    if table.shape[0] < 2 or table.shape[1] < 2:
        rows.append({
            "test_name": "sentiment_category_independence",
            "comparison": comparison,
            "status": "skipped",
            "statistic": np.nan,
            "p_value": np.nan,
            "effect": np.nan,
            "details_json": json.dumps({
                "reason": "fewer than two non-empty sentiment categories",
                "observed": table.to_dict(),
            }, ensure_ascii=False),
        })
    elif table.shape == (2, 2):
        # Exact test for 2x2 contingency.
        oddsratio, p_value = stats.fisher_exact(table)
        rows.append({
            "test_name": "fisher_exact_sentiment_category",
            "comparison": comparison,
            "status": "ok",
            "statistic": oddsratio,
            "p_value": p_value,
            "effect": np.nan,
            "details_json": table.to_json(),
        })
    else:
        # Chi-square test: tests independence of language_group and sentiment_category.
        # Effect size: Cramer's V (bounded 0-1, where 0=no association, 1=perfect association).
        chi2, p_value, dof, expected = stats.chi2_contingency(table)
        rows.append({
            "test_name": "chi_square_sentiment_category",
            "comparison": comparison,
            "status": "ok",
            "statistic": chi2,
            "p_value": p_value,
            "effect": _cramers_v(table),
            "details_json": json.dumps({
                "dof": int(dof),
                "observed": table.to_dict(),
                "expected": np.round(expected, 6).tolist(),
            }, ensure_ascii=False),
        })

    # Test 2: Mann-Whitney U test on raw sentiment scores (non-parametric, no normality assumption).
    # Compares the distribution of scores between language groups.
    mann = stats.mannwhitneyu(left, right, alternative="two-sided")
    rows.append({
        "test_name": "mann_whitney_u_sentiment_score",
        "comparison": comparison,
        "status": "ok",
        "statistic": float(mann.statistic),
        "p_value": float(mann.pvalue),
        "effect": np.nan,
        "details_json": json.dumps(score_scale_details),
    })

    # Test 3 & 4: Bootstrap confidence intervals for mean and median differences.
    # Bootstrap provides CI without assuming normality or equal variances.
    for name, reducer in [("mean", np.mean), ("median", np.median)]:
        observed, lower, upper = _bootstrap_diff(left, right, reducer)
        rows.append({
            "test_name": f"bootstrap_{name}_difference_sentiment_score",
            "comparison": comparison,
            "status": "ok",
            "statistic": observed,
            "p_value": np.nan,  # Bootstrap CIs don't produce p-values
            "effect": observed,
            "details_json": json.dumps({
                **score_scale_details,
                "ci_95_lower": lower,
                "ci_95_upper": upper,
                "iterations": BOOTSTRAP_ITERATIONS,
                "seed": BOOTSTRAP_SEED,
            }),
        })

    # Test 5 & 6: POI-level sensitivity checks (aggregate reviews within POIs before comparing).
    # Reduces review nesting: instead of comparing individual reviews, we first compute mean score per POI,
    # then compare POIs. This down-weights POIs with many reviews.
    poi_scores = _poi_level_scores(scored)
    poi_left = poi_scores.loc[
        poi_scores["language_group"] == left_name, "mean_sentiment_score"
    ].to_numpy()
    poi_right = poi_scores.loc[
        poi_scores["language_group"] == right_name, "mean_sentiment_score"
    ].to_numpy()

    if len(poi_left) >= 2 and len(poi_right) >= 2:
        poi_mann = stats.mannwhitneyu(poi_left, poi_right, alternative="two-sided")
        rows.append({
            "test_name": "poi_level_mann_whitney_mean_sentiment_score",
            "comparison": comparison,
            "status": "ok",
            "statistic": float(poi_mann.statistic),
            "p_value": float(poi_mann.pvalue),
            "effect": np.nan,
            "details_json": json.dumps({
                **score_scale_details,
                "left_n_poi": int(len(poi_left)),
                "right_n_poi": int(len(poi_right)),
                "unit": "one POI-language mean",
            }),
        })
        observed, lower, upper = _bootstrap_diff(poi_left, poi_right, np.mean)
        rows.append({
            "test_name": "poi_level_bootstrap_mean_difference_sentiment_score",
            "comparison": comparison,
            "status": "ok",
            "statistic": observed,
            "p_value": np.nan,
            "effect": observed,
            "details_json": json.dumps({
                **score_scale_details,
                "ci_95_lower": lower,
                "ci_95_upper": upper,
                "left_n_poi": int(len(poi_left)),
                "right_n_poi": int(len(poi_right)),
                "iterations": BOOTSTRAP_ITERATIONS,
                "seed": BOOTSTRAP_SEED,
                "unit": "one POI-language mean",
            }),
        })
    else:
        rows.append({
            "test_name": "poi_level_sensitivity",
            "comparison": comparison,
            "status": "skipped",
            "statistic": np.nan,
            "p_value": np.nan,
            "effect": np.nan,
            "details_json": json.dumps({
                "reason": "fewer than 2 POIs per language group",
                "left_n_poi": int(len(poi_left)),
                "right_n_poi": int(len(poi_right)),
            }),
        })

    observed, lower, upper, left_n_clusters, right_n_clusters = _cluster_bootstrap_mean_diff(
        scored, left_name, right_name
    )
    status = "ok" if not np.isnan(observed) else "skipped"
    rows.append({
        "test_name": "cluster_bootstrap_poi_mean_difference_sentiment_score",
        "comparison": comparison,
        "status": status,
        "statistic": observed,
        "p_value": np.nan,
        "effect": observed,
        "details_json": json.dumps({
            **score_scale_details,
            "ci_95_lower": lower,
            "ci_95_upper": upper,
            "left_n_poi": int(left_n_clusters),
            "right_n_poi": int(right_n_clusters),
            "iterations": BOOTSTRAP_ITERATIONS,
            "seed": BOOTSTRAP_SEED,
            "unit": "POI cluster resampling with review rows retained inside sampled clusters",
        }),
    })

    _append_raw_score_parametric_skip(rows, comparison)

    # Test 7: Welch t-test on review ratings (row-level, common Google 1-to-5 star scale).
    # Unlike VADER vs oseti scores, ratings are on the same scale, so parametric t-test is justified.
    rating_arrays = _numeric_group_arrays(scored, "review_rating", languages)
    rating_left = rating_arrays[left_name]
    rating_right = rating_arrays[right_name]

    if len(rating_left) >= 2 and len(rating_right) >= 2:
        # Welch t-test: does not assume equal variances (good for unequal group sizes).
        rating_t = stats.ttest_ind(rating_left, rating_right, equal_var=False, alternative="two-sided")
        rows.append({
            "test_name": "welch_t_review_rating",
            "comparison": comparison,
            "status": "ok",
            "statistic": float(rating_t.statistic),
            "p_value": float(rating_t.pvalue),
            "effect": float(np.mean(rating_left) - np.mean(rating_right)),
            "details_json": json.dumps({
                "left": left_name,
                "right": right_name,
                "unit": "one Google review row",
                "measurement_scale": "common_google_1_to_5_star_rating",
                "left_n": int(len(rating_left)),
                "right_n": int(len(rating_right)),
                "effect": "left_mean_rating_minus_right_mean_rating",
                "interpretation": "Parametric comparison is defensible for ratings because both groups use the same Google star scale.",
            }),
        })
    else:
        rows.append({
            "test_name": "welch_t_review_rating",
            "comparison": comparison,
            "status": "skipped",
            "statistic": np.nan,
            "p_value": np.nan,
            "effect": np.nan,
            "details_json": json.dumps({
                "reason": "fewer than 2 rows with review_rating per language group",
                "left_n": int(len(rating_left)),
                "right_n": int(len(rating_right)),
            }),
        })

    # Test 8: Welch ANOVA on review ratings (extension of Welch t-test for 2+ groups; here just 2 groups).
    # More general form, though with 2 groups it's equivalent to the t-test above.
    rating_f, rating_p, rating_df1, rating_df2 = _welch_anova(list(rating_arrays.values()))
    rows.append({
        "test_name": "welch_anova_review_rating",
        "comparison": comparison,
        "status": "ok" if not np.isnan(rating_f) else "skipped",
        "statistic": rating_f,
        "p_value": rating_p,
        "effect": np.nan,
        "details_json": json.dumps({
            "groups": languages,
            "unit": "one Google review row",
            "measurement_scale": "common_google_1_to_5_star_rating",
            "df_between": rating_df1,
            "df_within": rating_df2,
            "group_ns": {name: int(len(values)) for name, values in rating_arrays.items()},
            "interpretation": "Use for two or more Google review language groups on common star-rating scale; with two groups it is redundant with Welch t-test.",
        }),
    })

    if {"poi_id", "review_rating"} <= set(scored.columns):
        poi_rating = (
            scored[["language_group", "poi_id", "review_rating"]]
            .dropna()
            .assign(poi_id=lambda frame: frame["poi_id"].astype(str))
            .groupby(["language_group", "poi_id"], as_index=False)
            .agg(mean_review_rating=("review_rating", "mean"))
        )
        poi_rating_arrays = _numeric_group_arrays(poi_rating, "mean_review_rating", languages)
        poi_rating_left = poi_rating_arrays[left_name]
        poi_rating_right = poi_rating_arrays[right_name]
        if len(poi_rating_left) >= 2 and len(poi_rating_right) >= 2:
            poi_rating_t = stats.ttest_ind(
                poi_rating_left,
                poi_rating_right,
                equal_var=False,
                alternative="two-sided",
            )
            rows.append({
                "test_name": "poi_level_welch_t_mean_review_rating",
                "comparison": comparison,
                "status": "ok",
                "statistic": float(poi_rating_t.statistic),
                "p_value": float(poi_rating_t.pvalue),
                "effect": float(np.mean(poi_rating_left) - np.mean(poi_rating_right)),
                "details_json": json.dumps({
                    "left": left_name,
                    "right": right_name,
                    "unit": "one POI-language mean Google rating",
                    "measurement_scale": "common_google_1_to_5_star_rating",
                    "left_n_poi": int(len(poi_rating_left)),
                    "right_n_poi": int(len(poi_rating_right)),
                    "effect": "left_poi_mean_rating_minus_right_poi_mean_rating",
                    "interpretation": "POI-level sensitivity reduces review nesting but can be noisy with few English-language POIs.",
                }),
            })
        else:
            rows.append({
                "test_name": "poi_level_welch_t_mean_review_rating",
                "comparison": comparison,
                "status": "skipped",
                "statistic": np.nan,
                "p_value": np.nan,
                "effect": np.nan,
                "details_json": json.dumps({
                    "reason": "fewer than 2 POIs with review_rating per language group",
                    "left_n_poi": int(len(poi_rating_left)),
                    "right_n_poi": int(len(poi_rating_right)),
                }),
            })

    # Test 9: Spearman correlation between review_rating and sentiment_score (validation check).
    # Sanity check: do reviews with higher Google ratings also have higher sentiment scores?
    # This is descriptive, not causal.
    rating_work = scored[["language_group", "review_rating", "sentiment_score"]].dropna()
    if len(rating_work) >= 3:
        corr = stats.spearmanr(rating_work["review_rating"], rating_work["sentiment_score"])
        rows.append({
            "test_name": "rating_validation_spearman_score",
            "comparison": "all_groups",
            "status": "ok",
            "statistic": float(corr.statistic),
            "p_value": float(corr.pvalue),
            "effect": float(corr.statistic),
            "details_json": json.dumps({"n": int(len(rating_work))}),
        })
    else:
        rows.append({
            "test_name": "rating_validation_spearman_score",
            "comparison": "all_groups",
            "status": "skipped",
            "statistic": np.nan,
            "p_value": np.nan,
            "effect": np.nan,
            "details_json": json.dumps({"reason": "fewer than 3 rows with rating and sentiment"}),
        })
    return pd.DataFrame(rows)


def assert_no_forbidden_aggregate_columns(df: pd.DataFrame) -> None:
    # Privacy/sensitivity guardrail: ensure tracked aggregate outputs don't accidentally include
    # row-level text (review_text, author, URLs, IDs) that should stay in ignored row-level outputs only.
    try:
        assert_no_forbidden_columns(df.columns, FORBIDDEN_AGGREGATE_COLUMNS, "Aggregate output")
    except ProvenanceError as error:
        raise SentimentPipelineError(str(error)) from error


def write_readiness(report: dict, summary: pd.DataFrame, tests: pd.DataFrame, path: Path) -> None:
    # Write a human-readable markdown summary of inputs, denominators, test results, and caveats.
    # Includes file hashes (SHA256) to tie the report to the exact input files used.
    lines = [
        "# Sentiment Readiness",
        "",
        f"- generated_at: {report['generated_at']}",
        f"- command: `{report['command']}`",
        f"- input: `{report['input']['path']}`",
        f"- input_sha256: `{report['input']['sha256']}`",
        f"- poi_metadata: `{report['input']['poi_metadata_path']}`",
        f"- poi_metadata_sha256: `{report['input']['poi_metadata_sha256']}`",
        f"- reviewed_codebook: `{report['input']['reviewed_codebook_path']}`",
        f"- reviewed_codebook_sha256: `{report['input']['reviewed_codebook_sha256']}`",
        f"- row_level_output: `{report['outputs']['row_level_path']}`",
        f"- row_level_sha256: `{report['outputs']['row_level_sha256']}`",
        f"- filters: city == `{report['filters']['city']}`, "
        f"prefecture == `{report['filters']['prefecture']}`, "
        f"language_group in {report['filters']['groups']}",
        f"- primary_unit: {report['primary_unit']}",
        f"- codebook_evidence_status: {report['codebook_evidence_status']}",
        f"- bootstrap_seed: {BOOTSTRAP_SEED}",
        "",
        "## Dependency Versions",
        "",
    ]
    for name, version in report["dependency_versions"].items():
        lines.append(f"- {name}: {version}")
    lines.extend([
        "",
        "## Dependency Reproducibility",
        "",
        f"- setup_command: `{report['dependency_reproducibility']['setup_command']}`",
        f"- sentiment_lock: `{report['dependency_reproducibility']['sentiment_lock']}`",
        f"- environment_doc: `{report['dependency_reproducibility']['environment_doc']}`",
        f"- known_metadata_exception: {report['dependency_reproducibility']['known_metadata_exception']}",
    ])
    lines.extend(["", "## Denominators", ""])
    for _, row in summary.iterrows():
        prefecture = row.get("prefecture_normalized")
        lines.append(
            f"- {row['source_group']} / {row['language_group']} / "
            f"prefecture={prefecture} / city_bucket={row['city']}: "
            f"n_reviews={int(row['n_reviews'])}, n_scored={int(row['n_scored'])}, "
            f"ratings_present={int(row['n_review_rating_present'])}"
        )
    lines.extend(["", "## Tests", ""])
    for _, row in tests.iterrows():
        p_value = "NA" if pd.isna(row["p_value"]) else f"{float(row['p_value']):.6g}"
        lines.append(f"- {row['test_name']} ({row['comparison']}): status={row['status']}, p={p_value}")
    lines.extend([
        "",
        "## Caveats",
        "",
        "- Group labels describe review language, not reviewer nationality.",
        "- VADER and oseti scores are tool-specific. Do not interpret raw-score tests as cross-tool mean equivalence.",
        "- Raw sentiment-score t-tests/ANOVA are skipped because VADER compound and oseti document scores are not the same measurement scale.",
        "- `review_rating` is a common Google 1-to-5 scale, so Welch rating tests are companion outcome/validation evidence.",
        "- POI-level and cluster-bootstrap rows are sensitivity checks, not replacement primary models.",
        "- Reviewed JP/EN keyword evidence is an audit/sensitivity path, not a replacement for VADER/oseti.",
        "",
    ])
    path.write_text("\n".join(lines), encoding="utf-8")


def build_sentiment_analysis(
    paths: PipelinePaths = PipelinePaths(),
    groups: list[str] | None = None,
    city: str | None = None,
    prefecture: str | None = None,
    command: str | None = None,
    english_scorer: Callable[[str], dict[str, object]] | None = None,
    japanese_scorer: Callable[[str], dict[str, object]] | None = None,
) -> dict:
    # Main sentiment analysis pipeline:
    # 1. Load reviews, codebook, and metadata
    # 2. Score each review using VADER (English) or oseti (Japanese)
    # 3. Extract reviewed keyword evidence
    # 4. Build aggregate summary statistics
    # 5. Run statistical tests
    # 6. Write outputs and manifests

    groups = groups or ["japanese", "english"]

    # Compute SHA256 hashes of all inputs for provenance tracking.
    input_hash = sha256_file(paths.reviews_path) if paths.reviews_path.exists() else None
    metadata_hash = sha256_file(paths.poi_metadata_path) if prefecture and paths.poi_metadata_path.exists() else None
    codebook_hash = sha256_file(paths.reviewed_codebook_path) if paths.reviewed_codebook_path.exists() else None

    # Load inputs.
    reviewed_codebook = load_reviewed_evidence_codebook(paths.reviewed_codebook_path)
    reviews = load_reviews(
        paths.reviews_path,
        groups,
        city=city,
        prefecture=prefecture,
        poi_metadata_path=paths.poi_metadata_path,
    )

    # Score all reviews and extract evidence.
    scored = score_reviews(
        reviews,
        english_scorer=english_scorer,
        japanese_scorer=japanese_scorer,
        reviewed_codebook=reviewed_codebook,
    )

    # Create output directories.
    paths.row_output_dir.mkdir(parents=True, exist_ok=True)
    paths.aggregate_output_dir.mkdir(parents=True, exist_ok=True)

    # Write row-level scores to ignored path (contains individual review data).
    scope = prefecture or city or "all"
    row_path = paths.row_output_dir / f"google_reviews_{scope.lower()}_{'-'.join(groups)}.csv"
    scored.to_csv(row_path, index=False)
    row_hash = sha256_file(row_path)

    # Build aggregate summaries and run tests.
    summary = build_summary(scored, source_group_series(reviews))
    tests = build_tests(scored)
    # Guardrails run before writing aggregate CSVs, so a privacy leak fails loud.
    assert_no_forbidden_aggregate_columns(summary)
    assert_no_forbidden_aggregate_columns(tests)

    summary_path = paths.aggregate_output_dir / "source_group_sentiment_summary.csv"
    tests_path = paths.aggregate_output_dir / "source_group_sentiment_tests.csv"
    manifest_path = paths.aggregate_output_dir / "sentiment_manifest.json"
    readiness_path = paths.aggregate_output_dir / "sentiment_readiness.md"

    summary.to_csv(summary_path, index=False)
    tests.to_csv(tests_path, index=False)

    # The manifest is machine-readable provenance; readiness markdown is the
    # same run summarized for humans.
    generated_at = dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat()
    report = {
        "schema_version": "sentiment_manifest.v2",
        "generated_at": generated_at,
        "command": command or " ".join(sys.argv),
        "filters": {"city": city, "prefecture": prefecture, "groups": groups},
        "primary_unit": "one Google review row",
        "codebook_evidence_status": "active",
        "dependency_versions": dependency_versions(),
        "dependency_reproducibility": {
            "sentiment_lock": str(SENTIMENT_LOCK_PATH),
            "environment_doc": str(SENTIMENT_ENV_DOC_PATH),
            "setup_command": ".venv/bin/python3 scripts/bootstrap_sentiment_environment.py",
            "known_metadata_exception": (
                "oseti 0.4.3.1 declares legacy mecab; runtime uses "
                "mecab-python3 plus ipadic and initializes MeCab with -r /dev/null."
            ),
        },
        "input": {
            "path": str(paths.reviews_path),
            "sha256": input_hash,
            "poi_metadata_path": str(paths.poi_metadata_path) if prefecture else None,
            "poi_metadata_sha256": metadata_hash,
            "reviewed_codebook_path": str(paths.reviewed_codebook_path),
            "reviewed_codebook_sha256": codebook_hash,
        },
        "outputs": {
            "row_level_path": str(row_path),
            "row_level_sha256": row_hash,
            "summary_path": str(summary_path),
            "tests_path": str(tests_path),
            "readiness_path": str(readiness_path),
        },
        "denominators": json.loads(summary.to_json(orient="records")),
    }
    write_readiness(report, summary, tests, readiness_path)
    report["provenance"] = research_manifest(
        kind="jp_en_sentiment_analysis",
        command=report["command"],
        generated_at=generated_at,
        filters=report["filters"],
        inputs=[
            file_record(paths.reviews_path, "reviews_multilingual", required=True),
            file_record(paths.poi_metadata_path, "poi_metadata", required=bool(prefecture)),
            file_record(paths.reviewed_codebook_path, "reviewed_jp_en_codebook_config", required=True),
        ],
        outputs=[
            file_record(row_path, "ignored_row_level_scored_reviews", required=True),
            file_record(summary_path, "tracked_aggregate_summary", required=True),
            file_record(tests_path, "tracked_statistical_tests", required=True),
            file_record(readiness_path, "tracked_readiness_markdown", required=True),
        ],
        metrics={
            "primary_unit": report["primary_unit"],
            "scope_method": (
                sorted(str(value) for value in reviews["scope_method"].dropna().unique())
                if "scope_method" in reviews.columns else []
            ),
            "denominators": report["denominators"],
            "codebook_evidence_status": report["codebook_evidence_status"],
            "bootstrap_seed": BOOTSTRAP_SEED,
            "bootstrap_iterations": BOOTSTRAP_ITERATIONS,
        },
        caveats=[
            "Group labels describe review language, not reviewer nationality.",
            "VADER and oseti scores are tool-specific; raw sentiment-score t-tests/ANOVA are not run.",
            "Welch rating tests use common-scale Google review_rating as companion outcome/validation evidence.",
            "POI-level and cluster-bootstrap rows are sensitivity checks.",
            "Reviewed JP/EN codebook evidence is an audit/sensitivity path, not a replacement for VADER/oseti.",
        ],
        extra={
            "dependency_versions": report["dependency_versions"],
            "dependency_reproducibility": report["dependency_reproducibility"],
        },
    )
    write_json(manifest_path, report)
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reviews-path", type=Path, default=DEFAULT_REVIEWS_PATH)
    parser.add_argument("--poi-metadata-path", type=Path, default=DEFAULT_POI_METADATA_PATH)
    parser.add_argument("--reviewed-codebook-path", type=Path, default=DEFAULT_REVIEWED_CODEBOOK_PATH)
    parser.add_argument("--row-output-dir", type=Path, default=DEFAULT_ROW_OUTPUT_DIR)
    parser.add_argument("--aggregate-output-dir", type=Path, default=DEFAULT_AGG_OUTPUT_DIR)
    parser.add_argument("--groups", default="japanese,english")
    parser.add_argument("--city", default=None)
    parser.add_argument("--prefecture", default="Fukui")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    paths = PipelinePaths(
        reviews_path=args.reviews_path,
        poi_metadata_path=args.poi_metadata_path,
        reviewed_codebook_path=args.reviewed_codebook_path,
        row_output_dir=args.row_output_dir,
        aggregate_output_dir=args.aggregate_output_dir,
    )
    try:
        report = build_sentiment_analysis(
            paths=paths,
            groups=parse_groups(args.groups),
            city=args.city,
            prefecture=args.prefecture,
            command=" ".join(sys.argv),
        )
    except SentimentPipelineError as error:
        logger.error(str(error))
        return 1
    logger.info("Sentiment summary written: %s", report["outputs"]["summary_path"])
    logger.info("Sentiment tests written: %s", report["outputs"]["tests_path"])
    logger.info("Readiness written: %s", report["outputs"]["readiness_path"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
