# Codebook Review Templates

Use these files for manual, traceable codebook review handoff. The source
workbook is the audit source. Generate CSV templates from the workbook instead
of pasting from Excel, because Excel can replace Chinese/Japanese CSV text with
underscores when encoding is misdetected.

## Chinese Reviewed Codebook Template

File: `chinese_reviewed_codebook_template.csv`

Required import rules:

- `No change`: keep `keyword_original` as `keyword_final`
- `FIX`: use `keyword_final`; preserve `keyword_original`
- `delete`: keep row for audit trail, but importer excludes it
- blank `review_decision`: fail import
- accepted friction/topic/sentiment rows are runtime evidence terms
- reviewed friction rows supersede legacy YAML terms for the same code, so
  `delete` and `FIX` decisions are honored

`keyword_final` should always contain the exact term the pipeline should use
for `No change` and `FIX` rows. For `delete` rows, leave `keyword_final` blank.

Generate from the reviewed workbook:

```bash
python3 scripts/export_chinese_codebook_template.py --reviewed-at YYYY-MM-DD
```

The exporter writes UTF-8 with BOM (`utf-8-sig`) so Excel reopens the CSV with
Chinese/Japanese characters intact.

Do not paste source post/review text, URLs, author names, or screenshots into
these templates.

## Japanese/English Runtime Config Import

The JP/EN importer scaffold is:

```bash
python3 scripts/import_reviewed_codebook_config.py --status-only
python3 scripts/import_reviewed_codebook_config.py
```

`--status-only` reports review-completion counts without writing a runtime
config. The full import writes `config/reviewed_jp_en_codebook.yaml` only after
the requested Japanese-language and English-language rows have complete
`review_decision` values.

Required import rules:

- `No change`: keep `keyword_original` as the runtime keyword
- `FIX`: use `suggested_replacement_keyword` / `keyword_final`
- `delete`: preserve audit row metadata, exclude from runtime matching
- blank `review_decision`: fail import for JP/EN rows
- invalid `review_decision`: fail import
- fully deleted codes: fail import because no runtime keyword remains

Current status: manual JP/EN review is not complete, so this importer should be
treated as a validation gate and not as an evidence-producing runtime input yet.
