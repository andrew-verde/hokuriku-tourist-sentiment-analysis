# Cross-Language Tourism Trends — Group Project Design Record

**Status:** active group project. **Not thesis work.** The tourist-friction
thesis pipeline must never depend on anything in this layer; these outputs are
never cited as thesis evidence and stay out of advisor-facing documents.

## Purpose

Compare tourism trends for Fukui/Hokuriku across three traveler-facing text
populations:

1. **English-language Google reviewers** (multilingual review layer)
2. **Japanese-language Google reviewers** (multilingual review layer)
3. **Chinese-language social rows** — current main pipeline uses Xiaohongshu
   note rows from the companion `tourism-data` project; Douyin comments are
   available only through an explicit source-sensitivity target

Group membership is content language, never nationality.

## Agreed design decisions

| Decision | Choice |
|---|---|
| Ingestion source | Companion repo social data located via `TOURISM_DATA_DIR`: default path uses raw Xiaohongshu inputs under `data/raw/social/*.csv` or the reviewed manual XHS workbook; Douyin raw/comment exports are opt-in source-sensitivity inputs only; other processed CSVs remain annotations |
| Fan-pilgrimage content | Keep it; left-join colleague's `theme`/`fan_score`/`travel_score` from `data/processed/*.csv` on note id; report comparisons for `all_posts` and `excluding_fan`; unmatched rows are `unclassified` |
| Post dates | Parse from the Xiaohongshu author cell with a `post_date_precision` flag (`exact`/`year_inferred`/`relative_inferred`); inference anchored to the scrape file's git commit date (`CN_SCRAPE_REFERENCE_DATE` overrides) |
| Post text | Current main Chinese rows include Xiaohongshu body text where available; reviewed Chinese codebook rows now drive friction/topic/positive-evidence matching, but outputs remain descriptive until match precision is validated |
| Headline deliverable | Fukui-first aggregate baseline snapshot: English/Japanese Google review volume and rating mean, plus Chinese social-media post volume and SnowNLP sentiment by platform |
| Sentiment scales | Side-by-side, separate columns (`rating_mean` vs `sentiment_norm_mean`); never merged |
| Code layout | Separate stage script `scripts/build_cross_language_trends.py` + `make cross-language-trends`; hard error (naming the make target) when inputs are missing |
| Google scope filter | Use `output/checkpoints/poi_metadata.json` and `prefecture_normalized`; default prefecture is Fukui, with scaffold left for Ishikawa/Toyama later |
| Monthly trend posture | Disabled for now. Current Chinese post dates are mostly inferred or scrape-anchored; reintroduce only after date scrub requirements are met |
| Statistical posture | Descriptive cross-source category-share tests and XHS-first reviewed-evidence prevalence tests are allowed with caveats; raw SnowNLP/VADER/oseti score tests remain skipped |
| Thesis isolation | No thesis make-chain includes these targets; row-level outputs gitignored; source-ledger rows marked group project |

## Pipeline

```
tourism-data/data/raw/social/*xhs*.csv ─────────┐
repo docs/codebook_reviews/source/*.xlsx ───────┤ (manual XHS workbook)
tourism-data/data/processed/*.csv ──────────────┤ (theme annotations)
                                                ▼
                         make chinese-social
                                                ▼
        output/chinese_social_media_analysis/tagged_chinese_social_posts.csv
                                                ▼
make multilingual-reviews ──► make cross-language-trends
                                                ▼
                  output/cross_language_trends/cross_language_baseline_snapshot.csv
                  output/cross_language_trends/date_scrub_requirements.csv
                  output/cross_language_trends/cross_language_statistical_tests.csv

make sentiment-analysis ─────► make presentation-safe
                                                ▼
                  output/presentation_safe/jp_en_library_sentiment_chart_data.csv
                  output/presentation_safe/jp_en_statistical_sensitivity_summary.csv
                  output/presentation_safe/presentation_readiness.md
```

`make chinese-social` also writes aggregate-safe Chinese evidence tables:

- `chinese_friction_by_city_platform.csv`
- `chinese_topic_by_city_platform.csv`
- `chinese_enjoyment_evidence_by_city_platform.csv`
- `douyin_provenance_report.json` (empty for the current main XHS-only build)
- `chinese_reviewed_codebook_runtime_summary.csv`

`make chinese-insights` turns those Chinese-only outputs into tracked
presentation figures and aggregate data views under
`output/chinese_specific_insights/`:

- `figure_keyword_occurrence_by_category.svg`
- `figure_top_sentiment_keywords.svg`
- `figure_sentiment_category_by_platform.svg`
- `figure_theme_sentiment.svg`
- `keyword_occurrence_by_category.csv`
- `sentiment_keyword_counts.csv`
- `keywords_by_snownlp_sentiment_category.csv`
- `theme_sentiment_summary.csv`

The SVG figures are generated without a plotting dependency: the script uses
`pandas` plus Python standard-library SVG writing, so `requirements.txt` remains
the complete runtime package list for this step. The CSVs are the auditable
source for each figure and keep denominators, code labels, and caveats while
excluding row-level post/comment text, authors, URLs, and source IDs.
The main keyword-occurrence figure focuses on reviewed topic evidence split by
positive vs negative SnowNLP category, so positive-sentiment evidence terms do
not crowd out concrete Fukui topics.
The theme figure shows classified themes only; the CSV retains `unclassified`.
At the current snapshot, `unclassified` means no companion theme annotation was
joined for that Xiaohongshu row. Parsed Douyin comments are excluded from the
main theme annotation analysis until further notice.

`make presentation-safe` is deliberately narrower than the cross-language
baseline. It consumes tracked JP-EN sentiment aggregate files plus the ignored
scored-review audit file named in the sentiment manifest, then produces
slide-ready chart/table data plus captions. It reads only safe metadata from
the audit file to aggregate date ranges and POI-category mix. It does not write
row-level review text, POI IDs, author fields, URLs, or manual codebook review
files.

Presentation safeguards:

- Date range and POI-category mix must be real aggregate values; missing
  required metadata fails the command instead of writing placeholders.
- Date ranges come from parseable review dates, with parseable/missing date
  counts carried in the chart data.
- Generated chart/table files are scanned for dummy/placeholder-like values.
- JP/EN VADER/oseti remains a secondary library check. Reviewed JP/EN keyword
  evidence is now promoted into runtime outputs and used for evidence-rate
  diagnostics, but it is still not a replacement for language-specific
  sentiment tools.

## Expected growth

The colleague may add more scrape files (more keywords, Ishikawa/Toyama,
Douyin). The main ingestion stage currently discovers Xiaohongshu sources and
any theme-bearing CSV under `data/processed/`. Douyin CSVs under
`data/raw/social/` and the current `*douyin*comments*.csv` parsed export under
`data/processed/` are used only by the explicit Douyin-inclusive
source-sensitivity target.
Re-run `make chinese-social` then `make cross-language-trends` after each
upstream update.

## Monthly trend gate

Monthly trend analysis is not worthwhile for the current baseline because most
Chinese rows have `relative_inferred` or `year_inferred` dates. If monthly
trend output is reintroduced, first scrub:

- exact platform post dates for Chinese rows, or documented source evidence for
  recovered dates
- exclusion rules for `year_inferred`, `relative_inferred`, and missing Chinese
  dates
- per-platform Chinese denominators by month; any future Douyin reintroduction
  must stay stratified from Xiaohongshu unless a weighting rationale is
  documented
- Google review collection windows, `review_date` parse coverage, and
  `poi_metadata.json` SHA/filter provenance
- prefecture scope for every group; default stays Fukui until Ishikawa/Toyama
  Chinese inputs exist

## Current statistical tests

`make cross-language-trends` now writes
`output/cross_language_trends/cross_language_statistical_tests.csv`.

Currently valid:

- descriptive chi-square/Fisher category-share tests for
  English-language Google reviews, Japanese-language Google reviews, and
  Chinese-language social rows using positive/neutral/negative categories
- pairwise category-share tests comparing each Google review language group
  with all Chinese social rows
- XHS-first cross-source `any_friction` and `any_enjoyment_evidence`
  prevalence tests using reviewed JP/EN keyword evidence and Chinese reviewed
  keyword evidence
- within-Chinese source-platform tests only when an explicit Douyin-inclusive
  source-sensitivity input is supplied

Explicitly skipped:

- raw SnowNLP/VADER/oseti score t-tests or ANOVA

Interpretation: evidence prevalence tests are descriptive discourse-evidence
tests, not direct satisfaction measures, and Douyin remains outside the default
Chinese layer.

Interpretation: these p-values describe differences in platformed discourse
categories, not direct visitor satisfaction or nationality differences.

## Known limitations

- Main Chinese rows are Xiaohongshu notes, not full itineraries,
  platform-native POI reviews, or confirmed visits.
- Douyin comment rows are temporarily deferred from the main pipeline. In the
  opt-in variant, they use local parser IDs, not platform comment IDs; relative
  timestamps are approximate and cannot support monthly trend comparisons.
- Fukui Xiaohongshu chatter includes idol fan-pilgrimage content. Treat it as
  analytically interesting but distinct from general tourism; use generated
  theme-count outputs when reporting its share.
- Chinese sentiment uses SnowNLP as a secondary baseline, not a validated
  project-specific sentiment model; Google star ratings and SnowNLP probability
  are different instruments.
- Cross-source sentiment category tests compare platformed discourse categories
  across reviews, notes, and comments; they do not make social-media rows
  equivalent to Google reviews.
- Friction/topic/positive-evidence keyword tags on Chinese posts are reviewed
  codebook matches, but match precision is not yet independently validated;
  treat rates as directional.
