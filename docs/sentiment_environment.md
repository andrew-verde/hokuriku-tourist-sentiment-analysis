# Sentiment Environment Reproducibility

This repository separates the base analysis environment from the JP-EN
sentiment runtime.

## Base Environment

Install base project requirements:

```bash
.venv/bin/pip install -r requirements.txt
```

This file intentionally excludes `oseti`, because `oseti==0.4.3.1` declares the
legacy `mecab` package. On macOS and Python 3.14 that dependency tries to build
from source and fails without system `mecab-config`.

## JP-EN Sentiment Runtime

Install the pinned JP-EN sentiment stack with:

```bash
.venv/bin/python3 scripts/bootstrap_sentiment_environment.py
```

The bootstrap uses `requirements-sentiment.lock.txt` as the exact package list.
It installs the MeCab-compatible runtime stack first:

```text
mecab-python3==1.0.12
ipadic==1.0.0
bunkai==1.5.2
emoji==1.7.0
```

Then it installs:

```text
oseti==0.4.3.1 --no-deps
```

This is deliberate. Runtime imports use `mecab-python3` and `ipadic`, and
`scripts/build_sentiment_analysis.py` initializes oseti with:

```text
-r /dev/null -d <ipadic.DICDIR>
```

## Verification

After setup, run:

```bash
.venv/bin/python3 -m pytest
.venv/bin/python3 scripts/build_sentiment_analysis.py --groups japanese,english --city Fukui
```

The sentiment readiness report records installed versions, command, filters,
input hash, row-level output hash, denominators, and codebook-evidence status:

```text
output/sentiment_aggregates/sentiment_readiness.md
```

`pip check` may report:

```text
oseti 0.4.3.1 requires mecab, which is not installed.
```

Treat this as a known metadata mismatch, not a runtime failure, when the oseti
smoke test in `scripts/bootstrap_sentiment_environment.py` passes. The
reproducible runtime dependency is `mecab-python3` plus `ipadic`, not system
MeCab.
