# Context Glossary

## Chinese-language posts

Tourism-related Xiaohongshu or Douyin rows whose source text is Chinese-language
social-media content. This term describes content language, not author
nationality.

## English-language reviews

Google review rows whose review text is classified as English-language content.
This term describes review language, not reviewer nationality.

## Google review data

Local Google Maps review artifacts collected in the sibling
`platform-review-scraper` repository, including raw collection checkpoints and
derived multilingual review tables. These artifacts may contain row-level review
text, author names, place IDs, or source identifiers, so they are local inputs
for analysis and not committed in this repository.

## Dual-path sentiment evidence

Sentiment interpretation that preserves both a language-specific sentiment score
and reviewed keyword evidence. The score path provides comparable categories;
the evidence path provides human-auditable support and disagreement checks.

## Fukui-first analysis

Default research scope for this repository. Initial comparisons should filter to
Fukui Prefecture or Fukui city POIs, even when the local Google review cache also
contains Kanazawa/Ishikawa-adjacent or Toyama rows.

## Japanese-language reviews

Google review rows whose review text is classified as Japanese-language content.
This term describes review language, not reviewer nationality.

## Review-row analysis

Analysis whose primary observation is one Google review row. Sentence-level
scores may support audit and diagnostics, but they are nested evidence inside a
review rather than independent comparison observations.

## Survey data

Official or questionnaire-derived tourism datasets from FTAS, Code for Fukui,
Ishikawa, or similar survey sources. Survey data is outside this repository's
Google review validation unless explicitly requested.
