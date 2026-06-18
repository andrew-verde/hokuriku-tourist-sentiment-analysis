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

- Source repo: `/Users/andrewgreen/Repositories/tourism-data`
- Expected raw social inputs: `data/raw/social/*xhs*.csv`, `data/raw/social/*douyin*.csv`
- Current visible Fukui XHS files exist; manual full-text XHS pull is WIP.

## Project Readiness Checklist

- [ ] Human-reviewed keyword codebooks: review templates exist in
  `output/codebook_review/`, Chinese config exists in
  `config/chinese_social_friction_codebook.yaml`, and reviewed Chinese rows exist
  in `docs/codebook_templates/chinese_reviewed_codebook_template.csv`. Still
  needed: promote reviewed JP/EN decisions into runtime configs, promote reviewed
  Chinese rows if they supersede YAML, then report library-score/codebook
  disagreement rates.
- [ ] Chinese social sentiment/topic pipeline: `scripts/build_chinese_social_media_dataset.py`
  builds cleaned Chinese social outputs with transparent lexicon sentiment.
  Still needed: manual body-text completion, SnowNLP sentiment stage, and broader
  topic/enjoyment config wiring for presentation comparisons.
- [x] JP-EN Google review library sentiment: `scripts/build_sentiment_analysis.py`
  filters by Fukui prefecture metadata, scores English reviews with VADER,
  scores Japanese reviews with oseti, writes ignored row-level output, and tracks
  aggregate summaries/tests/readiness with hashes and dependency versions.
- [ ] Statistical comparison suite: JP-EN review-row tests, POI-level sensitivity,
  and POI cluster-bootstrap sensitivity exist. Still needed: decide whether final
  presentation summaries should weight POIs equally or by review volume, decide
  whether a clustered/covariate model is justified, and add EN/JP/CN comparisons
  once Chinese sentiment/codebook outputs are ready.
- [ ] Presentation outputs: presentation-safe figures and captions are not built
  yet. Slides must carry POI mix, date range, source hashes, denominators, and
  source/platform caveats for any Japanese-language vs English-language review
  sentiment comparison.

## Expected Analysis Shape

Default pipeline should become:

1. Sync Google review artifacts with `make multilingual-reviews`.
2. Build Chinese social rows from `tourism-data` with `make chinese-social`.
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
