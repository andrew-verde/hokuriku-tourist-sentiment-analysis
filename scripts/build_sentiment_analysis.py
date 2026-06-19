#!/usr/bin/env python3
"""
Build JP-EN Google review sentiment outputs.

Row-level scored reviews are written under ignored output paths. Tracked
aggregate outputs contain counts, tests, hashes, dependency versions, and
readiness notes only.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.utils.logger import setup_logger

logger = setup_logger(__name__)

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_REVIEWS_PATH = ROOT / "output" / "multilingual_review_analysis" / "reviews_multilingual.csv"
DEFAULT_POI_METADATA_PATH = ROOT / "output" / "checkpoints" / "poi_metadata.json"
DEFAULT_ROW_OUTPUT_DIR = ROOT / "output" / "sentiment_row_level"
DEFAULT_AGG_OUTPUT_DIR = ROOT / "output" / "sentiment_aggregates"
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
    row_output_dir: Path = DEFAULT_ROW_OUTPUT_DIR
    aggregate_output_dir: Path = DEFAULT_AGG_OUTPUT_DIR


def sha256_file(path: Path) -> str:
    # Hash the file in chunks so large inputs do not need to be loaded at once.
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sentiment_category(score: float, band: float = PRIMARY_BAND) -> str:
    # Convert a numeric sentiment score into the coarse category used in reports.
    if pd.isna(score):
        return "missing"
    if score >= band:
        return "positive"
    if score <= -band:
        return "negative"
    return "neutral"


def parse_groups(value: str) -> list[str]:
    # Normalize the comma-separated CLI input and reject an empty request.
    groups = [part.strip().lower() for part in value.split(",") if part.strip()]
    if not groups:
        raise SentimentPipelineError("--groups must name at least one language_group")
    return groups


def dependency_versions() -> dict[str, str]:
    # Record the installed package versions that shape the analysis results.
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
    if not path.exists():
        raise MissingInputError(
            f"Required POI metadata not found: {path}\n"
            "Generate or sync it first with `make multilingual-reviews`. "
            "Prefecture filtering requires checkpoint POI metadata."
        )
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise MissingColumnsError(f"POI metadata must be a JSON object keyed by poi_id: {path}")
    rows = []
    for poi_id, attrs in raw.items():
        # Keep only the metadata needed to filter review rows by prefecture.
        if isinstance(attrs, dict):
            rows.append({
                "poi_id": str(poi_id),
                "metadata_poi_name": attrs.get("name"),
                "prefecture": attrs.get("prefecture"),
                "prefecture_normalized": attrs.get("prefecture_normalized"),
                "municipality": attrs.get("municipality"),
                "municipality_short": attrs.get("municipality_short"),
                "prefecture_metadata_source": attrs.get("metadata_source"),
                "prefecture_metadata_language": attrs.get("metadata_language"),
            })
    metadata = pd.DataFrame(rows)
    required = {"poi_id", "prefecture_normalized"}
    missing = sorted(required - set(metadata.columns))
    if missing:
        raise MissingColumnsError(f"Required POI metadata columns missing from {path}: {', '.join(missing)}")
    if metadata["poi_id"].duplicated().any():
        duplicates = sorted(metadata.loc[metadata["poi_id"].duplicated(), "poi_id"].unique())
        raise MissingColumnsError(f"Duplicate poi_id values in POI metadata: {duplicates[:5]}")
    return metadata


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
    # VADER returns four scores; this project stores compound as the single
    # comparable score and keeps the component scores for audit.
    if analyzer is None:
        vader = require_dependency("vaderSentiment.vaderSentiment", "vaderSentiment")
        analyzer = vader.SentimentIntensityAnalyzer()
    scores = analyzer.polarity_scores(text or "")
    return {
        "vader_neg": float(scores["neg"]),
        "vader_neu": float(scores["neu"]),
        "vader_pos": float(scores["pos"]),
        "sentiment_score": float(scores["compound"]),
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
    # oseti returns sentence-level polarity scores, so this wrapper turns them
    # into the same row-level shape as the English scorer.
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
        "sentiment_score": doc_score,
    }


def load_reviews(
    path: Path,
    groups: list[str],
    city: str | None = None,
    prefecture: str | None = None,
    poi_metadata_path: Path = DEFAULT_POI_METADATA_PATH,
) -> pd.DataFrame:
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
    present_groups = set(df["language_group"].dropna().astype(str).str.lower())
    missing_groups = sorted(set(groups) - present_groups)
    if missing_groups:
        raise MissingGroupError(
            f"Requested language_group not present in input: {', '.join(missing_groups)}"
        )
    filtered = df[df["language_group"].astype(str).str.lower().isin(groups)].copy()
    # `copy()` avoids pandas "view versus copy" ambiguity before we add/convert
    # columns later in this function.
    if prefecture:
        # Prefecture filtering depends on POI metadata because the review file only stores poi_id.
        if "poi_id" not in filtered.columns:
            raise MissingColumnsError("Prefecture filtering requires reviews column: poi_id")
        metadata = load_poi_metadata(poi_metadata_path)
        # many_to_one means many review rows may point to one POI, but each POI
        # id in metadata must appear once. Pandas raises if that is not true.
        filtered = filtered.merge(metadata, on="poi_id", how="left", validate="many_to_one")
        missing_metadata = filtered["prefecture_normalized"].isna()
        if missing_metadata.any():
            missing_count = int(missing_metadata.sum())
            raise MissingColumnsError(
                f"POI metadata missing for {missing_count} requested review rows; "
                "prefecture filtering would be incomplete."
            )
        filtered = filtered[filtered["prefecture_normalized"].astype(str) == prefecture].copy()
    if city:
        filtered = filtered[filtered["city"].astype(str) == city].copy()
    filtered["language_group"] = filtered["language_group"].astype(str).str.lower()
    if filtered.empty:
        raise MissingGroupError(
            f"No rows after filters: city == {city!r}, prefecture == {prefecture!r}, "
            f"language_group in {groups!r}"
        )
    filtered["review_rating"] = pd.to_numeric(filtered["review_rating"], errors="coerce")
    return filtered


def score_reviews(
    reviews: pd.DataFrame,
    english_scorer: Callable[[str], dict[str, object]] | None = None,
    japanese_scorer: Callable[[str], dict[str, object]] | None = None,
) -> pd.DataFrame:
    if english_scorer is None:
        # Build the analyzer once and reuse it for every English row.
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
        # Preserve the original review columns and add sentiment-only outputs alongside them.
        language = row["language_group"]
        text = "" if pd.isna(row["review_text"]) else str(row["review_text"])
        base = {column: row[column] if column in reviews.columns else None for column in OPTIONAL_ROW_COLUMNS}
        # Length is safe to store because it is metadata about text, not the text.
        base["text_length_chars"] = len(text)
        if language == "english":
            scored = english_scorer(text)
        elif language == "japanese":
            scored = japanese_scorer(text)
        else:
            raise MissingGroupError(f"Scoring not implemented for language_group: {language}")
        base.update(scored)
        base["sentiment_category"] = sentiment_category(float(base["sentiment_score"]))
        for label, band in SENSITIVITY_BANDS.items():
            # Sensitivity categories let the paper/report show whether results
            # change when the neutral band is widened.
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
    # This function is the tracked aggregate layer: counts, means, medians,
    # percentages, and rating distributions only.
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
    rng = np.random.default_rng(seed)
    # Standard row-level bootstrap: resample each side independently, then compare.
    observed = float(reducer(left) - reducer(right))
    diffs = []
    for _ in range(iterations):
        # Resampling with replacement simulates rerunning the study on another
        # sample of the same size.
        sample_left = rng.choice(left, size=len(left), replace=True)
        sample_right = rng.choice(right, size=len(right), replace=True)
        diffs.append(float(reducer(sample_left) - reducer(sample_right)))
    lower, upper = np.percentile(diffs, [2.5, 97.5])
    return observed, float(lower), float(upper)


def _cluster_bootstrap_mean_diff(
    scored: pd.DataFrame,
    left_name: str,
    right_name: str,
    seed: int = BOOTSTRAP_SEED,
    iterations: int = BOOTSTRAP_ITERATIONS,
) -> tuple[float, float, float, int, int]:
    work = scored[["language_group", "poi_id", "sentiment_score"]].dropna().copy()
    work["poi_id"] = work["poi_id"].astype(str)
    # Resample by POI cluster so repeated reviews from one place stay together.
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
        # Sample POIs, then concatenate their review rows. This keeps within-POI
        # clustering visible in the uncertainty estimate.
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


def build_tests(scored: pd.DataFrame) -> pd.DataFrame:
    # Returns one row per statistical check. Tests can be "ok" or "skipped" so
    # reports explain why a check was not meaningful.
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
    left = scored.loc[scored["language_group"] == left_name, "sentiment_score"].dropna().to_numpy()
    right = scored.loc[scored["language_group"] == right_name, "sentiment_score"].dropna().to_numpy()
    # `left` and `right` are plain NumPy arrays because scipy functions expect
    # numeric array-like inputs.
    comparison = f"{left_name}_vs_{right_name}"

    table = pd.crosstab(scored["language_group"], scored["sentiment_category"])
    # crosstab counts how many negative/neutral/positive rows each language has.
    # Compare category shares first, then add score-based and sensitivity checks.
    for category in ["negative", "neutral", "positive"]:
        if category not in table.columns:
            table[category] = 0
    table = table[["negative", "neutral", "positive"]]
    table = table.loc[:, table.sum(axis=0) > 0]
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

    mann = stats.mannwhitneyu(left, right, alternative="two-sided")
    # Mann-Whitney compares score distributions without assuming normality.
    rows.append({
        "test_name": "mann_whitney_u_sentiment_score",
        "comparison": comparison,
        "status": "ok",
        "statistic": float(mann.statistic),
        "p_value": float(mann.pvalue),
        "effect": np.nan,
        "details_json": json.dumps({"left": left_name, "right": right_name}),
    })

    for name, reducer in [("mean", np.mean), ("median", np.median)]:
        # Bootstrap both mean and median because they answer slightly different
        # robustness questions.
        observed, lower, upper = _bootstrap_diff(left, right, reducer)
        rows.append({
            "test_name": f"bootstrap_{name}_difference_sentiment_score",
            "comparison": comparison,
            "status": "ok",
            "statistic": observed,
            "p_value": np.nan,
            "effect": observed,
            "details_json": json.dumps({
                "left": left_name,
                "right": right_name,
                "ci_95_lower": lower,
                "ci_95_upper": upper,
                "iterations": BOOTSTRAP_ITERATIONS,
                "seed": BOOTSTRAP_SEED,
            }),
        })

    poi_scores = _poi_level_scores(scored)
    # POI-level checks reduce nested review rows to one value per POI.
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
                "left": left_name,
                "right": right_name,
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
                "left": left_name,
                "right": right_name,
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
            "left": left_name,
            "right": right_name,
            "ci_95_lower": lower,
            "ci_95_upper": upper,
            "left_n_poi": int(left_n_clusters),
            "right_n_poi": int(right_n_clusters),
            "iterations": BOOTSTRAP_ITERATIONS,
            "seed": BOOTSTRAP_SEED,
            "unit": "POI cluster resampling with review rows retained inside sampled clusters",
        }),
    })

    rating_work = scored[["language_group", "review_rating", "sentiment_score"]].dropna()
    if len(rating_work) >= 3:
        # This is a light validation check, not a causal model.
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
    # Prevent row-level text and IDs from leaking into tracked aggregate outputs.
    forbidden = sorted(FORBIDDEN_AGGREGATE_COLUMNS & set(df.columns))
    if forbidden:
        raise SentimentPipelineError(
            f"Aggregate output contains forbidden row-level/PII columns: {', '.join(forbidden)}"
        )


def write_readiness(report: dict, summary: pd.DataFrame, tests: pd.DataFrame, path: Path) -> None:
    # Write a human-readable summary of inputs, denominators, and caveats.
    lines = [
        "# Sentiment Readiness",
        "",
        f"- generated_at: {report['generated_at']}",
        f"- command: `{report['command']}`",
        f"- input: `{report['input']['path']}`",
        f"- input_sha256: `{report['input']['sha256']}`",
        f"- poi_metadata: `{report['input']['poi_metadata_path']}`",
        f"- poi_metadata_sha256: `{report['input']['poi_metadata_sha256']}`",
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
        "- VADER and oseti scores are tool-specific. Main comparison uses category shares and score distributions.",
        "- `review_rating` is validation evidence only, not a covariate in this skeleton.",
        "- POI-level and cluster-bootstrap rows are sensitivity checks, not replacement primary models.",
        "- Reviewed JP/EN codebook evidence path is pending and does not block this library comparison.",
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
    groups = groups or ["japanese", "english"]
    # Keep the provenance hashes with the run so outputs can be traced back to inputs.
    input_hash = sha256_file(paths.reviews_path) if paths.reviews_path.exists() else None
    metadata_hash = sha256_file(paths.poi_metadata_path) if prefecture and paths.poi_metadata_path.exists() else None
    reviews = load_reviews(
        paths.reviews_path,
        groups,
        city=city,
        prefecture=prefecture,
        poi_metadata_path=paths.poi_metadata_path,
    )
    scored = score_reviews(reviews, english_scorer=english_scorer, japanese_scorer=japanese_scorer)

    paths.row_output_dir.mkdir(parents=True, exist_ok=True)
    paths.aggregate_output_dir.mkdir(parents=True, exist_ok=True)
    scope = prefecture or city or "all"
    row_path = paths.row_output_dir / f"google_reviews_{scope.lower()}_{'-'.join(groups)}.csv"
    scored.to_csv(row_path, index=False)
    row_hash = sha256_file(row_path)

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
    report = {
        "generated_at": dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat(),
        "command": command or " ".join(sys.argv),
        "filters": {"city": city, "prefecture": prefecture, "groups": groups},
        "primary_unit": "one Google review row",
        "codebook_evidence_status": "pending",
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
    manifest_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    write_readiness(report, summary, tests, readiness_path)
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reviews-path", type=Path, default=DEFAULT_REVIEWS_PATH)
    parser.add_argument("--poi-metadata-path", type=Path, default=DEFAULT_POI_METADATA_PATH)
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
