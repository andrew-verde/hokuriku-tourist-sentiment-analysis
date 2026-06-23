#!/usr/bin/env python3
"""Build aggregate-only SVG figures for the statistical test index."""

from __future__ import annotations

import argparse
import html
import json
import math
import sys
from pathlib import Path
from typing import Iterable

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.provenance import (
    assert_no_forbidden_columns,
    file_record,
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
    _input(path, make_target)
    df = pd.read_csv(path)
    assert_no_forbidden_columns(df.columns, forbidden=FORBIDDEN_AGGREGATE_COLUMNS, context=str(path))
    missing = sorted(required - set(df.columns))
    if missing:
        raise MissingColumnsError(f"Required columns missing from {path}: {', '.join(missing)}")
    return df


def _parse_json(value: object) -> dict:
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
    if pd.isna(value):
        return "p=n/a"
    number = float(value)
    if number < 0.001:
        return f"p={number:.1e}"
    return f"p={number:.3f}"


def _fmt_effect(value: object, label: str = "effect") -> str:
    if pd.isna(value):
        return f"{label}=n/a"
    return f"{label}={float(value):.3f}"


def _as_pct(value: object) -> float:
    number = float(value)
    return number * 100 if abs(number) <= 1 else number


def _safe_label(value: object, max_len: int = 42) -> str:
    text = str(value).replace("_", " ")
    return text if len(text) <= max_len else text[: max_len - 1] + "..."


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


def _stacked_pct_chart(
    path: Path,
    title: str,
    subtitle: str,
    rows: list[dict[str, object]],
    categories: list[tuple[str, str]],
    note: str,
) -> None:
    width = 1120
    top = 104
    row_height = 54
    left = 295
    right = 118
    height = top + 92 + max(1, len(rows)) * row_height
    chart_width = width - left - right
    parts = _svg_header(width, height, title, subtitle)
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
            parts.append(_text(left + chart_width + 10, y + 26, f"n={_fmt_n(row['n'])}", size=12, fill=PALETTE["muted"]))
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
    if zero_center:
        axis_x = left + chart_width / 2
        parts.append(f'<line x1="{axis_x:.2f}" x2="{axis_x:.2f}" y1="{top - 8}" y2="{height - 62}" stroke="{PALETTE["line"]}" stroke-width="1"/>')
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
        parts.append(_text(text_x, y + 23, label, size=12, anchor=anchor))
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
            parts.append(_text(left + bar_width + 8, bar_y + 12, f"{value:.1f}%", size=11))
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
    primary = h1[(h1["analysis_type"] == "primary") & (h1["status"] == "ok")].copy()
    rows = []
    for language, chunk in primary.groupby("language_group", sort=False):
        row = {
            "label": GROUP_LABELS.get(str(language), str(language)),
            "n": int(chunk["observed_count"].sum()),
        }
        for _, item in chunk.iterrows():
            row[str(item["category"])] = float(item["category_share"]) * 100
        rows.append(row)
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
    summaries = h2[h2["analysis_type"] == "group_summary"].copy()
    rating_rows = []
    for _, row in summaries.iterrows():
        dist = _parse_json(row["rating_distribution_json"])
        n = sum(int(value) for value in dist.values())
        chart_row = {"label": GROUP_LABELS.get(str(row["language_group"]), row["language_group"]), "n": n}
        for rating in range(1, 6):
            chart_row[f"rating_{rating}"] = int(dist.get(str(rating), 0)) / n * 100 if n else 0.0
        rating_rows.append(chart_row)
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
    evidence = h3[h3["analysis_type"] == "evidence_family_test"].copy()
    rows = []
    for _, row in evidence.sort_values("risk_difference_pct", ascending=False).iterrows():
        rows.append({
            "label": row["evidence_family"],
            "english": _as_pct(row["english_present_pct"]),
            "japanese": _as_pct(row["japanese_present_pct"]),
            "annotation": f"diff={float(row['risk_difference_pct']):.1f} pp; {_fmt_p(row['p_value_bh_fdr'])}",
        })
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
    rows = [{
        "label": "Chinese city/platform friction tests",
        "value": len(chinese_city) if not chinese_city.empty else 1,
        "color": PALETTE["neutral"] if chinese_city.empty else PALETTE["score"],
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
    work = df[df["status"] == "ok"].copy()
    rows = []
    for _, row in work.iterrows():
        color = PALETTE["score"] if row["analysis_type"] == "score_by_binary_predictor" else PALETTE["event"]
        if "association" in str(row["analysis_type"]) or "multicategory" in str(row["analysis_type"]):
            color = PALETTE["neutral"]
        rows.append({
            "label": f"{row['predictor']} / {row['outcome']}",
            "value": float(row["effect_size"]) if pd.notna(row["effect_size"]) else 0.0,
            "color": color,
            "annotation": f"effect={float(row['effect_size']):.3f}; {_fmt_p(row['p_value_bh_fdr'] if pd.notna(row.get('p_value_bh_fdr')) else row['p_value'])}",
        })
    rows = sorted(rows, key=lambda item: abs(float(item["value"])), reverse=True)[:12]
    limit = max([abs(float(row["value"])) for row in rows] + [0.1])
    path = output_dir / f"figure_within_{slug}_driver_effects.svg"
    _horizontal_bar_chart(
        path,
        title,
        subtitle,
        rows,
        "value",
        "color",
        "effect",
        "Score effects and event risk differences are within-language/source only.",
        zero_center=True,
        max_abs=max(0.1, limit),
    )
    return {"figure": title, "path": str(path), "question": "Which within-language/source predictors best explain sentiment differences?", "caveat": "Within one scoring tool/source only."}


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
    paths = {
        "h1": input_dir / "hypothesis_tests" / "h1_sentiment_category_jp_en.csv",
        "h2": input_dir / "hypothesis_tests" / "h2_review_rating_jp_en.csv",
        "h3": input_dir / "hypothesis_tests" / "h3_reviewed_evidence_jp_en.csv",
        "cross_tests": input_dir / "cross_language_trends" / "cross_language_statistical_tests.csv",
        "date_scrub": input_dir / "cross_language_trends" / "date_scrub_requirements.csv",
        "chinese_city": input_dir / "chinese_social_media_analysis" / "chinese_city_platform_friction_tests.csv",
        "en": input_dir / "within_language_sentiment" / "en_within_language_sentiment_drivers.csv",
        "jp": input_dir / "within_language_sentiment" / "jp_within_language_sentiment_drivers.csv",
        "cn": input_dir / "within_language_sentiment" / "cn_within_source_sentiment_drivers.csv",
    }
    h1 = _read_csv(paths["h1"], {"analysis_type", "status", "category", "language_group", "observed_count", "category_share", "p_value_holm", "effect_cramers_v", "neutral_band_note", "category_source_column"}, "hypothesis-tests")
    h2 = _read_csv(paths["h2"], {"analysis_type", "test_name", "status", "language_group", "n_rating_present", "mean_review_rating", "rating_distribution_json", "p_value", "effect_mean_difference"}, "hypothesis-tests")
    h3 = _read_csv(paths["h3"], {"analysis_type", "evidence_family", "status", "p_value_bh_fdr", "risk_difference_pct", "english_present_pct", "japanese_present_pct", "text_length_summary_json", "details_json"}, "hypothesis-tests")
    cross_tests = _read_csv(paths["cross_tests"], {"test_name", "comparison", "status", "p_value", "effect", "details_json"}, "cross-language-trends")
    date_scrub = _read_csv(paths["date_scrub"], {"source_kind", "date_precision", "count", "usable_for_monthly_trends"}, "cross-language-trends")
    chinese_city = _read_csv(paths["chinese_city"], {"comparison_type", "group_a", "group_b", "friction_code"}, "chinese-social")
    en = _read_csv(paths["en"], {"status", "analysis_type", "predictor", "outcome", "effect_size", "p_value", "p_value_bh_fdr"}, "within-language-sentiment")
    jp = _read_csv(paths["jp"], {"status", "analysis_type", "predictor", "outcome", "effect_size", "p_value", "p_value_bh_fdr"}, "within-language-sentiment")
    cn = _read_csv(paths["cn"], {"status", "analysis_type", "predictor", "outcome", "effect_size", "p_value", "p_value_bh_fdr"}, "within-language-sentiment")

    output_dir.mkdir(parents=True, exist_ok=True)
    questions: list[dict[str, str]] = []
    questions.extend(write_h1_figures(h1, output_dir))
    questions.extend(write_h2_figures(h2, output_dir))
    questions.extend(write_h3_figures(h3, output_dir))
    questions.extend(write_cross_source_figures(cross_tests, date_scrub, chinese_city, output_dir))
    questions.append(write_within_language_figure(en, output_dir, "english", "Within-English Sentiment Drivers", "Enjoyment/positive evidence has largest VADER-score separation"))
    questions.append(write_within_language_figure(jp, output_dir, "japanese", "Within-Japanese Sentiment Drivers", "Enjoyment/positive evidence drives oseti sentiment most clearly"))
    questions.append(write_within_language_figure(cn, output_dir, "chinese", "Within-Chinese Social Sentiment Drivers", "Topic tags separate SnowNLP sentiment more than food/friction tags"))

    questions_path = output_dir / "statistical_test_figure_questions.md"
    manifest_path = output_dir / "statistical_test_figure_manifest.json"
    index_path = output_dir / "statistical_test_figure_index.csv"
    _write_questions(questions_path, questions)
    pd.DataFrame(questions).to_csv(index_path, index=False)

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
