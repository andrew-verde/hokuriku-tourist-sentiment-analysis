#!/usr/bin/env python3
"""
Build presentation-safe aggregate tables and captions.

This stage consumes tracked JP-EN aggregate sentiment outputs plus the ignored
scored-review audit file named in the sentiment manifest. It reads only safe
metadata from that audit file to aggregate date ranges and POI-category mix; it
does not write row-level text, POI IDs, author fields, URLs, screenshots, or
manual capture files.
"""

from __future__ import annotations

import argparse
import html
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.provenance import (
    ProvenanceError,
    assert_no_forbidden_columns,
    file_record,
    research_manifest,
    sha256_file,
    write_json,
)
from src.utils.logger import setup_logger

logger = setup_logger(__name__)

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SENTIMENT_SUMMARY_PATH = (
    ROOT / "output" / "sentiment_aggregates" / "source_group_sentiment_summary.csv"
)
DEFAULT_SENTIMENT_TESTS_PATH = (
    ROOT / "output" / "sentiment_aggregates" / "source_group_sentiment_tests.csv"
)
DEFAULT_SENTIMENT_MANIFEST_PATH = ROOT / "output" / "sentiment_aggregates" / "sentiment_manifest.json"
DEFAULT_CROSS_LANGUAGE_BASELINE_PATH = (
    ROOT / "output" / "cross_language_trends" / "cross_language_baseline_snapshot.csv"
)
DEFAULT_CROSS_LANGUAGE_TESTS_PATH = (
    ROOT / "output" / "cross_language_trends" / "cross_language_statistical_tests.csv"
)
DEFAULT_OUTPUT_DIR = ROOT / "output" / "presentation_safe"

REQUIRED_SUMMARY_COLUMNS = {
    "source_group",
    "language_group",
    "prefecture_normalized",
    "city",
    "n_reviews",
    "n_scored",
    "mean_sentiment_score",
    "mean_review_rating",
    "negative_count",
    "negative_pct",
    "neutral_count",
    "neutral_pct",
    "positive_count",
    "positive_pct",
}

REQUIRED_TEST_COLUMNS = {
    "test_name",
    "comparison",
    "status",
    "statistic",
    "p_value",
    "effect",
    "details_json",
}

REQUIRED_ROW_LEVEL_COLUMNS = {
    "city",
    "prefecture_normalized",
    "poi_category",
    "review_date",
    "language_group",
}

REQUIRED_BASELINE_COLUMNS = {
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
}

FORBIDDEN_PRESENTATION_COLUMNS = {
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
}

FIGURE_PALETTE = {
    "english": "#2f6f73",
    "japanese": "#5b6c94",
    "chinese_social": "#bc6c25",
    "positive": "#2f6f73",
    "neutral": "#8d99ae",
    "negative": "#9a031e",
    "rating": "#5b6c94",
    "volume": "#bc6c25",
}
FIGURE_BG = "#fbfaf7"
FIGURE_INK = "#1f2933"
FIGURE_MUTED = "#52616b"
FIGURE_LINE = "#d7dde8"

FORBIDDEN_PRESENTATION_VALUES = {
    "dummy",
    "fixture",
    "placeholder",
    "sample",
    "synthetic",
    "test data",
    "test-only",
    "unavailable_in_aggregate_input",
}


class PresentationOutputError(RuntimeError):
    pass


class MissingInputError(PresentationOutputError):
    pass


class MissingColumnsError(PresentationOutputError):
    pass


def _require_input(path: Path, make_target: str) -> None:
    if not path.exists():
        raise MissingInputError(
            f"Required input not found: {path}\n"
            f"Generate it first with `make {make_target}`. This pipeline has no demo mode."
        )


def _read_manifest(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise PresentationOutputError(f"Invalid JSON manifest: {path}") from error


def _require_columns(df: pd.DataFrame, required: set[str], path: Path) -> None:
    missing = sorted(required - set(df.columns))
    if missing:
        raise MissingColumnsError(f"Required columns missing from {path}: {', '.join(missing)}")


def _input_hashes(manifest: dict) -> dict[str, str]:
    review_input = manifest.get("input", {})
    hashes = {
        "reviews_input_sha256": str(review_input.get("sha256", "")),
        "poi_metadata_sha256": str(review_input.get("poi_metadata_sha256", "")),
    }
    invalid = []
    for key, value in hashes.items():
        if len(value) != 64:
            invalid.append(key)
    if invalid:
        raise PresentationOutputError(
            "Sentiment manifest is missing valid input hashes: " + ", ".join(sorted(invalid))
        )
    return hashes


def _row_level_path(manifest: dict, override: Path | None) -> Path:
    if override is not None:
        return override
    row_level = manifest.get("outputs", {}).get("row_level_path")
    if not row_level:
        raise MissingInputError(
            "Sentiment manifest does not name outputs.row_level_path; rerun `make sentiment-analysis`."
        )
    return Path(row_level)


def build_metadata_summary(row_level: pd.DataFrame) -> pd.DataFrame:
    assert_no_forbidden_columns(
        row_level.columns,
        forbidden={
            "review_text",
            "text_content",
            "review_author",
            "author",
            "author_url",
            "note_url",
            "source_url",
            "url",
            "place_id",
            "source_review_id",
            "source_record_id",
        },
        context="presentation metadata input",
    )
    work = row_level[list(REQUIRED_ROW_LEVEL_COLUMNS)].copy()
    work["review_date"] = pd.to_datetime(work["review_date"], errors="coerce", utc=True)
    work["poi_category"] = work["poi_category"].fillna("unknown").astype(str)
    rows = []
    for keys, chunk in work.groupby(["prefecture_normalized", "city", "language_group"], dropna=False):
        prefecture, city, language = keys
        dated = chunk[chunk["review_date"].notna()]
        if dated.empty:
            raise PresentationOutputError(
                f"No parseable review_date values for {prefecture} {city} {language}."
            )
        mix = chunk["poi_category"].value_counts().sort_index()
        rows.append({
            "prefecture_normalized": prefecture,
            "city": city,
            "language_group": language,
            "date_range_start": dated["review_date"].min().date().isoformat(),
            "date_range_end": dated["review_date"].max().date().isoformat(),
            "review_date_parseable_count": int(chunk["review_date"].notna().sum()),
            "review_date_missing_count": int(chunk["review_date"].isna().sum()),
            "poi_mix": "; ".join(f"{category}={int(count)}" for category, count in mix.items()),
        })
    return pd.DataFrame(rows)


def _assert_no_fake_or_placeholder_values(df: pd.DataFrame, context: str) -> None:
    text = "\n".join(str(value) for value in df.to_numpy().ravel()).lower()
    blocked = sorted(value for value in FORBIDDEN_PRESENTATION_VALUES if value in text)
    if blocked:
        raise PresentationOutputError(
            f"{context} contains dummy/placeholder-like values: {', '.join(blocked)}"
        )


def _fmt_n(value: int | float) -> str:
    return f"{int(value):,}"


def _pct(numerator: float, denominator: float) -> float:
    return round((numerator / denominator) * 100, 3) if denominator else 0.0


def _language_key(language_source_group: str) -> str:
    return str(language_source_group).split("-language", maxsplit=1)[0]


def _svg_header(width: int, height: int, title: str, subtitle: str) -> list[str]:
    return [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        f'<rect width="100%" height="100%" fill="{FIGURE_BG}"/>',
        f'<text x="32" y="38" font-family="Arial, sans-serif" font-size="24" font-weight="700" fill="{FIGURE_INK}">{html.escape(title)}</text>',
        f'<text x="32" y="66" font-family="Arial, sans-serif" font-size="14" fill="{FIGURE_MUTED}">{html.escape(subtitle)}</text>',
    ]


def _text(x: float, y: float, value: object, size: int = 12, fill: str = FIGURE_INK, anchor: str = "start", weight: int = 400) -> str:
    return (
        f'<text x="{x:.2f}" y="{y:.2f}" text-anchor="{anchor}" font-family="Arial, sans-serif" '
        f'font-size="{size}" font-weight="{weight}" fill="{fill}">{html.escape(str(value))}</text>'
    )


def _chip(parts: list[str], x: float, y: float, width: float, height: float, label: str, *, size: int = 12, fill: str = FIGURE_BG, text_fill: str = FIGURE_INK) -> None:
    parts.append(
        f'<rect x="{x:.2f}" y="{y:.2f}" width="{width:.2f}" height="{height:.2f}" '
        f'rx="4" fill="{fill}" stroke="{FIGURE_LINE}" stroke-width="1"/>'
    )
    parts.append(_text(x + width / 2, y + height / 2 + size / 2 - 2, label, size=size, fill=text_fill, anchor="middle"))


def _chip_width(label: str, size: int = 12) -> float:
    return max(34.0, len(label) * size * 0.54 + 16.0)


def _label_chip(parts: list[str], x: float, baseline_y: float, label: str, *, canvas_width: float, size: int = 12, text_fill: str = FIGURE_INK, anchor: str = "start") -> bool:
    chip_width = _chip_width(label, size=size)
    if anchor == "end":
        chip_x = x - chip_width + 4
        if chip_x < 32:
            return False
    else:
        chip_x = x - 4
        if chip_x + chip_width > canvas_width - 32:
            return False
    _chip(parts, chip_x, baseline_y - 15, chip_width, 22, label, size=size, text_fill=text_fill)
    return True


def _gridlines(parts: list[str], left: float, chart_width: float, y1: float, y2: float) -> None:
    for tick_pct in (0.0, 0.5, 1.0):
        x = left + tick_pct * chart_width
        parts.append(
            f'<line x1="{x:.2f}" x2="{x:.2f}" y1="{y1:.2f}" y2="{y2:.2f}" '
            f'stroke="{FIGURE_LINE}" stroke-width="1" opacity="0.58"/>'
        )


def _write_single_sentiment_profile(row: pd.Series, path: Path, language_label: str) -> None:
    width = 1000
    height = 250
    left = 190
    top = 108
    chart_width = 690
    categories = [
        ("negative", float(row["negative_pct"])),
        ("neutral", float(row["neutral_pct"])),
        ("positive", float(row["positive_pct"])),
    ]
    parts = _svg_header(
        width,
        height,
        f"{language_label} Sentiment Profile",
        (
            f"{row['sentiment_tool']} secondary check; n={_fmt_n(row['n_reviews'])}, "
            f"mean rating={float(row['mean_review_rating']):.2f}"
        ),
    )
    parts.append(
        f'<text x="{left - 14}" y="{top + 24}" text-anchor="end" font-family="Arial, sans-serif" font-size="14" fill="#1f2933">share of rows</text>'
    )
    _gridlines(parts, left, chart_width, top + 4, top + 36)
    x = left
    for category, value in categories:
        segment_width = (value / 100.0) * chart_width
        parts.append(
            f'<rect x="{x:.2f}" y="{top + 7}" width="{segment_width:.2f}" height="26" fill="{FIGURE_PALETTE[category]}"/>'
        )
        if segment_width > 48:
            parts.append(
                f'<text x="{x + segment_width / 2:.2f}" y="{top + 26}" text-anchor="middle" font-family="Arial, sans-serif" font-size="12" fill="#ffffff">{value:.1f}%</text>'
            )
        x += segment_width
    parts.append(
        f'<text x="{left}" y="{top + 72}" font-family="Arial, sans-serif" font-size="13" fill="#52616b">Date range: {html.escape(str(row["date_range_start"]))} to {html.escape(str(row["date_range_end"]))}; dated={_fmt_n(row["review_date_parseable_count"])}, undated={_fmt_n(row["review_date_missing_count"])}</text>'
    )
    legend_y = height - 34
    legend_x = left
    for index, (category, value) in enumerate(categories):
        offset = index * 150
        parts.extend([
            f'<rect x="{legend_x + offset}" y="{legend_y - 10}" width="10" height="10" fill="{FIGURE_PALETTE[category]}"/>',
            f'<text x="{legend_x + offset + 16}" y="{legend_y}" font-family="Arial, sans-serif" font-size="12" fill="#52616b">{category} ({value:.1f}%)</text>',
        ])
    parts.append("</svg>")
    path.write_text("\n".join(parts), encoding="utf-8")


def _poi_mix_rows(row: pd.Series) -> list[dict[str, object]]:
    rows = []
    total = int(row["n_reviews"])
    for item in str(row["poi_mix"]).split(";"):
        if "=" not in item:
            continue
        category, count = item.strip().split("=", maxsplit=1)
        count_int = int(count)
        rows.append({
            "category": category,
            "count": count_int,
            "pct": _pct(count_int, total),
        })
    return sorted(rows, key=lambda item: (-int(item["count"]), str(item["category"])))


def _write_poi_priority_mix(row: pd.Series, path: Path, language_label: str) -> None:
    rows = _poi_mix_rows(row)
    width = 1000
    top = 100
    row_height = 38
    left = 270
    right = 90
    height = top + 58 + max(1, len(rows)) * row_height
    chart_width = width - left - right
    max_count = max([int(item["count"]) for item in rows] or [1])
    parts = _svg_header(
        width,
        height,
        f"{language_label} Tourism Priority Mix",
        f"Google review POI-category distribution; n={_fmt_n(row['n_reviews'])} rows",
    )
    color = FIGURE_PALETTE[_language_key(row["language_source_group"])]
    _gridlines(parts, left, chart_width, top - 4, top + (max(1, len(rows)) - 1) * row_height + 32)
    for index, item in enumerate(rows):
        y = top + index * row_height
        bar_width = (int(item["count"]) / max_count) * chart_width
        label = str(item["category"]).replace("_", " ")
        parts.extend([
            f'<text x="{left - 14}" y="{y + 23}" text-anchor="end" font-family="Arial, sans-serif" font-size="13" fill="#1f2933">{html.escape(label[:34])}</text>',
            f'<rect x="{left}" y="{y + 8}" width="{bar_width:.2f}" height="20" rx="3" fill="{color}"/>',
        ])
        value_label = f"{_fmt_n(item['count'])} ({float(item['pct']):.1f}%)"
        if not _label_chip(parts, left + bar_width + 8, y + 23, value_label, canvas_width=width):
            parts.append(
                f'<text x="{left + bar_width + 8}" y="{y + 23}" font-family="Arial, sans-serif" font-size="12" fill="#1f2933">{html.escape(value_label)}</text>'
            )
    parts.append("</svg>")
    path.write_text("\n".join(parts), encoding="utf-8")


def _write_multilingual_sentiment_share(
    chart: pd.DataFrame,
    baseline: pd.DataFrame,
    path: Path,
) -> None:
    rows = []
    for _, row in chart.iterrows():
        language = _language_key(row["language_source_group"])
        rows.append({
            "label": f"{language} Google reviews",
            "n": int(row["n_reviews"]),
            "negative": float(row["negative_pct"]),
            "neutral": float(row["neutral_pct"]),
            "positive": float(row["positive_pct"]),
        })
    chinese = baseline[baseline["source_kind"] == "chinese_social_post"].copy()
    if not chinese.empty:
        total = int(chinese["volume"].sum())
        rows.append({
            "label": "Chinese-language social rows",
            "n": total,
            "negative": round(float((chinese["negative_pct"] * chinese["volume"]).sum()) / total, 3),
            "neutral": round(float((chinese["neutral_pct"] * chinese["volume"]).sum()) / total, 3),
            "positive": round(float((chinese["positive_pct"] * chinese["volume"]).sum()) / total, 3),
        })
    width = 1000
    row_height = 48
    top = 98
    left = 245
    right = 80
    height = top + 64 + max(1, len(rows)) * row_height
    chart_width = width - left - right
    parts = _svg_header(
        width,
        height,
        "Sentiment Category Share by Language Source",
        "Secondary library/category shares; source platforms and tools differ",
    )
    _gridlines(parts, left, chart_width, top + 2, top + (max(1, len(rows)) - 1) * row_height + 36)
    for index, row in enumerate(rows):
        y = top + index * row_height
        parts.append(
            f'<text x="{left - 14}" y="{y + 25}" text-anchor="end" font-family="Arial, sans-serif" font-size="13" fill="#1f2933">{html.escape(row["label"])}</text>'
        )
        x = left
        for category in ["negative", "neutral", "positive"]:
            value = float(row[category])
            segment_width = (value / 100.0) * chart_width
            parts.append(
                f'<rect x="{x:.2f}" y="{y + 8}" width="{segment_width:.2f}" height="24" fill="{FIGURE_PALETTE[category]}"/>'
            )
            if segment_width > 44:
                parts.append(
                    f'<text x="{x + segment_width / 2:.2f}" y="{y + 25}" text-anchor="middle" font-family="Arial, sans-serif" font-size="11" fill="#ffffff">{value:.1f}%</text>'
                )
            x += segment_width
        n_label = f"n={_fmt_n(row['n'])}"
        if not _label_chip(parts, left + chart_width + 10, y + 25, n_label, canvas_width=width, text_fill=FIGURE_MUTED):
            parts.append(
                f'<text x="{left + chart_width + 10}" y="{y + 25}" font-family="Arial, sans-serif" font-size="12" fill="#52616b">{html.escape(n_label)}</text>'
            )
    legend_y = height - 30
    for index, category in enumerate(["negative", "neutral", "positive"]):
        offset = index * 122
        parts.extend([
            f'<rect x="{left + offset}" y="{legend_y - 10}" width="10" height="10" fill="{FIGURE_PALETTE[category]}"/>',
            f'<text x="{left + offset + 16}" y="{legend_y}" font-family="Arial, sans-serif" font-size="12" fill="#52616b">{category}</text>',
        ])
    parts.append("</svg>")
    path.write_text("\n".join(parts), encoding="utf-8")


def _write_multilingual_volume_context(baseline: pd.DataFrame, path: Path) -> None:
    rows = baseline.copy()
    rows["label"] = rows["group"].astype(str).str.replace("_", " ", regex=False)
    rows = rows.sort_values(["source_kind", "volume"], ascending=[True, False])
    width = 1000
    top = 98
    row_height = 38
    left = 285
    right = 120
    height = top + 52 + max(1, len(rows)) * row_height
    chart_width = width - left - right
    max_volume = max([int(value) for value in rows["volume"]] or [1])
    parts = _svg_header(
        width,
        height,
        "Comparable Volume Context",
        "Rows represented by source group; rating shown only for Google reviews",
    )
    _gridlines(parts, left, chart_width, top - 4, top + (max(1, len(rows)) - 1) * row_height + 32)
    for index, (_, row) in enumerate(rows.iterrows()):
        y = top + index * row_height
        volume = int(row["volume"])
        bar_width = (volume / max_volume) * chart_width
        if row["source_kind"] == "google_review":
            color = FIGURE_PALETTE[str(row["group"])]
            metric = f"mean rating {float(row['rating_mean']):.2f}"
        else:
            color = FIGURE_PALETTE["chinese_social"]
            metric = f"SnowNLP mean {float(row['sentiment_norm_mean']):.2f}"
        value_label = f"n={_fmt_n(volume)}; {metric}"
        if bar_width > chart_width * 0.72:
            value_x = left + bar_width - 8
            value_anchor = "end"
            value_fill = "#ffffff"
        else:
            value_x = left + bar_width + 8
            value_anchor = "start"
            value_fill = "#1f2933"
        parts.extend([
            f'<text x="{left - 14}" y="{y + 23}" text-anchor="end" font-family="Arial, sans-serif" font-size="13" fill="#1f2933">{html.escape(str(row["label"])[:38])}</text>',
            f'<rect x="{left}" y="{y + 8}" width="{bar_width:.2f}" height="20" rx="3" fill="{color}"/>',
        ])
        if value_fill == "#ffffff" or not _label_chip(parts, value_x, y + 23, value_label, canvas_width=width, text_fill=value_fill, anchor=value_anchor):
            parts.append(
                f'<text x="{value_x:.2f}" y="{y + 23}" text-anchor="{value_anchor}" font-family="Arial, sans-serif" font-size="12" fill="{value_fill}">{html.escape(value_label)}</text>'
            )
    parts.append("</svg>")
    path.write_text("\n".join(parts), encoding="utf-8")


def _evidence_metric_type(row: pd.Series) -> str:
    test_name = str(row.get("test_name", ""))
    details = {}
    try:
        details = json.loads(str(row.get("details_json", "{}")))
    except json.JSONDecodeError:
        details = {}
    method = str(details.get("method", "")).lower()
    if test_name == "chi_square_sentiment_category" or "sentiment_category_independence" in test_name or "chi_square" in method:
        return "Cramér's V"
    if "mean_review_rating" in test_name:
        return "mean diff, stars"
    if "mean_difference_sentiment_score" in test_name:
        return "mean diff, tool score"
    if "prevalence" in test_name or "risk_difference" in test_name:
        return "risk diff, pp"
    return "effect"


def _write_statistical_evidence_summary(jp_en_tests: pd.DataFrame, cross_tests: pd.DataFrame, path: Path) -> None:
    selected = pd.concat([
        jp_en_tests[jp_en_tests["test_name"].isin([
            "chi_square_sentiment_category",
            "cluster_bootstrap_poi_mean_difference_sentiment_score",
            "poi_level_welch_t_mean_review_rating",
        ])],
        cross_tests[cross_tests["test_name"].isin([
            "cross_source_sentiment_category_independence",
            "within_chinese_platform_sentiment_category_independence",
            "cross_source_friction_prevalence_not_run",
            "cross_source_enjoyment_recommendation_prevalence_not_run",
        ])],
    ], ignore_index=True)
    width = 1000
    top = 98
    row_height = 42
    left = 365
    right = 80
    height = top + 78 + max(1, len(selected)) * row_height
    chart_width = width - left - right
    ok_effects = pd.to_numeric(selected.loc[selected["status"] == "ok", "effect"], errors="coerce").fillna(0)
    max_effect = max([float(value) for value in ok_effects] + [1.0])
    parts = _svg_header(
        width,
        height,
        "Statistical Check Status",
        "Effect metrics differ by row and are NOT comparable bar-to-bar",
    )
    _gridlines(parts, left, chart_width, top + 2, top + (max(1, len(selected)) - 1) * row_height + 32)
    for index, (_, row) in enumerate(selected.iterrows()):
        y = top + index * row_height
        name = str(row["test_name"]).replace("_", " ")
        status = str(row["status"])
        metric_type = _evidence_metric_type(row)
        if status == "ok":
            effect = float(pd.to_numeric(pd.Series([row.get("effect")]), errors="coerce").fillna(0).iloc[0])
            bar_width = (effect / max_effect) * chart_width
            label = f"effect={effect:.3f} ({metric_type})"
            color = "#5b6c94"
        else:
            bar_width = chart_width * 0.18
            label = f"{status} ({metric_type})"
            color = "#8d99ae"
        parts.extend([
            f'<text x="{left - 14}" y="{y + 24}" text-anchor="end" font-family="Arial, sans-serif" font-size="12" fill="#1f2933">{html.escape(name[:52])}</text>',
            f'<rect x="{left}" y="{y + 9}" width="{bar_width:.2f}" height="20" rx="3" fill="{color}"/>',
        ])
        if not _label_chip(parts, left + bar_width + 8, y + 24, label, canvas_width=width):
            parts.append(
                f'<text x="{left + bar_width + 8}" y="{y + 24}" font-family="Arial, sans-serif" font-size="12" fill="#1f2933">{html.escape(label)}</text>'
            )
    parts.append(
        _text(
            32,
            height - 24,
            "Bars are status indicators only; compare each effect to its own metric, not across rows.",
            size=12,
            fill=FIGURE_MUTED,
        )
    )
    parts.append("</svg>")
    path.write_text("\n".join(parts), encoding="utf-8")


def _write_figure_questions(path: Path, figure_questions: list[dict[str, str]]) -> None:
    lines = [
        "# Presentation Figure Questions",
        "",
        "Each figure is aggregate-only and omits row-level review/post text, author fields, URLs, screenshots, POI IDs, and review IDs.",
        "",
    ]
    for item in figure_questions:
        lines.extend([
            f"## {item['figure']}",
            "",
            f"- Path: `{item['path']}`",
            f"- Question answered: {item['question']}",
            f"- Use caveat: {item['caveat']}",
            "",
        ])
    path.write_text("\n".join(lines), encoding="utf-8")


def build_sentiment_chart_data(
    summary: pd.DataFrame,
    metadata_summary: pd.DataFrame,
    manifest: dict,
) -> pd.DataFrame:
    assert_no_forbidden_columns(
        summary.columns,
        forbidden=FORBIDDEN_PRESENTATION_COLUMNS,
        context="presentation sentiment input",
    )
    hashes = _input_hashes(manifest)
    metadata = metadata_summary.set_index(["prefecture_normalized", "city", "language_group"])
    rows = []
    for _, row in summary.sort_values(["language_group", "city"]).iterrows():
        key = (row["prefecture_normalized"], row["city"], row["language_group"])
        if key not in metadata.index:
            raise PresentationOutputError(
                "Missing date range / POI mix metadata for "
                f"{row['prefecture_normalized']} {row['city']} {row['language_group']}"
            )
        meta = metadata.loc[key]
        denominator = int(row["n_reviews"])
        rows.append({
            "figure_id": "jp_en_library_sentiment_secondary_check",
            "prefecture": row["prefecture_normalized"],
            "city": row["city"],
            "source_group": row["source_group"],
            "language_source_group": f"{row['language_group']}-language Google reviews",
            "sentiment_tool": "VADER" if row["language_group"] == "english" else "oseti",
            "n_reviews": denominator,
            "n_scored": int(row["n_scored"]),
            "positive_pct": round(float(row["positive_pct"]) * 100, 3),
            "neutral_pct": round(float(row["neutral_pct"]) * 100, 3),
            "negative_pct": round(float(row["negative_pct"]) * 100, 3),
            "positive_count": int(row["positive_count"]),
            "neutral_count": int(row["neutral_count"]),
            "negative_count": int(row["negative_count"]),
            "mean_sentiment_score": round(float(row["mean_sentiment_score"]), 6),
            "mean_review_rating": round(float(row["mean_review_rating"]), 6),
            "date_range_start": meta["date_range_start"],
            "date_range_end": meta["date_range_end"],
            "review_date_parseable_count": int(meta["review_date_parseable_count"]),
            "review_date_missing_count": int(meta["review_date_missing_count"]),
            "poi_mix": meta["poi_mix"],
            "source_hashes": json.dumps(hashes, sort_keys=True),
            "caveat": (
                "Secondary library-score check only; reviewed JP/EN codebook evidence is an audit/sensitivity path. "
                "Groups are language/source labels, not nationalities."
            ),
        })
    output = pd.DataFrame(rows)
    assert_no_forbidden_columns(
        output.columns,
        forbidden=FORBIDDEN_PRESENTATION_COLUMNS,
        context="presentation sentiment output",
    )
    _assert_no_fake_or_placeholder_values(output, "presentation sentiment output")
    return output


def build_test_summary(tests: pd.DataFrame, manifest: dict) -> pd.DataFrame:
    assert_no_forbidden_columns(
        tests.columns,
        forbidden=FORBIDDEN_PRESENTATION_COLUMNS,
        context="presentation statistical input",
    )
    rows = []
    for _, row in tests.sort_values(["test_name"]).iterrows():
        rows.append({
            "table_id": "jp_en_statistical_sensitivity",
            "test_name": row["test_name"],
            "comparison": row["comparison"],
            "status": row["status"],
            "statistic": row["statistic"],
            "p_value": row["p_value"],
            "effect": row["effect"],
            "presentation_use": (
                "descriptive_sensitivity_only"
                if str(row["status"]) == "ok"
                else "not_for_slide_claim"
            ),
            "caveat": (
                "Rows are nested in POIs and language groups are imbalanced; "
                "treat p-values as descriptive unless clustered/covariate model is justified."
            ),
            "reviews_input_sha256": _input_hashes(manifest)["reviews_input_sha256"],
        })
    output = pd.DataFrame(rows)
    assert_no_forbidden_columns(
        output.columns,
        forbidden=FORBIDDEN_PRESENTATION_COLUMNS,
        context="presentation statistical output",
    )
    _assert_no_fake_or_placeholder_values(output, "presentation statistical output")
    return output


def _write_readiness(
    path: Path,
    chart: pd.DataFrame,
    tests: pd.DataFrame,
    sentiment_manifest: dict,
    outputs: dict[str, Path],
    figure_outputs: dict[str, Path],
) -> None:
    total_reviews = int(chart["n_reviews"].sum()) if not chart.empty else 0
    caveats = sentiment_manifest.get("provenance", {}).get("caveats", [])
    if not caveats:
        raise PresentationOutputError(
            "Sentiment manifest has no caveats; rerun `make sentiment-analysis` before presenting."
        )
    hashes = _input_hashes(sentiment_manifest)
    lines = [
        "# Presentation-Safe Readiness",
        "",
        "Fukui-only JP-EN Google review aggregate scaffold for slides.",
        "",
        "## Use Status",
        "",
        "- Ready for presentation as a secondary library sentiment check.",
        "- Reviewed JP/EN keyword evidence is available as an audit/sensitivity path, not a replacement for VADER/oseti.",
        "- H1-H3 statistical rows are descriptive support, not confirmatory claims; use the within-POI paired Wilcoxon test as the venue-clustering robustness check.",
        "- SVG figures are organized under `japanese/`, `english/`, and `multilingual/`.",
        "",
        "## Denominators",
        "",
        f"- Total Google review rows represented: {total_reviews}",
    ]
    for _, row in chart.iterrows():
        lines.append(
            f"- {row['language_source_group']}: n={int(row['n_reviews'])}, "
            f"scored={int(row['n_scored'])}, city={row['city']}, "
            f"dated={int(row['review_date_parseable_count'])}, "
            f"undated={int(row['review_date_missing_count'])}"
        )
    lines.extend([
        "",
        "## Provenance Required On Slides",
        "",
        f"- Reviews input SHA256: {hashes['reviews_input_sha256']}",
        f"- POI metadata SHA256: {hashes['poi_metadata_sha256']}",
        f"- Sentiment summary SHA256: {sha256_file(outputs['chart_data'])}",
        f"- Statistical summary SHA256: {sha256_file(outputs['statistical_summary'])}",
        "- Date range: derived from parseable review_date values in ignored scored-review audit file; aggregate only.",
        "- Date coverage: chart data includes parseable and missing review_date counts.",
        "- POI mix: derived from ignored scored-review audit file; aggregate category counts only.",
        "",
        "## Captions",
        "",
        "Figure JP-EN library sentiment: Fukui Google reviews only. Bars show "
        "VADER English-language and oseti Japanese-language sentiment category "
        "shares as secondary checks. Denominators and hashes are in the chart "
        "data; language labels are not nationality claims.",
        "",
        "Table statistical sensitivity: H1-H3 rows are descriptive support. "
        "The within-POI paired Wilcoxon test is the venue-clustering robustness "
        "check; report its paired-POI N alongside the result.",
        "",
        "## Figure Folders",
        "",
    ])
    for name, figure_path in figure_outputs.items():
        lines.append(f"- `{name}`: `{figure_path}`")
    lines.extend([
        "",
        "Questions answered by each figure are documented in `presentation_figure_questions.md`.",
        "",
        "## Caveats From Upstream Manifest",
        "",
    ])
    lines.extend(f"- {caveat}" for caveat in caveats)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_presentation_safe_outputs(
    sentiment_summary_path: Path = DEFAULT_SENTIMENT_SUMMARY_PATH,
    sentiment_tests_path: Path = DEFAULT_SENTIMENT_TESTS_PATH,
    sentiment_manifest_path: Path = DEFAULT_SENTIMENT_MANIFEST_PATH,
    cross_language_baseline_path: Path = DEFAULT_CROSS_LANGUAGE_BASELINE_PATH,
    cross_language_tests_path: Path = DEFAULT_CROSS_LANGUAGE_TESTS_PATH,
    row_level_path: Path | None = None,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    command: str | None = None,
) -> dict:
    _require_input(sentiment_summary_path, "sentiment-analysis")
    _require_input(sentiment_tests_path, "sentiment-analysis")
    _require_input(sentiment_manifest_path, "sentiment-analysis")
    _require_input(cross_language_baseline_path, "cross-language-trends")
    _require_input(cross_language_tests_path, "cross-language-trends")

    summary = pd.read_csv(sentiment_summary_path)
    tests = pd.read_csv(sentiment_tests_path)
    cross_baseline = pd.read_csv(cross_language_baseline_path)
    cross_tests = pd.read_csv(cross_language_tests_path)
    manifest = _read_manifest(sentiment_manifest_path)
    audit_path = _row_level_path(manifest, row_level_path)
    _require_input(audit_path, "sentiment-analysis")
    row_level = pd.read_csv(audit_path)
    _require_columns(summary, REQUIRED_SUMMARY_COLUMNS, sentiment_summary_path)
    _require_columns(tests, REQUIRED_TEST_COLUMNS, sentiment_tests_path)
    _require_columns(cross_baseline, REQUIRED_BASELINE_COLUMNS, cross_language_baseline_path)
    _require_columns(cross_tests, REQUIRED_TEST_COLUMNS, cross_language_tests_path)
    _require_columns(row_level, REQUIRED_ROW_LEVEL_COLUMNS, audit_path)

    if set(summary["prefecture_normalized"].dropna().astype(str)) != {"Fukui"}:
        raise PresentationOutputError("Presentation-safe defaults require Fukui-only aggregate inputs.")
    if set(summary["language_group"].dropna().astype(str)) - {"english", "japanese"}:
        raise PresentationOutputError("Presentation-safe JP-EN output accepts only English/Japanese review groups.")

    output_dir.mkdir(parents=True, exist_ok=True)
    japanese_dir = output_dir / "japanese"
    english_dir = output_dir / "english"
    multilingual_dir = output_dir / "multilingual"
    for figure_dir in [japanese_dir, english_dir, multilingual_dir]:
        figure_dir.mkdir(parents=True, exist_ok=True)
    chart_path = output_dir / "jp_en_library_sentiment_chart_data.csv"
    test_summary_path = output_dir / "jp_en_statistical_sensitivity_summary.csv"
    figure_questions_path = output_dir / "presentation_figure_questions.md"
    readiness_path = output_dir / "presentation_readiness.md"
    manifest_path = output_dir / "presentation_manifest.json"

    metadata_summary = build_metadata_summary(row_level)
    chart = build_sentiment_chart_data(summary, metadata_summary, manifest)
    test_summary = build_test_summary(tests, manifest)
    chart.to_csv(chart_path, index=False)
    test_summary.to_csv(test_summary_path, index=False)

    figure_outputs = {
        "japanese_sentiment_profile": japanese_dir / "figure_japanese_sentiment_profile.svg",
        "japanese_poi_priority_mix": japanese_dir / "figure_japanese_poi_priority_mix.svg",
        "english_sentiment_profile": english_dir / "figure_english_sentiment_profile.svg",
        "english_poi_priority_mix": english_dir / "figure_english_poi_priority_mix.svg",
        "multilingual_sentiment_share": multilingual_dir / "figure_sentiment_share_by_language_source.svg",
        "multilingual_volume_context": multilingual_dir / "figure_volume_context.svg",
        "multilingual_statistical_evidence": multilingual_dir / "figure_statistical_evidence_summary.svg",
    }
    figure_questions = []
    for language, language_dir, label in [
        ("japanese", japanese_dir, "Japanese-Language Reviews"),
        ("english", english_dir, "English-Language Reviews"),
    ]:
        row = chart[chart["language_source_group"].str.startswith(language)].iloc[0]
        sentiment_path = figure_outputs[f"{language}_sentiment_profile"]
        poi_path = figure_outputs[f"{language}_poi_priority_mix"]
        _write_single_sentiment_profile(row, sentiment_path, label)
        _write_poi_priority_mix(row, poi_path, label)
        figure_questions.extend([
            {
                "figure": f"{label} sentiment profile",
                "path": str(sentiment_path),
                "question": f"What share of {language}-language Fukui Google reviews is positive, neutral, or negative under the secondary library tool?",
                "caveat": "Secondary library-score check; reviewed JP/EN keyword evidence is an audit/sensitivity path.",
            },
            {
                "figure": f"{label} tourism priority mix",
                "path": str(poi_path),
                "question": f"Which POI categories dominate the {language}-language review sample, shaping what tourism priorities the sentiment result reflects?",
                "caveat": "POI-category mix describes collection/sample composition, not all visitor priorities.",
            },
        ])
    _write_multilingual_sentiment_share(chart, cross_baseline, figure_outputs["multilingual_sentiment_share"])
    _write_multilingual_volume_context(cross_baseline, figure_outputs["multilingual_volume_context"])
    _write_statistical_evidence_summary(test_summary, cross_tests, figure_outputs["multilingual_statistical_evidence"])
    figure_questions.extend([
        {
            "figure": "Multilingual sentiment share",
            "path": str(figure_outputs["multilingual_sentiment_share"]),
            "question": "How do positive, neutral, and negative category shares differ across English-language reviews, Japanese-language reviews, and Chinese-language social rows?",
            "caveat": "Source platforms and scoring tools differ; use category shares only as descriptive comparison.",
        },
        {
            "figure": "Multilingual volume context",
            "path": str(figure_outputs["multilingual_volume_context"]),
            "question": "How imbalanced are the language/source group sample sizes, and which scales are available for each group?",
            "caveat": "Google ratings and SnowNLP sentiment means are different scales and should not be equated.",
        },
        {
            "figure": "Statistical evidence summary",
            "path": str(figure_outputs["multilingual_statistical_evidence"]),
            "question": "Which descriptive statistical checks have usable status, and which metric type belongs to each row?",
            "caveat": "Bars are status indicators only; effect metrics differ by row and are not comparable bar-to-bar.",
        },
    ])
    _write_figure_questions(figure_questions_path, figure_questions)

    outputs = {
        "chart_data": chart_path,
        "statistical_summary": test_summary_path,
        "figure_questions": figure_questions_path,
        "readiness": readiness_path,
    }
    _write_readiness(readiness_path, chart, test_summary, manifest, outputs, figure_outputs)

    report = research_manifest(
        kind="presentation_safe_jp_en_sentiment",
        command=command or " ".join(sys.argv),
        inputs=[
            file_record(sentiment_summary_path, "tracked_aggregate_summary", required=True),
            file_record(sentiment_tests_path, "tracked_statistical_tests", required=True),
            file_record(sentiment_manifest_path, "tracked_sentiment_manifest", required=True),
            file_record(cross_language_baseline_path, "aggregate_cross_language_baseline", required=True),
            file_record(cross_language_tests_path, "aggregate_cross_language_statistical_tests", required=True),
            file_record(audit_path, "ignored_scored_review_audit_file", required=True),
        ],
        outputs=[
            file_record(chart_path, "presentation_chart_data", required=True),
            file_record(test_summary_path, "presentation_statistical_summary", required=True),
            file_record(figure_questions_path, "presentation_figure_questions", required=True),
            *[
                file_record(path, f"presentation_figure_{name}", required=True)
                for name, path in figure_outputs.items()
            ],
            file_record(readiness_path, "presentation_readiness_markdown", required=True),
        ],
        filters={"prefecture": "Fukui", "groups": ["english", "japanese"]},
        metrics={
            "review_rows_represented": int(chart["n_reviews"].sum()) if not chart.empty else 0,
            "codebook_evidence_status": manifest.get("codebook_evidence_status", "unknown"),
            "date_range_status": "derived_from_scored_review_audit_file",
            "poi_mix_status": "derived_from_scored_review_audit_file",
            "figure_count": len(figure_outputs),
        },
        caveats=[
            "Presentation files are aggregate-only and must not be used as row-level evidence.",
            "Library sentiment is a secondary check until reviewed JP/EN codebook evidence is promoted.",
            "Language/source groups are not nationality groups.",
            "Date range and POI mix are aggregate metadata derived from the ignored scored-review audit file.",
        ],
        extra={"source_hashes": _input_hashes(manifest)},
    )
    write_json(manifest_path, report)
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sentiment-summary-path", type=Path, default=DEFAULT_SENTIMENT_SUMMARY_PATH)
    parser.add_argument("--sentiment-tests-path", type=Path, default=DEFAULT_SENTIMENT_TESTS_PATH)
    parser.add_argument("--sentiment-manifest-path", type=Path, default=DEFAULT_SENTIMENT_MANIFEST_PATH)
    parser.add_argument("--cross-language-baseline-path", type=Path, default=DEFAULT_CROSS_LANGUAGE_BASELINE_PATH)
    parser.add_argument("--cross-language-tests-path", type=Path, default=DEFAULT_CROSS_LANGUAGE_TESTS_PATH)
    parser.add_argument("--row-level-path", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        report = build_presentation_safe_outputs(
            sentiment_summary_path=args.sentiment_summary_path,
            sentiment_tests_path=args.sentiment_tests_path,
            sentiment_manifest_path=args.sentiment_manifest_path,
            cross_language_baseline_path=args.cross_language_baseline_path,
            cross_language_tests_path=args.cross_language_tests_path,
            row_level_path=args.row_level_path,
            output_dir=args.output_dir,
        )
    except (PresentationOutputError, ProvenanceError) as error:
        logger.error(str(error))
        return 1
    logger.info("Presentation-safe rows represented: %s", report["metrics"]["review_rows_represented"])
    logger.info("Output written: %s", args.output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
