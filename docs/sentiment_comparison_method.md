# Sentiment Comparison Method

This note defines the programming contract for comparing Chinese-language
Xiaohongshu posts, Japanese-language Google reviews, and English-language Google
reviews in the Fukui-first side project. Group labels describe content language
and source platform, not nationality.

## Source Inputs

Chinese-language posts use the `fukui_xhs_reviews` sheet from:

```text
docs/codebook_reviews/source/fukui_xhs_reviews_manual.xlsx
```

The sheet may be exported as UTF-8 CSV before analysis. Required columns:

```text
note_id,title,note_url,author,author_url,body_text,capture_notes
```

Japanese-language and English-language reviews use the synced Google review
table:

```text
output/multilingual_review_analysis/reviews_multilingual.csv
```

Filter Google reviews to:

```text
city == "Fukui"
language_group in ["english", "japanese"]
```

Keep row-level text outputs under ignored `output/sentiment_row_level/` paths.
Do not commit source post/review text, URLs, author fields, screenshots, source
IDs, or row-level sentiment tables. Track aggregate sentiment outputs when they
contain only counts, statistics, filters, commands, dependency versions, and
input provenance. Include SHA256 hashes for ignored source inputs and row-level
intermediate files so outputs remain reproducible without committing PII-bearing
data.

## Scope Rules

Primary statistical comparison should use non-fan Chinese-language posts only.
Fan-pilgrimage posts are a valid descriptive subgroup, but fandom is currently a
source-specific theme in the Chinese data and should not be mixed into the main
cross-source test unless matching fandom evidence is built for English-language
reviews.

Primary Chinese sentiment rows should require non-empty `body_text`. Title-only
rows can be scored during early build-out for smoke tests, but exclude them from
published comparison tables. Report:

```text
n_total_xhs_rows
n_with_body_text
n_title_only_excluded
n_non_fan_compared
```

## Tool Choice

Use `vaderSentiment` for English-language reviews. VADER is a lexicon and
rule-based sentiment tool designed for social-media-style text and returns
`neg`, `neu`, `pos`, and normalized `compound` scores.

Use `oseti` for Japanese-language reviews as the primary VADER-type Japanese
sentiment tool. `oseti` is a dictionary-based Japanese polarity analyzer that
returns sentence-level polarity scores and positive/negative polarity evidence.
It is preferred here over transformer-based sentiment models because the method
is deterministic, inspectable, lightweight, and close to VADER's lexicon/rule
logic. Pin the exact `oseti` package version and hashes in the environment lock
file before publishing results.

Do not label `oseti` scores as VADER scores. Store them as:

```text
oseti_sentence_scores
oseti_doc_score = mean(oseti_sentence_scores)
oseti_positive_count
oseti_negative_count
```

Use `SnowNLP` for Chinese-language posts as the primary pre-built Chinese
sentiment library. It returns `sentiments`, interpreted as estimated positive
sentiment probability in `[0, 1]`. SnowNLP documentation warns that its built-in
sentiment model is mainly trained on product review data, so results need domain
caveats for tourism narratives and fandom language.

Do not label SnowNLP scores as VADER scores. Store them as:

```text
snownlp_positive_prob
snownlp_centered_score = (snownlp_positive_prob * 2) - 1
```

Use the reviewed codebook files as audit and sensitivity inputs:

```text
docs/codebook_reviews/source/multilingual_keyword_codebook_review.xlsx
docs/codebook_templates/chinese_reviewed_codebook_template.csv
config/chinese_social_friction_codebook.yaml
```

For sentiment terms in reviewed codebook rows, preserve reviewer decision,
replacement term, reviewer, and review date when promoting them into runtime
configs. Codebook matches should be reported as transparent evidence, not as a
silent replacement for the pre-built sentiment library.

Japanese-language sentiment should use a dual-path design:

1. Primary score path: `oseti` polarity scores and categories.
2. Evidence path: reviewed Japanese keyword codebook matches for polarity,
   recommendation intent, friction, and enjoyment terms.

The evidence path supports audit and sensitivity checks. It should not silently
override the primary `oseti` score. If the two paths disagree, preserve both and
report the disagreement rate by language group and topic/friction category.
The JP-EN library sentiment comparison may run before Japanese and English
reviewed codebooks are complete, as long as readiness output clearly marks the
codebook evidence path as pending. Once reviewed codebooks are complete, promote
them into runtime configs and add the evidence columns without changing the
library-score definitions.

## Row-Level Fields

Chinese ignored row-level output:

```text
record_id
note_id
city
source_platform
theme
title_has_text
body_has_text
text_scope
text_length_chars
post_date
post_date_precision
snownlp_positive_prob
snownlp_centered_score
sentiment_category
reviewed_positive_terms_matched
reviewed_negative_terms_matched
reviewed_recommendation_terms_matched
```

English ignored row-level output:

```text
review_id
city
poi_id
poi_category
review_date
review_rating
text_length_chars
vader_neg
vader_neu
vader_pos
vader_compound
sentiment_category
```

Japanese ignored row-level output:

```text
review_id
city
poi_id
poi_category
review_date
review_rating
text_length_chars
oseti_sentence_scores
oseti_doc_score
oseti_positive_count
oseti_negative_count
sentiment_category
reviewed_positive_terms_matched
reviewed_negative_terms_matched
reviewed_recommendation_terms_matched
reviewed_friction_terms_matched
reviewed_enjoyment_terms_matched
```

## Sentiment Categories

English VADER categories use standard `compound` thresholds:

```text
positive: compound >= 0.05
neutral: -0.05 < compound < 0.05
negative: compound <= -0.05
```

Japanese `oseti` categories should use the same symmetric threshold on
`oseti_doc_score`:

```text
positive: oseti_doc_score >= 0.05
neutral: -0.05 < oseti_doc_score < 0.05
negative: oseti_doc_score <= -0.05
```

Chinese SnowNLP categories should use a documented centered-score threshold:

```text
positive: snownlp_centered_score >= 0.05
neutral: -0.05 < snownlp_centered_score < 0.05
negative: snownlp_centered_score <= -0.05
```

These thresholds make category cut points symmetric, but they do not make raw
score scales identical. Main claims should be about category shares and
tool-specific score distributions, not direct equality of raw scores.

Use the `±0.05` thresholds as the primary reproducible rule for English,
Japanese, and Chinese sentiment categories. For JP-EN reporting, add sensitivity
tables with wider neutral bands:

```text
neutral_0_10: positive >= 0.10, neutral between -0.10 and 0.10, negative <= -0.10
neutral_0_20: positive >= 0.20, neutral between -0.20 and 0.20, negative <= -0.20
```

These sensitivity tables test whether JP-EN conclusions depend on narrow neutral
classification. They do not replace the primary threshold rule.

## Statistical Comparison

Full comparison suite should support all pairwise and three-way source/language
views when data are ready:

```text
Japanese-language Fukui Google reviews vs English-language Fukui Google reviews
Japanese-language Fukui Google reviews vs Chinese-language non-fan XHS posts
English-language Fukui Google reviews vs Chinese-language non-fan XHS posts
Japanese-language vs English-language vs Chinese-language groups
```

Current implementation priority is the English-Japanese Google-review
comparison, because source platform is held constant:

```text
Japanese-language Fukui Google reviews
vs
English-language Fukui Google reviews
```

For JP-EN, the primary unit of analysis is one Google review row. Do not
aggregate to one row per POI-language bucket for the primary model, because that
throws away text-level variation and reduces power, especially for
English-language reviews. Report POI and POI-category imbalance, then run
POI-level or cluster-aware sensitivity checks when model support is available.

Recommended tests:

```text
chi-square or Fisher exact: source_group x sentiment_category
Mann-Whitney U: centered sentiment score distributions
bootstrap 95% CI: mean/median score difference within the selected tools
logistic regression: positive_vs_not ~ source_group + text_length_chars + month
```

For this current JP-EN comparison, use `review_rating` only as descriptive
validation. Report rating distribution by language group and correlation between
rating and sentiment score/category. Do not control for rating in the main JP-EN
model unless a later research question explicitly needs that sensitivity check.
Ratings are platform-native outcomes and may partly encode sentiment, so
controlling for them can remove the signal being studied.

Add covariates only when present and comparable. For JP-EN, comparable covariates
can include `text_length_chars`, `month`, and `poi_category`. For comparisons
involving Chinese-language posts, if Chinese posts cannot be mapped to POI
category, do not control Google reviews by POI category in the main model. If
theme/topic tags exist for all compared groups later, add a second model:

```text
positive_vs_not ~ source_group + text_length_chars + month + topic
```

Sentence-level scores are diagnostic evidence, not the primary inferential unit.
For Japanese-language reviews, keep `oseti_sentence_scores` because `oseti`
returns sentence-level polarity and those scores help audit mixed reviews. For
English-language reviews, optional sentence-level VADER output may be generated
for parity checks. Published JP-EN tests should aggregate sentence scores back to
one score per review before statistical comparison. Sentence rows are nested
inside reviews, are not independent observations, and Japanese sentence boundary
segmentation can differ from English punctuation behavior.

## Aggregate Outputs

Implement sentiment analysis as a general pipeline with JP-EN as the first
complete mode, not as a one-off JP-EN script. Preferred entrypoint:

```text
scripts/build_sentiment_analysis.py
```

Initial command should focus on JP-EN:

```text
.venv/bin/python3 scripts/build_sentiment_analysis.py --groups japanese,english --city Fukui
```

The script should keep a group-aware structure so Chinese-language posts can be
added later without migrating outputs or method names. Fail loudly when requested
groups lack required inputs or dependencies.

Keep `requirements.txt` human-readable with minimum supported versions for
development. Before publishing or presenting sentiment outputs, generate and
commit `requirements.lock.txt` with exact package versions and hashes. Until that
lock file exists, readiness output must report exact installed versions from the
run environment.

Commit-safe aggregate outputs should avoid row-level text and source IDs. Track
these aggregate files in Git for academic reproducibility:

```text
output/sentiment_aggregates/source_group_sentiment_summary.csv
output/sentiment_aggregates/source_group_sentiment_tests.csv
output/sentiment_aggregates/sentiment_readiness.md
```

Summary columns:

```text
source_group
city
text_scope
theme_filter
n
n_body_text
score_mean
score_median
score_sd
positive_n
neutral_n
negative_n
positive_pct
neutral_pct
negative_pct
input_path
input_sha256
row_level_output_sha256
command
generated_at
```

Readiness report must include:

```text
input paths
input SHA256 hashes
row-level intermediate SHA256 hashes
commands
dependency versions
row filters
denominators
excluded title-only count
excluded fan count
codebook evidence status
score interpretation caveat
source/platform caveat
```

## Caveat Language

Use this interpretation boundary in reports:

```text
Sentiment scores come from different language-specific tools: VADER for
English-language Google reviews, oseti for Japanese-language Google reviews,
and SnowNLP for Chinese-language Xiaohongshu posts. Category shares and
distribution tests are reproducible under this pipeline, but raw score levels
are not evidence that one language/source group is intrinsically more positive
or negative. Source platform, text length, topic mix, and posting intent differ.
```

## Method References

- Hutto, C. J., & Gilbert, E. (2014). VADER: A parsimonious rule-based model for
  sentiment analysis of social media text. International AAAI Conference on Web
  and Social Media.
- Ikegami, Y. `oseti`: Dictionary based sentiment analysis for Japanese.
  <https://github.com/ikegami-yukino/oseti>
- `oseti` PyPI package metadata, version 0.4.3.1 released 2025-08-02.
  <https://pypi.org/project/oseti/>
- Kobayashi, N., Inui, K., Matsumoto, Y., & Tateishi, K. (2005). Collecting
  evaluative expressions for opinion extraction. Journal of Natural Language
  Processing, 12(3), 203-222.
- Higashiyama, M., Inui, K., & Matsumoto, Y. (2008). Learning sentiment of nouns
  from selectional preferences of verbs and adjectives. Proceedings of the 14th
  Annual Meeting of the Association for Natural Language Processing, 584-587.
