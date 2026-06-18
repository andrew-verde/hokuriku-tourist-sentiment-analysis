# Codebook Reviews

This directory stores human-review source material for keyword codebooks.

Academic audit trail rule: source workbooks live here; generated runtime config
belongs under `config/` or another clearly documented generated path.

## Source Workbook Location

Save the reviewed Drive export here:

```text
docs/codebook_reviews/source/multilingual_keyword_codebook_review.xlsx
```

This workbook is allowed in Git because it is a codebook review source, not
row-level post/review text.

Regenerate the CSV template from the workbook rather than using Excel's CSV
export:

```bash
python3 scripts/export_chinese_codebook_template.py --reviewed-at 2026-06-18
```

Excel has no dependable repo-local setting that guarantees every CSV export will
preserve Chinese/Japanese text. Keep `.xlsx` as the audit source and generate
UTF-8-with-BOM CSVs through the script.

Do not store source post/review text, author names, URLs, screenshots, or manual
raw captures in this directory.
