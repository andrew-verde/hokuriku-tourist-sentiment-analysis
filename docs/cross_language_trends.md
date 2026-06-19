# Cross-Language Tourism Trends — Group Project Design Record

**Status:** active group project. **Not thesis work.** The tourist-friction
thesis pipeline must never depend on anything in this layer; these outputs are
never cited as thesis evidence and stay out of advisor-facing documents.

## Purpose

Compare tourism trends for Fukui/Hokuriku across three traveler-facing text
populations:

1. **English-language Google reviewers** (multilingual review layer)
2. **Japanese-language Google reviewers** (multilingual review layer)
3. **Chinese social-media commenters** — Xiaohongshu/Douyin scrapes from the
   companion `tourism-data` project (colleague-collected)

Group membership is content language, never nationality.

## Agreed design decisions (updated 2026-06-19)

| Decision | Choice |
|---|---|
| Ingestion source | Companion repo social data located via `TOURISM_DATA_DIR`: raw Xiaohongshu/Douyin scrapes under `data/raw/social/*.csv`, plus the parsed Fukui Douyin comment export at `data/processed/fukui_douyin_comments_from_md.csv`; other processed CSVs remain annotations |
| Fan-pilgrimage content | Keep it; left-join colleague's `theme`/`fan_score`/`travel_score` from `data/processed/*.csv` on note id; report comparisons for `all_posts` and `excluding_fan`; unmatched rows are `unclassified` |
| Post dates | Parse from the Xiaohongshu author cell with a `post_date_precision` flag (`exact`/`year_inferred`/`relative_inferred`); inference anchored to the scrape file's git commit date (`CN_SCRAPE_REFERENCE_DATE` overrides) |
| Post text | Current Chinese rows include post/comment body text where available; friction tagging remains directional until keyword matches are manually validated |
| Headline deliverable | Fukui-first aggregate baseline snapshot: English/Japanese Google review volume and rating mean, plus Chinese social-media post volume and SnowNLP sentiment by platform |
| Sentiment scales | Side-by-side, separate columns (`rating_mean` vs `sentiment_norm_mean`); never merged |
| Code layout | Separate stage script `scripts/build_cross_language_trends.py` + `make cross-language-trends`; hard error (naming the make target) when inputs are missing |
| Google scope filter | Use `output/checkpoints/poi_metadata.json` and `prefecture_normalized`; default prefecture is Fukui, with scaffold left for Ishikawa/Toyama later |
| Monthly trend posture | Disabled for now. Current Chinese post dates are mostly inferred or scrape-anchored; reintroduce only after date scrub requirements are met |
| Statistical posture | Descriptive only; no significance testing in this group project layer |
| Thesis isolation | No thesis make-chain includes these targets; row-level outputs gitignored; source-ledger rows marked group project |

## Pipeline

```
tourism-data/data/raw/social/*.csv ─────────────┐
tourism-data/data/processed/fukui_douyin_*.csv ─┤ (Douyin comment source)
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
```

## Expected growth

The colleague may add more scrape files (more keywords, Ishikawa/Toyama,
Douyin). The ingestion stage discovers any `*xhs*`/`*douyin*` CSV under
`data/raw/social/`, the current `*douyin*comments*.csv` parsed export under
`data/processed/`, and any theme-bearing CSV under `data/processed/`.
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
- per-platform Chinese denominators by month; Xiaohongshu notes and Douyin
  comments must stay stratified unless a weighting rationale is documented
- Google review collection windows, `review_date` parse coverage, and
  `poi_metadata.json` SHA/filter provenance
- prefecture scope for every group; default stays Fukui until Ishikawa/Toyama
  Chinese inputs exist

## Known limitations

- Chinese rows mix Xiaohongshu notes and Douyin comments. They are not full
  itineraries, platform-native POI reviews, or confirmed visits.
- Douyin comment rows use local parser IDs, not platform comment IDs; relative
  timestamps are approximate and cannot support monthly trend comparisons.
- A large share of Fukui Xiaohongshu chatter is idol fan-pilgrimage content
  (theme `fan`, 22/105 after dedup) — analytically interesting, but a different
  travel motivation than general tourism; hence the dual-subset reporting.
- Chinese sentiment uses SnowNLP as the current baseline, not a validated
  project-specific sentiment model; Google star ratings and SnowNLP probability
  are different instruments.
- Friction keyword tags on Chinese posts are unvalidated; treat as directional.
