# Chinese-Specific Insight Outputs

These outputs cover Chinese-language Fukui Xiaohongshu rows only. They are aggregate views for presentation and exploratory review, not nationality claims.

- Analysis label: `Chinese-language Fukui Xiaohongshu rows only`
- Rows represented: 200
- Source platform mix: {'xiaohongshu': 200}
- Minimum theme slice rows for rates: 10
- Output folder: `output/chinese_specific_insights_xhs_only`

## Figures
- `figure_keyword_occurrence_by_category`: `output/chinese_specific_insights_xhs_only/figure_keyword_occurrence_by_category.svg`
- `figure_top_sentiment_keywords`: `output/chinese_specific_insights_xhs_only/figure_top_sentiment_keywords.svg`
- `figure_sentiment_category_by_platform`: `output/chinese_specific_insights_xhs_only/figure_sentiment_category_by_platform.svg`
- `figure_theme_sentiment`: `output/chinese_specific_insights_xhs_only/figure_theme_sentiment.svg`

## Data Views
- `keyword_inventory_by_category`: `output/chinese_specific_insights_xhs_only/keyword_inventory_by_category.csv`
- `keyword_occurrence_by_category`: `output/chinese_specific_insights_xhs_only/keyword_occurrence_by_category.csv`
- `sentiment_keyword_counts`: `output/chinese_specific_insights_xhs_only/sentiment_keyword_counts.csv`
- `keywords_by_snownlp_sentiment_category`: `output/chinese_specific_insights_xhs_only/keywords_by_snownlp_sentiment_category.csv`
- `sentiment_category_by_platform`: `output/chinese_specific_insights_xhs_only/sentiment_category_by_platform.csv`
- `theme_sentiment_summary`: `output/chinese_specific_insights_xhs_only/theme_sentiment_summary.csv`
- `topic_by_sentiment_category`: `output/chinese_specific_insights_xhs_only/topic_by_sentiment_category.csv`
- `friction_by_sentiment_category`: `output/chinese_specific_insights_xhs_only/friction_by_sentiment_category.csv`

## Caveats

- Keyword evidence uses reviewed substring matches and should be described as evidence counts, not inferred motives.
- Sentiment categories use SnowNLP as a secondary baseline; reviewed positive/negative/recommendation keyword matches are transparent evidence.
- Theme rates and sentiment means are suppressed below n=10; counts remain in CSV outputs.
- Theme labels come from companion processed annotation files; unmatched rows are `unclassified`, currently almost entirely parsed Douyin comments in the combined variant.
- Outputs intentionally omit row-level source text, authors, URLs, and record IDs.