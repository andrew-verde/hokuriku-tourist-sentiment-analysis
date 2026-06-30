"""Build a tagged Chinese-language Google-review dataset (Hokuriku-wide).

Companion to build_chinese_social_media_dataset.py. The Xiaohongshu (XHS) corpus
is Fukui-only mainland social posts; this module produces the second Chinese
anchor: Chinese-language Google reviews, which span all three Hokuriku
prefectures, are POI-linked and star-rated, and are scored with the SAME SnowNLP
instrument and SAME reviewed codebook as XHS so the two are directly comparable.

Source rows are the zh-detected reviews already isolated in the multilingual
review analysis output. Outputs stay row-level under an ignored path plus a
tagged CSV consumed by the cross-language layer.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from importlib import metadata

from build_chinese_social_media_dataset import (  # noqa: E402
    CHINESE_GOOGLE_REVIEW_CANDIDATES_PATH,
    CODEBOOK_PATH,
    REVIEWED_CODEBOOK_PATH,
    _append_sentiment_fields,
    _reviewed_terms_from_codebook,
    _tag_chinese_dataframe,
    load_chinese_codebook,
)
from src.platform_review_inputs import resolve_platform_review_paths  # noqa: E402
from src.provenance import (  # noqa: E402
    file_record,
    research_manifest,
    write_json,
)

PLATFORM_REVIEW_PATHS = resolve_platform_review_paths()
DEFAULT_INPUT = PLATFORM_REVIEW_PATHS.non_english_non_japanese_reviews_path
DEFAULT_OUTPUT_DIR = ROOT / "output" / "chinese_google_reviews_analysis"
OUTPUT_NAME = "tagged_chinese_google_reviews.csv"
MANIFEST_NAME = "tagged_chinese_google_reviews_manifest.json"

CAVEATS = [
    "Chinese-language Google reviews are the POI-linked, star-rated, region-wide Chinese evidence source; XHS is a separate, demoted directional guidepost (Fukui-only, no POI link, no rating).",
    "Sentiment scored with SnowNLP (same instrument as XHS) for comparability; SnowNLP is noisy on short/traditional review text and produces some false negatives, so sentiment_category is descriptive, not a validated outcome. POI positives should use review_rating, not SnowNLP.",
    "Friction/topic codes use the reviewed Chinese codebook with load-time simplified->traditional expansion (zhconv); colloquial review-register terms remain under-captured pending human review (see docs/codebook_templates/chinese_google_review_friction_candidates.csv).",
    "SnowNLP negative category is unvalidated on short Chinese review text: ~79% of reviews tagged 'negative' are rated 4-5 stars (false negatives), so it is NOT a reportable Chinese sentiment outcome; POI positive signal uses review_rating instead (see metrics.snownlp_validation).",
]


def _dependency_versions() -> dict[str, str]:
    versions = {}
    for package in ["pandas", "snownlp", "zhconv"]:
        try:
            versions[package] = metadata.version(package)
        except metadata.PackageNotFoundError:
            versions[package] = "missing"
    return versions


def load_chinese_google_reviews(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise SystemExit(
            f"Required input not found: {path}\n"
            "Set PLATFORM_REVIEW_SCRAPER_DIR or pass --input."
        )
    df = pd.read_csv(path)
    zh = df[df["detected_language"].astype(str).str.startswith("zh")].copy()
    if zh.empty:
        raise SystemExit(f"No zh-detected reviews found in {path}")
    out = pd.DataFrame()
    out["text_content"] = zh["review_text"].fillna("").astype(str)
    out["title"] = ""  # Google reviews have no title field
    out["city"] = zh["city"]
    out["source_platform"] = "google_review"
    out["content_language"] = "zh"
    out["post_date"] = zh["review_date"]
    out["post_date_precision"] = "exact"  # Google reviews carry true timestamps
    out["review_rating"] = zh["review_rating"]
    out["poi_id"] = zh["poi_id"]
    out["poi_name"] = zh["poi_name"]
    out["poi_category"] = zh["poi_category"]
    out["detected_language"] = zh["detected_language"]  # zh-cn vs zh-tw
    out["source_record_id"] = zh["review_id"]
    out["record_id"] = zh["review_id"]
    return out.reset_index(drop=True)


def build(input_path: Path = DEFAULT_INPUT, output_dir: Path = DEFAULT_OUTPUT_DIR) -> Path:
    codebook = load_chinese_codebook()
    reviewed_terms = _reviewed_terms_from_codebook(codebook)
    df = load_chinese_google_reviews(input_path)
    scored = _append_sentiment_fields(df, reviewed_terms)
    tagged = _tag_chinese_dataframe(scored, codebook)
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / OUTPUT_NAME
    tagged.to_csv(out_path, index=False)

    snownlp_neg = tagged[tagged["sentiment_category"] == "negative"]
    n_neg = int(len(snownlp_neg))
    n_neg_4plus = int((snownlp_neg["review_rating"] >= 4).sum())
    n_neg_2minus = int((snownlp_neg["review_rating"] <= 2).sum())
    snownlp_validation = {
        "snownlp_negative_n": n_neg,
        "snownlp_negative_rated_4_or_5_n": n_neg_4plus,
        "snownlp_negative_rated_4_or_5_share": round(n_neg_4plus / n_neg, 4) if n_neg else None,
        "snownlp_negative_rated_2_or_less_n": n_neg_2minus,
    }

    manifest = research_manifest(
        kind="chinese_google_reviews_tagged",
        command=" ".join(sys.argv),
        inputs=[
            file_record(input_path, "zh_google_reviews_source", required=True),
            file_record(REVIEWED_CODEBOOK_PATH, "reviewed_chinese_codebook", required=True),
            file_record(
                CHINESE_GOOGLE_REVIEW_CANDIDATES_PATH,
                "reviewed_chinese_google_review_candidates",
                required=True,
            ),
            file_record(CODEBOOK_PATH, "legacy_yaml_codebook"),
        ],
        outputs=[file_record(out_path, "tagged_chinese_google_reviews", required=True)],
        metrics={
            "n_reviews": int(len(tagged)),
            "by_city": {str(k): int(v) for k, v in tagged["city"].value_counts().items()},
            "by_detected_language": {str(k): int(v) for k, v in tagged["detected_language"].value_counts().items()},
            "sentiment_category": {str(k): int(v) for k, v in tagged["sentiment_category"].value_counts().items()},
            "snownlp_centered_score_mean": round(float(tagged["snownlp_centered_score"].mean()), 4),
            "mean_review_rating": round(float(tagged["review_rating"].mean()), 3),
            "any_friction_rate": round(float(tagged["any_friction"].mean()), 4),
            "unique_pois": int(tagged["poi_id"].nunique()),
            "snownlp_validation": snownlp_validation,
        },
        caveats=CAVEATS,
        extra={"dependency_versions": _dependency_versions()},
    )
    write_json(output_dir / MANIFEST_NAME, manifest)

    print(f"Wrote {len(tagged)} tagged Chinese Google reviews -> {out_path}")
    print("by city:\n", tagged["city"].value_counts().to_string())
    print("sentiment_category:\n", tagged["sentiment_category"].value_counts().to_string())
    print(f"snownlp_centered_score mean: {tagged['snownlp_centered_score'].mean():.4f}")
    print(f"mean star rating: {tagged['review_rating'].mean():.3f}")
    print(f"manifest -> {output_dir / MANIFEST_NAME}")
    return out_path


if __name__ == "__main__":
    build()
