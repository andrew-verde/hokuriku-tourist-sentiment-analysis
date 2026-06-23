PYTHON = .venv/bin/python3

.PHONY: help test chinese-codebook-template reviewed-codebook-config reviewed-codebook-status chinese-social chinese-social-xhs-only chinese-insights chinese-insights-xhs-only multilingual-reviews cross-language-trends sentiment-env sentiment-analysis hypothesis-h1 hypothesis-h2 hypothesis-h3 hypothesis-tests presentation-safe

help:
	@echo "Hokuriku tourist sentiment analysis"
	@echo ""
	@echo "  make chinese-codebook-template Export reviewed Chinese codebook CSV"
	@echo "  make reviewed-codebook-status Show JP/EN review completion counts"
	@echo "  make reviewed-codebook-config Import completed reviewed JP/EN codebook YAML"
	@echo "  make chinese-social          Build Chinese XHS/Douyin cleaned outputs"
	@echo "  make chinese-social-xhs-only Build labeled XHS-only Chinese outputs"
	@echo "  make chinese-insights        Build tracked Chinese-specific figure/data outputs"
	@echo "  make chinese-insights-xhs-only Build labeled XHS-only figure/data outputs"
	@echo "  make multilingual-reviews    Sync local Google review data from english-fukui-tourism"
	@echo "  make cross-language-trends   Build Fukui-first EN/JP/CN baseline tables"
	@echo "  make sentiment-env           Install pinned JP-EN sentiment runtime"
	@echo "  make sentiment-analysis      Build JP-EN sentiment aggregate outputs"
	@echo "  make hypothesis-h1           Run JP-EN sentiment category hypothesis test"
	@echo "  make hypothesis-h2           Run JP-EN star-rating hypothesis test"
	@echo "  make hypothesis-h3           Run JP-EN reviewed-evidence hypothesis tests"
	@echo "  make hypothesis-tests        Run H1, H2, and H3 hypothesis test scripts"
	@echo "  make presentation-safe       Build slide-safe JP-EN aggregate scaffold"
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

chinese-insights:
	$(PYTHON) scripts/build_chinese_specific_insights.py

chinese-insights-xhs-only:
	$(PYTHON) scripts/build_chinese_specific_insights.py --input-dir output/chinese_social_media_analysis_xhs_only --output-dir output/chinese_specific_insights_xhs_only --analysis-label "Chinese-language Fukui Xiaohongshu rows only"

multilingual-reviews:
	$(PYTHON) scripts/sync_google_review_data.py

cross-language-trends:
	$(PYTHON) scripts/build_cross_language_trends.py

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

hypothesis-tests: hypothesis-h1 hypothesis-h2 hypothesis-h3

presentation-safe:
	$(PYTHON) scripts/build_presentation_safe_outputs.py

test:
	$(PYTHON) -m pytest
