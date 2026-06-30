import json
from pathlib import Path

import pytest

from scripts.sync_google_review_data import validate_platform_review_data
from src.platform_review_inputs import (
    PlatformReviewInputError,
    resolve_platform_review_paths,
    resolve_platform_review_scraper_dir,
)


def _write_platform_review_inputs(root: Path) -> Path:
    project = root / "data" / "projects" / "hokuriku"
    checkpoints = project / "checkpoints"
    multilingual = project / "multilingual_review_analysis"
    formatted = project / "formatted"
    checkpoints.mkdir(parents=True)
    multilingual.mkdir(parents=True)
    formatted.mkdir(parents=True)

    (checkpoints / "poi_metadata.json").write_text('{"p1": {"prefecture_normalized": "Fukui"}}\n', encoding="utf-8")
    (multilingual / "reviews_multilingual.csv").write_text(
        "city,language_group,review_text,review_rating\nFukui,english,Great,5\n",
        encoding="utf-8",
    )
    (multilingual / "non_english_non_japanese_reviews.csv").write_text(
        "city,detected_language,review_text,review_rating,poi_id\n"
        "Fukui,zh-cn,很棒,5,p1\n",
        encoding="utf-8",
    )
    (multilingual / "tagged_reviews_multilingual.csv").write_text(
        "city,detected_language,language_group,review_text,poi_id,review_rating,transport_access,wayfinding_signage,english_information_gap,staff_communication,booking_ticketing,waiting_crowding,price_value,cleanliness_comfort,opening_hours_availability,itinerary_fit_time_cost,accessibility_mobility,food_amenities_gap,scenic_value,worthwhile_destination,friendly_service,underpromoted_feature,easy_if_guided,good_for_itinerary_bundle,any_friction\n"
        "Fukui,zh-cn,english,Great,px,5,False,False,False,False,False,False,False,False,False,False,False,False,False,False,False,False,False,False\n",
        encoding="utf-8",
    )
    (formatted / "friction_by_city_language_group.csv").write_text(
        "city,language_group,code,label,count,denominator_reviews,pct_reviews\n"
        "Fukui,english,transport_access,Transport / Access,1,1,100.0\n",
        encoding="utf-8",
    )
    return root


def test_platform_review_resolver_uses_env_override(tmp_path, monkeypatch):
    source = _write_platform_review_inputs(tmp_path / "platform-review-scraper")
    monkeypatch.setenv("PLATFORM_REVIEW_SCRAPER_DIR", str(source))

    scraper_dir = resolve_platform_review_scraper_dir()
    paths = resolve_platform_review_paths()

    assert scraper_dir == source.resolve()
    assert paths.poi_metadata_path == source / "data" / "projects" / "hokuriku" / "checkpoints" / "poi_metadata.json"
    assert paths.reviews_multilingual_path.name == "reviews_multilingual.csv"
    assert paths.non_english_non_japanese_reviews_path.name == "non_english_non_japanese_reviews.csv"
    assert paths.tagged_reviews_multilingual_path.name == "tagged_reviews_multilingual.csv"
    assert paths.review_friction_by_city_language_group_path.name == "friction_by_city_language_group.csv"


def test_validate_platform_review_data_records_hashes_without_copying(tmp_path, monkeypatch):
    source = _write_platform_review_inputs(tmp_path / "platform-review-scraper")
    monkeypatch.setenv("PLATFORM_REVIEW_SCRAPER_DIR", str(source))

    out = tmp_path / "hokuriku" / "output"
    manifest = validate_platform_review_data(output_root=out)

    manifest_on_disk = json.loads((out / "google_review_input_validation.json").read_text(encoding="utf-8"))
    assert manifest_on_disk["schema_version"] == "google_review_input_validation.v1"
    assert manifest_on_disk["provenance"]["schema_version"] == "research_provenance.v1"
    assert manifest_on_disk["provenance"]["metrics"]["files_validated"] == len(manifest["validated_files"])
    assert len(manifest["validated_files"]) == 5
    assert {record["role"] for record in manifest["validated_files"]} == {
        "poi_metadata",
        "reviews_multilingual",
        "non_english_non_japanese_reviews",
        "tagged_reviews_multilingual",
        "review_friction_by_city_language_group",
    }
    assert not (out / "checkpoints").exists()
    assert not (out / "multilingual_review_analysis").exists()
    assert (source / "data" / "projects" / "hokuriku" / "multilingual_review_analysis" / "reviews_multilingual.csv").exists()


def test_validate_platform_review_data_fails_on_missing_inputs(tmp_path, monkeypatch):
    source = tmp_path / "platform-review-scraper"
    project = source / "data" / "projects" / "hokuriku"
    (project / "checkpoints").mkdir(parents=True)
    (project / "multilingual_review_analysis").mkdir(parents=True)
    monkeypatch.setenv("PLATFORM_REVIEW_SCRAPER_DIR", str(source))

    with pytest.raises(PlatformReviewInputError, match="PLATFORM_REVIEW_SCRAPER_DIR"):
        validate_platform_review_data(output_root=tmp_path / "out")
