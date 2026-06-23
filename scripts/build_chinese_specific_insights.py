#!/usr/bin/env python3
"""
Build aggregate Chinese-language social-media insight tables and figures.

The script consumes the outputs from `make chinese-social` and writes only
aggregate CSV/SVG artifacts. It intentionally avoids copying row-level text,
authors, URLs, or source record IDs into the insight folder.
"""

from __future__ import annotations

import argparse
import html
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.provenance import assert_no_forbidden_columns, file_record, research_manifest, write_json
from src.utils.logger import setup_logger


logger = setup_logger(__name__)

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INPUT_DIR = ROOT / "output" / "chinese_social_media_analysis"
DEFAULT_OUTPUT_DIR = ROOT / "output" / "chinese_specific_insights"

SENTIMENT_MATCH_COLUMNS = {
    "positive_sentiment": "reviewed_positive_terms_matched",
    "negative_sentiment": "reviewed_negative_terms_matched",
    "recommendation_intent": "reviewed_recommendation_terms_matched",
}

REQUIRED_TAGGED_COLUMNS = {
    "city",
    "source_platform",
    "sentiment_category",
    "sentiment_norm",
    "theme",
}

TOPIC_AGGREGATE_INPUT = "chinese_topic_by_city_platform.csv"

FIGURE_PALETTE = [
    "#2f6f73",
    "#bc6c25",
    "#5b6c94",
    "#8a5a44",
    "#4f7d3a",
    "#9d4edd",
    "#386641",
    "#9a031e",
]

SENTIMENT_GROUP_LABELS = {
    "positive_sentiment": "Positive",
    "negative_sentiment": "Negative",
    "recommendation_intent": "Recommendation",
}
MIN_THEME_SLICE_ROWS = 10


class ChineseInsightError(RuntimeError):
    pass


def _require_input(path: Path, make_target: str = "chinese-social") -> None:
    if not path.exists():
        raise ChineseInsightError(
            f"Required input not found: {path}\n"
            f"Generate it first with `make {make_target}`. This script has no demo mode."
        )


def _read_csv(path: Path, make_target: str = "chinese-social") -> pd.DataFrame:
    _require_input(path, make_target)
    return pd.read_csv(path)


def _coerce_bool(series: pd.Series) -> pd.Series:
    if series.dtype == bool:
        return series.fillna(False)
    return series.fillna(False).astype(str).str.lower().isin({"true", "1", "yes"})


def _split_terms(value: object) -> list[str]:
    if pd.isna(value):
        return []
    return [term.strip() for term in str(value).split("|") if term.strip()]


def _pct(numerator: float, denominator: float) -> float:
    if denominator == 0:
        return 0.0
    return round((numerator / denominator) * 100, 3)


def _fmt_n(value: int | float) -> str:
    return f"{int(value):,}"


def load_tagged_rows(path: Path) -> pd.DataFrame:
    tagged = _read_csv(path)
    missing = REQUIRED_TAGGED_COLUMNS - set(tagged.columns)
    if missing:
        raise ChineseInsightError(f"Tagged Chinese rows missing required columns: {sorted(missing)}")
    return tagged


def load_codebook_summary(path: Path) -> pd.DataFrame:
    summary = _read_csv(path)
    required = {"code_family", "code", "label", "keyword_count"}
    missing = required - set(summary.columns)
    if missing:
        raise ChineseInsightError(f"Codebook summary missing required columns: {sorted(missing)}")
    return summary


def build_keyword_inventory(codebook_summary: pd.DataFrame) -> pd.DataFrame:
    rows = codebook_summary[["code_family", "code", "label", "keyword_count"]].copy()
    rows = rows.sort_values(["code_family", "keyword_count", "code"], ascending=[True, False, True])
    return rows.reset_index(drop=True)


def build_category_occurrence(input_dir: Path) -> pd.DataFrame:
    filename = TOPIC_AGGREGATE_INPUT
    df = _read_csv(input_dir / filename)
    required = {"city", "source_platform", "code", "label", "count", "denominator_posts", "pct_posts"}
    missing = required - set(df.columns)
    if missing:
        raise ChineseInsightError(f"{filename} missing required columns: {sorted(missing)}")
    combined = df[["city", "source_platform", "code", "label", "count", "denominator_posts", "pct_posts"]].copy()
    combined["evidence_family"] = "topic"
    grouped = (
        combined.groupby(["evidence_family", "code", "label"], dropna=False)
        .agg(count=("count", "sum"), denominator_posts=("denominator_posts", "sum"))
        .reset_index()
    )
    grouped["pct_posts"] = grouped.apply(
        lambda row: _pct(float(row["count"]), float(row["denominator_posts"])), axis=1
    )
    return grouped.sort_values(["count", "evidence_family", "code"], ascending=[False, True, True]).reset_index(drop=True)


def build_topic_sentiment_chart_rows(topic_by_sentiment: pd.DataFrame) -> list[dict[str, object]]:
    if topic_by_sentiment.empty:
        return []
    required = {"sentiment_category", "code", "label", "count"}
    missing = required - set(topic_by_sentiment.columns)
    if missing:
        raise ChineseInsightError(f"Topic sentiment data missing required columns: {sorted(missing)}")
    chart = topic_by_sentiment[topic_by_sentiment["sentiment_category"].isin(["positive", "negative"])].copy()
    if chart.empty:
        return []
    pivot = (
        chart.pivot_table(index=["code", "label"], columns="sentiment_category", values="count", aggfunc="sum", fill_value=0)
        .reset_index()
    )
    for column in ["positive", "negative"]:
        if column not in pivot.columns:
            pivot[column] = 0
    pivot["total_positive_negative"] = pivot["positive"] + pivot["negative"]
    pivot = pivot.sort_values(["total_positive_negative", "positive", "label"], ascending=[False, False, True])
    return pivot.to_dict("records")


def build_sentiment_keyword_chart_rows(sentiment_keywords: pd.DataFrame, top_n_per_group: int = 6) -> list[dict[str, object]]:
    if sentiment_keywords.empty:
        return []
    chart = sentiment_keywords[sentiment_keywords["source_platform"] == "all"].copy()
    if chart.empty:
        return []
    chart["sentiment_group_label"] = chart["sentiment_group"].map(SENTIMENT_GROUP_LABELS).fillna(
        chart["sentiment_group"]
    )
    chart["chart_label"] = chart["sentiment_group_label"].astype(str) + ": " + chart["keyword"].astype(str)
    group_order = {
        "positive_sentiment": 0,
        "recommendation_intent": 1,
        "negative_sentiment": 2,
    }
    chart["group_order"] = chart["sentiment_group"].map(group_order).fillna(99)
    top_rows = (
        chart.sort_values(["sentiment_group", "count", "keyword"], ascending=[True, False, True])
        .groupby("sentiment_group", group_keys=False)
        .head(top_n_per_group)
    )
    top_rows = top_rows.sort_values(["group_order", "count", "keyword"], ascending=[True, False, True])
    return top_rows.to_dict("records")


def build_sentiment_keyword_counts(tagged: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for group, column in SENTIMENT_MATCH_COLUMNS.items():
        if column not in tagged.columns:
            continue
        for _, row in tagged[["source_platform", column]].iterrows():
            for keyword in _split_terms(row[column]):
                rows.append(
                    {
                        "sentiment_group": group,
                        "source_platform": row["source_platform"],
                        "keyword": keyword,
                        "count": 1,
                    }
                )
    if not rows:
        return pd.DataFrame(columns=["sentiment_group", "source_platform", "keyword", "count", "pct_all_rows"])

    counts = pd.DataFrame(rows)
    grouped = counts.groupby(["sentiment_group", "source_platform", "keyword"], dropna=False)["count"].sum().reset_index()
    all_platform = counts.groupby(["sentiment_group", "keyword"], dropna=False)["count"].sum().reset_index()
    all_platform["source_platform"] = "all"
    grouped = pd.concat([grouped, all_platform], ignore_index=True)
    grouped["pct_all_rows"] = grouped["count"].apply(lambda value: _pct(float(value), float(len(tagged))))
    return grouped.sort_values(["count", "sentiment_group", "keyword"], ascending=[False, True, True]).reset_index(drop=True)


def build_keywords_by_snownlp_category(tagged: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for group, column in SENTIMENT_MATCH_COLUMNS.items():
        if column not in tagged.columns:
            continue
        for _, row in tagged[["sentiment_category", column]].iterrows():
            for keyword in _split_terms(row[column]):
                rows.append(
                    {
                        "snownlp_sentiment_category": row["sentiment_category"],
                        "reviewed_sentiment_group": group,
                        "keyword": keyword,
                        "count": 1,
                    }
                )
    if not rows:
        return pd.DataFrame(
            columns=["snownlp_sentiment_category", "reviewed_sentiment_group", "keyword", "count"]
        )
    counts = pd.DataFrame(rows)
    return (
        counts.groupby(["snownlp_sentiment_category", "reviewed_sentiment_group", "keyword"], dropna=False)["count"]
        .sum()
        .reset_index()
        .sort_values(["snownlp_sentiment_category", "count", "keyword"], ascending=[True, False, True])
        .reset_index(drop=True)
    )


def build_sentiment_category_by_platform(tagged: pd.DataFrame) -> pd.DataFrame:
    counts = (
        tagged.groupby(["source_platform", "sentiment_category"], dropna=False)
        .size()
        .reset_index(name="count")
    )
    totals = counts.groupby("source_platform")["count"].transform("sum")
    counts["pct_platform_rows"] = counts.apply(lambda row: _pct(float(row["count"]), float(totals.loc[row.name])), axis=1)
    return counts.sort_values(["source_platform", "sentiment_category"]).reset_index(drop=True)


def build_theme_sentiment_summary(tagged: pd.DataFrame) -> pd.DataFrame:
    def _mean_or_na(values: pd.Series) -> float | pd.NA:
        if len(values) < MIN_THEME_SLICE_ROWS:
            return pd.NA
        return round(float(values.mean()), 6)

    def _count_positive(values: pd.Series) -> int:
        return int((values == "positive").sum())

    def _count_negative(values: pd.Series) -> int:
        return int((values == "negative").sum())

    summary = (
        tagged.groupby(["theme", "source_platform"], dropna=False)
        .agg(
            rows=("theme", "size"),
            sentiment_norm_mean=("sentiment_norm", _mean_or_na),
            positive_rows=("sentiment_category", _count_positive),
            negative_rows=("sentiment_category", _count_negative),
        )
        .reset_index()
    )
    summary["theme_slice_status"] = summary["rows"].map(
        lambda value: "ok" if int(value) >= MIN_THEME_SLICE_ROWS else "suppressed_small_n"
    )
    summary["positive_pct"] = summary.apply(
        lambda row: pd.NA if row["theme_slice_status"] == "suppressed_small_n" else _pct(float(row["positive_rows"]), float(row["rows"])),
        axis=1,
    )
    summary["negative_pct"] = summary.apply(
        lambda row: pd.NA if row["theme_slice_status"] == "suppressed_small_n" else _pct(float(row["negative_rows"]), float(row["rows"])),
        axis=1,
    )
    all_theme = (
        tagged.groupby(["theme"], dropna=False)
        .agg(
            rows=("theme", "size"),
            sentiment_norm_mean=("sentiment_norm", _mean_or_na),
            positive_rows=("sentiment_category", _count_positive),
            negative_rows=("sentiment_category", _count_negative),
        )
        .reset_index()
    )
    all_theme["source_platform"] = "all"
    all_theme["theme_slice_status"] = all_theme["rows"].map(
        lambda value: "ok" if int(value) >= MIN_THEME_SLICE_ROWS else "suppressed_small_n"
    )
    all_theme["positive_pct"] = all_theme.apply(
        lambda row: pd.NA if row["theme_slice_status"] == "suppressed_small_n" else _pct(float(row["positive_rows"]), float(row["rows"])),
        axis=1,
    )
    all_theme["negative_pct"] = all_theme.apply(
        lambda row: pd.NA if row["theme_slice_status"] == "suppressed_small_n" else _pct(float(row["negative_rows"]), float(row["rows"])),
        axis=1,
    )
    combined = pd.concat([summary, all_theme], ignore_index=True)
    return combined.sort_values(["rows", "theme"], ascending=[False, True]).reset_index(drop=True)


def build_code_by_sentiment_category(
    tagged: pd.DataFrame,
    codebook_summary: pd.DataFrame,
    code_family: str,
) -> pd.DataFrame:
    codes = codebook_summary.loc[codebook_summary["code_family"] == code_family, ["code", "label"]]
    rows: list[dict[str, object]] = []
    for sentiment_category, group in tagged.groupby("sentiment_category", dropna=False):
        denominator = len(group)
        for _, code_row in codes.iterrows():
            code = str(code_row["code"])
            if code not in group.columns:
                continue
            count = int(_coerce_bool(group[code]).sum())
            if count == 0:
                continue
            rows.append(
                {
                    "sentiment_category": sentiment_category,
                    "code_family": code_family,
                    "code": code,
                    "label": code_row["label"],
                    "count": count,
                    "denominator_rows": denominator,
                    "pct_sentiment_category_rows": _pct(count, denominator),
                }
            )
    columns = [
        "sentiment_category",
        "code_family",
        "code",
        "label",
        "count",
        "denominator_rows",
        "pct_sentiment_category_rows",
    ]
    return pd.DataFrame(rows, columns=columns).sort_values(["sentiment_category", "count"], ascending=[True, False])


def _write_svg_bar_chart(
    rows: list[dict[str, object]],
    path: Path,
    title: str,
    subtitle: str,
    label_key: str,
    value_key: str,
    color_key: str | None = None,
    max_rows: int = 14,
) -> None:
    chart_rows = rows[:max_rows]
    width = 1000
    row_height = 34
    top = 96
    left = 300
    right = 70
    bottom = 52
    height = top + bottom + max(1, len(chart_rows)) * row_height
    chart_width = width - left - right
    max_value = max([float(row[value_key]) for row in chart_rows] or [1.0])
    max_value = max(max_value, 1.0)

    color_values: dict[object, str] = {}
    if color_key:
        for row in chart_rows:
            value = row[color_key]
            if value not in color_values:
                color_values[value] = FIGURE_PALETTE[len(color_values) % len(FIGURE_PALETTE)]

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#fbfaf7"/>',
        f'<text x="32" y="38" font-family="Arial, sans-serif" font-size="24" font-weight="700" fill="#1f2933">{html.escape(title)}</text>',
        f'<text x="32" y="66" font-family="Arial, sans-serif" font-size="14" fill="#52616b">{html.escape(subtitle)}</text>',
    ]
    for index, row in enumerate(chart_rows):
        y = top + index * row_height
        value = float(row[value_key])
        bar_width = (value / max_value) * chart_width
        color = color_values.get(row[color_key], FIGURE_PALETTE[index % len(FIGURE_PALETTE)]) if color_key else FIGURE_PALETTE[index % len(FIGURE_PALETTE)]
        label = str(row[label_key])
        value_label = f"{value:,.0f}" if value.is_integer() else f"{value:,.3f}"
        parts.extend(
            [
                f'<text x="{left - 14}" y="{y + 22}" text-anchor="end" font-family="Arial, sans-serif" font-size="13" fill="#1f2933">{html.escape(label[:42])}</text>',
                f'<rect x="{left}" y="{y + 7}" width="{bar_width:.2f}" height="18" rx="3" fill="{color}"/>',
                f'<text x="{left + bar_width + 8}" y="{y + 22}" font-family="Arial, sans-serif" font-size="12" fill="#1f2933">{html.escape(value_label)}</text>',
            ]
        )
    if color_key and color_values:
        legend_x = left
        legend_y = height - 22
        offset = 0
        for value, color in color_values.items():
            text = str(value)
            parts.extend(
                [
                    f'<rect x="{legend_x + offset}" y="{legend_y - 10}" width="10" height="10" fill="{color}"/>',
                    f'<text x="{legend_x + offset + 16}" y="{legend_y}" font-family="Arial, sans-serif" font-size="12" fill="#52616b">{html.escape(text)}</text>',
                ]
            )
            offset += 18 + len(text) * 8
    parts.append("</svg>")
    path.write_text("\n".join(parts), encoding="utf-8")


def _write_svg_stacked_bar_chart(
    df: pd.DataFrame,
    path: Path,
    title: str,
    subtitle: str,
    group_col: str,
    category_col: str,
    value_col: str,
) -> None:
    categories = [category for category in ["negative", "neutral", "positive"] if category in set(df[category_col])]
    if not categories:
        categories = sorted(str(value) for value in df[category_col].dropna().unique())
    colors = {"negative": "#9a031e", "neutral": "#8d99ae", "positive": "#2f6f73"}
    width = 1000
    row_height = 46
    top = 96
    left = 220
    right = 90
    bottom = 58
    groups = sorted(str(value) for value in df[group_col].dropna().unique())
    height = top + bottom + max(1, len(groups)) * row_height
    chart_width = width - left - right

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#fbfaf7"/>',
        f'<text x="32" y="38" font-family="Arial, sans-serif" font-size="24" font-weight="700" fill="#1f2933">{html.escape(title)}</text>',
        f'<text x="32" y="66" font-family="Arial, sans-serif" font-size="14" fill="#52616b">{html.escape(subtitle)}</text>',
    ]
    for index, group in enumerate(groups):
        y = top + index * row_height
        x = left
        parts.append(
            f'<text x="{left - 14}" y="{y + 24}" text-anchor="end" font-family="Arial, sans-serif" font-size="14" fill="#1f2933">{html.escape(group)}</text>'
        )
        group_df = df[df[group_col].astype(str) == group]
        for category in categories:
            value = float(group_df.loc[group_df[category_col].astype(str) == category, value_col].sum())
            segment_width = (value / 100.0) * chart_width
            parts.append(
                f'<rect x="{x:.2f}" y="{y + 8}" width="{segment_width:.2f}" height="22" fill="{colors.get(category, "#5b6c94")}"/>'
            )
            if segment_width > 42:
                parts.append(
                    f'<text x="{x + segment_width / 2:.2f}" y="{y + 24}" text-anchor="middle" font-family="Arial, sans-serif" font-size="11" fill="#ffffff">{value:.1f}%</text>'
                )
            x += segment_width
    legend_x = left
    legend_y = height - 26
    for index, category in enumerate(categories):
        offset = index * 116
        parts.extend(
            [
                f'<rect x="{legend_x + offset}" y="{legend_y - 10}" width="10" height="10" fill="{colors.get(category, "#5b6c94")}"/>',
                f'<text x="{legend_x + offset + 16}" y="{legend_y}" font-family="Arial, sans-serif" font-size="12" fill="#52616b">{html.escape(category)}</text>',
            ]
        )
    parts.append("</svg>")
    path.write_text("\n".join(parts), encoding="utf-8")


def _write_svg_dual_bar_chart(
    rows: list[dict[str, object]],
    path: Path,
    title: str,
    subtitle: str,
    label_key: str,
    positive_key: str = "positive",
    negative_key: str = "negative",
    max_rows: int = 12,
) -> None:
    chart_rows = rows[:max_rows]
    width = 1000
    row_height = 46
    top = 100
    left = 280
    right = 80
    bottom = 58
    height = top + bottom + max(1, len(chart_rows)) * row_height
    chart_width = width - left - right
    max_value = max(
        [float(row.get(positive_key, 0)) for row in chart_rows]
        + [float(row.get(negative_key, 0)) for row in chart_rows]
        + [1.0]
    )
    colors = {"positive": "#2f6f73", "negative": "#9a031e"}
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#fbfaf7"/>',
        f'<text x="32" y="38" font-family="Arial, sans-serif" font-size="24" font-weight="700" fill="#1f2933">{html.escape(title)}</text>',
        f'<text x="32" y="66" font-family="Arial, sans-serif" font-size="14" fill="#52616b">{html.escape(subtitle)}</text>',
    ]
    for index, row in enumerate(chart_rows):
        y = top + index * row_height
        label = str(row[label_key])
        positive = float(row.get(positive_key, 0))
        negative = float(row.get(negative_key, 0))
        positive_width = (positive / max_value) * chart_width
        negative_width = (negative / max_value) * chart_width
        parts.extend(
            [
                f'<text x="{left - 14}" y="{y + 26}" text-anchor="end" font-family="Arial, sans-serif" font-size="13" fill="#1f2933">{html.escape(label[:42])}</text>',
                f'<rect x="{left}" y="{y + 7}" width="{positive_width:.2f}" height="14" rx="3" fill="{colors["positive"]}"/>',
                f'<rect x="{left}" y="{y + 25}" width="{negative_width:.2f}" height="14" rx="3" fill="{colors["negative"]}"/>',
                f'<text x="{left + positive_width + 8}" y="{y + 19}" font-family="Arial, sans-serif" font-size="11" fill="#1f2933">{positive:,.0f}</text>',
                f'<text x="{left + negative_width + 8}" y="{y + 37}" font-family="Arial, sans-serif" font-size="11" fill="#1f2933">{negative:,.0f}</text>',
            ]
        )
    legend_y = height - 28
    parts.extend(
        [
            f'<rect x="{left}" y="{legend_y - 10}" width="10" height="10" fill="{colors["positive"]}"/>',
            f'<text x="{left + 16}" y="{legend_y}" font-family="Arial, sans-serif" font-size="12" fill="#52616b">positive SnowNLP rows</text>',
            f'<rect x="{left + 190}" y="{legend_y - 10}" width="10" height="10" fill="{colors["negative"]}"/>',
            f'<text x="{left + 206}" y="{legend_y}" font-family="Arial, sans-serif" font-size="12" fill="#52616b">negative SnowNLP rows</text>',
        ]
    )
    parts.append("</svg>")
    path.write_text("\n".join(parts), encoding="utf-8")


def _write_readiness(path: Path, outputs: dict[str, Path], metrics: dict[str, object]) -> None:
    lines = [
        "# Chinese-Specific Insight Outputs",
        "",
        f"These outputs cover {metrics['analysis_label']}. They are aggregate views for presentation and exploratory review, not nationality claims.",
        "",
        f"- Analysis label: `{metrics['analysis_label']}`",
        f"- Rows represented: {metrics['rows_represented']}",
        f"- Source platform mix: {metrics['source_platform_mix']}",
        f"- Minimum theme slice rows for rates: {metrics['minimum_theme_slice_rows_for_rates']}",
        f"- Output folder: `{path.parent}`",
        "",
        "## Figures",
    ]
    for name, output_path in outputs.items():
        if output_path.suffix == ".svg":
            lines.append(f"- `{name}`: `{output_path}`")
    lines.extend(
        [
            "",
            "## Data Views",
        ]
    )
    for name, output_path in outputs.items():
        if output_path.suffix == ".csv":
            lines.append(f"- `{name}`: `{output_path}`")
    lines.extend(
        [
            "",
            "## Caveats",
            "",
            "- Keyword evidence uses reviewed substring matches and should be described as evidence counts, not inferred motives.",
            "- Sentiment categories use SnowNLP as a secondary baseline; reviewed positive/negative/recommendation keyword matches are transparent evidence.",
            f"- Theme rates and sentiment means are suppressed below n={MIN_THEME_SLICE_ROWS}; counts remain in CSV outputs.",
            "- Theme labels come from companion processed annotation files; unmatched rows are `unclassified`. Douyin is excluded from the main theme analysis until further notice.",
            "- Outputs intentionally omit row-level source text, authors, URLs, and record IDs.",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def _write_safe_csv(df: pd.DataFrame, path: Path) -> None:
    assert_no_forbidden_columns(df.columns, context=str(path))
    df.to_csv(path, index=False)


def build_chinese_specific_insights(
    input_dir: Path = DEFAULT_INPUT_DIR,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    analysis_label: str = "Chinese-language Fukui social-media rows",
) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)

    tagged_path = input_dir / "tagged_chinese_social_posts.csv"
    codebook_summary_path = input_dir / "chinese_reviewed_codebook_runtime_summary.csv"
    tagged = load_tagged_rows(tagged_path)
    codebook_summary = load_codebook_summary(codebook_summary_path)

    outputs = {
        "keyword_inventory_by_category": output_dir / "keyword_inventory_by_category.csv",
        "keyword_occurrence_by_category": output_dir / "keyword_occurrence_by_category.csv",
        "sentiment_keyword_counts": output_dir / "sentiment_keyword_counts.csv",
        "keywords_by_snownlp_sentiment_category": output_dir / "keywords_by_snownlp_sentiment_category.csv",
        "sentiment_category_by_platform": output_dir / "sentiment_category_by_platform.csv",
        "theme_sentiment_summary": output_dir / "theme_sentiment_summary.csv",
        "topic_by_sentiment_category": output_dir / "topic_by_sentiment_category.csv",
        "friction_by_sentiment_category": output_dir / "friction_by_sentiment_category.csv",
        "figure_keyword_occurrence_by_category": output_dir / "figure_keyword_occurrence_by_category.svg",
        "figure_top_sentiment_keywords": output_dir / "figure_top_sentiment_keywords.svg",
        "figure_sentiment_category_by_platform": output_dir / "figure_sentiment_category_by_platform.svg",
        "figure_theme_sentiment": output_dir / "figure_theme_sentiment.svg",
        "readiness": output_dir / "chinese_specific_insights_readiness.md",
        "manifest": output_dir / "chinese_specific_insights_manifest.json",
    }

    keyword_inventory = build_keyword_inventory(codebook_summary)
    category_occurrence = build_category_occurrence(input_dir)
    sentiment_keywords = build_sentiment_keyword_counts(tagged)
    keywords_by_snownlp = build_keywords_by_snownlp_category(tagged)
    sentiment_by_platform = build_sentiment_category_by_platform(tagged)
    theme_sentiment = build_theme_sentiment_summary(tagged)
    topic_by_sentiment = build_code_by_sentiment_category(tagged, codebook_summary, "topic")
    friction_by_sentiment = build_code_by_sentiment_category(tagged, codebook_summary, "friction")

    data_views = {
        "keyword_inventory_by_category": keyword_inventory,
        "keyword_occurrence_by_category": category_occurrence,
        "sentiment_keyword_counts": sentiment_keywords,
        "keywords_by_snownlp_sentiment_category": keywords_by_snownlp,
        "sentiment_category_by_platform": sentiment_by_platform,
        "theme_sentiment_summary": theme_sentiment,
        "topic_by_sentiment_category": topic_by_sentiment,
        "friction_by_sentiment_category": friction_by_sentiment,
    }
    for name, df in data_views.items():
        _write_safe_csv(df, outputs[name])

    topic_sentiment_chart_rows = build_topic_sentiment_chart_rows(topic_by_sentiment)
    sentiment_denominators = (
        topic_by_sentiment[["sentiment_category", "denominator_rows"]]
        .drop_duplicates()
        .set_index("sentiment_category")["denominator_rows"]
        .to_dict()
        if not topic_by_sentiment.empty
        else {}
    )
    _write_svg_dual_bar_chart(
        topic_sentiment_chart_rows,
        outputs["figure_keyword_occurrence_by_category"],
        "Chinese Topic Evidence by Sentiment",
        (
            f"Topic keyword matches across n={_fmt_n(len(tagged))} rows; "
            f"positive n={_fmt_n(sentiment_denominators.get('positive', 0))}, "
            f"negative n={_fmt_n(sentiment_denominators.get('negative', 0))}"
        ),
        "label",
    )

    top_sentiment = build_sentiment_keyword_chart_rows(sentiment_keywords)
    _write_svg_bar_chart(
        top_sentiment,
        outputs["figure_top_sentiment_keywords"],
        "Most Common Reviewed Sentiment Keywords by Group",
        f"Top matched terms within each reviewed sentiment-evidence group; n={_fmt_n(len(tagged))} Chinese rows",
        "chart_label",
        "count",
        "sentiment_group_label",
        max_rows=18,
    )

    platform_totals = sentiment_by_platform.groupby("source_platform")["count"].sum().to_dict()
    sentiment_by_platform_chart = sentiment_by_platform.copy()
    sentiment_by_platform_chart["source_platform_label"] = sentiment_by_platform_chart["source_platform"].map(
        lambda value: f"{value} (n={_fmt_n(platform_totals.get(value, 0))})"
    )
    _write_svg_stacked_bar_chart(
        sentiment_by_platform_chart,
        outputs["figure_sentiment_category_by_platform"],
        "SnowNLP Sentiment Share by Platform",
        f"Percentage of Chinese rows in each sentiment category; total n={_fmt_n(len(tagged))}",
        "source_platform_label",
        "sentiment_category",
        "pct_platform_rows",
    )

    theme_rows = theme_sentiment[
        (theme_sentiment["source_platform"] == "all")
        & (theme_sentiment["theme"].astype(str) != "unclassified")
        & (theme_sentiment["theme_slice_status"].astype(str) == "ok")
    ].copy()
    unclassified_rows = int(
        theme_sentiment.loc[
            (theme_sentiment["source_platform"] == "all")
            & (theme_sentiment["theme"].astype(str) == "unclassified"),
            "rows",
        ].sum()
    )
    _write_svg_bar_chart(
        theme_rows.to_dict("records"),
        outputs["figure_theme_sentiment"],
        "Classified Chinese Social Themes",
        (
            f"Rows with explicit theme labels n={_fmt_n(int(theme_rows['rows'].sum()))}; "
            f"unclassified n={_fmt_n(unclassified_rows)} remains in the CSV; low-n themes suppressed"
        ),
        "theme",
        "rows",
    )

    metrics = {
        "analysis_label": analysis_label,
        "rows_represented": int(len(tagged)),
        "source_platform_mix": {str(k): int(v) for k, v in tagged["source_platform"].value_counts().items()},
        "minimum_theme_slice_rows_for_rates": MIN_THEME_SLICE_ROWS,
        "data_view_count": len(data_views),
        "figure_count": 4,
    }
    _write_readiness(outputs["readiness"], outputs, metrics)

    manifest = research_manifest(
        kind="chinese_specific_insights",
        command="python scripts/build_chinese_specific_insights.py",
        inputs=[
            file_record(tagged_path, "ignored_tagged_chinese_social_rows", required=True),
            file_record(codebook_summary_path, "aggregate_runtime_codebook_summary", required=True),
            file_record(input_dir / TOPIC_AGGREGATE_INPUT, "aggregate_topic_evidence", required=True),
        ],
        outputs=[
            file_record(path, name, required=True)
            for name, path in outputs.items()
            if name != "manifest"
        ],
        filters={
            "scope": analysis_label,
            "minimum_theme_slice_rows_for_rates": MIN_THEME_SLICE_ROWS,
        },
        metrics=metrics,
        caveats=[
            "Keyword evidence is reviewed substring matching, not a causal explanation.",
            "SnowNLP sentiment is a secondary baseline sentiment tool for Chinese-language social text.",
            f"Theme rates and sentiment means are suppressed below n={MIN_THEME_SLICE_ROWS}; counts remain visible.",
            "No row-level text, author, URL, or source record columns are written to this output folder.",
        ],
    )
    write_json(outputs["manifest"], manifest)

    logger.info("Chinese-specific insight outputs written: %s", output_dir)
    return {"outputs": {name: str(path) for name, path in outputs.items()}, "metrics": metrics}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--analysis-label", default="Chinese-language Fukui social-media rows")
    args = parser.parse_args()

    build_chinese_specific_insights(
        input_dir=args.input_dir,
        output_dir=args.output_dir,
        analysis_label=args.analysis_label,
    )


if __name__ == "__main__":
    main()
