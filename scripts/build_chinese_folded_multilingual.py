#!/usr/bin/env python3
"""Promote Chinese-language Google reviews into the multilingual POI input."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from build_chinese_social_media_dataset import (  # noqa: E402
    CHINESE_GOOGLE_REVIEW_CANDIDATES_PATH,
    REVIEWED_CODEBOOK_PATH,
    _append_sentiment_fields,
    _reviewed_terms_from_codebook,
    _tag_chinese_dataframe,
    load_chinese_codebook,
)
from src.provenance import file_record, research_manifest, write_json  # noqa: E402

INPUT_PATH = ROOT / "output" / "multilingual_review_analysis" / "tagged_reviews_multilingual.csv"
OUTPUT_PATH = (
    ROOT
    / "output"
    / "multilingual_review_analysis"
    / "tagged_reviews_multilingual_chinese_folded.csv"
)
MANIFEST_PATH = (
    ROOT
    / "output"
    / "multilingual_review_analysis"
    / "tagged_reviews_multilingual_chinese_folded_manifest.json"
)

FOLD_CAVEATS = [
    "Local post-sync stage: promotes zh rows in the synced tagged_reviews_multilingual.csv to language_group='chinese'. The synced source file is never modified.",
    "CN codebook codes map onto the shared multilingual aspect columns; all 6 nudgeable-friction aspects map 1:1. Four enjoyment aspects (friendly_service, underpromoted_feature, easy_if_guided, good_for_itinerary_bundle) have no Chinese-codebook equivalent and are set to 0 for Chinese rows, so Chinese promote-it draw is under-counted relative to EN/JP.",
    "POI-level Chinese signal is thin (median ~3 reviews/POI; most POIs below LOW_CONFIDENCE_N=10). Per-POI Chinese friction should be read as directional, not confirmatory.",
]

CN_TO_ASPECT = {
    "transport_access": "transport_access",
    "wayfinding_signage": "wayfinding_signage",
    "staff_communication": "staff_communication",
    "booking_ticketing": "booking_ticketing",
    "waiting_crowding": "waiting_crowding",
    "price_value": "price_value",
    "cleanliness_comfort": "cleanliness_comfort",
    "opening_hours_availability": "opening_hours_availability",
    "itinerary_fit_time_cost": "itinerary_fit_time_cost",
    "accessibility_mobility": "accessibility_mobility",
    "food_amenities_gap": "food_amenities_gap",
    "language_information_gap": "english_information_gap",
    "scenic_nature": "scenic_value",
    "recommendation_intent": "worthwhile_destination",
}
UNMAPPED_ASPECTS = [
    "friendly_service",
    "underpromoted_feature",
    "easy_if_guided",
    "good_for_itinerary_bundle",
]
FRICTION_ASPECTS = [
    "transport_access",
    "wayfinding_signage",
    "english_information_gap",
    "staff_communication",
    "booking_ticketing",
    "waiting_crowding",
    "price_value",
    "cleanliness_comfort",
    "opening_hours_availability",
    "itinerary_fit_time_cost",
    "accessibility_mobility",
    "food_amenities_gap",
]


class ChineseFoldError(RuntimeError):
    """Raised when folded multilingual input cannot be built safely."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=INPUT_PATH)
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH)
    return parser.parse_args()


def build_folded(input_path: Path) -> pd.DataFrame:
    if not input_path.exists():
        raise ChineseFoldError(f"Required input not found: {input_path}")

    source = pd.read_csv(input_path)
    required = {
        "detected_language",
        "language_group",
        "review_text",
        *CN_TO_ASPECT.values(),
        *UNMAPPED_ASPECTS,
        *FRICTION_ASPECTS,
        "any_friction",
    }
    missing = sorted(required - set(source.columns))
    if missing:
        raise ChineseFoldError(f"Required columns missing: {', '.join(missing)}")

    chinese_mask = source["detected_language"].astype("string").str.startswith("zh", na=False)
    if not chinese_mask.any():
        raise ChineseFoldError("No detected_language values starting with 'zh'")

    codebook = load_chinese_codebook()
    missing_codes = sorted(set(CN_TO_ASPECT) - set(codebook))
    if missing_codes:
        raise ChineseFoldError(f"Chinese codebook codes missing: {', '.join(missing_codes)}")

    chinese = pd.DataFrame(
        {
            "text_content": source.loc[chinese_mask, "review_text"].fillna(""),
            "title": "",
        }
    )
    chinese = _append_sentiment_fields(chinese, _reviewed_terms_from_codebook(codebook))
    chinese = _tag_chinese_dataframe(chinese, codebook)

    folded = source.copy()
    aspect_columns = list(dict.fromkeys([*CN_TO_ASPECT.values(), *UNMAPPED_ASPECTS]))
    for aspect in aspect_columns:
        folded[aspect] = folded[aspect].astype("int8")
    folded["any_friction"] = folded["any_friction"].astype("int8")
    folded.loc[chinese_mask, "language_group"] = "chinese"
    for code, aspect in CN_TO_ASPECT.items():
        folded.loc[chinese_mask, aspect] = chinese[code].astype("int8")
    for aspect in UNMAPPED_ASPECTS:
        folded.loc[chinese_mask, aspect] = 0
    folded.loc[chinese_mask, "any_friction"] = (
        folded.loc[chinese_mask, FRICTION_ASPECTS].astype(bool).any(axis=1).astype("int8")
    )
    return folded


def main() -> None:
    args = parse_args()
    folded = build_folded(args.input)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    folded.to_csv(args.output, index=False)
    chinese_count = int((folded["language_group"] == "chinese").sum())

    chinese_rows = folded[folded["language_group"] == "chinese"]
    manifest = research_manifest(
        kind="chinese_folded_multilingual_reviews",
        command=" ".join(sys.argv),
        inputs=[
            file_record(args.input, "synced_tagged_multilingual_reviews", required=True),
            file_record(REVIEWED_CODEBOOK_PATH, "reviewed_chinese_codebook", required=True),
            file_record(
                CHINESE_GOOGLE_REVIEW_CANDIDATES_PATH,
                "reviewed_chinese_google_review_candidates",
                required=True,
            ),
        ],
        outputs=[file_record(args.output, "chinese_folded_tagged_multilingual_reviews", required=True)],
        metrics={
            "n_rows": int(len(folded)),
            "language_group_counts": {str(k): int(v) for k, v in folded["language_group"].value_counts().items()},
            "chinese_any_friction_hits": int(chinese_rows["any_friction"].sum()),
            "chinese_unique_pois": int(chinese_rows["poi_id"].nunique()) if "poi_id" in chinese_rows else None,
            "cn_to_aspect_map": CN_TO_ASPECT,
            "unmapped_aspects_zeroed": UNMAPPED_ASPECTS,
        },
        caveats=FOLD_CAVEATS,
    )
    write_json(MANIFEST_PATH if args.output == OUTPUT_PATH else args.output.with_name(args.output.stem + "_manifest.json"), manifest)

    print(f"Wrote {len(folded)} rows to {args.output} ({chinese_count} Chinese-language reviews)")
    print(f"manifest -> {MANIFEST_PATH if args.output == OUTPUT_PATH else args.output.with_name(args.output.stem + '_manifest.json')}")


if __name__ == "__main__":
    main()
