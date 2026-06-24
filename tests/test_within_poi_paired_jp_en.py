import json
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.hypothesis_test_common import MissingColumnsError, MissingInputError
from scripts.test_within_poi_paired_jp_en import (
    build_within_poi_paired_jp_en,
    paired_poi_test,
)


FORBIDDEN = {
    "review_text",
    "review_author",
    "author",
    "author_url",
    "note_url",
    "source_url",
    "url",
    "place_id",
    "poi_id",
    "review_id",
    "source_review_id",
}


def _synthetic_rows() -> list[dict]:
    rows = []
    for poi, en_rating, jp_rating in [("p1", 5, 3), ("p2", 4, 2), ("p3", 5, 4)]:
        for _ in range(5):
            rows.append({
                "language_group": "english",
                "review_rating": en_rating,
                "poi_id": poi,
                "sentiment_category": "positive",
            })
        for _ in range(5):
            rows.append({
                "language_group": "japanese",
                "review_rating": jp_rating,
                "poi_id": poi,
                "sentiment_category": "neutral",
            })
    for _ in range(4):
        rows.append({
            "language_group": "english",
            "review_rating": 5,
            "poi_id": "p4",
            "sentiment_category": "positive",
        })
    for _ in range(5):
        rows.append({
            "language_group": "japanese",
            "review_rating": 1,
            "poi_id": "p4",
            "sentiment_category": "negative",
        })
    return rows


def _write_input(path: Path) -> None:
    pd.DataFrame(_synthetic_rows()).to_csv(path, index=False)


def test_paired_poi_test_positive_median_and_threshold_exclusion():
    df = pd.DataFrame(_synthetic_rows())

    result = paired_poi_test(df, outcome="rating", min_en_reviews=5)

    assert result["status"] == "skipped"
    assert result["n_pairs"] == 3
    assert result["n_shared_poi_candidates"] == 4
    assert result["n_english_reviews_paired"] == 15
    assert result["n_japanese_reviews_paired"] == 15
    assert result["threshold_min_jp_reviews"] == 5
    assert result["median_diff_en_minus_jp"] > 0
    assert result["median_diff_en_minus_jp"] == pytest.approx(2.0)


def test_within_poi_outputs_schema_manifest_and_safe_columns(tmp_path):
    source = tmp_path / "scored.csv"
    _write_input(source)

    report = build_within_poi_paired_jp_en(source, tmp_path / "out", command="pytest within")

    out = pd.read_csv(report["csv"])
    manifest = json.loads(Path(report["manifest"]).read_text(encoding="utf-8"))

    assert list(out.columns) == [
        "test_name",
        "comparison",
        "status",
        "statistic",
        "p_value",
        "effect",
        "details_json",
    ]
    assert not (FORBIDDEN & set(out.columns))
    assert set(out["test_name"]) == {
        "within_poi_paired_rating",
        "within_poi_paired_positive_share",
    }

    rating = out[out["test_name"] == "within_poi_paired_rating"].iloc[0]
    details = json.loads(rating["details_json"])
    assert rating["status"] == "skipped"
    assert details["n_pairs"] == 3
    assert details["n_shared_poi_candidates"] == 4
    assert details["n_english_reviews_paired"] == 15
    assert details["n_japanese_reviews_paired"] == 15
    assert details["threshold_min_en_reviews"] == 5
    assert details["threshold_min_jp_reviews"] == 5
    assert details["median_diff_en_minus_jp"] == pytest.approx(2.0)
    assert details["unit"] == "POI pair"
    assert "poi_id" not in rating["details_json"]

    assert manifest["kind"] == "hypothesis_within_poi_paired_jp_en"
    assert manifest["metrics"]["primary_unit"] == "POI pair"
    assert manifest["metrics"]["rating"]["n_pairs"] == 3
    assert manifest["metrics"]["rating"]["n_shared_poi_candidates"] == 4
    assert manifest["metrics"]["rating"]["n_english_reviews_paired"] == 15
    assert manifest["metrics"]["rating"]["n_japanese_reviews_paired"] == 15
    assert manifest["metrics"]["denominators"] == {"english": 19, "japanese": 20}
    assert "Within-POI paired robustness check" in " ".join(manifest["caveats"])


def test_paired_poi_all_zero_differences_skip_cleanly():
    rows = []
    for poi in ["p1", "p2", "p3", "p4", "p5", "p6"]:
        for _ in range(5):
            rows.append({
                "language_group": "english",
                "review_rating": 4,
                "poi_id": poi,
                "sentiment_category": "positive",
            })
        for _ in range(5):
            rows.append({
                "language_group": "japanese",
                "review_rating": 4,
                "poi_id": poi,
                "sentiment_category": "positive",
            })

    result = paired_poi_test(pd.DataFrame(rows), outcome="rating", min_en_reviews=5)

    assert result["status"] == "skipped"
    assert result["n_pairs"] == 6
    assert result["n_zero"] == 6
    assert result["reason"] == "all paired differences are zero"


def test_paired_poi_ok_branch_and_missing_poi_ignored():
    rows = []
    for index, poi in enumerate(["p1", "p2", "p3", "p4", "p5", "p6"], start=1):
        en_rating = 5 if index % 2 else 2
        jp_rating = 3
        for _ in range(5):
            rows.append({
                "language_group": "english",
                "review_rating": en_rating,
                "poi_id": poi,
                "sentiment_category": "positive" if en_rating > 3 else "negative",
            })
        for _ in range(5):
            rows.append({
                "language_group": "japanese",
                "review_rating": jp_rating,
                "poi_id": poi,
                "sentiment_category": "neutral",
            })
    for language in ["english", "japanese"]:
        rows.append({
            "language_group": language,
            "review_rating": 5,
            "poi_id": None,
            "sentiment_category": "positive",
        })

    result = paired_poi_test(pd.DataFrame(rows), outcome="rating", min_en_reviews=5)

    assert result["status"] == "ok"
    assert result["n_pairs"] == 6
    assert result["n_shared_poi_candidates"] == 6
    assert result["n_english_reviews_paired"] == 30
    assert result["n_japanese_reviews_paired"] == 30
    assert result["p_value"] is not None


def test_within_poi_missing_input_and_columns_fail_loud(tmp_path):
    with pytest.raises(MissingInputError, match="make sentiment-analysis"):
        build_within_poi_paired_jp_en(tmp_path / "missing.csv", tmp_path / "out")

    bad = tmp_path / "bad.csv"
    bad.write_text("language_group,review_rating,poi_id\nenglish,5,p1\njapanese,4,p1\n", encoding="utf-8")
    with pytest.raises(MissingColumnsError, match="sentiment_category"):
        build_within_poi_paired_jp_en(bad, tmp_path / "out")
