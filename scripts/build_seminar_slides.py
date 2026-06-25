#!/usr/bin/env python3
"""Build SEMINAR-Slides-Preview.html — a 16:9 IMRAD seminar-deck mockup.

Same provenance contract as scripts/build_pbl_dashboard.py: EVERY NUMBER ON A
SLIDE IS A LIVE REFERENCE TO AN ANALYSIS OUTPUT FILE. No numeric value is typed
by hand. Each is fetched via stat() with an explicit getter pointing at a CSV
cell or JSON field; a missing value fails the build loud rather than inventing a
number. Figures are the same script-generated SVGs the dashboard embeds.

This file is a PREVIEW of what the PowerPoint will look like (10-minute talk,
English spoken slowly for a Japanese audience, two co-presenters). It is
gitignored — it is a derived view, not source of truth.

Run:  .venv/bin/python scripts/build_seminar_slides.py
"""
from __future__ import annotations

import hashlib
import html
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
OUT_HTML = ROOT / "SEMINAR-Slides-Preview.html"

# Reuse the dashboard's source + figure registry verbatim (single source of truth).
SOURCES: dict[str, Path] = {
    "h1": ROOT / "output/hypothesis_tests/h1_sentiment_category_jp_en.csv",
    "h2": ROOT / "output/hypothesis_tests/h2_review_rating_jp_en.csv",
    "h3": ROOT / "output/hypothesis_tests/h3_reviewed_evidence_jp_en.csv",
    "wpoi": ROOT / "output/hypothesis_tests/within_poi_paired_jp_en.csv",
    "wen": ROOT / "output/within_language_sentiment/en_within_language_sentiment_drivers.csv",
    "cn_plat": ROOT / "output/chinese_specific_insights/sentiment_category_by_platform.csv",
    "cn_manifest": ROOT / "output/chinese_specific_insights/chinese_specific_insights_manifest.json",
    "pres_manifest": ROOT / "output/presentation_safe/presentation_manifest.json",
}

FIGURES = {
    "overview": ROOT / "docs/statistical_test_figures/figure_hypothesis_overview.svg",
    "h3_prev": ROOT / "docs/statistical_test_figures/figure_h3_reviewed_evidence_prevalence.svg",
    "h2_ladder": ROOT / "docs/statistical_test_figures/figure_h2_rating_gap_robustness_ladder.svg",
    "h2_dist": ROOT / "docs/statistical_test_figures/figure_h2_rating_distribution.svg",
    "wpoi_shift": ROOT / "docs/statistical_test_figures/figure_within_poi_paired_shift.svg",
    "h1_share": ROOT / "docs/statistical_test_figures/figure_h1_sentiment_category_share.svg",
    "cross_cat": ROOT / "docs/statistical_test_figures/figure_cross_source_sentiment_category.svg",
    "cn_plat": ROOT / "output/chinese_specific_insights/figure_sentiment_category_by_platform.svg",
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


# --- getters (identical logic to the dashboard) -------------------------------
def h1_cell(col):
    def g(d):
        r = d[d["analysis_type"] == "primary"]
        return float(r[col].iloc[0])
    return g


def h1_share(category, group):
    def g(d):
        r = d[(d["analysis_type"] == "primary") & (d["category"] == category) & (d["language_group"] == group)]
        return float(r["category_share"].iloc[0]) * 100
    return g


def h2_test(test_name, col):
    def g(d):
        r = d[d["test_name"] == test_name]
        return float(r[col].iloc[0])
    return g


def h2_mean(group):
    def g(d):
        r = d[(d["analysis_type"] == "group_summary") & (d["language_group"] == group)]
        return float(r["mean_review_rating"].iloc[0])
    return g


def h2_n(group):
    def g(d):
        r = d[(d["analysis_type"] == "group_summary") & (d["language_group"] == group)]
        return int(r["n_rating_present"].iloc[0])
    return g


def h3_fam(family, col):
    def g(d):
        r = d[(d["analysis_type"] == "evidence_family_test") & (d["evidence_family"] == family)]
        return float(r[col].iloc[0])
    return g


def h3_textlen(group, key):
    def g(d):
        r = d[d["text_length_summary_json"].notna()]
        obj = json.loads(r["text_length_summary_json"].iloc[0])
        return float(obj[group][key])
    return g


def wpoi_field(test_name, col):
    def g(d):
        r = d[d["test_name"] == test_name]
        return float(r[col].iloc[0])
    return g


def wpoi_detail(test_name, key):
    def g(d):
        r = d[d["test_name"] == test_name]
        obj = json.loads(r["details_json"].iloc[0])
        return int(obj[key])
    return g


def wl_row(analysis_id, outcome, col):
    def g(d):
        r = d[(d["analysis_id"] == analysis_id) & (d["outcome"] == outcome)]
        return float(r[col].iloc[0])
    return g


def cn_plat_pct(category):
    def g(d):
        r = d[d["sentiment_category"] == category]
        return float(r["pct_platform_rows"].iloc[0])
    return g


def manifest_metric(*path):
    def g(d):
        cur = d["metrics"]
        for k in path:
            cur = cur[k]
        return cur
    return g


def fig(key: str, max_h: int = 360) -> str:
    path = FIGURES[key]
    if not path.exists():
        raise SystemExit(f"missing figure: {path}")
    svg = path.read_text()
    svg = svg[svg.find("<svg"):]
    return f'<div class="fig" style="--maxh:{max_h}px">{svg}</div>'


# --- formatters ---------------------------------------------------------------
def pp(x):
    return f"{float(x):+.1f} pp"


def stars(x):
    return f"{float(x):+.2f}"


pct1 = lambda x: f"{float(x):.1f}%"
ncomma = "{:,.0f}"


def build() -> str:
    # ---- pull every displayed number from a source file -----------------------
    total_rows = stat("pres_manifest", manifest_metric("review_rows_represented"), ncomma, "", "metrics.review_rows_represented")
    en_n = stat("h2", h2_n("english"), ncomma, "", "H2 n_rating_present[english]")
    jp_n = stat("h2", h2_n("japanese"), ncomma, "", "H2 n_rating_present[japanese]")
    cn_n = stat("cn_manifest", manifest_metric("rows_represented"), ncomma, "", "CN metrics.rows_represented")

    en_len = stat("h3", h3_textlen("english", "median"), "{:.0f}", " chars", "H3 text_length english median")
    jp_len = stat("h3", h3_textlen("japanese", "median"), "{:.0f}", " chars", "H3 text_length japanese median")

    h2_diff = stat("h2", h2_test("welch_t_review_rating", "effect_mean_difference"), stars, "", "H2 welch mean_difference")
    h2_lo = stat("h2", h2_test("welch_t_review_rating", "ci_95_lower"), "{:.2f}", "", "H2 welch ci_lower")
    h2_hi = stat("h2", h2_test("welch_t_review_rating", "ci_95_upper"), "{:.2f}", "", "H2 welch ci_upper")
    h2_p = stat("h2", h2_test("welch_t_review_rating", "p_value"), pfmt, "", "H2 welch p_value")
    h2_en_mean = stat("h2", h2_mean("english"), "{:.2f}", "", "H2 english mean_review_rating")
    h2_jp_mean = stat("h2", h2_mean("japanese"), "{:.2f}", "", "H2 japanese mean_review_rating")
    h2_poi_diff = stat("h2", h2_test("poi_level_welch_t_mean_review_rating", "effect_mean_difference"), stars, "", "H2 POI-level mean_difference")
    h2_poi_p = stat("h2", h2_test("poi_level_welch_t_mean_review_rating", "p_value"), pfmt, "", "H2 POI-level p_value")

    h1_chi = stat("h1", h1_cell("statistic"), "{:.1f}", "", "H1 chi-square")
    h1_p = stat("h1", h1_cell("p_value_holm"), pfmt, "", "H1 p_value_holm")
    h1_v = stat("h1", h1_cell("effect_cramers_v"), "{:.2f}", "", "H1 cramers_v")
    h1_pos_en = stat("h1", h1_share("positive", "english"), pct1, "", "H1 positive share english")
    h1_pos_jp = stat("h1", h1_share("positive", "japanese"), pct1, "", "H1 positive share japanese")

    h3_enj = stat("h3", h3_fam("enjoyment", "risk_difference_pct"), pp, "", "H3 enjoyment risk_diff")
    h3_enj_p = stat("h3", h3_fam("enjoyment", "p_value_bh_fdr"), pfmt, "", "H3 enjoyment p_bh")
    h3_fri = stat("h3", h3_fam("friction", "risk_difference_pct"), pp, "", "H3 friction risk_diff")
    h3_fri_p = stat("h3", h3_fam("friction", "p_value_bh_fdr"), pfmt, "", "H3 friction p_bh")

    wp_pos = stat("wpoi", wpoi_field("within_poi_paired_positive_share", "effect"), "{:+.2f}", "", "within-POI positive_share effect")
    wp_pos_p = stat("wpoi", wpoi_field("within_poi_paired_positive_share", "p_value"), pfmt, "", "within-POI positive_share p")
    wp_rat = stat("wpoi", wpoi_field("within_poi_paired_rating", "effect"), stars, "", "within-POI rating effect")
    wp_rat_p = stat("wpoi", wpoi_field("within_poi_paired_rating", "p_value"), pfmt, "", "within-POI rating p")
    wp_pairs = stat("wpoi", wpoi_detail("within_poi_paired_positive_share", "n_pairs"), "{:.0f}", "", "within-POI n_pairs")
    wp_cand = stat("wpoi", wpoi_detail("within_poi_paired_positive_share", "n_shared_poi_candidates"), "{:.0f}", "", "within-POI n_candidates")

    wen_enj = stat("wen", wl_row("WL-EN-2", "sentiment_score", "effect_size"), "{:+.2f}", "", "WL-EN enjoyment effect")
    wen_enj_p = stat("wen", wl_row("WL-EN-2", "sentiment_score", "p_value_bh_fdr"), pfmt, "", "WL-EN enjoyment p_bh")

    cn_pos = stat("cn_plat", cn_plat_pct("positive"), pct1, "", "CN XHS positive pct")
    cn_neg = stat("cn_plat", cn_plat_pct("negative"), pct1, "", "CN XHS negative pct")

    A = '<span class="who a">Andrew</span>'
    C = '<span class="who c">Co-presenter</span>'
    BOTH = '<span class="who b">Both</span>'

    # ---- slides ---------------------------------------------------------------
    slides: list[str] = []

    def slide(kind, num, body, notes, time):
        slides.append(
            f'<div class="slide {kind}"><div class="canvas">{body}'
            f'<div class="pagefoot"><span>Fukui Cross-Language Tourism Sentiment</span>'
            f'<span>{num}</span></div></div>'
            f'<div class="notes"><b>⏱ {time}</b> &nbsp;{notes}</div></div>'
        )

    # 1 — TITLE
    slide("title", "Title", f"""
      <p class="kicker">PBL Seminar · IMRAD format</p>
      <h1>What different language groups say<br>about Fukui tourism</h1>
      <p class="sub">A cross-language sentiment comparison of Google reviews
        (English &amp; Japanese) and Xiaohongshu posts (Chinese).</p>
      <div class="presenters">
        <div>{A}<span>presents in slow, clear English</span></div>
        <div>{C}<span>international student · Chinese-language data</span></div>
      </div>
      <p class="scope">Scope: Fukui Prefecture · {total_rows} review/post rows ·
        every number traced to a source file ●</p>
    """, f"{BOTH} Greet audience. Andrew: \"We will speak slowly — please stop us "
         "if you need a word repeated.\" State the one-line question: do English, "
         "Japanese, Chinese visitors talk about Fukui differently? Hand naming split: "
         "Andrew = Google/English+Japanese + stats; Co-presenter = Chinese/XHS strand.",
         "0:00–0:50")

    # 2 — INTRODUCTION
    slide("text", "Introduction", f"""
      <p class="secnum">I — INTRODUCTION</p>
      <h2>The question</h2>
      <ul class="big">
        <li>Tourists review Fukui in <b>different languages</b> on different platforms.</li>
        <li>Do the <b>language groups differ</b> in how positive they sound —
            and if so, <b>why</b>?</li>
        <li>Hard part: each language is scored by a <b>different tool</b>, so raw
            scores are <b>not comparable</b>. We compare only fair, shared measures.</li>
      </ul>
      <div class="pill">Confirmatory comparison = English vs Japanese Google reviews.
        Chinese / Xiaohongshu = descriptive context.</div>
    """, f"{A} Keep it to three sentences, slowly. The trap we avoid: comparing a "
         "VADER number to an oseti number. Emphasise the honest framing — Chinese strand "
         "is context, not a head-to-head test. This sets up Methods.",
         "0:50–2:00")

    # 3 — DATA SOURCES (Google + XHS)
    slide("text", "Methods · Data", f"""
      <p class="secnum">M — METHODS · WHERE THE TEXT COMES FROM</p>
      <h2>Two platforms, three language groups</h2>
      <div class="cols3">
        <div class="card g"><h3>Google reviews</h3>
          <p>Solicited public reviews with a <b>1–5 star</b> rating.</p>
          <p class="n">{en_n} English &nbsp;·&nbsp; {jp_n} Japanese</p>
          <p class="muted">Fukui POIs · Outscraper-derived local cache.</p></div>
        <div class="card x"><h3>Xiaohongshu (小红书)</h3>
          <p>Chinese <b>social-media posts</b> — curated, lifestyle, <b>no star rating</b>.</p>
          <p class="n">{cn_n} posts</p>
          <p class="muted">External tourism-data checkout · single platform.</p></div>
        <div class="card t"><h3>Why it matters</h3>
          <p>Reviews vs social posts are <b>different genres</b>.</p>
          <p>So Google EN/JP is the <b>fair</b> comparison; XHS sits beside it.</p></div>
      </div>
      <p class="scope">Raw text, authors, URLs, IDs never leave the project — only
        aggregate counts published. {total_rows} rows total ●</p>
    """, f"{C} Takes this slide. Explain Xiaohongshu briefly for a Japanese audience: "
         "China's Instagram-meets-review app, travel inspiration, very positive by design. "
         "Key point: no star rating on XHS, so it cannot be compared like-for-like to Google. "
         f"Andrew gives Google counts ({en_n}/{jp_n}).",
         "2:00–3:15")

    # 4 — DATA FORMAT & PROCESSING
    slide("text", "Methods · Pipeline", f"""
      <p class="secnum">M — METHODS · PROCESSING</p>
      <h2>From raw text to auditable evidence</h2>
      <ol class="pipe">
        <li><b>Filter</b> to Fukui POIs; split Google into English / Japanese rows.</li>
        <li><b>Dual-path scoring</b> — each row gets <i>two</i> signals:</li>
      </ol>
      <div class="cols2">
        <div class="card"><h3>① Sentiment score → category</h3>
          <p>VADER (EN) · oseti (JP) · SnowNLP (CN).</p>
          <p>Shared rule: ≥ +0.05 positive, ≤ −0.05 negative.</p></div>
        <div class="card"><h3>② Reviewed keyword evidence</h3>
          <p>Hand-checked codebooks: friction · enjoyment ·
             recommendation · positive.</p>
          <p>Gives a <b>human-auditable reason</b>, not just a number.</p></div>
      </div>
      <div class="pill warn">Honesty rule: scores from different tools are
        <b>never</b> compared directly. We compare category shares, shared 1–5 stars,
        and evidence prevalence.</div>
    """, f"{A} Slowly: \"score path\" = comparable category; \"evidence path\" = why. "
         "The threshold ±0.05 is the same for everyone. Stress the honesty rule — this is "
         "the methodological backbone reviewers will check. Then hand to Co-presenter for stats.",
         "3:15–4:30")

    # 5 — STATISTICAL METHODS explained
    slide("text", "Methods · Stats", f"""
      <p class="secnum">M — METHODS · STATISTICAL TESTS</p>
      <h2>Four tests, plain language</h2>
      <table class="stats">
        <tr><th>Test</th><th>Question in plain words</th><th>Guard</th></tr>
        <tr><td><b>χ² independence</b></td><td>Is the positive/neutral/negative
          <i>mix</i> linked to language?</td><td>Holm correction</td></tr>
        <tr><td><b>Welch t-test</b></td><td>Do mean <i>star ratings</i> (1–5) differ?
          The fair, shared scale.</td><td>95% CI</td></tr>
        <tr><td><b>Prevalence test</b></td><td>Does each <i>evidence family</i> appear
          more in one language?</td><td>Benjamini–Hochberg FDR</td></tr>
        <tr><td><b>Wilcoxon (within-POI)</b></td><td>Same venue, both languages — does the
          gap survive?</td><td>pairs the venues</td></tr>
      </table>
      <div class="pill">Rows are nested in venues (POIs), so single-level p-values are
        <b>descriptive</b>; the within-POI paired test is the real robustness check.
        α = .05 throughout.</div>
    """, f"{C} Don't read the table — explain the idea of multiple-testing correction "
         "in one breath: \"run many tests, some look significant by luck, so we adjust.\" "
         "Within-POI = the honest move: same place, both languages, is the gap real? "
         "Andrew can chip in on nesting if asked.",
         "4:30–5:45")

    # 6 — RESULTS OVERVIEW
    slide("fig", "Results", f"""
      <p class="secnum">R — RESULTS · AT A GLANCE</p>
      <h2>English reviews are consistently more positive</h2>
      {fig("overview", 360)}
      <p class="scope">Four confirmatory checks · effect sizes with
        multiplicity-adjusted p-values · we go cleanest → most caveated.</p>
    """, f"{A} One sentence: English-language reviews rate higher and sound more positive "
         "than Japanese-language reviews of the same venues — and it mostly survives "
         "controls. Say the next slides go strongest to weakest. Don't read the panel.",
         "5:45–6:20")

    # 7 — RESULT F1 rating gap (number + ladder)
    slide("fig", "Result · Rating gap", f"""
      <p class="secnum">R — FINDING 1 · CLEANEST COMPARISON</p>
      <h2>English reviewers give higher star ratings</h2>
      <p class="lead big-stat">EN <b>{h2_en_mean}</b> &nbsp;vs&nbsp; JP <b>{h2_jp_mean}</b>
        &nbsp;→&nbsp; Δ = <b>{h2_diff}</b> stars</p>
      <p class="muted center">Shared 1–5 scale, no tool in between ·
        95% CI {h2_lo}–{h2_hi}, {h2_p}</p>
      {fig("h2_ladder", 320)}
    """, f"{A} This is THE defensible result — same star scale for everyone, no tool bias. "
         "The ladder: the gap stays right of zero as the unit tightens from reviews to POI "
         f"averages ({h2_poi_diff}, {h2_poi_p}). Direction clear; cause waits for Discussion.",
         "6:20–7:00")

    # 8 — RESULT F1 distribution (figure-led, light)
    slide("fig", "Result · Distribution", f"""
      <p class="secnum">R — FINDING 1 · WHERE THE GAP LIVES</p>
      <h2>Both skew high — English has more 5-star rows</h2>
      {fig("h2_dist", 380)}
    """, f"{A} Quick slide — let the picture talk. Both groups love Fukui (most reviews 4–5 "
         "stars), so the gap is not complaints, it's the size of the top bar: English piles "
         "up more 5-star reviews. This visual sets up the response-style point later.",
         "7:00–7:30")

    # 9 — RESULT F2 within-POI
    slide("fig", "Result · Robustness", f"""
      <p class="secnum">R — FINDING 2 · VENUE-CONTROLLED ROBUSTNESS</p>
      <h2>Same venues, both languages: the gap mostly holds</h2>
      <div class="cols2 vtop">
        <div>
          <p class="lead">{wp_pairs} Fukui venues reviewed by both groups
            (of {wp_cand}):</p>
          <ul class="big">
            <li>Positive-share gap <b>{wp_pos}</b> ({wp_pos_p}) — <b>significant</b>.</li>
            <li>Star-rating gap <b>{wp_rat}</b> ({wp_rat_p}) — borderline.</li>
          </ul>
          <p class="muted">Same place, both languages — removes <i>which</i> venues each
            group picks. One confound, not all.</p>
        </div>
        <div>{fig("wpoi_shift", 330)}</div>
      </div>
    """, f"{A} Honest: mixed, not a clean win. Positive-share gap survives inside shared "
         f"venues; rating gap goes borderline because only {wp_pairs} venues overlap — "
         "underpowered, so inconclusive, not a null.",
         "7:30–8:10")

    # 10 — RESULT F3 sentiment mix
    slide("fig", "Result · Sentiment mix", f"""
      <p class="secnum">R — FINDING 3 · SENTIMENT MIX</p>
      <h2>The positive / neutral / negative mix differs</h2>
      <div class="cols2 vtop">
        <div>
          <p class="lead">Positive share: EN <b>{h1_pos_en}</b> vs JP <b>{h1_pos_jp}</b>.</p>
          <ul class="big">
            <li>χ² = {h1_chi}, {h1_p} — statistically clear.</li>
            <li class="key">But <b>small</b> in size: Cramér's V = {h1_v}.</li>
          </ul>
          <p class="muted">Significant-but-modest — report it honestly, not as a
            dramatic split.</p>
        </div>
        <div>{fig("h1_share", 330)}</div>
      </div>
    """, f"{C} Significance and size are different things — say that plainly. The mix differs, "
         "but the effect is small. Good teaching moment for the audience: a tiny p-value does "
         "not mean a big difference.",
         "8:10–8:45")

    # 11 — RESULT F4 evidence + friction null
    slide("fig", "Result · Evidence", f"""
      <p class="secnum">R — FINDING 4 · REVIEWED EVIDENCE</p>
      <h2>More praise — not fewer complaints</h2>
      <div class="cols2 vtop">
        <div>
          <ul class="big">
            <li>Enjoyment evidence gap <b>{h3_enj}</b> ({h3_enj_p}).</li>
            <li class="key">Friction (complaints) gap <b>{h3_fri}</b> ({h3_fri_p})
              — <b>not significant</b>.</li>
          </ul>
          <div class="pill warn">English reviews are longer
            ({en_len} vs {jp_len}) → more keyword matches by chance. Read the
            evidence gap with care.</div>
        </div>
        <div>{fig("h3_prev", 330)}</div>
      </div>
    """, f"{C} The clever bit: groups differ in how much they PRAISE, not how much they "
         "COMPLAIN. Friction null is the tell — remember it, it returns in Discussion. "
         "Mention the length confound honestly. Then hand to your Chinese slide.",
         "8:45–9:20")

    # 12 — Chinese strand (co-presenter)
    slide("fig", "Result · Chinese", f"""
      <p class="secnum">R — FINDING 5 · CHINESE SOCIAL POSTS (CONTEXT)</p>
      <h2>Xiaohongshu reads overwhelmingly positive</h2>
      <div class="cols2 vtop">
        <div>
          <p class="lead big-stat">{cn_pos} positive &nbsp;·&nbsp; {cn_neg} negative</p>
          <p class="muted">{cn_n} posts, single platform.</p>
          <ul class="big">
            <li>Different platform, tool, and unit → <b>context, not a test</b>.</li>
            <li>One platform only = no within-Chinese comparison yet.
              A data gap, not a finding.</li>
          </ul>
        </div>
        <div>{fig("cn_plat", 330)}</div>
      </div>
    """, f"{C} Your slide. XHS positivity is partly by design — aspirational travel content. "
         "That is exactly why it cannot be ranked against Google reviews. It generates "
         "hypotheses for future work, not conclusions now.",
         "9:20–9:55")

    # 13 — DISCUSSION 1: the cause
    slide("text", "Discussion · Cause", f"""
      <p class="secnum">D — DISCUSSION</p>
      <h2>The gap is real — its cause is not settled</h2>
      <ul class="big">
        <li>Direction is clear on the clean scale ({h2_diff} stars).</li>
        <li>Two readings fit equally well: a <b>real experience</b> difference,
          <b>or</b> a difference in <b>rating style</b>.</li>
        <li class="key">Equal complaint rate ({h3_fri}, {h3_fri_p}) tips the balance:
          groups <b>praise</b> differently but <b>complain</b> the same — the signature
          of a response-style effect.</li>
      </ul>
      <p class="scope">Within each language, enjoyment evidence drives higher sentiment
        ({wen_enj}, {wen_enj_p}) — consistent mechanism, never compared as raw scores
        across tools.</p>
    """, f"{A} Slowly. This is the intellectual core. If Fukui truly served one group worse, "
         "complaints would move too — they don't. So the gap is, at least partly, about how "
         "groups express praise, not how well Fukui treats them. Pause here.",
         "9:55–10:30")

    # 14 — DISCUSSION 2: takeaway + next
    slide("text", "Discussion · Takeaway", f"""
      <p class="secnum">D — TAKEAWAY &amp; NEXT</p>
      <h2>What to do with this</h2>
      <div class="cols2">
        <div class="card"><h3>For Fukui stakeholders</h3>
          <p>Don't benchmark raw cross-language scores against each other.</p>
          <p>Use <b>friction evidence</b> to find real service issues —
            it is language-independent.</p></div>
        <div class="card"><h3>Where this goes next</h3>
          <p>Calibrate response style · power up the venue test ·
            validate the scoring tools · add a 2nd Chinese platform.</p></div>
      </div>
      <p class="scope">Limitations: Fukui-only convenience cache · underpowered venue test
        ({wp_pairs} pairs) · tools not human-validated · Chinese strand single-platform.</p>
      <p class="closing">Real gap on a clean scale — but it reflects, in part, how groups
        <b>express</b> evaluation, not how well Fukui serves them. &nbsp;Thank you.</p>
    """, f"{BOTH} Co-presenter delivers the stakeholder takeaway and next steps. Andrew closes "
         "on the one-line conclusion, slowly, then invites questions. Don't rush the last line.",
         "10:30–11:00")

    # ---- assemble -------------------------------------------------------------
    css = r"""
:root{
  --paper:#fbfaf7;--ink:#172033;--muted:#5b677a;--teal:#2f6f73;--teal-deep:#1a4d50;
  --rule:#d7dde8;--neg:#9a031e;--band:#f1efe9;--teal-tint:#eaf1f0;--gold:#bc6c25;
  --xhs:#c0334d;--google:#2f6f73;
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
.canvas h1{font-size:42px;line-height:1.1;margin:6px 0 14px;font-weight:600;letter-spacing:-.01em}
.canvas h2{font-size:30px;line-height:1.15;margin:2px 0 16px;font-weight:600;letter-spacing:-.01em}
.canvas h3{font-size:17px;margin:0 0 7px;color:var(--teal-deep)}
.secnum{font-family:ui-monospace,Menlo,monospace;font-size:12px;letter-spacing:.14em;
  color:var(--teal-deep);margin:0 0 4px;text-transform:uppercase}
.kicker{font-family:ui-monospace,Menlo,monospace;font-size:13px;letter-spacing:.2em;
  text-transform:uppercase;color:var(--teal-deep);margin:0}
.sub{font-size:20px;color:#33414f;max-width:54ch;margin:0 0 22px}
.lead{font-size:19px;color:#2b3742;margin:0 0 14px}
.lead.big-stat{font-size:26px;margin:10px 0 4px}
.lead.big-stat b{color:var(--teal-deep)}
.center{text-align:center}
.closing{font-size:18px;color:var(--teal-deep);margin:14px 0 0;line-height:1.45;
  border-top:2px solid var(--teal);padding-top:12px}
.muted{color:var(--muted);font-size:15px}
.muted.center{text-align:center;margin:0 0 8px}
ul.big,ol.pipe{margin:6px 0 14px;padding-left:24px}
ul.big li{font-size:19px;margin:0 0 11px;line-height:1.4}
ul.big li.key{color:var(--teal-deep)}
ol.pipe li{font-size:18px;margin:0 0 8px}
.pill{background:var(--band);border-left:3px solid var(--teal);padding:11px 16px;
  font-size:16px;margin:8px 0;border-radius:0 4px 4px 0}
.pill.warn{background:#fbf3f0;border-left-color:var(--neg);color:#5a2630;font-size:15px}
.cols2{display:grid;grid-template-columns:1fr 1fr;gap:20px}
.cols3{display:grid;grid-template-columns:1fr 1fr 1fr;gap:16px}
.cols2.vtop{align-items:start}
.card{background:#fff;border:1px solid var(--rule);border-radius:5px;padding:14px 16px}
.card p{margin:0 0 7px;font-size:15.5px}
.card.g{border-top:4px solid var(--google)}
.card.x{border-top:4px solid var(--xhs)}
.card.t{border-top:4px solid var(--gold)}
.card .n{font-family:ui-monospace,Menlo,monospace;font-size:15px;color:var(--teal-deep);font-weight:600}
.presenters{display:flex;gap:34px;margin:6px 0 18px}
.presenters>div{display:flex;flex-direction:column;gap:3px}
.presenters span:not(.who){font-size:14px;color:var(--muted)}
.who{display:inline-block;font-family:ui-monospace,Menlo,monospace;font-size:12px;
  font-weight:600;color:#fff;padding:2px 9px;border-radius:3px;letter-spacing:.04em;width:max-content}
.who.a{background:var(--teal)} .who.c{background:var(--xhs)} .who.b{background:#475569}
.scope{font-family:ui-monospace,Menlo,monospace;font-size:12px;color:var(--muted);
  margin-top:auto;line-height:1.6;padding-top:10px}
.stat{color:var(--teal-deep);white-space:nowrap;cursor:help;font-variant-numeric:tabular-nums;
  border-bottom:1px dotted var(--teal);font-weight:600}
.prov-dot{font-size:.5em;vertical-align:.5em;color:var(--teal);margin-left:1px;opacity:.6}
.fig{background:#fff;border:1px solid var(--rule);border-radius:4px;padding:8px;
  display:flex;justify-content:center;align-items:center}
.fig svg{width:100%;height:auto;max-height:var(--maxh,360px)}
table.stats{width:100%;border-collapse:collapse;font-size:15.5px;margin:4px 0 12px}
table.stats th,table.stats td{text-align:left;padding:7px 10px;border-bottom:1px solid var(--rule);vertical-align:top}
table.stats th{font-family:ui-monospace,Menlo,monospace;font-size:11px;letter-spacing:.06em;
  text-transform:uppercase;color:var(--muted);font-weight:400}
table.stats td:first-child{white-space:nowrap}
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
        "<title>Fukui Sentiment — Seminar Slides Preview</title>",
        f"<style>{css}</style></head><body>",
        "<div class='bar'><span><b>SEMINAR DECK PREVIEW</b> · IMRAD · 10 min · 2 presenters</span>"
        "<span>orange box = speaker notes (not on slide) · ● = traced to source file · "
        "<a href='PBL-Dashboard.html'>full dashboard ↗</a></span></div>",
        "<div class='deck'>",
        "".join(slides),
        f"<p style='text-align:center;color:#5b677a;font-family:ui-monospace,Menlo,monospace;"
        f"font-size:12px;margin:30px 0 0'>Generated by scripts/build_seminar_slides.py — "
        f"every number resolved from a source file at build time ({len(REFS)} traced values). "
        f"Print to PDF for a clean export. Gitignored preview; not source of truth.</p>",
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
