# Presentation-Safe Readiness

Fukui-only JP-EN Google review aggregate scaffold for slides.

## Use Status

- Ready for presentation as a secondary library sentiment check.
- Not ready as primary JP/EN sentiment evidence until reviewed codebook evidence is promoted.
- Statistical rows are descriptive sensitivity checks, not confirmatory claims.

## Denominators

- Total Google review rows represented: 2014
- english-language Google reviews: n=214, scored=214, city=Fukui, dated=181, undated=33
- japanese-language Google reviews: n=1800, scored=1800, city=Fukui, dated=1800, undated=0

## Provenance Required On Slides

- Reviews input SHA256: 6bc06f34848954674506f6fefb84ffd9689b4cc9b2c90780fd5c8fc45eafaa56
- POI metadata SHA256: 34b088a57c0e61d23471cf3745ca2ec6e2811dce71aa7ab2a5a508fa5178e79a
- Sentiment summary SHA256: 0200df8e14574170a5207e532a45bae808a30536c60e40d4a2fb05c432d0b854
- Statistical summary SHA256: 452cf42f25580de154e0e539638306692d4ca1623ae04bc7a837180946eeeb1d
- Date range: derived from parseable review_date values in ignored scored-review audit file; aggregate only.
- Date coverage: chart data includes parseable and missing review_date counts.
- POI mix: derived from ignored scored-review audit file; aggregate category counts only.

## Captions

Figure JP-EN library sentiment: Fukui Google reviews only. Bars show VADER English-language and oseti Japanese-language sentiment category shares as secondary checks. Denominators and hashes are in the chart data; language labels are not nationality claims.

Table statistical sensitivity: Review-row, POI-level, and cluster bootstrap checks summarize robustness. Because review rows are nested within POIs and group sizes are imbalanced, use as descriptive sensitivity only.

## Caveats From Upstream Manifest

- Group labels describe review language, not reviewer nationality.
- VADER and oseti scores are tool-specific; raw sentiment-score t-tests/ANOVA are not run.
- Welch rating tests use common-scale Google review_rating as companion outcome/validation evidence.
- POI-level and cluster-bootstrap rows are sensitivity checks.
- Reviewed JP/EN codebook evidence path is pending.
