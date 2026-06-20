import csv
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.reviewed_codebook import (
    ReviewedCodebookError,
    build_runtime_config,
    load_reviewed_codebook_rows,
    validation_status,
)


FIELDNAMES = [
    "source_sheet",
    "source_row_id",
    "language",
    "code_family",
    "code",
    "label_en",
    "keyword_original",
    "reviewer",
    "review_decision",
    "keyword_final",
]


def _write_codebook(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def test_jp_en_import_fails_loud_on_blank_review_decision(tmp_path):
    source = tmp_path / "reviewed.csv"
    _write_codebook(
        source,
        [
            {
                "source_sheet": "Japanese",
                "source_row_id": "2",
                "language": "Japanese",
                "code_family": "sentiment",
                "code": "positive_sentiment",
                "label_en": "Positive sentiment",
                "keyword_original": "sample positive term",
                "reviewer": "",
                "review_decision": "",
                "keyword_final": "",
            },
            {
                "source_sheet": "English",
                "source_row_id": "2",
                "language": "English",
                "code_family": "friction",
                "code": "transport_access",
                "label_en": "Transport Access",
                "keyword_original": "sample access term",
                "reviewer": "Reviewer",
                "review_decision": "No change",
                "keyword_final": "sample access term",
            },
        ],
    )

    rows = load_reviewed_codebook_rows(source)
    with pytest.raises(ReviewedCodebookError, match="blank review_decision"):
        build_runtime_config(rows, source_path=source, languages=["Japanese", "English"], command="pytest")

    status = validation_status(rows, ["Japanese", "English"])
    assert status["Japanese"]["blank_review_decision_rows"] == 1
    assert status["English"]["review_decision_counts"] == {"No change": 1}


def test_completed_jp_en_rows_promote_to_runtime_config(tmp_path):
    source = tmp_path / "reviewed.csv"
    _write_codebook(
        source,
        [
            {
                "source_sheet": "Japanese",
                "source_row_id": "2",
                "language": "Japanese",
                "code_family": "sentiment",
                "code": "positive_sentiment",
                "label_en": "Positive sentiment",
                "keyword_original": "jp original",
                "reviewer": "Reviewer",
                "review_decision": "FIX",
                "keyword_final": "jp replacement",
            },
            {
                "source_sheet": "Japanese",
                "source_row_id": "3",
                "language": "Japanese",
                "code_family": "sentiment",
                "code": "positive_sentiment",
                "label_en": "Positive sentiment",
                "keyword_original": "jp delete",
                "reviewer": "Reviewer",
                "review_decision": "delete",
                "keyword_final": "",
            },
            {
                "source_sheet": "English",
                "source_row_id": "2",
                "language": "English",
                "code_family": "friction",
                "code": "transport_access",
                "label_en": "Transport Access",
                "keyword_original": "en original",
                "reviewer": "Reviewer",
                "review_decision": "No change",
                "keyword_final": "en original",
            },
        ],
    )

    rows = load_reviewed_codebook_rows(source)
    config = build_runtime_config(rows, source_path=source, languages=["Japanese", "English"], command="pytest")

    assert config["schema_version"] == "reviewed_codebook_runtime.v1"
    assert set(config["languages"]) == {"Japanese", "English"}
    assert config["languages"]["Japanese"]["codes"]["positive_sentiment"]["keywords"] == ["jp replacement"]
    assert config["languages"]["English"]["codes"]["transport_access"]["keywords"] == ["en original"]
    reviewed_rows = config["languages"]["Japanese"]["codes"]["positive_sentiment"]["reviewed_rows"]
    assert [row["review_decision"] for row in reviewed_rows] == ["FIX", "delete"]
