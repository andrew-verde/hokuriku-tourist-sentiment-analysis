# Hokuriku Tourist Sentiment Analysis

Fukui-first cross-language tourism text project.

Project brief and readiness map: [docs/repo_guidance.md](docs/repo_guidance.md).

Scope:
- Chinese Xiaohongshu / Douyin post text, titles, metadata from `tourism-data`
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

Build Chinese social outputs from local `tourism-data`:

```bash
TOURISM_DATA_DIR=/Users/andrewgreen/Repositories/tourism-data make chinese-social
```

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

The current Chinese analysis still supports friction keywords, but project aim is
broader topic and sentiment analysis. Future work should promote the reviewed
multilingual keyword CSV into a first-class config.

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
data/raw/social/*douyin*.csv
data/processed/*.csv
```

Supported current columns:

```text
XHS: note_id,title,note_url,author,author_url
Douyin: video_id,title,video_url,author
Future manual body text: text,description,or content
```

## Research Boundary

This repo is not thesis SEM friction-analysis repo. Treat all outputs as
cross-language descriptive/sentiment side-project artifacts unless separately
validated.
