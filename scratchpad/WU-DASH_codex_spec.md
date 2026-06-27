# Task: rewrite the PBL dashboard's Chinese narrative to match the current project state

Caveman mode: terse output, full technical substance. Surgical where possible, but this IS a
content rewrite of specific sections. Do NOT commit. Repo:
/home/andrewgreen/Repositories/andrew-verde/hokuriku-tourist-sentiment-analysis. Python: `.venv/bin/python`.

## READ FIRST (authoritative — do not re-derive, build on these)
1. `docs/chinese_evidence_strategy.md` — the canonical decision record for the Chinese pivot AND
   the rigor fixes. This is the single source of truth for the story. Read it fully.
2. `scratchpad/RIGOR_REVIEW_findings.md` — the adversarial rigor findings (SnowNLP false negatives,
   friction=topic-presence, thin-CN gate, etc.).
3. `.claude/.../memory/MEMORY.md` and the memory files it indexes (nudge-opportunity-pivot,
   pbl-dashboard-provenance, hokuriku-scope-expansion, within-poi-confirmatory-design,
   douyin-scope-decision, corpus-record-count).
4. The current generator `scripts/build_pbl_dashboard.py` — study its `stat()`, `raw()`, `n()`,
   `fig()`, `SOURCES`/`FIGS` patterns; you MUST reuse them (see Provenance below).

## THE PROBLEM (verified)
The dashboard currently tells the OLD Chinese story: it never reads
`output/chinese_google_reviews_analysis/`; its only Chinese content frames Chinese as
**Xiaohongshu-only, single-platform, descriptive** (generator lines ~494-496, ~719, ~957-971,
~1032-1033). That contradicts the current project state.

## THE CURRENT STORY TO TELL (per the canonical docs)
- **Chinese-language Google reviews are the PRIMARY Chinese statistical evidence**: POI-linked,
  star-rated, Hokuriku-wide (Kanazawa/Toyama/Fukui), n=243, same reviewed codebook as EN/JP.
- **Xiaohongshu (XHS) is DEMOTED to a directional guidepost** (Fukui-only, no POI link, no rating,
  fan-pilgrimage skew). Keep it, but reframed as directional — not the Chinese measurement source.
- **Convergence** between XHS and Google is shown on **keyword evidence (topics + pain-point/friction
  codes), NOT sentiment** (transport_access is the #1 pain point in both; 5/6 top topics & 5/6 top
  frictions shared). This is why XHS is safe as a guidepost.
- **SnowNLP honesty**: Chinese SnowNLP sentiment is unvalidated on short text — 64 of 81 "negative"
  rows (79%) are 4-5★ (`metrics.snownlp_validation`). Chinese sentiment categories / the
  0.63 / 33%-negative figure are NOT reportable sentiment outcomes. Chinese POSITIVE signal uses
  STAR ratings, not SnowNLP.
- **Chinese folded into the POI opportunity map** under a **language-aware confidence gate**: a flip
  cannot be driven by a per-POI-thin language (Chinese n<10 at that POI) or by <3 supporting tags.
  Per-POI Chinese is thin (median ~3/POI) → directional, not confirmatory.
- **Chinese pain-point tags are keyword topic-presence, not polarity** (fire on 5★ "停車很方便").
  Lynn approved the colloquial keyword vocabulary (recall up), but tagging stays polarity-blind.
- **Text length**: Chinese reviews are the shortest (median ~30 chars) → least keyword-match
  opportunity (already shown in the H3 text-length figure).
- **Terminology**: audience-facing, use **"pain points"** (not "friction"); the rest of the deck
  already uses it.

## WHAT TO DO
Rewrite ONLY the Chinese-related parts of `scripts/build_pbl_dashboard.py` so the rendered
`PBL-Dashboard.html` presents the above. Concretely:
1. **Corpus section** ("Where the text comes from", ~line 719): replace the "Chinese posts = N
   Xiaohongshu rows" line with BOTH sources in their roles — Chinese-language Google reviews
   (primary, n=243, POI-linked/star-rated/Hokuriku) and XHS (directional guidepost). Use the
   Chinese-Google count from `output/chinese_google_reviews_analysis/tagged_chinese_google_reviews_manifest.json`.
2. **New/expanded Chinese section**: present Chinese Google reviews as the primary Chinese source,
   the convergence (topics + pain points, transport #1 in both), and the cross-language comparison
   INCLUDING Chinese (use star ratings + evidence prevalence; NOT SnowNLP sentiment). Demote and
   keep the XHS strand as a directional guidepost. Reframe the old "Chinese strand: single-platform
   / descriptive only" text (lines ~1032-1033) to the new two-source split.
3. **Carry the honesty caveats** prominently in that section: SnowNLP false-negative rate (from
   `metrics.snownlp_validation`), Chinese pain-point tags are topic-presence (Lynn-approved
   vocabulary, still polarity-blind), per-POI Chinese is thin/directional, gate behavior.
4. Embed relevant existing figures where they help (do NOT invent figures). Candidates:
   `output/presentation_safe/multilingual/figure_cn_anchor_comparison.svg` and siblings
   (figure_sentiment_share_by_language_source, figure_statistical_evidence_summary,
   figure_volume_context). Wire them through the existing `fig()`/FIGS mechanism. Only embed if the
   figure honestly supports the claim (e.g. the cn anchor uses stars for Google, SnowNLP for XHS —
   fine as a directional anchor with caveat).
5. Keep the JP/EN confirmatory sections, the opportunity map, and the existing CN pain-point caveat
   intact — do not rewrite sound content. This is additive/reframing for the Chinese strand.

## DATA SOURCES (wire numbers from these; explore for exact fields)
- `output/chinese_google_reviews_analysis/tagged_chinese_google_reviews_manifest.json`
  (metrics: n_reviews, by_city, mean_review_rating, any_friction_rate, unique_pois, snownlp_validation).
- `output/cross_language_trends_hokuriku/cross_language_baseline_snapshot.csv` and
  `cross_language_statistical_tests.csv` (cross-language volume/rating/evidence; the chi-square
  carries the SnowNLP caveat already).
- `output/nudge_analysis/poi_opportunity_index_manifest.json` (CN per-POI counts, gate metrics,
  n_fix_it/promote).
- `docs/codebook_templates/chinese_google_review_friction_candidates.csv` (Lynn-approved, status=reviewed).

## HARD CONSTRAINTS
- **Provenance (critical)**: every NUMBER rendered must be a live traced reference via the existing
  `stat()`/`raw()`/`n()` helpers tied to a source file + SHA — never hardcode a literal number and
  never invent one. The build fails loud on missing inputs; keep it that way. If you need a new
  source file, register it in the SOURCES/paths dict the same way existing ones are.
- **Honesty**: do NOT present Chinese SnowNLP sentiment (the 0.63 / 33%-negative) as a sentiment
  result anywhere. Chinese positives use star ratings. Chinese per-POI pain points are directional.
  No causal/effectiveness claims.
- **Terminology**: "pain points" not "friction" in audience-facing text; do not rename data columns
  or aspect codes (e.g. `*_friction`, `any_friction`).
- Do not touch the JP/EN confirmatory analysis, the within-POI paired test framing, or the
  opportunity-map gate logic. Aggregate-only; no row text/author/id leakage.

## VERIFY + REPORT (caveman)
- `make dashboard` runs clean; print the "N traced references" line.
- `.venv/bin/python -m pytest -q` stays green (62 expected; if a dashboard test asserts on removed
  XHS-only prose, update it as a legitimate snapshot with a one-line comment — do NOT weaken).
- Grep the rendered `PBL-Dashboard.html`: confirm it now references Chinese Google reviews as
  primary, XHS as directional, the SnowNLP false-negative caveat, and uses "pain points".
- Report: sections changed, figures embedded, every new traced number + its source, any honesty
  caveat added, test result. Flag anything you were unsure about for the orchestrator.
