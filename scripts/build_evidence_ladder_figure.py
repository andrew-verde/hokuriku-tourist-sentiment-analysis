#!/usr/bin/env python3
"""Render the 'evidence ladder' figure for slide 12 (What this can and cannot claim).

A conceptual three-rung ladder: Description -> Association (you are here) ->
Causal claim (requires a randomized experiment, i.e. slide 13). No data values,
so nothing is read from the analysis outputs.

Run:  .venv/bin/python scripts/build_evidence_ladder_figure.py
"""
from __future__ import annotations

from pathlib import Path

import cairosvg

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "docs" / "statistical_test_figures"
PNG_DIR = ROOT / "docs" / "statistical_test_figures_png"

PALETTE = {
    "ink": "#172033",
    "muted": "#5b677a",
    "bg": "#fbfaf7",
    "here": "#2f6f73",      # association rung (where the study sits)
    "below": "#6f8f72",     # description rung (solid, reached)
    "above": "#bc6c25",     # causal rung accent (not yet reached)
    "above_fill": "#f1ece4",
    "badge": "#9a031e",
    "spine": "#33414f",
}

JP = "'Noto Sans CJK JP', sans-serif"


def _esc(t: str) -> str:
    return str(t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def build_svg() -> str:
    width, height = 1500, 940
    parts: list[str] = []
    parts.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" font-family="Helvetica, Arial, sans-serif">'
    )
    parts.append(f'<rect width="{width}" height="{height}" fill="{PALETTE["bg"]}"/>')
    parts.append(f'<rect x="0" y="0" width="14" height="{height}" fill="{PALETTE["here"]}"/>')

    parts.append(
        f'<text x="60" y="58" font-size="38" font-weight="700" '
        f'fill="{PALETTE["ink"]}">What we can and cannot claim</text>'
    )
    parts.append(
        f'<text x="60" y="92" font-size="22" fill="{PALETTE["muted"]}" '
        f'font-family="{JP}">主張できること・できないこと</text>'
    )

    # Rungs, top (goal) to bottom (foundation).
    box_x, box_w, box_h, gap = 260, 1060, 188, 34
    top = 150
    # (key, en title, ja title, annotation en, annotation ja)
    rungs = [
        ("above", "Causal claim", "因果の主張",
         "Requires a randomized experiment - next semester (slide 13).",
         "無作為化実験が必要 — 来学期(スライド13)。"),
        ("here", "Association", "関連",
         "FDR-tested adjusted odds ratios. This is what the study supports.",
         "FDR補正済みの調整オッズ比。本研究が支持する範囲。"),
        ("below", "Description", "記述",
         "Prevalence, counts, and language mix of the reviews.",
         "口コミの有病率・件数・言語構成。"),
    ]

    y = top
    for i, (key, en, ja, ann_en, ann_ja) in enumerate(rungs):
        if key == "above":
            # Goal rung: dashed outline, faded fill = not yet reached.
            parts.append(
                f'<rect x="{box_x}" y="{y}" width="{box_w}" height="{box_h}" rx="10" '
                f'fill="{PALETTE["above_fill"]}" stroke="{PALETTE["above"]}" '
                f'stroke-width="3" stroke-dasharray="10 7"/>'
            )
            title_color = PALETTE["above"]
        else:
            fill = PALETTE["here"] if key == "here" else PALETTE["below"]
            parts.append(
                f'<rect x="{box_x}" y="{y}" width="{box_w}" height="{box_h}" rx="10" '
                f'fill="{fill}"/>'
            )
            title_color = "#ffffff"

        ja_color = PALETTE["muted"] if key == "above" else "#eaf1f0"
        ann_color = PALETTE["ink"] if key == "above" else "#eaf1f0"

        parts.append(
            f'<text x="{box_x + 36}" y="{y + 70}" font-size="34" font-weight="700" '
            f'fill="{title_color}">{_esc(en)}</text>'
        )
        parts.append(
            f'<text x="{box_x + 36}" y="{y + 104}" font-size="19" fill="{ja_color}" '
            f'font-family="{JP}">{_esc(ja)}</text>'
        )
        parts.append(
            f'<text x="{box_x + 36}" y="{y + 142}" font-size="19" fill="{ann_color}">'
            f'{_esc(ann_en)}</text>'
        )
        parts.append(
            f'<text x="{box_x + 36}" y="{y + 168}" font-size="15" fill="{ann_color}" '
            f'font-family="{JP}">{_esc(ann_ja)}</text>'
        )

        if key == "here":
            # "You are here" badge on the right edge of the association rung.
            bx, bw, bh = box_x + box_w - 250, 214, 52
            by = y + box_h / 2 - bh / 2
            parts.append(
                f'<rect x="{bx}" y="{by:.1f}" width="{bw}" height="{bh}" rx="26" '
                f'fill="{PALETTE["badge"]}"/>'
            )
            parts.append(
                f'<text x="{bx + bw / 2:.1f}" y="{by + 34:.1f}" font-size="22" '
                f'font-weight="700" fill="#ffffff" text-anchor="middle">YOU ARE HERE</text>'
            )

        # Gap marker between the association rung and the causal rung above it.
        if key == "above":
            gy = y + box_h + gap / 2
            parts.append(
                f'<text x="{box_x + box_w}" y="{gy + 6:.1f}" font-size="16" '
                f'fill="{PALETTE["above"]}" font-style="italic" text-anchor="end">'
                f'the gap an experiment closes</text>'
            )
        y += box_h + gap

    # Left spine: upward arrow = stronger causal claim.
    sx = 150
    sy_top, sy_bot = top + 6, y - gap - 6
    parts.append(
        f'<line x1="{sx}" y1="{sy_bot:.1f}" x2="{sx}" y2="{sy_top:.1f}" '
        f'stroke="{PALETTE["spine"]}" stroke-width="3"/>'
    )
    parts.append(
        f'<polygon points="{sx - 9},{sy_top + 16:.1f} {sx + 9},{sy_top + 16:.1f} '
        f'{sx},{sy_top:.1f}" fill="{PALETTE["spine"]}"/>'
    )
    mid = (sy_top + sy_bot) / 2
    parts.append(
        f'<text x="{sx - 22}" y="{mid:.1f}" font-size="18" fill="{PALETTE["spine"]}" '
        f'text-anchor="middle" transform="rotate(-90 {sx - 22} {mid:.1f})">'
        f'stronger causal claim</text>'
    )

    parts.append("</svg>")
    return "".join(parts)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    PNG_DIR.mkdir(parents=True, exist_ok=True)
    name = "figure_evidence_ladder"
    svg = build_svg()
    (OUT_DIR / f"{name}.svg").write_text(svg, encoding="utf-8")
    cairosvg.svg2png(bytestring=svg.encode("utf-8"),
                     write_to=str(PNG_DIR / f"{name}.png"), output_width=1500)
    print(f"wrote {(OUT_DIR / (name + '.svg')).relative_to(ROOT)} and "
          f"{(PNG_DIR / (name + '.png')).relative_to(ROOT)}")


if __name__ == "__main__":
    main()
