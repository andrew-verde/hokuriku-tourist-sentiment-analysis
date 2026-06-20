# Manual Keyword Review Follow-Up

Use this note when the English and Japanese manual keyword review is complete.
It records coding tasks and tests needed to promote reviewed EN/JP evidence into
the statistical comparison layer.

## Trigger

Start this work only after reviewed English and Japanese keyword/codebook files
exist under `docs/codebook_reviews/source/` or `docs/codebook_templates/`, with
review decisions preserved. Do not infer missing EN/JP terms from current
library sentiment output.

## Required Coding Tasks

1. Add EN/JP codebook import/promote path.
   - Preserve original keyword, final keyword, language, code family, code,
     reviewer decision, reviewer, and review date.
   - Fail loud on blank review decisions, missing required columns, or duplicate
     active terms that would make audit output ambiguous.
   - Keep row-level matched review text out of tracked outputs.

2. Extend JP/EN sentiment row output.
   - Add reviewed evidence columns for each review row:
     `reviewed_positive_terms_matched`,
     `reviewed_negative_terms_matched`,
     `reviewed_recommendation_terms_matched`,
     `reviewed_friction_terms_matched`,
     `reviewed_enjoyment_terms_matched`.
   - Add binary comparison fields, at minimum:
     `any_friction`, `any_enjoyment_evidence`,
     `any_recommendation_evidence`, and `any_positive_evidence`.
   - Keep VADER/oseti scores unchanged. Evidence columns are audit/sensitivity
     paths, not replacements for library scores.

3. Add aggregate EN/JP evidence summaries.
   - Counts and denominators by `language_group`, `prefecture_normalized`,
     `city`, and if useful `poi_category`.
   - Include source hashes, codebook hashes, and codebook evidence status.
   - No `review_text`, review IDs, POI IDs, author names, URLs, or source row IDs
     in tracked aggregate outputs.

4. Enable cross-source evidence tests in `scripts/build_cross_language_trends.py`.
   - Replace skipped rows for cross-source friction prevalence and cross-source
     enjoyment/recommendation prevalence.
   - Compare aligned binary evidence rates across English-language Google
     reviews, Japanese-language Google reviews, and Chinese-language social rows.
   - Keep labels explicit: cross-source discourse prevalence tests, not direct
     satisfaction or nationality tests.

5. Add disagreement reporting.
   - For EN/JP, report library sentiment category vs reviewed sentiment evidence
     disagreement rates.
   - For CN/EN/JP, report which comparison fields are library-derived vs
     reviewed-codebook-derived.

## Required Tests

1. Codebook importer tests.
   - `No change`, `FIX`, `delete`, and blank decision behavior.
   - Required-column failure.
   - Unicode preservation for Japanese and English terms.
   - Audit metadata preserved.

2. JP/EN row-output tests.
   - Evidence columns appear in ignored row-level output.
   - Matched terms are populated by deterministic fake rows.
   - No row-level text or IDs leak into aggregate CSVs/manifests.

3. Aggregate evidence summary tests.
   - Counts, denominators, and percentages are correct for tiny fake EN/JP
     fixtures.
   - Source/codebook hashes are present.
   - Missing reviewed codebooks fail loud or mark status as pending, never
     silently pass as zero evidence.

4. Cross-language statistical tests.
   - Current skipped cross-source evidence rows become `ok` when fake aligned
     EN/JP/CN binary evidence is present.
   - Rows remain `skipped` with clear reason when reviewed EN/JP evidence is
     absent.
   - Fisher exact is used for 2x2 tests; chi-square is used for larger tables.
   - `details_json` includes denominators, row units, and cross-source caveat.

5. Regression tests for invalid statistics.
   - Raw VADER/oseti/SnowNLP score t-tests or ANOVA stay absent/skipped.
   - Google `review_rating` tests stay limited to Google review groups.
   - Cross-source claims never use nationality labels.

## Expected Commands

```bash
.venv/bin/python3 -m pytest
.venv/bin/python3 scripts/build_sentiment_analysis.py --groups japanese,english --prefecture Fukui
.venv/bin/python3 scripts/build_cross_language_trends.py
```

If local ignored inputs live outside the current worktree, pass explicit
`--reviews-path`, `--poi-metadata-path`, `--chinese-path`, and
`--sentiment-summary-path` values rather than copying row-level source data into
Git.

## Output Contract

Tracked-safe outputs may contain counts, rates, test statistics, hashes,
commands, dependency versions, caveats, and codebook provenance. They must not
contain row-level post/review text, author names, handles, URLs, screenshots,
review IDs, POI IDs, place IDs, source row IDs, or raw manual captures.
