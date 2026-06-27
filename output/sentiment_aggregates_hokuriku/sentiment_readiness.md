# Sentiment Readiness

- generated_at: 2026-06-27T13:39:03+00:00
- command: `scripts/build_sentiment_analysis.py --groups japanese,english --prefecture  --aggregate-output-dir output/sentiment_aggregates_hokuriku`
- input: `output/multilingual_review_analysis/reviews_multilingual.csv`
- input_sha256: `6bc06f34848954674506f6fefb84ffd9689b4cc9b2c90780fd5c8fc45eafaa56`
- poi_metadata: `None`
- poi_metadata_sha256: `None`
- reviewed_codebook: `config/reviewed_jp_en_codebook.yaml`
- reviewed_codebook_sha256: `8626d2c47effd2e51d9d95e67a03a7fb2db317857f60ea0b9b97f351a0bb3944`
- row_level_output: `output/sentiment_row_level/google_reviews_all_japanese-english.csv`
- row_level_sha256: `691d47f94f49aa61160d62df1c02cd092832413a02591beb7b1608b46b5230c9`
- filters: city == `None`, prefecture == ``, language_group in ['japanese', 'english']
- primary_unit: one Google review row
- codebook_evidence_status: active
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
- sentiment_lock: `requirements-sentiment.lock.txt`
- environment_doc: `docs/sentiment_environment.md`
- known_metadata_exception: oseti 0.4.3.1 declares legacy mecab; runtime uses mecab-python3 plus ipadic and initializes MeCab with -r /dev/null.

## Denominators

- google_maps_outscraper / english / prefecture=nan / city_bucket=Fukui: n_reviews=214, n_scored=214, ratings_present=214
- google_maps_outscraper / english / prefecture=nan / city_bucket=Kanazawa: n_reviews=536, n_scored=536, ratings_present=536
- google_maps_outscraper / english / prefecture=nan / city_bucket=Toyama: n_reviews=169, n_scored=169, ratings_present=169
- google_maps_outscraper / japanese / prefecture=nan / city_bucket=Fukui: n_reviews=1800, n_scored=1800, ratings_present=1800
- google_maps_outscraper / japanese / prefecture=nan / city_bucket=Kanazawa: n_reviews=1050, n_scored=1050, ratings_present=1050
- google_maps_outscraper / japanese / prefecture=nan / city_bucket=Toyama: n_reviews=1187, n_scored=1187, ratings_present=1187

## Tests

- chi_square_sentiment_category (english_vs_japanese): status=ok, p=2.81049e-27
- mann_whitney_u_sentiment_score (english_vs_japanese): status=ok, p=4.12225e-36
- bootstrap_mean_difference_sentiment_score (english_vs_japanese): status=ok, p=NA
- bootstrap_median_difference_sentiment_score (english_vs_japanese): status=ok, p=NA
- poi_level_mann_whitney_mean_sentiment_score (english_vs_japanese): status=ok, p=2.72087e-12
- poi_level_bootstrap_mean_difference_sentiment_score (english_vs_japanese): status=ok, p=NA
- cluster_bootstrap_poi_mean_difference_sentiment_score (english_vs_japanese): status=ok, p=NA
- raw_score_parametric_tests_not_run (english_vs_japanese): status=skipped, p=NA
- welch_t_review_rating (english_vs_japanese): status=ok, p=4.41952e-11
- welch_anova_review_rating (english_vs_japanese): status=ok, p=4.41952e-11
- poi_level_welch_t_mean_review_rating (english_vs_japanese): status=ok, p=0.0013496
- rating_validation_spearman_score (all_groups): status=ok, p=2.01525e-67

## Caveats

- Group labels describe review language, not reviewer nationality.
- VADER and oseti scores are tool-specific. Do not interpret raw-score tests as cross-tool mean equivalence.
- Raw sentiment-score t-tests/ANOVA are skipped because VADER compound and oseti document scores are not the same measurement scale.
- `review_rating` is a common Google 1-to-5 scale, so Welch rating tests are companion outcome/validation evidence.
- POI-level and cluster-bootstrap rows are sensitivity checks, not replacement primary models.
- Reviewed JP/EN keyword evidence is an audit/sensitivity path, not a replacement for VADER/oseti.
