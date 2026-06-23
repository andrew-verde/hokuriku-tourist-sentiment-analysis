# Chinese-Specific Insight Outputs

These outputs cover Chinese-language Fukui social-media rows. They are aggregate views for presentation and exploratory review, not nationality claims.

- Analysis label: `Chinese-language Fukui social-media rows`
- Rows represented: 200
- Source platform mix: {'xiaohongshu': 200}
- Minimum theme slice rows for rates: 10
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
- Sentiment categories use SnowNLP as a secondary baseline; reviewed positive/negative/recommendation keyword matches are transparent evidence.
- Theme rates and sentiment means are suppressed below n=10; counts remain in CSV outputs.
- Theme labels come from companion processed annotation files; unmatched rows are `unclassified`. Douyin is excluded from the main theme analysis until further notice.
- Outputs intentionally omit row-level source text, authors, URLs, and record IDs.