import csv
from pathlib import Path

from openpyxl import Workbook

from scripts.export_chinese_codebook_template import export_chinese_codebook_template


def test_export_preserves_chinese_characters_and_review_decisions(tmp_path):
    workbook_path = tmp_path / "review.xlsx"
    output_path = tmp_path / "review.csv"

    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "Chinese"
    worksheet.append([
        "project_scope",
        "language",
        "source_layer",
        "code_family",
        "code",
        "label_en",
        "label_cn",
        "keyword",
        "keyword_translation_or_note",
        "current_pipeline_status",
        "reviewer",
        "review_decision",
        "suggested_replacement_keyword",
        "notes",
    ])
    worksheet.append([
        "cross_language_tourism_group_project",
        "Chinese",
        "Xiaohongshu titles",
        "friction",
        "transport_access",
        "Transport / Access",
        "交通/無障礙設施",
        "交通不便",
        "Existing keyword",
        "currently_used",
        "Lynn",
        "No change",
        "",
        "",
    ])
    worksheet.append([
        "cross_language_tourism_group_project",
        "Chinese",
        "Xiaohongshu titles",
        "friction",
        "language_information_gap",
        "Language Information Gap",
        "語言資訊不足",
        "英语",
        "Existing keyword",
        "currently_used",
        "Lynn",
        "FIX",
        "都是英语",
        "",
    ])
    workbook.save(workbook_path)

    rows = export_chinese_codebook_template(workbook_path, output_path, reviewed_at="2026-06-18")

    assert rows[0]["keyword_final"] == "交通不便"
    assert rows[1]["keyword_final"] == "都是英语"
    assert output_path.read_bytes().startswith(b"\xef\xbb\xbf")

    with output_path.open(newline="", encoding="utf-8-sig") as handle:
        csv_rows = list(csv.DictReader(handle))
    assert csv_rows[0]["label_cn"] == "交通/無障礙設施"
    assert csv_rows[0]["keyword_original"] == "交通不便"
    assert csv_rows[1]["keyword_final"] == "都是英语"
