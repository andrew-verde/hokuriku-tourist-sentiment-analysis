PYTHON = .venv/bin/python3
PBL_SITE ?= $(HOME)/pbl-site

.PHONY: help test chinese-codebook-template reviewed-codebook-config reviewed-codebook-status chinese-social chinese-social-xhs-only chinese-social-with-douyin chinese-insights chinese-insights-xhs-only multilingual-reviews cross-language-trends sentiment-env sentiment-analysis hypothesis-h1 hypothesis-h2 hypothesis-h3 hypothesis-within-poi hypothesis-tests nudge-analysis poi-opportunity nudge-figures nudge-register nudge-all within-en-sentiment within-jp-sentiment within-cn-sentiment within-language-sentiment presentation-safe statistical-test-figures dashboard nudge-slides nudge-pptx deploy

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
	@echo "  make multilingual-reviews    Sync local Google review data from english-fukui-tourism"
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
	@echo "  make nudge-figures           Build aggregate nudge opportunity SVG figures"
	@echo "  make nudge-register          Build HTML next-semester nudge experiment register"
	@echo "  make nudge-all               Build all nudge outputs, figures, register, and dashboard"
	@echo "  make within-en-sentiment     Run English within-language sentiment drivers"
	@echo "  make within-jp-sentiment     Run Japanese within-language sentiment drivers"
	@echo "  make within-cn-sentiment     Run Chinese within-source sentiment drivers"
	@echo "  make within-language-sentiment Run all within-language/source sentiment drivers"
	@echo "  make presentation-safe       Build slide-safe JP-EN aggregate scaffold"
	@echo "  make statistical-test-figures Build aggregate-only SVG figures for statistical tests"
	@echo "  make dashboard               Build provenance-locked PBL-Dashboard.html"
	@echo "  make nudge-slides            Build bilingual nudge IMRAD seminar deck HTML"
	@echo "  make nudge-pptx              Build native editable bilingual nudge PowerPoint"
	@echo "  make deploy                  Regenerate figures+dashboard and sync to PBL_SITE ($(PBL_SITE))"
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

hypothesis-within-poi:
	$(PYTHON) scripts/test_within_poi_paired_jp_en.py

hypothesis-tests: hypothesis-h1 hypothesis-h2 hypothesis-h3 hypothesis-within-poi

nudge-analysis:
	$(PYTHON) scripts/build_nudge_opportunity_analysis.py

poi-opportunity:
	$(PYTHON) scripts/build_poi_opportunity_index.py

nudge-figures:
	$(PYTHON) scripts/build_nudge_figures.py

nudge-register:
	$(PYTHON) scripts/build_nudge_experiment_register.py

nudge-all: nudge-analysis poi-opportunity nudge-figures nudge-register dashboard

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

dashboard:
	$(PYTHON) scripts/build_pbl_dashboard.py

nudge-slides:
	$(PYTHON) scripts/build_nudge_seminar_slides.py

nudge-pptx:
	$(PYTHON) scripts/build_nudge_pptx.py

# Regenerate figures + both HTML pages, then sync landing page plus referenced
# assets (figure SVGs + provenance source files) into the served directory.
# Asset list is parsed from both HTML pages so register-only provenance assets
# are included too; override destination with `make deploy PBL_SITE=/path`.
deploy: statistical-test-figures nudge-register dashboard
	@mkdir -p "$(PBL_SITE)"
	@cp -f PBL-Dashboard.html "$(PBL_SITE)/index.html"
	@cp -f PBL-Dashboard.html "$(PBL_SITE)/PBL-Dashboard.html"
	@for html in PBL-Dashboard.html docs/nudge_experiment_register.html; do \
		grep -oE "(href|data-source)=['\"](docs|output)/[^'\"]+" "$$html"; \
	done | sed -E "s/.*['\"]//" | sort -u \
		| while read -r p; do \
			mkdir -p "$(PBL_SITE)/$$(dirname "$$p")"; \
			cp -f "$$p" "$(PBL_SITE)/$$p"; \
		done
	@n=$$(for html in PBL-Dashboard.html docs/nudge_experiment_register.html; do \
		grep -oE "(href|data-source)=['\"](docs|output)/[^'\"]+" "$$html"; \
	done | sed -E "s/.*['\"]//" | sort -u | wc -l); \
		echo "deployed index.html + PBL-Dashboard.html + $$n referenced assets to $(PBL_SITE)"

test:
	$(PYTHON) -m pytest
