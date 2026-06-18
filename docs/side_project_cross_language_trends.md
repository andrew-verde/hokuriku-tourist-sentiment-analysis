# Cross-Language Tourism Trends — Side-Project Design Record

**Status:** active side project. **Not thesis work.** The tourist-friction
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

## Agreed design decisions (2026-06-12)

| Decision | Choice |
|---|---|
| Ingestion source | Companion repo **raw scrapes** (`tourism-data/data/raw/social/*.csv`), located via `TOURISM_DATA_DIR`; processed CSVs are consumed only as annotations |
| Fan-pilgrimage content | Keep it; left-join colleague's `theme`/`fan_score`/`travel_score` from `data/processed/*.csv` on note id; report comparisons for `all_posts` and `excluding_fan`; unmatched rows are `unclassified` |
| Post dates | Parse from the Xiaohongshu author cell with a `post_date_precision` flag (`exact`/`year_inferred`/`relative_inferred`); inference anchored to the scrape file's git commit date (`CN_SCRAPE_REFERENCE_DATE` overrides) |
| Title-only text | Theme mix, monthly volume, and sentiment are headline outputs; friction tagging runs but is directional only with an explicit title-level caveat |
| Headline deliverable | Monthly trends table (city × group × month: volume + group-specific sentiment) plus the existing static rate comparisons |
| Sentiment scales | Side-by-side, separate columns (`rating_mean` vs `sentiment_norm_mean`); never merged; only within-group trajectories are interpretable |
| Code layout | Separate stage script `scripts/build_cross_language_trends.py` + `make cross-language-trends`; hard error (naming the make target) when inputs are missing |
| Statistical posture | Descriptive only; no significance testing on the small monthly series |
| Thesis isolation | No thesis make-chain includes these targets; row-level outputs gitignored; source-ledger rows marked side-project |

## Pipeline

```
tourism-data/data/raw/social/*.csv ──┐
tourism-data/data/processed/*.csv ───┤ (theme annotations)
                                     ▼
                         make chinese-social
                                     ▼
        output/chinese_social_media_analysis/tagged_chinese_social_posts.csv
                                     ▼
make multilingual-reviews ──► make cross-language-trends
                                     ▼
                  output/cross_language_trends/monthly_trends.csv
                  output/cross_language_trends/chinese_theme_mix_monthly.csv
```

## Expected growth

The colleague will add more scrape files (more keywords, Kanazawa/Toyama,
Douyin). The ingestion stage discovers any `*xhs*`/`*douyin*` CSV under
`data/raw/social/` and any theme-bearing CSV under `data/processed/`, so new
files require no code changes. Re-run `make chinese-social` then
`make cross-language-trends` after each upstream update, and regenerate the
data manifest (`make data-manifest`).

## Known limitations

- Chinese rows are title-level search results, not full posts or confirmed
  visits; volumes are small (106 notes as of 2026-06-12, Fukui only).
- A large share of Fukui Xiaohongshu chatter is idol fan-pilgrimage content
  (theme `fan`, 22/105 after dedup) — analytically interesting, but a different
  travel motivation than general tourism; hence the dual-subset reporting.
- Chinese sentiment is a transparent keyword-polarity scaffold, not a validated
  model; Google star ratings and lexicon polarity are different instruments.
- Friction keyword tags on Chinese titles are unvalidated; treat as directional.
