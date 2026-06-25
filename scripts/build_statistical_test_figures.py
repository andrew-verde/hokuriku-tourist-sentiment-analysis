#!/usr/bin/env python3
"""Build aggregate-only SVG figures for the statistical test index.

This script:
1. Loads CSVs containing statistical test results (hypothesis tests, cross-language comparisons, within-language drivers)
2. Parses test results and effect sizes
3. Generates publication-quality SVG visualizations:
   - Forest charts (effect sizes with confidence intervals)
   - Bar/stacked-percent charts (sentiment shares, evidence prevalence)
   - Results panels (test verdicts and p-values)
   - Driver effect charts (within-language predictors)
4. Writes index markdown and manifest JSON
"""

from __future__ import annotations

import argparse
import html
import json
import math
import sys
import textwrap
from pathlib import Path
from typing import Iterable

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.provenance import (
    assert_no_forbidden_columns,
    file_record,
    repo_relative,
    research_manifest,
    write_json,
)

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INPUT_DIR = ROOT / "docs" / "statistical_test_outputs"
DEFAULT_OUTPUT_DIR = ROOT / "docs" / "statistical_test_figures"

FORBIDDEN_AGGREGATE_COLUMNS = {
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

PALETTE = {
    "english": "#2f6f73",
    "japanese": "#5b6c94",
    "chinese": "#bc6c25",
    "positive": "#2f6f73",
    "neutral": "#8d99ae",
    "negative": "#9a031e",
    "rating_1": "#963a35",
    "rating_2": "#c06c38",
    "rating_3": "#d6a14a",
    "rating_4": "#6f8f72",
    "rating_5": "#2f6f73",
    "score": "#5b6c94",
    "event": "#bc6c25",
    "line": "#d7dde8",
    "ink": "#172033",
    "muted": "#5b677a",
    "bg": "#fbfaf7",
}

GROUP_LABELS = {
    "english": "English-language reviews",
    "japanese": "Japanese-language reviews",
    "google_review_english": "English-language Google reviews",
    "google_review_japanese": "Japanese-language Google reviews",
    "chinese_social_all": "Chinese-language social rows",
    "chinese_social_xiaohongshu": "Chinese-language XHS rows",
}


class FigureBuildError(RuntimeError):
    pass


class MissingInputError(FigureBuildError):
    pass


class MissingColumnsError(FigureBuildError):
    pass


def _input(path: Path, make_target: str) -> Path:
    if not path.exists():
        raise MissingInputError(f"Required input not found: {path}. Run `make {make_target}` first.")
    return path


def _read_csv(path: Path, required: set[str], make_target: str) -> pd.DataFrame:
    # Load a CSV test results file, check for forbidden (row-level) columns, verify required columns.
    _input(path, make_target)
    df = pd.read_csv(path)

    # Privacy check: ensure aggregate outputs don't contain row-level text/IDs.
    assert_no_forbidden_columns(df.columns, forbidden=FORBIDDEN_AGGREGATE_COLUMNS, context=str(path))

    # Schema check: verify all required columns are present.
    missing = sorted(required - set(df.columns))
    if missing:
        raise MissingColumnsError(f"Required columns missing from {path}: {', '.join(missing)}")
    return df


def _parse_json(value: object) -> dict:
    # Parse JSON string stored in a CSV cell (e.g., contingency table details, text length stats).
    # Returns empty dict if value is NaN, malformed, or not a dict.
    if pd.isna(value):
        return {}
    try:
        parsed = json.loads(str(value))
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _fmt_n(value: object) -> str:
    return f"{int(float(value)):,}"


def _fmt_pct(value: object) -> str:
    return f"{float(value):.1f}%"


def _fmt_p(value: object) -> str:
    # Format p-value for display: "p=n/a", "p=0.001", or "p=1e-08" if very small.
    if pd.isna(value):
        return "p=n/a"
    number = float(value)
    if number < 0.001:
        return f"p={number:.1e}"
    return f"p={number:.3f}"


def _fmt_p_number(value: object) -> str:
    # Format p-value as plain number without "p=" prefix: "n/a", "0.001", or "1e-08".
    if pd.isna(value):
        return "n/a"
    number = float(value)
    if number < 0.001:
        return f"{number:.1e}"
    return f"{number:.3f}"


def _fmt_effect(value: object, label: str = "effect") -> str:
    # Format effect size label: "effect=n/a" or "V=0.123" (for Cramer's V) or "rho=0.456" (for Spearman).
    if pd.isna(value):
        return f"{label}=n/a"
    return f"{label}={float(value):.3f}"


def _fmt_signed(value: object, digits: int = 2) -> str:
    return f"{float(value):+.{digits}f}"


def _as_pct(value: object) -> float:
    number = float(value)
    return number * 100 if abs(number) <= 1 else number


def _safe_label(value: object, max_len: int = 42) -> str:
    text = str(value).replace("_", " ")
    return text if len(text) <= max_len else text[: max_len - 1] + "..."


def _wrapped_label_lines(value: object, max_len: int = 48) -> list[str]:
    text = str(value).replace("_", " ")
    lines = textwrap.wrap(text, width=max_len, break_long_words=False, break_on_hyphens=False)
    return lines or [""]


def _text(x: float, y: float, value: object, size: int = 13, weight: int = 400,
          fill: str = PALETTE["ink"], anchor: str = "start") -> str:
    return (
        f'<text x="{x:.2f}" y="{y:.2f}" text-anchor="{anchor}" '
        f'font-family="Arial, sans-serif" font-size="{size}" font-weight="{weight}" '
        f'fill="{fill}">{html.escape(str(value))}</text>'
    )


def _svg_header(width: int, height: int, title: str, subtitle: str) -> list[str]:
    return [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        f'<rect width="100%" height="100%" fill="{PALETTE["bg"]}"/>',
        _text(32, 39, title, size=24, weight=700),
        _text(32, 66, subtitle, size=14, fill=PALETTE["muted"]),
    ]


def _write_svg(path: Path, parts: list[str]) -> None:
    parts.append("</svg>")
    path.write_text("\n".join(parts), encoding="utf-8")


def _legend(parts: list[str], x: float, y: float, items: Iterable[tuple[str, str]]) -> None:
    offset = 0
    for label, color in items:
        parts.append(f'<rect x="{x + offset:.2f}" y="{y - 10:.2f}" width="10" height="10" fill="{color}"/>')
        parts.append(_text(x + offset + 16, y, label, size=12, fill=PALETTE["muted"]))
        offset += max(118, len(label) * 7 + 32)


def _required_row(df: pd.DataFrame, mask: pd.Series, label: str) -> pd.Series:
    rows = df[mask]
    if rows.empty:
        raise FigureBuildError(f"Required row missing for statistical figure: {label}")
    return rows.iloc[0]


def _chip(
    parts: list[str],
    x: float,
    y: float,
    width: float,
    height: float,
    label: str,
    *,
    fill: str = PALETTE["bg"],
    stroke: str = PALETTE["line"],
    text_fill: str = PALETTE["ink"],
    size: int = 11,
    weight: int = 400,
) -> None:
    parts.append(
        f'<rect x="{x:.2f}" y="{y:.2f}" width="{width:.2f}" height="{height:.2f}" '
        f'rx="4" fill="{fill}" stroke="{stroke}" stroke-width="1"/>'
    )
    parts.append(_text(x + width / 2, y + height / 2 + size / 2 - 2, label, size=size, weight=weight, fill=text_fill, anchor="middle"))


def _chip_width(label: str, size: int = 12) -> float:
    return max(34.0, len(label) * size * 0.54 + 16.0)


def _status_color(status: object) -> str:
    normalized = str(status).lower()
    if normalized == "supported":
        return PALETTE["positive"]
    if normalized in {"mixed", "partial"}:
        return PALETTE["event"]
    return PALETTE["neutral"]


def _label_chip(
    parts: list[str],
    x: float,
    baseline_y: float,
    label: str,
    *,
    anchor: str = "start",
    canvas_width: float,
    size: int = 12,
    text_fill: str = PALETTE["ink"],
) -> bool:
    chip_width = _chip_width(label, size=size)
    chip_height = 22
    if anchor == "end":
        chip_x = x - chip_width + 4
        if chip_x < 32:
            return False
    else:
        chip_x = x - 4
        if chip_x + chip_width > canvas_width - 32:
            return False
    _chip(
        parts,
        chip_x,
        baseline_y - 15,
        chip_width,
        chip_height,
        label,
        fill=PALETTE["bg"],
        stroke=PALETTE["line"],
        text_fill=text_fill,
        size=size,
    )
    return True


def _forest_chart(
    path: Path,
    title: str,
    subtitle: str,
    rows: list[dict[str, object]],
    note: str,
    *,
    x_min: float,
    x_max: float,
    ticks: list[float],
    caption: str | None = None,
    positive_annotation: str | None = None,
) -> None:
    # Generate a forest plot (effect size visualization) showing point estimates and confidence intervals.
    # Each row: label, point (effect size), ci_low/ci_high (95% CI bounds), p_chip, value_label, color.
    # Useful for comparing effect sizes across multiple tests/units of analysis.
    width = 1120
    top = 118
    row_height = 62
    left = 382
    chart_width = 430
    chart_right = left + chart_width
    p_chip_x = chart_right + 18
    value_chip_x = p_chip_x + 88
    value_chip_width = width - value_chip_x - 32
    axis_y = top + len(rows) * row_height + 9
    caption_space = 24 if caption else 0
    height = axis_y + 72 + caption_space

    def sx(value: float) -> float:
        # Convert value on x-axis to screen coordinates.
        return left + (value - x_min) / (x_max - x_min) * chart_width

    zero_x = sx(0.0)
    parts = _svg_header(width, height, title, subtitle)
    parts.append(
        f'<rect x="{max(left, zero_x):.2f}" y="{top - 28:.2f}" '
        f'width="{max(0.0, chart_right - max(left, zero_x)):.2f}" height="{len(rows) * row_height + 20:.2f}" '
        f'fill="{PALETTE["positive"]}" opacity="0.07"/>'
    )
    parts.append(
        f'<line x1="{zero_x:.2f}" x2="{zero_x:.2f}" y1="{top - 31:.2f}" y2="{axis_y:.2f}" '
        f'stroke="{PALETTE["line"]}" stroke-width="1.5" stroke-dasharray="5 5"/>'
    )

    if positive_annotation:
        parts.append(_text(chart_right - 8, top - 13, positive_annotation, size=12, fill=PALETTE["muted"], anchor="end"))

    for idx, row in enumerate(rows):
        y = top + idx * row_height
        cy = y + 24
        point = float(row["point"])
        color = str(row.get("color", PALETTE["score"]))
        parts.append(_text(left - 16, cy + 4, _safe_label(row["label"], 48), size=12, anchor="end"))
        parts.append(f'<line x1="{left:.2f}" x2="{chart_right:.2f}" y1="{cy:.2f}" y2="{cy:.2f}" stroke="{PALETTE["line"]}" stroke-width="1" opacity="0.65"/>')
        if row.get("ci_low") is not None and row.get("ci_high") is not None:
            low_x = sx(float(row["ci_low"]))
            high_x = sx(float(row["ci_high"]))
            parts.append(f'<line x1="{low_x:.2f}" x2="{high_x:.2f}" y1="{cy:.2f}" y2="{cy:.2f}" stroke="{color}" stroke-width="2.2"/>')
            parts.append(f'<line x1="{low_x:.2f}" x2="{low_x:.2f}" y1="{cy - 7:.2f}" y2="{cy + 7:.2f}" stroke="{color}" stroke-width="2.2"/>')
            parts.append(f'<line x1="{high_x:.2f}" x2="{high_x:.2f}" y1="{cy - 7:.2f}" y2="{cy + 7:.2f}" stroke="{color}" stroke-width="2.2"/>')
        parts.append(f'<circle cx="{sx(point):.2f}" cy="{cy:.2f}" r="5.2" fill="{color}"/>')
        _chip(parts, p_chip_x, cy - 12, 76, 23, str(row.get("p_chip", "")), fill=PALETTE["bg"], stroke=PALETTE["line"], text_fill=PALETTE["muted"], size=10)
        _chip(parts, value_chip_x, cy - 13, value_chip_width, 25, str(row.get("value_label", _fmt_signed(point, 2))), fill=PALETTE["bg"], stroke=PALETTE["line"], text_fill=PALETTE["ink"], size=11, weight=700)

    parts.append(f'<line x1="{left:.2f}" x2="{chart_right:.2f}" y1="{axis_y:.2f}" y2="{axis_y:.2f}" stroke="{PALETTE["line"]}" stroke-width="1.2"/>')
    for tick in ticks:
        x = sx(float(tick))
        parts.append(f'<line x1="{x:.2f}" x2="{x:.2f}" y1="{axis_y:.2f}" y2="{axis_y + 6:.2f}" stroke="{PALETTE["line"]}" stroke-width="1"/>')
        tick_label = "0" if abs(float(tick)) < 0.0005 else f"{float(tick):.2f}".rstrip("0").rstrip(".")
        parts.append(_text(x, axis_y + 22, tick_label, size=11, fill=PALETTE["muted"], anchor="middle"))

    if caption:
        parts.append(_text(32, height - 42, caption, size=12, fill=PALETTE["muted"]))
        parts.append(_text(32, height - 18, note, size=12, fill=PALETTE["muted"]))
    else:
        parts.append(_text(32, height - 18, note, size=12, fill=PALETTE["muted"]))
    _write_svg(path, parts)


def _results_panel(
    path: Path,
    title: str,
    subtitle: str,
    rows: list[dict[str, str]],
    note: str,
) -> None:
    width = 1120
    top = 104
    row_height = 70
    height = top + len(rows) * row_height + 54
    parts = _svg_header(width, height, title, subtitle)
    for idx, row in enumerate(rows):
        y = top + idx * row_height
        if idx % 2:
            parts.append(
                f'<rect x="32" y="{y - 11:.2f}" width="1056" height="56" '
                f'rx="6" fill="{PALETTE["line"]}" opacity="0.22"/>'
            )
        parts.append(_text(58, y + 12, row["label"], size=15, weight=700))
        parts.append(_text(172, y + 12, row["verdict"], size=13, fill=PALETTE["ink"]))
        _chip(parts, 590, y - 8, 318, 30, row["effect"], fill=PALETTE["bg"], stroke=PALETTE["line"], text_fill=PALETTE["ink"], size=10, weight=700)
        _chip(parts, 920, y - 8, 98, 30, row["p"], fill=PALETTE["bg"], stroke=PALETTE["line"], text_fill=PALETTE["muted"], size=10)
        status_color = _status_color(row["status"])
        _chip(parts, 1030, y - 8, 58, 30, row["status"], fill=status_color, stroke=status_color, text_fill=PALETTE["bg"], size=9, weight=700)
    parts.append(_text(32, height - 18, note, size=12, fill=PALETTE["muted"]))
    _write_svg(path, parts)


def _stacked_pct_chart(
    path: Path,
    title: str,
    subtitle: str,
    rows: list[dict[str, object]],
    categories: list[tuple[str, str]],
    note: str,
) -> None:
    # Generate a 100% stacked bar chart showing category shares (e.g., negative/neutral/positive sentiment %).
    # Each row is one group; categories are the segments that stack to 100%.
    # Useful for showing how sentiment distribution shifts between language/source groups.
    width = 1120
    top = 104
    row_height = 54
    left = 295
    right = 118
    height = top + 92 + max(1, len(rows)) * row_height
    chart_width = width - left - right
    parts = _svg_header(width, height, title, subtitle)
    grid_bottom = top + (max(1, len(rows)) - 1) * row_height + 38

    # Add vertical grid lines at 0%, 50%, 100%.
    for tick_pct in (0.0, 0.5, 1.0):
        x = left + tick_pct * chart_width
        parts.append(
            f'<line x1="{x:.2f}" x2="{x:.2f}" y1="{top + 2:.2f}" y2="{grid_bottom:.2f}" '
            f'stroke="{PALETTE["line"]}" stroke-width="1" opacity="0.55"/>'
        )
    for idx, row in enumerate(rows):
        y = top + idx * row_height
        parts.append(_text(left - 14, y + 26, _safe_label(row["label"], 36), size=13, anchor="end"))
        x = left
        for key, color in categories:
            value = float(row.get(key, 0.0))
            segment_width = (value / 100.0) * chart_width
            parts.append(
                f'<rect x="{x:.2f}" y="{y + 8:.2f}" width="{segment_width:.2f}" height="25" fill="{color}"/>'
            )
            if segment_width > 42:
                parts.append(_text(x + segment_width / 2, y + 26, f"{value:.1f}%", size=11, fill="#ffffff", anchor="middle"))
            x += segment_width
        if row.get("n") is not None:
            label = f"n={_fmt_n(row['n'])}"
            if not _label_chip(parts, left + chart_width + 10, y + 26, label, canvas_width=width, size=12, text_fill=PALETTE["muted"]):
                parts.append(_text(left + chart_width + 10, y + 26, label, size=12, fill=PALETTE["muted"]))
    _legend(parts, left, height - 42, [(key, color) for key, color in categories])
    parts.append(_text(32, height - 18, note, size=12, fill=PALETTE["muted"]))
    _write_svg(path, parts)


def _horizontal_bar_chart(
    path: Path,
    title: str,
    subtitle: str,
    rows: list[dict[str, object]],
    value_key: str,
    color_key: str,
    value_label: str,
    note: str,
    *,
    zero_center: bool = False,
    max_abs: float | None = None,
) -> None:
    # Generate a horizontal bar chart for showing effect sizes, differences, or other single-value metrics.
    # If zero_center=True, bars can extend left (negative) or right (positive) from center.
    # Otherwise, bars start from the left and extend rightward.
    width = 1120
    top = 102
    row_height = 39
    left = 365
    right = 170
    height = top + 76 + max(1, len(rows)) * row_height
    chart_width = width - left - right

    values = [float(row.get(value_key, 0.0) or 0.0) for row in rows]
    if zero_center:
        limit = max_abs or max([abs(value) for value in values] + [1.0])
    else:
        limit = max_abs or max(values + [1.0])
    parts = _svg_header(width, height, title, subtitle)
    y1 = top - 8
    y2 = height - 62
    if zero_center:
        axis_x = left + chart_width / 2
        for x in (left, axis_x, left + chart_width):
            parts.append(f'<line x1="{x:.2f}" x2="{x:.2f}" y1="{y1:.2f}" y2="{y2:.2f}" stroke="{PALETTE["line"]}" stroke-width="1" opacity="0.65"/>')
    else:
        for tick_pct in (0.0, 0.5, 1.0):
            x = left + tick_pct * chart_width
            parts.append(f'<line x1="{x:.2f}" x2="{x:.2f}" y1="{y1:.2f}" y2="{y2:.2f}" stroke="{PALETTE["line"]}" stroke-width="1" opacity="0.65"/>')
    parts.append(f'<line x1="{left:.2f}" x2="{left + chart_width:.2f}" y1="{y2:.2f}" y2="{y2:.2f}" stroke="{PALETTE["line"]}" stroke-width="1" opacity="0.75"/>')
    for idx, row in enumerate(rows):
        y = top + idx * row_height
        value = float(row.get(value_key, 0.0) or 0.0)
        color = str(row.get(color_key, PALETTE["score"]))
        parts.append(_text(left - 14, y + 23, _safe_label(row["label"], 48), size=12, anchor="end"))
        if zero_center:
            axis_x = left + chart_width / 2
            bar_width = abs(value) / limit * (chart_width / 2)
            x = axis_x - bar_width if value < 0 else axis_x
        else:
            x = left
            bar_width = value / limit * chart_width
        parts.append(f'<rect x="{x:.2f}" y="{y + 8:.2f}" width="{bar_width:.2f}" height="20" rx="3" fill="{color}"/>')
        text_x = x + bar_width + 8 if value >= 0 or not zero_center else x - 8
        anchor = "start" if value >= 0 or not zero_center else "end"
        label = str(row.get("annotation", f"{value_label}={value:.3f}"))
        if not _label_chip(parts, text_x, y + 23, label, anchor=anchor, canvas_width=width, size=12):
            parts.append(_text(text_x, y + 23, label, size=12, anchor=anchor))
    parts.append(_text(32, height - 20, note, size=12, fill=PALETTE["muted"]))
    _write_svg(path, parts)


def _driver_effect_chart(
    path: Path,
    title: str,
    subtitle: str,
    groups: list[dict[str, object]],
    note: str,
) -> None:
    # Generate a multi-panel driver effect chart showing how different predictors explain within-language sentiment.
    # Each panel shows a different outcome type (score differences, event risk differences, correlations, etc.)
    # with a separate axis. Useful for visualizing many effect sizes across different statistical models.
    width = 1240
    top = 102
    left = 470
    right = 190
    chart_width = width - left - right
    row_base_height = 38
    line_gap = 14
    panel_gap = 28
    axis_height = 30

    visible_groups = [group for group in groups if group["rows"]]
    for group in visible_groups:
        rows = group["rows"]
        # Compute row heights based on label line wrapping.
        for row in rows:
            row["label_lines"] = _wrapped_label_lines(row["label"], 50)
            row["height"] = max(row_base_height, 16 + len(row["label_lines"]) * line_gap)
        # Each panel has rows, plus top padding and an axis.
        group["height"] = 42 + sum(int(row["height"]) for row in rows) + axis_height

    height = top + sum(int(group["height"]) for group in visible_groups) + panel_gap * max(0, len(visible_groups) - 1) + 64
    parts = _svg_header(width, height, title, subtitle)
    y = top
    for group in visible_groups:
        rows = group["rows"]
        values = [abs(float(row["value"])) for row in rows]
        limit = max(values + [float(group.get("min_limit", 0.1))])
        axis_x = left + chart_width / 2
        panel_top = y + 28
        row_y = y + 42
        panel_bottom = row_y + sum(int(row["height"]) for row in rows) + 2

        parts.append(_text(32, y + 12, group["title"], size=14, weight=700))
        parts.append(_text(left, y + 12, f"Unit: {group['unit']}", size=12, fill=PALETTE["muted"]))
        for x in (left, axis_x, left + chart_width):
            parts.append(
                f'<line x1="{x:.2f}" x2="{x:.2f}" y1="{panel_top:.2f}" y2="{panel_bottom:.2f}" '
                f'stroke="{PALETTE["line"]}" stroke-width="1" opacity="0.65"/>'
            )

        for row in rows:
            row_height = int(row["height"])
            cy = row_y + row_height / 2
            value = float(row["value"])
            color = str(row.get("color", PALETTE["score"]))
            label_lines = row["label_lines"]
            first_baseline = cy - ((len(label_lines) - 1) * line_gap / 2) + 4
            for line_idx, line in enumerate(label_lines):
                parts.append(_text(left - 16, first_baseline + line_idx * line_gap, line, size=11, anchor="end"))
            parts.append(
                f'<line x1="{left:.2f}" x2="{left + chart_width:.2f}" y1="{cy:.2f}" y2="{cy:.2f}" '
                f'stroke="{PALETTE["line"]}" stroke-width="1" opacity="0.55"/>'
            )
            bar_width = abs(value) / limit * (chart_width / 2) if limit else 0.0
            x = axis_x - bar_width if value < 0 else axis_x
            parts.append(f'<rect x="{x:.2f}" y="{cy - 10:.2f}" width="{bar_width:.2f}" height="20" rx="3" fill="{color}"/>')
            label = str(row["annotation"])
            chip_width = _chip_width(label, size=11)
            if value < 0:
                text_x = axis_x + 8
                anchor = "start"
            else:
                text_x = x + bar_width + 8
                anchor = "start"
            if text_x - 4 + chip_width > width - 32:
                text_x = width - 32
                anchor = "end"
            if not _label_chip(parts, text_x, cy + 4, label, anchor=anchor, canvas_width=width, size=11):
                parts.append(_text(text_x, cy + 4, label, size=11, anchor=anchor))
            row_y += row_height

        axis_y = panel_bottom + 10
        parts.append(
            f'<line x1="{left:.2f}" x2="{left + chart_width:.2f}" y1="{axis_y:.2f}" y2="{axis_y:.2f}" '
            f'stroke="{PALETTE["line"]}" stroke-width="1" opacity="0.75"/>'
        )
        for tick in (-limit, 0.0, limit):
            x = axis_x + (tick / limit) * (chart_width / 2) if limit else axis_x
            parts.append(f'<line x1="{x:.2f}" x2="{x:.2f}" y1="{axis_y:.2f}" y2="{axis_y + 6:.2f}" stroke="{PALETTE["line"]}" stroke-width="1"/>')
            tick_label = "0" if abs(tick) < 0.0005 else f"{tick:+.2f}".rstrip("0").rstrip(".")
            if group.get("tick_suffix"):
                tick_label = f"{tick_label}{group['tick_suffix']}"
            parts.append(_text(x, axis_y + 22, tick_label, size=10, fill=PALETTE["muted"], anchor="middle"))
        y = panel_bottom + axis_height + panel_gap

    parts.append(_text(32, height - 20, note, size=12, fill=PALETTE["muted"]))
    _write_svg(path, parts)


def _grouped_pct_chart(
    path: Path,
    title: str,
    subtitle: str,
    rows: list[dict[str, object]],
    groups: list[tuple[str, str] | tuple[str, str, str]],
    note: str,
) -> None:
    width = 1120
    top = 104
    row_height = 76
    left = 310
    right = 130
    height = top + 92 + max(1, len(rows)) * row_height
    chart_width = width - left - right
    parts = _svg_header(width, height, title, subtitle)
    grid_bottom = top + (max(1, len(rows)) - 1) * row_height + 56
    for tick_pct in (0.0, 0.5, 1.0):
        x = left + tick_pct * chart_width
        parts.append(
            f'<line x1="{x:.2f}" x2="{x:.2f}" y1="{top - 2:.2f}" y2="{grid_bottom:.2f}" '
            f'stroke="{PALETTE["line"]}" stroke-width="1" opacity="0.55"/>'
        )
    for idx, row in enumerate(rows):
        y = top + idx * row_height
        parts.append(_text(left - 14, y + 33, _safe_label(row["label"], 38), size=13, anchor="end"))
        bar_h = 15
        for gidx, group_item in enumerate(groups):
            key, color = group_item[0], group_item[1]
            value = float(row.get(key, 0.0) or 0.0)
            bar_y = y + gidx * 19
            bar_width = (value / 100.0) * chart_width
            parts.append(f'<rect x="{left}" y="{bar_y}" width="{bar_width:.2f}" height="{bar_h}" rx="2" fill="{color}"/>')
            label = f"{value:.1f}%"
            if not _label_chip(parts, left + bar_width + 8, bar_y + 12, label, canvas_width=width, size=11):
                parts.append(_text(left + bar_width + 8, bar_y + 12, label, size=11))
    legend_items = []
    for group_item in groups:
        key, color = group_item[0], group_item[1]
        label = group_item[2] if len(group_item) > 2 else key
        legend_items.append((label, color))
    _legend(parts, left, height - 42, legend_items)
    parts.append(_text(32, height - 18, note, size=12, fill=PALETTE["muted"]))
    _write_svg(path, parts)


def _observed_share_rows(details: dict, labels: dict[str, str] | None = None) -> list[dict[str, object]]:
    observed = details.get("observed", {})
    denominators = details.get("denominators", {})
    groups = sorted(denominators)
    rows: list[dict[str, object]] = []
    for group in groups:
        n = float(denominators[group])
        row: dict[str, object] = {"label": (labels or GROUP_LABELS).get(group, group), "n": n}
        for category, group_counts in observed.items():
            row[str(category)] = float(group_counts.get(group, 0)) / n * 100 if n else 0.0
        rows.append(row)
    return rows


def write_h1_figures(h1: pd.DataFrame, output_dir: Path) -> list[dict[str, str]]:
    # Generate figures for Hypothesis 1: sentiment category share differences between JP and EN reviews.
    # H1 is the primary hypothesis, tested via chi-square on the contingency table of language_group x sentiment_category.

    primary = h1[(h1["analysis_type"] == "primary") & (h1["status"] == "ok")].copy()

    # Prepare data for stacked bar chart: one bar per language group, segments = sentiment categories.
    rows = []
    for language, chunk in primary.groupby("language_group", sort=False):
        row = {
            "label": GROUP_LABELS.get(str(language), str(language)),
            "n": int(chunk["observed_count"].sum()),
        }
        # Extract category percentages (convert from 0-1 fraction to 0-100 percent).
        for _, item in chunk.iterrows():
            row[str(item["category"])] = float(item["category_share"]) * 100
        rows.append(row)

    # Figure 1: Sentiment category shares (e.g., "35% positive English vs 28% positive Japanese").
    path1 = output_dir / "figure_h1_sentiment_category_share.svg"
    p = primary["p_value_holm"].dropna().iloc[0] if not primary.empty else math.nan
    effect = primary["effect_cramers_v"].dropna().iloc[0] if not primary.empty else math.nan
    _stacked_pct_chart(
        path1,
        "H1 Sentiment Category Shares",
        f"JP/EN Google reviews; {_fmt_p(p)}, Cramer's V={float(effect):.3f}",
        rows,
        [("negative", PALETTE["negative"]), ("neutral", PALETTE["neutral"]), ("positive", PALETTE["positive"])],
        "Category-share test only; VADER and oseti raw scores stay separate.",
    )

    # Figure 2: Sensitivity analysis—does H1 hold if we use wider neutral bands?
    # Neutral bands of 0.10 and 0.20 are stricter (fewer reviews categorized as "neutral").
    # Confirms the finding isn't just an artifact of the neutral-band definition.
    sensitivity = (
        h1[h1["status"] == "ok"]
        .drop_duplicates(["category_source_column"])
        .sort_values("neutral_band_note")
    )
    rows2 = []
    for _, row in sensitivity.iterrows():
        rows2.append({
            "label": row["neutral_band_note"],
            "value": float(row["effect_cramers_v"]),
            "color": PALETTE["score"],
            "annotation": f"V={float(row['effect_cramers_v']):.3f}; {_fmt_p(row['p_value_holm'])}",
        })

    path2 = output_dir / "figure_h1_neutral_band_sensitivity.svg"
    _horizontal_bar_chart(
        path2,
        "H1 Neutral-Band Sensitivity",
        "Effect remains visible as neutral band widens",
        rows2,
        "value",
        "color",
        "V",
        "Sensitivity rows are robustness checks, not new independent hypotheses.",
        max_abs=0.2,
    )
    return [
        {"figure": "H1 sentiment category shares", "path": str(path1), "question": "Which sentiment categories drive the JP/EN difference?", "caveat": "Category shares only; raw sentiment scores are not common-scale."},
        {"figure": "H1 neutral-band sensitivity", "path": str(path2), "question": "Does H1 survive wider neutral-band definitions?", "caveat": "Sensitivity rows are robustness checks."},
    ]


def write_h2_figures(h2: pd.DataFrame, output_dir: Path) -> list[dict[str, str]]:
    # Generate figures for Hypothesis 2: English-language reviews rate higher on Google's 1-to-5 star scale.
    # H2 uses the common Google star rating as companion outcome evidence (not VADER/oseti, which are tool-specific).

    summaries = h2[h2["analysis_type"] == "group_summary"].copy()

    # Prepare data for 5-star rating distribution chart.
    rating_rows = []
    for _, row in summaries.iterrows():
        dist = _parse_json(row["rating_distribution_json"])  # JSON dict: "1"->count, "2"->count, etc.
        n = sum(int(value) for value in dist.values())
        chart_row = {"label": GROUP_LABELS.get(str(row["language_group"]), row["language_group"]), "n": n}
        # Convert counts to percentages for each star level.
        for rating in range(1, 6):
            chart_row[f"rating_{rating}"] = int(dist.get(str(rating), 0)) / n * 100 if n else 0.0
        rating_rows.append(chart_row)

    # Figure 1: Star rating distribution by language group.
    path1 = output_dir / "figure_h2_rating_distribution.svg"
    p_dist = h2.loc[h2["test_name"] == "chi_square_rating_distribution", "p_value"].dropna()
    _stacked_pct_chart(
        path1,
        "H2 Star Rating Distribution",
        f"Common 1-to-5 Google scale; {_fmt_p(p_dist.iloc[0] if not p_dist.empty else math.nan)}",
        rating_rows,
        [(f"rating_{i}", PALETTE[f"rating_{i}"]) for i in range(1, 6)],
        "Ceiling effects matter: both groups skew high, but English has more 5-star rows.",
    )

    rows2 = []
    for _, row in summaries.iterrows():
        rows2.append({
            "label": f"{GROUP_LABELS.get(str(row['language_group']), row['language_group'])} mean",
            "value": float(row["mean_review_rating"]),
            "color": PALETTE[str(row["language_group"])],
            "annotation": f"mean={float(row['mean_review_rating']):.2f}; n={_fmt_n(row['n_rating_present'])}",
        })
    for _, row in h2[h2["analysis_type"].isin(["test", "sensitivity"])].iterrows():
        if pd.notna(row.get("effect_mean_difference")):
            rows2.append({
                "label": _safe_label(str(row["test_name"]), 50),
                "value": float(row["effect_mean_difference"]),
                "color": PALETTE["event"],
                "annotation": f"EN-JP={float(row['effect_mean_difference']):.2f}; {_fmt_p(row['p_value'])}",
            })
    path2 = output_dir / "figure_h2_rating_mean_sensitivity.svg"
    _horizontal_bar_chart(
        path2,
        "H2 Mean Rating + Sensitivity",
        "English-language reviews rate higher on common Google scale",
        rows2,
        "value",
        "color",
        "value",
        "Mean rows use 1-to-5 stars; difference rows show English minus Japanese.",
        max_abs=5.0,
    )
    return [
        {"figure": "H2 star rating distribution", "path": str(path1), "question": "Where does the rating-distribution difference appear?", "caveat": "Common Google stars, not text-sentiment equivalence."},
        {"figure": "H2 mean rating sensitivity", "path": str(path2), "question": "How large is the English-minus-Japanese rating gap under row and POI sensitivity?", "caveat": "Rows remain nested in POIs."},
    ]


def write_h3_figures(h3: pd.DataFrame, output_dir: Path) -> list[dict[str, str]]:
    # Generate figures for Hypothesis 3: English reviews contain more enjoyment/recommendation evidence.
    # H3 uses reviewed (manually-coded) keyword matching, separate from VADER/oseti.
    # Tests use Benjamini–Hochberg FDR adjustment for multiple comparisons.

    evidence = h3[h3["analysis_type"] == "evidence_family_test"].copy()

    # Prepare data for grouped bar chart: one pair of bars per evidence family, sorted by risk difference.
    rows = []
    for _, row in evidence.sort_values("risk_difference_pct", ascending=False).iterrows():
        rows.append({
            "label": row["evidence_family"],
            "english": _as_pct(row["english_present_pct"]),
            "japanese": _as_pct(row["japanese_present_pct"]),
            "annotation": f"diff={float(row['risk_difference_pct']):.1f} pp; {_fmt_p(row['p_value_bh_fdr'])}",
        })

    # Figure 1: Evidence prevalence by family (e.g., "friction", "enjoyment", "positive_sentiment").
    path1 = output_dir / "figure_h3_reviewed_evidence_prevalence.svg"
    _grouped_pct_chart(
        path1,
        "H3 Reviewed Evidence Prevalence",
        "English-language rows show more enjoyment/recommendation/positive evidence; friction similar",
        rows,
        [
            ("english", PALETTE["english"], "English-language reviews"),
            ("japanese", PALETTE["japanese"], "Japanese-language reviews"),
        ],
        "FDR-adjusted tests use reviewed keyword evidence, aggregate-only.",
    )

    diagnostic = h3[h3["analysis_type"] == "diagnostic"].head(1)
    length_rows = []
    if not diagnostic.empty:
        text_lengths = _parse_json(diagnostic.iloc[0]["text_length_summary_json"])
        for language, values in text_lengths.items():
            length_rows.append({
                "label": f"{GROUP_LABELS.get(language, language)} mean chars",
                "value": float(values.get("mean", 0.0)),
                "color": PALETTE.get(language, PALETTE["score"]),
                "annotation": f"mean={float(values.get('mean', 0.0)):.1f}; median={float(values.get('median', 0.0)):.1f}",
            })
    path2 = output_dir / "figure_h3_text_length_diagnostic.svg"
    _horizontal_bar_chart(
        path2,
        "H3 Text Length Diagnostic",
        "Longer reviews have more opportunity to match evidence terms",
        length_rows,
        "value",
        "color",
        "chars",
        "Use as caveat beside H3 evidence-prevalence claims.",
    )
    return [
        {"figure": "H3 reviewed evidence prevalence", "path": str(path1), "question": "Which reviewed evidence families differ most between JP/EN review rows?", "caveat": "Keyword evidence prevalence; text length can affect match opportunity."},
        {"figure": "H3 text length diagnostic", "path": str(path2), "question": "How much more text is available for evidence matching by language group?", "caveat": "Diagnostic only."},
    ]


def write_cross_source_figures(cross_tests: pd.DataFrame, date_scrub: pd.DataFrame, chinese_city: pd.DataFrame, output_dir: Path) -> list[dict[str, str]]:
    questions: list[dict[str, str]] = []
    primary = cross_tests[cross_tests["test_name"] == "cross_source_sentiment_category_independence"].head(1)
    if not primary.empty:
        details = _parse_json(primary.iloc[0]["details_json"])
        rows = _observed_share_rows(details)
        path = output_dir / "figure_cross_source_sentiment_category.svg"
        _stacked_pct_chart(
            path,
            "Cross-Source Sentiment Category Shares",
            f"Descriptive source-aware comparison; {_fmt_p(primary.iloc[0]['p_value'])}, V={float(primary.iloc[0]['effect']):.3f}",
            rows,
            [("negative", PALETTE["negative"]), ("neutral", PALETTE["neutral"]), ("positive", PALETTE["positive"])],
            "Google reviews and Xiaohongshu rows differ in platform, unit, and scoring tool.",
        )
        questions.append({"figure": "Cross-source sentiment category shares", "path": str(path), "question": "How do category shares differ across English, Japanese, and Chinese-language source groups?", "caveat": "Descriptive only across platforms/tools."})

    evidence_rows = []
    for test_name, label in [
        ("cross_source_friction_prevalence", "Friction evidence"),
        ("cross_source_enjoyment_recommendation_prevalence", "Enjoyment evidence"),
    ]:
        row = cross_tests[cross_tests["test_name"] == test_name].head(1)
        if row.empty:
            continue
        details = _parse_json(row.iloc[0]["details_json"])
        observed = details.get("observed", {})
        denominators = details.get("denominators", {})
        chart_row: dict[str, object] = {"label": label}
        for group in ["google_review_english", "google_review_japanese", "chinese_social_all"]:
            n = float(denominators.get(group, 0.0))
            chart_row[group] = float(observed.get("present", {}).get(group, 0.0)) / n * 100 if n else 0.0
        evidence_rows.append(chart_row)
    path = output_dir / "figure_cross_source_evidence_prevalence.svg"
    _grouped_pct_chart(
        path,
        "Cross-Source Evidence Prevalence",
        "Chinese-language XHS rows carry much more friction and enjoyment evidence",
        evidence_rows,
        [
            ("google_review_english", PALETTE["english"], "English Google"),
            ("google_review_japanese", PALETTE["japanese"], "Japanese Google"),
            ("chinese_social_all", PALETTE["chinese"], "Chinese XHS"),
        ],
        "Reviewed evidence tests are source-aware discourse comparisons, not behavior rates.",
    )
    questions.append({"figure": "Cross-source evidence prevalence", "path": str(path), "question": "Which source group most often contains friction or enjoyment evidence?", "caveat": "Source/platform units differ."})

    rows = []
    for _, row in cross_tests.iterrows():
        status = str(row["status"])
        value = 0.03 if status != "ok" or pd.isna(row["effect"]) else float(row["effect"])
        color = PALETTE["score"] if status == "ok" else PALETTE["neutral"]
        rows.append({
            "label": row["test_name"],
            "value": value,
            "color": color,
            "annotation": f"{status}; {_fmt_effect(row['effect'], 'V')}; {_fmt_p(row['p_value'])}",
        })
    path = output_dir / "figure_cross_source_test_effects.svg"
    _horizontal_bar_chart(
        path,
        "Cross-Source Test Effects And Gaps",
        "Largest descriptive effects are evidence-prevalence tests; platform-only CN checks skipped",
        rows,
        "value",
        "color",
        "V",
        "Skipped rows mark unavailable comparison groups, not null results.",
        max_abs=0.45,
    )
    questions.append({"figure": "Cross-source test effects and gaps", "path": str(path), "question": "Which cross-source tests have strongest descriptive effects, and which are skipped?", "caveat": "Skipped rows mean insufficient comparison groups."})

    scrub_rows = []
    grouped = date_scrub.groupby("source_kind", dropna=False)
    for source_kind, chunk in grouped:
        usable = int(chunk.loc[chunk["usable_for_monthly_trends"].astype(bool), "count"].sum())
        total = int(chunk["count"].sum())
        scrub_rows.append({
            "label": str(source_kind).replace("_", " "),
            "usable": usable / total * 100 if total else 0.0,
            "needs repair": (total - usable) / total * 100 if total else 0.0,
            "n": total,
        })
    path = output_dir / "figure_date_scrub_requirements.svg"
    _stacked_pct_chart(
        path,
        "Date Quality For Trend Claims",
        "Monthly trend figures should wait until weak dates are repaired",
        scrub_rows,
        [("usable", PALETTE["positive"]), ("needs repair", PALETTE["negative"])],
        "Google review dates are mostly usable; Chinese social dates need repair before monthly trend claims.",
    )
    questions.append({"figure": "Date quality for trend claims", "path": str(path), "question": "Which source dates are usable for monthly trend analysis?", "caveat": "Date quality diagnostic, not hypothesis evidence."})

    status = "ready" if not chinese_city.empty else "no comparison rows available"
    path = output_dir / "figure_chinese_city_platform_friction_status.svg"
    if chinese_city.empty:
        width = 1120
        height = 260
        parts = _svg_header(
            width,
            height,
            "Chinese City/Platform Friction Status",
            "Current tracked output is header-only because comparison groups are unavailable",
        )
        message = (
            "No within-Chinese city/platform comparison available - current Fukui "
            "Chinese-language posts are single-platform (Xiaohongshu only)."
        )
        parts.append(
            f'<rect x="172.00" y="104.00" width="776.00" height="74.00" rx="6" '
            f'fill="{PALETTE["line"]}" opacity="0.22"/>'
        )
        parts.append(_text(width / 2, 144, message, size=15, weight=700, fill=PALETTE["ink"], anchor="middle"))
        parts.append(_text(width / 2, 169, "Do not present absent city/platform friction rows as evidence.", size=12, fill=PALETTE["muted"], anchor="middle"))
        _write_svg(path, parts)
    else:
        rows = [{
            "label": "Chinese city/platform friction tests",
            "value": len(chinese_city),
            "color": PALETTE["score"],
            "annotation": status,
        }]
        _horizontal_bar_chart(
            path,
            "Chinese City/Platform Friction Status",
            "Current tracked output is header-only because comparison groups are unavailable",
            rows,
            "value",
            "color",
            "rows",
            "Do not present absent city/platform friction rows as evidence.",
            max_abs=max(1.0, float(len(chinese_city))),
        )
    questions.append({"figure": "Chinese city/platform friction status", "path": str(path), "question": "Can current Chinese city/platform friction tests be visualized?", "caveat": "Current files are header-only; no comparison finding."})
    return questions


def write_within_language_figure(df: pd.DataFrame, output_dir: Path, slug: str, title: str, subtitle: str) -> dict[str, str]:
    # Generate within-language driver effects: what predictors best explain sentiment within English/Japanese/Chinese reviews?
    # Shows predictor/outcome pairs with their effect sizes, organized by analysis type.
    # E.g., for English: "has_friction / sentiment_score" = score difference of -0.15 (friction lowers sentiment).

    work = df[df["status"] == "ok"].copy()

    # Organize effects into panels by analysis type.
    grouped_rows: dict[str, list[dict[str, object]]] = {
        "score": [],          # Sentiment score differences (true vs false)
        "event": [],          # Positive category risk differences (percentage points)
        "association": [],    # Spearman correlations with rating
        "multicategory": [],  # ANOVA epsilon-squared effects
    }

    for _, row in work.iterrows():
        analysis_type = str(row["analysis_type"])
        effect = float(row["effect_size"]) if pd.notna(row["effect_size"]) else 0.0
        p_value = row["p_value_bh_fdr"] if pd.notna(row.get("p_value_bh_fdr")) else row["p_value"]
        label = f"{row['predictor']} / {row['outcome']}"

        if analysis_type == "score_by_binary_predictor":
            # Score difference: how much does the predictor shift the mean sentiment score?
            grouped_rows["score"].append({
                "label": label,
                "value": effect,
                "color": PALETTE["score"],
                "annotation": f"score diff={_fmt_signed(effect, 3)}; {_fmt_p(p_value)}",
            })
        elif analysis_type == "category_event_by_binary_predictor":
            # Risk difference: by how many percentage points does the predictor change the rate of positive sentiment?
            risk_difference_pp = effect * 100
            grouped_rows["event"].append({
                "label": label,
                "value": risk_difference_pp,
                "color": PALETTE["event"],
                "annotation": f"risk diff={_fmt_signed(risk_difference_pp, 1)}pp; {_fmt_p(p_value)}",
            })
        elif analysis_type == "association":
            # Spearman correlation: continuous predictor association with sentiment score/rating.
            grouped_rows["association"].append({
                "label": label,
                "value": effect,
                "color": PALETTE["neutral"],
                "annotation": f"rho={_fmt_signed(effect, 3)}; {_fmt_p(p_value)}",
            })
        elif "multicategory" in analysis_type:
            # ANOVA epsilon-squared: effect size for multi-category predictors.
            grouped_rows["multicategory"].append({
                "label": label,
                "value": effect,
                "color": PALETTE["neutral"],
                "annotation": f"epsilon^2={effect:.3f}; {_fmt_p(p_value)}",
            })

    for rows in grouped_rows.values():
        rows.sort(key=lambda item: abs(float(item["value"])), reverse=True)

    path = output_dir / f"figure_within_{slug}_driver_effects.svg"
    _driver_effect_chart(
        path,
        title,
        subtitle,
        [
            {
                "title": "Score mean differences",
                "unit": "mean sentiment-score difference, true minus false, within one scoring tool",
                "rows": grouped_rows["score"],
                "tick_suffix": "",
                "min_limit": 0.1,
            },
            {
                "title": "Positive-event risk differences",
                "unit": "percentage points, true minus false",
                "rows": grouped_rows["event"],
                "tick_suffix": "pp",
                "min_limit": 1.0,
            },
            {
                "title": "Rating association",
                "unit": "Spearman rho",
                "rows": grouped_rows["association"],
                "tick_suffix": "",
                "min_limit": 0.1,
            },
            {
                "title": "Multicategory score effects",
                "unit": "epsilon-squared",
                "rows": grouped_rows["multicategory"],
                "tick_suffix": "",
                "min_limit": 0.1,
            },
        ],
        "Panels use separate axes: score rows are mean score differences; event rows are percentage-point risk differences; rho and epsilon-squared are separate diagnostics.",
    )
    return {"figure": title, "path": str(path), "question": "Which within-language/source predictors best explain sentiment differences?", "caveat": "Within one scoring tool/source only."}


def write_hypothesis_overview_figure(h1: pd.DataFrame, h2: pd.DataFrame, h3: pd.DataFrame, within_poi: pd.DataFrame, output_dir: Path) -> dict[str, str]:
    h1_primary = h1[(h1["analysis_type"] == "primary") & (h1["status"] == "ok")]
    h1_test = _required_row(h1_primary, h1_primary["test_name"] == "chi_square_sentiment_category", "H1 primary chi-square")
    h1_en_positive = _required_row(
        h1_primary,
        (h1_primary["category"] == "positive") & (h1_primary["language_group"] == "english"),
        "H1 English positive share",
    )
    h1_jp_positive = _required_row(
        h1_primary,
        (h1_primary["category"] == "positive") & (h1_primary["language_group"] == "japanese"),
        "H1 Japanese positive share",
    )

    h2_row = _required_row(h2, h2["test_name"] == "welch_t_review_rating", "H2 review-level Welch t")
    h3_enjoyment = _required_row(h3, h3["evidence_family"] == "enjoyment", "H3 enjoyment evidence")
    h3_positive = _required_row(h3, h3["evidence_family"] == "positive_sentiment", "H3 positive evidence")
    h3_recommendation = _required_row(h3, h3["evidence_family"] == "recommendation", "H3 recommendation evidence")
    h3_friction = _required_row(h3, h3["evidence_family"] == "friction", "H3 friction evidence")
    paired_rating = _required_row(within_poi, within_poi["test_name"] == "within_poi_paired_rating", "within-POI paired rating")
    paired_positive = _required_row(within_poi, within_poi["test_name"] == "within_poi_paired_positive_share", "within-POI paired positive share")
    paired_details = _parse_json(paired_rating["details_json"])
    alpha = 0.05
    paired_rating_p = float(paired_rating["p_value"])
    paired_positive_p = float(paired_positive["p_value"])
    paired_rating_significant = paired_rating_p < alpha
    paired_positive_significant = paired_positive_p < alpha
    if paired_rating_significant and paired_positive_significant:
        paired_status = "supported"
    elif paired_rating_significant or paired_positive_significant:
        paired_status = "mixed"
    else:
        paired_status = "failed"
    paired_positive_verdict = "holds" if paired_positive_significant else "does not hold"
    if paired_rating_significant:
        paired_rating_verdict = "significant"
    elif paired_rating_p < alpha * 2:
        paired_rating_verdict = "borderline/n.s."
    else:
        paired_rating_verdict = "n.s."
    paired_verdict = f"Positive-share {paired_positive_verdict}; rating {paired_rating_verdict}"
    if not paired_verdict.endswith("."):
        paired_verdict += "."

    significant_h3_ps = [
        float(h3_enjoyment["p_value_bh_fdr"]),
        float(h3_positive["p_value_bh_fdr"]),
        float(h3_recommendation["p_value_bh_fdr"]),
    ]
    h3_p_label = "p(FDR)<1e-8" if max(significant_h3_ps) < 1e-8 else f"p(FDR)<={_fmt_p_number(max(significant_h3_ps))}"
    rows = [
        {
            "label": "H1",
            "verdict": (
                "English reviews skew more positive "
                f"({float(h1_en_positive['category_share']):.0%} vs {float(h1_jp_positive['category_share']):.0%} positive)."
            ),
            "effect": f"Cramér's V={float(h1_test['effect_cramers_v']):.2f} (χ²={float(h1_test['statistic']):.1f})",
            "p": f"p(Holm)={_fmt_p_number(h1_test['p_value_holm'])}",
            "status": "supported",
        },
        {
            "label": "H2",
            "verdict": "Holds at review and POI level; within-POI rating borderline.",
            "effect": (
                f"ΔEN−JP={_fmt_signed(h2_row['effect_mean_difference'], 2)} stars "
                f"(95% CI {float(h2_row['ci_95_lower']):.2f}–{float(h2_row['ci_95_upper']):.2f})"
            ),
            "p": f"p={_fmt_p_number(h2_row['p_value'])}",
            "status": "supported",
        },
        {
            "label": "H3",
            "verdict": f"Friction prevalence does NOT differ ({float(h3_friction['risk_difference_pct']):+.1f}pp, n.s.).",
            "effect": (
                f"enjoyment {float(h3_enjoyment['risk_difference_pct']):+.0f}pp; "
                f"positive {float(h3_positive['risk_difference_pct']):+.0f}pp; "
                f"recommendation {float(h3_recommendation['risk_difference_pct']):+.0f}pp"
            ),
            "p": h3_p_label,
            "status": "supported",
        },
        {
            "label": "Robustness",
            "verdict": paired_verdict,
            "effect": (
                f"positive-share {_fmt_signed(paired_positive['effect'], 2)} ({_fmt_p(paired_positive['p_value'])}); "
                f"rating {_fmt_signed(paired_rating['effect'], 2)} ({_fmt_p(paired_rating['p_value'])})"
            ),
            "p": f"n={int(paired_details.get('n_pairs', 0))} POIs",
            "status": paired_status,
        },
    ]
    path = output_dir / "figure_hypothesis_overview.svg"
    _results_panel(
        path,
        "Hypothesis Results at a Glance",
        "Fukui Google reviews; effect sizes with multiplicity-adjusted p-values",
        rows,
        "H1 Holm-adjusted; H3 Benjamini–Hochberg FDR. Rows nested in POIs; the within-POI paired row is the venue-clustering robustness check.",
    )
    return {
        "figure": "Hypothesis results at a glance",
        "path": str(path),
        "question": "Which main hypotheses are supported, and by which aggregate effect sizes?",
        "caveat": "Rows remain nested in POIs; adjusted p-values and venue-paired robustness checks answer different threats.",
    }


def write_h2_rating_gap_robustness_ladder(h2: pd.DataFrame, within_poi: pd.DataFrame, output_dir: Path) -> dict[str, str]:
    review = _required_row(h2, h2["test_name"] == "welch_t_review_rating", "H2 review-level Welch t")
    poi = _required_row(h2, h2["test_name"] == "poi_level_welch_t_mean_review_rating", "H2 POI-level Welch t")
    paired = _required_row(within_poi, within_poi["test_name"] == "within_poi_paired_rating", "within-POI paired rating")
    review_details = _parse_json(review["details_json"])
    poi_details = _parse_json(poi["details_json"])
    paired_details = _parse_json(paired["details_json"])
    rows = [
        {
            "label": f"Review-level Welch t (n={_fmt_n(review_details.get('english_n', review['english_n']))} vs {_fmt_n(review_details.get('japanese_n', review['japanese_n']))})",
            "point": float(review["effect_mean_difference"]),
            "ci_low": float(review["ci_95_lower"]),
            "ci_high": float(review["ci_95_upper"]),
            "p_chip": _fmt_p(review["p_value"]),
            "value_label": f"{_fmt_signed(review['effect_mean_difference'], 2)} [{float(review['ci_95_lower']):.2f}, {float(review['ci_95_upper']):.2f}]",
            "color": PALETTE["score"],
        },
        {
            "label": f"POI-level Welch t ({_fmt_n(poi_details.get('english_n'))} vs {_fmt_n(poi_details.get('japanese_n'))} POIs)",
            "point": float(poi["effect_mean_difference"]),
            "ci_low": float(poi["ci_95_lower"]),
            "ci_high": float(poi["ci_95_upper"]),
            "p_chip": _fmt_p(poi["p_value"]),
            "value_label": f"{_fmt_signed(poi['effect_mean_difference'], 2)} [{float(poi['ci_95_lower']):.2f}, {float(poi['ci_95_upper']):.2f}]",
            "color": PALETTE["event"],
        },
        {
            "label": f"Within-POI paired Wilcoxon ({_fmt_n(paired_details.get('n_pairs'))} shared POIs)",
            "point": float(paired["effect"]),
            "ci_low": None,
            "ci_high": None,
            "p_chip": _fmt_p(paired["p_value"]),
            "value_label": _fmt_signed(paired["effect"], 3),
            "color": PALETTE["positive"],
        },
    ]
    path = output_dir / "figure_h2_rating_gap_robustness_ladder.svg"
    _forest_chart(
        path,
        "English Rating Advantage Holds Across Units of Analysis",
        "EN−JP mean Google star difference, three nested unit definitions",
        rows,
        "Same estimand (English minus Japanese) under progressively stricter venue control; common 1–5 star scale, not text-sentiment equivalence.",
        x_min=-0.02,
        x_max=0.55,
        ticks=[0.0, 0.2, 0.4, 0.55],
    )
    return {
        "figure": "H2 rating gap robustness ladder",
        "path": str(path),
        "question": "Does the English-minus-Japanese Google rating gap persist as the unit shifts from rows to POIs to shared POIs?",
        "caveat": "Common Google stars are companion outcome evidence, not cross-language text-sentiment equivalence.",
    }


def write_within_poi_paired_shift_figure(within_poi: pd.DataFrame, output_dir: Path) -> dict[str, str]:
    rating = _required_row(within_poi, within_poi["test_name"] == "within_poi_paired_rating", "within-POI paired rating")
    positive = _required_row(within_poi, within_poi["test_name"] == "within_poi_paired_positive_share", "within-POI paired positive share")
    details = _parse_json(rating["details_json"])
    rows = [
        {
            "label": "Mean star rating",
            "point": float(rating["effect"]),
            "ci_low": None,
            "ci_high": None,
            "p_chip": _fmt_p(rating["p_value"]),
            "value_label": _fmt_signed(rating["effect"], 3),
            "color": PALETTE["score"],
        },
        {
            "label": "Positive sentiment share",
            "point": float(positive["effect"]),
            "ci_low": None,
            "ci_high": None,
            "p_chip": f"{_fmt_p(positive['p_value'])} *",
            "value_label": _fmt_signed(positive["effect"], 3),
            "color": PALETTE["positive"],
        },
    ]
    caption = (
        f"{_fmt_n(details.get('n_pairs'))} paired POIs from {_fmt_n(details.get('n_shared_poi_candidates'))} shared candidates; "
        f"{_fmt_n(details.get('n_english_reviews_paired'))} English + {_fmt_n(details.get('n_japanese_reviews_paired'))} Japanese reviews paired."
    )
    path = output_dir / "figure_within_poi_paired_shift.svg"
    _forest_chart(
        path,
        "Within-POI Paired Differences (English minus Japanese)",
        f"Holding venue constant across {_fmt_n(details.get('n_pairs'))} shared Fukui POIs (≥5 reviews per language)",
        rows,
        "Pairing removes venue/POI composition as a confound; Wilcoxon signed-rank on POI-pair differences.",
        x_min=-0.03,
        x_max=0.34,
        ticks=[0.0, 0.1, 0.2, 0.3],
        caption=caption,
        positive_annotation="favors English →",
    )
    return {
        "figure": "Within-POI paired differences",
        "path": str(path),
        "question": "When the same Fukui POIs are compared directly, do English-language reviews still score higher?",
        "caveat": "The paired unit is POI, not review row; the rating shift is marginal while positive-share shift is significant.",
    }


def _write_questions(path: Path, questions: list[dict[str, str]]) -> None:
    lines = [
        "# Statistical Test Figure Questions",
        "",
        "All figures are aggregate-only. They omit row-level post/review text, authors, URLs, IDs, screenshots, and raw captures.",
        "",
    ]
    for item in questions:
        lines.extend([
            f"## {item['figure']}",
            "",
            f"- Path: `{item['path']}`",
            f"- Question answered: {item['question']}",
            f"- Caveat: {item['caveat']}",
            "",
        ])
    path.write_text("\n".join(lines), encoding="utf-8")


def build_statistical_test_figures(
    input_dir: Path = DEFAULT_INPUT_DIR,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    command: str | None = None,
) -> dict:
    # Main figure-building pipeline:
    # 1. Load statistical test results from CSVs
    # 2. Generate visualizations for each hypothesis (H1, H2, H3) and sensitivity analyses
    # 3. Create cross-language comparison figures
    # 4. Generate within-language driver effect charts
    # 5. Write manifest and index markdown

    # Define all input file paths.
    paths = {
        "h1": input_dir / "hypothesis_tests" / "h1_sentiment_category_jp_en.csv",
        "h2": input_dir / "hypothesis_tests" / "h2_review_rating_jp_en.csv",
        "h3": input_dir / "hypothesis_tests" / "h3_reviewed_evidence_jp_en.csv",
        "within_poi": input_dir / "hypothesis_tests" / "within_poi_paired_jp_en.csv",
        "cross_tests": input_dir / "cross_language_trends" / "cross_language_statistical_tests.csv",
        "date_scrub": input_dir / "cross_language_trends" / "date_scrub_requirements.csv",
        "chinese_city": input_dir / "chinese_social_media_analysis" / "chinese_city_platform_friction_tests.csv",
        "en": input_dir / "within_language_sentiment" / "en_within_language_sentiment_drivers.csv",
        "jp": input_dir / "within_language_sentiment" / "jp_within_language_sentiment_drivers.csv",
        "cn": input_dir / "within_language_sentiment" / "cn_within_source_sentiment_drivers.csv",
    }

    # Load all test result CSVs (includes schema validation).
    h1 = _read_csv(paths["h1"], {"analysis_type", "test_name", "status", "category", "language_group", "observed_count", "category_share", "statistic", "p_value_holm", "effect_cramers_v", "neutral_band_note", "category_source_column"}, "hypothesis-tests")
    h2 = _read_csv(paths["h2"], {"analysis_type", "test_name", "status", "language_group", "english_n", "japanese_n", "n_rating_present", "mean_review_rating", "rating_distribution_json", "statistic", "p_value", "effect_mean_difference", "ci_95_lower", "ci_95_upper", "details_json"}, "hypothesis-tests")
    h3 = _read_csv(paths["h3"], {"analysis_type", "evidence_family", "status", "p_value_bh_fdr", "risk_difference_pct", "english_present_pct", "japanese_present_pct", "text_length_summary_json", "details_json"}, "hypothesis-tests")
    within_poi = _read_csv(paths["within_poi"], {"test_name", "status", "effect", "p_value", "details_json"}, "hypothesis-tests")
    cross_tests = _read_csv(paths["cross_tests"], {"test_name", "comparison", "status", "p_value", "effect", "details_json"}, "cross-language-trends")
    date_scrub = _read_csv(paths["date_scrub"], {"source_kind", "date_precision", "count", "usable_for_monthly_trends"}, "cross-language-trends")
    chinese_city = _read_csv(paths["chinese_city"], {"comparison_type", "group_a", "group_b", "friction_code"}, "chinese-social")
    en = _read_csv(paths["en"], {"status", "analysis_type", "predictor", "outcome", "effect_size", "p_value", "p_value_bh_fdr"}, "within-language-sentiment")
    jp = _read_csv(paths["jp"], {"status", "analysis_type", "predictor", "outcome", "effect_size", "p_value", "p_value_bh_fdr"}, "within-language-sentiment")
    cn = _read_csv(paths["cn"], {"status", "analysis_type", "predictor", "outcome", "effect_size", "p_value", "p_value_bh_fdr"}, "within-language-sentiment")

    output_dir.mkdir(parents=True, exist_ok=True)

    # Generate all figures and collect their metadata (path, question, caveat).
    questions: list[dict[str, str]] = []
    questions.extend(write_h1_figures(h1, output_dir))
    questions.extend(write_h2_figures(h2, output_dir))
    questions.extend(write_h3_figures(h3, output_dir))
    questions.append(write_hypothesis_overview_figure(h1, h2, h3, within_poi, output_dir))
    questions.append(write_h2_rating_gap_robustness_ladder(h2, within_poi, output_dir))
    questions.append(write_within_poi_paired_shift_figure(within_poi, output_dir))
    questions.extend(write_cross_source_figures(cross_tests, date_scrub, chinese_city, output_dir))
    questions.append(write_within_language_figure(en, output_dir, "english", "Within-English Sentiment Drivers", "Enjoyment/positive evidence has largest VADER-score separation"))
    questions.append(write_within_language_figure(jp, output_dir, "japanese", "Within-Japanese Sentiment Drivers", "Enjoyment/positive evidence drives oseti sentiment most clearly"))
    questions.append(write_within_language_figure(cn, output_dir, "chinese", "Within-Chinese Social Sentiment Drivers", "Topic tags separate SnowNLP sentiment more than food/friction tags"))

    # Write index files (markdown and CSV) describing all figures.
    question_records = [{**item, "path": repo_relative(item["path"])} for item in questions]
    questions_path = output_dir / "statistical_test_figure_questions.md"
    manifest_path = output_dir / "statistical_test_figure_manifest.json"
    index_path = output_dir / "statistical_test_figure_index.csv"
    _write_questions(questions_path, question_records)
    pd.DataFrame(question_records).to_csv(index_path, index=False)

    figure_paths = [Path(item["path"]) for item in questions]
    report = research_manifest(
        kind="statistical_test_figure_pack",
        command=command or " ".join(sys.argv),
        inputs=[file_record(path, role, required=True) for role, path in paths.items()],
        outputs=[
            file_record(index_path, "statistical_test_figure_index", required=True),
            file_record(questions_path, "statistical_test_figure_questions", required=True),
            *[file_record(path, f"statistical_test_figure_{path.stem}", required=True) for path in figure_paths],
        ],
        filters={"prefecture": "Fukui", "output_surface": "aggregate-only SVG"},
        metrics={"figure_count": len(figure_paths)},
        caveats=[
            "Language/source groups are not nationality groups.",
            "Raw VADER, oseti, and SnowNLP scores are not common-scale evidence.",
            "Cross-source tests are descriptive because platforms, units, and collection windows differ.",
            "Google review rows remain nested in POIs; p-values are descriptive without a clustered/covariate model.",
        ],
    )
    write_json(manifest_path, report)
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    build_statistical_test_figures(
        input_dir=args.input_dir,
        output_dir=args.output_dir,
        command=" ".join(sys.argv),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
