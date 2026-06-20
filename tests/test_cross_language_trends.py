import sys
import json
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.build_cross_language_trends import (
    MissingInputError,
    build_cross_language_trends,
)


def _write_inputs(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    # Create three fake input files matching the real pipeline contracts:
    # multilingual reviews, Chinese social rows, and POI prefecture metadata.
    reviews = tmp_path / "reviews_multilingual.csv"
    reviews.write_text(
        "city,poi_id,language_group,review_date,review_rating,review_text\n"
        "Fukui,p1,english,2025-08-03T10:00:00Z,5,Great cliffs\n"
        "Fukui,p1,english,2025-08-20T10:00:00Z,3,Hard to reach\n"
        "Fukui,p2,japanese,2025-08-05T10:00:00Z,4,良かった\n"
        "Toyama,p3,english,2025-08-05T10:00:00Z,5,Great but out of scope\n"
        "Fukui,p1,other_non_english_non_japanese,2025-08-05T10:00:00Z,4,bra\n",
        encoding="utf-8",
    )
    metadata = tmp_path / "poi_metadata.json"
    metadata.write_text(
        json.dumps(
            {
                "p1": {"prefecture_normalized": "Fukui", "municipality": "Fukui"},
                "p2": {"prefecture_normalized": "Fukui", "municipality": "Eiheiji"},
                "p3": {"prefecture_normalized": "Toyama", "municipality": "Toyama"},
            }
        ),
        encoding="utf-8",
    )
    chinese = tmp_path / "tagged_chinese_social_posts.csv"
    chinese.write_text(
        "city,source_platform,text_content,post_date,post_date_precision,sentiment_norm,sentiment_category,theme,any_friction,any_enjoyment_evidence\n"
        "Fukui,xiaohongshu,福井交通不便,2025-08-14,exact,0.1,negative,travel,True,False\n"
        "Fukui,xiaohongshu,走Riku走过的道路,2025-08-30,year_inferred,0.9,positive,fan,False,True\n"
        "Fukui,douyin,无日期帖子,,none,0.5,neutral,ordinary,False,False\n"
        "Toyama,xiaohongshu,富山帖子,2025-08-14,exact,0.8,positive,travel,False,True\n",
        encoding="utf-8",
    )
    sentiment_summary = tmp_path / "source_group_sentiment_summary.csv"
    sentiment_summary.write_text(
        "source_group,language_group,prefecture_normalized,city,n_reviews,n_scored,negative_count,negative_pct,neutral_count,neutral_pct,positive_count,positive_pct\n"
        "google_maps_outscraper,english,Fukui,Fukui,2,2,0,0.0,1,0.5,1,0.5\n"
        "google_maps_outscraper,japanese,Fukui,Fukui,1,1,0,0.0,0,0.0,1,1.0\n"
        "google_maps_outscraper,english,Toyama,Toyama,1,1,1,1.0,0,0.0,0,0.0\n",
        encoding="utf-8",
    )
    return reviews, chinese, metadata, sentiment_summary


def test_baseline_filters_reviews_by_prefecture_metadata_and_keeps_scales_separate(tmp_path):
    # Google ratings and Chinese sentiment are different scales, so the baseline
    # should put them in separate columns instead of blending them.
    reviews, chinese, metadata, sentiment_summary = _write_inputs(tmp_path)

    report = build_cross_language_trends(
        reviews_path=reviews,
        chinese_path=chinese,
        poi_metadata_path=metadata,
        sentiment_summary_path=sentiment_summary,
        output_dir=tmp_path / "out",
    )

    baseline = pd.read_csv(tmp_path / "out" / "cross_language_baseline_snapshot.csv")
    assert set(baseline["group"]) == {"english", "japanese", "chinese_social_xiaohongshu", "chinese_social_douyin"}
    assert set(baseline["prefecture"]) == {"Fukui"}
    assert report["review_rows_retained"] == 3
    assert report["chinese_rows_retained"] == 3
    assert report["schema_version"] == "cross_language_trends_manifest.v2"
    assert len(report["reviews_input_sha256"]) == 64
    assert len(report["chinese_input_sha256"]) == 64
    assert report["monthly_trends_enabled"] is False
    assert not (tmp_path / "out" / "monthly_trends.csv").exists()
    tests = pd.read_csv(tmp_path / "out" / "cross_language_statistical_tests.csv")
    assert "cross_source_sentiment_category_independence" in set(tests["test_name"])
    assert "pairwise_cross_source_sentiment_category_independence" in set(tests["test_name"])
    assert "within_chinese_platform_sentiment_category_independence" in set(tests["test_name"])
    assert "within_chinese_platform_any_friction_prevalence" in set(tests["test_name"])
    assert "within_chinese_platform_any_enjoyment_evidence_prevalence" in set(tests["test_name"])
    assert (
        tests[tests["test_name"] == "within_chinese_platform_any_friction_prevalence"]
        .iloc[0]["status"]
        == "ok"
    )
    assert (
        tests[tests["test_name"] == "within_chinese_platform_any_enjoyment_evidence_prevalence"]
        .iloc[0]["status"]
        == "ok"
    )
    friction_skip = tests[tests["test_name"] == "cross_source_friction_prevalence_not_run"].iloc[0]
    assert friction_skip["status"] == "skipped"
    assert "Reviewed EN/JP keyword evidence is not ready" in friction_skip["details_json"]

    manifest = json.loads((tmp_path / "out" / "cross_language_trends_readiness.json").read_text(encoding="utf-8"))
    assert manifest["provenance"]["schema_version"] == "research_provenance.v1"
    assert manifest["provenance"]["metrics"]["review_scope_method"] == ["poi_metadata_prefecture"]
    assert manifest["provenance"]["metrics"]["chinese_scope_method"] == ["source_city_label"]
    assert {record["role"] for record in manifest["provenance"]["inputs"]} == {
        "reviews_multilingual",
        "poi_metadata",
        "tagged_chinese_social_posts",
        "jp_en_sentiment_summary",
    }
    assert all("sha256" in record for record in manifest["provenance"]["inputs"])

    english = baseline[baseline["group"] == "english"].iloc[0]
    # Google-review rows keep rating means but do not get Chinese sentiment means.
    assert english["volume"] == 2
    assert english["rating_mean"] == 4.0
    assert pd.isna(english["sentiment_norm_mean"])

    xhs = baseline[baseline["group"] == "chinese_social_xiaohongshu"].iloc[0]
    # Chinese social rows keep SnowNLP sentiment means but do not get Google ratings.
    assert xhs["volume"] == 2
    assert pd.isna(xhs["rating_mean"])
    assert xhs["sentiment_norm_mean"] == 0.5


def test_date_scrub_requirements_replace_monthly_theme_mix(tmp_path):
    # Monthly trend outputs are disabled; this test checks that date quality is
    # reported instead of silently publishing a weak monthly trend.
    reviews, chinese, metadata, sentiment_summary = _write_inputs(tmp_path)

    build_cross_language_trends(
        reviews_path=reviews,
        chinese_path=chinese,
        poi_metadata_path=metadata,
        sentiment_summary_path=sentiment_summary,
        output_dir=tmp_path / "out",
    )

    scrub = pd.read_csv(tmp_path / "out" / "date_scrub_requirements.csv")
    chinese_scrub = scrub[scrub["source_kind"] == "chinese_social_post"]
    assert set(chinese_scrub["date_precision"]) == {"exact", "year_inferred", "none"}
    assert not chinese_scrub[chinese_scrub["date_precision"] == "year_inferred"]["usable_for_monthly_trends"].iloc[0]
    assert "Recover exact source post date" in (
        tmp_path / "out" / "cross_language_trends_readiness.md"
    ).read_text(encoding="utf-8")


def test_missing_inputs_fail_with_make_target_hint(tmp_path):
    # Missing prerequisites should fail with a concrete make target for repair.
    reviews, chinese, metadata, sentiment_summary = _write_inputs(tmp_path)

    with pytest.raises(MissingInputError, match="make multilingual-reviews"):
        build_cross_language_trends(
            reviews_path=tmp_path / "absent.csv",
            chinese_path=chinese,
            poi_metadata_path=metadata,
            sentiment_summary_path=sentiment_summary,
            output_dir=tmp_path / "out",
        )
    with pytest.raises(MissingInputError, match="make chinese-social"):
        build_cross_language_trends(
            reviews_path=reviews,
            chinese_path=tmp_path / "absent.csv",
            poi_metadata_path=metadata,
            sentiment_summary_path=sentiment_summary,
            output_dir=tmp_path / "out",
        )
    assert not (tmp_path / "out").exists()
