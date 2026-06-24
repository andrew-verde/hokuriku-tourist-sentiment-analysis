"""
Fukui-first scope helpers shared by analysis builders.

This module provides functions to filter and annotate review and survey data
by geographic scope (prefecture, city). It ensures that downstream analysis
stays within the region of interest and can attach metadata about how each
row was scoped.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


POI_SCOPE_METHOD = "poi_metadata_prefecture"
SOURCE_LABEL_SCOPE_METHOD = "source_city_label"


class ScopeError(RuntimeError):
    pass


class MissingScopeInputError(ScopeError):
    pass


class MissingScopeColumnsError(ScopeError):
    pass


def load_poi_scope_metadata(path: Path) -> pd.DataFrame:
    """Load POI metadata used for prefecture-level Google review scope."""
    # Read the POI (Point of Interest) metadata from a JSON file keyed by poi_id.
    # This file maps each point of interest (e.g., a landmark, restaurant) to its
    # prefecture and other geographic attributes for later filtering.
    if not path.exists():
        raise MissingScopeInputError(f"Required POI metadata not found: {path}")
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise MissingScopeColumnsError(f"POI metadata must be a JSON object keyed by poi_id: {path}")

    # Convert the JSON object into a list of rows suitable for a DataFrame.
    rows = []
    for poi_id, attrs in raw.items():
        if not isinstance(attrs, dict):
            continue
        rows.append({
            "poi_id": str(poi_id),
            "metadata_poi_name": attrs.get("name"),
            "prefecture": attrs.get("prefecture"),
            "prefecture_normalized": attrs.get("prefecture_normalized") or attrs.get("prefecture"),
            "municipality": attrs.get("municipality"),
            "municipality_short": attrs.get("municipality_short"),
            "prefecture_metadata_source": attrs.get("metadata_source"),
            "prefecture_metadata_language": attrs.get("metadata_language"),
        })

    metadata = pd.DataFrame(rows)
    # Validate that all required columns are present and contain meaningful data.
    required = {"poi_id", "prefecture_normalized"}
    missing = sorted(required - set(metadata.columns))
    if missing:
        raise MissingScopeColumnsError(
            f"Required POI metadata columns missing from {path}: {', '.join(missing)}"
        )
    if metadata.empty or metadata["prefecture_normalized"].isna().all():
        raise MissingScopeColumnsError(f"POI metadata missing prefecture_normalized values: {path}")
    if metadata["poi_id"].duplicated().any():
        duplicates = sorted(metadata.loc[metadata["poi_id"].duplicated(), "poi_id"].unique())
        raise MissingScopeColumnsError(f"Duplicate poi_id values in POI metadata: {duplicates[:5]}")
    return metadata


def scope_reviews_by_poi_prefecture(
    reviews: pd.DataFrame,
    metadata: pd.DataFrame,
    prefecture: str,
) -> pd.DataFrame:
    """Attach POI metadata and keep review rows inside one prefecture."""
    # Filter Google review data to a single prefecture by joining with POI metadata
    # (which includes the prefecture for each point of interest) and selecting only
    # rows within the target prefecture.
    if "poi_id" not in reviews.columns:
        raise MissingScopeColumnsError("Prefecture filtering requires reviews column: poi_id")
    scoped = reviews.merge(metadata, on="poi_id", how="left", validate="many_to_one")
    # Verify that every review row has a matching POI in the metadata; if not, the
    # scope filtering would be incomplete.
    missing_metadata = scoped["prefecture_normalized"].isna()
    if missing_metadata.any():
        missing_ids = sorted(scoped.loc[missing_metadata, "poi_id"].astype(str).unique())[:5]
        raise MissingScopeColumnsError(
            "POI metadata missing for requested review rows; "
            f"prefecture filtering would be incomplete. Example poi_id values: {missing_ids}"
        )
    # Keep only rows in the requested prefecture and tag them with scope metadata.
    scoped = scoped[scoped["prefecture_normalized"].astype(str) == prefecture].copy()
    scoped["scope_prefecture"] = prefecture
    scoped["scope_method"] = POI_SCOPE_METHOD
    return scoped


def scope_rows_by_source_city_label(
    rows: pd.DataFrame,
    prefecture: str,
    city_column: str = "city",
) -> pd.DataFrame:
    """Keep non-POI rows whose source city label matches the target prefecture."""
    # Filter survey or text data (which lack POI IDs) to a single prefecture by
    # matching the source city label column against the target prefecture name.
    if rows.empty:
        scoped = rows.copy()
        scoped["scope_prefecture"] = pd.Series(dtype=object)
        scoped["scope_method"] = pd.Series(dtype=object)
        return scoped
    if city_column not in rows.columns:
        raise MissingScopeColumnsError(f"Prefecture filtering requires source label column: {city_column}")
    # Keep only rows where the city label matches the target prefecture.
    scoped = rows[rows[city_column].astype(str) == prefecture].copy()
    scoped["scope_prefecture"] = prefecture
    scoped["scope_method"] = SOURCE_LABEL_SCOPE_METHOD
    return scoped
