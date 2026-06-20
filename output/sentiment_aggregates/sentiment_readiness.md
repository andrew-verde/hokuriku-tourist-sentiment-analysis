# Sentiment Readiness

- generated_at: 2026-06-20T02:47:52+00:00
- command: `scripts/build_sentiment_analysis.py --groups japanese,english --prefecture Fukui`
- input: `/home/andrewgreen/Repositories/andrew-verde/hokuriku-tourist-sentiment-analysis/output/multilingual_review_analysis/reviews_multilingual.csv`
- input_sha256: `6bc06f34848954674506f6fefb84ffd9689b4cc9b2c90780fd5c8fc45eafaa56`
- poi_metadata: `/home/andrewgreen/Repositories/andrew-verde/hokuriku-tourist-sentiment-analysis/output/checkpoints/poi_metadata.json`
- poi_metadata_sha256: `34b088a57c0e61d23471cf3745ca2ec6e2811dce71aa7ab2a5a508fa5178e79a`
- row_level_output: `/home/andrewgreen/Repositories/andrew-verde/hokuriku-tourist-sentiment-analysis/output/sentiment_row_level/google_reviews_fukui_japanese-english.csv`
- row_level_sha256: `3af51c8f32cdfe24207f32071ef3c74d9ff0271cd306bce7462bcbc4913de542`
- filters: city == `None`, prefecture == `Fukui`, language_group in ['japanese', 'english']
- primary_unit: one Google review row
- codebook_evidence_status: pending
- bootstrap_seed: 20260618

## Dependency Versions

- pandas: 3.0.3
- numpy: 2.4.6
- scipy: 1.18.0
- vaderSentiment: 3.3.2
- oseti: 0.4.3.1
- mecab-python3: 1.0.12
- bunkai: 1.5.2
- unidic-lite: 1.0.8
- ipadic: 1.0.0
- emoji: 1.7.0

## Dependency Reproducibility

- setup_command: `.venv/bin/python3 scripts/bootstrap_sentiment_environment.py`
- sentiment_lock: `/home/andrewgreen/Repositories/andrew-verde/hokuriku-tourist-sentiment-analysis/requirements-sentiment.lock.txt`
- environment_doc: `/home/andrewgreen/Repositories/andrew-verde/hokuriku-tourist-sentiment-analysis/docs/sentiment_environment.md`
- known_metadata_exception: oseti 0.4.3.1 declares legacy mecab; runtime uses mecab-python3 plus ipadic and initializes MeCab with -r /dev/null.

## Denominators

- google_maps_outscraper / english / prefecture=Fukui / city_bucket=Fukui: n_reviews=214, n_scored=214, ratings_present=214
- google_maps_outscraper / japanese / prefecture=Fukui / city_bucket=Fukui: n_reviews=1800, n_scored=1800, ratings_present=1800

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
