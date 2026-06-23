import json
import sys
from pathlib import Path

import pandas as pd
import pytest
from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.hypothesis_test_common import MissingColumnsError, MissingInputError
from scripts.test_h2_review_rating_jp_en import build_h2_review_rating


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


def _write_h2_input(path: Path) -> None:
    path.write_text(
        "language_group,review_rating,poi_id\n"
        "english,5,p1\n"
        "english,4,p1\n"
        "english,5,p2\n"
        "english,,p3\n"
        "japanese,3,p4\n"
        "japanese,4,p4\n"
        "japanese,2,p5\n"
        "japanese,3,p6\n",
        encoding="utf-8",
    )


def test_h2_outputs_welch_rating_tests_and_safe_manifest(tmp_path):
    source = tmp_path / "scored.csv"
    _write_h2_input(source)

    report = build_h2_review_rating(source, tmp_path / "out", command="pytest h2")

    out = pd.read_csv(report["csv"])
    manifest = json.loads(Path(report["manifest"]).read_text(encoding="utf-8"))

    assert not (FORBIDDEN & set(out.columns))
    assert {"rating_descriptives", "welch_t_review_rating", "poi_level_welch_t_mean_review_rating"} <= set(out["test_name"])
    assert "mann_whitney_u_review_rating" in set(out["test_name"])
    assert "chi_square_rating_distribution" in set(out["test_name"])
    assert out["source_input_sha256"].str.len().eq(64).all()

    english = out[(out["test_name"] == "rating_descriptives") & (out["language_group"] == "english")].iloc[0]
    assert english["n_rating_present"] == 3
    assert english["n_rating_missing"] == 1
    assert english["mean_review_rating"] == pytest.approx((5 + 4 + 5) / 3)
    assert json.loads(english["rating_distribution_json"]) == {"1": 0, "2": 0, "3": 0, "4": 1, "5": 2}

    welch = out[out["test_name"] == "welch_t_review_rating"].iloc[0]
    result = stats.ttest_ind([5, 4, 5], [3, 4, 2, 3], equal_var=False, alternative="two-sided")
    assert welch["status"] == "ok"
    assert welch["statistic"] == pytest.approx(result.statistic)
    assert welch["p_value"] == pytest.approx(result.pvalue)
    assert welch["effect_mean_difference"] == pytest.approx(((5 + 4 + 5) / 3) - 3)
    assert welch["ci_95_lower"] < welch["effect_mean_difference"] < welch["ci_95_upper"]

    poi = out[out["test_name"] == "poi_level_welch_t_mean_review_rating"].iloc[0]
    assert poi["status"] == "ok"
    assert "POI-language mean" in poi["unit"]

    assert manifest["kind"] == "hypothesis_h2_review_rating_jp_en"
    assert manifest["metrics"]["measurement_scale"] == "common_google_1_to_5_star_rating"
    assert manifest["metrics"]["denominators"] == {"english": 4, "japanese": 4}


def test_h2_missing_input_and_columns_fail_loud(tmp_path):
    with pytest.raises(MissingInputError, match="make sentiment-analysis"):
        build_h2_review_rating(tmp_path / "missing.csv", tmp_path / "out")

    bad = tmp_path / "bad.csv"
    bad.write_text("language_group,review_rating\nenglish,5\njapanese,4\n", encoding="utf-8")
    with pytest.raises(MissingColumnsError, match="poi_id"):
        build_h2_review_rating(bad, tmp_path / "out")
