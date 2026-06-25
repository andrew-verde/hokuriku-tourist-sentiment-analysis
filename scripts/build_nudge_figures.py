#!/usr/bin/env python3
"""Build aggregate-only SVG figures for the nudge opportunity analysis.

This script reads the live nudge-analysis CSV outputs and turns them into a
small figure pack:
1. Aspect penalty-by-prevalence map for friction codes.
2. POI action map for fix-it, promote-it, and crowding-hotspot candidates.
3. Information-lever prevalence chart for nudge-able friction aspects.

All numbers are fetched from aggregate CSVs at build time. Missing required
rows or fields fail the build rather than producing guessed values. The figures
are exploratory visual summaries, not causal-effect estimates.
"""

from __future__ import annotations

import argparse
import html
import math
import sys
import textwrap
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.provenance import (  # noqa: E402
    assert_no_forbidden_columns,
    file_record,
    repo_relative,
    research_manifest,
    write_json,
)


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INPUT_DIR = ROOT / "output" / "nudge_analysis"
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

NUDGEABLE_FRICTION_ASPECTS = [
    "english_information_gap",
    "wayfinding_signage",
    "transport_access",
    "booking_ticketing",
    "opening_hours_availability",
    "itinerary_fit_time_cost",
]
SIGNIFICANT_LABEL_ASPECTS = {
    "opening_hours_availability",
    "price_value",
    "cleanliness_comfort",
    "itinerary_fit_time_cost",
}


class NudgeFigureError(RuntimeError):
    pass


class MissingInputError(NudgeFigureError):
    pass


class MissingColumnsError(NudgeFigureError):
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


def _safe_label(value: object, max_len: int = 42) -> str:
    text = str(value).replace("_", " ")
    return text if len(text) <= max_len else text[: max_len - 1] + "..."


def _wrapped_label_lines(value: object, max_len: int = 34) -> list[str]:
    text = str(value).replace("_", " ")
    return textwrap.wrap(text, width=max_len, break_long_words=False, break_on_hyphens=False) or [""]


def _fmt_pct(value: object, digits: int = 1) -> str:
    return f"{float(value) * 100:.{digits}f}%"


def _fmt_p(value: object) -> str:
    if pd.isna(value):
        return "FDR n/a"
    number = float(value)
    if number < 0.001:
        return f"FDR {number:.1e}"
    return f"FDR {number:.3f}"


def _legend(parts: list[str], x: float, y: float, items: list[tuple[str, str]]) -> None:
    offset = 0
    for label, color in items:
        parts.append(f'<rect x="{x + offset:.2f}" y="{y - 10:.2f}" width="10" height="10" fill="{color}"/>')
        parts.append(_text(x + offset + 16, y, label, size=12, fill=PALETTE["muted"]))
        offset += max(120, len(label) * 7 + 32)


def _required_row(df: pd.DataFrame, mask: pd.Series, label: str) -> pd.Series:
    rows = df[mask]
    if rows.empty:
        raise NudgeFigureError(f"Required row missing for nudge figure: {label}")
    return rows.iloc[0]


def _bool_value(value: object) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes"}


def _scale(value: float, data_min: float, data_max: float, pixel_min: float, pixel_max: float) -> float:
    if data_max <= data_min:
        return (pixel_min + pixel_max) / 2
    return pixel_min + (value - data_min) / (data_max - data_min) * (pixel_max - pixel_min)


def write_aspect_opportunity_map(aspects: pd.DataFrame, output_dir: Path) -> dict[str, str]:
    # One row per friction aspect from the primary pooled model. Values all come
    # from aspect_opportunity_map.csv: prevalence, Firth OR, and FDR flag.
    data = aspects[
        (aspects["analysis"] == "A_primary")
        & (aspects["segment"] == "pooled")
        & (aspects["signal_type"] == "friction")
        & (aspects["status"] == "ok")
    ].copy()
    if data.empty:
        raise NudgeFigureError("No A_primary pooled friction rows available for aspect map")
    required_labels = SIGNIFICANT_LABEL_ASPECTS - set(data["aspect"])
    if required_labels:
        raise NudgeFigureError(f"Required significant aspect rows missing: {', '.join(sorted(required_labels))}")

    width = 1120
    height = 720
    left = 110
    right = 70
    top = 102
    bottom = 132
    chart_w = width - left - right
    chart_h = height - top - bottom
    x_max = max(float(data["prevalence"].max()) * 1.18, 0.01)
    y_max = max(float(data["odds_ratio"].max()) * 1.12, 2.0)

    def sx(value: float) -> float:
        return _scale(value, 0.0, x_max, left, left + chart_w)

    def sy(value: float) -> float:
        return _scale(value, 0.0, y_max, top + chart_h, top)

    path = output_dir / "figure_nudge_aspect_opportunity_map.svg"
    parts = _svg_header(
        width,
        height,
        "Nudge Aspect Opportunity Map",
        "Primary friction aspects: prevalence vs adjusted odds of low rating",
    )
    # Axis grid and OR=1 reference line.
    for tick in (0.0, x_max / 2, x_max):
        x = sx(tick)
        parts.append(f'<line x1="{x:.2f}" x2="{x:.2f}" y1="{top:.2f}" y2="{top + chart_h:.2f}" stroke="{PALETTE["line"]}" opacity="0.55"/>')
        parts.append(_text(x, top + chart_h + 24, f"{tick * 100:.1f}%", size=11, fill=PALETTE["muted"], anchor="middle"))
    for tick in (0.0, 1.0, y_max / 2, y_max):
        y = sy(tick)
        parts.append(f'<line x1="{left:.2f}" x2="{left + chart_w:.2f}" y1="{y:.2f}" y2="{y:.2f}" stroke="{PALETTE["line"]}" opacity="0.55"/>')
        parts.append(_text(left - 12, y + 4, f"{tick:.1f}", size=11, fill=PALETTE["muted"], anchor="end"))
    parts.append(f'<line x1="{left:.2f}" x2="{left + chart_w:.2f}" y1="{sy(1.0):.2f}" y2="{sy(1.0):.2f}" stroke="{PALETTE["negative"]}" stroke-dasharray="6 5" stroke-width="1.7"/>')
    parts.append(_text(left + chart_w - 4, sy(1.0) - 8, "OR=1 reference", size=11, fill=PALETTE["negative"], anchor="end"))

    for _, row in data.sort_values("fdr_significant").iterrows():
        sig = _bool_value(row["fdr_significant"])
        x = sx(float(row["prevalence"]))
        y = sy(float(row["odds_ratio"]))
        color = PALETTE["negative"] if sig else PALETTE["neutral"]
        opacity = 0.9 if sig else 0.35
        radius = 7.5 if sig else 5.0
        fill = color if sig else PALETTE["bg"]
        parts.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{radius:.2f}" fill="{fill}" stroke="{color}" stroke-width="2" opacity="{opacity:.2f}"/>')
        if sig and row["aspect"] in SIGNIFICANT_LABEL_ASPECTS:
            label = str(row["aspect"]).replace("_", " ")
            parts.append(_text(min(x + 10, left + chart_w - 8), max(y - 8, top + 14), label, size=11, weight=700, fill=PALETTE["ink"]))
    parts.append(_text(left + chart_w / 2, height - 78, "Pooled prevalence of aspect code", size=13, weight=700, anchor="middle"))
    parts.append(_text(24, top + chart_h / 2, "Adjusted odds ratio for low rating", size=13, weight=700, anchor="start"))
    _legend(parts, left, height - 42, [("FDR-significant", PALETTE["negative"]), ("not FDR-significant", PALETTE["neutral"])])
    parts.append(_text(32, height - 18, "Firth-penalized logit; text length, language, and prefecture adjusted; BH-FDR; exploratory ranking only.", size=12, fill=PALETTE["muted"]))
    _write_svg(path, parts)
    return {
        "figure": "Nudge aspect opportunity map",
        "path": str(path),
        "question": "Which friction aspects are both common and associated with low ratings?",
        "caveat": "Exploratory Firth-penalized associations, not causal effects.",
    }


def _poi_class(row: pd.Series) -> tuple[str, str]:
    if _bool_value(row["is_promote_it"]):
        return "promote-it", PALETTE["positive"]
    if _bool_value(row["is_crowding_hotspot"]):
        return "crowding hotspot", PALETTE["negative"]
    if _bool_value(row["is_fix_it"]):
        return "fix-it", PALETTE["event"]
    return "other", PALETTE["neutral"]


def write_poi_action_map(pois: pd.DataFrame, output_dir: Path) -> dict[str, str]:
    # Each dot is one POI aggregate. No POI IDs are present in the input/output.
    data = pois[pois["n_reviews"].astype(float) >= 10].copy()
    if data.empty:
        raise NudgeFigureError("No POIs with n_reviews >= 10 available for action map")
    low_threshold = float(data["low_volume_threshold"].dropna().iloc[0])
    high_threshold = float(data["high_volume_threshold"].dropna().iloc[0])

    width = 1240
    height = 760
    left = 92
    right = 80
    top = 104
    bottom = 138
    chart_w = width - left - right
    chart_h = height - top - bottom
    x_max = max(float(data["n_reviews"].max()) * 1.08, high_threshold * 1.08)
    y_min = max(0.0, float(data["positive_share_ci_low"].min()) - 0.04)
    y_max = min(1.0, float(data["positive_share_ci_high"].max()) + 0.04)

    def sx(value: float) -> float:
        return _scale(value, 0.0, x_max, left, left + chart_w)

    def sy(value: float) -> float:
        return _scale(value, y_min, y_max, top + chart_h, top)

    path = output_dir / "figure_nudge_poi_action_map.svg"
    parts = _svg_header(
        width,
        height,
        "POI Action Map: Fix, Promote, Redirect",
        "POI aggregates with rating-based positive share and Wilson uncertainty",
    )
    for threshold, label in [(low_threshold, "low-volume cutoff"), (high_threshold, "high-volume cutoff")]:
        x = sx(threshold)
        parts.append(f'<line x1="{x:.2f}" x2="{x:.2f}" y1="{top:.2f}" y2="{top + chart_h:.2f}" stroke="{PALETTE["line"]}" stroke-dasharray="6 5" stroke-width="1.5"/>')
        parts.append(_text(x + 6, top + 14, label, size=11, fill=PALETTE["muted"]))
    for tick in (0.0, low_threshold, high_threshold, x_max):
        x = sx(tick)
        parts.append(_text(x, top + chart_h + 24, f"{tick:.0f}", size=11, fill=PALETTE["muted"], anchor="middle"))
    for tick in (0.7, 0.85, 1.0):
        if y_min <= tick <= y_max:
            y = sy(tick)
            parts.append(f'<line x1="{left:.2f}" x2="{left + chart_w:.2f}" y1="{y:.2f}" y2="{y:.2f}" stroke="{PALETTE["line"]}" opacity="0.55"/>')
            parts.append(_text(left - 12, y + 4, f"{tick * 100:.0f}%", size=11, fill=PALETTE["muted"], anchor="end"))

    label_rows = data[
        data["is_promote_it"].map(_bool_value) | data["is_crowding_hotspot"].map(_bool_value)
    ].copy()
    for _, row in data.iterrows():
        x = sx(float(row["n_reviews"]))
        y = sy(float(row["positive_share"]))
        y_low = sy(float(row["positive_share_ci_low"]))
        y_high = sy(float(row["positive_share_ci_high"]))
        klass, color = _poi_class(row)
        parts.append(f'<line x1="{x:.2f}" x2="{x:.2f}" y1="{y_low:.2f}" y2="{y_high:.2f}" stroke="{color}" stroke-width="1.2" opacity="0.55"/>')
        marker = "rect" if klass == "fix-it" else "circle"
        if marker == "rect":
            parts.append(f'<rect x="{x - 5:.2f}" y="{y - 5:.2f}" width="10" height="10" fill="{color}" opacity="0.78"/>')
        else:
            parts.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="5.5" fill="{color}" opacity="0.78"/>')
        if _bool_value(row["is_fukui"]):
            parts.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="9.0" fill="none" stroke="{PALETTE["ink"]}" stroke-width="1.5" opacity="0.85"/>')

    for _, row in label_rows.sort_values(["is_promote_it", "is_crowding_hotspot"], ascending=False).iterrows():
        x = sx(float(row["n_reviews"]))
        y = sy(float(row["positive_share"]))
        label = _safe_label(row["poi_name"], 30)
        parts.append(_text(min(x + 9, left + chart_w - 6), max(y - 9, top + 12), label, size=10, weight=700))

    parts.append(_text(left + chart_w / 2, height - 84, "Review volume (n reviews)", size=13, weight=700, anchor="middle"))
    parts.append(_text(24, top + chart_h / 2, "Positive share (4-5 star reviews)", size=13, weight=700))
    _legend(
        parts,
        left,
        height - 48,
        [
            ("promote-it", PALETTE["positive"]),
            ("fix-it", PALETTE["event"]),
            ("crowding hotspot", PALETTE["negative"]),
            ("other", PALETTE["neutral"]),
        ],
    )
    parts.append(_text(32, height - 18, "Positive share is rating-based; promote-it is exploratory candidate-generation; small-n Wilson CIs are wide.", size=12, fill=PALETTE["muted"]))
    _write_svg(path, parts)
    return {
        "figure": "Nudge POI action map",
        "path": str(path),
        "question": "Which POIs are candidate fix-it, promote-it, or redirect-from hotspots?",
        "caveat": "POI classes are exploratory; positive share is Google-star based.",
    }


def write_info_levers(aspects: pd.DataFrame, output_dir: Path) -> dict[str, str]:
    # Six nudge-able friction aspects. Bar lengths and CI whiskers use Wilson
    # prevalence estimates from the aspect map CSV; text labels show Firth OR.
    rows = []
    for aspect in NUDGEABLE_FRICTION_ASPECTS:
        row = _required_row(
            aspects,
            (aspects["analysis"] == "A_primary")
            & (aspects["segment"] == "pooled")
            & (aspects["aspect"] == aspect),
            aspect,
        )
        rows.append(row)
    data = pd.DataFrame(rows).sort_values("prevalence", ascending=True)

    width = 1160
    height = 520
    left = 330
    right = 270
    top = 98
    row_h = 54
    chart_w = width - left - right
    x_max = max(float(data["prevalence_ci_high"].max()) * 1.15, 0.01)

    def sx(value: float) -> float:
        return _scale(value, 0.0, x_max, left, left + chart_w)

    path = output_dir / "figure_nudge_info_levers.svg"
    parts = _svg_header(
        width,
        height,
        "Nudge-Able Information Levers",
        "Prevalence and adjusted low-rating association for six friction aspects",
    )
    grid_bottom = top + (len(data) - 1) * row_h + 36
    for tick in (0.0, x_max / 2, x_max):
        x = sx(tick)
        parts.append(f'<line x1="{x:.2f}" x2="{x:.2f}" y1="{top - 8:.2f}" y2="{grid_bottom:.2f}" stroke="{PALETTE["line"]}" opacity="0.55"/>')
        parts.append(_text(x, grid_bottom + 24, f"{tick * 100:.1f}%", size=11, fill=PALETTE["muted"], anchor="middle"))
    for idx, row in enumerate(data.itertuples(index=False)):
        y = top + idx * row_h
        cy = y + 22
        sig = _bool_value(row.fdr_significant)
        color = PALETTE["negative"] if sig else PALETTE["event"]
        prevalence = float(row.prevalence)
        low = float(row.prevalence_ci_low)
        high = float(row.prevalence_ci_high)
        parts.append(_text(left - 14, cy + 4, _safe_label(row.aspect, 38), size=12, anchor="end"))
        parts.append(f'<line x1="{sx(low):.2f}" x2="{sx(high):.2f}" y1="{cy:.2f}" y2="{cy:.2f}" stroke="{color}" stroke-width="2.0"/>')
        parts.append(f'<rect x="{left:.2f}" y="{cy - 9:.2f}" width="{sx(prevalence) - left:.2f}" height="18" rx="3" fill="{color}" opacity="0.78"/>')
        star = " *" if sig else ""
        under = " underpowered" if _bool_value(row.underpowered) else ""
        if pd.notna(row.odds_ratio):
            label = f"OR {float(row.odds_ratio):.2f}; {_fmt_p(row.p_value_bh_fdr)}{star}{under}"
        else:
            label = f"OR n/a; {_fmt_p(row.p_value_bh_fdr)}{under}"
        parts.append(_text(left + chart_w + 18, cy + 4, label, size=11, weight=700 if sig else 400, fill=PALETTE["ink"]))
    parts.append(_text(left + chart_w / 2, height - 54, "Pooled prevalence with Wilson 95% CI", size=13, weight=700, anchor="middle"))
    parts.append(_text(32, height - 18, "Asterisk marks BH-FDR significance; rare or underpowered levers remain visible with uncertainty.", size=12, fill=PALETTE["muted"]))
    _write_svg(path, parts)
    return {
        "figure": "Nudge information levers",
        "path": str(path),
        "question": "Which nudge-able friction levers are present and statistically evidenced?",
        "caveat": "Rare aspects stay visible; underpowered flags should temper interpretation.",
    }


def _write_questions(path: Path, questions: list[dict[str, str]]) -> None:
    lines = [
        "# Nudge Figure Questions",
        "",
        "All figures are aggregate-only. They omit row-level review text, authors, URLs, POI IDs, review IDs, and raw captures.",
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


def build_nudge_figures(
    input_dir: Path = DEFAULT_INPUT_DIR,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    command: str | None = None,
) -> dict:
    paths = {
        "aspect_opportunity_map": input_dir / "aspect_opportunity_map.csv",
        "poi_opportunity_index": input_dir / "poi_opportunity_index.csv",
    }
    aspects = _read_csv(
        paths["aspect_opportunity_map"],
        {
            "analysis",
            "aspect",
            "signal_type",
            "segment",
            "prevalence",
            "prevalence_ci_low",
            "prevalence_ci_high",
            "odds_ratio",
            "p_value_bh_fdr",
            "fdr_significant",
            "underpowered",
            "status",
        },
        "nudge-analysis",
    )
    pois = _read_csv(
        paths["poi_opportunity_index"],
        {
            "poi_name",
            "prefecture",
            "n_reviews",
            "positive_share",
            "positive_share_ci_low",
            "positive_share_ci_high",
            "is_fukui",
            "is_fix_it",
            "is_promote_it",
            "is_crowding_hotspot",
            "low_volume_threshold",
            "high_volume_threshold",
        },
        "poi-opportunity",
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    questions = [
        write_aspect_opportunity_map(aspects, output_dir),
        write_poi_action_map(pois, output_dir),
        write_info_levers(aspects, output_dir),
    ]

    question_records = [{**item, "path": repo_relative(item["path"])} for item in questions]
    questions_path = output_dir / "nudge_figure_questions.md"
    index_path = output_dir / "nudge_figure_index.csv"
    manifest_path = output_dir / "nudge_figure_manifest.json"
    _write_questions(questions_path, question_records)
    index = pd.DataFrame(question_records)
    assert_no_forbidden_columns(index.columns, forbidden=FORBIDDEN_AGGREGATE_COLUMNS, context=str(index_path))
    index.to_csv(index_path, index=False)

    figure_paths = [Path(item["path"]) for item in questions]
    report = research_manifest(
        kind="nudge_figure_pack",
        command=command or " ".join(sys.argv),
        inputs=[file_record(path, role, required=True) for role, path in paths.items()],
        outputs=[
            file_record(index_path, "nudge_figure_index", required=True),
            file_record(questions_path, "nudge_figure_questions", required=True),
            *[file_record(path, f"nudge_figure_{path.stem}", required=True) for path in figure_paths],
        ],
        filters={"output_surface": "aggregate-only SVG", "source": "nudge analysis CSVs"},
        metrics={"figure_count": len(figure_paths)},
        caveats=[
            "Exploratory and hypothesis-generating; not causal.",
            "Aspect estimates use Firth-penalized models and BH-FDR from the source CSV.",
            "POI promote-it status is exploratory candidate-generation; small-n intervals are shown.",
            "Positive share is based on Google star ratings, not sentiment-tool scores.",
            "Figures are generated from aggregate CSVs and omit row-level text, URLs, authors, POI IDs, and review IDs.",
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
    report = build_nudge_figures(
        input_dir=args.input_dir,
        output_dir=args.output_dir,
        command=" ".join(sys.argv),
    )
    print(f"wrote {report['metrics']['figure_count']} nudge figures")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
