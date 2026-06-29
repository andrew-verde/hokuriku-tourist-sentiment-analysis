#!/usr/bin/env python3
"""Plain-language ("12th-grade") variant of the decision-rule funnel.

Same live stage counts as scripts/build_decision_funnel_figure.py (reused via its
gate_counts()), but every label is de-jargoned: no "odds ratio", "FDR", or
"Benjamini-Hochberg" on the figure. Used by the simplified methods deck
(scripts/build_methods_simple_pptx.py). The original funnel is left untouched.

Run:  .venv/bin/python scripts/build_decision_funnel_figure_simple.py
"""
from __future__ import annotations

from pathlib import Path

import cairosvg

import build_decision_funnel_figure as funnel
from build_decision_funnel_figure import MIN_MENTIONS, PALETTE, _esc, _label

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "docs" / "statistical_test_figures"
PNG_DIR = ROOT / "docs" / "statistical_test_figures_png"
NAME = "figure_decision_rule_funnel_simple"


def build_svg(c: dict) -> str:
    width, height = 1500, 1080
    cx = width / 2
    parts: list[str] = []
    parts.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" font-family="Helvetica, Arial, sans-serif">'
    )
    parts.append(f'<rect width="{width}" height="{height}" fill="{PALETTE["bg"]}"/>')
    parts.append(f'<rect x="0" y="0" width="14" height="{height}" fill="{PALETTE["stage"]}"/>')

    parts.append(
        f'<text x="60" y="58" font-size="38" font-weight="700" '
        f'fill="{PALETTE["ink"]}">From 18 topics to nudge candidates</text>'
    )
    parts.append(
        f'<text x="60" y="92" font-size="22" fill="{PALETTE["muted"]}" '
        f"font-family=\"'Noto Sans CJK JP', sans-serif\">"
        f'18の話題から、ナッジ候補を絞り込む</text>'
    )

    # Plain-language stages: (count, en label, ja label).
    stages = [
        (c["n_models"], "Topics tested", "調べた話題"),
        (c["n_harmful"], "Linked to worse ratings", "悪い評価と結びつく"),
        (c["n_fdr"], "Pass the strict test", "厳しい基準を通過"),
        (c["n_passed"], "Mentioned enough times", "十分な回数現れた"),
    ]
    gates = [
        "Keep problems tied to low ratings",
        "Tighten the bar for testing many topics",
        f"Drop rarely-mentioned topics (seen under {MIN_MENTIONS} times)",
    ]

    top = 150
    stage_h = 78
    gap = 66
    max_w = 980
    min_w = 360
    counts = [s[0] for s in stages]
    cmax, cmin = max(counts), min(counts)

    def stage_w(n: int) -> float:
        if cmax == cmin:
            return max_w
        return min_w + (max_w - min_w) * (n - cmin) / (cmax - cmin)

    y = top
    for i, (n, en, ja) in enumerate(stages):
        w = stage_w(n)
        x = cx - w / 2
        frac = i / (len(stages) - 1)
        fill = PALETTE["stage"] if frac < 0.5 else PALETTE["stage_fade"]
        parts.append(
            f'<rect x="{x:.1f}" y="{y}" width="{w:.1f}" height="{stage_h}" rx="8" fill="{fill}"/>'
        )
        parts.append(
            f'<text x="{cx:.1f}" y="{y + 34}" font-size="34" font-weight="700" '
            f'fill="#ffffff" text-anchor="middle">{n}</text>'
        )
        parts.append(
            f'<text x="{cx:.1f}" y="{y + 62}" font-size="18" fill="#eaf1f0" '
            f'text-anchor="middle">{_esc(en)}</text>'
        )
        parts.append(
            f'<text x="{cx + max_w / 2 + 30:.1f}" y="{y + 48}" font-size="15" '
            f'fill="{PALETTE["muted"]}" text-anchor="start" '
            f"font-family=\"'Noto Sans CJK JP', sans-serif\">{_esc(ja)}</text>"
        )
        if i < len(stages) - 1:
            ay = y + stage_h
            parts.append(
                f'<line x1="{cx:.1f}" y1="{ay}" x2="{cx:.1f}" y2="{ay + gap - 14:.1f}" '
                f'stroke="{PALETTE["gate"]}" stroke-width="2"/>'
            )
            parts.append(
                f'<polygon points="{cx - 8:.1f},{ay + gap - 16:.1f} '
                f'{cx + 8:.1f},{ay + gap - 16:.1f} {cx:.1f},{ay + gap - 4:.1f}" '
                f'fill="{PALETTE["gate"]}"/>'
            )
            parts.append(
                f'<text x="{cx + 24:.1f}" y="{ay + gap / 2 - 2:.1f}" font-size="16" '
                f'fill="{PALETTE["gate"]}" text-anchor="start" font-style="italic">'
                f'{_esc(gates[i])}</text>'
            )
        y += stage_h + gap

    split_y = y + 14
    parts.append(
        f'<text x="{cx:.1f}" y="{split_y}" font-size="18" fill="{PALETTE["ink"]}" '
        f'text-anchor="middle" font-weight="700">Sort each kept topic</text>'
    )
    box_y = split_y + 26
    box_h = 168
    box_w = 600
    gapx = 40
    left_x = cx - gapx / 2 - box_w
    right_x = cx + gapx / 2

    def outcome(x: float, color: str, title_en: str, title_ja: str, codes: list[str]):
        parts.append(
            f'<rect x="{x:.1f}" y="{box_y}" width="{box_w}" height="{box_h}" rx="8" '
            f'fill="{PALETTE["bg"]}" stroke="{color}" stroke-width="3"/>'
        )
        parts.append(f'<rect x="{x:.1f}" y="{box_y}" width="{box_w}" height="6" fill="{color}"/>')
        parts.append(
            f'<text x="{x + 24:.1f}" y="{box_y + 44}" font-size="24" font-weight="700" '
            f'fill="{color}">{len(codes)} {_esc(title_en)}</text>'
        )
        parts.append(
            f'<text x="{x + 24:.1f}" y="{box_y + 70}" font-size="15" fill="{PALETTE["muted"]}" '
            f"font-family=\"'Noto Sans CJK JP', sans-serif\">{_esc(title_ja)}</text>"
        )
        names = ", ".join(_label(code) for code in codes)
        parts.append(
            f'<text x="{x + 24:.1f}" y="{box_y + 108}" font-size="18" '
            f'fill="{PALETTE["ink"]}">{_esc(names)}</text>'
        )

    outcome(left_x, PALETTE["nudge"], "Information can help", "情報で改善できる", c["nudges"])
    outcome(right_x, PALETTE["operator"], "Operator must act", "事業者の対応が必要", c["operator"])

    parts.append("</svg>")
    return "".join(parts)


def main() -> None:
    if not funnel.INPUT.exists():
        raise SystemExit(f"Missing input: {funnel.INPUT}. Run `make nudge-analysis` first.")
    c = funnel.gate_counts()
    svg = build_svg(c)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    PNG_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / f"{NAME}.svg").write_text(svg, encoding="utf-8")
    cairosvg.svg2png(bytestring=svg.encode("utf-8"), write_to=str(PNG_DIR / f"{NAME}.png"),
                     output_width=1500)
    print(f"wrote {(OUT_DIR / (NAME + '.svg')).relative_to(ROOT)} and "
          f"{(PNG_DIR / (NAME + '.png')).relative_to(ROOT)}")
    print(f"gate counts: {c}")


if __name__ == "__main__":
    main()
