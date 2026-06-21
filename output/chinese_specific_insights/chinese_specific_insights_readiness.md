# Chinese-Specific Insight Outputs

These outputs summarize Chinese-language Fukui social-media rows only. They are aggregate views for presentation and exploratory review, not nationality claims.

- Rows represented: 1670
- Source platform mix: {'douyin': 1521, 'xiaohongshu': 149}
- Output folder: `/home/andrewgreen/Repositories/andrew-verde/hokuriku-tourist-sentiment-analysis/output/chinese_specific_insights`

## Figures
- `figure_keyword_occurrence_by_category`: `/home/andrewgreen/Repositories/andrew-verde/hokuriku-tourist-sentiment-analysis/output/chinese_specific_insights/figure_keyword_occurrence_by_category.svg`
- `figure_top_sentiment_keywords`: `/home/andrewgreen/Repositories/andrew-verde/hokuriku-tourist-sentiment-analysis/output/chinese_specific_insights/figure_top_sentiment_keywords.svg`
- `figure_sentiment_category_by_platform`: `/home/andrewgreen/Repositories/andrew-verde/hokuriku-tourist-sentiment-analysis/output/chinese_specific_insights/figure_sentiment_category_by_platform.svg`
- `figure_theme_sentiment`: `/home/andrewgreen/Repositories/andrew-verde/hokuriku-tourist-sentiment-analysis/output/chinese_specific_insights/figure_theme_sentiment.svg`

## Data Views
- `keyword_inventory_by_category`: `/home/andrewgreen/Repositories/andrew-verde/hokuriku-tourist-sentiment-analysis/output/chinese_specific_insights/keyword_inventory_by_category.csv`
- `keyword_occurrence_by_category`: `/home/andrewgreen/Repositories/andrew-verde/hokuriku-tourist-sentiment-analysis/output/chinese_specific_insights/keyword_occurrence_by_category.csv`
- `sentiment_keyword_counts`: `/home/andrewgreen/Repositories/andrew-verde/hokuriku-tourist-sentiment-analysis/output/chinese_specific_insights/sentiment_keyword_counts.csv`
- `keywords_by_snownlp_sentiment_category`: `/home/andrewgreen/Repositories/andrew-verde/hokuriku-tourist-sentiment-analysis/output/chinese_specific_insights/keywords_by_snownlp_sentiment_category.csv`
- `sentiment_category_by_platform`: `/home/andrewgreen/Repositories/andrew-verde/hokuriku-tourist-sentiment-analysis/output/chinese_specific_insights/sentiment_category_by_platform.csv`
- `theme_sentiment_summary`: `/home/andrewgreen/Repositories/andrew-verde/hokuriku-tourist-sentiment-analysis/output/chinese_specific_insights/theme_sentiment_summary.csv`
- `topic_by_sentiment_category`: `/home/andrewgreen/Repositories/andrew-verde/hokuriku-tourist-sentiment-analysis/output/chinese_specific_insights/topic_by_sentiment_category.csv`
- `friction_by_sentiment_category`: `/home/andrewgreen/Repositories/andrew-verde/hokuriku-tourist-sentiment-analysis/output/chinese_specific_insights/friction_by_sentiment_category.csv`

## Caveats

- Keyword evidence uses reviewed substring matches and should be described as evidence counts, not inferred motives.
- Sentiment categories use SnowNLP as the current baseline; reviewed positive/negative/recommendation keyword matches are transparent secondary evidence.
- Theme labels come from companion processed annotation files; unmatched rows are `unclassified`, currently almost entirely parsed Douyin comments.
- Outputs intentionally omit row-level source text, authors, URLs, and record IDs.