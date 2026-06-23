import json
import sys
from pathlib import Path

import pandas as pd
import pytest
from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.hypothesis_test_common import MissingColumnsError, MissingInputError
from scripts.test_h1_sentiment_category_jp_en import (
    build_h1_sentiment_category,
    cramers_v,
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


def _write_h1_input(path: Path) -> None:
    path.write_text(
        "language_group,sentiment_category,sentiment_category_neutral_0_10,sentiment_category_neutral_0_20\n"
        "english,positive,positive,neutral\n"
        "english,positive,neutral,neutral\n"
        "english,positive,positive,positive\n"
        "english,neutral,neutral,neutral\n"
        "japanese,negative,negative,negative\n"
        "japanese,negative,neutral,neutral\n"
        "japanese,neutral,neutral,neutral\n"
        "japanese,positive,positive,neutral\n",
        encoding="utf-8",
    )


def test_h1_outputs_category_test_manifest_and_safe_columns(tmp_path):
    source = tmp_path / "scored.csv"
    _write_h1_input(source)

    report = build_h1_sentiment_category(source, tmp_path / "out", command="pytest h1")

    out = pd.read_csv(report["csv"])
    manifest = json.loads(Path(report["manifest"]).read_text(encoding="utf-8"))

    assert not (FORBIDDEN & set(out.columns))
    assert set(out["analysis_type"]) == {"primary", "sensitivity"}
    assert set(out["category"]) == {"negative", "neutral", "positive"}
    assert out["source_input_sha256"].str.len().eq(64).all()
    assert out["command"].eq("pytest h1").all()
    assert out["caveat"].str.contains("not reviewer nationality").all()

    primary = out[out["analysis_type"] == "primary"].copy()
    assert primary["status"].eq("ok").all()
    assert primary["observed_count"].sum() == 8

    table = pd.DataFrame(
        [[0, 1, 3], [2, 1, 1]],
        index=["english", "japanese"],
        columns=["negative", "neutral", "positive"],
    )
    chi2, p_value, dof, expected = stats.chi2_contingency(table)
    assert primary["statistic"].iloc[0] == pytest.approx(chi2)
    assert primary["p_value"].iloc[0] == pytest.approx(p_value)
    assert primary["degrees_of_freedom"].iloc[0] == dof
    assert primary["effect_cramers_v"].iloc[0] == pytest.approx(cramers_v(table, chi2))
    assert primary["min_expected_count"].iloc[0] == pytest.approx(expected.min())
    assert primary["p_value_holm"].notna().all()

    assert manifest["schema_version"] == "research_provenance.v1"
    assert manifest["kind"] == "hypothesis_h1_sentiment_category_jp_en"
    assert manifest["metrics"]["denominators"] == {"english": 4, "japanese": 4}
    assert {record["role"] for record in manifest["inputs"]} == {"ignored_scored_review_audit_file"}
    assert {record["role"] for record in manifest["outputs"]} == {"tracked_hypothesis_test_csv"}


def test_h1_missing_input_and_columns_fail_loud(tmp_path):
    with pytest.raises(MissingInputError, match="make sentiment-analysis"):
        build_h1_sentiment_category(tmp_path / "missing.csv", tmp_path / "out")

    bad = tmp_path / "bad.csv"
    bad.write_text("language_group,sentiment_category\nenglish,positive\njapanese,negative\n", encoding="utf-8")
    with pytest.raises(MissingColumnsError, match="sentiment_category_neutral_0_10"):
        build_h1_sentiment_category(bad, tmp_path / "out")
