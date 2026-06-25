# Statistical Test Figure Questions

All figures are aggregate-only. They omit row-level post/review text, authors, URLs, IDs, screenshots, and raw captures.

## H1 sentiment category shares

- Path: `docs/statistical_test_figures/figure_h1_sentiment_category_share.svg`
- Question answered: Which sentiment categories drive the JP/EN difference?
- Caveat: Category shares only; raw sentiment scores are not common-scale.

## H1 neutral-band sensitivity

- Path: `docs/statistical_test_figures/figure_h1_neutral_band_sensitivity.svg`
- Question answered: Does H1 survive wider neutral-band definitions?
- Caveat: Sensitivity rows are robustness checks.

## H2 star rating distribution

- Path: `docs/statistical_test_figures/figure_h2_rating_distribution.svg`
- Question answered: Where does the rating-distribution difference appear?
- Caveat: Common Google stars, not text-sentiment equivalence.

## H2 mean rating sensitivity

- Path: `docs/statistical_test_figures/figure_h2_rating_mean_sensitivity.svg`
- Question answered: How large is the English-minus-Japanese rating gap under row and POI sensitivity?
- Caveat: Rows remain nested in POIs.

## H3 reviewed evidence prevalence

- Path: `docs/statistical_test_figures/figure_h3_reviewed_evidence_prevalence.svg`
- Question answered: Which reviewed evidence families differ most between JP/EN review rows?
- Caveat: Keyword evidence prevalence; text length can affect match opportunity.

## H3 text length diagnostic

- Path: `docs/statistical_test_figures/figure_h3_text_length_diagnostic.svg`
- Question answered: How much more text is available for evidence matching by language group?
- Caveat: Diagnostic only.

## Hypothesis results at a glance

- Path: `docs/statistical_test_figures/figure_hypothesis_overview.svg`
- Question answered: Which main hypotheses are supported, and by which aggregate effect sizes?
- Caveat: Rows remain nested in POIs; adjusted p-values and venue-paired robustness checks answer different threats.

## H2 rating gap robustness ladder

- Path: `docs/statistical_test_figures/figure_h2_rating_gap_robustness_ladder.svg`
- Question answered: Does the English-minus-Japanese Google rating gap persist as the unit shifts from rows to POIs to shared POIs?
- Caveat: Common Google stars are companion outcome evidence, not cross-language text-sentiment equivalence.

## Within-POI paired differences

- Path: `docs/statistical_test_figures/figure_within_poi_paired_shift.svg`
- Question answered: When the same Fukui POIs are compared directly, do English-language reviews still score higher?
- Caveat: The paired unit is POI, not review row; the rating shift is marginal while positive-share shift is significant.

## Cross-source sentiment category shares

- Path: `docs/statistical_test_figures/figure_cross_source_sentiment_category.svg`
- Question answered: How do category shares differ across English, Japanese, and Chinese-language source groups?
- Caveat: Descriptive only across platforms/tools.

## Cross-source evidence prevalence

- Path: `docs/statistical_test_figures/figure_cross_source_evidence_prevalence.svg`
- Question answered: Which source group most often contains friction or enjoyment evidence?
- Caveat: Source/platform units differ.

## Cross-source test effects and gaps

- Path: `docs/statistical_test_figures/figure_cross_source_test_effects.svg`
- Question answered: Which cross-source tests have strongest descriptive effects, and which are skipped?
- Caveat: Skipped rows mean insufficient comparison groups.

## Date quality for trend claims

- Path: `docs/statistical_test_figures/figure_date_scrub_requirements.svg`
- Question answered: Which source dates are usable for monthly trend analysis?
- Caveat: Date quality diagnostic, not hypothesis evidence.

## Chinese city/platform friction status

- Path: `docs/statistical_test_figures/figure_chinese_city_platform_friction_status.svg`
- Question answered: Can current Chinese city/platform friction tests be visualized?
- Caveat: Current files are header-only; no comparison finding.

## Within-English Sentiment Drivers

- Path: `docs/statistical_test_figures/figure_within_english_driver_effects.svg`
- Question answered: Which within-language/source predictors best explain sentiment differences?
- Caveat: Within one scoring tool/source only.

## Within-Japanese Sentiment Drivers

- Path: `docs/statistical_test_figures/figure_within_japanese_driver_effects.svg`
- Question answered: Which within-language/source predictors best explain sentiment differences?
- Caveat: Within one scoring tool/source only.

## Within-Chinese Social Sentiment Drivers

- Path: `docs/statistical_test_figures/figure_within_chinese_driver_effects.svg`
- Question answered: Which within-language/source predictors best explain sentiment differences?
- Caveat: Within one scoring tool/source only.
