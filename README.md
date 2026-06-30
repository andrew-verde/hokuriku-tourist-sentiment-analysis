# Hokuriku Tourist Sentiment Analysis

Public research code and disclosure-safe evidence for cross-language tourism
text analysis in Hokuriku, with Fukui retained as the primary confirmatory
scope.

The project compares content-language/source groups, never inferred
nationalities:

- Chinese-language Google reviews: primary Chinese statistical evidence
- Chinese-language Xiaohongshu posts: Fukui-only directional evidence
- Japanese-language Google reviews
- English-language Google reviews

Google-review comparisons run at Fukui and Hokuriku scopes where documented.
See [repo guidance](docs/repo_guidance.md), [Chinese evidence strategy](docs/chinese_evidence_strategy.md),
and [sentiment comparison method](docs/sentiment_comparison_method.md).

POI-level aggregate tables may name public attractions but contain no reviewer
identity or review text. Small-cell and interpretation limits are documented in
their manifests/readiness notes.

Committed evidence supports method and aggregate-result audit. Full clean-room
rebuild requires separately obtained source data; platform-derived row-level
text cannot be redistributed here.

## Public artifact map

- `docs/statistical_tests.html`: reviewer-facing statistical test index
- `docs/statistical_test_outputs/`: stable aggregate result snapshots
- `docs/statistical_test_figures/`: SVG figures, indexes, manifests, questions
- `docs/statistical_test_figures_png/`: selected raster figure copies
- `output/chinese_specific_insights*/`: disclosure-safe Chinese aggregate tables/figures
- `output/cross_language_trends_hokuriku/`: Hokuriku aggregate comparisons
- `output/hypothesis_tests*/`, `output/within_language_sentiment/`: aggregate tests
- `output/nudge_analysis*/`: exploratory aggregate POI/aspect analysis
- `config/`, `docs/codebook_reviews/`, `docs/codebook_templates/`: reviewed evidence definitions

`output/` is normally a local build tree. Only explicitly reviewed aggregate
subtrees are tracked. Stable review snapshots under `docs/` let readers inspect
results without restricted inputs.

## Setup and tests

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python3 -m pytest
```

Pinned JP/EN sentiment runtime:

```bash
make sentiment-env
```

`oseti` uses `mecab-python3` plus `ipadic`. `pip check` may still report
`oseti requires mecab` because upstream metadata names legacy `mecab`; do not
change this environment without revalidating Japanese scores.

## Restricted-input rebuilds

Chinese social input:

```bash
TOURISM_DATA_DIR=/path/to/tourism-data make chinese-social
make chinese-insights
```

Google review input:

```bash
PLATFORM_REVIEW_SCRAPER_DIR=/path/to/platform-review-scraper make multilingual-reviews
make sentiment-analysis
make hypothesis-tests
make within-language-sentiment
make cross-language-trends
```

Hokuriku parallel analysis:

```bash
make hokuriku-all
```

Aggregate publication figures and their backing tables:

```bash
make presentation-safe
make statistical-test-figures
make nudge-all
```

These commands fail on missing required inputs; no demo/fallback data is used.

## Interpretation limits

- Reviewed keyword/codebook evidence is primary; VADER, oseti, and SnowNLP are
  secondary checks.
- VADER and oseti raw scores are different measurement scales. Compare category
  shares and within-tool distributions, not raw cross-language scores.
- SnowNLP sentiment is not a reportable Chinese outcome in current short-review
  data; Chinese Google star ratings and reviewed keyword evidence carry analysis.
- Review rows are nested in POIs and group sizes are imbalanced. Current
  review-row, POI-level, and cluster-bootstrap p-values remain descriptive.
- Platform, POI mix, collection window, and language-source differences prevent
  nationality or population-representative claims.
- Nudge/POI outputs are exploratory opportunity screens, not causal evidence or
  intervention-effect estimates.

## Data safety and citation

Never commit row-level text, people identifiers, URLs, screenshots, or private
captures. See [public release policy](docs/public_release.md) before adding data.

No repository license or citation metadata is currently declared. Public
visibility alone does not grant reuse rights. Add an owner-approved `LICENSE`,
data/figure terms, and `CITATION.cff` before soliciting third-party reuse.
