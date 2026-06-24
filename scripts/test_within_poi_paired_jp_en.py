#!/usr/bin/env python3
"""
Within-POI paired JP/EN robustness check for Fukui Google reviews.

This script compares English-language and Japanese-language Google reviews
within shared Fukui POIs. The primary outcome is per-POI mean review_rating.
The optional secondary row uses per-POI positive share from sentiment_category.

Framing: this is a robustness check that accounts for venue clustering, not a
confirmatory replacement for H1-H3.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.hypothesis_test_common import (
    DEFAULT_GROUPS,
    group_denominators,
    load_scored_reviews,
    parse_common_args,
    default_command,
    generated_at as generated_at_now,
    write_csv,
    write_manifest,
)

REQUIRED_COLUMNS = {"poi_id", "review_rating", "language_group", "sentiment_category"}
INPUT_PATH = Path(__file__).resolve().parent.parent / "output" / "sentiment_row_level" / "google_reviews_fukui_japanese-english.csv"
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "output" / "hypothesis_tests"
OUTPUT_CSV = OUTPUT_DIR / "within_poi_paired_jp_en.csv"
OUTPUT_MANIFEST = OUTPUT_DIR / "within_poi_paired_jp_en_manifest.json"
COMPARISON = "english_vs_japanese_within_shared_fukui_poi"
MIN_EN_REVIEWS = 5
MIN_JP_REVIEWS = 5

WITHIN_POI_CAVEATS = [
    "Group labels describe review language, not reviewer nationality.",
    "Within-POI paired robustness check: unit = POI pair. Effective N is the paired-POI count, not review rows. Small N, low power - a non-significant result is not evidence of no difference. Conditions on shared venues but does not balance review counts within each POI.",
    "Positive-share paired row is a secondary library sentiment-category check; VADER and oseti raw scores are not treated as equivalent measurement scales.",
    "Outputs are aggregate-only and omit row-level text, author fields, URLs, source IDs, review IDs, place IDs, and POI IDs.",
]


def paired_poi_test(
    df: pd.DataFrame,
    *,
    outcome: str = "rating",
    min_en_reviews: int = MIN_EN_REVIEWS,
    min_jp_reviews: int = MIN_JP_REVIEWS,
) -> dict:
    """Run a paired Wilcoxon test on POI-level EN minus JP differences."""
    if outcome not in {"rating", "positive_share"}:
        raise ValueError(f"Unsupported outcome: {outcome}")

    data = df.copy()
    data["language_group"] = data["language_group"].astype(str).str.lower()
    data = data[data["poi_id"].notna()].copy()
    data["poi_id"] = data["poi_id"].astype(str)
    data["review_rating"] = pd.to_numeric(data["review_rating"], errors="coerce")
    data["is_positive"] = (
        data["sentiment_category"].astype(str).str.lower() == "positive"
    ).astype(int)
    value_column = "review_rating" if outcome == "rating" else "is_positive"

    english = data[data["language_group"] == "english"]
    japanese = data[data["language_group"] == "japanese"]
    english_counts = english.groupby("poi_id").size()
    japanese_counts = japanese.groupby("poi_id").size()
    shared_candidates = set(english_counts.index) & set(japanese_counts.index)
    keep = (
        set(english_counts[english_counts >= min_en_reviews].index)
        & set(japanese_counts[japanese_counts >= min_jp_reviews].index)
    )

    english_values = english[english["poi_id"].isin(keep)].groupby("poi_id")[value_column].mean()
    japanese_values = japanese[japanese["poi_id"].isin(keep)].groupby("poi_id")[value_column].mean()
    paired = pd.concat({"en": english_values, "jp": japanese_values}, axis=1).dropna()
    paired_pois = set(paired.index)
    diff = (paired["en"] - paired["jp"]).to_numpy(dtype=float)
    n_pairs = int(len(diff))
    n_zero = int((diff == 0).sum())

    result = {
        "outcome": outcome,
        "threshold_min_en_reviews": int(min_en_reviews),
        "threshold_min_jp_reviews": int(min_jp_reviews),
        "n_pairs": n_pairs,
        "n_zero": n_zero,
        "n_shared_poi_candidates": int(len(shared_candidates)),
        "n_english_reviews_paired": int(english["poi_id"].isin(paired_pois).sum()),
        "n_japanese_reviews_paired": int(japanese["poi_id"].isin(paired_pois).sum()),
        "median_diff_en_minus_jp": float(np.median(diff)) if n_pairs else None,
        "unit": "POI pair",
    }
    if n_pairs < 6:
        result.update({
            "status": "skipped",
            "statistic": None,
            "p_value": None,
            "reason": "fewer than 6 POI pairs",
        })
        return result
    if n_zero == n_pairs:
        result.update({
            "status": "skipped",
            "statistic": None,
            "p_value": None,
            "reason": "all paired differences are zero",
        })
        return result

    wilcoxon = stats.wilcoxon(diff, zero_method="wilcox", alternative="two-sided")
    result.update({
        "status": "ok",
        "statistic": float(wilcoxon.statistic),
        "p_value": float(wilcoxon.pvalue),
    })
    return result


def _result_row(test_name: str, result: dict) -> dict:
    effect = result.get("median_diff_en_minus_jp")
    details = {
        "outcome": result["outcome"],
        "threshold_min_en_reviews": result["threshold_min_en_reviews"],
        "threshold_min_jp_reviews": result["threshold_min_jp_reviews"],
        "n_pairs": result["n_pairs"],
        "n_zero": result["n_zero"],
        "n_shared_poi_candidates": result["n_shared_poi_candidates"],
        "n_english_reviews_paired": result["n_english_reviews_paired"],
        "n_japanese_reviews_paired": result["n_japanese_reviews_paired"],
        "median_diff_en_minus_jp": result["median_diff_en_minus_jp"],
        "unit": result["unit"],
    }
    if result["status"] == "skipped":
        details["reason"] = result.get("reason")

    return {
        "test_name": test_name,
        "comparison": COMPARISON,
        "status": result["status"],
        "statistic": result.get("statistic"),
        "p_value": result.get("p_value"),
        "effect": effect,
        "details_json": json.dumps(details, sort_keys=True),
    }


def build_within_poi_paired_jp_en(
    input_path: Path = INPUT_PATH,
    output_dir: Path = OUTPUT_DIR,
    command: str | None = None,
) -> dict:
    df = load_scored_reviews(input_path, REQUIRED_COLUMNS)
    command = command or default_command("test_within_poi_paired_jp_en.py")
    generated_at = generated_at_now()

    rating_result = paired_poi_test(df, outcome="rating", min_en_reviews=MIN_EN_REVIEWS)
    positive_result = paired_poi_test(df, outcome="positive_share", min_en_reviews=MIN_EN_REVIEWS)
    rows = [
        _result_row("within_poi_paired_rating", rating_result),
        _result_row("within_poi_paired_positive_share", positive_result),
    ]

    out = pd.DataFrame(rows, columns=[
        "test_name",
        "comparison",
        "status",
        "statistic",
        "p_value",
        "effect",
        "details_json",
    ])
    output_csv = output_dir / OUTPUT_CSV.name
    output_manifest = output_dir / OUTPUT_MANIFEST.name
    write_csv(out, output_csv)
    manifest = write_manifest(
        kind="hypothesis_within_poi_paired_jp_en",
        command=command,
        generated=generated_at,
        input_path=input_path,
        output_csv=output_csv,
        manifest_path=output_manifest,
        metrics={
            "analysis": "within-POI paired robustness check",
            "primary_unit": "POI pair",
            "denominators": group_denominators(df),
            "threshold_min_en_reviews": MIN_EN_REVIEWS,
            "threshold_min_jp_reviews": MIN_JP_REVIEWS,
            "rating": {
                "n_pairs": rating_result["n_pairs"],
                "n_zero": rating_result["n_zero"],
                "n_shared_poi_candidates": rating_result["n_shared_poi_candidates"],
                "n_english_reviews_paired": rating_result["n_english_reviews_paired"],
                "n_japanese_reviews_paired": rating_result["n_japanese_reviews_paired"],
                "median_diff_en_minus_jp": rating_result["median_diff_en_minus_jp"],
                "status": rating_result["status"],
            },
            "positive_share": {
                "n_pairs": positive_result["n_pairs"],
                "n_zero": positive_result["n_zero"],
                "n_shared_poi_candidates": positive_result["n_shared_poi_candidates"],
                "n_english_reviews_paired": positive_result["n_english_reviews_paired"],
                "n_japanese_reviews_paired": positive_result["n_japanese_reviews_paired"],
                "median_diff_en_minus_jp": positive_result["median_diff_en_minus_jp"],
                "status": positive_result["status"],
            },
        },
        caveats=WITHIN_POI_CAVEATS,
    )
    return {"csv": str(output_csv), "manifest": str(output_manifest), "rows": len(out), "provenance": manifest}


def main() -> None:
    args = parse_common_args(__doc__ or "Run within-POI paired JP/EN robustness check.")
    report = build_within_poi_paired_jp_en(input_path=args.input, output_dir=args.output_dir)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
