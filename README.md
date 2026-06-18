# Hokuriku Tourist Sentiment Analysis

Separate cross-language tourism text project.

Scope:
- Chinese Xiaohongshu / Douyin post text, titles, metadata from `tourism-data`
- English/Japanese review text when explicitly provided as cleaned inputs
- Transparent keyword/topic/sentiment codebooks
- Optional model comparison later, e.g. SnowNLP, BosonNLP, transformer models

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

Build Chinese social outputs from local `tourism-data`:

```bash
TOURISM_DATA_DIR=/Users/andrewgreen/Repositories/tourism-data make chinese-social
```

Build cross-language trend tables after cleaned English/Japanese review rows exist:

```bash
make cross-language-trends
```

## Codebook Review

Review templates live in `output/codebook_review/`. These are keyword lists only,
not source text.

The current Chinese analysis still supports friction keywords, but project aim is
broader topic and sentiment analysis. Future work should promote the reviewed
multilingual keyword CSV into a first-class config.

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
