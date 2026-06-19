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

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.utils.logger import setup_logger

logger = setup_logger(__name__)

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_REVIEWS_PATH = ROOT / "output" / "multilingual_review_analysis" / "reviews_multilingual.csv"
DEFAULT_CHINESE_PATH = ROOT / "output" / "chinese_social_media_analysis" / "tagged_chinese_social_posts.csv"
DEFAULT_POI_METADATA_PATH = ROOT / "output" / "checkpoints" / "poi_metadata.json"
DEFAULT_OUTPUT_DIR = ROOT / "output" / "cross_language_trends"

REVIEW_GROUPS = ["english", "japanese"]
CHINESE_GROUP = "chinese_social"
NEIGHBORING_PREFECTURE_SCAFFOLD = ["Ishikawa", "Toyama"]

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
    _require_input(path, "multilingual-reviews")
    raw = json.loads(path.read_text(encoding="utf-8"))
    rows = []
    for poi_id, attrs in raw.items():
        # Keep only the fields needed for prefecture scoping and simple output labels.
        rows.append({
            "poi_id": str(poi_id),
            "prefecture_normalized": attrs.get("prefecture_normalized") or attrs.get("prefecture"),
            "municipality": attrs.get("municipality") or attrs.get("municipality_short"),
        })
    metadata = pd.DataFrame(rows)
    if metadata.empty or "prefecture_normalized" not in metadata.columns:
        # Without prefecture data, Fukui-only filtering would be unreliable.
        raise MissingInputError(f"POI metadata missing prefecture_normalized values: {path}")
    return metadata


def load_review_rows(path: Path, poi_metadata_path: Path, prefecture: str) -> pd.DataFrame:
    # Load Google reviews, keep only English/Japanese groups, then attach POI
    # metadata so the prefecture filter does not rely on city text.
    df = pd.read_csv(path)
    df = df[df["language_group"].astype(str).str.lower().isin(REVIEW_GROUPS)].copy()
    metadata = load_poi_metadata(poi_metadata_path)
    df = df.merge(metadata, on="poi_id", how="left", validate="many_to_one")
    missing = df["prefecture_normalized"].isna()
    if missing.any():
        missing_ids = sorted(df.loc[missing, "poi_id"].astype(str).unique())[:5]
        raise MissingInputError(
            "Review rows missing POI prefecture metadata; rerun `make multilingual-reviews`. "
            f"Example poi_id values: {missing_ids}"
        )
    scoped = df[df["prefecture_normalized"].astype(str) == prefecture].copy()
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
    scoped = df[df["city"].astype(str) == prefecture].copy()
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
        f"- Neighboring-prefecture scaffold kept for later: {report['neighboring_prefecture_scaffold']}",
        "",
        "## Current Decision",
        "",
        "- Monthly trend analysis is not worthwhile yet for the Chinese layer. "
        "Most Chinese rows use inferred dates, and Douyin comment dates are anchored to scrape/parser context rather than exact platform timestamps.",
        "- Current output is aggregate baseline only: source volumes, Google rating mean, and Chinese SnowNLP sentiment summary by platform.",
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
        "- Chinese sentiment uses SnowNLP as the current baseline; Google ratings are a separate measurement instrument.",
        "- Neighboring prefectures remain scaffolded for later work, but current default output is Fukui-only.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def build_cross_language_trends(
    reviews_path: Path = DEFAULT_REVIEWS_PATH,
    chinese_path: Path = DEFAULT_CHINESE_PATH,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    poi_metadata_path: Path = DEFAULT_POI_METADATA_PATH,
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

    # All outputs are aggregate/readiness files; no row-level text is written here.
    baseline_path = output_dir / "cross_language_baseline_snapshot.csv"
    date_scrub_path = output_dir / "date_scrub_requirements.csv"
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

    report = {
        "prefecture": prefecture,
        "neighboring_prefecture_scaffold": NEIGHBORING_PREFECTURE_SCAFFOLD,
        "reviews_input": str(reviews_path),
        "poi_metadata_input": str(poi_metadata_path),
        "chinese_input": str(chinese_path),
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
            "cross_language_trends_readiness": str(report_md_path),
        },
    }
    report_json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_readiness(report, report_md_path)
    return report


def parse_args() -> argparse.Namespace:
    # Convert command-line strings into typed Path/default values.
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reviews-path", type=Path, default=DEFAULT_REVIEWS_PATH)
    parser.add_argument("--chinese-path", type=Path, default=DEFAULT_CHINESE_PATH)
    parser.add_argument("--poi-metadata-path", type=Path, default=DEFAULT_POI_METADATA_PATH)
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
