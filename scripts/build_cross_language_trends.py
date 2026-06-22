#!/usr/bin/env python3
"""
Build Fukui-first cross-language baseline tables (group project).

Compares English-language Google reviews, Japanese-language Google reviews,
and Chinese social-media posts at aggregate level. Monthly trend output is
intentionally disabled until Chinese post dates are scrubbed enough for time
series use.

Inputs:

  - `make multilingual-reviews` -> output/multilingual_review_analysis/reviews_multilingual.csv
  - `make chinese-social`       -> output/chinese_social_media_analysis/tagged_chinese_social_posts.csv

Google review scope is filtered by checkpoint POI prefecture metadata. The
default is Fukui; the same scaffold can later run for Ishikawa or Toyama once
matching Chinese social inputs exist.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd
from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.utils.logger import setup_logger
from src.provenance import file_record, research_manifest, sha256_file, write_json
from src.scope import (
    MissingScopeColumnsError,
    MissingScopeInputError,
    load_poi_scope_metadata,
    scope_reviews_by_poi_prefecture,
    scope_rows_by_source_city_label,
)

logger = setup_logger(__name__)

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_REVIEWS_PATH = ROOT / "output" / "multilingual_review_analysis" / "reviews_multilingual.csv"
DEFAULT_CHINESE_PATH = ROOT / "output" / "chinese_social_media_analysis" / "tagged_chinese_social_posts.csv"
DEFAULT_POI_METADATA_PATH = ROOT / "output" / "checkpoints" / "poi_metadata.json"
DEFAULT_SENTIMENT_SUMMARY_PATH = ROOT / "output" / "sentiment_aggregates" / "source_group_sentiment_summary.csv"
DEFAULT_OUTPUT_DIR = ROOT / "output" / "cross_language_trends"

REVIEW_GROUPS = ["english", "japanese"]
CHINESE_GROUP = "chinese_social"
NEIGHBORING_PREFECTURE_SCAFFOLD = ["Ishikawa", "Toyama"]
CATEGORY_ORDER = ["negative", "neutral", "positive"]

BASELINE_COLUMNS = [
    # Columns in the aggregate baseline CSV. Each row is a language/source
    # group inside one city/prefecture bucket.
    "prefecture",
    "city",
    "group",
    "source_kind",
    "volume",
    "rating_mean",
    "sentiment_norm_mean",
    "positive_pct",
    "neutral_pct",
    "negative_pct",
]

DATE_SCRUB_COLUMNS = [
    # Columns in the date-readiness CSV. This replaces weak monthly trend output.
    "source_kind",
    "date_precision",
    "count",
    "pct_rows",
    "usable_for_monthly_trends",
    "scrub_required",
]

TEST_COLUMNS = [
    "test_name",
    "comparison",
    "status",
    "statistic",
    "p_value",
    "effect",
    "details_json",
]


class MissingInputError(RuntimeError):
    pass


def _require_input(path: Path, make_target: str) -> None:
    # Fail loudly if the upstream build step has not created the required file yet.
    if not path.exists():
        raise MissingInputError(
            f"Required input not found: {path}\n"
            f"Generate it first with `make {make_target}`. "
            "This pipeline has no demo mode."
        )


def load_poi_metadata(path: Path) -> pd.DataFrame:
    # POI metadata is the authority for prefecture scoping.
    try:
        return load_poi_scope_metadata(path)
    except MissingScopeInputError as error:
        raise MissingInputError(
            f"Required input not found: {path}\n"
            "Generate it first with `make multilingual-reviews`. "
            "This pipeline has no demo mode."
        ) from error
    except MissingScopeColumnsError as error:
        raise MissingInputError(str(error)) from error


def load_review_rows(path: Path, poi_metadata_path: Path, prefecture: str) -> pd.DataFrame:
    # Load Google reviews, keep only English/Japanese groups, then attach POI
    # metadata so the prefecture filter does not rely on city text.
    df = pd.read_csv(path)
    df = df[df["language_group"].astype(str).str.lower().isin(REVIEW_GROUPS)].copy()
    metadata = load_poi_metadata(poi_metadata_path)
    try:
        scoped = scope_reviews_by_poi_prefecture(df, metadata, prefecture)
    except MissingScopeColumnsError as error:
        raise MissingInputError(
            "Review rows missing POI prefecture metadata; rerun `make multilingual-reviews`. "
            f"{error}"
        ) from error
    # Normalize numeric/date-like columns before any aggregate calculation happens.
    scoped["review_rating"] = pd.to_numeric(scoped.get("review_rating"), errors="coerce")
    scoped["review_date_present"] = pd.to_datetime(scoped.get("review_date"), errors="coerce", utc=True).notna()
    scoped["language_group"] = scoped["language_group"].astype(str).str.lower()
    return scoped


def load_chinese_rows(path: Path, prefecture: str) -> pd.DataFrame:
    # Load ignored row-level Chinese output created by `make chinese-social`.
    df = pd.read_csv(path)
    if df.empty:
        return df
    try:
        scoped = scope_rows_by_source_city_label(df, prefecture)
    except MissingScopeColumnsError as error:
        raise MissingInputError(str(error)) from error
    # Leave the Chinese layer in its original shape except for the columns used here.
    scoped["sentiment_norm"] = pd.to_numeric(scoped.get("sentiment_norm"), errors="coerce")
    if "sentiment_category" not in scoped.columns:
        scoped["sentiment_category"] = "unknown"
    if "post_date_precision" not in scoped.columns:
        scoped["post_date_precision"] = "none"
    return scoped


def _pct(count: int, denominator: int) -> float:
    # Use percentages in the readiness table so the denominator is easy to read.
    return round(100 * count / denominator, 3) if denominator else 0.0


def baseline_snapshot(reviews: pd.DataFrame, chinese: pd.DataFrame, prefecture: str) -> pd.DataFrame:
    # Build one combined table for presentation-safe headline numbers.
    rows = []
    for (city, group), chunk in reviews.groupby(["city", "language_group"], dropna=False):
        denominator = len(chunk)
        # One row per city/language bucket keeps the baseline compact and comparable.
        rows.append({
            "prefecture": prefecture,
            "city": city,
            "group": group,
            "source_kind": "google_review",
            "volume": denominator,
            "rating_mean": round(float(chunk["review_rating"].mean()), 4)
            if chunk["review_rating"].notna().any() else None,
            "sentiment_norm_mean": None,
            "positive_pct": None,
            "neutral_pct": None,
            "negative_pct": None,
        })
    if not chinese.empty:
        for (city, platform), chunk in chinese.groupby(["city", "source_platform"], dropna=False):
            denominator = len(chunk)
            categories = chunk["sentiment_category"].fillna("unknown").astype(str)
            # Keep Xiaohongshu and Douyin separate so platform differences stay visible.
            rows.append({
                "prefecture": prefecture,
                "city": city,
                "group": f"{CHINESE_GROUP}_{platform}",
                "source_kind": "chinese_social_post",
                "volume": denominator,
                "rating_mean": None,
                "sentiment_norm_mean": round(float(chunk["sentiment_norm"].mean()), 6)
                if chunk["sentiment_norm"].notna().any() else None,
                "positive_pct": _pct(int((categories == "positive").sum()), denominator),
                "neutral_pct": _pct(int((categories == "neutral").sum()), denominator),
                "negative_pct": _pct(int((categories == "negative").sum()), denominator),
            })
    return pd.DataFrame(rows, columns=BASELINE_COLUMNS).sort_values(
        ["prefecture", "city", "source_kind", "group"]
    ).reset_index(drop=True)


def date_scrub_requirements(reviews: pd.DataFrame, chinese: pd.DataFrame) -> pd.DataFrame:
    # Explain which rows are safe for monthly trends and which need date repair.
    rows = []
    if len(reviews):
        present = int(reviews["review_date_present"].sum())
        missing = len(reviews) - present
        # Split Google review rows into usable and unusable date buckets.
        rows.extend([
            {
                "source_kind": "google_review",
                "date_precision": "exact_or_provider_timestamp",
                "count": present,
                "pct_rows": _pct(present, len(reviews)),
                "usable_for_monthly_trends": True,
                "scrub_required": "Keep provider review_date, collection_date, POI metadata, and language filter hashes.",
            },
            {
                "source_kind": "google_review",
                "date_precision": "missing_or_unparseable",
                "count": missing,
                "pct_rows": _pct(missing, len(reviews)),
                "usable_for_monthly_trends": False,
                "scrub_required": "Exclude or repair before monthly trend output.",
            },
        ])
    if len(chinese):
        counts = chinese["post_date_precision"].fillna("none").astype(str).value_counts()
        for precision, count in counts.items():
            usable = precision == "exact"
            # Only exact Chinese post dates are ready for a monthly trend pipeline.
            if usable:
                scrub = "Keep only rows with exact platform post dates for monthly trend output."
            elif precision == "year_inferred":
                scrub = "Recover exact source post date or exclude from monthly trend output."
            elif precision == "relative_inferred":
                scrub = "Recover absolute source post date from capture evidence; current scrape-anchored dates are not monthly-trend evidence."
            else:
                scrub = "Recover source post date or exclude from monthly trend output."
            rows.append({
                "source_kind": "chinese_social_post",
                "date_precision": precision,
                "count": int(count),
                "pct_rows": _pct(int(count), len(chinese)),
                "usable_for_monthly_trends": usable,
                "scrub_required": scrub,
            })
    return pd.DataFrame(rows, columns=DATE_SCRUB_COLUMNS)


def _cramers_v(table: pd.DataFrame) -> float | None:
    chi2, _, _, _ = stats.chi2_contingency(table)
    n = float(table.to_numpy().sum())
    if n == 0:
        return None
    r, k = table.shape
    denom = n * min(k - 1, r - 1)
    return float((chi2 / denom) ** 0.5) if denom else None


def _category_count_row(group: str, source_kind: str, row_unit: str, categories: pd.Series) -> dict:
    values = categories.fillna("unknown").astype(str).str.lower()
    row = {
        "group": group,
        "source_kind": source_kind,
        "row_unit": row_unit,
        "denominator": int(values.isin(CATEGORY_ORDER).sum()),
    }
    for category in CATEGORY_ORDER:
        row[category] = int((values == category).sum())
    return row


def _review_sentiment_count_rows(sentiment_summary_path: Path, prefecture: str) -> tuple[list[dict], dict | None]:
    if not sentiment_summary_path.exists():
        return [], {
            "reason": "JP/EN sentiment summary missing; run `make sentiment-analysis` first",
            "sentiment_summary_path": str(sentiment_summary_path),
        }
    summary = pd.read_csv(sentiment_summary_path)
    if "prefecture_normalized" in summary.columns:
        summary = summary[summary["prefecture_normalized"].astype(str) == prefecture].copy()
    rows = []
    for _, item in summary.iterrows():
        language = str(item.get("language_group", "")).lower()
        if language not in REVIEW_GROUPS:
            continue
        row = {
            "group": f"google_review_{language}",
            "source_kind": "google_review",
            "row_unit": "one Google review",
            "denominator": int(item.get("n_scored", item.get("n_reviews", 0))),
        }
        for category in CATEGORY_ORDER:
            row[category] = int(item.get(f"{category}_count", 0))
        rows.append(row)
    if not rows:
        return [], {
            "reason": "JP/EN sentiment summary contains no scoped English/Japanese rows",
            "sentiment_summary_path": str(sentiment_summary_path),
            "prefecture": prefecture,
        }
    return rows, None


def _chinese_sentiment_count_rows(chinese: pd.DataFrame) -> list[dict]:
    if chinese.empty or "sentiment_category" not in chinese.columns:
        return []
    rows = [
        _category_count_row(
            "chinese_social_all",
            "chinese_social_media",
            "one Xiaohongshu note or Douyin comment row",
            chinese["sentiment_category"],
        )
    ]
    if "source_platform" in chinese.columns:
        for platform, chunk in chinese.groupby("source_platform", dropna=False):
            rows.append(_category_count_row(
                f"chinese_social_{platform}",
                "chinese_social_media",
                "one source-platform row",
                chunk["sentiment_category"],
            ))
    return rows


def _category_test_row(
    count_rows: list[dict],
    groups: list[str],
    test_name: str,
    comparison: str,
    extra_details: dict | None = None,
) -> dict:
    selected = [row for row in count_rows if row["group"] in groups]
    if len(selected) < len(groups):
        return {
            "test_name": test_name,
            "comparison": comparison,
            "status": "skipped",
            "statistic": None,
            "p_value": None,
            "effect": None,
            "details_json": json.dumps({
                "reason": "required groups missing",
                "requested_groups": groups,
                "available_groups": [row["group"] for row in count_rows],
                **(extra_details or {}),
            }),
        }
    table = pd.DataFrame(
        [[row[category] for category in CATEGORY_ORDER] for row in selected],
        index=[row["group"] for row in selected],
        columns=CATEGORY_ORDER,
    )
    table = table.loc[:, table.sum(axis=0) > 0]
    table = table.loc[table.sum(axis=1) > 0, :]
    details = {
        "observed": table.to_dict(),
        "denominators": {row["group"]: row["denominator"] for row in selected},
        "row_units": {row["group"]: row["row_unit"] for row in selected},
        "interpretation": "Descriptive cross-source category-share comparison; source platforms and scoring tools differ.",
        **(extra_details or {}),
    }
    if table.shape[0] < 2 or table.shape[1] < 2:
        return {
            "test_name": test_name,
            "comparison": comparison,
            "status": "skipped",
            "statistic": None,
            "p_value": None,
            "effect": None,
            "details_json": json.dumps({"reason": "fewer than two non-empty groups/categories", **details}),
        }
    if table.shape == (2, 2):
        oddsratio, p_value = stats.fisher_exact(table)
        return {
            "test_name": test_name,
            "comparison": comparison,
            "status": "ok",
            "statistic": float(oddsratio),
            "p_value": float(p_value),
            "effect": None,
            "details_json": json.dumps({"method": "fisher_exact", **details}),
        }
    chi2, p_value, dof, expected = stats.chi2_contingency(table)
    return {
        "test_name": test_name,
        "comparison": comparison,
        "status": "ok",
        "statistic": float(chi2),
        "p_value": float(p_value),
        "effect": _cramers_v(table),
        "details_json": json.dumps({
            "method": "chi_square",
            "dof": int(dof),
            "expected": pd.DataFrame(expected, index=table.index, columns=table.columns).round(6).to_dict(),
            **details,
        }),
    }


def _coerce_bool(value: object) -> bool | None:
    if pd.isna(value):
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "y"}:
        return True
    if text in {"false", "0", "no", "n", ""}:
        return False
    return bool(text)


def _binary_prevalence_test(
    df: pd.DataFrame,
    group_col: str,
    value_col: str,
    test_name: str,
    comparison: str,
    details: dict | None = None,
) -> dict:
    if df.empty or group_col not in df.columns or value_col not in df.columns:
        return {
            "test_name": test_name,
            "comparison": comparison,
            "status": "skipped",
            "statistic": None,
            "p_value": None,
            "effect": None,
            "details_json": json.dumps({
                "reason": "required columns missing or no rows",
                "group_col": group_col,
                "value_col": value_col,
                **(details or {}),
            }),
        }
    work = df[[group_col, value_col]].copy()
    work[value_col] = work[value_col].map(_coerce_bool)
    work = work.dropna()
    if work.empty or work[group_col].nunique(dropna=True) < 2:
        return {
            "test_name": test_name,
            "comparison": comparison,
            "status": "skipped",
            "statistic": None,
            "p_value": None,
            "effect": None,
            "details_json": json.dumps({
                "reason": "fewer than two groups with data",
                "group_col": group_col,
                "value_col": value_col,
                **(details or {}),
            }),
        }
    work[value_col] = work[value_col].map({False: "not_present", True: "present"})
    table = pd.crosstab(work[group_col].astype(str), work[value_col])
    for value in ["not_present", "present"]:
        if value not in table.columns:
            table[value] = 0
    table = table[["not_present", "present"]]
    table = table.loc[:, table.sum(axis=0) > 0]
    table = table.loc[table.sum(axis=1) > 0, :]
    base_details = {
        "observed": table.to_dict(),
        "unit": "one Chinese social-media source row",
        **(details or {}),
    }
    if table.shape[0] < 2 or table.shape[1] < 2:
        return {
            "test_name": test_name,
            "comparison": comparison,
            "status": "skipped",
            "statistic": None,
            "p_value": None,
            "effect": None,
            "details_json": json.dumps({"reason": "fewer than two non-empty groups/outcomes", **base_details}),
        }
    if table.shape == (2, 2):
        oddsratio, p_value = stats.fisher_exact(table)
        return {
            "test_name": test_name,
            "comparison": comparison,
            "status": "ok",
            "statistic": float(oddsratio),
            "p_value": float(p_value),
            "effect": None,
            "details_json": json.dumps({"method": "fisher_exact", **base_details}),
        }
    chi2, p_value, dof, expected = stats.chi2_contingency(table)
    return {
        "test_name": test_name,
        "comparison": comparison,
        "status": "ok",
        "statistic": float(chi2),
        "p_value": float(p_value),
        "effect": _cramers_v(table),
        "details_json": json.dumps({
            "method": "chi_square",
            "dof": int(dof),
            "expected": pd.DataFrame(expected, index=table.index, columns=table.columns).round(6).to_dict(),
            **base_details,
        }),
    }


def comparison_statistical_tests(
    chinese: pd.DataFrame,
    sentiment_summary_path: Path,
    prefecture: str,
) -> pd.DataFrame:
    rows = []
    review_counts, missing_review_reason = _review_sentiment_count_rows(sentiment_summary_path, prefecture)
    chinese_counts = _chinese_sentiment_count_rows(chinese)
    count_rows = review_counts + chinese_counts
    if missing_review_reason:
        rows.append({
            "test_name": "cross_source_sentiment_category_independence",
            "comparison": "google_review_english_vs_google_review_japanese_vs_chinese_social_all",
            "status": "skipped",
            "statistic": None,
            "p_value": None,
            "effect": None,
            "details_json": json.dumps(missing_review_reason),
        })
    else:
        rows.append(_category_test_row(
            count_rows,
            ["google_review_english", "google_review_japanese", "chinese_social_all"],
            "cross_source_sentiment_category_independence",
            "google_review_english_vs_google_review_japanese_vs_chinese_social_all",
        ))
        for review_group in ["google_review_english", "google_review_japanese"]:
            rows.append(_category_test_row(
                count_rows,
                [review_group, "chinese_social_all"],
                "pairwise_cross_source_sentiment_category_independence",
                f"{review_group}_vs_chinese_social_all",
            ))
    if chinese_counts:
        platform_groups = [row["group"] for row in chinese_counts if row["group"].startswith("chinese_social_") and row["group"] != "chinese_social_all"]
        rows.append(_category_test_row(
            chinese_counts,
            platform_groups,
            "within_chinese_platform_sentiment_category_independence",
            "chinese_source_platforms",
            {"platform_grouping": "source_platform"},
        ))
    else:
        rows.append({
            "test_name": "within_chinese_platform_sentiment_category_independence",
            "comparison": "chinese_source_platforms",
            "status": "skipped",
            "statistic": None,
            "p_value": None,
            "effect": None,
            "details_json": json.dumps({"reason": "Chinese sentiment_category rows missing"}),
        })

    rows.append(_binary_prevalence_test(
        chinese,
        "source_platform",
        "any_friction",
        "within_chinese_platform_any_friction_prevalence",
        "chinese_source_platforms",
        {"current_scope": "within Chinese social rows only"},
    ))
    rows.append(_binary_prevalence_test(
        chinese,
        "source_platform",
        "any_enjoyment_evidence",
        "within_chinese_platform_any_enjoyment_evidence_prevalence",
        "chinese_source_platforms",
        {"current_scope": "within Chinese social rows only"},
    ))
    for test_name, evidence_column in [
        ("cross_source_friction_prevalence_not_run", "any_friction"),
        ("cross_source_enjoyment_recommendation_prevalence_not_run", "any_enjoyment_evidence"),
    ]:
        rows.append({
            "test_name": test_name,
            "comparison": "google_review_languages_vs_chinese_social",
            "status": "skipped",
            "statistic": None,
            "p_value": None,
            "effect": None,
            "details_json": json.dumps({
                "reason": "Reviewed EN/JP keyword evidence is not ready, so cross-source evidence prevalence would not use aligned codebooks.",
                "chinese_column_ready": evidence_column in chinese.columns,
                "required_next_step": "Promote reviewed English/Japanese keyword evidence into runtime outputs, then compare aligned binary evidence rates.",
            }),
        })
    return pd.DataFrame(rows, columns=TEST_COLUMNS)


def _write_readiness(report: dict, path: Path) -> None:
    # Write a compact note for humans about what this baseline does and does not do.
    lines = [
        "# Cross-Language Baseline Readiness (Group Project)",
        "",
        "Fukui-first aggregate comparison for English-language Google reviews, "
        "Japanese-language Google reviews, and Chinese-language social-media posts. "
        "Monthly trend output is disabled for now.",
        "",
        f"- Active prefecture: {report['prefecture']}",
        f"- Review rows retained after POI-prefecture filter: {report['review_rows_retained']}",
        f"- Chinese posts retained: {report['chinese_rows_retained']}",
        f"- Statistical tests output: `{report['outputs']['cross_language_statistical_tests']}`",
        f"- Neighboring-prefecture scaffold kept for later: {report['neighboring_prefecture_scaffold']}",
        "",
        "## Current Decision",
        "",
        "- Monthly trend analysis is not worthwhile yet for the Chinese layer. "
        "Most Chinese rows use inferred dates, and Douyin comment dates are anchored to scrape/parser context rather than exact platform timestamps.",
        "- Current output is aggregate baseline only: source volumes, Google rating mean, and Chinese SnowNLP secondary sentiment summary by platform.",
        "- Current statistical tests are limited to descriptive sentiment-category shares and within-Chinese platform evidence tests. Cross-source friction/enjoyment tests are explicitly skipped until EN/JP keyword evidence is ready.",
        "",
        "## If Monthly Trends Are Reintroduced",
        "",
        "- Filter Google reviews by POI `prefecture_normalized` from `output/checkpoints/poi_metadata.json`.",
        "- Keep Chinese rows with exact platform post dates, or recover exact dates from source evidence.",
        "- Recover exact source post date for rows currently marked `year_inferred`, `relative_inferred`, or `none`; otherwise exclude them from monthly output.",
        "- Exclude `year_inferred`, `relative_inferred`, and missing Chinese dates unless separately audited.",
        "- Report date precision counts, source file hashes, collection windows, and per-platform monthly denominators.",
        "- Stratify Chinese social posts by platform; do not pool Xiaohongshu notes and Douyin comments as one time series without weighting rationale.",
        "",
        "## Caveats",
        "",
        "- Group membership is content language/source platform, not nationality.",
        "- Chinese sentiment uses SnowNLP as a secondary baseline; Google ratings are a separate measurement instrument.",
        "- Cross-source sentiment category tests compare platformed discourse categories, not direct visitor satisfaction.",
        "- Chinese social rows are Xiaohongshu notes or Douyin comments; Google rows are reviews.",
        "- Neighboring prefectures remain scaffolded for later work, but current default output is Fukui-only.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def build_cross_language_trends(
    reviews_path: Path = DEFAULT_REVIEWS_PATH,
    chinese_path: Path = DEFAULT_CHINESE_PATH,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    poi_metadata_path: Path = DEFAULT_POI_METADATA_PATH,
    sentiment_summary_path: Path = DEFAULT_SENTIMENT_SUMMARY_PATH,
    prefecture: str = "Fukui",
) -> dict:
    # Main orchestration function: validate inputs, load scoped rows, write
    # aggregate outputs, and record a manifest/readiness note.
    _require_input(reviews_path, "multilingual-reviews")
    _require_input(chinese_path, "chinese-social")
    output_dir.mkdir(parents=True, exist_ok=True)

    reviews = load_review_rows(reviews_path, poi_metadata_path, prefecture)
    chinese = load_chinese_rows(chinese_path, prefecture)

    baseline = baseline_snapshot(reviews, chinese, prefecture)
    date_scrub = date_scrub_requirements(reviews, chinese)
    statistical_tests = comparison_statistical_tests(chinese, sentiment_summary_path, prefecture)

    # All outputs are aggregate/readiness files; no row-level text is written here.
    baseline_path = output_dir / "cross_language_baseline_snapshot.csv"
    date_scrub_path = output_dir / "date_scrub_requirements.csv"
    tests_path = output_dir / "cross_language_statistical_tests.csv"
    report_json_path = output_dir / "cross_language_trends_readiness.json"
    report_md_path = output_dir / "cross_language_trends_readiness.md"
    for stale_path in [
        output_dir / "monthly_trends.csv",
        output_dir / "chinese_theme_mix_monthly.csv",
    ]:
        # Remove old monthly outputs so the directory does not suggest a result that is no longer produced.
        if stale_path.exists():
            stale_path.unlink()

    baseline.to_csv(baseline_path, index=False)
    date_scrub.to_csv(date_scrub_path, index=False)
    statistical_tests.to_csv(tests_path, index=False)

    report = {
        "schema_version": "cross_language_trends_manifest.v2",
        "prefecture": prefecture,
        "neighboring_prefecture_scaffold": NEIGHBORING_PREFECTURE_SCAFFOLD,
        "reviews_input": str(reviews_path),
        "reviews_input_sha256": sha256_file(reviews_path),
        "poi_metadata_input": str(poi_metadata_path),
        "poi_metadata_input_sha256": sha256_file(poi_metadata_path),
        "chinese_input": str(chinese_path),
        "chinese_input_sha256": sha256_file(chinese_path),
        "sentiment_summary_input": str(sentiment_summary_path),
        "sentiment_summary_input_sha256": sha256_file(sentiment_summary_path)
        if sentiment_summary_path.exists() else None,
        "review_rows_retained": int(len(reviews)),
        "chinese_rows_retained": int(len(chinese)),
        "chinese_date_precision_counts": (
            {str(k): int(v) for k, v in chinese["post_date_precision"].value_counts().items()}
            if not chinese.empty and "post_date_precision" in chinese.columns else {}
        ),
        "monthly_trends_enabled": False,
        # The disabled reason is stored in the manifest so the choice stays auditable.
        "monthly_trends_disabled_reason": (
            "Chinese post dates are mostly inferred or scrape-anchored; aggregate baseline is safer."
        ),
        "outputs": {
            "cross_language_baseline_snapshot": str(baseline_path),
            "date_scrub_requirements": str(date_scrub_path),
            "cross_language_statistical_tests": str(tests_path),
            "cross_language_trends_readiness": str(report_md_path),
        },
    }
    _write_readiness(report, report_md_path)
    report["outputs"].update({
        "cross_language_baseline_snapshot_sha256": sha256_file(baseline_path),
        "date_scrub_requirements_sha256": sha256_file(date_scrub_path),
        "cross_language_statistical_tests_sha256": sha256_file(tests_path),
        "cross_language_trends_readiness_sha256": sha256_file(report_md_path),
    })
    report["provenance"] = research_manifest(
        kind="cross_language_baseline",
        command=" ".join(sys.argv),
        filters={
            "prefecture": prefecture,
            "review_groups": REVIEW_GROUPS,
            "chinese_group": CHINESE_GROUP,
        },
        inputs=[
            file_record(reviews_path, "reviews_multilingual", required=True),
            file_record(poi_metadata_path, "poi_metadata", required=True),
            file_record(chinese_path, "tagged_chinese_social_posts", required=True),
            file_record(sentiment_summary_path, "jp_en_sentiment_summary", required=False),
        ],
        outputs=[
            file_record(baseline_path, "aggregate_cross_language_baseline", required=True),
            file_record(date_scrub_path, "aggregate_date_scrub_requirements", required=True),
            file_record(tests_path, "aggregate_cross_language_statistical_tests", required=True),
            file_record(report_md_path, "readiness_markdown", required=True),
        ],
        metrics={
            "review_rows_retained": int(len(reviews)),
            "chinese_rows_retained": int(len(chinese)),
            "review_scope_method": (
                sorted(str(value) for value in reviews["scope_method"].dropna().unique())
                if "scope_method" in reviews.columns else []
            ),
            "chinese_scope_method": (
                sorted(str(value) for value in chinese["scope_method"].dropna().unique())
                if "scope_method" in chinese.columns else []
            ),
            "monthly_trends_enabled": False,
            "chinese_date_precision_counts": report["chinese_date_precision_counts"],
            "statistical_tests": statistical_tests.to_dict(orient="records"),
        },
        caveats=[
            "Group membership is content language/source platform, not nationality.",
            "Chinese SnowNLP sentiment and Google review ratings are separate instruments.",
            "Cross-source sentiment category tests compare platformed discourse categories, not direct satisfaction.",
            "Cross-source friction/enjoyment tests are skipped until reviewed EN/JP keyword evidence is ready.",
            "Monthly trend output is disabled until Chinese post dates are exact enough.",
            "Default output is Fukui-only.",
        ],
        extra={
            "neighboring_prefecture_scaffold": NEIGHBORING_PREFECTURE_SCAFFOLD,
            "monthly_trends_disabled_reason": report["monthly_trends_disabled_reason"],
        },
    )
    write_json(report_json_path, report)
    return report


def parse_args() -> argparse.Namespace:
    # Convert command-line strings into typed Path/default values.
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reviews-path", type=Path, default=DEFAULT_REVIEWS_PATH)
    parser.add_argument("--chinese-path", type=Path, default=DEFAULT_CHINESE_PATH)
    parser.add_argument("--poi-metadata-path", type=Path, default=DEFAULT_POI_METADATA_PATH)
    parser.add_argument("--sentiment-summary-path", type=Path, default=DEFAULT_SENTIMENT_SUMMARY_PATH)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--prefecture", default="Fukui")
    return parser.parse_args()


def main() -> int:
    # CLI entrypoint: return status code 1 on known input problems.
    args = parse_args()
    try:
        report = build_cross_language_trends(
            reviews_path=args.reviews_path,
            chinese_path=args.chinese_path,
            output_dir=args.output_dir,
            poi_metadata_path=args.poi_metadata_path,
            sentiment_summary_path=args.sentiment_summary_path,
            prefecture=args.prefecture,
        )
    except MissingInputError as error:
        logger.error(str(error))
        return 1
    logger.info("Baseline rows retained: reviews=%s chinese=%s", report["review_rows_retained"], report["chinese_rows_retained"])
    logger.info("Output written: %s", args.output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
