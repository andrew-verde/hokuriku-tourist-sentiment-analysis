# Repo Guidance

## Purpose

This repository exists to support a Fukui-first cross-language tourism text
analysis project for a near-term team presentation.

Compare what different language/source groups discuss about Fukui tourism:

- Chinese-language Xiaohongshu posts from `tourism-data`; Douyin is temporarily
  excluded from the main pipeline and kept for explicit source-sensitivity runs
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

Current local review cache counts must come from generated sync/sentiment
manifests, not hand-maintained documentation. Run `make multilingual-reviews`
and `make sentiment-analysis`, then cite the generated aggregate manifests or
readiness outputs.

Chinese social inputs are external and should remain external:

- Source repo: sibling `tourism-data` checkout, or `TOURISM_DATA_DIR` override
- Expected main social inputs: `data/raw/social/*xhs*.csv` or the reviewed manual XHS workbook
- Douyin source-sensitivity inputs only: `data/raw/social/*douyin*.csv` and `data/processed/fukui_douyin_comments_from_md.csv`
- Current visible Fukui XHS files exist; manual full-text XHS pull is WIP.
- `make chinese-social` must fail when no real Chinese source files are found;
  there is no demo/fallback input mode for academic outputs. It currently
  excludes Douyin from the main pipeline.
- `make chinese-social-xhs-only` and `make chinese-insights-xhs-only` write
  labeled `_xhs_only` compatibility outputs for Xiaohongshu-only checks.
- `make chinese-social-with-douyin` is the explicit opt-in path for
  Douyin-inclusive source-sensitivity outputs.

## Project Readiness Checklist

- [x] Human-reviewed keyword codebooks: review templates exist in
  `output/codebook_review/`, Chinese config exists in
  `config/chinese_social_friction_codebook.yaml`, and reviewed Chinese rows exist
  in `docs/codebook_templates/chinese_reviewed_codebook_template.csv`. Current
  Chinese social runtime promotion uses reviewed Chinese friction/topic/sentiment
  rows and supersedes legacy YAML terms for matching codes. JP/EN native-speaker
  review decisions are complete in
  `docs/codebook_reviews/source/multilingual_keyword_codebook_review.xlsx`, and
  `make reviewed-codebook-config` promotes them into
  `config/reviewed_jp_en_codebook.yaml`. JP/EN sentiment output now includes
  reviewed keyword evidence columns, aggregate evidence rates, and
  library-score/codebook positive-evidence disagreement rates.
- [x] Chinese social sentiment/topic pipeline: `scripts/build_chinese_social_media_dataset.py`
  builds cleaned Chinese social outputs with SnowNLP secondary baseline sentiment from
  one `make chinese-social` trigger for Xiaohongshu rows. Reviewed Chinese
  friction/topic/sentiment codebook rows now feed runtime evidence matching,
  Douyin comment exports fail loud on missing parser provenance fields when the
  explicit Douyin-inclusive variant is used, missing discovered Chinese inputs fail loud, theme-sliced
  rates are suppressed below 10 rows, and aggregate topic/positive-evidence
  outputs are wired for presentation comparisons. Douyin is temporarily excluded
  from the main pipeline; an explicit opt-in path is available for
  source-sensitivity checks.
- [x] JP-EN Google review library sentiment: `scripts/build_sentiment_analysis.py`
  filters by Fukui prefecture metadata, scores English reviews with VADER,
  scores Japanese reviews with oseti, matches reviewed JP/EN keyword evidence,
  writes ignored row-level output, and tracks aggregate summaries/tests/readiness
  with hashes and dependency versions.
- [x] Statistical comparison suite: JP-EN review-row tests, POI-level sensitivity,
  POI cluster-bootstrap sensitivity, and Fukui-only
  EN/JP/CN aggregate baseline outputs exist. Current valid tests include
  common-scale Google `review_rating` Welch t-test / Welch ANOVA, explicit
  skipped raw-score parametric tests for VADER/oseti/SnowNLP non-equivalence,
  EN/JP/CN sentiment-category chi-square/Fisher tests, within-Chinese
  source-platform tests when multiple Chinese platforms are present, and
  XHS-first cross-source friction/enjoyment evidence prevalence tests using
  reviewed keyword evidence. The H1-H3 JP-EN descriptive-support scripts and
  within-POI paired robustness script now write aggregate-only hypothesis
  outputs under `output/hypothesis_tests/`: H1 sentiment category chi-square
  with neutral-band sensitivity, H2 common-scale star-rating Welch tests, H3
  reviewed evidence prevalence tests with FDR correction, and within-POI paired
  Wilcoxon checks for venue-clustering robustness.
- [x] Presentation outputs: `make presentation-safe` builds aggregate-only JP-EN
  chart/table data, captions, readiness notes, hashes, date coverage, and
  POI-category mix under `output/presentation_safe/`. The stage regenerates from
  real ignored inputs, fails on missing metadata instead of placeholders, and
  scans generated data for dummy/placeholder/test markers and row-level fields.

## Expected Analysis Shape

Default pipeline should become:

1. Sync Google review artifacts with `make multilingual-reviews`.
2. Build Chinese social rows from `tourism-data` with `make chinese-social`.
   Keep the main path Xiaohongshu-only for clarity until Douyin annotations and
   provenance are strong enough for the main theme analysis.
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
