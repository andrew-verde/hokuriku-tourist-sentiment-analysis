#!/usr/bin/env python3
"""WL-CN: within-Chinese social-source sentiment driver tests."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.within_language_sentiment_common import (
    COMMON_WITHIN_CAVEATS,
    DEFAULT_CHINESE_INPUT_PATH,
    DEFAULT_OUTPUT_DIR,
    apply_bh,
    binary_event_row,
    bool_series,
    default_command,
    generated_at as generated_at_now,
    kruskal_row,
    load_csv_fail_loud,
    parse_args,
    score_by_binary_row,
    sha256_file,
    write_csv,
    write_manifest,
)

SCRIPT_NAME = "test_cn_within_source_sentiment_drivers.py"
OUTPUT_CSV = "cn_within_source_sentiment_drivers.csv"
OUTPUT_MANIFEST = "cn_within_source_sentiment_manifest.json"
LANGUAGE_LABEL = "Chinese-language Fukui social rows"
SCORE_COLUMN = "snownlp_centered_score"
TOPIC_COLUMNS = [
    "scenic_nature",
    "temples_spiritual",
    "history_culture",
    "dinosaurs_museums",
    "food_local_cuisine",
    "hot_springs_relaxation",
    "crafts_shopping",
    "fan_pilgrimage_pop_culture",
    "accommodation",
    "seasonal_events",
]
REQUIRED_COLUMNS = {
    "source_platform",
    "theme",
    "text_length_chars",
    "body_has_text",
    "text_scope",
    SCORE_COLUMN,
    "sentiment_category",
    "any_friction",
    "any_topic",
    "any_enjoyment_evidence",
} | set(TOPIC_COLUMNS)
CAVEATS = COMMON_WITHIN_CAVEATS + [
    "SnowNLP centered scores are interpreted only within Chinese-language social rows.",
    "Chinese rows mix social platform forms; platform diagnostics are source-sensitivity checks.",
    "Theme diagnostics treat unclassified as unresolved coverage, not a substantive theme.",
]


def _read_chinese_readiness(input_path: Path) -> dict:
    readiness_path = input_path.with_name("chinese_social_readiness.json")
    if not readiness_path.exists():
        return {}
    with readiness_path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    keys = [
        "analysis_variant",
        "analysis_scope_label",
        "n_total_xhs_rows",
        "n_total_douyin_rows",
        "n_with_body_text",
        "n_title_only_excluded",
        "n_non_fan_compared",
        "source_platform_counts",
        "theme_counts",
    ]
    return {key: data[key] for key in keys if key in data}


def build_cn_within_source_sentiment_drivers(
    input_path: Path = DEFAULT_CHINESE_INPUT_PATH,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    command: str | None = None,
) -> dict:
    df = load_csv_fail_loud(input_path, REQUIRED_COLUMNS, "make chinese-social")
    if "city" in df.columns:
        df = df[df["city"].astype(str).str.lower().eq("fukui")].copy()
    body_mask = bool_series(df["body_has_text"]) | df["text_scope"].astype(str).str.contains("body|comment", case=False, na=False)
    df = df[body_mask].copy()
    command = command or default_command(SCRIPT_NAME)
    generated = generated_at_now()
    source_hash = sha256_file(input_path)
    caveat = "; ".join(CAVEATS)
    readiness_metrics = _read_chinese_readiness(input_path)
    denominators = {"chinese_social_rows": int(len(df))}
    for key in [
        "n_total_xhs_rows",
        "n_total_douyin_rows",
        "n_with_body_text",
        "n_title_only_excluded",
        "n_non_fan_compared",
    ]:
        if key in readiness_metrics:
            denominators[key] = readiness_metrics[key]

    rows = _cn_rows(df, input_path, source_hash, command, generated, caveat)
    out = pd.DataFrame(rows)
    output_csv = output_dir / OUTPUT_CSV
    output_manifest = output_dir / OUTPUT_MANIFEST
    write_csv(out, output_csv)
    manifest = write_manifest(
        kind="within_source_sentiment_drivers_cn",
        command=command,
        generated=generated,
        input_path=input_path,
        output_csv=output_csv,
        manifest_path=output_manifest,
        filters={"scope": "Fukui when city column is present", "text": "body/comment text present"},
        metrics={
            "analysis_family": "WL-CN",
            "primary_unit": "one Chinese-language Fukui social row with body/comment text",
            "denominators": denominators,
            "chinese_social_readiness": readiness_metrics,
            "score": "SnowNLP centered score, interpreted within Chinese source only",
            "topic_columns": TOPIC_COLUMNS,
            "multiple_testing": "Benjamini-Hochberg FDR within Chinese topic and platform diagnostic families.",
        },
        caveats=CAVEATS,
        input_role="ignored_tagged_chinese_social_posts_file",
    )
    return {"csv": str(output_csv), "manifest": str(output_manifest), "rows": len(out), "provenance": manifest}


def _cn_rows(df: pd.DataFrame, input_path: Path, source_hash: str, command: str, generated: str, caveat: str) -> list[dict]:
    rows = [
        score_by_binary_row(
            df=df,
            analysis_id="WL-CN-1",
            research_question="Do Chinese-language social rows with friction evidence show lower SnowNLP sentiment?",
            language_source_group=LANGUAGE_LABEL,
            outcome=SCORE_COLUMN,
            predictor="any_friction",
            expected_direction="lower when true",
            unit="one Chinese-language Fukui social row",
            source_input_path=input_path,
            source_input_sha256=source_hash,
            command=command,
            generated=generated,
            caveat=caveat,
            multiple_testing_family="chinese_evidence_predictors",
        ),
        binary_event_row(
            df=df,
            analysis_id="WL-CN-1",
            research_question="Do Chinese-language social rows with friction evidence have lower positive sentiment prevalence?",
            language_source_group=LANGUAGE_LABEL,
            outcome="sentiment_category",
            predictor="any_friction",
            positive_event="positive",
            unit="one Chinese-language Fukui social row",
            source_input_path=input_path,
            source_input_sha256=source_hash,
            command=command,
            generated=generated,
            caveat=caveat,
            multiple_testing_family="chinese_evidence_predictors",
        ),
    ]
    for topic in TOPIC_COLUMNS:
        rows.append(score_by_binary_row(
            df=df,
            analysis_id="WL-CN-2",
            research_question=f"Is Chinese topic code {topic} associated with SnowNLP sentiment?",
            language_source_group=LANGUAGE_LABEL,
            outcome=SCORE_COLUMN,
            predictor=topic,
            expected_direction="diagnostic",
            unit="one Chinese-language Fukui social row",
            source_input_path=input_path,
            source_input_sha256=source_hash,
            command=command,
            generated=generated,
            caveat=caveat,
            multiple_testing_family="chinese_topic_predictors",
        ))
        rows.append(binary_event_row(
            df=df,
            analysis_id="WL-CN-2",
            research_question=f"Is Chinese topic code {topic} associated with positive sentiment prevalence?",
            language_source_group=LANGUAGE_LABEL,
            outcome="sentiment_category",
            predictor=topic,
            positive_event="positive",
            unit="one Chinese-language Fukui social row",
            source_input_path=input_path,
            source_input_sha256=source_hash,
            command=command,
            generated=generated,
            caveat=caveat,
            multiple_testing_family="chinese_topic_predictors",
        ))
    rows.append(kruskal_row(
        df=df,
        analysis_id="WL-CN-3",
        research_question="Do Chinese social source platforms differ in SnowNLP sentiment?",
        language_source_group=LANGUAGE_LABEL,
        score_column=SCORE_COLUMN,
        predictor="source_platform",
        unit="one Chinese-language Fukui social row",
        min_group_n=3,
        source_input_path=input_path,
        source_input_sha256=source_hash,
        command=command,
        generated=generated,
        caveat=caveat,
        family="chinese_platform_diagnostics",
    ))
    rows.append(kruskal_row(
        df=df[df["theme"].astype(str).str.lower().ne("unclassified")].copy(),
        analysis_id="WL-CN-4",
        research_question="Do classified Chinese themes differ in SnowNLP sentiment?",
        language_source_group=LANGUAGE_LABEL,
        score_column=SCORE_COLUMN,
        predictor="theme",
        unit="one Chinese-language Fukui social row with classified theme",
        min_group_n=10,
        source_input_path=input_path,
        source_input_sha256=source_hash,
        command=command,
        generated=generated,
        caveat=caveat,
        family="chinese_theme_diagnostic",
    ))
    apply_bh(rows, "chinese_evidence_predictors")
    apply_bh(rows, "chinese_topic_predictors")
    return rows


def main() -> None:
    args = parse_args(__doc__ or "Run WL-CN within-source sentiment drivers.", DEFAULT_CHINESE_INPUT_PATH)
    print(json.dumps(build_cn_within_source_sentiment_drivers(args.input, args.output_dir), indent=2))


if __name__ == "__main__":
    main()
