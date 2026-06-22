# Repo Guidance

## Purpose

This repository exists to support a Fukui-first cross-language tourism text
analysis project for a near-term team presentation.

Compare what different language/source groups discuss about Fukui tourism:

- Chinese-language Xiaohongshu/Douyin posts from `tourism-data`
- Japanese-language Google reviews from the local `english-fukui-tourism` review cache
- English-language Google reviews from the same Google review cache

Treat group membership as content language/source platform, not nationality.

## Current Scope

Primary scope is Fukui Prefecture only.

Google review data currently includes Fukui, Kanazawa, and Toyama rows. Initial
analysis should filter Google POIs/reviews to Fukui. Kanazawa/Ishikawa and
Toyama rows are useful for later comparison only. Chinese colleague collection
may add Ishikawa Prefecture posts later; do not assume those exist until local
`tourism-data` files prove it.

Do not import FTAS SEM thesis logic or official survey data unless explicitly
requested.

## Data Sources Present Locally

Google review artifacts are synced locally under ignored `output/` paths:

- `output/checkpoints/`: raw Google Maps/Outscraper collection checkpoints
- `output/multilingual_review_analysis/`: derived multilingual review tables
- `output/google_review_sync_manifest.json`: local sync manifest with hashes

Current local review cache after sync:

- `reviews_multilingual.csv`: 6,036 rows
- Fukui rows: 2,209
- Fukui language groups: 214 English, 1,800 Japanese, 186 other, 9 too short or undetected
- Full cache language groups: 919 English, 4,037 Japanese, 1,040 other, 40 too short or undetected
- Checkpoint review totals: 2,405 Fukui, 2,425 Kanazawa, 1,839 Toyama

Chinese social inputs are external and should remain external:

- Source repo: sibling `tourism-data` checkout, or `TOURISM_DATA_DIR` override
- Expected raw social inputs: `data/raw/social/*xhs*.csv`, `data/raw/social/*douyin*.csv`
- Current parsed Douyin comment source: `data/processed/fukui_douyin_comments_from_md.csv`
- Current visible Fukui XHS files exist; manual full-text XHS pull is WIP.
- `make chinese-social` must fail when no real Chinese source files are found;
  there is no demo/fallback input mode for academic outputs.
- `make chinese-social-xhs-only` and `make chinese-insights-xhs-only` write
  labeled `_xhs_only` outputs for Xiaohongshu-only source-sensitivity checks
  when Douyin comments are too weak for a claim.

## Project Readiness Checklist

- [ ] Human-reviewed keyword codebooks: review templates exist in
  `output/codebook_review/`, Chinese config exists in
  `config/chinese_social_friction_codebook.yaml`, and reviewed Chinese rows exist
  in `docs/codebook_templates/chinese_reviewed_codebook_template.csv`. Current
  Chinese social runtime promotion uses reviewed Chinese friction/topic/sentiment
  rows and supersedes legacy YAML terms for matching codes. A JP/EN import gate
  now exists (`make reviewed-codebook-status` /
  `make reviewed-codebook-config`) and fails loud until manual JP/EN
  `review_decision` values are complete. Still needed: finish manual JP/EN
  review decisions, promote reviewed JP/EN decisions into runtime configs, add
  JP/EN evidence columns, then report library-score/codebook disagreement rates.
  Once manual review is complete, use `docs/manual_keyword_review_followup.md`
  as the agent implementation checklist.
- [x] Chinese social sentiment/topic pipeline: `scripts/build_chinese_social_media_dataset.py`
  builds cleaned Chinese social outputs with SnowNLP secondary baseline sentiment from
  one `make chinese-social` trigger for Xiaohongshu rows and parsed Douyin
  comments. Reviewed Chinese friction/topic/sentiment codebook rows now feed
  runtime evidence matching, Douyin comment exports fail loud on missing parser
  provenance fields, missing discovered Chinese inputs fail loud, theme-sliced
  rates are suppressed below 10 rows, and aggregate topic/positive-evidence
  outputs are wired for presentation comparisons. A labeled XHS-only alternate
  path is available for source-sensitivity checks.
- [x] JP-EN Google review library sentiment: `scripts/build_sentiment_analysis.py`
  filters by Fukui prefecture metadata, scores English reviews with VADER,
  scores Japanese reviews with oseti, writes ignored row-level output, and tracks
  aggregate summaries/tests/readiness with hashes and dependency versions.
- [x] Statistical comparison suite: JP-EN review-row tests, POI-level sensitivity,
  POI cluster-bootstrap sensitivity, and Fukui-only
  EN/JP/CN aggregate baseline outputs exist. Current valid tests include
  common-scale Google `review_rating` Welch t-test / Welch ANOVA, explicit
  skipped raw-score parametric tests for VADER/oseti/SnowNLP non-equivalence,
  EN/JP/CN sentiment-category chi-square/Fisher tests, and within-Chinese
  source-platform tests. Cross-source friction/enjoyment evidence tests remain
  skipped until JP/EN reviewed codebooks land.
- [x] Presentation outputs: `make presentation-safe` builds aggregate-only JP-EN
  chart/table data, captions, readiness notes, hashes, date coverage, and
  POI-category mix under `output/presentation_safe/`. The stage regenerates from
  real ignored inputs, fails on missing metadata instead of placeholders, and
  scans generated data for dummy/placeholder/test markers and row-level fields.

## Expected Analysis Shape

Default pipeline should become:

1. Sync Google review artifacts with `make multilingual-reviews`.
2. Build Chinese social rows from `tourism-data` with `make chinese-social`.
   Keep Xiaohongshu and Douyin in the same runtime path so codebook matching,
   SnowNLP scoring, denominator reporting, and caveats stay comparable.
3. Promote reviewed codebook CSV/Excel files into versioned configs.
4. Run Fukui-only language/source tagging:
   - Chinese-language posts: topic/friction/enjoyment keywords plus Chinese sentiment
   - Japanese-language reviews: manually reviewed Japanese codebook plus `oseti`
   - English-language reviews: manually reviewed English codebook plus VADER
5. Compare language/source groups descriptively and statistically where valid.
6. Generate presentation figures with explicit caveats about platform/source differences.

## Guardrails

- Do not commit row-level post/review text, author names, URLs, screenshots, source IDs, or raw manual captures.
- Keep `output/checkpoints/`, `output/multilingual_review_analysis/`, and Chinese raw/processed social rows ignored.
- Track aggregate outputs that contain only counts, statistics, filters,
  commands, dependency versions, input provenance, and SHA256 hashes for ignored
  source/intermediate files.
- Prefer fail-loud missing-input errors over demo data.
- Use transparent keyword evidence and reviewed codebooks as primary analysis.
- Model or VADER-like sentiment tools are secondary checks, not silent replacements for codebooks.
- Never describe review/post language groups as nationalities.

## Academic Rigor

All work in this repository should preserve an academic audit trail:

- Keep human review source files under `docs/codebook_reviews/source/`.
- Keep generated runtime configs separate from human review source files.
- Preserve original keyword, review decision, replacement keyword, reviewer, and
  date whenever codebooks are promoted into config.
- Report denominators, filters, source paths, and commands for every analysis output.
- Fail loudly on missing or stale inputs; do not silently fall back to toy data.
- Prefer clear caveats over overstated cross-platform comparisons.
