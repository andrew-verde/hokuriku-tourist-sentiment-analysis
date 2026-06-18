#!/usr/bin/env python3
"""
Build cross-language monthly tourism-trend tables (side project).

Compares English-language Google reviewers, Japanese-language Google
reviewers, and Chinese social-media commenters (Xiaohongshu/Douyin) on
monthly volume and within-group sentiment, by city. Sentiment scales are
group-specific (Google star ratings vs Chinese keyword-lexicon polarity)
and are reported side by side, never merged.

This is a side-project deliverable separate from the tourist-friction
thesis pipeline; nothing in the thesis chain depends on these outputs.
Both inputs are row-level files produced by earlier stages:

  - `make multilingual-reviews` -> output/multilingual_review_analysis/reviews_multilingual.csv
  - `make chinese-social`       -> output/chinese_social_media_analysis/tagged_chinese_social_posts.csv

There is no demo mode: missing inputs are an error naming the command to run.
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
DEFAULT_OUTPUT_DIR = ROOT / "output" / "cross_language_trends"

REVIEW_GROUPS = ["english", "japanese"]
CHINESE_GROUP = "chinese_social"

TRENDS_COLUMNS = [
    "city",
    "group",
    "month",
    "volume",
    "rating_mean",
    "sentiment_norm_mean",
]


class MissingInputError(RuntimeError):
    pass


def _require_input(path: Path, make_target: str) -> None:
    if not path.exists():
        raise MissingInputError(
            f"Required input not found: {path}\n"
            f"Generate it first with `make {make_target}`. "
            "This pipeline has no demo mode."
        )


def _month_series(values: pd.Series) -> pd.Series:
    parsed = pd.to_datetime(values, errors="coerce", format="mixed", utc=True)
    return parsed.dt.tz_localize(None).dt.to_period("M").astype(str)


def load_review_rows(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df = df[df["language_group"].isin(REVIEW_GROUPS)].copy()
    df["month"] = _month_series(df["review_date"])
    df["rating"] = pd.to_numeric(df.get("review_rating"), errors="coerce")
    return df


def load_chinese_rows(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    if df.empty:
        return df
    df = df.copy()
    df["month"] = _month_series(df.get("post_date"))
    df["sentiment_norm"] = pd.to_numeric(df.get("sentiment_norm"), errors="coerce")
    if "theme" not in df.columns:
        df["theme"] = "unclassified"
    df["theme"] = df["theme"].fillna("unclassified")
    return df


def monthly_trends(reviews: pd.DataFrame, chinese: pd.DataFrame) -> pd.DataFrame:
    rows = []
    dated_reviews = reviews[reviews["month"].notna()]
    for (city, group, month), chunk in dated_reviews.groupby(["city", "language_group", "month"]):
        rows.append({
            "city": city,
            "group": group,
            "month": month,
            "volume": len(chunk),
            "rating_mean": round(float(chunk["rating"].mean()), 4) if chunk["rating"].notna().any() else None,
            "sentiment_norm_mean": None,
        })
    if not chinese.empty:
        dated_chinese = chinese[chinese["month"].notna()]
        for (city, month), chunk in dated_chinese.groupby(["city", "month"]):
            rows.append({
                "city": city,
                "group": CHINESE_GROUP,
                "month": month,
                "volume": len(chunk),
                "rating_mean": None,
                "sentiment_norm_mean": round(float(chunk["sentiment_norm"].mean()), 6)
                if chunk["sentiment_norm"].notna().any() else None,
            })
    trends = pd.DataFrame(rows, columns=TRENDS_COLUMNS)
    return trends.sort_values(["city", "group", "month"]).reset_index(drop=True)


def chinese_theme_mix_monthly(chinese: pd.DataFrame) -> pd.DataFrame:
    columns = ["city", "month", "theme", "count", "pct_posts"]
    if chinese.empty:
        return pd.DataFrame(columns=columns)
    dated = chinese[chinese["month"].notna()]
    rows = []
    for (city, month), chunk in dated.groupby(["city", "month"]):
        denominator = len(chunk)
        for theme, theme_chunk in chunk.groupby("theme"):
            rows.append({
                "city": city,
                "month": month,
                "theme": theme,
                "count": len(theme_chunk),
                "pct_posts": round(100 * len(theme_chunk) / denominator, 3),
            })
    return pd.DataFrame(rows, columns=columns).sort_values(["city", "month", "theme"]).reset_index(drop=True)


def _write_readiness(report: dict, path: Path) -> None:
    lines = [
        "# Cross-Language Trends Readiness (Side Project)",
        "",
        "Monthly volume and within-group sentiment for English Google reviewers, "
        "Japanese Google reviewers, and Chinese social-media commenters. "
        "Descriptive side-project comparison; not thesis evidence.",
        "",
        f"- Review rows (english/japanese, dated): {report['review_rows_dated']}",
        f"- Chinese posts total: {report['chinese_rows_total']}",
        f"- Chinese posts with a usable post_date: {report['chinese_rows_dated']}",
        f"- Chinese post_date precision mix: {report['chinese_date_precision_counts']}",
        "",
        "## Caveats",
        "",
        "- Sentiment scales are group-specific: `rating_mean` is the Google 1-5 star mean "
        "(english/japanese); `sentiment_norm_mean` is the Chinese keyword-lexicon polarity "
        "mean in [0,1]. Levels are NOT comparable across groups; only within-group "
        "trajectories are interpretable.",
        "- Chinese text is title-level and volumes are small; treat monthly Chinese cells "
        "as directional interest signals, not rates.",
        "- Chinese `post_date` values flagged `year_inferred` or `relative_inferred` were "
        "reconstructed relative to the scrape date (see chinese_social_readiness.md).",
        "- Group membership is content language, not nationality.",
        "- No significance testing is run on these series by design (descriptive scope).",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def build_cross_language_trends(
    reviews_path: Path = DEFAULT_REVIEWS_PATH,
    chinese_path: Path = DEFAULT_CHINESE_PATH,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
) -> dict:
    _require_input(reviews_path, "multilingual-reviews")
    _require_input(chinese_path, "chinese-social")
    output_dir.mkdir(parents=True, exist_ok=True)

    reviews = load_review_rows(reviews_path)
    chinese = load_chinese_rows(chinese_path)

    trends = monthly_trends(reviews, chinese)
    theme_mix = chinese_theme_mix_monthly(chinese)

    trends_path = output_dir / "monthly_trends.csv"
    theme_mix_path = output_dir / "chinese_theme_mix_monthly.csv"
    report_json_path = output_dir / "cross_language_trends_readiness.json"
    report_md_path = output_dir / "cross_language_trends_readiness.md"

    trends.to_csv(trends_path, index=False)
    theme_mix.to_csv(theme_mix_path, index=False)

    report = {
        "reviews_input": str(reviews_path),
        "chinese_input": str(chinese_path),
        "review_rows_dated": int(reviews["month"].notna().sum()),
        "chinese_rows_total": int(len(chinese)),
        "chinese_rows_dated": int(chinese["month"].notna().sum()) if not chinese.empty else 0,
        "chinese_date_precision_counts": (
            {str(k): int(v) for k, v in chinese["post_date_precision"].value_counts().items()}
            if not chinese.empty and "post_date_precision" in chinese.columns else {}
        ),
        "outputs": {
            "monthly_trends": str(trends_path),
            "chinese_theme_mix_monthly": str(theme_mix_path),
            "cross_language_trends_readiness": str(report_md_path),
        },
    }
    report_json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_readiness(report, report_md_path)
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reviews-path", type=Path, default=DEFAULT_REVIEWS_PATH)
    parser.add_argument("--chinese-path", type=Path, default=DEFAULT_CHINESE_PATH)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        report = build_cross_language_trends(
            reviews_path=args.reviews_path,
            chinese_path=args.chinese_path,
            output_dir=args.output_dir,
        )
    except MissingInputError as error:
        logger.error(str(error))
        return 1
    logger.info("Monthly trend rows: %s", report["review_rows_dated"] + report["chinese_rows_dated"])
    logger.info("Output written: %s", args.output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
