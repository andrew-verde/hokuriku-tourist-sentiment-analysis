PYTHON = .venv/bin/python3

.PHONY: help test chinese-codebook-template chinese-social multilingual-reviews cross-language-trends sentiment-env sentiment-analysis

help:
	@echo "Hokuriku tourist sentiment analysis"
	@echo ""
	@echo "  make chinese-codebook-template Export reviewed Chinese codebook CSV"
	@echo "  make chinese-social          Build Chinese XHS/Douyin cleaned outputs"
	@echo "  make multilingual-reviews    Sync local Google review data from english-fukui-tourism"
	@echo "  make cross-language-trends   Build Fukui-first EN/JP/CN baseline tables"
	@echo "  make sentiment-env           Install pinned JP-EN sentiment runtime"
	@echo "  make sentiment-analysis      Build JP-EN sentiment aggregate outputs"
	@echo "  make test                    Run pytest"

chinese-codebook-template:
	$(PYTHON) scripts/export_chinese_codebook_template.py

chinese-social:
	$(PYTHON) scripts/build_chinese_social_media_dataset.py

multilingual-reviews:
	$(PYTHON) scripts/sync_google_review_data.py

cross-language-trends:
	$(PYTHON) scripts/build_cross_language_trends.py

sentiment-env:
	$(PYTHON) scripts/bootstrap_sentiment_environment.py

sentiment-analysis:
	$(PYTHON) scripts/build_sentiment_analysis.py --groups japanese,english --prefecture Fukui

test:
	$(PYTHON) -m pytest
