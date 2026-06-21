import json
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.build_presentation_safe_outputs import (
    FORBIDDEN_PRESENTATION_COLUMNS,
    MissingColumnsError,
    MissingInputError,
    build_presentation_safe_outputs,
)


def _write_inputs(tmp_path: Path) -> tuple[Path, Path, Path, Path, Path]:
    summary = tmp_path / "source_group_sentiment_summary.csv"
    summary.write_text(
        "source_group,language_group,prefecture_normalized,city,n_reviews,n_scored,"
        "mean_sentiment_score,median_sentiment_score,mean_review_rating,n_review_rating_present,"
        "negative_count,negative_pct,neutral_count,neutral_pct,positive_count,positive_pct,"
        "rating_distribution_json\n"
        'google_maps_outscraper,english,Fukui,Fukui,2,2,0.4,0.4,4.5,2,0,0.0,1,0.5,1,0.5,"{""4"": 1, ""5"": 1}"\n'
        'google_maps_outscraper,japanese,Fukui,Fukui,3,3,0.2,0.2,4.0,3,1,0.333333,1,0.333333,1,0.333333,"{""3"": 1, ""4"": 1, ""5"": 1}"\n',
        encoding="utf-8",
    )
    tests = tmp_path / "source_group_sentiment_tests.csv"
    tests.write_text(
        "test_name,comparison,status,statistic,p_value,effect,details_json\n"
        'chi_square_sentiment_category,english_vs_japanese,ok,1.2,0.3,0.1,"{}"\n'
        'cluster_bootstrap_poi_mean_difference_sentiment_score,english_vs_japanese,ok,0.2,,0.2,"{}"\n',
        encoding="utf-8",
    )
    manifest = tmp_path / "sentiment_manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": "sentiment_manifest.v2",
                "codebook_evidence_status": "pending",
                "input": {
                    "sha256": "a" * 64,
                    "poi_metadata_sha256": "b" * 64,
                },
                "outputs": {
                    "row_level_path": str(tmp_path / "google_reviews_fukui_japanese-english.csv"),
                },
                "provenance": {
                    "caveats": [
                        "Group labels describe review language, not reviewer nationality.",
                        "VADER and oseti scores are tool-specific.",
                    ]
                },
            }
        ),
        encoding="utf-8",
    )
    row_level = tmp_path / "google_reviews_fukui_japanese-english.csv"
    row_level.write_text(
        "review_id,city,prefecture_normalized,municipality,poi_id,poi_category,review_date,"
        "review_rating,language_group,text_length_chars,sentiment_score,sentiment_category\n"
        "r1,Fukui,Fukui,Fukui,p1,temple_shrine,2026-05-01T00:00:00+00:00,5,english,20,0.5,positive\n"
        "r2,Fukui,Fukui,Fukui,p2,museum,2026-05-03T00:00:00+00:00,4,english,21,0.0,neutral\n"
        "r3,Fukui,Fukui,Fukui,p3,temple_shrine,2026-05-02T00:00:00+00:00,5,japanese,22,0.5,positive\n"
        "r4,Fukui,Fukui,Fukui,p4,park,2026-05-04T00:00:00+00:00,3,japanese,23,0.0,neutral\n"
        "r5,Fukui,Fukui,Fukui,p5,park,2026-05-05T00:00:00+00:00,2,japanese,24,-0.5,negative\n",
        encoding="utf-8",
    )
    baseline = tmp_path / "cross_language_baseline_snapshot.csv"
    baseline.write_text(
        "prefecture,city,group,source_kind,volume,rating_mean,sentiment_norm_mean,positive_pct,neutral_pct,negative_pct\n"
        "Fukui,Fukui,chinese_social_douyin,chinese_social_post,10,,0.7,70.0,10.0,20.0\n"
        "Fukui,Fukui,chinese_social_xiaohongshu,chinese_social_post,5,,0.8,80.0,0.0,20.0\n"
        "Fukui,Fukui,english,google_review,2,4.5,,,\n"
        "Fukui,Fukui,japanese,google_review,3,4.0,,,\n",
        encoding="utf-8",
    )
    cross_tests = tmp_path / "cross_language_statistical_tests.csv"
    cross_tests.write_text(
        "test_name,comparison,status,statistic,p_value,effect,details_json\n"
        'cross_source_sentiment_category_independence,all,ok,3.2,0.04,0.2,"{}"\n'
        'within_chinese_platform_sentiment_category_independence,chinese_source_platforms,ok,1.1,0.2,0.1,"{}"\n'
        'cross_source_friction_prevalence_not_run,all,skipped,,,"","{}"\n'
        'cross_source_enjoyment_recommendation_prevalence_not_run,all,skipped,,,"","{}"\n',
        encoding="utf-8",
    )
    return summary, tests, manifest, baseline, cross_tests


def test_builds_presentation_safe_aggregate_files_with_required_provenance(tmp_path):
    summary, tests, manifest, baseline, cross_tests = _write_inputs(tmp_path)

    report = build_presentation_safe_outputs(
        sentiment_summary_path=summary,
        sentiment_tests_path=tests,
        sentiment_manifest_path=manifest,
        cross_language_baseline_path=baseline,
        cross_language_tests_path=cross_tests,
        output_dir=tmp_path / "presentation",
        command="pytest command",
    )

    chart = pd.read_csv(tmp_path / "presentation" / "jp_en_library_sentiment_chart_data.csv")
    sensitivity = pd.read_csv(
        tmp_path / "presentation" / "jp_en_statistical_sensitivity_summary.csv"
    )
    readiness = (tmp_path / "presentation" / "presentation_readiness.md").read_text(
        encoding="utf-8"
    )
    figure_questions = (
        tmp_path / "presentation" / "presentation_figure_questions.md"
    ).read_text(encoding="utf-8")
    manifest_out = json.loads(
        (tmp_path / "presentation" / "presentation_manifest.json").read_text(encoding="utf-8")
    )
    figure_paths = [
        tmp_path / "presentation" / "japanese" / "figure_japanese_sentiment_profile.svg",
        tmp_path / "presentation" / "japanese" / "figure_japanese_poi_priority_mix.svg",
        tmp_path / "presentation" / "english" / "figure_english_sentiment_profile.svg",
        tmp_path / "presentation" / "english" / "figure_english_poi_priority_mix.svg",
        tmp_path / "presentation" / "multilingual" / "figure_sentiment_share_by_language_source.svg",
        tmp_path / "presentation" / "multilingual" / "figure_volume_context.svg",
        tmp_path / "presentation" / "multilingual" / "figure_statistical_evidence_summary.svg",
    ]

    assert set(chart["language_source_group"]) == {
        "english-language Google reviews",
        "japanese-language Google reviews",
    }
    assert chart["n_reviews"].sum() == 5
    assert set(chart["date_range_start"]) == {"2026-05-01", "2026-05-02"}
    assert set(chart["date_range_end"]) == {"2026-05-03", "2026-05-05"}
    assert chart["review_date_parseable_count"].sum() == 5
    assert chart["review_date_missing_count"].sum() == 0
    assert any("temple_shrine=1" in value for value in set(chart["poi_mix"]))
    assert chart["source_hashes"].str.contains("a" * 64).all()
    assert chart["caveat"].str.contains("secondary library-score check", case=False).all()
    assert not (FORBIDDEN_PRESENTATION_COLUMNS & set(chart.columns))
    assert not (FORBIDDEN_PRESENTATION_COLUMNS & set(sensitivity.columns))
    assert not chart.astype(str).apply(lambda col: col.str.contains("unavailable|placeholder|dummy", case=False)).any().any()

    assert "Date range: derived from parseable review_date values" in readiness
    assert "Date coverage: chart data includes parseable and missing review_date counts" in readiness
    assert "POI mix: derived from ignored scored-review audit file" in readiness
    assert "`japanese/`" in readiness
    assert "`english/`" in readiness
    assert "`multilingual/`" in readiness
    assert "Questions answered by each figure" in readiness
    assert "Question answered: What share of japanese-language Fukui Google reviews" in figure_questions
    assert "Question answered: How do positive, neutral, and negative category shares differ" in figure_questions
    for path in figure_paths:
        assert path.exists()
        svg = path.read_text(encoding="utf-8")
        assert "<svg" in svg
        assert "placeholder" not in svg.lower()
    assert "not nationality" in readiness
    assert "reviewer" not in "\n".join(chart.astype(str).to_numpy().ravel())

    assert report["schema_version"] == "research_provenance.v1"
    assert manifest_out["metrics"]["review_rows_represented"] == 5
    assert manifest_out["metrics"]["codebook_evidence_status"] == "pending"
    assert manifest_out["metrics"]["date_range_status"] == "derived_from_scored_review_audit_file"
    assert manifest_out["metrics"]["poi_mix_status"] == "derived_from_scored_review_audit_file"
    assert manifest_out["metrics"]["figure_count"] == 7
    assert manifest_out["extra"]["source_hashes"]["reviews_input_sha256"] == "a" * 64
    output_roles = {record["role"] for record in manifest_out["outputs"]}
    assert {
        "presentation_chart_data",
        "presentation_statistical_summary",
        "presentation_figure_questions",
        "presentation_readiness_markdown",
    } <= output_roles
    assert len([role for role in output_roles if role.startswith("presentation_figure_")]) == 8
    input_roles = {record["role"] for record in manifest_out["inputs"]}
    assert "ignored_scored_review_audit_file" in input_roles
    assert "aggregate_cross_language_baseline" in input_roles
    assert "aggregate_cross_language_statistical_tests" in input_roles


def test_missing_inputs_and_required_columns_fail_loud(tmp_path):
    summary, tests, manifest, baseline, cross_tests = _write_inputs(tmp_path)

    with pytest.raises(MissingInputError, match="make sentiment-analysis"):
        build_presentation_safe_outputs(
            sentiment_summary_path=tmp_path / "missing.csv",
            sentiment_tests_path=tests,
            sentiment_manifest_path=manifest,
            cross_language_baseline_path=baseline,
            cross_language_tests_path=cross_tests,
            output_dir=tmp_path / "presentation",
        )

    bad_summary = tmp_path / "bad_summary.csv"
    bad_summary.write_text("language_group,n_reviews\nenglish,1\n", encoding="utf-8")
    with pytest.raises(MissingColumnsError, match="positive_pct"):
        build_presentation_safe_outputs(
            sentiment_summary_path=bad_summary,
            sentiment_tests_path=tests,
            sentiment_manifest_path=manifest,
            cross_language_baseline_path=baseline,
            cross_language_tests_path=cross_tests,
            output_dir=tmp_path / "presentation",
        )
