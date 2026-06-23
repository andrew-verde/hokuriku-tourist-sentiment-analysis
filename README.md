# Hokuriku Tourist Sentiment Analysis

Fukui-first cross-language tourism text project.

Project brief and readiness map: [docs/repo_guidance.md](docs/repo_guidance.md).

Scope:
- Chinese Xiaohongshu note text from `tourism-data`; Douyin is temporarily
  excluded from the main pipeline and kept for explicit source-sensitivity runs
- English/Japanese review text when explicitly provided as cleaned inputs
- Transparent keyword/topic/sentiment codebooks
- Secondary library sentiment checks: VADER for English, oseti for Japanese,
  SnowNLP for Chinese
- Fukui Prefecture as the initial analysis scope; Ishikawa/Toyama Google review
  data can support later comparison, but should be filtered out by default for
  initial results.

Out of scope:
- FTAS / Code for Fukui SEM thesis pipeline
- Official survey friction SEM
- Nudge ranking
- Public release of raw row-level social/review text

## Data Safety

Do not commit:
- raw post/review text
- author names or handles
- source URLs
- row-level normalized outputs
- screenshots
- manually collected body text
- API keys or `.env`

Keep data external. Point scripts at local data:

```bash
TOURISM_DATA_DIR=/Users/andrewgreen/Repositories/tourism-data make chinese-social
```

## Commands

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python3 -m pytest
```

Install the pinned JP-EN sentiment runtime:

```bash
make sentiment-env
```

Build Chinese social outputs from local `tourism-data`. The main target now
normalizes Xiaohongshu rows only before applying SnowNLP plus reviewed
friction/topic/positive-evidence codebook matching. Douyin is temporarily
excluded from the main pipeline for clarity:

```bash
TOURISM_DATA_DIR=/Users/andrewgreen/Repositories/tourism-data make chinese-social
```

Build Chinese-specific presentation figures and supporting aggregate data views:

```bash
make chinese-insights
```

This writes tracked, aggregate-only outputs under
`output/chinese_specific_insights/`, including SVG figures for category
topic occurrence by positive/negative sentiment, top reviewed sentiment
keywords, platform sentiment shares, and theme volume. The figure generator uses the Python standard library plus
`pandas`, which is already listed in `requirements.txt`; no extra plotting
package is required. The companion CSV files preserve the denominators behind
each figure and omit row-level text, authors, URLs, and source record IDs.
Theme figures show classified themes only; the backing CSV keeps
`unclassified` for Xiaohongshu rows without joined companion theme annotations.
Parsed Douyin comments are not used in the main theme annotation analysis until
further notice.

Sync Google review artifacts from the local `english-fukui-tourism` clone. If
that directory is absent, the script uses the current local clone path
`/Users/andrewgreen/Repositories/andrew-verde/america-fukui-tourism`, whose Git
remote is `andrew-verde/english-fukui-tourism`. This copies
`output/checkpoints/` and `output/multilingual_review_analysis/` only; survey
outputs remain excluded.

```bash
make multilingual-reviews
```

Build cross-language trend tables after cleaned English/Japanese review rows exist:

```bash
make cross-language-trends
```

Build Fukui JP-EN sentiment aggregates:

```bash
make sentiment-analysis
```

Run professor-readable H1/H2/H3 JP-EN hypothesis test scripts from the ignored
scored-review audit file:

```bash
make hypothesis-tests
```

This writes aggregate-only CSV and manifest files under
`output/hypothesis_tests/` for:

```text
H1 sentiment category chi-square with neutral-band sensitivity
H2 Google star-rating Welch tests with POI-level sensitivity
H3 reviewed evidence prevalence tests with Benjamini-Hochberg FDR
```

Run within-language/source sentiment driver tests:

```bash
make within-language-sentiment
```

This writes aggregate-only `WL-EN-*`, `WL-JP-*`, and `WL-CN-*` driver outputs
under `output/within_language_sentiment/`.

Build slide-safe JP-EN aggregate chart/table scaffolding from tracked aggregate
sentiment outputs and locally generated cross-language baseline tables:

```bash
make presentation-safe
```

This writes aggregate-only files under `output/presentation_safe/`:

```text
japanese/
english/
multilingual/
jp_en_library_sentiment_chart_data.csv
jp_en_statistical_sensitivity_summary.csv
presentation_figure_questions.md
presentation_readiness.md
presentation_manifest.json
```

The presentation scaffold carries denominators, source hashes, caveats, date
ranges, date coverage counts, POI-category mix, and SVG figures. Japanese and
English folders contain language-specific sentiment/POI-priority figures; the
multilingual folder contains cross-language sentiment-share, volume-context, and
statistical-readiness figures. `presentation_figure_questions.md` documents what
question each figure answers. Date range and POI mix are derived as aggregate
metadata from the ignored scored-review audit file named in the sentiment
manifest; if required metadata is missing, the command fails instead of writing
placeholder figure data.

## Japanese Sentiment: oseti

`oseti` is a deterministic Japanese sentiment analyzer. It uses MeCab tokenizing
and polarity dictionaries to score Japanese text without calling a remote model.

In this project, `oseti` is the Japanese-language counterpart to English VADER
for Google review sentiment. It is a secondary library check alongside reviewed
keyword/codebook evidence, not a replacement for human-auditable codebooks.

For each Japanese review row, the sentiment pipeline writes ignored row-level
fields:

```text
oseti_sentence_scores
oseti_doc_score
oseti_positive_count
oseti_negative_count
sentiment_category
```

`oseti_doc_score` is the mean of sentence scores. Categories use the shared
threshold rule: positive `>= 0.05`, negative `<= -0.05`, neutral between those
bounds. Tracked aggregate outputs keep only counts, tests, hashes, dependency
versions, and readiness notes.

## Codebook Review

Review templates live in `output/codebook_review/`. These are keyword lists only,
not source text.

The current Chinese analysis promotes reviewed Chinese codebook rows into the
runtime evidence layer for friction, topic, and sentiment/recommendation terms.
Legacy YAML friction terms remain documented, but reviewed rows supersede YAML
terms for matching codes.

Durable codebook and sentiment method notes:

```text
docs/codebook_reviews/source/
docs/codebook_templates/
config/chinese_social_friction_codebook.yaml
docs/sentiment_comparison_method.md
```

## Inputs Expected

Raw social files, outside Git:

```text
data/raw/social/*xhs*.csv
data/raw/social/*douyin*.csv for explicit source-sensitivity runs only
data/processed/fukui_douyin_comments_from_md.csv for explicit source-sensitivity runs only
data/processed/*.csv for theme annotations
```

Supported current columns:

```text
XHS: note_id,title,note_url,author,author_url
Douyin: video_id,title,video_url,author
Douyin comments: source_record_id,comment_text,relative_time,parse_confidence,parse_notes,source_start_line,source_end_line
Manual body/comment text: body_text,comment_text,text,description,or content
```

Parsed Douyin comment exports must preserve parser-line provenance and the
`local_record_id_not_platform_comment_id` caveat in `parse_notes`.

## Research Boundary

This repo is not thesis SEM friction-analysis repo. Treat all outputs as
cross-language descriptive/sentiment group project artifacts unless separately
validated.
