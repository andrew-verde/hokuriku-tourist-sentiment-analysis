#!/usr/bin/env python3
"""Export the reviewed Chinese codebook sheet to a UTF-8 CSV template."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_WORKBOOK = ROOT / "docs" / "codebook_reviews" / "source" / "multilingual_keyword_codebook_review.xlsx"
DEFAULT_OUTPUT = ROOT / "docs" / "codebook_templates" / "chinese_reviewed_codebook_template.csv"
CHINESE_SHEET = "Chinese"

OUTPUT_COLUMNS = [
    "source_sheet",
    "source_row_id",
    "project_scope",
    "language",
    "source_layer",
    "code_family",
    "code",
    "label_en",
    "label_cn",
    "keyword_original",
    "keyword_translation_or_note",
    "current_pipeline_status",
    "reviewer",
    "review_decision",
    "keyword_final",
    "notes",
    "reviewed_at",
]

SOURCE_TO_OUTPUT = {
    "project_scope": "project_scope",
    "language": "language",
    "source_layer": "source_layer",
    "code_family": "code_family",
    "code": "code",
    "label_en": "label_en",
    "label_cn": "label_cn",
    "keyword": "keyword_original",
    "keyword_translation_or_note": "keyword_translation_or_note",
    "current_pipeline_status": "current_pipeline_status",
    "reviewer": "reviewer",
    "review_decision": "review_decision",
    "suggested_replacement_keyword": "keyword_final",
    "notes": "notes",
}

VALID_DECISIONS = {"No change", "FIX", "delete"}


class CodebookExportError(RuntimeError):
    pass


def _clean(value: object) -> str:
    return "" if value is None else str(value).strip()


def export_chinese_codebook_template(
    workbook_path: Path = DEFAULT_WORKBOOK,
    output_path: Path = DEFAULT_OUTPUT,
    reviewed_at: str = "",
) -> list[dict[str, str]]:
    workbook = load_workbook(workbook_path, read_only=True, data_only=True)
    if CHINESE_SHEET not in workbook.sheetnames:
        raise CodebookExportError(f"Workbook missing required sheet: {CHINESE_SHEET}")

    rows = list(workbook[CHINESE_SHEET].iter_rows(values_only=True))
    if not rows:
        raise CodebookExportError("Chinese sheet is empty")

    headers = [_clean(value) for value in rows[0]]
    header_indexes = {name: index for index, name in enumerate(headers) if name}
    missing = sorted(set(SOURCE_TO_OUTPUT) - set(header_indexes))
    if missing:
        raise CodebookExportError(f"Chinese sheet missing required columns: {missing}")

    exported: list[dict[str, str]] = []
    for excel_row_number, source_row in enumerate(rows[1:], start=2):
        row = {column: "" for column in OUTPUT_COLUMNS}
        row["source_sheet"] = CHINESE_SHEET
        row["source_row_id"] = str(excel_row_number)
        row["reviewed_at"] = reviewed_at
        for source_col, output_col in SOURCE_TO_OUTPUT.items():
            source_index = header_indexes[source_col]
            row[output_col] = _clean(source_row[source_index] if source_index < len(source_row) else "")

        if not any(row[column] for column in ("language", "code_family", "code", "keyword_original")):
            continue
        if row["language"] != "Chinese":
            continue
        if row["review_decision"] not in VALID_DECISIONS:
            raise CodebookExportError(
                f"Invalid review_decision on Chinese row {excel_row_number}: {row['review_decision']!r}"
            )
        if row["review_decision"] == "No change":
            row["keyword_final"] = row["keyword_original"]
        if row["review_decision"] == "delete":
            row["keyword_final"] = ""
        if row["review_decision"] == "FIX" and not row["keyword_final"]:
            raise CodebookExportError(f"FIX row missing suggested replacement on Chinese row {excel_row_number}")
        exported.append(row)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()
        writer.writerows(exported)
    return exported


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workbook", type=Path, default=DEFAULT_WORKBOOK)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--reviewed-at", default="")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        rows = export_chinese_codebook_template(args.workbook, args.output, args.reviewed_at)
    except CodebookExportError as error:
        print(error)
        return 1
    print(f"Exported {len(rows)} Chinese codebook rows to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
