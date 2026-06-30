PYTHON = .venv/bin/python3
.PHONY: help test public-check chinese-codebook-template reviewed-codebook-config reviewed-codebook-status chinese-social chinese-social-xhs-only chinese-social-with-douyin chinese-insights chinese-insights-xhs-only multilingual-reviews chinese-folded-multilingual cross-language-trends sentiment-env sentiment-analysis hypothesis-h1 hypothesis-h2 hypothesis-h3 hypothesis-within-poi hypothesis-tests nudge-analysis poi-opportunity poi-opportunity-chinese-folded nudge-priorities nudge-figures nudge-all within-en-sentiment within-jp-sentiment within-cn-sentiment within-language-sentiment presentation-safe statistical-test-figures chinese-google-reviews sentiment-analysis-hokuriku hypothesis-tests-hokuriku cross-language-trends-hokuriku cn-anchor-figure hokuriku-all

help:
	@echo "Hokuriku tourist sentiment analysis"
	@echo ""
	@echo "  make chinese-codebook-template Export reviewed Chinese codebook CSV"
	@echo "  make reviewed-codebook-status Show JP/EN review completion counts"
	@echo "  make reviewed-codebook-config Import completed reviewed JP/EN codebook YAML"
	@echo "  make chinese-social          Build main Chinese XHS-only cleaned outputs"
	@echo "  make chinese-social-xhs-only Build compatibility XHS-only Chinese outputs"
	@echo "  make chinese-social-with-douyin Build explicit XHS/Douyin source-sensitivity outputs"
	@echo "  make chinese-insights        Build tracked Chinese-specific figure/data outputs"
	@echo "  make chinese-insights-xhs-only Build labeled XHS-only figure/data outputs"
	@echo "  make multilingual-reviews    Validate sibling platform-review-scraper Google review inputs"
	@echo "  make chinese-folded-multilingual Promote Chinese Google reviews in copied multilingual output"
	@echo "  make cross-language-trends   Build Fukui-first EN/JP/CN baseline tables"
	@echo "  make sentiment-env           Install pinned JP-EN sentiment runtime"
	@echo "  make sentiment-analysis      Build JP-EN sentiment aggregate outputs"
	@echo "  make hypothesis-h1           Run JP-EN sentiment category hypothesis test"
	@echo "  make hypothesis-h2           Run JP-EN star-rating hypothesis test"
	@echo "  make hypothesis-h3           Run JP-EN reviewed-evidence hypothesis tests"
	@echo "  make hypothesis-within-poi   Run within-POI paired JP-EN robustness check"
	@echo "  make hypothesis-tests        Run H1, H2, H3, and within-POI robustness scripts"
	@echo "  make nudge-analysis          Build aggregate aspect nudge opportunity map"
	@echo "  make poi-opportunity         Build aggregate POI nudge opportunity index"
	@echo "  make poi-opportunity-chinese-folded Build POI index from Chinese-folded multilingual output"
	@echo "  make nudge-priorities        Rank cross-language solution families"
	@echo "  make nudge-figures           Build aggregate nudge opportunity SVG figures"
	@echo "  make nudge-all               Build public aggregate nudge analyses and figures"
	@echo "  make within-en-sentiment     Run English within-language sentiment drivers"
	@echo "  make within-jp-sentiment     Run Japanese within-language sentiment drivers"
	@echo "  make within-cn-sentiment     Run Chinese within-source sentiment drivers"
	@echo "  make within-language-sentiment Run all within-language/source sentiment drivers"
	@echo "  make presentation-safe       Build slide-safe JP-EN aggregate scaffold"
	@echo "  make statistical-test-figures Build aggregate-only SVG figures for statistical tests"
	@echo "  make public-check            Scan tracked files for public-release violations"
	@echo "  make test                    Run pytest"

chinese-codebook-template:
	$(PYTHON) scripts/export_chinese_codebook_template.py

reviewed-codebook-status:
	$(PYTHON) scripts/import_reviewed_codebook_config.py --status-only

reviewed-codebook-config:
	$(PYTHON) scripts/import_reviewed_codebook_config.py

chinese-social:
	$(PYTHON) scripts/build_chinese_social_media_dataset.py

chinese-social-xhs-only:
	$(PYTHON) scripts/build_chinese_social_media_dataset.py --xhs-only --output-dir output/chinese_social_media_analysis_xhs_only

chinese-social-with-douyin:
	$(PYTHON) scripts/build_chinese_social_media_dataset.py --include-douyin

chinese-insights:
	$(PYTHON) scripts/build_chinese_specific_insights.py

chinese-insights-xhs-only:
	$(PYTHON) scripts/build_chinese_specific_insights.py --input-dir output/chinese_social_media_analysis_xhs_only --output-dir output/chinese_specific_insights_xhs_only --analysis-label "Chinese-language Fukui Xiaohongshu rows only"

multilingual-reviews:
	$(PYTHON) scripts/sync_google_review_data.py

chinese-folded-multilingual:
	$(PYTHON) scripts/build_chinese_folded_multilingual.py

cross-language-trends:
	$(PYTHON) scripts/build_cross_language_trends.py

# --- Hokuriku-wide (region-wide) parallel runs, alongside the Fukui defaults ---
chinese-google-reviews:
	$(PYTHON) scripts/build_chinese_google_reviews_dataset.py

sentiment-analysis-hokuriku:
	$(PYTHON) scripts/build_sentiment_analysis.py --groups japanese,english --prefecture "" --aggregate-output-dir output/sentiment_aggregates_hokuriku

hypothesis-tests-hokuriku: sentiment-analysis-hokuriku
	$(PYTHON) scripts/test_h1_sentiment_category_jp_en.py --input output/sentiment_row_level/google_reviews_all_japanese-english.csv --output-dir output/hypothesis_tests_hokuriku
	$(PYTHON) scripts/test_h2_review_rating_jp_en.py --input output/sentiment_row_level/google_reviews_all_japanese-english.csv --output-dir output/hypothesis_tests_hokuriku
	$(PYTHON) scripts/test_h3_reviewed_evidence_jp_en.py --input output/sentiment_row_level/google_reviews_all_japanese-english.csv --output-dir output/hypothesis_tests_hokuriku

cross-language-trends-hokuriku: chinese-google-reviews sentiment-analysis-hokuriku
	$(PYTHON) scripts/build_cross_language_trends.py --prefecture Hokuriku \
	  --chinese-path output/chinese_google_reviews_analysis/tagged_chinese_google_reviews.csv \
	  --sentiment-summary-path output/sentiment_aggregates_hokuriku/source_group_sentiment_summary.csv \
	  --output-dir output/cross_language_trends_hokuriku

cn-anchor-figure: cross-language-trends-hokuriku
	$(PYTHON) scripts/build_cn_anchor_comparison_figure.py

hokuriku-all: hypothesis-tests-hokuriku cross-language-trends-hokuriku cn-anchor-figure

sentiment-env:
	$(PYTHON) scripts/bootstrap_sentiment_environment.py

sentiment-analysis:
	$(PYTHON) scripts/build_sentiment_analysis.py --groups japanese,english --prefecture Fukui

hypothesis-h1:
	$(PYTHON) scripts/test_h1_sentiment_category_jp_en.py

hypothesis-h2:
	$(PYTHON) scripts/test_h2_review_rating_jp_en.py

hypothesis-h3:
	$(PYTHON) scripts/test_h3_reviewed_evidence_jp_en.py

hypothesis-within-poi:
	$(PYTHON) scripts/test_within_poi_paired_jp_en.py

hypothesis-tests: hypothesis-h1 hypothesis-h2 hypothesis-h3 hypothesis-within-poi

nudge-analysis: chinese-folded-multilingual
	$(PYTHON) scripts/build_nudge_opportunity_analysis.py

poi-opportunity: chinese-folded-multilingual
	$(PYTHON) scripts/build_poi_opportunity_index.py

poi-opportunity-chinese-folded: chinese-folded-multilingual
	$(PYTHON) scripts/build_poi_opportunity_index.py --input output/multilingual_review_analysis/tagged_reviews_multilingual_chinese_folded.csv --output-dir output/nudge_analysis_chinese_folded

nudge-figures:
	$(PYTHON) scripts/build_nudge_figures.py

nudge-priorities: nudge-analysis hypothesis-h3 within-cn-sentiment
	$(PYTHON) scripts/build_cross_language_solution_priorities.py

nudge-all: nudge-analysis poi-opportunity nudge-priorities nudge-figures

within-en-sentiment:
	$(PYTHON) scripts/test_en_within_language_sentiment_drivers.py

within-jp-sentiment:
	$(PYTHON) scripts/test_jp_within_language_sentiment_drivers.py

within-cn-sentiment:
	$(PYTHON) scripts/test_cn_within_source_sentiment_drivers.py

within-language-sentiment: within-en-sentiment within-jp-sentiment within-cn-sentiment

presentation-safe:
	$(PYTHON) scripts/build_presentation_safe_outputs.py

statistical-test-figures:
	$(PYTHON) scripts/build_statistical_test_figures.py

test:
	$(PYTHON) -m pytest

public-check:
	$(PYTHON) scripts/check_public_release.py
