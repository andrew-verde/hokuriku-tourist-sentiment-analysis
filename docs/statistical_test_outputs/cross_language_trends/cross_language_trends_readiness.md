# Cross-Language Baseline Readiness (Group Project)

Fukui-first aggregate comparison for English-language Google reviews, Japanese-language Google reviews, and Chinese-language Xiaohongshu posts. Monthly trend output is disabled for now.

- Active prefecture: Fukui
- Review rows retained after POI-prefecture filter: 2014
- Chinese posts retained: 200
- Statistical tests output: `output/cross_language_trends/cross_language_statistical_tests.csv`
- Neighboring-prefecture scaffold kept for later: ['Ishikawa', 'Toyama']

## Current Decision

- Monthly trend analysis is not worthwhile yet for the Chinese layer. Most Chinese rows use inferred dates, and Douyin comment dates are anchored to scrape/parser context rather than exact platform timestamps.
- Current output is aggregate baseline only: source volumes, Google rating mean, Chinese SnowNLP secondary sentiment summary, and reviewed keyword evidence prevalence.
- Current cross-source evidence tests use reviewed EN/JP keyword evidence and Chinese-language XHS evidence. Douyin comments remain deferred because relevance is limited.

## If Monthly Trends Are Reintroduced

- Filter Google reviews by POI `prefecture_normalized` from `output/checkpoints/poi_metadata.json`.
- Keep Chinese rows with exact platform post dates, or recover exact dates from source evidence.
- Recover exact source post date for rows currently marked `year_inferred`, `relative_inferred`, or `none`; otherwise exclude them from monthly output.
- Exclude `year_inferred`, `relative_inferred`, and missing Chinese dates unless separately audited.
- Report date precision counts, source file hashes, collection windows, and per-platform monthly denominators.
- Stratify Chinese social posts by platform; do not pool Xiaohongshu notes and Douyin comments as one time series without weighting rationale.

## Caveats

- Group membership is content language/source platform, not nationality.
- Chinese sentiment uses SnowNLP as a secondary baseline; Google ratings are a separate measurement instrument.
- Cross-source sentiment category tests compare platformed discourse categories, not direct visitor satisfaction.
- Chinese social rows are Xiaohongshu notes by default; Google rows are reviews.
- Neighboring prefectures remain scaffolded for later work, but current default output is Fukui-only.
