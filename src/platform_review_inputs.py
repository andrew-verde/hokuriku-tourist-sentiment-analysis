"""Resolve shared inputs from sibling platform-review-scraper checkout."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parent.parent
PLATFORM_REVIEW_SCRAPER_ENV = "PLATFORM_REVIEW_SCRAPER_DIR"
DEFAULT_PLATFORM_REVIEW_SCRAPER_DIR = REPO_ROOT.parent / "platform-review-scraper"
DEFAULT_PROJECT = "hokuriku"


class PlatformReviewInputError(RuntimeError):
    pass


@dataclass(frozen=True)
class PlatformReviewPaths:
    scraper_dir: Path
    project_dir: Path
    checkpoints_dir: Path
    multilingual_review_analysis_dir: Path
    formatted_dir: Path
    poi_metadata_path: Path
    reviews_multilingual_path: Path
    non_english_non_japanese_reviews_path: Path
    tagged_reviews_multilingual_path: Path
    review_friction_by_city_language_group_path: Path


def resolve_platform_review_scraper_dir(override: Path | None = None) -> Path:
    if override is not None:
        return Path(override).expanduser().resolve()
    env_override = os.environ.get(PLATFORM_REVIEW_SCRAPER_ENV)
    if env_override:
        return Path(env_override).expanduser().resolve()
    return DEFAULT_PLATFORM_REVIEW_SCRAPER_DIR.resolve()


def resolve_platform_review_paths(
    project: str = DEFAULT_PROJECT,
    scraper_dir: Path | None = None,
) -> PlatformReviewPaths:
    scraper_dir = resolve_platform_review_scraper_dir(scraper_dir)
    project_dir = scraper_dir / "data" / "projects" / project
    checkpoints_dir = project_dir / "checkpoints"
    multilingual_review_analysis_dir = project_dir / "multilingual_review_analysis"
    formatted_dir = project_dir / "formatted"
    return PlatformReviewPaths(
        scraper_dir=scraper_dir,
        project_dir=project_dir,
        checkpoints_dir=checkpoints_dir,
        multilingual_review_analysis_dir=multilingual_review_analysis_dir,
        formatted_dir=formatted_dir,
        poi_metadata_path=checkpoints_dir / "poi_metadata.json",
        reviews_multilingual_path=multilingual_review_analysis_dir / "reviews_multilingual.csv",
        non_english_non_japanese_reviews_path=(
            multilingual_review_analysis_dir / "non_english_non_japanese_reviews.csv"
        ),
        tagged_reviews_multilingual_path=multilingual_review_analysis_dir / "tagged_reviews_multilingual.csv",
        review_friction_by_city_language_group_path=(
            formatted_dir / "friction_by_city_language_group.csv"
        ),
    )


def platform_review_required_inputs(paths: PlatformReviewPaths | None = None) -> dict[str, Path]:
    paths = paths or resolve_platform_review_paths()
    return {
        "poi_metadata": paths.poi_metadata_path,
        "reviews_multilingual": paths.reviews_multilingual_path,
        "non_english_non_japanese_reviews": paths.non_english_non_japanese_reviews_path,
        "tagged_reviews_multilingual": paths.tagged_reviews_multilingual_path,
        "review_friction_by_city_language_group": paths.review_friction_by_city_language_group_path,
    }


def missing_platform_review_inputs(
    paths: PlatformReviewPaths | None = None,
    required_roles: Iterable[str] | None = None,
) -> list[tuple[str, Path]]:
    paths = paths or resolve_platform_review_paths()
    required = platform_review_required_inputs(paths)
    roles = list(required_roles) if required_roles is not None else list(required)
    return [
        (role, required[role])
        for role in roles
        if role in required and not required[role].exists()
    ]


def require_platform_review_inputs(
    paths: PlatformReviewPaths | None = None,
    required_roles: Iterable[str] | None = None,
) -> PlatformReviewPaths:
    missing = missing_platform_review_inputs(paths, required_roles)
    if missing:
        details = ", ".join(f"{role}: {path}" for role, path in missing)
        raise PlatformReviewInputError(
            f"Required platform-review inputs missing: {details}\n"
            f"Set {PLATFORM_REVIEW_SCRAPER_ENV} or create sibling checkout at "
            f"{DEFAULT_PLATFORM_REVIEW_SCRAPER_DIR}."
        )
    return paths or resolve_platform_review_paths()
