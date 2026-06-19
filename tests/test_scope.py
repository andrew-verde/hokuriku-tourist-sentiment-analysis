import json
from pathlib import Path

import pandas as pd
import pytest

from src.scope import (
    MissingScopeColumnsError,
    POI_SCOPE_METHOD,
    SOURCE_LABEL_SCOPE_METHOD,
    load_poi_scope_metadata,
    scope_reviews_by_poi_prefecture,
    scope_rows_by_source_city_label,
)


def _write_metadata(path: Path) -> None:
    path.write_text(
        json.dumps({
            "p1": {"prefecture_normalized": "Fukui", "municipality": "Fukui"},
            "p2": {"prefecture_normalized": "Toyama", "municipality": "Toyama"},
        }),
        encoding="utf-8",
    )


def test_poi_prefecture_scope_uses_metadata_not_city_text(tmp_path):
    metadata_path = tmp_path / "poi_metadata.json"
    _write_metadata(metadata_path)
    metadata = load_poi_scope_metadata(metadata_path)
    reviews = pd.DataFrame([
        {"city": "Toyama", "poi_id": "p1", "language_group": "english"},
        {"city": "Fukui", "poi_id": "p2", "language_group": "english"},
    ])

    scoped = scope_reviews_by_poi_prefecture(reviews, metadata, "Fukui")

    assert len(scoped) == 1
    assert scoped.iloc[0]["poi_id"] == "p1"
    assert scoped.iloc[0]["scope_method"] == POI_SCOPE_METHOD


def test_source_city_label_scope_is_explicit():
    rows = pd.DataFrame([
        {"city": "Fukui", "source_platform": "xiaohongshu"},
        {"city": "Toyama", "source_platform": "xiaohongshu"},
    ])

    scoped = scope_rows_by_source_city_label(rows, "Fukui")

    assert len(scoped) == 1
    assert scoped.iloc[0]["scope_method"] == SOURCE_LABEL_SCOPE_METHOD


def test_poi_scope_fails_loud_when_metadata_missing_row(tmp_path):
    metadata_path = tmp_path / "poi_metadata.json"
    _write_metadata(metadata_path)
    metadata = load_poi_scope_metadata(metadata_path)
    reviews = pd.DataFrame([{"city": "Fukui", "poi_id": "missing"}])

    with pytest.raises(MissingScopeColumnsError, match="metadata missing"):
        scope_reviews_by_poi_prefecture(reviews, metadata, "Fukui")
