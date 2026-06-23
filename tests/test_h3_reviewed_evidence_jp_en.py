import json
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.hypothesis_test_common import MissingColumnsError, MissingInputError
from scripts.test_h3_reviewed_evidence_jp_en import build_h3_reviewed_evidence


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


def _write_h3_input(path: Path) -> None:
    path.write_text(
        "language_group,text_length_chars,any_friction,any_enjoyment_evidence,any_recommendation_evidence,any_positive_evidence\n"
        "english,120,true,true,true,true\n"
        "english,80,false,true,false,true\n"
        "english,60,false,false,false,false\n"
        "english,40,false,false,false,true\n"
        "japanese,50,true,false,false,false\n"
        "japanese,45,true,false,false,false\n"
        "japanese,70,false,true,false,true\n"
        "japanese,90,false,false,true,false\n",
        encoding="utf-8",
    )


def test_h3_outputs_evidence_family_tests_fdr_and_safe_manifest(tmp_path):
    source = tmp_path / "scored.csv"
    _write_h3_input(source)

    report = build_h3_reviewed_evidence(source, tmp_path / "out", command="pytest h3")

    out = pd.read_csv(report["csv"])
    manifest = json.loads(Path(report["manifest"]).read_text(encoding="utf-8"))

    assert not (FORBIDDEN & set(out.columns))
    family_rows = out[out["analysis_type"] == "evidence_family_test"]
    assert set(family_rows["evidence_column"]) == {
        "any_friction",
        "any_enjoyment_evidence",
        "any_recommendation_evidence",
        "any_positive_evidence",
    }
    assert family_rows["p_value_bh_fdr"].notna().all()
    assert family_rows["source_input_sha256"].str.len().eq(64).all()
    assert family_rows["caveat"].str.contains("does not prove motive").all()

    positive = family_rows[family_rows["evidence_column"] == "any_positive_evidence"].iloc[0]
    assert positive["english_n"] == 4
    assert positive["english_present_count"] == 3
    assert positive["english_present_pct"] == pytest.approx(0.75)
    assert positive["japanese_present_count"] == 1
    assert positive["risk_difference_pct"] == pytest.approx(50.0)
    assert positive["test_name"] in {"fisher_exact_evidence_prevalence", "chi_square_evidence_prevalence"}

    diagnostic = out[out["test_name"] == "text_length_summary_by_language_group"].iloc[0]
    text_summary = json.loads(diagnostic["text_length_summary_json"])
    assert text_summary["english"]["n"] == 4
    assert text_summary["japanese"]["median"] == pytest.approx(60.0)

    assert manifest["kind"] == "hypothesis_h3_reviewed_evidence_jp_en"
    assert manifest["metrics"]["multiple_testing"].startswith("Benjamini-Hochberg")
    assert manifest["metrics"]["denominators"] == {"english": 4, "japanese": 4}


def test_h3_missing_input_and_columns_fail_loud(tmp_path):
    with pytest.raises(MissingInputError, match="make sentiment-analysis"):
        build_h3_reviewed_evidence(tmp_path / "missing.csv", tmp_path / "out")

    bad = tmp_path / "bad.csv"
    bad.write_text(
        "language_group,text_length_chars,any_friction\nenglish,10,true\njapanese,20,false\n",
        encoding="utf-8",
    )
    with pytest.raises(MissingColumnsError, match="any_positive_evidence"):
        build_h3_reviewed_evidence(bad, tmp_path / "out")
