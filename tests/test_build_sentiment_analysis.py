import hashlib
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.build_sentiment_analysis import (
    MissingColumnsError,
    MissingInputError,
    PipelinePaths,
    build_sentiment_analysis,
    sentiment_category,
    sha256_file,
)


def _write_reviews(path: Path) -> None:
    # This CSV is deliberately tiny and fake: enough columns to exercise the
    # pipeline without using any real review text or real reviewer IDs.
    path.write_text(
        "city,poi_id,poi_category,review_id,review_date,review_rating,review_text,language_group,"
        "review_author,place_id,source_review_id,source_platform\n"
        "Fukui,p1,museum,r1,2025-08-01,5,Great view,english,Alice,place1,src1,google_reviews\n"
        "Fukui,p2,station,r2,2025-08-02,2,Bad access,english,Bob,place2,src2,google_reviews\n"
        "Fukui,p3,temple,r3,2025-08-03,4,良いです,japanese,Chika,place3,src3,google_reviews\n"
        "Fukui,p4,park,r4,2025-08-04,1,悪いです,japanese,Dai,place4,src4,google_reviews\n"
        "Toyama,p5,park,r5,2025-08-05,5,Great,english,Eri,place5,src5,google_reviews\n",
        encoding="utf-8",
    )


def _write_poi_metadata(path: Path) -> None:
    # POI metadata is separate from review rows in the real pipeline, so the
    # tests mirror that shape instead of putting prefecture directly in reviews.
    path.write_text(
        json.dumps(
            {
                "p1": {
                    "name": "Fukui Castle",
                    "prefecture_normalized": "Fukui",
                    "municipality": "Fukui",
                },
                "p2": {
                    "name": "Fukui Station",
                    "prefecture_normalized": "Fukui",
                    "municipality": "Fukui",
                },
                "p3": {
                    "name": "Eiheiji Temple",
                    "prefecture_normalized": "Fukui",
                    "municipality": "Eiheiji",
                },
                "p4": {
                    "name": "Echizen Ono Castle",
                    "prefecture_normalized": "Fukui",
                    "municipality": "Ono",
                },
                "p5": {
                    "name": "Toyama Castle",
                    "prefecture_normalized": "Toyama",
                    "municipality": "Toyama",
                },
            }
        ),
        encoding="utf-8",
    )


def _write_reviewed_codebook(path: Path) -> None:
    path.write_text(
        """
schema_version: reviewed_codebook_runtime.v1
languages:
  English:
    codes:
      positive_sentiment:
        code_family: sentiment
        keywords: [Great]
      negative_sentiment:
        code_family: sentiment
        keywords: [Bad]
      recommendation_intent:
        code_family: sentiment
        keywords: [view]
      transport_access:
        code_family: friction
        keywords: [access]
  Japanese:
    codes:
      positive_sentiment:
        code_family: sentiment
        keywords: [良い]
      negative_sentiment:
        code_family: sentiment
        keywords: [悪い]
      recommendation_intent:
        code_family: sentiment
        keywords: [です]
      transport_access:
        code_family: friction
        keywords: [不便]
""".strip(),
        encoding="utf-8",
    )


def _english_scorer(text: str) -> dict[str, float]:
    # Test scorer: deterministic stand-in for VADER so tests do not depend on
    # external model behavior.
    compound = 0.80 if "Great" in text else -0.80
    return {
        "vader_neg": 0.0 if compound > 0 else 0.8,
        "vader_neu": 0.2,
        "vader_pos": 0.8 if compound > 0 else 0.0,
        "sentiment_score": compound,
    }


def _japanese_scorer(text: str) -> dict[str, object]:
    # Test scorer: deterministic stand-in for oseti with the same output fields
    # the production code expects.
    score = 0.20 if "良い" in text else -0.20
    return {
        "oseti_sentence_scores": f"[{score}]",
        "oseti_doc_score": score,
        "oseti_positive_count": 1 if score > 0 else 0,
        "oseti_negative_count": 1 if score < 0 else 0,
        "sentiment_score": score,
    }


def test_category_threshold_boundaries():
    # Boundaries matter because exactly +/-0.05 should fall into positive/negative,
    # while values just inside the band should stay neutral.
    assert sentiment_category(0.05) == "positive"
    assert sentiment_category(0.049999) == "neutral"
    assert sentiment_category(-0.049999) == "neutral"
    assert sentiment_category(-0.05) == "negative"
    assert sentiment_category(0.10, band=0.10) == "positive"
    assert sentiment_category(-0.10, band=0.10) == "negative"


def test_sha256_file_stable(tmp_path):
    # Hashing the same bytes twice should always produce the same digest.
    path = tmp_path / "sample.txt"
    path.write_text("same bytes\n", encoding="utf-8")
    assert sha256_file(path) == hashlib.sha256(b"same bytes\n").hexdigest()
    assert sha256_file(path) == sha256_file(path)


def test_build_outputs_aggregate_excludes_forbidden_row_level_fields(tmp_path):
    # Main privacy regression test: row-level outputs can keep IDs/text, but
    # tracked aggregate outputs must not expose those fields.
    reviews = tmp_path / "reviews_multilingual.csv"
    codebook = tmp_path / "reviewed_jp_en_codebook.yaml"
    _write_reviews(reviews)
    _write_reviewed_codebook(codebook)

    report = build_sentiment_analysis(
        paths=PipelinePaths(
            reviews_path=reviews,
            reviewed_codebook_path=codebook,
            row_output_dir=tmp_path / "row",
            aggregate_output_dir=tmp_path / "agg",
        ),
        groups=["japanese", "english"],
        city="Fukui",
        command="pytest command",
        english_scorer=_english_scorer,
        japanese_scorer=_japanese_scorer,
    )

    row_level = pd.read_csv(tmp_path / "row" / "google_reviews_fukui_japanese-english.csv")
    # Row-level output is ignored by Git, so it can keep review IDs and scoring
    # details needed for audit/debugging.
    assert "review_id" in row_level.columns
    assert "oseti_sentence_scores" in row_level.columns
    assert "reviewed_positive_terms_matched" in row_level.columns
    assert "reviewed_friction_terms_matched" in row_level.columns
    assert "any_positive_evidence" in row_level.columns
    assert row_level.loc[row_level["review_id"] == "r1", "reviewed_positive_terms_matched"].iloc[0] == "Great"
    assert bool(row_level.loc[row_level["review_id"] == "r2", "any_friction"].iloc[0])

    summary = pd.read_csv(tmp_path / "agg" / "source_group_sentiment_summary.csv")
    tests = pd.read_csv(tmp_path / "agg" / "source_group_sentiment_tests.csv")
    # These names are disallowed in aggregate files because they can identify
    # people, places, source rows, or original text.
    forbidden = {
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
    assert not (forbidden & set(summary.columns))
    assert not (forbidden & set(tests.columns))
    assert summary["n_reviews"].sum() == 4
    assert "any_positive_evidence_count" in summary.columns
    assert "library_vs_reviewed_positive_disagreement_pct" in summary.columns
    assert "mann_whitney_u_sentiment_score" in set(tests["test_name"])
    assert "raw_score_parametric_tests_not_run" in set(tests["test_name"])
    assert "welch_t_review_rating" in set(tests["test_name"])
    assert "welch_anova_review_rating" in set(tests["test_name"])
    assert (
        {"chi_square_sentiment_category", "fisher_exact_sentiment_category"}
        & set(tests["test_name"])
    )
    assert "poi_level_mann_whitney_mean_sentiment_score" in set(tests["test_name"])
    assert "cluster_bootstrap_poi_mean_difference_sentiment_score" in set(tests["test_name"])
    assert "poi_level_welch_t_mean_review_rating" in set(tests["test_name"])
    raw_parametric = tests[tests["test_name"] == "raw_score_parametric_tests_not_run"].iloc[0]
    assert raw_parametric["status"] == "skipped"
    assert "different tool-specific scales" in raw_parametric["details_json"]
    rating_t = tests[tests["test_name"] == "welch_t_review_rating"].iloc[0]
    assert rating_t["status"] == "ok"
    assert "common_google_1_to_5_star_rating" in rating_t["details_json"]

    readiness = (tmp_path / "agg" / "sentiment_readiness.md").read_text(encoding="utf-8")
    assert report["input"]["sha256"] in readiness
    assert report["outputs"]["row_level_sha256"] in readiness
    assert report["input"]["reviewed_codebook_sha256"] in readiness
    assert "codebook_evidence_status: active" in readiness
    assert "Raw sentiment-score t-tests/ANOVA are skipped" in readiness

    manifest = json.loads((tmp_path / "agg" / "sentiment_manifest.json").read_text(encoding="utf-8"))
    assert manifest["schema_version"] == "sentiment_manifest.v2"
    assert manifest["codebook_evidence_status"] == "active"
    assert manifest["provenance"]["schema_version"] == "research_provenance.v1"
    assert {record["role"] for record in manifest["provenance"]["inputs"]} >= {
        "reviews_multilingual",
        "reviewed_jp_en_codebook_config",
    }
    output_roles = {record["role"] for record in manifest["provenance"]["outputs"]}
    assert "tracked_aggregate_summary" in output_roles
    assert "tracked_statistical_tests" in output_roles
    assert all(
        "sha256" in record
        for record in manifest["provenance"]["outputs"]
        if record["role"].startswith("tracked_")
    )


def test_missing_input_and_columns_fail_loud(tmp_path):
    # Missing files or required columns should stop the pipeline, not generate
    # demo/fallback data.
    with pytest.raises(MissingInputError, match="PLATFORM_REVIEW_SCRAPER_DIR"):
        build_sentiment_analysis(
            paths=PipelinePaths(
                reviews_path=tmp_path / "absent.csv",
                row_output_dir=tmp_path / "row",
                aggregate_output_dir=tmp_path / "agg",
            ),
            english_scorer=_english_scorer,
            japanese_scorer=_japanese_scorer,
        )

    bad = tmp_path / "bad.csv"
    bad.write_text("city,language_group,review_text\nFukui,english,Great\n", encoding="utf-8")
    with pytest.raises(MissingColumnsError, match="review_rating"):
        build_sentiment_analysis(
            paths=PipelinePaths(
                reviews_path=bad,
                row_output_dir=tmp_path / "row",
                aggregate_output_dir=tmp_path / "agg",
            ),
            english_scorer=_english_scorer,
            japanese_scorer=_japanese_scorer,
        )


def test_scoring_wrappers_can_be_monkeypatched_without_external_models(tmp_path):
    # Injected scorer functions let this test validate pipeline wiring without
    # importing VADER/oseti.
    reviews = tmp_path / "reviews_multilingual.csv"
    codebook = tmp_path / "reviewed_jp_en_codebook.yaml"
    _write_reviews(reviews)
    _write_reviewed_codebook(codebook)
    build_sentiment_analysis(
        paths=PipelinePaths(
            reviews_path=reviews,
            reviewed_codebook_path=codebook,
            row_output_dir=tmp_path / "row",
            aggregate_output_dir=tmp_path / "agg",
        ),
        groups=["japanese", "english"],
        city="Fukui",
        english_scorer=_english_scorer,
        japanese_scorer=_japanese_scorer,
    )
    row_level = pd.read_csv(tmp_path / "row" / "google_reviews_fukui_japanese-english.csv")
    english = row_level[row_level["language_group"] == "english"]
    japanese = row_level[row_level["language_group"] == "japanese"]
    assert set(english["sentiment_category"]) == {"positive", "negative"}
    assert set(japanese["sentiment_category"]) == {"positive", "negative"}


def test_prefecture_filter_uses_poi_metadata_not_city_name(tmp_path):
    # The review CSV city field is not enough for scope control; this test
    # proves prefecture filtering comes from POI metadata.
    reviews = tmp_path / "reviews_multilingual.csv"
    metadata = tmp_path / "poi_metadata.json"
    codebook = tmp_path / "reviewed_jp_en_codebook.yaml"
    _write_reviews(reviews)
    _write_poi_metadata(metadata)
    _write_reviewed_codebook(codebook)

    report = build_sentiment_analysis(
        paths=PipelinePaths(
            reviews_path=reviews,
            poi_metadata_path=metadata,
            reviewed_codebook_path=codebook,
            row_output_dir=tmp_path / "row",
            aggregate_output_dir=tmp_path / "agg",
        ),
        groups=["japanese", "english"],
        prefecture="Fukui",
        english_scorer=_english_scorer,
        japanese_scorer=_japanese_scorer,
    )

    row_level = pd.read_csv(tmp_path / "row" / "google_reviews_fukui_japanese-english.csv")
    assert len(row_level) == 4
    assert set(row_level["municipality"]) == {"Fukui", "Eiheiji", "Ono"}
    assert "Toyama" not in set(row_level["prefecture_normalized"])
    assert report["input"]["poi_metadata_sha256"] == sha256_file(metadata)
    assert report["provenance"]["metrics"]["scope_method"] == ["poi_metadata_prefecture"]
