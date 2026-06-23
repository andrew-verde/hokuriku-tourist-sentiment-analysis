import json
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.test_jp_within_language_sentiment_drivers import build_jp_within_language_sentiment_drivers
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
        "japanese,Fukui,0.70,positive,false,true,true,true,5,museum,p1,100\n"
        "japanese,Fukui,0.50,positive,false,true,false,true,4,museum,p1,90\n"
        "japanese,Fukui,-0.40,negative,true,false,false,false,2,temple,p2,80\n"
        "japanese,Fukui,-0.20,negative,true,false,false,false,2,temple,p2,70\n"
        "japanese,Fukui,0.10,positive,false,false,true,true,4,park,p3,60\n"
        "japanese,Fukui,0.00,neutral,false,false,false,false,3,park,p3,50\n"
        "english,Fukui,0.20,positive,false,true,false,true,4,museum,p4,40\n",
        encoding="utf-8",
    )


def test_jp_outputs_within_language_rows_and_manifest(tmp_path):
    source = tmp_path / "scored.csv"
    _write_review_input(source)

    report = build_jp_within_language_sentiment_drivers(source, tmp_path / "out", command="pytest wl-jp")

    out = pd.read_csv(report["csv"])
    manifest = json.loads(Path(report["manifest"]).read_text(encoding="utf-8"))

    assert not (FORBIDDEN & set(out.columns))
    assert set(out["analysis_id"]) == {"WL-JP-1", "WL-JP-2", "WL-JP-3", "WL-JP-4"}
    assert out["language_source_group"].eq("Japanese-language Fukui Google reviews").all()
    assert out["research_question"].str.contains("English-language").sum() == 0
    assert out["research_question"].str.contains("oseti").any()
    assert out["caveat"].str.contains("within Japanese only").all()

    friction = out[(out["analysis_id"] == "WL-JP-1") & (out["test_name"] == "mann_whitney_u_sentiment_score")].iloc[0]
    assert friction["status"] == "ok"
    assert friction["effect_size"] < 0
    assert pd.notna(friction["p_value_bh_fdr"])

    assert manifest["kind"] == "within_language_sentiment_drivers_jp"
    assert manifest["metrics"]["denominators"] == {"japanese": 6}
    assert manifest["filters"]["language_group"] == "japanese"


def test_jp_missing_input_and_columns_fail_loud(tmp_path):
    with pytest.raises(MissingInputError, match="make sentiment-analysis"):
        build_jp_within_language_sentiment_drivers(tmp_path / "missing.csv", tmp_path / "out")

    bad = tmp_path / "bad.csv"
    bad.write_text("language_group,sentiment_score\njapanese,0.1\n", encoding="utf-8")
    with pytest.raises(MissingColumnsError, match="poi_category"):
        build_jp_within_language_sentiment_drivers(bad, tmp_path / "out")
