#!/usr/bin/env python3
"""
Build POI-level nudge opportunity index from aggregate review aspect codes.

Research purpose:
    Identify public tourist sites that may be good candidates for two
    exploratory action types:
    - "fix-it": high-volume POIs with credibly elevated nudge-able friction.
    - "promote-it": bottom-quartile-volume POIs with high rating-based
      satisfaction. Draw evidence boosts the rank but does not gate membership.

Methods:
    - Review rating is used as the tool-independent outcome. Positive share is
      the share of reviews with rating >= 4, with Wilson score 95% confidence
      intervals (Wilson, 1927).
    - Aspect lift is computed as POI prevalence minus the global aspect
      prevalence across all reviews in the input file.
    - A POI aspect is "dominant" only when the Wilson lower bound for that POI
      exceeds the global base prevalence. This is a conservative descriptive
      rule, not a causal test.

Valid interpretation:
    This table ranks exploratory intervention hypotheses for stakeholder review.
    It does not estimate effectiveness of any nudge or operator action.
"""

from __future__ import annotations

import argparse
import math
import sys
from importlib import metadata
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.build_nudge_opportunity_analysis import (  # noqa: E402
    ASPECTS,
    CITY_TO_PREFECTURE,
    DRAW_ASPECTS,
    FRICTION_ASPECTS,
    SIGNAL_TYPE,
    strict_binary,
    wilson_interval,
)
from scripts.hypothesis_test_common import default_command, generated_at as generated_at_now  # noqa: E402
from src.provenance import (  # noqa: E402
    assert_no_forbidden_columns,
    file_record,
    research_manifest,
    write_json,
)


ROOT = Path(__file__).resolve().parent.parent
# Chinese-folded tagged file (zh promoted to language_group='chinese'); built by
# build_chinese_folded_multilingual.py from the synced tagged_reviews_multilingual.csv.
INPUT_PATH = ROOT / "output" / "multilingual_review_analysis" / "tagged_reviews_multilingual_chinese_folded.csv"
OUTPUT_DIR = ROOT / "output" / "nudge_analysis"
OUTPUT_CSV = OUTPUT_DIR / "poi_opportunity_index.csv"
OUTPUT_MANIFEST = OUTPUT_DIR / "poi_opportunity_index_manifest.json"

NUDGEABLE_FRICTION_ASPECTS = [
    "english_information_gap",
    "wayfinding_signage",
    "transport_access",
    "booking_ticketing",
    "opening_hours_availability",
    "itinerary_fit_time_cost",
]
PROMOTE_DRAW_ASPECTS = [
    "underpromoted_feature",
    "scenic_value",
    "worthwhile_destination",
]
# Tunable thresholds for POI- and aspect-level membership confidence.
LOW_CONFIDENCE_N = 10
MIN_DOMINANT_ASPECT_N = 3


class PoiOpportunityError(RuntimeError):
    """Raised when POI opportunity inputs or outputs are invalid."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build aggregate POI nudge opportunity index.")
    parser.add_argument("--input", type=Path, default=INPUT_PATH)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    return parser.parse_args()


def dependency_versions() -> dict[str, str]:
    versions = {}
    for package in ["pandas", "numpy"]:
        try:
            versions[package] = metadata.version(package)
        except metadata.PackageNotFoundError:
            versions[package] = "missing"
    return versions


def load_tagged_reviews(path: Path) -> pd.DataFrame:
    """Load and validate the tagged review file, failing loudly on schema gaps."""
    required = {
        "poi_id",
        "poi_name",
        "poi_category",
        "review_rating",
        "city",
        "language_group",
    } | set(ASPECTS)
    if not path.exists():
        raise PoiOpportunityError(f"Required input not found: {path}\nRun `make multilingual-reviews` first.")
    df = pd.read_csv(path)
    missing = sorted(required - set(df.columns))
    if missing:
        raise PoiOpportunityError(f"Required columns missing from {path}: {', '.join(missing)}")

    df = df.copy()
    df["prefecture"] = df["city"].map(CITY_TO_PREFECTURE)
    unmapped = sorted(df.loc[df["prefecture"].isna(), "city"].dropna().unique())
    if unmapped:
        raise PoiOpportunityError(f"Unmapped city values in {path}: {', '.join(unmapped)}")

    df["review_rating"] = pd.to_numeric(df["review_rating"], errors="coerce")
    if df["review_rating"].isna().any():
        raise PoiOpportunityError(f"review_rating contains missing/non-numeric values in {path}")
    for aspect in ASPECTS:
        df[aspect] = strict_binary(df[aspect], aspect)
    return df


def one_value(group: pd.DataFrame, column: str) -> str:
    """Return one stable POI metadata value; fail if one poi_id maps to many."""
    values = sorted(group[column].dropna().astype(str).unique())
    if len(values) != 1:
        raise PoiOpportunityError(
            f"POI metadata not unique for poi_id={group['poi_id'].iloc[0]} column={column}: {values}"
        )
    return values[0]


def join_codes(codes: list[str]) -> str:
    return ";".join(codes)


def build_index(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Aggregate rows to one public POI row and classify nudge archetypes."""
    global_base = {aspect: float(df[aspect].mean()) for aspect in ASPECTS}
    poi_sizes = df.groupby("poi_id").size()
    threshold_source = poi_sizes[poi_sizes >= LOW_CONFIDENCE_N]
    if threshold_source.empty:
        raise PoiOpportunityError("No POIs meet n_reviews >= 10, cannot define volume thresholds")
    high_volume_threshold = float(threshold_source.median())
    # Review volume is capped by collection, so "under-exposed" means the true
    # bottom quartile. Use the ceiling of Q1 because review counts are integers.
    low_volume_quantile = float(threshold_source.quantile(0.25))
    low_volume_threshold = int(math.ceil(low_volume_quantile))

    rows = []
    for poi_id, group in df.groupby("poi_id", sort=False):
        n_reviews = int(len(group))
        positive_count = int((group["review_rating"] >= 4).sum())
        positive_share, positive_low, positive_high = wilson_interval(positive_count, n_reviews)
        low_confidence = n_reviews < LOW_CONFIDENCE_N
        language_counts = group["language_group"].value_counts()
        published_language_counts = {
            "n_reviews_chinese": int(language_counts.get("chinese", 0)),
            "n_reviews_japanese": int(language_counts.get("japanese", 0)),
            "n_reviews_english": int(language_counts.get("english", 0)),
            "n_reviews_other": int(
                language_counts.drop(
                    labels=["chinese", "japanese", "english"], errors="ignore"
                ).sum()
            ),
        }

        # A credible lift means this POI's Wilson lower bound is above the
        # all-review base prevalence for that aspect.
        dominant_friction: list[str] = []
        dominant_draw: list[str] = []
        draw_signal: list[str] = []
        dominant_nudgeable_friction: list[str] = []
        promote_draw: list[str] = []
        fix_it_membership: list[str] = []
        promote_strict_membership: list[str] = []
        membership_thin_language_blocked = False
        aspect_values: dict[str, float | int | None] = {}
        for aspect in ASPECTS:
            n_positive = int(group[aspect].sum())
            prevalence, ci_low, ci_high = wilson_interval(n_positive, n_reviews)
            lift = None if prevalence is None else prevalence - global_base[aspect]
            aspect_values[f"{aspect}_n_positive"] = n_positive
            aspect_values[f"{aspect}_prevalence"] = prevalence
            aspect_values[f"{aspect}_ci_low"] = ci_low
            aspect_values[f"{aspect}_ci_high"] = ci_high
            aspect_values[f"{aspect}_global_base_prevalence"] = global_base[aspect]
            aspect_values[f"{aspect}_lift"] = lift
            if ci_low is not None and ci_low > global_base[aspect]:
                if SIGNAL_TYPE[aspect] == "friction":
                    dominant_friction.append(aspect)
                    if aspect in NUDGEABLE_FRICTION_ASPECTS:
                        dominant_nudgeable_friction.append(aspect)
                else:
                    dominant_draw.append(aspect)
                    if aspect in PROMOTE_DRAW_ASPECTS:
                        promote_draw.append(aspect)
                positive_languages = group.loc[group[aspect] == 1, "language_group"]
                positive_language_counts = positive_languages.value_counts()
                driving_languages = (
                    positive_language_counts[
                        positive_language_counts == positive_language_counts.max()
                    ].index.tolist()
                    if not positive_language_counts.empty
                    else []
                )
                passes_membership_gate = (
                    n_positive >= MIN_DOMINANT_ASPECT_N
                    and bool(driving_languages)
                    and all(
                        int(language_counts.get(language, 0)) >= LOW_CONFIDENCE_N
                        for language in driving_languages
                    )
                )
                if aspect in NUDGEABLE_FRICTION_ASPECTS:
                    if passes_membership_gate:
                        fix_it_membership.append(aspect)
                    else:
                        membership_thin_language_blocked = True
                if aspect in PROMOTE_DRAW_ASPECTS:
                    if passes_membership_gate:
                        promote_strict_membership.append(aspect)
                    else:
                        membership_thin_language_blocked = True
            if SIGNAL_TYPE[aspect] == "draw" and prevalence is not None and prevalence > global_base[aspect]:
                draw_signal.append(aspect)

        high_volume = n_reviews >= high_volume_threshold
        low_volume = n_reviews <= low_volume_threshold
        fix_lift_sum = sum(
            max(0.0, float(aspect_values[f"{aspect}_lift"] or 0.0))
            for aspect in dominant_nudgeable_friction
        )
        promote_draw_prevalence_sum = sum(
            float(aspect_values[f"{aspect}_prevalence"] or 0.0)
            for aspect in dominant_draw
        )
        has_draw_signal = bool(draw_signal)

        is_fix_it = bool((not low_confidence) and high_volume and fix_it_membership)
        is_promote_it_strict = bool(
            (not low_confidence)
            and low_volume
            and positive_low is not None
            and positive_low >= 0.70
            and promote_strict_membership
        )
        is_promote_it = bool((not low_confidence) and low_volume and positive_share is not None and positive_share >= 0.85)
        if n_reviews >= 30:
            promote_confidence = "moderate"
        elif n_reviews >= LOW_CONFIDENCE_N:
            promote_confidence = "low"
        else:
            promote_confidence = "excluded"
        is_crowding_hotspot = bool(
            high_volume
            and aspect_values["waiting_crowding_ci_low"] is not None
            and aspect_values["waiting_crowding_ci_low"] > global_base["waiting_crowding"]
        )
        archetypes = []
        if is_fix_it:
            archetypes.append("fix-it")
        if is_promote_it:
            archetypes.append("promote-it")

        # Scores are transparent sorting aids. Fix-it rewards volume plus
        # elevated nudge-able friction lift. Promote-it rewards high point
        # satisfaction, a draw-signal boost, and lower exposure.
        row = {
            "poi_name": one_value(group, "poi_name"),
            "poi_category": one_value(group, "poi_category"),
            "city": one_value(group, "city"),
            "prefecture": one_value(group, "prefecture"),
            "is_fukui": bool(one_value(group, "prefecture") == "Fukui"),
            "n_reviews": n_reviews,
            **published_language_counts,
            "mean_rating": float(group["review_rating"].mean()),
            "positive_count": positive_count,
            "positive_share": positive_share,
            "positive_share_ci_low": positive_low,
            "positive_share_ci_high": positive_high,
            "low_confidence": low_confidence,
            "high_volume_threshold": high_volume_threshold,
            "low_volume_threshold": low_volume_threshold,
            "is_high_volume": bool(high_volume),
            "is_low_volume": bool(low_volume),
            "dominant_friction_codes": join_codes(dominant_friction),
            "dominant_draw_codes": join_codes(dominant_draw),
            "draw_signal_codes": join_codes(draw_signal),
            "has_draw_signal": has_draw_signal,
            "dominant_nudgeable_friction_codes": join_codes(dominant_nudgeable_friction),
            "promote_draw_codes": join_codes(promote_draw),
            "fix_it_membership_codes": join_codes(fix_it_membership),
            "promote_strict_membership_codes": join_codes(promote_strict_membership),
            "membership_thin_language_blocked": membership_thin_language_blocked,
            "fix_it_elevated_friction_lift_sum": fix_lift_sum,
            "promote_it_draw_prevalence_sum": promote_draw_prevalence_sum,
            "fix_it_score": float(n_reviews * fix_lift_sum) if is_fix_it else 0.0,
            "promote_it_score": (
                float(positive_share * (1 + int(has_draw_signal)) * (low_volume_threshold / n_reviews))
                if is_promote_it and positive_share is not None
                else 0.0
            ),
            "is_fix_it": is_fix_it,
            "is_promote_it": is_promote_it,
            "is_promote_it_strict": is_promote_it_strict,
            "promote_confidence": promote_confidence,
            "is_crowding_hotspot": is_crowding_hotspot,
            "archetype": ";".join(archetypes) if archetypes else "neither",
            **aspect_values,
        }
        rows.append(row)

    out = pd.DataFrame(rows)
    out["fix_it_rank"] = out.loc[out["is_fix_it"], "fix_it_score"].rank(method="dense", ascending=False)
    out["promote_it_rank"] = out.loc[out["is_promote_it"], "promote_it_score"].rank(method="dense", ascending=False)
    out = out.sort_values(
        ["is_promote_it", "promote_it_score", "is_fix_it", "fix_it_score", "n_reviews"],
        ascending=[False, False, False, False, False],
    ).reset_index(drop=True)

    metrics = {
        "n_input_rows": int(len(df)),
        "n_pois_total": int(len(out)),
        "n_pois_by_prefecture": {
            str(k): int(v) for k, v in out["prefecture"].value_counts().sort_index().to_dict().items()
        },
        "n_low_confidence_pois": int(out["low_confidence"].sum()),
        "n_fix_it": int(out["is_fix_it"].sum()),
        "n_promote_it": int(out["is_promote_it"].sum()),
        "n_promote_it_strict": int(out["is_promote_it_strict"].sum()),
        "n_fix_it_fukui": int((out["is_fix_it"] & out["is_fukui"]).sum()),
        "n_promote_it_fukui": int((out["is_promote_it"] & out["is_fukui"]).sum()),
        "n_crowding_hotspots": int(out["is_crowding_hotspot"].sum()),
        "high_volume_threshold_n_reviews": high_volume_threshold,
        "low_volume_threshold_n_reviews": low_volume_threshold,
        "low_volume_quantile_raw": low_volume_quantile,
        "low_confidence_threshold_n_reviews": LOW_CONFIDENCE_N,
        "min_dominant_aspect_n_positive": MIN_DOMINANT_ASPECT_N,
        "global_base_prevalence": global_base,
    }
    return out, metrics


def write_outputs(
    *,
    output: pd.DataFrame,
    metrics: dict,
    input_path: Path,
    output_csv: Path,
    output_manifest: Path,
    command: str,
    generated: str,
) -> dict:
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    # `poi_id` is forbidden by the provenance guard. We aggregate by it
    # internally, then publish public attraction metadata only.
    assert_no_forbidden_columns(output.columns, context=str(output_csv))
    output.to_csv(output_csv, index=False)

    manifest = research_manifest(
        kind="poi_nudge_opportunity_index",
        command=command,
        generated_at=generated,
        filters={
            "unit": "POI aggregate grouped internally by poi_id",
            "published_key": ["poi_name", "poi_category", "city", "prefecture"],
            "positive_share_definition": "review_rating >= 4",
            "dominant_code_rule": "POI Wilson lower bound exceeds global base prevalence",
            "membership_aspect_support_floor": MIN_DOMINANT_ASPECT_N,
            "membership_driving_language_rule": (
                "Each tied plurality language for positive aspect tags must have at least "
                f"{LOW_CONFIDENCE_N} reviews at the POI"
            ),
            "promote_it_relaxed_rule": "n_reviews >= 10, n_reviews <= bottom-quartile cutoff, positive_share point estimate >= 0.85",
            "promote_it_score": "positive_share * (1 + has_draw_signal) * (low_volume_threshold / n_reviews)",
            "crowding_hotspot_rule": "high volume and waiting_crowding Wilson lower bound exceeds global base prevalence",
            "nudgeable_friction_aspects": NUDGEABLE_FRICTION_ASPECTS,
            "promote_draw_aspects": PROMOTE_DRAW_ASPECTS,
        },
        inputs=[file_record(input_path, "aspect_tagged_multilingual_reviews", required=True)],
        outputs=[file_record(output_csv, "aggregate_poi_opportunity_index", required=True)],
        metrics=metrics,
        caveats=[
            "Exploratory and hypothesis-generating; not causal.",
            "POI rows are aggregate-only and omit poi_id, review text, authors, URLs, and review IDs.",
            "Positive share is rating-based and does not use sentiment-tool scores.",
            "Promote-it is exploratory candidate-generation using point-estimate satisfaction; confidence intervals are reported as uncertainty, not used as a gate.",
            "Review volume is capped by collection, so low-volume means bottom-quartile exposure rather than below-median volume.",
            "Small-n POIs are flagged low_confidence; Wilson intervals are descriptive uncertainty bounds.",
            "Dominant aspect codes use a conservative lift rule, not a formal multiple-comparison test.",
            "Fix-it and strict promote-it membership require at least "
            f"{MIN_DOMINANT_ASPECT_N} positive aspect tags and exclude aspects plurality-driven "
            f"by a language group with fewer than {LOW_CONFIDENCE_N} reviews at that POI; "
            "all tied plurality languages must pass.",
            "Fix-it and promote-it archetypes rank candidate follow-up work, not intervention effectiveness.",
            "Groups describe review language when present in upstream data, not reviewer nationality.",
        ],
        extra={"dependency_versions": dependency_versions()},
    )
    manifest["dependency_versions"] = dependency_versions()
    write_json(output_manifest, manifest)
    return manifest


def build(
    *,
    input_path: Path = INPUT_PATH,
    output_dir: Path = OUTPUT_DIR,
    command: str | None = None,
) -> dict:
    command = command or default_command("build_poi_opportunity_index.py")
    generated = generated_at_now()
    output_csv = output_dir / "poi_opportunity_index.csv"
    output_manifest = output_dir / "poi_opportunity_index_manifest.json"
    df = load_tagged_reviews(input_path)
    output, metrics = build_index(df)
    return write_outputs(
        output=output,
        metrics=metrics,
        input_path=input_path,
        output_csv=output_csv,
        output_manifest=output_manifest,
        command=command,
        generated=generated,
    )


def main() -> None:
    args = parse_args()
    try:
        manifest = build(input_path=args.input, output_dir=args.output_dir)
    except Exception as error:
        raise SystemExit(str(error)) from error
    print(f"wrote {args.output_dir / 'poi_opportunity_index.csv'}")
    print(f"wrote {args.output_dir / 'poi_opportunity_index_manifest.json'}")
    print(
        "pois/fix-it/promote-it: "
        f"{manifest['metrics']['n_pois_total']}/"
        f"{manifest['metrics']['n_fix_it']}/"
        f"{manifest['metrics']['n_promote_it']}"
    )


if __name__ == "__main__":
    main()
