#!/usr/bin/env python3
"""Render the methods decision-rule funnel for slide 6 from the live aspect map.

The gating chain on slide 6 ("harmful association -> FDR significance -> >=20
pooled mentions -> classify as information nudge or operator fix") is turned into
a funnel whose stage counts are computed live from
output/nudge_analysis/aspect_opportunity_map.csv (A_primary pooled). No count is
hand-typed.

Run:  .venv/bin/python scripts/build_decision_funnel_figure.py
"""
from __future__ import annotations

from pathlib import Path

import cairosvg
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "output" / "nudge_analysis" / "aspect_opportunity_map.csv"
OUT_DIR = ROOT / "docs" / "statistical_test_figures"
PNG_DIR = ROOT / "docs" / "statistical_test_figures_png"

PALETTE = {
    "ink": "#172033",
    "muted": "#5b677a",
    "line": "#d7dde8",
    "bg": "#fbfaf7",
    "stage": "#2f6f73",
    "stage_fade": "#5b8d8f",
    "nudge": "#2f6f73",
    "operator": "#c06c38",
    "gate": "#33414f",
}

# Same fixed nudge-able friction set the analysis uses (info levers visitors can
# be nudged on, vs. aspects that need an operator change).
NUDGEABLE = {
    "english_information_gap",
    "wayfinding_signage",
    "transport_access",
    "booking_ticketing",
    "opening_hours_availability",
    "itinerary_fit_time_cost",
}
LABELS = {
    "opening_hours_availability": "Opening hours",
    "itinerary_fit_time_cost": "Itinerary fit",
    "wayfinding_signage": "Wayfinding",
    "price_value": "Price",
    "cleanliness_comfort": "Cleanliness",
    "accessibility_mobility": "Accessibility",
    "waiting_crowding": "Crowding",
    "staff_communication": "Staff communication",
}
MIN_MENTIONS = 20


def _esc(t: str) -> str:
    return str(t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _label(code: str) -> str:
    return LABELS.get(code, code.replace("_", " "))


def gate_counts() -> dict:
    d = pd.read_csv(INPUT)
    p = d[(d["analysis"] == "A_primary") & (d["segment"] == "pooled")].copy()
    friction = p[p["signal_type"] == "friction"]
    harmful = friction[friction["odds_ratio"] > 1]
    fdr = harmful[harmful["fdr_significant"] == True]  # noqa: E712
    passed = fdr[fdr["n_positive"] >= MIN_MENTIONS]
    nudges = sorted(passed[passed["aspect"].isin(NUDGEABLE)]["aspect"])
    operator = sorted(passed[~passed["aspect"].isin(NUDGEABLE)]["aspect"])
    return {
        "n_models": int(len(p)),
        "n_harmful": int(len(harmful)),
        "n_fdr": int(len(fdr)),
        "n_passed": int(len(passed)),
        "nudges": nudges,
        "operator": operator,
    }


def build_svg(c: dict) -> str:
    width, height = 1500, 1080
    cx = width / 2
    parts: list[str] = []
    parts.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" '
        f'font-family="Helvetica, Arial, sans-serif">'
    )
    parts.append(f'<rect width="{width}" height="{height}" fill="{PALETTE["bg"]}"/>')
    parts.append(f'<rect x="0" y="0" width="14" height="{height}" fill="{PALETTE["stage"]}"/>')

    # Title.
    parts.append(
        f'<text x="60" y="58" font-size="38" font-weight="700" '
        f'fill="{PALETTE["ink"]}">From 18 aspects to nudge candidates</text>'
    )
    parts.append(
        f'<text x="60" y="92" font-size="22" fill="{PALETTE["muted"]}" '
        f"font-family=\"'Noto Sans CJK JP', sans-serif\">"
        f'18の項目から、ナッジ候補を絞り込む決定ルール</text>'
    )

    # Funnel stages: (count, en label, ja label).
    stages = [
        (c["n_models"], "Aspect models tested", "検証した項目モデル"),
        (c["n_harmful"], "Harmful association (odds ratio > 1)", "有害な関連(オッズ比 > 1)"),
        (c["n_fdr"], "FDR-significant (Benjamini-Hochberg)", "FDR有意(BH補正)"),
        (c["n_passed"], f"≥ {MIN_MENTIONS} pooled mentions", f"統合データで {MIN_MENTIONS}件以上の言及"),
    ]
    # Gate captions sit on the arrows between stages.
    gates = [
        "Keep pain-point aspects with a low-rating risk",
        "Correct p-values across all tests",
        f"Drop rare aspects (e.g. staff communication, n < {MIN_MENTIONS})",
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
        # Blend stage color from deep teal to a lighter teal down the funnel.
        fill = PALETTE["stage"] if frac < 0.5 else PALETTE["stage_fade"]
        parts.append(
            f'<rect x="{x:.1f}" y="{y}" width="{w:.1f}" height="{stage_h}" rx="8" '
            f'fill="{fill}"/>'
        )
        parts.append(
            f'<text x="{cx:.1f}" y="{y + 34}" font-size="34" font-weight="700" '
            f'fill="#ffffff" text-anchor="middle">{n}</text>'
        )
        parts.append(
            f'<text x="{cx:.1f}" y="{y + 62}" font-size="18" fill="#eaf1f0" '
            f'text-anchor="middle">{_esc(en)}</text>'
        )
        # Japanese stage label to the right of the funnel.
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

    # Classification split into two outcome boxes.
    split_y = y + 14
    parts.append(
        f'<text x="{cx:.1f}" y="{split_y}" font-size="18" fill="{PALETTE["ink"]}" '
        f'text-anchor="middle" font-weight="700">Classify each survivor</text>'
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

    outcome(left_x, PALETTE["nudge"], "Information nudges", "情報ナッジ", c["nudges"])
    outcome(right_x, PALETTE["operator"], "Operator fixes", "事業者による改善", c["operator"])

    parts.append("</svg>")
    return "".join(parts)


def main() -> None:
    if not INPUT.exists():
        raise SystemExit(f"Missing input: {INPUT}. Run `make nudge-analysis` first.")
    c = gate_counts()
    svg = build_svg(c)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    PNG_DIR.mkdir(parents=True, exist_ok=True)
    name = "figure_decision_rule_funnel"
    (OUT_DIR / f"{name}.svg").write_text(svg, encoding="utf-8")
    cairosvg.svg2png(bytestring=svg.encode("utf-8"), write_to=str(PNG_DIR / f"{name}.png"),
                     output_width=1500)
    print(f"wrote {(OUT_DIR / (name + '.svg')).relative_to(ROOT)} and "
          f"{(PNG_DIR / (name + '.png')).relative_to(ROOT)}")
    print(f"gate counts: {c}")


if __name__ == "__main__":
    main()
