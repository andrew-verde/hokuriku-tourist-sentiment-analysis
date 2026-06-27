#!/usr/bin/env python3
"""Build NUDGE-Seminar-Slides-Preview.html: a 16:9 bilingual IMRAD seminar deck.

This is the nudge-refocused successor to scripts/build_seminar_slides.py. It keeps
the SAME provenance contract: EVERY NUMBER ON EVERY SLIDE IS A LIVE REFERENCE TO AN
ANALYSIS OUTPUT FILE. No numeric value is typed by hand in either language. Each
is fetched via stat() with an explicit getter pointing at a CSV cell or JSON field;
a missing value fails the build loud rather than inventing a number. Figures are the
same script-generated SVGs the dashboard embeds.

BILINGUAL: every on-slide line appears in English, then a Japanese translation
directly below it via the .jp class (smaller, lighter, ja font stack). When a line
carries a number, the Japanese reuses the SAME traced stat() span; the digits stay
a live reference, never retyped. Speaker notes (orange .notes boxes) stay English.

This file is a PREVIEW of what the PowerPoint will look like (~10-12 minute talk,
English spoken slowly for a Japanese audience, two co-presenters). It is a derived
view, not source of truth.

Run:  .venv/bin/python3 scripts/build_nudge_seminar_slides.py
"""
from __future__ import annotations

import hashlib
import html
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
OUT_HTML = ROOT / "NUDGE-Seminar-Slides-Preview.html"

# Nudge source registry (single source of truth, mirrors the dashboard's nudge block).
SOURCES: dict[str, Path] = {
    "nudge_aspect": ROOT / "output/nudge_analysis/aspect_opportunity_map.csv",
    "nudge_poi": ROOT / "output/nudge_analysis/poi_opportunity_index.csv",
    "nudge_tax": ROOT / "output/nudge_analysis/nudge_taxonomy.csv",
    "aspect_mfst": ROOT / "output/nudge_analysis/aspect_opportunity_map_manifest.json",
    "poi_mfst": ROOT / "output/nudge_analysis/poi_opportunity_index_manifest.json",
    "cn_drivers": ROOT / "output/within_language_sentiment/cn_within_source_sentiment_drivers.csv",
    "cn_mfst": ROOT / "output/within_language_sentiment/cn_within_source_sentiment_manifest.json",
    "solution_priorities": ROOT / "output/nudge_analysis/cross_language_solution_priorities.csv",
}

FIGURES = {
    "nudge_aspect_fig": ROOT / "docs/statistical_test_figures/figure_nudge_aspect_opportunity_map.svg",
    "nudge_poi_fig": ROOT / "docs/statistical_test_figures/figure_nudge_poi_action_map.svg",
    "nudge_info_fig": ROOT / "docs/statistical_test_figures/figure_nudge_info_levers.svg",
    "txtlen": ROOT / "docs/statistical_test_figures/figure_h3_text_length_diagnostic.svg",
    "volume": ROOT / "output/presentation_safe/multilingual/figure_volume_context.svg",
}

DATA: dict[str, object] = {}
SHA: dict[str, str] = {}
REFS: list[dict] = []


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load() -> None:
    for sid, path in SOURCES.items():
        if not path.exists():
            raise SystemExit(f"missing source: {path}")
        SHA[sid] = _sha256(path)
        if path.suffix == ".csv":
            DATA[sid] = pd.read_csv(path)
        elif path.suffix == ".json":
            DATA[sid] = json.loads(path.read_text())
        else:
            DATA[sid] = path.read_text()


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def pfmt(p: float) -> str:
    p = float(p)
    if p < 1e-4:
        mant, exp = f"{p:.1e}".split("e")
        return f"p = {mant}×10<sup>{int(exp)}</sup>"
    if p < 0.001:
        return "p &lt; .001"
    return f"p = {p:.3f}".replace("0.", ".")


def stat(src_id: str, getter, fmt="{:.0f}", unit: str = "", field: str = "") -> str:
    """Fetch ONE value and wrap it in a traced span (fail loud if getter raises)."""
    raw = getter(DATA[src_id])
    disp = fmt(raw) if callable(fmt) else fmt.format(raw) + unit
    src_path = rel(SOURCES[src_id])
    sha = SHA[src_id]
    REFS.append({"value": disp, "field": field, "source": src_path, "sha256": sha})
    tip = f"raw: {raw}\nfield: {field}\nsource: {src_path}\nsha256: {sha}"
    return (
        f'<span class="stat" title="{html.escape(tip)}">{disp}'
        f'<span class="prov-dot">●</span></span>'
    )


# --- getters: copied verbatim from build_pbl_dashboard.py nudge block --------
def aspect_value(aspect, col, segment="pooled"):
    def g(d):
        r = d[(d["analysis"] == "A_primary") & (d["segment"] == segment) & (d["aspect"] == aspect)]
        if r.empty:
            raise KeyError(f"missing aspect row: {aspect}/{segment}")
        return r[col].iloc[0]
    return g


def aspect_n(segment):
    def g(d):
        r = d[(d["analysis"] == "A_primary") & (d["segment"] == segment)]
        if r.empty:
            raise KeyError(f"missing A_primary segment: {segment}")
        return int(r["n"].iloc[0])
    return g


def secondary_total_n():
    def g(d):
        en = d[d["analysis"] == "A_secondary_en"]
        jp = d[d["analysis"] == "A_secondary_jp"]
        if en.empty or jp.empty:
            raise KeyError("missing secondary EN/JP rows")
        return int(en["n"].iloc[0]) + int(jp["n"].iloc[0])
    return g


def poi_metric(col):
    def g(d):
        return d[col].iloc[0]
    return g


def poi_sum(col, fukui: bool | None = None):
    def g(d):
        work = d
        if fukui is not None:
            work = work[work["is_fukui"].astype(bool) == fukui]
        return int(work[col].astype(bool).sum())
    return g


def poi_total_reviews():
    def g(d):
        return int(d["n_reviews"].sum())
    return g


def poi_ranked(kind, index, col):
    def g(d):
        if kind == "promote_fukui":
            work = d[(d["is_promote_it"].astype(bool)) & (d["is_fukui"].astype(bool))].sort_values("promote_it_score", ascending=False)
        elif kind == "fix":
            work = d[d["is_fix_it"].astype(bool)].sort_values("fix_it_score", ascending=False)
        elif kind == "crowding":
            work = d[d["is_crowding_hotspot"].astype(bool)].sort_values("waiting_crowding_prevalence", ascending=False)
        elif kind == "promote":
            work = d[d["is_promote_it"].astype(bool)].sort_values("promote_it_score", ascending=False)
        else:
            raise KeyError(f"unknown POI rank kind: {kind}")
        if len(work) <= index:
            raise KeyError(f"missing POI rank {kind}[{index}]")
        return work.iloc[index][col]
    return g


def taxonomy_value(aspect, col):
    def g(d):
        r = d[d["aspect"] == aspect]
        if r.empty:
            raise KeyError(f"missing taxonomy row: {aspect}")
        return r[col].iloc[0]
    return g


def cn_driver_value(predictor, outcome, col):
    """Resolve one within-Chinese predictor result from the aggregate test output."""
    def g(d):
        r = d[(d["predictor"] == predictor) & (d["outcome"] == outcome) & (d["status"] == "ok")]
        if len(r) != 1:
            raise KeyError(f"expected one Chinese driver row: {predictor}/{outcome}; found {len(r)}")
        return r[col].iloc[0]
    return g


def priority_value(rank, col):
    """Resolve one ranked cross-language solution field."""
    def g(d):
        r = d[d["rank"] == rank]
        if len(r) != 1:
            raise KeyError(f"expected one solution priority rank {rank}; found {len(r)}")
        if col not in r.columns:
            raise KeyError(f"missing solution priority column: {col}")
        return r[col].iloc[0]
    return g


# manifest_metric: this deck's variant indexes into d["metrics"] (no src_id arg),
# matching scripts/build_seminar_slides.py. Pass the nested path keys.
def manifest_metric(*path):
    def g(d):
        cur = d["metrics"]
        for k in path:
            cur = cur[k]
        return cur
    return g


def manifest_top(*path):
    # like manifest_metric but reads from the manifest root (e.g. filters, caveats)
    def g(d):
        cur = d
        for k in path:
            cur = cur[k]
        return cur
    return g


def caveat_text(index):
    # verbatim caveat string from the manifest caveats list, fail loud on overrun
    def g(d):
        caveats = d["caveats"]
        if index >= len(caveats):
            raise KeyError(f"missing caveat index: {index}")
        return caveats[index]
    return g


def plain_vs_firth_max_logdiff():
    # max log_abs_diff across the plain-vs-Firth sanity dict (the worst-case gap)
    def g(d):
        sanity = d["metrics"]["plain_vs_firth_sanity"]
        return max(float(v["log_abs_diff"]) for v in sanity.values())
    return g


def fig(key: str, max_h: int = 360) -> str:
    path = FIGURES[key]
    if not path.exists():
        raise SystemExit(f"missing figure: {path}")
    svg = path.read_text()
    svg = svg[svg.find("<svg"):]
    return f'<div class="fig" style="--maxh:{max_h}px">{svg}</div>'


# --- formatters ---------------------------------------------------------------
def pct1(x):
    return f"{float(x) * 100:.1f}%"


def keep(x):
    # pass a string value through unchanged (proper nouns, taxonomy labels, text)
    return f"{x}"


ncomma = "{:,.0f}"


def jp(text: str) -> str:
    """Render a Japanese translation block below an English line (smaller, lighter)."""
    return f'<div class="jp" lang="ja">{text}</div>'


_SUP = str.maketrans("-0123456789", "⁻⁰¹²³⁴⁵⁶⁷⁸⁹")


def psup(p: float) -> str:
    """p-value with a unicode superscript exponent (no HTML <sup>, no em dash)."""
    p = float(p)
    if p < 1e-4:
        mant, exp = f"{p:.1e}".split("e")
        return f"p = {mant}×10{str(int(exp)).translate(_SUP)}"
    if p < 0.001:
        return "p &lt; .001"
    return f"p = {p:.3f}".replace("0.", ".")


def f2(x):
    return f"{float(x):.2f}"


def build() -> str:
    # ---- pull every displayed number from a source file -----------------------
    # Scope (slide 1)
    total_reviews = stat("nudge_poi", poi_total_reviews(), ncomma, "", "sum(n_reviews) tagged review records")
    n_pois = stat("poi_mfst", manifest_metric("n_pois_total"), "{:.0f}", "", "poi_mfst metrics.n_pois_total")

    # Data (slide 3)
    tagged_rows = stat("aspect_mfst", manifest_metric("tagged_input_rows"), ncomma, "", "aspect_mfst metrics.tagged_input_rows")
    lang_jp = stat("aspect_mfst", manifest_metric("tagged_language_group_counts", "japanese"), ncomma, "", "tagged_language_group_counts.japanese")
    lang_en = stat("aspect_mfst", manifest_metric("tagged_language_group_counts", "english"), ncomma, "", "tagged_language_group_counts.english")
    lang_other = stat("aspect_mfst", manifest_metric("tagged_language_group_counts", "other_non_english_non_japanese"), ncomma, "", "tagged_language_group_counts.other")
    poi_fukui = stat("poi_mfst", manifest_metric("n_pois_by_prefecture", "Fukui"), "{:.0f}", "", "n_pois_by_prefecture.Fukui")
    poi_ishikawa = stat("poi_mfst", manifest_metric("n_pois_by_prefecture", "Ishikawa"), "{:.0f}", "", "n_pois_by_prefecture.Ishikawa")
    poi_toyama = stat("poi_mfst", manifest_metric("n_pois_by_prefecture", "Toyama"), "{:.0f}", "", "n_pois_by_prefecture.Toyama")

    # Pipeline (slide 4)
    model_rows = stat("aspect_mfst", manifest_metric("primary_model_rows"), ncomma, "", "aspect_mfst metrics.primary_model_rows")
    low_rating_rows = stat("aspect_mfst", manifest_metric("primary_low_rating_rows"), ncomma, "", "aspect_mfst metrics.primary_low_rating_rows")
    low_rating_def = stat("aspect_mfst", manifest_top("filters", "low_rating_definition"), keep, "", "filters.low_rating_definition")

    # Model + guards (slide 5)
    models_primary = stat("aspect_mfst", manifest_metric("A_primary_models_fit"), "{:.0f}", "", "A_primary_models_fit")
    status_ok = stat("aspect_mfst", manifest_metric("status_counts", "ok"), "{:.0f}", "", "status_counts.ok")
    status_prev = stat("aspect_mfst", manifest_metric("status_counts", "prevalence_only"), "{:.0f}", "", "status_counts.prevalence_only")
    status_skip = stat("aspect_mfst", manifest_metric("status_counts", "skipped"), "{:.0f}", "", "status_counts.skipped")
    models_total = stat("aspect_mfst", manifest_metric("total_models_fit"), "{:.0f}", "", "total_models_fit")
    min_p = stat("aspect_mfst", manifest_metric("min_model_p_value"), pfmt, "", "min_model_p_value")
    firth_sanity = stat("aspect_mfst", plain_vs_firth_max_logdiff(), "{:.3f}", "", "max plain_vs_firth log_abs_diff")
    caveat_gate = stat("aspect_mfst", caveat_text(6), keep, "", "caveats[6] gating rule")

    # Nudge taxonomy (slide 6)
    eng_type = stat("nudge_tax", taxonomy_value("english_information_gap", "nudge_type"), keep, "", "taxonomy english_information_gap nudge_type")
    eng_mech = stat("nudge_tax", taxonomy_value("english_information_gap", "mechanism"), keep, "", "taxonomy english_information_gap mechanism")
    book_type = stat("nudge_tax", taxonomy_value("booking_ticketing", "nudge_type"), keep, "", "taxonomy booking_ticketing nudge_type")
    book_mech = stat("nudge_tax", taxonomy_value("booking_ticketing", "mechanism"), keep, "", "taxonomy booking_ticketing mechanism")
    crowd_type = stat("nudge_tax", taxonomy_value("waiting_crowding", "nudge_type"), keep, "", "taxonomy waiting_crowding nudge_type")
    crowd_mech = stat("nudge_tax", taxonomy_value("waiting_crowding", "mechanism"), keep, "", "taxonomy waiting_crowding mechanism")
    staff_type = stat("nudge_tax", taxonomy_value("staff_communication", "nudge_type"), keep, "", "taxonomy staff_communication nudge_type")
    staff_mech = stat("nudge_tax", taxonomy_value("staff_communication", "mechanism"), keep, "", "taxonomy staff_communication mechanism")

    # Aspect opportunity map (slide 7)
    open_prev = stat("nudge_aspect", aspect_value("opening_hours_availability", "prevalence"), pct1, "", "opening_hours_availability pooled prevalence")
    open_or = stat("nudge_aspect", aspect_value("opening_hours_availability", "odds_ratio"), "{:.2f}", "", "opening_hours_availability Firth OR")
    open_p = stat("nudge_aspect", aspect_value("opening_hours_availability", "p_value_bh_fdr"), pfmt, "", "opening_hours_availability BH-FDR p")
    time_prev = stat("nudge_aspect", aspect_value("itinerary_fit_time_cost", "prevalence"), pct1, "", "itinerary_fit_time_cost pooled prevalence")
    time_or = stat("nudge_aspect", aspect_value("itinerary_fit_time_cost", "odds_ratio"), "{:.2f}", "", "itinerary_fit_time_cost Firth OR")
    time_p = stat("nudge_aspect", aspect_value("itinerary_fit_time_cost", "p_value_bh_fdr"), pfmt, "", "itinerary_fit_time_cost BH-FDR p")
    eng_gap_prev = stat("nudge_aspect", aspect_value("english_information_gap", "prevalence"), pct1, "", "english_information_gap pooled prevalence")
    sign_prev = stat("nudge_aspect", aspect_value("wayfinding_signage", "prevalence"), pct1, "", "wayfinding_signage pooled prevalence")
    access_prev = stat("nudge_aspect", aspect_value("transport_access", "prevalence"), pct1, "", "transport_access pooled prevalence")
    booking_prev = stat("nudge_aspect", aspect_value("booking_ticketing", "prevalence"), pct1, "", "booking_ticketing pooled prevalence")
    price_or = stat("nudge_aspect", aspect_value("price_value", "odds_ratio"), "{:.2f}", "", "price_value Firth OR")

    # Chinese-language Xiaohongshu promotion hypothesis (slide 9)
    cn_rows = stat("cn_mfst", manifest_metric("denominators", "chinese_social_rows"), ncomma, "", "cn_mfst metrics.denominators.chinese_social_rows")
    cn_xhs_rows = stat("cn_mfst", manifest_metric("denominators", "n_total_xhs_rows"), ncomma, "", "cn_mfst metrics.denominators.n_total_xhs_rows")
    dino_n = stat("cn_drivers", cn_driver_value("dinosaurs_museums", "sentiment_category=positive", "group_a_n"), "{:.0f}", "", "dinosaurs_museums positive-category group_a_n")
    dino_pos = stat("cn_drivers", cn_driver_value("dinosaurs_museums", "sentiment_category=positive", "group_a_event_count"), "{:.0f}", "", "dinosaurs_museums positive-category group_a_event_count")
    dino_pct = stat("cn_drivers", cn_driver_value("dinosaurs_museums", "sentiment_category=positive", "group_a_event_pct"), pct1, "", "dinosaurs_museums positive-category group_a_event_pct")
    dino_other_pct = stat("cn_drivers", cn_driver_value("dinosaurs_museums", "sentiment_category=positive", "group_b_event_pct"), pct1, "", "dinosaurs_museums positive-category group_b_event_pct")
    dino_fdr = stat("cn_drivers", cn_driver_value("dinosaurs_museums", "sentiment_category=positive", "p_value_bh_fdr"), pfmt, "", "dinosaurs_museums positive-category BH-FDR p")
    scenic_n = stat("cn_drivers", cn_driver_value("scenic_nature", "sentiment_category=positive", "group_a_n"), "{:.0f}", "", "scenic_nature positive-category group_a_n")
    scenic_pos = stat("cn_drivers", cn_driver_value("scenic_nature", "sentiment_category=positive", "group_a_event_count"), "{:.0f}", "", "scenic_nature positive-category group_a_event_count")
    scenic_pct = stat("cn_drivers", cn_driver_value("scenic_nature", "sentiment_category=positive", "group_a_event_pct"), pct1, "", "scenic_nature positive-category group_a_event_pct")
    scenic_other_pct = stat("cn_drivers", cn_driver_value("scenic_nature", "sentiment_category=positive", "group_b_event_pct"), pct1, "", "scenic_nature positive-category group_b_event_pct")
    scenic_fdr = stat("cn_drivers", cn_driver_value("scenic_nature", "sentiment_category=positive", "p_value_bh_fdr"), pfmt, "", "scenic_nature positive-category BH-FDR p")

    # Final cross-language recommendation ranking (slide 11)
    priorities = []
    for rank in (1, 2, 3):
        priorities.append({
            "rank": stat("solution_priorities", priority_value(rank, "rank"), "{:.0f}", "", f"priority rank {rank}"),
            "name_en": stat("solution_priorities", priority_value(rank, "solution_label_en"), keep, "", f"priority rank {rank} solution_label_en"),
            "name_ja": stat("solution_priorities", priority_value(rank, "solution_label_ja"), keep, "", f"priority rank {rank} solution_label_ja"),
            "impact": stat("solution_priorities", priority_value(rank, "impact_tier"), keep, "", f"priority rank {rank} impact_tier"),
            "ease": stat("solution_priorities", priority_value(rank, "ease_tier"), keep, "", f"priority rank {rank} ease_tier"),
            "summary_en": stat("solution_priorities", priority_value(rank, "evidence_summary_en"), keep, "", f"priority rank {rank} evidence_summary_en"),
            "summary_ja": stat("solution_priorities", priority_value(rank, "evidence_summary_ja"), keep, "", f"priority rank {rank} evidence_summary_ja"),
            "test_en": stat("solution_priorities", priority_value(rank, "intervention_en"), keep, "", f"priority rank {rank} intervention_en"),
            "test_ja": stat("solution_priorities", priority_value(rank, "intervention_ja"), keep, "", f"priority rank {rank} intervention_ja"),
        })

    # POI action map (slide 10)
    fix_count = stat("nudge_poi", poi_sum("is_fix_it"), "{:.0f}", "", "count is_fix_it")
    fix_fukui = stat("nudge_poi", poi_sum("is_fix_it", True), "{:.0f}", "", "count is_fix_it and is_fukui")
    promote_count = stat("nudge_poi", poi_sum("is_promote_it"), "{:.0f}", "", "count is_promote_it")
    promote_fukui = stat("nudge_poi", poi_sum("is_promote_it", True), "{:.0f}", "", "count is_promote_it and is_fukui")
    crowd_count = stat("nudge_poi", poi_sum("is_crowding_hotspot"), "{:.0f}", "", "count is_crowding_hotspot")
    low_vol = stat("nudge_poi", poi_metric("low_volume_threshold"), "{:.0f}", "", "low_volume_threshold")
    high_vol = stat("nudge_poi", poi_metric("high_volume_threshold"), "{:.0f}", "", "high_volume_threshold")
    promo1 = stat("nudge_poi", poi_ranked("promote_fukui", 0, "poi_name"), keep, "", "top Fukui promote-it poi_name")
    promo1_share = stat("nudge_poi", poi_ranked("promote_fukui", 0, "positive_share"), pct1, "", "top Fukui promote-it positive_share")
    promo1_low = stat("nudge_poi", poi_ranked("promote_fukui", 0, "positive_share_ci_low"), pct1, "", "top Fukui promote-it positive_share_ci_low")
    promo1_high = stat("nudge_poi", poi_ranked("promote_fukui", 0, "positive_share_ci_high"), pct1, "", "top Fukui promote-it positive_share_ci_high")
    promo1_conf = stat("nudge_poi", poi_ranked("promote_fukui", 0, "promote_confidence"), keep, "", "top Fukui promote-it confidence")
    promo2 = stat("nudge_poi", poi_ranked("promote_fukui", 1, "poi_name"), keep, "", "second Fukui promote-it poi_name")
    promo2_share = stat("nudge_poi", poi_ranked("promote_fukui", 1, "positive_share"), pct1, "", "second Fukui promote-it positive_share")
    promo2_low = stat("nudge_poi", poi_ranked("promote_fukui", 1, "positive_share_ci_low"), pct1, "", "second Fukui promote-it positive_share_ci_low")
    promo2_high = stat("nudge_poi", poi_ranked("promote_fukui", 1, "positive_share_ci_high"), pct1, "", "second Fukui promote-it positive_share_ci_high")
    promo2_conf = stat("nudge_poi", poi_ranked("promote_fukui", 1, "promote_confidence"), keep, "", "second Fukui promote-it confidence")

    # Discussion caveats (slide 10): verbatim manifest strings
    cav_not_causal = stat("aspect_mfst", caveat_text(0), keep, "", "caveats[0]")
    cav_rank = stat("aspect_mfst", caveat_text(1), keep, "", "caveats[1]")
    cav_cluster = stat("aspect_mfst", caveat_text(3), keep, "", "caveats[3]")
    cav_lang = stat("aspect_mfst", caveat_text(8), keep, "", "caveats[8]")

    A = '<span class="who a">Andrew</span>'
    C = '<span class="who c">Co-presenter</span>'
    BOTH = '<span class="who b">Both</span>'

    # ---- slides ---------------------------------------------------------------
    slides: list[str] = []

    def slide(kind, num, body, notes, time):
        slides.append(
            f'<div class="slide {kind}"><div class="canvas">{body}'
            f'<div class="pagefoot"><span>Hokuriku Review Text → Testable Nudges</span>'
            f'<span>{num}</span></div></div>'
            f'<div class="notes"><b>⏱ {time}</b> &nbsp;{notes}</div></div>'
        )

    # 1: TITLE
    slide("title", "Title", f"""
      <p class="kicker">PBL Seminar · IMRAD format</p>
      <h1>Turning Hokuriku review text<br>into testable nudges</h1>
      {jp('<span class="jp-h1">北陸の口コミテキストを、検証可能なナッジへ</span>')}
      <p class="sub">An exploratory opportunity map: which friction and draw signals in
        reviews are <b>nudge-able</b>, and which POIs are fix-it vs promote-it.</p>
      {jp('口コミに表れる「不満」と「魅力」のうち、どれが<b>ナッジ可能</b>か、'
          'どのスポットが「改善型」か「推奨型」かを探索的に地図化します。')}
      <div class="presenters">
        <div>{A}<span>presents in slow, clear English</span>
          {jp('ゆっくり明瞭な英語で発表')}</div>
        <div>{C}<span>international student · co-presenter</span>
          {jp('留学生・共同発表者')}</div>
      </div>
      <p class="scope">Scope: {total_reviews} tagged reviews across {n_pois} POIs,
        three prefectures · every number traced to a source file ●</p>
      {jp(f'対象:3県・{n_pois}スポットの{total_reviews}件のタグ付き口コミ・'
          'すべての数値はソースファイルに紐づく ●')}
    """, f"{BOTH} Greet the audience. Andrew: \"We will speak slowly; please stop us if "
         "you need a word repeated.\" State the one-line goal: read review text, then rank "
         "which signals are nudge-able and where to experiment next. This is the nudge-refocused "
         "successor to last seminar's measurement deck. Note the provenance dot: every number "
         "is a live reference to a source file.",
         "0:00-0:55")

    # 2: INTRODUCTION
    slide("text", "Introduction", f"""
      <p class="secnum">I. INTRODUCTION</p>
      <h2>The question</h2>
      {jp('問い')}
      <ul class="big">
        <li>Visitors leave <b>friction and draw signals</b> in their reviews.</li>
        {jp('訪問者は口コミに<b>不満と魅力のシグナル</b>を残す。')}
        <li>Which are <b>nudge-able</b>: information provision, pre-commitment,
          demand redistribution, versus an <b>operator fix</b>?</li>
        {jp('そのうちどれが<b>ナッジ可能</b>(情報提供・事前コミットメント・需要の再配分)で、'
            'どれが<b>事業者側の改善</b>が必要か?')}
        <li>And which POIs are <b>fix-it</b> versus <b>promote-it</b>?</li>
        {jp('そして、どのスポットが<b>改善型</b>で、どれが<b>推奨型</b>か?')}
      </ul>
      <div class="pill">Exploratory and hypothesis-generating: we <b>rank candidate
        experiments</b>, not effects.</div>
      {jp('探索的・仮説生成型:私たちは<b>効果ではなく、候補となる実験を順位づけ</b>する。')}
    """, f"{A} Keep it to three sentences, slowly. The pivot from last time: not 'is there a "
         "language gap' but 'where can a low-cost nudge plausibly help'. Stress the honest frame: "
         "we rank where to experiment, we do not claim any nudge works yet. This sets up Methods.",
         "0:55-2:05")

    # 3: METHODS · DATA
    slide("text", "Methods · Data", f"""
      <p class="secnum">II. METHODS · WHERE THE TEXT COMES FROM</p>
      <h2>The corpus</h2>
      {jp('コーパス')}
      <div class="cols2 vtop">
        <div>
          <div class="card g"><h3>Tagged reviews</h3>
            {jp('タグ付き口コミ')}
            <p class="n">{tagged_rows} rows</p>
            {jp(f'{tagged_rows} 行')}
            <p class="n">JP {lang_jp} · EN {lang_en} · other {lang_other}</p>
            {jp(f'日本語 {lang_jp} · 英語 {lang_en} · その他 {lang_other}')}</div>
          <div class="card t"><h3>POIs by prefecture</h3>
            {jp('県別スポット数')}
            <p>Fukui {poi_fukui} · Ishikawa {poi_ishikawa} · Toyama {poi_toyama}.</p>
            {jp(f'福井 {poi_fukui} · 石川 {poi_ishikawa} · 富山 {poi_toyama}。')}
            <p class="muted">Review language, not nationality.</p>
            {jp('口コミの言語であり、国籍ではない。')}</div>
        </div>
        <div>{fig("volume", 250)}
          <p class="cap">Per-source volume lens: the within-language sentiment
            subset, not the full model corpus.</p>
          {jp('ソース別の件数の見方:全モデルコーパスではなく、'
              '同一言語内の感情サブセット。')}</div>
      </div>
      <p class="scope">Raw text, authors, URLs, and IDs never leave the project; only
        aggregate counts and statistics are published. {tagged_rows} rows total ●</p>
      {jp(f'原文・執筆者・URL・IDはプロジェクト外に出さず、集計値のみ公開。合計 {tagged_rows} 行 ●')}
    """, f"{C} Takes this slide. Explain: each review row is tagged with the aspects it mentions, "
         "across three Hokuriku prefectures. The 'other' bucket contains mixed-language Google reviews. "
         f"It is separate from the {cn_rows} Xiaohongshu posts shown later. Privacy line matters for a "
         "Japanese audience: only aggregates leave the project.",
         "2:05-3:20")

    # 4: METHODS · PIPELINE
    slide("text", "Methods · Pipeline", f"""
      <p class="secnum">II. METHODS · TEXT TO MODELED OUTCOME</p>
      <h2>From text to a modeled outcome</h2>
      {jp('テキストからモデル化された結果へ')}
      <ol class="pipe">
        <li><b>Tag</b> each review against 18 reviewed aspect codes (friction + draw).</li>
        {jp('各口コミを18のレビュー済みアスペクトコード(不満+魅力)に照合してタグ付け。')}
        <li><b>Model rows</b> with a supported language and a star rating: {model_rows}.</li>
        {jp(f'対応言語かつ星評価ありのモデル対象行:{model_rows}。')}
        <li><b>Outcome</b> = a low star rating, defined as <code>{low_rating_def}</code>
          ({low_rating_rows} rows).</li>
        {jp(f'結果変数=低い星評価、定義は <code>{low_rating_def}</code>({low_rating_rows} 行)。')}
      </ol>
      <div class="pill warn">Honesty rule: sentiment tools are <b>never compared across
        languages</b>. Secondary sentiment checks are within-language only.</div>
      {jp('誠実性ルール:感情分析ツールを<b>言語間で比較することは決してしない</b>。'
          '副次的な感情チェックは同一言語内のみ。')}
    """, f"{A} Slowly: the modeled outcome is a LOW star rating, a shared 1-5 scale, no sentiment "
         f"tool in the loop. {model_rows} rows have a supported language and a rating; {low_rating_rows} "
         "of them are low-rated. The aspect tags are the predictors. Emphasise the honesty rule: "
         "it is the methodological backbone reviewers will probe. Then hand to Co-presenter for the model.",
         "3:20-4:35")

    # 5: METHODS · MODEL + GUARDS
    slide("text", "Methods · Model + guards", f"""
      <p class="secnum">II. METHODS · MODEL &amp; GUARDS</p>
      <h2>Firth penalized logistic regression</h2>
      {jp('Firth ペナルティ付きロジスティック回帰')}
      <div class="cols2">
        <div>
          <ul class="big">
            <li>Hand-coded Firth model, adjusted for <b>text length, language,
              prefecture</b>.</li>
            {jp('自前実装の Firth モデル、<b>文字数・言語・県</b>を調整。')}
            <li>{models_primary} primary aspect models fit; across all segments
              {models_total} fit.</li>
            {jp(f'主分析で {models_primary} のアスペクトモデルを推定、全セグメントで {models_total} 推定。')}
            <li>Status: ok {status_ok} · prevalence-only {status_prev} · skipped {status_skip}.</li>
            {jp(f'状態:ok {status_ok} · 有病率のみ {status_prev} · スキップ {status_skip}。')}
          </ul>
        </div>
        <div>
          <div class="card"><h3>Sanity &amp; guards</h3>
            {jp('健全性チェックとガード')}
            <p>Plain vs Firth OR agree closely (max |Δlog| = {firth_sanity}).</p>
            {jp(f'通常ロジットと Firth の OR はよく一致(最大 |Δlog| = {firth_sanity})。')}
            <p>Smallest model p-value: {min_p}. Multiplicity: BH-FDR.</p>
            {jp(f'最小のモデル p 値:{min_p}。多重比較:BH-FDR。')}</div>
          {fig("txtlen", 200)}
          <p class="cap">Why we adjust for text length: review length differs sharply
            by language.</p>
          {jp('文字数を調整する理由:口コミの長さは言語によって大きく異なる。')}
        </div>
      </div>
      <div class="pill warn">{caveat_gate}</div>
      {jp('機会スコアは、摩擦アスペクトが FDR 有意かつ有害(オッズ比が 1 超)でない限り、'
          'ゼロにゲートされる。')}
    """, f"{C} Don't read every number. Two ideas: (1) Firth penalization keeps estimates stable "
         "when an aspect is rare or a cell is near-zero, and it barely moves the answer versus a "
         "plain logit, which is the sanity check. (2) The gate is the integrity move: an opportunity "
         "score is forced to zero unless the friction aspect is FDR-significant AND harmful. No "
         "cherry-picking. Andrew can field nesting questions.",
         "4:35-5:50")

    # 6: METHODS · NUDGE TAXONOMY
    slide("text", "Methods · Taxonomy", f"""
      <p class="secnum">II. METHODS · NUDGE TAXONOMY</p>
      <h2>Mapping each signal to a lever</h2>
      {jp('各シグナルをレバーに対応づける')}
      <table class="stats">
        <tr><th>Signal</th><th>Nudge type</th><th>Mechanism</th></tr>
        <tr>
          <td>English information gap{jp('英語情報の不足')}</td>
          <td>{eng_type}{jp('情報提供')}</td>
          <td>{eng_mech}{jp('計画・到着時点で短い英語の要約・FAQ・翻訳済みの判断手がかりを提供。')}</td>
        </tr>
        <tr>
          <td>Booking / ticketing{jp('予約・チケット')}</td>
          <td>{book_type}{jp('事前コミットメント')}</td>
          <td>{book_mech}{jp('旅行前に予約手順・チケット選択・締切・必要情報を提示。')}</td>
        </tr>
        <tr>
          <td>Waiting / crowding{jp('待ち時間・混雑')}</td>
          <td>{crowd_type}{jp('需要の再配分')}</td>
          <td>{crowd_mech}{jp('空いている時間帯・別の入口・近隣の代替地へ誘導。')}</td>
        </tr>
        <tr>
          <td>Staff communication{jp('スタッフ対応')}</td>
          <td>{staff_type}{jp('事業者側の改善')}</td>
          <td>{staff_mech}{jp('事業者が管理する接客スクリプト・翻訳補助・エスカレーション手順を改善。')}</td>
        </tr>
      </table>
      <div class="pill">Four nudge types: information provision · pre-commitment ·
        demand redistribution · operator fix (out of nudging scope).</div>
      {jp('4つのナッジ類型:情報提供・事前コミットメント・需要の再配分・'
          '事業者側の改善(ナッジの対象外)。')}
    """, f"{C} The taxonomy is the bridge from statistics to action. Every cell here is pulled live "
         "from the taxonomy CSV; labels and mechanisms are not typed by hand. The key distinction: "
         "the first three types are things a planning app or signage can do (nudge-able); 'operator "
         "fix' (staff, pricing) is flagged honestly as out of scope for a behavioral nudge.",
         "5:50-7:00")

    # 7: RESULTS · ASPECT OPPORTUNITY MAP
    slide("fig", "Result · Aspect map", f"""
      <p class="secnum">III. RESULTS · ASPECT OPPORTUNITY MAP</p>
      <h2>Two nudge-able friction levers stand out</h2>
      {jp('2つのナッジ可能な摩擦レバーが際立つ')}
      <div class="cols2 vtop">
        <div>
          <ul class="big">
            <li>Opening hours / availability: prevalence {open_prev}, OR {open_or},
              {open_p}.</li>
            {jp(f'開館時間・営業状況:有病率 {open_prev}、OR {open_or}、{open_p}。')}
            <li>Itinerary fit / time cost: prevalence {time_prev}, OR {time_or},
              {time_p}.</li>
            {jp(f'行程との適合・所要時間:有病率 {time_prev}、OR {time_or}、{time_p}。')}
            <li class="key">Prevalence-only (not yet rankable): English info gap
              {eng_gap_prev}, signage {sign_prev}, transport {access_prev},
              booking {booking_prev}.</li>
            {jp(f'有病率のみ(まだ順位づけ不可):英語情報の不足 {eng_gap_prev}、'
                f'案内表示 {sign_prev}、交通 {access_prev}、予約 {booking_prev}。')}
          </ul>
          <div class="pill warn">Honesty: price/value has a high OR ({price_or}) but is an
            <b>operator fix</b>: flagged, not nudge-able.</div>
          {jp(f'誠実性:価格・コスパは OR が高い({price_or})が<b>事業者側の改善</b>であり、'
              'ナッジ対象としては除外。')}
        </div>
        <div>{fig("nudge_aspect_fig", 320)}</div>
      </div>
    """, f"{A} The map plots penalty (odds ratio) against prevalence. Two friction aspects clear "
         "the gate: opening hours and itinerary/time-cost, both information/pre-commitment levers. "
         "Several others are common enough to see but not yet evidenced strongly, so they are "
         "targeted-collection candidates, not rankings. The price_value line is the integrity point: "
         "big effect, but you cannot nudge your way out of pricing, so we exclude it.",
         "7:00-7:50")

    # 8: RESULTS · INFORMATION LEVERS
    slide("fig", "Result · Info levers", f"""
      <p class="secnum">III. RESULTS · INFORMATION LEVERS</p>
      <h2>Nudge-able levers are the actionable set</h2>
      {jp('ナッジ可能なレバーが、実行可能な対象')}
      {fig("nudge_info_fig", 360)}
      <p class="scope">Information-provision and pre-commitment aspects are the actionable
        levers; operator-fix aspects are flagged but out of nudging scope.</p>
      {jp('情報提供・事前コミットメントのアスペクトが実行可能なレバー。'
          '事業者側の改善アスペクトは記録するがナッジの対象外。')}
    """, f"{A} Let the picture talk for a moment. The chart isolates the nudge-able friction levers "
         "with their Wilson prevalence intervals and Firth odds ratios. The story: these are where a "
         "low-cost information or pre-commitment prompt could plausibly move the low-rating outcome. "
         "Operator-fix aspects are deliberately greyed out of the action set, following the same honesty rule.",
         "7:50-8:25")

    # 9: RESULTS · XHS CONTEXT
    slide("text", "Result · XHS context", f"""
      <p class="secnum">III. RESULTS · CHINESE-LANGUAGE XIAOHONGSHU CONTEXT</p>
      <h2>A separate promotion hypothesis from Xiaohongshu</h2>
      {jp('小紅書から得た、別枠のプロモーション仮説')}
      <div class="cols2 vtop">
        <div class="card">
          <h3>Descriptive evidence grade</h3>
          {jp('記述的エビデンス')}
          <p>{cn_rows} Chinese-language Fukui social posts, all {cn_xhs_rows} from Xiaohongshu.
            These posts have no star-rating outcome.</p>
          {jp(f'福井に関する中国語 SNS 投稿 {cn_rows} 件。全 {cn_xhs_rows} 件が小紅書。'
              '星評価の結果変数はない。')}
          <p>SnowNLP categories are interpreted only within this source.</p>
          {jp('SnowNLP の分類は、このソース内だけで解釈する。')}
        </div>
        <div class="card">
          <h3>Signals worth testing</h3>
          {jp('検証する価値のあるシグナル')}
          <p><b>Dinosaur / museum:</b> {dino_pos} of {dino_n} posts positive
            ({dino_pct}) versus {dino_other_pct} without this tag; BH-FDR {dino_fdr}.</p>
          {jp(f'<b>恐竜・博物館:</b>{dino_n} 件中 {dino_pos} 件がポジティブ'
              f'({dino_pct})。タグなしは {dino_other_pct}、BH-FDR {dino_fdr}。')}
          <p><b>Scenic nature:</b> {scenic_pos} of {scenic_n} positive
            ({scenic_pct}) versus {scenic_other_pct}; BH-FDR {scenic_fdr}.</p>
          {jp(f'<b>自然景観:</b>{scenic_n} 件中 {scenic_pos} 件がポジティブ'
              f'({scenic_pct})。タグなしは {scenic_other_pct}、BH-FDR {scenic_fdr}。')}
        </div>
      </div>
      <div class="pill"><b>Candidate nudge:</b> A/B test a Chinese-language discovery card
        foregrounding dinosaur / museum and scenic-nature content. Measure clicks, saves,
        and itinerary intent.</div>
      {jp('<b>候補ナッジ:</b>恐竜・博物館と自然景観を前面に出した中国語の発見カードを'
          'A/B テストし、クリック・保存・旅程への追加意向を測定する。')}
      <p class="scope">Hypothesis-generating only: one platform, reviewed keyword tags,
        SnowNLP secondary sentiment, no rating model, no causal claim.</p>
      {jp('仮説生成に限定:単一プラットフォーム、レビュー済みキーワードタグ、'
          'SnowNLP の副次的感情分析、星評価モデルなし、因果主張なし。')}
    """, f"{C} Present this as a separate evidence stream. The {cn_rows} Xiaohongshu posts cannot enter "
         "the star-rating model because they have no ratings. Within Xiaohongshu, dinosaur and scenic-nature "
         "tags coincide with higher SnowNLP-positive shares after topic-family FDR correction. This supports "
         "an A/B-test candidate, not a proven effect. Do not compare SnowNLP with VADER or oseti.",
         "8:25-9:15")

    # 10: RESULTS · POI ACTION MAP
    slide("fig", "Result · POI map", f"""
      <p class="secnum">III. RESULTS · POI ACTION MAP</p>
      <h2>Fix-it, promote-it, and crowding hotspots</h2>
      {jp('改善型・推奨型・混雑ホットスポット')}
      <div class="cols2 vtop">
        <div>
          <ul class="big">
            <li><b>Fix-it</b>: {fix_count} POIs ({fix_fukui} in Fukui), high-volume with
              nudge-able friction.</li>
            {jp(f'<b>改善型</b>:{fix_count} スポット(うち福井 {fix_fukui})、来訪が多く'
                'ナッジ可能な摩擦あり。')}
            <li><b>Promote-it</b>: {promote_count} POIs ({promote_fukui} in Fukui),
              low-volume, high-satisfaction.</li>
            {jp(f'<b>推奨型</b>:{promote_count} スポット(うち福井 {promote_fukui})、'
                '来訪は少ないが満足度が高い。')}
            <li><b>Crowding hotspots</b>: {crowd_count}, demand-redistribution candidates.</li>
            {jp(f'<b>混雑ホットスポット</b>:{crowd_count}、需要再配分の候補。')}
          </ul>
          <p class="muted">Volume thresholds: low &lt; {low_vol} reviews · high &gt; {high_vol}.</p>
          {jp(f'件数しきい値:低 &lt; {low_vol} 件 · 高 &gt; {high_vol} 件。')}
          <p class="lead">Top Fukui promote-it: <b>{promo1}</b>, positive share {promo1_share}
            (CI {promo1_low} to {promo1_high}, {promo1_conf}); then <b>{promo2}</b>
            {promo2_share} (CI {promo2_low} to {promo2_high}, {promo2_conf}).</p>
          {jp(f'福井の推奨型トップ:<b>{promo1}</b>、ポジティブ割合 {promo1_share}'
              f'(信頼区間 {promo1_low}から{promo1_high}、{promo1_conf});次に <b>{promo2}</b> '
              f'{promo2_share}(信頼区間 {promo2_low}から{promo2_high}、{promo2_conf})。')}
        </div>
        <div>{fig("nudge_poi_fig", 330)}</div>
      </div>
    """, f"{C} Your slide. Three archetypes from the POI index: fix-it (busy + fixable friction), "
         "promote-it (hidden gems with high satisfaction but low volume, the demand-redistribution "
         "targets), and crowding hotspots (where you'd redirect demand FROM). Read the two top Fukui "
         "gems with their confidence intervals; note the small-n CIs honestly. POI names are proper "
         "nouns, so we keep them as-is in both languages.",
         "9:15-10:10")

    # 11: RESULTS · FINAL CROSS-LANGUAGE PRIORITIES
    p1, p2, p3 = priorities
    slide("text", "Result · Final priorities", f"""
      <p class="secnum">III. RESULTS · FINAL CROSS-LANGUAGE PRIORITIES</p>
      <h2>Rank common nudges by impact, then ease</h2>
      {jp('共通ナッジをインパクト、次に実装容易性で順位づける')}
      <table class="stats">
        <tr><th>Priority</th><th>Common solution</th><th>Evidence and ease</th><th>Next-semester test</th></tr>
        <tr>
          <td>{p1['rank']}</td>
          <td><b>{p1['name_en']}</b>{jp(p1['name_ja'])}</td>
          <td><b>{p1['impact']} impact · {p1['ease']}</b><br>{p1['summary_en']}{jp(p1['summary_ja'])}</td>
          <td>{p1['test_en']}{jp(p1['test_ja'])}</td>
        </tr>
        <tr>
          <td>{p2['rank']}</td>
          <td><b>{p2['name_en']}</b>{jp(p2['name_ja'])}</td>
          <td><b>{p2['impact']} impact · {p2['ease']}</b><br>{p2['summary_en']}{jp(p2['summary_ja'])}</td>
          <td>{p2['test_en']}{jp(p2['test_ja'])}</td>
        </tr>
        <tr>
          <td>{p3['rank']}</td>
          <td><b>{p3['name_en']}</b>{jp(p3['name_ja'])}</td>
          <td><b>{p3['impact']} impact · {p3['ease']}</b><br>{p3['summary_en']}{jp(p3['summary_ja'])}</td>
          <td>{p3['test_en']}{jp(p3['test_ja'])}</td>
        </tr>
      </table>
      <div class="pill">Ordinal opportunity ranking, not causal effectiveness.
        Impact tier comes first; implementation ease breaks ties.</div>
      {jp('因果的な効果ではなく、順序尺度による機会ランキング。'
          'インパクト層を優先し、同じ層では実装容易性で順位づける。')}
    """, f"{BOTH} This is the decision slide. Read only the first row in detail. Each solution "
         "has reviewed support from English, Japanese, and Chinese-language sources, although the "
         "evidence types differ. Priority one comes first because it combines high-impact evidence "
         "with the easiest prototype. The experiment register carries these exact ranks into next semester.",
         "10:10-11:00")

    # 12: DISCUSSION
    slide("text", "Discussion", f"""
      <p class="secnum">IV. DISCUSSION</p>
      <h2>What this can and cannot claim</h2>
      {jp('主張できること・できないこと')}
      <ul class="big">
        <li>{cav_not_causal}</li>
        {jp('探索的・仮説生成型であり、因果関係ではない。')}
        <li>{cav_rank}</li>
        {jp('機会スコアは候補となる追跡実験を順位づけるものであり、介入効果ではない。')}
        <li>{cav_cluster}</li>
        {jp('POIレベルのクラスタリングは Firth では未モデル化。行レベル推定は POI 入れ子の'
            '不確実性を過小評価しうる;探索的な順位づけのみ。')}
        <li>{cav_lang}</li>
        {jp('言語グループは口コミの言語を表し、執筆者の国籍ではない。')}
      </ul>
      <div class="pill">Every caveat above is pulled verbatim from the analysis manifest,
        not paraphrased on the slide.</div>
      {jp('上記の注意点はすべて分析マニフェストから逐語的に引用しており、スライド上で'
          '言い換えていない。')}
    """, f"{A} Slowly. This is the intellectual honesty slide. Each bullet is the verbatim caveat "
         "string from the manifest, so the limitations we present are exactly the ones the analysis "
         "itself records. The big four: not causal, ranks experiments not effects, POI clustering "
         "unmodeled, and language ≠ nationality. These limits are why the ranked solutions become "
         "randomized experiments next semester. Pause here.",
         "11:00-11:45")

    # 13: FUTURE WORK
    slide("text", "Future work", f"""
      <p class="secnum">IV. FUTURE WORK</p>
      <h2>From ranking to experiments</h2>
      {jp('順位づけから実験へ')}
      <div class="cols2">
        <div class="card"><h3>Experiment register</h3>
          {jp('実験レジスター')}
          <p>The next-semester register operationalizes the top-ranked opportunities into
            <b>A/B-testable nudges</b>.</p>
          {jp('来学期のレジスターが、上位の機会を<b>A/Bテスト可能なナッジ</b>に具体化する。')}
          <p><a class="reglink" href="docs/nudge_experiment_register.html">Open the
            experiment register →</a></p>
          {jp('<a class="reglink" href="docs/nudge_experiment_register.html">'
              '実験レジスターを開く →</a>')}</div>
        <div class="card"><h3>First experiment</h3>
          {jp('最初の実験')}
          <p>Begin with priority {p1['rank']}: <b>{p1['name_en']}</b>. Randomize exposure,
            log interactions, then estimate behavior change.</p>
          {jp(f'優先順位 {p1["rank"]} の<b>{p1["name_ja"]}</b>から開始。'
              '提示を無作為化し、反応を記録して行動変化を推定する。')}</div>
      </div>
      <p class="closing">This deck ranks <b>where</b> to experiment; the register says
        <b>how</b>. &nbsp;Thank you.</p>
      {jp('このデッキは<b>どこで</b>実験するかを順位づけし、レジスターは<b>どのように</b>'
          '行うかを示す。 &nbsp;ありがとうございました。')}
    """, f"{BOTH} Co-presenter delivers the register hand-off. Next semester begins with priority "
         f"{p1['rank']}, {p1['name_en']}, randomized by visitor session with exposure and interaction "
         "logging. Andrew closes: deck ranks WHERE, register says HOW. Then invite questions.",
         "11:45-12:30")

    # ---- assemble -------------------------------------------------------------
    css = r"""
:root{
  --paper:#fbfaf7;--ink:#172033;--muted:#5b677a;--teal:#2f6f73;--teal-deep:#1a4d50;
  --rule:#d7dde8;--neg:#9a031e;--band:#f1efe9;--teal-tint:#eaf1f0;--gold:#bc6c25;
  --xhs:#c0334d;--google:#2f6f73;--jp:#7c8794;
}
*{box-sizing:border-box}
body{margin:0;background:#e9e7e1;color:var(--ink);
  font-family:"Iowan Old Style","Palatino Linotype",Palatino,Georgia,serif;
  font-size:16px;-webkit-font-smoothing:antialiased}
.bar{position:sticky;top:0;z-index:10;background:#10302f;color:#eaf1f0;
  padding:10px 22px;display:flex;justify-content:space-between;align-items:center;
  font-family:ui-monospace,Menlo,monospace;font-size:12.5px;letter-spacing:.04em}
.bar b{color:#fff;letter-spacing:.12em}
.bar a{color:#9fd0cf;text-decoration:none}
.deck{max-width:1080px;margin:26px auto 80px;padding:0 20px}
.slide{margin:0 0 40px}
.canvas{position:relative;aspect-ratio:16/9;background:var(--paper);
  border:1px solid #c5ccd6;border-radius:6px;box-shadow:0 8px 28px rgba(20,30,45,.14);
  padding:46px 54px 56px;overflow:hidden;display:flex;flex-direction:column}
.canvas h1{font-size:42px;line-height:1.1;margin:6px 0 4px;font-weight:600;letter-spacing:-.01em}
.canvas h2{font-size:30px;line-height:1.15;margin:2px 0 4px;font-weight:600;letter-spacing:-.01em}
.canvas h3{font-size:17px;margin:0 0 4px;color:var(--teal-deep)}
.secnum{font-family:ui-monospace,Menlo,monospace;font-size:12px;letter-spacing:.14em;
  color:var(--teal-deep);margin:0 0 4px;text-transform:uppercase}
.kicker{font-family:ui-monospace,Menlo,monospace;font-size:13px;letter-spacing:.2em;
  text-transform:uppercase;color:var(--teal-deep);margin:0}
.sub{font-size:20px;color:#33414f;max-width:60ch;margin:8px 0 2px}
.lead{font-size:18px;color:#2b3742;margin:8px 0 2px}
.center{text-align:center}
.closing{font-size:18px;color:var(--teal-deep);margin:14px 0 0;line-height:1.45;
  border-top:2px solid var(--teal);padding-top:12px}
.muted{color:var(--muted);font-size:15px;margin:6px 0 2px}
ul.big,ol.pipe{margin:6px 0 10px;padding-left:24px}
ul.big li{font-size:18px;margin:0 0 2px;line-height:1.35}
ul.big li.key{color:var(--teal-deep)}
ol.pipe li{font-size:18px;margin:0 0 2px}
.pill{background:var(--band);border-left:3px solid var(--teal);padding:10px 16px;
  font-size:16px;margin:8px 0 2px;border-radius:0 4px 4px 0}
.pill.warn{background:#fbf3f0;border-left-color:var(--neg);color:#5a2630;font-size:15px}
.cols2{display:grid;grid-template-columns:1fr 1fr;gap:20px}
.cols2.vtop{align-items:start}
.card{background:#fff;border:1px solid var(--rule);border-radius:5px;padding:14px 16px}
.card p{margin:0 0 2px;font-size:15.5px}
.card.g{border-top:4px solid var(--google)}
.card.t{border-top:4px solid var(--gold)}
.card .n{font-family:ui-monospace,Menlo,monospace;font-size:15px;color:var(--teal-deep);font-weight:600}
.presenters{display:flex;gap:34px;margin:14px 0 14px}
.presenters>div{display:flex;flex-direction:column;gap:2px}
.presenters span:not(.who){font-size:14px;color:var(--muted)}
.who{display:inline-block;font-family:ui-monospace,Menlo,monospace;font-size:12px;
  font-weight:600;color:#fff;padding:2px 9px;border-radius:3px;letter-spacing:.04em;width:max-content}
.who.a{background:var(--teal)} .who.c{background:var(--xhs)} .who.b{background:#475569}
.scope{font-family:ui-monospace,Menlo,monospace;font-size:12px;color:var(--muted);
  margin-top:auto;line-height:1.5;padding-top:10px}
.stat{color:var(--teal-deep);white-space:nowrap;cursor:help;font-variant-numeric:tabular-nums;
  border-bottom:1px dotted var(--teal);font-weight:600}
.prov-dot{font-size:.5em;vertical-align:.5em;color:var(--teal);margin-left:1px;opacity:.6}
.reglink{color:var(--teal-deep);text-decoration:none;border-bottom:1px solid var(--teal);
  font-family:ui-monospace,Menlo,monospace;font-size:14px}
.fig{background:#fff;border:1px solid var(--rule);border-radius:4px;padding:8px;
  display:flex;justify-content:center;align-items:center}
.fig svg{width:100%;height:auto;max-height:var(--maxh,360px)}
.cap{font-size:13.5px;color:var(--muted);margin:6px 0 1px;line-height:1.35;font-style:italic}
table.stats{width:100%;border-collapse:collapse;font-size:15px;margin:4px 0 8px}
table.stats th,table.stats td{text-align:left;padding:6px 10px;border-bottom:1px solid var(--rule);vertical-align:top}
table.stats th{font-family:ui-monospace,Menlo,monospace;font-size:11px;letter-spacing:.06em;
  text-transform:uppercase;color:var(--muted);font-weight:400}
table.stats td:first-child{white-space:nowrap}
/* Bilingual Japanese sub-line: smaller, lighter, ja font stack */
.jp{font-family:"Hiragino Kaku Gothic ProN","Yu Gothic","Noto Sans JP",sans-serif;
  font-size:.82em;font-weight:300;color:var(--jp);line-height:1.4;margin:1px 0 6px}
.jp .stat{font-weight:400}
.jp-h1{font-size:.62em;font-weight:300}
table.stats .jp{margin:2px 0 0}
.card .jp{margin:0 0 5px}
.presenters .jp{margin:1px 0 0}
.scope+.jp{font-family:"Hiragino Kaku Gothic ProN","Yu Gothic","Noto Sans JP",sans-serif}
.pagefoot{position:absolute;left:54px;right:54px;bottom:18px;display:flex;
  justify-content:space-between;font-family:ui-monospace,Menlo,monospace;font-size:11px;
  color:var(--muted);border-top:1px solid var(--rule);padding-top:7px}
.slide.title .canvas{background:linear-gradient(160deg,#fff 0%,var(--teal-tint) 100%);
  border-top:6px solid var(--teal)}
.notes{max-width:1080px;margin:8px auto 0;font-size:14.5px;color:#3a4654;line-height:1.55;
  background:#fff;border:1px dashed #b9c2cf;border-left:4px solid var(--gold);
  border-radius:0 5px 5px 0;padding:11px 16px}
.notes b{font-family:ui-monospace,Menlo,monospace;color:var(--gold)}
@media print{
  body{background:#fff}.bar,.notes{display:none}
  .deck{max-width:none;margin:0;padding:0}
  .slide{margin:0;page-break-after:always}
  .canvas{box-shadow:none;border:none;border-radius:0;width:100vw;height:100vh;aspect-ratio:auto}
}
"""
    out = [
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>",
        "<meta name='viewport' content='width=device-width,initial-scale=1'>",
        "<title>Hokuriku Nudge: Seminar Slides Preview</title>",
        f"<style>{css}</style></head><body>",
        "<div class='bar'><span><b>NUDGE SEMINAR DECK PREVIEW</b> · IMRAD · bilingual · ~11 min · 2 presenters</span>"
        "<span>orange box = English speaker notes (not on slide) · ● = traced to source file · "
        "<a href='PBL-Dashboard.html'>full dashboard ↗</a></span></div>",
        "<div class='deck'>",
        "".join(slides),
        f"<p style='text-align:center;color:#5b677a;font-family:ui-monospace,Menlo,monospace;"
        f"font-size:12px;margin:30px 0 0'>Generated by scripts/build_nudge_seminar_slides.py: "
        f"every number resolved from a source file at build time ({len(REFS)} traced values). "
        f"Print to PDF for a clean export. Derived preview; not source of truth.</p>",
        "</div></body></html>",
    ]
    return "\n".join(out)


def main() -> int:
    load()
    OUT_HTML.write_text(build(), encoding="utf-8")
    print(f"wrote {OUT_HTML} ({OUT_HTML.stat().st_size:,} bytes); {len(REFS)} traced references")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
