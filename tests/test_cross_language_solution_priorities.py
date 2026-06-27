import json
import sys
from pathlib import Path

import pandas as pd
import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.build_cross_language_solution_priorities import (  # noqa: E402
    ASPECT_INPUT,
    CN_ENJOYMENT_INPUT,
    CN_FRICTION_INPUT,
    CN_WITHIN_INPUT,
    CONFIG,
    H3_INPUT,
    SolutionPriorityError,
    build_cross_language_solution_priorities,
)


FORBIDDEN = {
    "review_text",
    "text_content",
    "author",
    "url",
    "poi_id",
    "review_id",
    "source_record_id",
}


def test_real_aggregate_inputs_rank_expected_solutions(tmp_path):
    result = build_cross_language_solution_priorities(output_dir=tmp_path)
    priorities = pd.read_csv(result["priorities"])
    evidence = pd.read_csv(result["evidence"])
    manifest = json.loads(result["manifest"].read_text(encoding="utf-8"))

    assert priorities["solution_id"].tolist() == [
        "visit_readiness_card",
        "localized_discovery_card",
        "off_peak_alternative_prompt",
    ]
    assert priorities["rank"].tolist() == [1, 2, 3]
    assert priorities["language_support_count"].eq(3).all()
    assert priorities["support_rule"].eq("all_three").all()
    assert priorities["impact_tier"].tolist() == ["High", "High", "Medium"]
    assert priorities["ease_tier"].tolist() == ["Easy", "Moderate", "Harder"]
    assert len(evidence) == 9
    assert set(evidence["language_source_group"]) == {"english", "japanese", "chinese"}
    assert not (FORBIDDEN & set(priorities.columns))
    assert not (FORBIDDEN & set(evidence.columns))
    assert manifest["metrics"]["fallback_used"] is False
    assert manifest["metrics"]["ranked_solution_ids"] == priorities["solution_id"].tolist()
    assert all(item["sha256"] for item in manifest["inputs"])


def test_missing_input_fails_loud(tmp_path):
    with pytest.raises(SolutionPriorityError, match="Required input missing"):
        build_cross_language_solution_priorities(
            aspect_path=tmp_path / "missing.csv",
            output_dir=tmp_path / "out",
        )


def test_duplicate_required_row_fails_loud(tmp_path):
    aspects = pd.read_csv(ASPECT_INPUT)
    duplicate = aspects[
        (aspects["analysis"] == "A_primary")
        & (aspects["segment"] == "english")
        & (aspects["aspect"] == "opening_hours_availability")
    ]
    broken = pd.concat([aspects, duplicate], ignore_index=True)
    aspect_path = tmp_path / "duplicate.csv"
    broken.to_csv(aspect_path, index=False)

    with pytest.raises(SolutionPriorityError, match="Expected exactly one row"):
        build_cross_language_solution_priorities(
            config_path=CONFIG,
            aspect_path=aspect_path,
            h3_path=H3_INPUT,
            cn_friction_path=CN_FRICTION_INPUT,
            cn_enjoyment_path=CN_ENJOYMENT_INPUT,
            cn_within_path=CN_WITHIN_INPUT,
            output_dir=tmp_path / "out",
        )


def test_two_of_three_used_only_when_no_all_three_solution(tmp_path):
    config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    config["solutions"] = [
        item for item in config["solutions"] if item["solution_id"] == "off_peak_alternative_prompt"
    ]
    config_path = tmp_path / "mapping.yaml"
    config_path.write_text(yaml.safe_dump(config, allow_unicode=True), encoding="utf-8")

    aspects = pd.read_csv(ASPECT_INPUT)
    mask = (
        (aspects["analysis"] == "A_primary")
        & (aspects["segment"] == "english")
        & (aspects["aspect"] == "waiting_crowding")
    )
    aspects.loc[mask, "n_positive"] = 0
    aspect_path = tmp_path / "aspects.csv"
    aspects.to_csv(aspect_path, index=False)

    result = build_cross_language_solution_priorities(
        config_path=config_path,
        aspect_path=aspect_path,
        output_dir=tmp_path / "out",
    )
    priorities = pd.read_csv(result["priorities"])
    manifest = json.loads(result["manifest"].read_text(encoding="utf-8"))

    assert priorities["support_rule"].tolist() == ["two_of_three_fallback"]
    assert priorities["language_support_count"].tolist() == [2]
    assert manifest["metrics"]["fallback_used"] is True
