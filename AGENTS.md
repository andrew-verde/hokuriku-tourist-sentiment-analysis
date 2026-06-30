# AGENTS.md

Contributor and automation guardrails.

## Scope

This repo is for Fukui-first cross-language tourism text sentiment/topic
analysis across Chinese-language social posts, Japanese-language Google reviews,
and English-language Google reviews.

Use `docs/repo_guidance.md` as the durable project brief before planning major
analysis work.

Do not import FTAS SEM thesis logic here unless user explicitly asks.

## Data Guardrails

- Do not commit row-level post/review text.
- Do not commit author names, handles, URLs, screenshots, or raw manual captures.
- Do not commit `data/raw/`, `data/processed/`, or row-level `output/`.
- Commit reviewed, disclosure-safe aggregate tables, manifests, statistical
  outputs, and figures needed for academic audit.
- Keep slides, decks, speaker documents, dashboards, and delivery-only
  generation scripts private.
- Keep agent scratchpads, handoffs, and machine-specific state private.
- Keep raw inputs in external repos/folders, especially `tourism-data`.
- Prefer fail-loud missing-input errors over demo/fallback data.
- Use "Chinese-language posts", "Japanese-language reviews", "English-language reviews"; do not infer nationality.
- Default analysis scope is Fukui Prefecture. Ishikawa/Toyama Google data exists
  for later comparison, but do not expand scope unless requested.

## Codebooks

- Human review sources: `docs/codebook_reviews/source/`
- Exported review templates: `docs/codebook_templates/`
- Current Chinese friction runtime config: `config/chinese_social_friction_codebook.yaml`
- Treat reviewed codebook CSV rows as audit evidence and runtime config inputs;
  do not paste row-level source text into codebooks.
- For sentiment comparison planning, read `docs/sentiment_comparison_method.md`.

## Commands

```bash
.venv/bin/pip install -r requirements.txt
.venv/bin/python3 -m pytest
TOURISM_DATA_DIR=/path/to/tourism-data make chinese-social
ENGLISH_FUKUI_TOURISM_DIR=/path/to/english-fukui-tourism make multilingual-reviews
make cross-language-trends
```

## Method

Primary analysis should be transparent:
- reviewed keyword codebooks
- matched term evidence
- explicit caveats for source/platform differences
- source files and review decisions preserved for academic audit trail
- every generated result tied back to a documented input and reproducible command

Model sentiment tools may be added as secondary checks, not silent replacements.

Academic rigor is a repo-wide requirement. Prefer provenance, reviewed
codebooks, explicit denominators, reproducible scripts, and fail-loud errors over
ad hoc outputs or undocumented manual changes.

## Critical Academic Review Notes

- JP-EN output includes reviewed codebook evidence plus library-score checks.
  Treat VADER and oseti as secondary; preserve disagreement rates.
- Current JP-EN tests include review-row, POI-level, and POI cluster-bootstrap
  sensitivity checks. Because rows are nested in POIs and sample sizes are
  imbalanced, treat p-values as descriptive unless a later, explicitly justified
  clustered/covariate model is added.
- VADER compound and oseti document scores are not the same measurement scale.
  Compare category shares and within-tool distributions; do not claim raw score
  equivalence across languages.
- Google review rows come from a local Outscraper-derived cache and may reflect
  collection order/window and POI mix. Preserve denominators, date ranges,
  source hashes, and POI imbalance notes in any publication output.
- The oseti runtime is reproducible through
  `scripts/bootstrap_sentiment_environment.py`; `pip check` may still report
  `oseti requires mecab` because oseti metadata names legacy `mecab`. Runtime
  uses `mecab-python3` plus `ipadic`; do not "fix" this without revalidating
  Japanese scores.
