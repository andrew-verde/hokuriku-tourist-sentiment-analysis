#!/usr/bin/env python3
"""Build NUDGE-Seminar-Slides.pptx - a native, editable PowerPoint of the nudge deck.

Same provenance contract as the HTML deck: every number resolves from an analysis
output file via the SAME getters. We do not re-implement getters or re-type digits.
We import scripts/build_nudge_seminar_slides.py, call deck.load(), and pull RAW values
straight off deck.DATA[...] through the deck's getter factories. If a getter raises,
the build crashes (fail-loud) rather than inventing a number. Figures are the same
script-generated SVGs, rasterized to PNG with cairosvg.

Style: school colors only (white, blue, black). Century Gothic. One section label
top-left. No em dashes. Stats-heavy methods and stats-justified results.

Run:  .venv/bin/python3 scripts/build_nudge_pptx.py
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import cairosvg
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Emu, Inches, Pt

ROOT = Path(__file__).resolve().parent.parent
OUT_PPTX = ROOT / "NUDGE-Seminar-Slides.pptx"
SCRATCH = Path(
    "/tmp/claude-1000/-home-andrewgreen-Repositories-andrew-verde-hokuriku-tourist-sentiment-analysis/"
    "10c07a34-3a17-4c5a-aa81-7faf2262a082/scratchpad"
)
SCRATCH.mkdir(parents=True, exist_ok=True)
N_SLIDES = 13


# --- import the HTML deck module and reuse its getters / SOURCES / FIGURES -----
def _load_deck():
    spec = importlib.util.spec_from_file_location(
        "nudge_deck", ROOT / "scripts/build_nudge_seminar_slides.py"
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["nudge_deck"] = mod
    spec.loader.exec_module(mod)
    mod.load()  # populate DATA / SHA
    return mod


deck = _load_deck()


# --- value resolution: RAW values come ONLY through deck getters --------------
def raw(src_id: str, getter):
    """Resolve a single raw value via a deck getter (fail-loud)."""
    return getter(deck.DATA[src_id])


_SUP = str.maketrans("-0123456789", "⁻⁰¹²³⁴⁵⁶⁷⁸⁹")


def fp(p: float) -> str:
    """'p = ...' display with unicode superscripts for small p."""
    p = float(p)
    if p < 1e-4:
        mant, exp = f"{p:.1e}".split("e")
        return f"p = {mant}×10{str(int(exp)).translate(_SUP)}"
    if p < 0.001:
        return "p < .001"
    return f"p = {p:.3f}".replace("0.", ".")


def fpv(p: float) -> str:
    """Bare p value (no 'p = ' prefix), for table cells."""
    p = float(p)
    if p < 1e-4:
        mant, exp = f"{p:.1e}".split("e")
        return f"{mant}×10{str(int(exp)).translate(_SUP)}"
    if p < 0.001:
        return "< .001"
    return f"{p:.3f}".replace("0.", ".")


def fpct1(x) -> str:
    return f"{float(x) * 100:.1f}%"


def fnum(x) -> str:
    return f"{int(round(float(x))):,}"


def f2(x) -> str:
    return f"{float(x):.2f}"


def ftext(x) -> str:
    return f"{x}"


# ---- pull EVERY displayed number through a deck getter ------------------------
# Scope / data
TOTAL_REVIEWS = fnum(raw("nudge_poi", deck.poi_total_reviews()))
N_POIS = fnum(raw("poi_mfst", deck.manifest_metric("n_pois_total")))
TAGGED_ROWS = fnum(raw("aspect_mfst", deck.manifest_metric("tagged_input_rows")))
LANG_JP = fnum(raw("aspect_mfst", deck.manifest_metric("tagged_language_group_counts", "japanese")))
LANG_EN = fnum(raw("aspect_mfst", deck.manifest_metric("tagged_language_group_counts", "english")))
LANG_CN = fnum(raw("aspect_mfst", deck.manifest_metric("tagged_language_group_counts", "chinese")))
LANG_OTHER = fnum(raw("aspect_mfst", deck.manifest_metric("tagged_language_group_counts", "other_non_english_non_japanese")))
POI_FUKUI = fnum(raw("poi_mfst", deck.manifest_metric("n_pois_by_prefecture", "Fukui")))
POI_ISHIKAWA = fnum(raw("poi_mfst", deck.manifest_metric("n_pois_by_prefecture", "Ishikawa")))
POI_TOYAMA = fnum(raw("poi_mfst", deck.manifest_metric("n_pois_by_prefecture", "Toyama")))

# Pipeline
MODEL_ROWS = fnum(raw("aspect_mfst", deck.manifest_metric("primary_model_rows")))
LOW_RATING_ROWS = fnum(raw("aspect_mfst", deck.manifest_metric("primary_low_rating_rows")))
LOW_RATING_DEF = ftext(raw("aspect_mfst", deck.manifest_top("filters", "low_rating_definition")))

# Model + guards
MODELS_PRIMARY = fnum(raw("aspect_mfst", deck.manifest_metric("A_primary_models_fit")))
MODELS_TOTAL = fnum(raw("aspect_mfst", deck.manifest_metric("total_models_fit")))
STATUS_OK = fnum(raw("aspect_mfst", deck.manifest_metric("status_counts", "ok")))
STATUS_PREV = fnum(raw("aspect_mfst", deck.manifest_metric("status_counts", "prevalence_only")))
STATUS_SKIP = fnum(raw("aspect_mfst", deck.manifest_metric("status_counts", "skipped")))
MIN_P = fp(raw("aspect_mfst", deck.manifest_metric("min_model_p_value")))
FIRTH_SANITY = f"{float(raw('aspect_mfst', deck.plain_vs_firth_max_logdiff())):.3f}"
CAVEAT_GATE = ftext(raw("aspect_mfst", deck.caveat_text(6)))


def asp(aspect, col):
    return raw("nudge_aspect", deck.aspect_value(aspect, col))


# Aspect opportunity map (prevalence, odds ratio, 95% CI, FDR p)
OPEN_PREV = fpct1(asp("opening_hours_availability", "prevalence"))
OPEN_OR = f2(asp("opening_hours_availability", "odds_ratio"))
OPEN_CIL = f2(asp("opening_hours_availability", "or_ci_low"))
OPEN_CIH = f2(asp("opening_hours_availability", "or_ci_high"))
OPEN_P = fp(asp("opening_hours_availability", "p_value_bh_fdr"))
OPEN_PV = fpv(asp("opening_hours_availability", "p_value_bh_fdr"))

TIME_PREV = fpct1(asp("itinerary_fit_time_cost", "prevalence"))
TIME_OR = f2(asp("itinerary_fit_time_cost", "odds_ratio"))
TIME_CIL = f2(asp("itinerary_fit_time_cost", "or_ci_low"))
TIME_CIH = f2(asp("itinerary_fit_time_cost", "or_ci_high"))
TIME_P = fp(asp("itinerary_fit_time_cost", "p_value_bh_fdr"))
TIME_PV = fpv(asp("itinerary_fit_time_cost", "p_value_bh_fdr"))

PRICE_PREV = fpct1(asp("price_value", "prevalence"))
PRICE_OR = f2(asp("price_value", "odds_ratio"))
PRICE_CIL = f2(asp("price_value", "or_ci_low"))
PRICE_CIH = f2(asp("price_value", "or_ci_high"))
PRICE_PV = fpv(asp("price_value", "p_value_bh_fdr"))

CLEAN_PREV = fpct1(asp("cleanliness_comfort", "prevalence"))
CLEAN_OR = f2(asp("cleanliness_comfort", "odds_ratio"))
CLEAN_CIL = f2(asp("cleanliness_comfort", "or_ci_low"))
CLEAN_CIH = f2(asp("cleanliness_comfort", "or_ci_high"))
CLEAN_PV = fpv(asp("cleanliness_comfort", "p_value_bh_fdr"))

ENG_GAP_PREV = fpct1(asp("english_information_gap", "prevalence"))
SIGN_PREV = fpct1(asp("wayfinding_signage", "prevalence"))
SIGN_OR = f2(asp("wayfinding_signage", "odds_ratio"))
SIGN_CIL = f2(asp("wayfinding_signage", "or_ci_low"))
SIGN_CIH = f2(asp("wayfinding_signage", "or_ci_high"))
SIGN_PV = fpv(asp("wayfinding_signage", "p_value_bh_fdr"))
ACCESS_PREV = fpct1(asp("transport_access", "prevalence"))
BOOKING_PREV = fpct1(asp("booking_ticketing", "prevalence"))

# Chinese-language Xiaohongshu context
CN_ROWS = fnum(raw("cn_mfst", deck.manifest_metric("denominators", "chinese_social_rows")))
CN_XHS_ROWS = fnum(raw("cn_mfst", deck.manifest_metric("denominators", "n_total_xhs_rows")))


def cnv(predictor, col):
    return raw(
        "cn_drivers",
        deck.cn_driver_value(predictor, "sentiment_category=positive", col),
    )


DINO_N = fnum(cnv("dinosaurs_museums", "group_a_n"))
DINO_POS = fnum(cnv("dinosaurs_museums", "group_a_event_count"))
DINO_PCT = fpct1(cnv("dinosaurs_museums", "group_a_event_pct"))
DINO_OTHER_PCT = fpct1(cnv("dinosaurs_museums", "group_b_event_pct"))
DINO_FDR = fp(cnv("dinosaurs_museums", "p_value_bh_fdr"))
SCENIC_N = fnum(cnv("scenic_nature", "group_a_n"))
SCENIC_POS = fnum(cnv("scenic_nature", "group_a_event_count"))
SCENIC_PCT = fpct1(cnv("scenic_nature", "group_a_event_pct"))
SCENIC_OTHER_PCT = fpct1(cnv("scenic_nature", "group_b_event_pct"))
SCENIC_FDR = fp(cnv("scenic_nature", "p_value_bh_fdr"))


def prv(rank, col):
    return raw("solution_priorities", deck.priority_value(rank, col))


PRIORITIES = [
    {
        "rank": fnum(prv(rank, "rank")),
        "name_en": ftext(prv(rank, "solution_label_en")),
        "name_ja": ftext(prv(rank, "solution_label_ja")),
        "impact": ftext(prv(rank, "impact_tier")),
        "ease": ftext(prv(rank, "ease_tier")),
        "summary_en": ftext(prv(rank, "evidence_summary_en")),
        "summary_ja": ftext(prv(rank, "evidence_summary_ja")),
        "test_en": ftext(prv(rank, "intervention_en")),
        "test_ja": ftext(prv(rank, "intervention_ja")),
    }
    for rank in (1, 2, 3)
]

# POI action map
FIX_COUNT = fnum(raw("nudge_poi", deck.poi_sum("is_fix_it")))
FIX_FUKUI = fnum(raw("nudge_poi", deck.poi_sum("is_fix_it", True)))
PROMOTE_COUNT = fnum(raw("nudge_poi", deck.poi_sum("is_promote_it")))
PROMOTE_FUKUI = fnum(raw("nudge_poi", deck.poi_sum("is_promote_it", True)))
CROWD_COUNT = fnum(raw("nudge_poi", deck.poi_sum("is_crowding_hotspot")))
LOW_VOL = fnum(raw("nudge_poi", deck.poi_metric("low_volume_threshold")))
HIGH_VOL = fnum(raw("nudge_poi", deck.poi_metric("high_volume_threshold")))
PROMO1 = ftext(raw("nudge_poi", deck.poi_ranked("promote_fukui", 0, "poi_name")))
PROMO1_SHARE = fpct1(raw("nudge_poi", deck.poi_ranked("promote_fukui", 0, "positive_share")))
PROMO1_LOW = fpct1(raw("nudge_poi", deck.poi_ranked("promote_fukui", 0, "positive_share_ci_low")))
PROMO1_HIGH = fpct1(raw("nudge_poi", deck.poi_ranked("promote_fukui", 0, "positive_share_ci_high")))
PROMO2 = ftext(raw("nudge_poi", deck.poi_ranked("promote_fukui", 1, "poi_name")))
PROMO2_SHARE = fpct1(raw("nudge_poi", deck.poi_ranked("promote_fukui", 1, "positive_share")))
PROMO2_LOW = fpct1(raw("nudge_poi", deck.poi_ranked("promote_fukui", 1, "positive_share_ci_low")))
PROMO2_HIGH = fpct1(raw("nudge_poi", deck.poi_ranked("promote_fukui", 1, "positive_share_ci_high")))

# Discussion caveats (verbatim manifest strings)
CAV0 = ftext(raw("aspect_mfst", deck.caveat_text(0)))
CAV1 = ftext(raw("aspect_mfst", deck.caveat_text(1)))
CAV3 = ftext(raw("aspect_mfst", deck.caveat_text(3)))
CAV8 = ftext(raw("aspect_mfst", deck.caveat_text(8)))


# ---- figures: rasterize each SVG in deck.FIGURES to PNG ----------------------
def rasterize(key: str) -> Path:
    svg_path = deck.FIGURES[key]
    if not svg_path.exists():
        raise SystemExit(f"missing figure: {svg_path}")
    png = SCRATCH / f"nudge_pptx_{key}.png"
    cairosvg.svg2png(url=str(svg_path), write_to=str(png), output_width=1600)
    return png


PNG = {key: rasterize(key) for key in deck.FIGURES}


# --- palette: white / blue / black only (school colors) -----------------------
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
NAVY = RGBColor(0x16, 0x34, 0x5E)   # primary: headings, labels, rules, key numbers
BLUE = RGBColor(0x2C, 0x5A, 0xB0)   # accent
INK = RGBColor(0x14, 0x18, 0x1D)    # body text
GREY = RGBColor(0x5A, 0x65, 0x73)   # secondary + Japanese text
BORDER = RGBColor(0xD3, 0xD9, 0xE2)
CARD_BG = RGBColor(0xF4, 0xF6, 0xF8)
TINT = RGBColor(0xEA, 0xF0, 0xF8)   # very light blue box (still blue family)

EN_FONT = "Century Gothic"
HEAD_FONT = "Century Gothic"
JP_FONT = "Yu Gothic"

EMU_W = Inches(13.333)
EMU_H = Inches(7.5)
MX = Inches(0.6)
CW = Inches(13.333 - 1.2)


# --- low-level helpers --------------------------------------------------------
def _set_bg(slide, color: RGBColor):
    fill = slide.background.fill
    fill.solid()
    fill.fore_color.rgb = color


def _style_run(run, size, color, bold=False, italic=False, font=EN_FONT):
    run.font.size = Pt(size)
    run.font.color.rgb = color
    run.font.bold = bold
    run.font.italic = italic
    run.font.name = font
    rPr = run._r.get_or_add_rPr()
    for tag in ("a:latin", "a:ea", "a:cs"):
        el = rPr.find(qn(tag))
        if el is None:
            el = rPr.makeelement(qn(tag), {})
            rPr.append(el)
        el.set("typeface", font)


def textbox(slide, x, y, w, h, anchor=MSO_ANCHOR.TOP):
    tb = slide.shapes.add_textbox(x, y, w, h)
    tf = tb.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    tf.margin_left = Inches(0.04)
    tf.margin_right = Inches(0.04)
    tf.margin_top = Inches(0.02)
    tf.margin_bottom = Inches(0.02)
    return tb, tf


def add_para(tf, first=False):
    p = tf.paragraphs[0] if first and not tf.paragraphs[0].runs else tf.add_paragraph()
    p.alignment = PP_ALIGN.LEFT
    return p


def en_jp(tf, en, jp, en_size=18, jp_size=14, en_color=INK, bold=False, first=False,
          space_after=10, bullet=False):
    """Add an EN paragraph then a JP paragraph directly below (lighter, JP font)."""
    pe = add_para(tf, first=first)
    pe.space_after = Pt(1)
    pe.space_before = Pt(0)
    re_ = pe.add_run()
    re_.text = ("•  " if bullet else "") + en
    _style_run(re_, en_size, en_color, bold=bold)
    pj = tf.add_paragraph()
    pj.alignment = PP_ALIGN.LEFT
    pj.space_after = Pt(space_after)
    pj.space_before = Pt(0)
    rj = pj.add_run()
    rj.text = ("　 " if bullet else "") + jp
    _style_run(rj, jp_size, GREY, font=JP_FONT)
    return pe, pj


def card(slide, x, y, w, h, bg=CARD_BG, border=BORDER):
    """Flat professional box: light fill, thin full border, even padding. No stripes."""
    sh = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, x, y, w, h)
    sh.adjustments[0] = 0.04
    sh.fill.solid()
    sh.fill.fore_color.rgb = bg
    sh.line.color.rgb = border
    sh.line.width = Pt(0.75)
    sh.shadow.inherit = False
    tf = sh.text_frame
    tf.word_wrap = True
    tf.margin_left = Inches(0.16)
    tf.margin_right = Inches(0.16)
    tf.margin_top = Inches(0.11)
    tf.margin_bottom = Inches(0.11)
    tf.vertical_anchor = MSO_ANCHOR.TOP
    tf.paragraphs[0].alignment = PP_ALIGN.LEFT
    return sh, tf


def label(slide, text):
    """Single section label, top-left, navy small-caps, letter-spaced."""
    tb, tf = textbox(slide, MX, Inches(0.4), CW, Inches(0.34))
    p = tf.paragraphs[0]
    r = p.add_run()
    r.text = text
    _style_run(r, 13, NAVY, bold=True)
    rPr = r._r.get_or_add_rPr()
    rPr.set("spc", "200")
    return tb


def title(slide, en, jp, size=32, color=NAVY, jp_size=15, y=0.84):
    tb, tf = textbox(slide, MX, Inches(y), CW, Inches(1.15))
    pe = tf.paragraphs[0]
    pe.space_after = Pt(2)
    re_ = pe.add_run()
    re_.text = en
    _style_run(re_, size, color, bold=True, font=HEAD_FONT)
    pj = tf.add_paragraph()
    pj.space_before = Pt(0)
    rj = pj.add_run()
    rj.text = jp
    _style_run(rj, jp_size, GREY, font=JP_FONT)
    return tb


def infobox(slide, x, y, w, h, en, jp, bg=TINT):
    """Light box for an honesty / guard note. No edge stripe, no warning red."""
    sh = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, x, y, w, h)
    sh.adjustments[0] = 0.06
    sh.fill.solid()
    sh.fill.fore_color.rgb = bg
    sh.line.color.rgb = BORDER
    sh.line.width = Pt(0.75)
    sh.shadow.inherit = False
    tf = sh.text_frame
    tf.word_wrap = True
    tf.margin_left = Inches(0.18)
    tf.margin_right = Inches(0.18)
    tf.margin_top = Inches(0.09)
    tf.margin_bottom = Inches(0.09)
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    en_jp(tf, en, jp, en_size=14, jp_size=11.5, en_color=NAVY, first=True, space_after=0)
    return sh


def stat_callout(slide, x, y, w, value, en_label, jp_label, vsize=42):
    _, tf = card(slide, x, y, w, Inches(1.6))
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    pv = tf.paragraphs[0]
    pv.alignment = PP_ALIGN.CENTER
    pv.space_after = Pt(2)
    rv = pv.add_run()
    rv.text = value
    _style_run(rv, vsize, NAVY, bold=True, font=HEAD_FONT)
    ple = tf.add_paragraph()
    ple.alignment = PP_ALIGN.CENTER
    ple.space_after = Pt(0)
    rle = ple.add_run()
    rle.text = en_label
    _style_run(rle, 12.5, INK, bold=True)
    plj = tf.add_paragraph()
    plj.alignment = PP_ALIGN.CENTER
    plj.space_before = Pt(0)
    rlj = plj.add_run()
    rlj.text = jp_label
    _style_run(rlj, 11, GREY, font=JP_FONT)


def caption(slide, x, y, w, en, jp):
    tb, tf = textbox(slide, x, y, w, Inches(0.75))
    pe = tf.paragraphs[0]
    pe.space_after = Pt(0)
    re_ = pe.add_run()
    re_.text = en
    _style_run(re_, 12, GREY, italic=True)
    pj = tf.add_paragraph()
    pj.space_before = Pt(0)
    rj = pj.add_run()
    rj.text = jp
    _style_run(rj, 10.5, GREY, italic=True, font=JP_FONT)


def placeholder(slide, x, y, w, h, en="image", jp="画像"):
    """Empty dashed-border box for the user to drop a photo / logo into later."""
    sh = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, x, y, w, h)
    sh.fill.solid()
    sh.fill.fore_color.rgb = RGBColor(0xFA, 0xFB, 0xFC)
    sh.line.color.rgb = RGBColor(0xB2, 0xBB, 0xC8)
    sh.line.width = Pt(1.0)
    sh.shadow.inherit = False
    ln = sh.line._get_or_add_ln()
    ln.append(ln.makeelement(qn("a:prstDash"), {"val": "dash"}))
    tf = sh.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    r = p.add_run()
    r.text = f"[ {en} ]"
    _style_run(r, 12.5, RGBColor(0x97, 0xA1, 0xAE))
    pj = tf.add_paragraph()
    pj.alignment = PP_ALIGN.CENTER
    rj = pj.add_run()
    rj.text = jp
    _style_run(rj, 10.5, RGBColor(0x97, 0xA1, 0xAE), font=JP_FONT)
    return sh


def picture_fit(slide, key, x, y, max_w, max_h):
    from PIL import Image
    png = PNG[key]
    iw, ih = Image.open(png).size
    ar = iw / ih
    box_ar = max_w / max_h
    if ar > box_ar:
        w = max_w
        h = int(max_w / ar)
    else:
        h = max_h
        w = int(max_h * ar)
    px = x + (max_w - w) // 2
    py = y + (max_h - h) // 2
    slide.shapes.add_picture(str(png), Emu(int(px)), Emu(int(py)), Emu(int(w)), Emu(int(h)))


def notes(slide, text):
    slide.notes_slide.notes_text_frame.text = text


def foot(slide, num):
    """Page number only, bottom-right, grey."""
    tb, tf = textbox(slide, Inches(11.0), Inches(7.04), Inches(1.83), Inches(0.3))
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.RIGHT
    r = p.add_run()
    r.text = f"{num} / {N_SLIDES}"
    _style_run(r, 10, GREY)


def _cell(cell, text, size, color, bold=False, align=PP_ALIGN.LEFT, fill=None,
          jp=None, font=EN_FONT):
    if fill is not None:
        cell.fill.solid()
        cell.fill.fore_color.rgb = fill
    else:
        cell.fill.solid()
        cell.fill.fore_color.rgb = WHITE
    cell.margin_left = Inches(0.07)
    cell.margin_right = Inches(0.06)
    cell.margin_top = Inches(0.03)
    cell.margin_bottom = Inches(0.03)
    cell.vertical_anchor = MSO_ANCHOR.MIDDLE
    tf = cell.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.alignment = align
    r = p.add_run()
    r.text = text
    _style_run(r, size, color, bold=bold, font=font)
    if jp:
        pj = tf.add_paragraph()
        pj.alignment = align
        rj = pj.add_run()
        rj.text = jp
        _style_run(rj, size - 3.5, GREY, font=JP_FONT)


# =============================================================================
def build():
    prs = Presentation()
    prs.slide_width = EMU_W
    prs.slide_height = EMU_H
    blank = prs.slide_layouts[6]

    def new():
        s = prs.slides.add_slide(blank)
        _set_bg(s, WHITE)
        return s

    # ---- 1 TITLE ----
    s = new()
    tb, tf = textbox(s, MX, Inches(0.9), CW, Inches(0.5))
    r = tf.paragraphs[0].add_run()
    r.text = "福井大学 ・ 竹本研 ・ 福井観光PBL"
    _style_run(r, 17, NAVY, bold=True, font=JP_FONT)
    placeholder(s, Inches(10.55), Inches(0.55), Inches(2.2), Inches(1.1), "logo", "ロゴ")
    tb, tf = textbox(s, MX, Inches(1.85), CW, Inches(1.7))
    pe = tf.paragraphs[0]
    pe.space_after = Pt(3)
    r = pe.add_run()
    r.text = "Turning Hokuriku review text into testable nudges"
    _style_run(r, 38, NAVY, bold=True, font=HEAD_FONT)
    pj = tf.add_paragraph()
    pj.space_before = Pt(2)
    rj = pj.add_run()
    rj.text = "北陸の口コミテキストを、検証可能なナッジへ"
    _style_run(rj, 18, GREY, font=JP_FONT)
    tb2, tf2 = textbox(s, MX, Inches(3.95), CW, Inches(1.1))
    en_jp(tf2,
          "An exploratory opportunity map of which review signals are nudge-able, and which sites are fix-it or promote-it.",
          "口コミに表れるシグナルのうち、どれがナッジ可能か、どのスポットが改善型か推奨型かを探索的に地図化する。",
          en_size=16, jp_size=13, en_color=INK, first=True, space_after=0)
    # presenters + date, formal, no chips
    tbp, tfp = textbox(s, MX, Inches(5.55), CW, Inches(0.9))
    pe = tfp.paragraphs[0]
    pe.space_after = Pt(2)
    r = pe.add_run()
    r.text = "Green Andrew  ・  Xu Zilin"
    _style_run(r, 18, NAVY, bold=True)
    pj = tfp.add_paragraph()
    rj = pj.add_run()
    rj.text = "2026年6月30日"
    _style_run(rj, 14, GREY, font=JP_FONT)
    # scope stat line (traced)
    sc_tb, sc_tf = textbox(s, MX, Inches(6.55), CW, Inches(0.8))
    en_jp(sc_tf,
          f"{TOTAL_REVIEWS} tagged reviews across {N_POIS} sites, three prefectures. Every figure traces to a source file ●",
          f"3県・{N_POIS}スポットの{TOTAL_REVIEWS}件のタグ付き口コミ。すべての数値はソースファイルに紐づく ●",
          en_size=12, jp_size=10.5, en_color=GREY, first=True, space_after=0)
    notes(s, "Both: Greet the audience. Andrew speaks in slow, clear English. State the one-line goal: read review "
              "text, then rank which signals are nudge-able and where to experiment next. Lynn covers the data and "
              "the Chinese-language strand. Note the provenance dot: every number is a live reference to a source file.")

    # ---- 2 INTRODUCTION ----
    s = new()
    label(s, "I.  INTRODUCTION")
    title(s, "The question", "問い")
    _, tf = textbox(s, MX, Inches(2.15), Inches(7.5), Inches(4.0))
    en_jp(tf, "Reviews carry two signals: pain points (what went wrong) and draw (what pulled visitors in).",
          "口コミは2種類のシグナルを持つ。不満(問題点)と魅力(惹きつけた点)。",
          first=True, bullet=True, space_after=18)
    en_jp(tf, "Some pain points ease with better pre-visit information. Others need an on-site operator fix.",
          "一部の不満は訪問前の情報で和らぐ。他は現地での事業者改善が必要。",
          bullet=True, space_after=18)
    en_jp(tf, "Which signals are nudge-able, and which sites are fix-it or promote-it?",
          "どのシグナルがナッジ可能で、どのスポットが改善型か推奨型か?",
          bullet=True, space_after=0)
    levers = [("Information provision", "情報提供"),
              ("Pre-commitment", "事前コミットメント"),
              ("Demand redistribution", "需要の再配分")]
    cy = Inches(2.05)
    for i, (en, jp) in enumerate(levers):
        _, ctf = card(s, Inches(8.6), cy + Inches(i * 1.3), Inches(4.0), Inches(1.12))
        ctf.vertical_anchor = MSO_ANCHOR.MIDDLE
        pe = ctf.paragraphs[0]
        pe.alignment = PP_ALIGN.CENTER
        pe.space_after = Pt(1)
        rr = pe.add_run()
        rr.text = en
        _style_run(rr, 16, NAVY, bold=True, font=HEAD_FONT)
        pjp = ctf.add_paragraph()
        pjp.alignment = PP_ALIGN.CENTER
        rjp = pjp.add_run()
        rjp.text = jp
        _style_run(rjp, 12, GREY, font=JP_FONT)
    infobox(s, MX, Inches(6.3), Inches(7.5), Inches(0.7),
            "This is an exploratory, hypothesis-generating study. It ranks candidate experiments. It does not estimate causal effects.",
            "本研究は探索的・仮説生成型である。候補となる実験を順位づけする。因果効果は推定しない。")
    foot(s, 2)
    notes(s, "Andrew: Keep it to three sentences, slowly. The pivot from last time: the question is not whether a "
              "language gap exists, but where a low-cost nudge could plausibly help. Stress the honest frame. We rank "
              "where to experiment. We do not claim any nudge works yet. This sets up Methods.")

    # ---- 3 METHODS DATA ----
    s = new()
    label(s, "II.  METHODS")
    title(s, "The corpus", "コーパス")
    _, c1 = card(s, MX, Inches(2.05), Inches(5.7), Inches(2.05))
    pe = c1.paragraphs[0]
    rr = pe.add_run()
    rr.text = "Tagged reviews"
    _style_run(rr, 16, NAVY, bold=True, font=HEAD_FONT)
    pj = c1.add_paragraph()
    rj = pj.add_run()
    rj.text = "タグ付き口コミ"
    _style_run(rj, 11.5, GREY, font=JP_FONT)
    en_jp(c1, f"{TAGGED_ROWS} rows", f"{TAGGED_ROWS} 行", en_size=17, jp_size=12, en_color=NAVY, bold=True)
    en_jp(c1, f"Japanese {LANG_JP} · English {LANG_EN} · Chinese {LANG_CN} · other {LANG_OTHER}",
          f"日本語 {LANG_JP} ・ 英語 {LANG_EN} ・ 中国語 {LANG_CN} ・ その他 {LANG_OTHER}",
          en_size=14.5, jp_size=11.5, en_color=INK, space_after=0)
    _, c2 = card(s, MX, Inches(4.3), Inches(5.7), Inches(1.95))
    pe = c2.paragraphs[0]
    rr = pe.add_run()
    rr.text = "Sites by prefecture"
    _style_run(rr, 16, NAVY, bold=True, font=HEAD_FONT)
    pj = c2.add_paragraph()
    rj = pj.add_run()
    rj.text = "県別スポット数"
    _style_run(rj, 11.5, GREY, font=JP_FONT)
    en_jp(c2, f"Fukui {POI_FUKUI} · Ishikawa {POI_ISHIKAWA} · Toyama {POI_TOYAMA}",
          f"福井 {POI_FUKUI} ・ 石川 {POI_ISHIKAWA} ・ 富山 {POI_TOYAMA}",
          en_size=15, jp_size=12)
    en_jp(c2, "Language labels describe the review language, not the reviewer's nationality.",
          "言語ラベルは口コミの言語を表し、執筆者の国籍ではない。",
          en_size=13, jp_size=10.5, en_color=GREY, space_after=0)
    picture_fit(s, "volume", Inches(6.55), Inches(2.0), Inches(6.2), Inches(3.5))
    caption(s, Inches(6.65), Inches(5.6), Inches(6.0),
            "Hokuriku supported-language rows entering the pooled low-rating model. No sentiment score is shown.",
            "北陸の統合低評価モデルに入る対応言語の行数。感情スコアは表示しない。")
    foot(s, 3)
    notes(s, f"Lynn takes this slide. Each review row is tagged with the aspects it mentions, across three Hokuriku "
              "prefectures. The 'other' bucket contains mixed-language Google reviews. It is separate from the "
              f"{CN_ROWS} Xiaohongshu posts shown later. Privacy line matters for a Japanese audience: only aggregates "
              "leave the project.")

    # ---- 4 METHODS PIPELINE ----
    s = new()
    label(s, "II.  METHODS")
    title(s, "Turning text into a tested signal", "テキストを検証可能なシグナルに変える")
    _, tf = textbox(s, MX, Inches(2.15), Inches(7.6), Inches(4.0))
    en_jp(tf, "Each review tagged for 18 aspect codes (12 pain points, 6 draw) from reviewed keyword codebooks.",
          "各口コミを18のアスペクトコード(不満12・魅力6)に、レビュー済み辞書でタグ付け。",
          first=True, bullet=True, space_after=17)
    en_jp(tf, f"Outcome: a low rating, defined as {LOW_RATING_DEF} ({LOW_RATING_ROWS} of {MODEL_ROWS} modelled rows).",
          f"結果変数:低評価。定義は {LOW_RATING_DEF}(モデル {MODEL_ROWS} 行中 {LOW_RATING_ROWS} 行)。",
          bullet=True, space_after=17)
    en_jp(tf, "Per aspect: when a review mentions it, are the odds of a low rating higher?",
          "アスペクトごと:言及があると低評価のオッズは高いか?",
          bullet=True, space_after=17)
    en_jp(tf, "Sentiment tools are never compared across languages; secondary checks stay within-language.",
          "感情ツールを言語間で比較しない。副次チェックは同一言語内のみ。",
          bullet=True, space_after=0)
    stat_callout(s, Inches(8.55), Inches(2.2), Inches(4.05), MODEL_ROWS, "modelled rows", "モデル対象行")
    stat_callout(s, Inches(8.55), Inches(4.05), Inches(4.05), LOW_RATING_ROWS, "low-rated rows", "低評価の行")
    foot(s, 4)
    notes(s, "Andrew: Slowly. The modelled outcome is a low star rating, a shared 1 to 5 scale with no sentiment tool "
              f"in the loop. {MODEL_ROWS} rows have a supported language and a rating; {LOW_RATING_ROWS} of them are "
              "low-rated. The aspect tags are the predictors. Emphasise the honesty rule. It is the methodological "
              "backbone reviewers will probe. Then hand to Lynn for the model.")

    # ---- 5 METHODS MODEL (stats-heavy) ----
    s = new()
    label(s, "II.  METHODS")
    title(s, "The statistical model", "統計モデル")
    _, tf = textbox(s, MX, Inches(2.05), Inches(7.4), Inches(4.0))
    en_jp(tf, "Model: Firth penalized logistic regression, one fit per aspect, outcome = a low rating.",
          "モデル:Firth ペナルティ付きロジスティック回帰。アスペクトごとに推定、結果は低評価。",
          first=True, bullet=True, en_size=16, jp_size=12.5, space_after=15)
    en_jp(tf, "Why Firth: rare aspect mentions make plain logistic regression unstable under separation. Firth returns finite, less-biased odds ratios. Hand-coded here.",
          "Firth の理由:言及が稀で、通常のロジスティック回帰は分離下で不安定。Firth は有限で偏りの小さいオッズ比を返す。自前実装。",
          bullet=True, en_size=16, jp_size=12.5, space_after=15)
    en_jp(tf, "Adjusted for review text length, language, and prefecture.",
          "文字数・言語・県を調整。",
          bullet=True, en_size=16, jp_size=12.5, space_after=15)
    en_jp(tf, f"Effect: an adjusted odds ratio with a Wald penalized-information 95% CI. {MODELS_PRIMARY} primary models, {MODELS_TOTAL} across segments.",
          f"効果:調整済みオッズ比と Wald ペナルティ付き95%CI。主分析 {MODELS_PRIMARY}、全体 {MODELS_TOTAL} モデル。",
          bullet=True, en_size=16, jp_size=12.5, space_after=0)
    picture_fit(s, "txtlen", Inches(8.25), Inches(2.15), Inches(4.5), Inches(2.95))
    caption(s, Inches(8.3), Inches(5.2), Inches(4.45),
            "JP/EN are the Fukui confirmatory diagnostic; Chinese (Hokuriku Google reviews) added for comparison — shortest text, least match opportunity. CJK vs Latin chars not 1:1.",
            "日本語・英語は福井の確認診断。比較のため中国語(北陸のGoogleレビュー)を追加:文字数が最短で一致機会が最小。CJKとラテン文字は同等比較不可。")
    foot(s, 5)
    notes(s, "Lynn: Do not read every number. Three ideas. One, the outcome is a low star rating, modelled with "
              "logistic regression. Two, Firth penalization keeps the odds ratio finite and stable when an aspect is "
              "rare, which is common here. Three, every model adjusts for text length, language, and prefecture, so "
              "the association is not just longer reviews matching more words. Andrew can field nesting questions.")

    # ---- 6 METHODS INFERENCE + DECISION RULE (stats-heavy) ----
    s = new()
    label(s, "II.  METHODS")
    title(s, "Inference, multiple testing, and the decision rule", "推論・多重比較・判定ルール")
    _, tf = textbox(s, MX, Inches(2.05), Inches(6.95), Inches(4.4))
    en_jp(tf, f"Multiple testing: Benjamini-Hochberg FDR across the aspect family. Smallest model {MIN_P}.",
          f"多重比較:アスペクト群で BH-FDR 補正。最小モデル {MIN_P}。",
          first=True, bullet=True, en_size=16, jp_size=12.5, space_after=16)
    en_jp(tf, "Decision rule: a non-zero opportunity score needs FDR-significant AND harmful (OR > 1). Everything else stays at zero.",
          "判定:非ゼロの機会スコアは FDR 有意かつ有害(OR > 1)が必要。それ以外はゼロ。",
          bullet=True, en_size=16, jp_size=12.5, space_after=16)
    en_jp(tf, f"Robustness: Firth and plain-logit odds ratios agree to max |Δlog| = {FIRTH_SANITY}.",
          f"頑健性:Firth と通常ロジットの OR は最大 |Δlog| = {FIRTH_SANITY} で一致。",
          bullet=True, en_size=16, jp_size=12.5, space_after=16)
    en_jp(tf, "Nudge-able = pre-visit information can ease it. Operator fix = the site must change. Only nudge-able, FDR-significant pain points qualify.",
          "ナッジ可能=訪問前情報で緩和。事業者改善=現地を変える必要。ナッジ可能かつ FDR 有意のみ候補。",
          bullet=True, en_size=16, jp_size=12.5, space_after=0)
    placeholder(s, Inches(8.05), Inches(2.05), Inches(4.55), Inches(4.25),
                "diagram or photo", "図または写真")
    foot(s, 6)
    notes(s, "Lynn: This is the integrity slide. The Benjamini-Hochberg correction controls the false discovery rate "
              "because we fit many models. The decision rule is the key: an opportunity score is forced to zero unless "
              "the pain point is both FDR-significant and harmful, so there is no cherry-picking. The robustness line "
              "shows Firth barely moves the answer versus a plain logit. Then the nudge-able versus operator split sets "
              "up Results.")

    # ---- 7 RESULTS: stat table ----
    s = new()
    label(s, "III.  RESULTS")
    title(s, "Which pain points actually predict low ratings", "どの不満が低評価を予測するか")
    _, tf = textbox(s, MX, Inches(1.9), CW, Inches(0.55))
    en_jp(tf, "Three nudge-able pain points are statistically significant after FDR correction.",
          "FDR 補正後に有意なナッジ可能の不満点は3つ。",
          first=True, en_size=15, jp_size=11.5, space_after=0)
    headers = ["Aspect", "Prev.", "OR (95% CI)", "FDR p", "Nudge-able"]
    body = [
        ("Opening hours / availability", "開館時間・営業状況", OPEN_PREV, OPEN_OR, f"{OPEN_CIL} to {OPEN_CIH}", OPEN_PV, "Yes", True),
        ("Itinerary fit / time-cost", "行程適合・所要時間", TIME_PREV, TIME_OR, f"{TIME_CIL} to {TIME_CIH}", TIME_PV, "Yes", True),
        ("Wayfinding / signage", "道案内・表示", SIGN_PREV, SIGN_OR, f"{SIGN_CIL} to {SIGN_CIH}", SIGN_PV, "Yes", True),
        ("Price / value", "価格・コスパ", PRICE_PREV, PRICE_OR, f"{PRICE_CIL} to {PRICE_CIH}", PRICE_PV, "No (operator)", False),
        ("Cleanliness / comfort", "清潔さ・快適さ", CLEAN_PREV, CLEAN_OR, f"{CLEAN_CIL} to {CLEAN_CIH}", CLEAN_PV, "No (operator)", False),
    ]
    n_rows = len(body) + 1
    tx, ty, tw, th = MX, Inches(2.7), Inches(8.05), Inches(3.0)
    gt = s.shapes.add_table(n_rows, 5, tx, ty, tw, th).table
    gt.first_row = False
    gt.horz_banding = False
    widths = [Inches(2.85), Inches(0.9), Inches(2.0), Inches(1.05), Inches(1.25)]
    for i, wv in enumerate(widths):
        gt.columns[i].width = wv
    for j, htext in enumerate(headers):
        _cell(gt.cell(0, j), htext, 12.5, WHITE, bold=True,
              align=PP_ALIGN.LEFT if j == 0 else PP_ALIGN.CENTER, fill=NAVY)
    for ri, (en, jp, prev, orv, ci, pv, nud, ok) in enumerate(body, start=1):
        rowfill = WHITE if ri % 2 else CARD_BG
        _cell(gt.cell(ri, 0), en, 12, INK, bold=True, fill=rowfill, jp=jp)
        _cell(gt.cell(ri, 1), prev, 12, INK, align=PP_ALIGN.CENTER, fill=rowfill)
        _cell(gt.cell(ri, 2), f"{orv}  ({ci})", 12, INK, align=PP_ALIGN.CENTER, fill=rowfill)
        _cell(gt.cell(ri, 3), pv, 12, INK, align=PP_ALIGN.CENTER, fill=rowfill)
        _cell(gt.cell(ri, 4), nud, 12, NAVY if ok else GREY, bold=ok, align=PP_ALIGN.CENTER, fill=rowfill)
    picture_fit(s, "nudge_aspect_fig", Inches(8.85), Inches(2.6), Inches(3.95), Inches(3.4))
    caption(s, MX, Inches(5.95), Inches(8.05),
            "OR = adjusted odds of a low rating, with a 95% interval. English-information gap, transport, and booking are not FDR-significant, so their scores stay at zero.",
            "OR は低評価の調整済みオッズ比(95%区間)。英語情報の不足・交通・予約は FDR 有意でなく、スコアはゼロ。")
    foot(s, 7)
    notes(s, "Andrew: Read the table top to bottom. Opening hours and itinerary fit are both significant after FDR "
              "and nudge-able; wayfinding/signage also clears FDR. Price and cleanliness are significant operator fixes, so they "
              "are flagged rather than nudged. The aspects not in the table, like English-information gap and transport, "
              "are present in reviews but do not clear FDR, so we hold them at zero and wait for more data.")

    # ---- 8 RESULTS: the two justified nudges ----
    s = new()
    label(s, "III.  RESULTS")
    title(s, "Three justified information nudges", "根拠のある3つの情報ナッジ")
    _, b1 = card(s, MX, Inches(2.0), Inches(7.55), Inches(2.0))
    pe = b1.paragraphs[0]
    rr = pe.add_run()
    rr.text = "Opening hours and availability"
    _style_run(rr, 16, NAVY, bold=True, font=HEAD_FONT)
    pj = b1.add_paragraph()
    rj = pj.add_run()
    rj.text = "開館時間・営業状況"
    _style_run(rj, 11.5, GREY, font=JP_FONT)
    en_jp(b1, f"Adjusted odds of a low rating {OPEN_OR}x higher (95% CI {OPEN_CIL} to {OPEN_CIH}, {OPEN_P}). Information nudge: show current hours, last entry, and closure risk before the trip.",
          f"低評価の調整済みオッズが {OPEN_OR} 倍(95%CI {OPEN_CIL}〜{OPEN_CIH}、{OPEN_P})。情報ナッジ:営業時間・最終入場・休業リスクを訪問前に提示。",
          en_size=15, jp_size=11.5, space_after=0)
    _, b2 = card(s, MX, Inches(4.15), Inches(7.55), Inches(2.05))
    pe = b2.paragraphs[0]
    rr = pe.add_run()
    rr.text = "Itinerary fit and time-cost"
    _style_run(rr, 16, NAVY, bold=True, font=HEAD_FONT)
    pj = b2.add_paragraph()
    rj = pj.add_run()
    rj.text = "行程適合・所要時間"
    _style_run(rj, 11.5, GREY, font=JP_FONT)
    en_jp(b2, f"Adjusted odds of a low rating {TIME_OR}x higher (95% CI {TIME_CIL} to {TIME_CIH}, {TIME_P}). Pre-commitment nudge: show realistic durations and route order before the itinerary locks.",
          f"低評価の調整済みオッズが {TIME_OR} 倍(95%CI {TIME_CIL}〜{TIME_CIH}、{TIME_P})。事前コミットメントのナッジ:所要時間とルート順を行程確定前に提示。",
          en_size=15, jp_size=11.5, space_after=0)
    picture_fit(s, "nudge_info_fig", Inches(8.35), Inches(2.0), Inches(4.4), Inches(4.2))
    infobox(s, MX, Inches(6.35), Inches(12.13), Inches(0.65),
            f"Wayfinding/signage also qualifies (OR {SIGN_OR}, FDR {SIGN_PV}): test clearer route cues. Price (OR {PRICE_OR}) and cleanliness (OR {CLEAN_OR}) remain operator fixes.",
            f"道案内・表示も該当(OR {SIGN_OR}、FDR {SIGN_PV}):ルート案内を検証。価格(OR {PRICE_OR})と清潔さ(OR {CLEAN_OR})は事業者側の改善。")
    foot(s, 8)
    notes(s, "Andrew: This is the justification slide. Each nudge is tied to its odds ratio, confidence interval, and "
              f"FDR p value. Opening hours: {OPEN_OR} times higher odds of a low rating, eased by showing hours and closure "
              f"risk before the trip. Itinerary fit: {TIME_OR} times higher odds, eased by showing realistic durations. "
              f"Wayfinding/signage also qualifies at OR {SIGN_OR}; test clearer route cues. "
              "Price and cleanliness are larger effects but belong to the operator, so we are honest and exclude them "
              "from the nudge set.")

    # ---- 9 RESULTS: Chinese-language Xiaohongshu context ----
    s = new()
    label(s, "III.  RESULTS")
    title(s, "A separate promotion hypothesis from Xiaohongshu", "小紅書から得た、別枠のプロモーション仮説")
    _, c1 = card(s, MX, Inches(2.0), Inches(5.7), Inches(3.15))
    pe = c1.paragraphs[0]
    rr = pe.add_run()
    rr.text = "Descriptive evidence grade"
    _style_run(rr, 16, NAVY, bold=True, font=HEAD_FONT)
    pj = c1.add_paragraph()
    rj = pj.add_run()
    rj.text = "記述的エビデンス"
    _style_run(rj, 11.5, GREY, font=JP_FONT)
    en_jp(c1, f"{CN_ROWS} Chinese-language Fukui social posts, all {CN_XHS_ROWS} from Xiaohongshu. No star-rating outcome.",
          f"福井に関する中国語 SNS 投稿 {CN_ROWS} 件。全 {CN_XHS_ROWS} 件が小紅書。星評価の結果変数はない。",
          en_size=14, jp_size=11, space_after=12)
    en_jp(c1, "SnowNLP categories are interpreted only within this source.",
          "SnowNLP の分類は、このソース内だけで解釈する。",
          en_size=13.5, jp_size=10.8, en_color=GREY, space_after=0)
    _, c2 = card(s, Inches(6.55), Inches(2.0), Inches(6.1), Inches(3.15))
    pe = c2.paragraphs[0]
    rr = pe.add_run()
    rr.text = "Signals worth testing"
    _style_run(rr, 16, NAVY, bold=True, font=HEAD_FONT)
    pj = c2.add_paragraph()
    rj = pj.add_run()
    rj.text = "検証する価値のあるシグナル"
    _style_run(rj, 11.5, GREY, font=JP_FONT)
    en_jp(c2, f"Dinosaur / museum: {DINO_POS} of {DINO_N} posts positive ({DINO_PCT}) versus {DINO_OTHER_PCT} without this tag; BH-FDR {DINO_FDR}.",
          f"恐竜・博物館:{DINO_N} 件中 {DINO_POS} 件がポジティブ({DINO_PCT})。タグなしは {DINO_OTHER_PCT}、BH-FDR {DINO_FDR}。",
          en_size=14, jp_size=11, space_after=12)
    en_jp(c2, f"Scenic nature: {SCENIC_POS} of {SCENIC_N} positive ({SCENIC_PCT}) versus {SCENIC_OTHER_PCT}; BH-FDR {SCENIC_FDR}.",
          f"自然景観:{SCENIC_N} 件中 {SCENIC_POS} 件がポジティブ({SCENIC_PCT})。タグなしは {SCENIC_OTHER_PCT}、BH-FDR {SCENIC_FDR}。",
          en_size=14, jp_size=11, space_after=0)
    infobox(s, MX, Inches(5.45), Inches(12.05), Inches(0.92),
            "Candidate nudge: A/B test a Chinese-language discovery card foregrounding dinosaur / museum and scenic-nature content. Measure clicks, saves, and itinerary intent.",
            "候補ナッジ:恐竜・博物館と自然景観を前面に出した中国語の発見カードを A/B テストし、クリック・保存・旅程への追加意向を測定する。")
    _, tf = textbox(s, MX, Inches(6.48), Inches(12.0), Inches(0.42))
    en_jp(tf, "Hypothesis-generating only: one platform, reviewed keyword tags, SnowNLP secondary sentiment, no rating model, no causal claim.",
          "仮説生成に限定:単一プラットフォーム、レビュー済みキーワードタグ、SnowNLP の副次的感情分析、星評価モデルなし、因果主張なし。",
          first=True, en_size=11.5, jp_size=9.5, en_color=GREY, space_after=0)
    foot(s, 9)
    notes(s, f"Lynn: Present this as a separate evidence stream. The {CN_ROWS} Xiaohongshu posts cannot enter the "
              "star-rating model because they have no ratings. Within Xiaohongshu, dinosaur and scenic-nature tags "
              "coincide with higher SnowNLP-positive shares after topic-family FDR correction. This supports an "
              "A/B-test candidate, not a proven effect. Do not compare SnowNLP with VADER or oseti.")

    # ---- 10 RESULTS: POI action map ----
    s = new()
    label(s, "III.  RESULTS")
    title(s, "Where to act: fix-it and promote-it sites", "どこで動くか:改善型と推奨型のスポット")
    stat_callout(s, MX, Inches(1.95), Inches(2.05), FIX_COUNT, "Fix-it sites", "改善型", vsize=36)
    stat_callout(s, Inches(2.78), Inches(1.95), Inches(2.05), PROMOTE_COUNT, "Promote-it sites", "推奨型", vsize=36)
    stat_callout(s, Inches(4.96), Inches(1.95), Inches(2.05), CROWD_COUNT, "Crowding hotspots", "混雑ホット", vsize=36)
    _, tf = textbox(s, MX, Inches(3.85), Inches(6.5), Inches(3.0))
    en_jp(tf, f"Fix-it: {FIX_COUNT} ({FIX_FUKUI} Fukui), high pain-point lift. Promote-it: {PROMOTE_COUNT} ({PROMOTE_FUKUI} Fukui), high positive share.",
          f"改善型 {FIX_COUNT}(福井 {FIX_FUKUI})、不満点上振れ。推奨型 {PROMOTE_COUNT}(福井 {PROMOTE_FUKUI})、高い肯定割合。",
          first=True, en_size=14.5, jp_size=11.5, space_after=14)
    en_jp(tf, f"Volume gates confidence: thin under {LOW_VOL} reviews, high-volume over {HIGH_VOL}.",
          f"件数で信頼度を判断:{LOW_VOL} 件未満は少数、{HIGH_VOL} 件超は多数。",
          en_size=14.5, jp_size=11.5, en_color=GREY, space_after=14)
    en_jp(tf, f"Top Fukui promote-it: {PROMO1} {PROMO1_SHARE} (Wilson 95% CI {PROMO1_LOW} to {PROMO1_HIGH}); then {PROMO2} {PROMO2_SHARE} ({PROMO2_LOW} to {PROMO2_HIGH}).",
          f"福井の推奨型トップ:{PROMO1} {PROMO1_SHARE}(Wilson 95%CI {PROMO1_LOW}〜{PROMO1_HIGH});次に {PROMO2} {PROMO2_SHARE}({PROMO2_LOW}〜{PROMO2_HIGH})。",
          en_size=14, jp_size=11, space_after=0)
    picture_fit(s, "nudge_poi_fig", Inches(7.15), Inches(1.95), Inches(5.5), Inches(4.9))
    foot(s, 10)
    notes(s, "Lynn: Your slide. Three archetypes from the POI index. Fix-it sites are busy with fixable pain points. "
              "Promote-it sites have high satisfaction but low volume, the demand-redistribution targets. Crowding "
              "hotspots are where you would redirect demand away from. Read the two top Fukui promote-it sites with "
              "their Wilson intervals, and note the small-sample uncertainty honestly. Positive share is computed from "
              "Google star ratings, so thin sites are not over-read.")

    # ---- 11 RESULTS: FINAL CROSS-LANGUAGE PRIORITIES ----
    s = new()
    label(s, "III.  RESULTS")
    title(s, "Rank common nudges by impact, then ease",
          "共通ナッジをインパクト、次に実装容易性で順位づける")
    _, tf = textbox(s, MX, Inches(1.82), CW, Inches(0.55))
    en_jp(tf,
          "Each solution has reviewed support from English, Japanese, and Chinese-language sources. Evidence types remain separate.",
          "各施策には英語・日本語・中国語ソースのレビュー済みエビデンスがある。エビデンス種別は統合しない。",
          first=True, en_size=13.5, jp_size=10.5, en_color=GREY, space_after=0)
    gt = s.shapes.add_table(4, 4, MX, Inches(2.48), Inches(12.05), Inches(3.92)).table
    widths = [Inches(0.75), Inches(2.55), Inches(4.35), Inches(4.4)]
    for i, width in enumerate(widths):
        gt.columns[i].width = width
    headers = [
        ("Rank", "順位"),
        ("Common solution", "共通施策"),
        ("Evidence and ease", "エビデンスと実装容易性"),
        ("Next-semester test", "来学期の実験"),
    ]
    for j, (en, jp) in enumerate(headers):
        _cell(gt.cell(0, j), en, 11.5, WHITE, bold=True, align=PP_ALIGN.CENTER, fill=NAVY, jp=jp)
    for row_index, priority in enumerate(PRIORITIES, start=1):
        row_fill = WHITE if row_index % 2 else CARD_BG
        _cell(gt.cell(row_index, 0), priority["rank"], 16, NAVY, bold=True,
              align=PP_ALIGN.CENTER, fill=row_fill)
        _cell(gt.cell(row_index, 1), priority["name_en"], 11.5, INK, bold=True,
              fill=row_fill, jp=priority["name_ja"])
        _cell(
            gt.cell(row_index, 2),
            f"{priority['impact']} impact, {priority['ease']}\n{priority['summary_en']}",
            10.5,
            INK,
            fill=row_fill,
            jp=f"インパクト {priority['impact']}・実装容易性 {priority['ease']}\n{priority['summary_ja']}",
        )
        _cell(gt.cell(row_index, 3), priority["test_en"], 10.5, INK,
              fill=row_fill, jp=priority["test_ja"])
    infobox(
        s, MX, Inches(6.55), Inches(12.05), Inches(0.52),
        "Ordinal opportunity ranking, not causal effectiveness. Impact tier first; implementation ease breaks ties.",
        "因果的効果ではなく機会ランキング。インパクト層を優先し、同じ層では実装容易性で順位づける。",
    )
    foot(s, 11)
    notes(s, "Both: This is the decision slide. Read only the first row in detail. Each solution has reviewed "
              "support from English, Japanese, and Chinese-language sources, although evidence types differ. "
              "Priority one comes first because it combines high-impact evidence with the easiest prototype. "
              "The experiment register carries these exact ranks into next semester.")

    # ---- 12 DISCUSSION ----
    s = new()
    label(s, "IV.  DISCUSSION")
    title(s, "What this can and cannot claim", "主張できること・できないこと")
    cavs = [
        (CAV0, "探索的・仮説生成型であり、因果関係ではない。"),
        (CAV1, "機会スコアは候補となる追跡実験を順位づけるものであり、介入効果ではない。"),
        (CAV3, "POI レベルのクラスタリングは Firth では未モデル化。行レベル推定は POI 入れ子の不確実性を過小評価しうる。"),
        (CAV8, "言語グループは口コミの言語を表し、執筆者の国籍ではない。"),
    ]
    _, tf = textbox(s, MX, Inches(2.05), Inches(7.75), Inches(4.0))
    for i, (en, jp) in enumerate(cavs):
        en_jp(tf, en, jp, first=(i == 0), bullet=True, en_size=15.5, jp_size=12, space_after=15)
    placeholder(s, Inches(8.75), Inches(2.05), Inches(3.88), Inches(3.55), "photo", "写真")
    infobox(s, MX, Inches(6.25), Inches(12.13), Inches(0.7),
            "Every caveat here is quoted from the analysis manifest, not paraphrased on the slide.",
            "ここに挙げた注意点はすべて分析マニフェストからの引用であり、スライド上で言い換えていない。")
    foot(s, 12)
    notes(s, "Andrew: Slowly. This is the intellectual honesty slide. Each bullet is the verbatim caveat string from "
              "the manifest, so the limitations we present are exactly the ones the analysis itself records. The four: "
              "not causal, ranks experiments rather than effects, POI clustering unmodelled, and language is not "
              "nationality. These limits are why the ranked solutions become randomized experiments next semester. "
              "Pause here.")

    # ---- 13 FUTURE WORK (close, white) ----
    s = new()
    label(s, "IV.  DISCUSSION")
    title(s, "From ranking to experiments", "順位づけから実験へ")
    _, c1 = card(s, MX, Inches(2.1), Inches(6.0), Inches(2.55))
    pe = c1.paragraphs[0]
    rr = pe.add_run()
    rr.text = "Experiment register"
    _style_run(rr, 17, NAVY, bold=True, font=HEAD_FONT)
    pj = c1.add_paragraph()
    rj = pj.add_run()
    rj.text = "実験レジスター"
    _style_run(rj, 11.5, GREY, font=JP_FONT)
    en_jp(c1, "The experiment register turns the top-ranked opportunities into A/B-testable nudges. It records hypothesis, metric, and target site for each.",
          "実験レジスターは上位の機会を A/B テスト可能なナッジに変える。各項目について仮説・指標・対象スポットを記録する。",
          en_size=13.5, jp_size=11, space_after=4)
    pe = c1.add_paragraph()
    rr = pe.add_run()
    rr.text = "docs/nudge_experiment_register.html"
    _style_run(rr, 11, BLUE, font="Consolas")
    _, c2 = card(s, Inches(6.95), Inches(2.1), Inches(5.7), Inches(2.55))
    pe = c2.paragraphs[0]
    rr = pe.add_run()
    rr.text = "First experiment"
    _style_run(rr, 17, NAVY, bold=True, font=HEAD_FONT)
    pj = c2.add_paragraph()
    rj = pj.add_run()
    rj.text = "最初の実験"
    _style_run(rj, 11.5, GREY, font=JP_FONT)
    en_jp(c2, f"Begin with priority {PRIORITIES[0]['rank']}: {PRIORITIES[0]['name_en']}. Randomize exposure, log interactions, then estimate behavior change.",
          f"優先順位 {PRIORITIES[0]['rank']} の「{PRIORITIES[0]['name_ja']}」から開始。提示を無作為化し、反応を記録して行動変化を推定する。",
          en_size=13.5, jp_size=11, space_after=0)
    cl_tb, cl_tf = textbox(s, MX, Inches(5.2), CW, Inches(1.3))
    pe = cl_tf.paragraphs[0]
    pe.space_after = Pt(3)
    rr = pe.add_run()
    rr.text = "This deck ranks where to run the next experiment. The register records how to run it."
    _style_run(rr, 17, NAVY, bold=True, font=HEAD_FONT)
    pj = cl_tf.add_paragraph()
    rj = pj.add_run()
    rj.text = "このデッキは次の実験をどこで行うかを順位づけする。レジスターはどのように行うかを記録する。"
    _style_run(rj, 13, GREY, font=JP_FONT)
    pe2 = cl_tf.add_paragraph()
    pe2.space_before = Pt(8)
    rr = pe2.add_run()
    rr.text = "Thank you.  ありがとうございました。"
    _style_run(rr, 15, NAVY, bold=True, font=JP_FONT)
    foot(s, 13)
    notes(s, f"Both: Lynn delivers the register hand-off. Next semester begins with priority "
              f"{PRIORITIES[0]['rank']}, {PRIORITIES[0]['name_en']}, randomized by visitor session with exposure "
              "and interaction logging. Andrew closes slowly: this deck ranks where to experiment, the register "
              "records how. Then invite questions.")

    prs.save(str(OUT_PPTX))
    return prs


def main() -> int:
    build()
    size = OUT_PPTX.stat().st_size
    print(f"wrote {OUT_PPTX} ({size:,} bytes); {N_SLIDES} slides; figures rasterized: {list(PNG)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
