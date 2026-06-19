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
python3 scripts/export_chinese_codebook_template.py --reviewed-at 2026-06-18
```

The exporter writes UTF-8 with BOM (`utf-8-sig`) so Excel reopens the CSV with
Chinese/Japanese characters intact.

Do not paste source post/review text, URLs, author names, or screenshots into
these templates.
