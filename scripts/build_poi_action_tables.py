#!/usr/bin/env python3
"""Render two presentation table figures from the live POI opportunity index:

  * figure_poi_fix_it_table   — top fix-it POIs (busy, high-volume, nudge-able pain points)
  * figure_poi_promote_it_table — top promote-it POIs (low-volume, high-satisfaction gems)

Both read output/nudge_analysis/poi_opportunity_index.csv live (no hand-typed
numbers), emit an SVG in the house palette, and rasterize to PNG with cairosvg
so the figures drop straight into slides.

Run:  .venv/bin/python scripts/build_poi_action_tables.py
"""
from __future__ import annotations

from pathlib import Path

import cairosvg
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "output" / "nudge_analysis" / "poi_opportunity_index.csv"
OUT_DIR = ROOT / "docs" / "statistical_test_figures"
PNG_DIR = ROOT / "docs" / "statistical_test_figures_png"

# House palette (mirrors scripts/build_nudge_figures.py).
PALETTE = {
    "ink": "#172033",
    "muted": "#5b677a",
    "line": "#d7dde8",
    "bg": "#fbfaf7",
    "header": "#2f6f73",
    "row_alt": "#f1efe9",
    "promote": "#2f6f73",
    "fix": "#c06c38",
}

# Friction/draw aspect codes -> short readable labels for the audience.
ASPECT_LABELS = {
    "english_information_gap": "English info",
    "wayfinding_signage": "Wayfinding",
    "transport_access": "Transport access",
    "booking_ticketing": "Booking/ticketing",
    "opening_hours_availability": "Opening hours",
    "itinerary_fit_time_cost": "Itinerary fit",
}


def _esc(text: str) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _labels(codes: object) -> str:
    if not isinstance(codes, str) or not codes.strip():
        return "—"
    out = [ASPECT_LABELS.get(c, c.replace("_", " ")) for c in codes.split(";") if c]
    return ", ".join(out)


def _pct(value: float) -> str:
    return f"{value * 100:.0f}%"


def _table_svg(
    title: str,
    subtitle_ja: str,
    columns: list[tuple[str, float, str]],  # (header, x_fraction, align)
    rows: list[list[str]],
    accent: str,
) -> str:
    width = 1900
    margin = 60
    title_h = 110
    header_h = 56
    row_h = 64
    height = title_h + header_h + row_h * len(rows) + margin
    inner_w = width - 2 * margin

    def col_x(frac: float) -> float:
        return margin + frac * inner_w

    parts: list[str] = []
    parts.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" '
        f'font-family="Helvetica, Arial, \'Noto Sans CJK JP\', sans-serif">'
    )
    parts.append(f'<rect width="{width}" height="{height}" fill="{PALETTE["bg"]}"/>')
    parts.append(f'<rect x="0" y="0" width="14" height="{height}" fill="{accent}"/>')

    # Title block.
    parts.append(
        f'<text x="{margin}" y="56" font-size="38" font-weight="700" '
        f'fill="{PALETTE["ink"]}">{_esc(title)}</text>'
    )
    # cairosvg has no per-glyph font fallback, so the CJK subtitle needs a
    # font-family that leads with a Japanese face or the glyphs render blank.
    parts.append(
        f'<text x="{margin}" y="90" font-size="22" fill="{PALETTE["muted"]}" '
        f"font-family=\"'Noto Sans CJK JP', sans-serif\">"
        f'{_esc(subtitle_ja)}</text>'
    )

    top = title_h
    # Header row.
    parts.append(
        f'<rect x="{margin}" y="{top}" width="{inner_w}" height="{header_h}" '
        f'fill="{PALETTE["header"]}"/>'
    )
    for head, frac, align in columns:
        anchor = {"start": "start", "mid": "middle", "end": "end"}[align]
        parts.append(
            f'<text x="{col_x(frac):.1f}" y="{top + 37}" font-size="22" '
            f'font-weight="700" fill="#ffffff" text-anchor="{anchor}">{_esc(head)}</text>'
        )

    # Body rows.
    y = top + header_h
    for i, row in enumerate(rows):
        if i % 2 == 1:
            parts.append(
                f'<rect x="{margin}" y="{y}" width="{inner_w}" height="{row_h}" '
                f'fill="{PALETTE["row_alt"]}"/>'
            )
        for (_, frac, align), value in zip(columns, row):
            anchor = {"start": "start", "mid": "middle", "end": "end"}[align]
            parts.append(
                f'<text x="{col_x(frac):.1f}" y="{y + 41}" font-size="23" '
                f'fill="{PALETTE["ink"]}" text-anchor="{anchor}">{_esc(value)}</text>'
            )
        parts.append(
            f'<line x1="{margin}" y1="{y + row_h}" x2="{margin + inner_w}" '
            f'y2="{y + row_h}" stroke="{PALETTE["line"]}" stroke-width="1"/>'
        )
        y += row_h

    parts.append("</svg>")
    return "".join(parts)


def _write(name: str, svg: str) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    PNG_DIR.mkdir(parents=True, exist_ok=True)
    svg_path = OUT_DIR / f"{name}.svg"
    png_path = PNG_DIR / f"{name}.png"
    svg_path.write_text(svg, encoding="utf-8")
    cairosvg.svg2png(bytestring=svg.encode("utf-8"), write_to=str(png_path), output_width=1600)
    print(f"wrote {svg_path.relative_to(ROOT)} and {png_path.relative_to(ROOT)}")


def main() -> None:
    if not INPUT.exists():
        raise SystemExit(f"Missing input: {INPUT}. Run `make nudge-poi` first.")
    df = pd.read_csv(INPUT)

    # ---- Fix-it table ----------------------------------------------------
    fix = df[df["is_fix_it"].astype(bool)].sort_values("fix_it_score", ascending=False)
    fix_cols = [
        ("#", 0.01, "start"),
        ("Site", 0.04, "start"),
        ("Pref.", 0.40, "start"),
        ("Reviews", 0.55, "end"),
        ("Positive", 0.64, "end"),
        ("Main pain points", 0.68, "start"),
    ]
    fix_rows = [
        [
            str(rank),
            r["poi_name"],
            r["prefecture"],
            f'{int(r["n_reviews"])}',
            _pct(r["positive_share"]),
            _labels(r["dominant_nudgeable_friction_codes"]),
        ]
        for rank, (_, r) in enumerate(fix.iterrows(), start=1)
    ]
    _write(
        "figure_poi_fix_it_table",
        _table_svg(
            "Fix-it sites · Hokuriku",
            "改善型スポット — 来訪が多く、ナッジ可能な不満点あり",
            fix_cols,
            fix_rows,
            PALETTE["fix"],
        ),
    )

    # ---- Promote-it table ------------------------------------------------
    promote = df[df["is_promote_it"].astype(bool)].sort_values(
        "promote_it_score", ascending=False
    )
    promote_cols = [
        ("#", 0.01, "start"),
        ("Site", 0.04, "start"),
        ("Pref.", 0.40, "start"),
        ("Reviews", 0.55, "end"),
        ("Positive (95% CI)", 0.80, "end"),
        ("Confidence", 0.83, "start"),
    ]
    promote_rows = [
        [
            str(rank),
            r["poi_name"],
            r["prefecture"],
            f'{int(r["n_reviews"])}',
            f'{_pct(r["positive_share"])} '
            f'({_pct(r["positive_share_ci_low"])}–{_pct(r["positive_share_ci_high"])})',
            str(r["promote_confidence"]),
        ]
        for rank, (_, r) in enumerate(promote.iterrows(), start=1)
    ]
    _write(
        "figure_poi_promote_it_table",
        _table_svg(
            "Promote-it sites · Hokuriku",
            "推奨型スポット — 来訪は少ないが満足度が高い隠れた名所",
            promote_cols,
            promote_rows,
            PALETTE["promote"],
        ),
    )


if __name__ == "__main__":
    main()
