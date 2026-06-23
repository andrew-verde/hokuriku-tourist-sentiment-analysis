import json
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.test_en_within_language_sentiment_drivers import build_en_within_language_sentiment_drivers
from scripts.within_language_sentiment_common import MissingColumnsError, MissingInputError


FORBIDDEN = {
    "review_text",
    "text_content",
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
    "source_record_id",
    "title",
}


def _write_review_input(path: Path) -> None:
    path.write_text(
        "language_group,prefecture_normalized,sentiment_score,sentiment_category,any_friction,any_enjoyment_evidence,any_recommendation_evidence,any_positive_evidence,review_rating,poi_category,poi_id,text_length_chars\n"
        "english,Fukui,0.80,positive,false,true,true,true,5,museum,p1,100\n"
        "english,Fukui,0.60,positive,false,true,false,true,5,museum,p1,90\n"
        "english,Fukui,-0.50,negative,true,false,false,false,2,temple,p2,80\n"
        "english,Fukui,-0.30,negative,true,false,false,false,2,temple,p2,70\n"
        "english,Fukui,0.10,positive,false,false,true,true,4,park,p3,60\n"
        "english,Fukui,0.00,neutral,false,false,false,false,3,park,p3,50\n"
        "japanese,Fukui,0.20,positive,false,true,false,true,4,museum,p4,40\n",
        encoding="utf-8",
    )


def test_en_outputs_within_language_rows_fdr_and_manifest(tmp_path):
    source = tmp_path / "scored.csv"
    _write_review_input(source)

    report = build_en_within_language_sentiment_drivers(source, tmp_path / "out", command="pytest wl-en")

    out = pd.read_csv(report["csv"])
    manifest = json.loads(Path(report["manifest"]).read_text(encoding="utf-8"))

    assert not (FORBIDDEN & set(out.columns))
    assert set(out["analysis_id"]) == {"WL-EN-1", "WL-EN-2", "WL-EN-3", "WL-EN-4"}
    assert out["language_source_group"].eq("English-language Fukui Google reviews").all()
    assert out["source_input_sha256"].str.len().eq(64).all()
    assert out["command"].eq("pytest wl-en").all()
    assert out["caveat"].str.contains("within English only").all()

    friction = out[(out["analysis_id"] == "WL-EN-1") & (out["test_name"] == "mann_whitney_u_sentiment_score")].iloc[0]
    assert friction["status"] == "ok"
    assert friction["group_a_n"] == 2
    assert friction["group_b_n"] == 4
    assert friction["effect_size"] == pytest.approx(((-0.5 - 0.3) / 2) - ((0.8 + 0.6 + 0.1 + 0.0) / 4))
    assert pd.notna(friction["p_value_bh_fdr"])

    rating = out[out["test_name"] == "spearman_score_rating"].iloc[0]
    assert rating["status"] == "ok"
    assert rating["effect_size"] > 0

    assert manifest["kind"] == "within_language_sentiment_drivers_en"
    assert manifest["metrics"]["denominators"] == {"english": 6}
    assert manifest["filters"]["language_group"] == "english"


def test_en_missing_input_and_columns_fail_loud(tmp_path):
    with pytest.raises(MissingInputError, match="make sentiment-analysis"):
        build_en_within_language_sentiment_drivers(tmp_path / "missing.csv", tmp_path / "out")

    bad = tmp_path / "bad.csv"
    bad.write_text("language_group,sentiment_score\nenglish,0.1\n", encoding="utf-8")
    with pytest.raises(MissingColumnsError, match="review_rating"):
        build_en_within_language_sentiment_drivers(bad, tmp_path / "out")
