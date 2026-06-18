# Sentiment Readiness

- generated_at: 2026-06-18T10:30:04+00:00
- command: `scripts/build_sentiment_analysis.py --groups japanese,english --city Fukui`
- input: `/Users/andrewgreen/Repositories/andrew-verde/hokuriku-tourist-sentiment-analysis/output/multilingual_review_analysis/reviews_multilingual.csv`
- input_sha256: `7642ca798262f925ee165582c5e5e341cd0d768d4bd034b8d0d6998e4d589579`
- row_level_output: `/Users/andrewgreen/Repositories/andrew-verde/hokuriku-tourist-sentiment-analysis/output/sentiment_row_level/google_reviews_fukui_japanese-english.csv`
- row_level_sha256: `1afb1aaefcf6b97d3329df4627b39d0b46d83079533932b2e5ac21d40bf3a099`
- filters: city == `Fukui`, language_group in ['japanese', 'english']
- primary_unit: one Google review row
- codebook_evidence_status: pending
- bootstrap_seed: 20260618

## Dependency Versions

- pandas: 3.0.3
- numpy: 2.4.6
- scipy: 1.17.1
- vaderSentiment: 3.3.2
- oseti: 0.4.3.1
- mecab-python3: 1.0.12
- bunkai: 1.5.2
- unidic-lite: 1.0.8
- ipadic: 1.0.0
- emoji: 1.7.0

## Dependency Reproducibility

- setup_command: `.venv/bin/python3 scripts/bootstrap_sentiment_environment.py`
- sentiment_lock: `/Users/andrewgreen/Repositories/andrew-verde/hokuriku-tourist-sentiment-analysis/requirements-sentiment.lock.txt`
- environment_doc: `/Users/andrewgreen/Repositories/andrew-verde/hokuriku-tourist-sentiment-analysis/docs/sentiment_environment.md`
- known_metadata_exception: oseti 0.4.3.1 declares legacy mecab; runtime uses mecab-python3 plus ipadic and initializes MeCab with -r /dev/null.

## Denominators

- google_maps_outscraper / english / Fukui: n_reviews=214, n_scored=214, ratings_present=214
- google_maps_outscraper / japanese / Fukui: n_reviews=1800, n_scored=1800, ratings_present=1800

## Tests

- chi_square_sentiment_category (english_vs_japanese): status=ok, p=4.21514e-09
- mann_whitney_u_sentiment_score (english_vs_japanese): status=ok, p=1.165e-17
- bootstrap_mean_difference_sentiment_score (english_vs_japanese): status=ok, p=NA
- bootstrap_median_difference_sentiment_score (english_vs_japanese): status=ok, p=NA
- poi_level_mann_whitney_mean_sentiment_score (english_vs_japanese): status=ok, p=1.21892e-05
- poi_level_bootstrap_mean_difference_sentiment_score (english_vs_japanese): status=ok, p=NA
- cluster_bootstrap_poi_mean_difference_sentiment_score (english_vs_japanese): status=ok, p=NA
- rating_validation_spearman_score (all_groups): status=ok, p=2.44023e-24

## Caveats

- Group labels describe review language, not reviewer nationality.
- VADER and oseti scores are tool-specific. Main comparison uses category shares and score distributions.
- `review_rating` is validation evidence only, not a covariate in this skeleton.
- POI-level and cluster-bootstrap rows are sensitivity checks, not replacement primary models.
- Reviewed JP/EN codebook evidence path is pending and does not block this library comparison.
