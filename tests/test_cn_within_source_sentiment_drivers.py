import json
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.test_cn_within_source_sentiment_drivers import (
    TOPIC_COLUMNS,
    build_cn_within_source_sentiment_drivers,
)
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


def _topic_values(active: str | None) -> list[str]:
    return ["true" if column == active else "false" for column in TOPIC_COLUMNS]


def _write_cn_input(path: Path) -> None:
    header = [
        "city",
        "source_platform",
        "theme",
        "text_length_chars",
        "body_has_text",
        "text_scope",
        "snownlp_centered_score",
        "sentiment_category",
        "any_friction",
        "any_topic",
        "any_enjoyment_evidence",
        *TOPIC_COLUMNS,
    ]
    rows = [
        ["Fukui", "xhs", "nature", "100", "true", "body", "0.80", "positive", "false", "true", "true", *_topic_values("scenic_nature")],
        ["Fukui", "xhs", "nature", "90", "true", "body", "0.60", "positive", "false", "true", "true", *_topic_values("scenic_nature")],
        ["Fukui", "douyin", "unclassified", "40", "true", "comment", "-0.50", "negative", "true", "false", "false", *_topic_values(None)],
        ["Fukui", "douyin", "unclassified", "35", "true", "comment", "-0.40", "negative", "true", "false", "false", *_topic_values(None)],
        ["Fukui", "xhs", "food", "75", "true", "body", "0.30", "positive", "false", "true", "true", *_topic_values("food_local_cuisine")],
        ["Fukui", "xhs", "food", "65", "true", "body", "0.20", "positive", "false", "true", "false", *_topic_values("food_local_cuisine")],
        ["Fukui", "douyin", "unclassified", "20", "false", "title", "0.90", "positive", "false", "false", "false", *_topic_values(None)],
    ]
    path.write_text(",".join(header) + "\n" + "\n".join(",".join(row) for row in rows) + "\n", encoding="utf-8")


def test_cn_outputs_topic_platform_theme_diagnostics_and_manifest(tmp_path):
    source = tmp_path / "tagged.csv"
    _write_cn_input(source)

    report = build_cn_within_source_sentiment_drivers(source, tmp_path / "out", command="pytest wl-cn")

    out = pd.read_csv(report["csv"])
    manifest = json.loads(Path(report["manifest"]).read_text(encoding="utf-8"))

    assert not (FORBIDDEN & set(out.columns))
    assert {"WL-CN-1", "WL-CN-2", "WL-CN-3", "WL-CN-4"} <= set(out["analysis_id"])
    assert out["language_source_group"].eq("Chinese-language Fukui social rows").all()
    assert out["source_input_sha256"].str.len().eq(64).all()
    assert out["caveat"].str.contains("unclassified").all()

    friction = out[(out["analysis_id"] == "WL-CN-1") & (out["test_name"] == "mann_whitney_u_sentiment_score")].iloc[0]
    assert friction["status"] == "ok"
    assert friction["group_a_n"] == 2
    assert friction["group_b_n"] == 4
    assert friction["effect_size"] < 0

    topic_rows = out[out["multiple_testing_family"] == "chinese_topic_predictors"]
    assert len(topic_rows) == len(TOPIC_COLUMNS) * 2
    assert topic_rows["p_value_bh_fdr"].notna().any()

    theme = out[out["analysis_id"] == "WL-CN-4"].iloc[0]
    assert theme["status"] == "skipped"
    assert "group_counts" in json.loads(theme["details_json"])

    assert manifest["kind"] == "within_source_sentiment_drivers_cn"
    assert manifest["metrics"]["denominators"] == {"chinese_social_rows": 6}


def test_cn_missing_input_and_columns_fail_loud(tmp_path):
    with pytest.raises(MissingInputError, match="make chinese-social"):
        build_cn_within_source_sentiment_drivers(tmp_path / "missing.csv", tmp_path / "out")

    bad = tmp_path / "bad.csv"
    bad.write_text("source_platform,snownlp_centered_score\nxhs,0.1\n", encoding="utf-8")
    with pytest.raises(MissingColumnsError, match="body_has_text"):
        build_cn_within_source_sentiment_drivers(bad, tmp_path / "out")
