PYTHON = .venv/bin/python3

.PHONY: help test chinese-social cross-language-trends

help:
	@echo "Hokuriku tourist sentiment analysis"
	@echo ""
	@echo "  make chinese-social          Build Chinese XHS/Douyin cleaned outputs"
	@echo "  make cross-language-trends   Build monthly EN/JP/CN trend tables"
	@echo "  make test                    Run pytest"

chinese-social:
	$(PYTHON) scripts/build_chinese_social_media_dataset.py

cross-language-trends:
	$(PYTHON) scripts/build_cross_language_trends.py

test:
	$(PYTHON) -m pytest
