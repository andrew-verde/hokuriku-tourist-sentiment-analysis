#!/usr/bin/env python3
"""Build NUDGE-Intro-Simple.pptx: a plain, read-along replacement for the
INTRODUCTION, to be hand-inserted into the live Google Drive deck.

Splits the single overloaded "Research question" slide into TWO slides:
  Slide 2  - the actual research question (the WHAT), big and self-reading.
  Slide 3  - "Our approach: small nudges" (the HOW), the levers + caveat.

Audience = Japanese viewers with limited English: every line is a full EN
sentence the presenter can read off, with a complete plain JP subtitle, so the
talk needs minimal extra explanation. Reuses scripts/build_nudge_pptx.py for
styling helpers, brand colors, and provenance-resolved constants (TAGGED_ROWS,
N_POIS). Nothing in the existing generation is modified.

Run:  .venv/bin/python3 scripts/build_intro_simple_pptx.py
"""
from __future__ import annotations

from pathlib import Path

from pptx import Presentation
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Inches, Pt

import build_nudge_pptx as bp

ROOT = Path(__file__).resolve().parent.parent
OUT_PPTX = ROOT / "NUDGE-Intro-Simple.pptx"

# Splitting one intro slide into two grows the merged deck from 12 to 13.
DECK_TOTAL = 13


def foot(slide, num: int):
    tb, tf = bp.textbox(slide, Inches(11.0), Inches(7.04), Inches(1.83), Inches(0.3))
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.RIGHT
    r = p.add_run()
    r.text = f"{num} / {DECK_TOTAL}"
    bp._style_run(r, 10, bp.GREY)


def _centered(tf, runs):
    """runs = list of (text, size, color, font, bold, space_after_pt)."""
    for i, (text, size, color, font, bold, sa) in enumerate(runs):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = PP_ALIGN.CENTER
        p.space_after = Pt(sa)
        r = p.add_run()
        r.text = text
        bp._style_run(r, size, color, bold=bold, font=font)


def build():
    prs = Presentation()
    prs.slide_width = bp.EMU_W
    prs.slide_height = bp.EMU_H
    blank = prs.slide_layouts[6]

    def new():
        s = prs.slides.add_slide(blank)
        bp._set_bg(s, bp.WHITE)
        return s

    # ===== SLIDE 2: the actual research question (WHAT) ======================
    s = new()
    bp.label(s, "I.  INTRODUCTION")
    bp.title(s, "Our research question", "私たちの研究の問い")

    _, q = bp.textbox(s, bp.MX, Inches(1.95), bp.CW, Inches(1.4))
    bp.en_jp(
        q,
        "What do tourist reviews tell us about how to improve Hokuriku tourism?",
        "口コミは、北陸の観光をどう良くできるかを教えてくれるか?",
        en_size=26, jp_size=16, en_color=bp.NAVY, bold=True, first=True, space_after=0,
    )

    subs = [
        ("Which problems lower ratings?", "どの問題が評価を下げるか?", "→ fix it  改善", bp.NAVY),
        ("Which good places get too few visitors?", "良い場所で、来訪が少ないのはどこか?",
         "→ promote it  推奨", bp.BLUE),
    ]
    cw, gap = Inches(6.0), Inches(0.33)
    xs = [bp.MX, bp.MX + cw + gap]
    for (en, jp, tag, accent), x in zip(subs, xs):
        _, c = bp.card(s, x, Inches(3.65), cw, Inches(1.95))
        c.vertical_anchor = MSO_ANCHOR.MIDDLE
        _centered(c, [
            (en, 19, bp.NAVY, bp.HEAD_FONT, True, 2),
            (jp, 12.5, bp.GREY, bp.JP_FONT, False, 8),
            (tag, 15, accent, bp.HEAD_FONT, True, 0),
        ])

    _, b = bp.textbox(s, bp.MX, Inches(5.95), bp.CW, Inches(0.6))
    bp.en_jp(
        b,
        f"We read {bp.TAGGED_ROWS} reviews from {bp.N_POIS} Hokuriku sites to answer this.",
        f"北陸{bp.N_POIS}スポットの口コミ{bp.TAGGED_ROWS}件で、これに答える。",
        en_size=15, jp_size=11.5, en_color=bp.GREY, first=True, space_after=0,
    )
    bp.notes(s,
             "Andrew (20 sec): Our question is simple. What do tourist reviews tell us about how to improve "
             "Hokuriku tourism? It has two parts: which problems lower ratings, so we can fix them; and which "
             f"good places get too few visitors, so we can promote them. We read {bp.TAGGED_ROWS} reviews from "
             f"{bp.N_POIS} Hokuriku sites to answer this.")
    foot(s, 2)

    # ===== SLIDE 3: our approach (HOW) =======================================
    s = new()
    bp.label(s, "I.  INTRODUCTION")
    bp.title(s, "Our approach: small nudges", "私たちの方法:小さなナッジ")

    _, tf = bp.textbox(s, bp.MX, Inches(2.15), Inches(7.4), Inches(3.7))
    bp.en_jp(tf, "Reviews show pain points and reasons to visit.",
             "口コミは、不満点と訪問の理由を示す。",
             first=True, bullet=True, en_size=17, jp_size=12, space_after=16)
    bp.en_jp(tf, "Some pain points shrink with better information before the trip.",
             "一部の不満は、旅行前の分かりやすい情報で減る。",
             bullet=True, en_size=17, jp_size=12, space_after=16)
    bp.en_jp(tf, "We rank low-cost ideas (nudges) to test next.",
             "次に検証する、低コストの案(ナッジ)を順位づける。",
             bullet=True, en_size=17, jp_size=12, space_after=0)

    levers = [
        ("Information provision", "情報提供",
         "Give clear info before the visit", "訪問前に分かりやすい情報を渡す"),
        ("Demand redistribution", "需要の再配分",
         "Guide visitors to quieter good places", "空いている良い場所へ誘導する"),
    ]
    for i, (en, jp, sub_en, sub_jp) in enumerate(levers):
        _, c = bp.card(s, Inches(8.55), Inches(2.2) + Inches(i * 1.75), Inches(4.18), Inches(1.55))
        c.vertical_anchor = MSO_ANCHOR.MIDDLE
        _centered(c, [
            (en, 16, bp.NAVY, bp.HEAD_FONT, True, 1),
            (jp, 11.5, bp.GREY, bp.JP_FONT, False, 6),
            (sub_en, 11.5, bp.INK, bp.EN_FONT, False, 1),
            (sub_jp, 10, bp.GREY, bp.JP_FONT, False, 0),
        ])

    bp.infobox(
        s, bp.MX, Inches(6.25), Inches(7.4), Inches(0.7),
        "Exploratory study: it finds experiments to test, not proof of cause and effect.",
        "探索的研究:検証する実験を見つけるもので、因果関係の証明ではない。",
    )
    bp.notes(s,
             "Andrew (30 sec): Reviews show two things - pain points, and reasons people visit. Some pain points "
             "can shrink with clearer information before the trip; that is an information nudge. Others, like "
             "crowding, we address by guiding visitors toward quieter good places. We rank these low-cost ideas "
             "to test next. This is exploratory: it finds experiments to test, not proof of cause and effect.")
    foot(s, 3)

    prs.save(str(OUT_PPTX))
    return prs


def main() -> int:
    build()
    n = len(Presentation(str(OUT_PPTX)).slides)
    print(f"wrote {OUT_PPTX} ({OUT_PPTX.stat().st_size:,} bytes); {n} slides "
          f"(splits live slide 2 into research-question + approach; deck total -> {DECK_TOTAL})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
