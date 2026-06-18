# AGENTS.md

Local agent notes.

## Scope

This repo is for Hokuriku cross-language tourism text sentiment/topic analysis.

Do not import FTAS SEM thesis logic here unless user explicitly asks.

## Data Guardrails

- Do not commit row-level post/review text.
- Do not commit author names, handles, URLs, screenshots, or raw manual captures.
- Do not commit `data/raw/`, `data/processed/`, or row-level `output/`.
- Keep raw inputs in external repos/folders, especially `tourism-data`.
- Prefer fail-loud missing-input errors over demo/fallback data.
- Use "Chinese-language posts", "Japanese-language reviews", "English-language reviews"; do not infer nationality.

## Commands

```bash
.venv/bin/pip install -r requirements.txt
.venv/bin/python3 -m pytest
TOURISM_DATA_DIR=/Users/andrewgreen/Repositories/tourism-data make chinese-social
make cross-language-trends
```

## Method

Primary analysis should be transparent:
- reviewed keyword codebooks
- matched term evidence
- explicit caveats for source/platform differences

Model sentiment tools may be added as secondary checks, not silent replacements.
