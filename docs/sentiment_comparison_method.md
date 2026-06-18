# Sentiment Comparison Method

This note defines the programming contract for comparing Chinese-language
Xiaohongshu posts with English-language Google reviews in the Fukui-first side
project. Group labels describe content language and source platform, not
nationality.

## Source Inputs

Chinese-language posts use the `fukui_xhs_reviews` sheet from:

```text
docs/codebook_reviews/source/fukui_xhs_reviews_manual.xlsx
```

The sheet may be exported as UTF-8 CSV before analysis. Required columns:

```text
note_id,title,note_url,author,author_url,body_text,capture_notes
```

English-language reviews use the synced Google review table:

```text
output/multilingual_review_analysis/reviews_multilingual.csv
```

Filter English reviews to:

```text
city == "Fukui"
language_group == "english"
```

Keep row-level text outputs under ignored `output/` paths. Do not commit source
post/review text, URLs, author fields, screenshots, or row-level sentiment
tables.

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

## Sentiment Categories

English VADER categories use standard `compound` thresholds:

```text
positive: compound >= 0.05
neutral: -0.05 < compound < 0.05
negative: compound <= -0.05
```

Chinese SnowNLP categories should use a documented centered-score threshold:

```text
positive: snownlp_centered_score >= 0.05
neutral: -0.05 < snownlp_centered_score < 0.05
negative: snownlp_centered_score <= -0.05
```

These thresholds make the category cut points symmetric, but they do not make
the two raw score scales identical. Main claims should be about category shares
and model-specific score distributions, not direct equality of raw scores.

## Statistical Comparison

Primary comparison:

```text
Chinese-language non-fan XHS posts with body_text
vs
English-language Fukui Google reviews
```

Recommended tests:

```text
chi-square or Fisher exact: source_group x sentiment_category
Mann-Whitney U: centered sentiment score distributions
bootstrap 95% CI: mean/median score difference within the selected tools
logistic regression: positive_vs_not ~ source_group + text_length_chars + month
```

Add covariates only when present and comparable. If Chinese posts cannot be
mapped to POI category, do not control English reviews by POI category in the
main model. If theme/topic tags exist for both groups later, add a second model:

```text
positive_vs_not ~ source_group + text_length_chars + month + topic
```

## Aggregate Outputs

Commit-safe aggregate outputs should avoid row-level text and source IDs:

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
command
generated_at
```

Readiness report must include:

```text
input paths
commands
dependency versions
row filters
denominators
excluded title-only count
excluded fan count
score interpretation caveat
source/platform caveat
```

## Caveat Language

Use this interpretation boundary in reports:

```text
Sentiment scores come from different language-specific tools: VADER for
English-language Google reviews and SnowNLP for Chinese-language Xiaohongshu
posts. Category shares and distribution tests are reproducible under this
pipeline, but raw score levels are not evidence that one language/source group
is intrinsically more positive or negative. Source platform, text length, topic
mix, and posting intent differ.
```
