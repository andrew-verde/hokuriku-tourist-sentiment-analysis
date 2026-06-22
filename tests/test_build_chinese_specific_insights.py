import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.build_chinese_specific_insights import build_chinese_specific_insights


def _write_inputs(base: Path) -> Path:
    input_dir = base / "chinese_social_media_analysis"
    input_dir.mkdir()

    tagged_rows = [
            {
                "city": "Fukui",
                "source_platform": "xiaohongshu",
                "sentiment_category": "positive",
                "sentiment_norm": 0.91,
                "theme": "travel",
                "reviewed_positive_terms_matched": "美|推荐",
                "reviewed_negative_terms_matched": "",
                "reviewed_recommendation_terms_matched": "推荐",
                "transport_access": True,
                "scenic_nature": True,
            },
    ]
    for index in range(10):
        tagged_rows.append(
            {
                "city": "Fukui",
                "source_platform": "douyin",
                "sentiment_category": "negative" if index == 0 else "positive",
                "sentiment_norm": 0.21 if index == 0 else 0.72,
                "theme": "unclassified",
                "reviewed_positive_terms_matched": "",
                "reviewed_negative_terms_matched": "贵" if index == 0 else "",
                "reviewed_recommendation_terms_matched": "",
                "transport_access": False,
                "scenic_nature": False,
            }
        )
    tagged = pd.DataFrame(tagged_rows)
    tagged.to_csv(input_dir / "tagged_chinese_social_posts.csv", index=False)

    codebook = pd.DataFrame(
        [
            {
                "code_family": "friction",
                "code": "transport_access",
                "label": "Transport / Access",
                "keyword_count": 3,
            },
            {
                "code_family": "topic",
                "code": "scenic_nature",
                "label": "Scenic Nature",
                "keyword_count": 4,
            },
            {
                "code_family": "sentiment",
                "code": "positive_sentiment",
                "label": "Positive Sentiment",
                "keyword_count": 2,
            },
        ]
    )
    codebook.to_csv(input_dir / "chinese_reviewed_codebook_runtime_summary.csv", index=False)

    pd.DataFrame(
        [
            {
                "city": "Fukui",
                "source_platform": "xiaohongshu",
                "friction_code": "transport_access",
                "friction_label": "Transport / Access",
                "count": 1,
                "denominator_posts": 1,
                "pct_posts": 100.0,
            }
        ]
    ).to_csv(input_dir / "chinese_friction_by_city_platform.csv", index=False)
    pd.DataFrame(
        [
            {
                "city": "Fukui",
                "source_platform": "xiaohongshu",
                "code_family": "topic",
                "code": "scenic_nature",
                "label": "Scenic Nature",
                "count": 1,
                "denominator_posts": 1,
                "pct_posts": 100.0,
            }
        ]
    ).to_csv(input_dir / "chinese_topic_by_city_platform.csv", index=False)
    pd.DataFrame(
        [
            {
                "city": "Fukui",
                "source_platform": "xiaohongshu",
                "code_family": "sentiment",
                "code": "positive_sentiment",
                "label": "Positive Sentiment",
                "count": 1,
                "denominator_posts": 1,
                "pct_posts": 100.0,
            }
        ]
    ).to_csv(input_dir / "chinese_enjoyment_evidence_by_city_platform.csv", index=False)
    return input_dir


def test_build_chinese_specific_insights_writes_safe_figures_and_views(tmp_path):
    input_dir = _write_inputs(tmp_path)
    output_dir = tmp_path / "chinese_specific_insights"

    report = build_chinese_specific_insights(input_dir=input_dir, output_dir=output_dir)

    assert report["metrics"]["rows_represented"] == 11
    assert (output_dir / "figure_keyword_occurrence_by_category.svg").exists()
    assert (output_dir / "figure_top_sentiment_keywords.svg").exists()
    assert (output_dir / "chinese_specific_insights_readiness.md").exists()

    sentiment_keywords = pd.read_csv(output_dir / "sentiment_keyword_counts.csv")
    assert {"sentiment_group", "keyword", "count", "pct_all_rows"}.issubset(sentiment_keywords.columns)
    assert sentiment_keywords[sentiment_keywords["keyword"] == "推荐"]["count"].max() >= 1

    category_occurrence = pd.read_csv(output_dir / "keyword_occurrence_by_category.csv")
    assert {"evidence_family", "code", "label", "count", "denominator_posts"}.issubset(category_occurrence.columns)
    assert set(category_occurrence["evidence_family"]) == {"topic"}

    forbidden = {"text_content", "author", "source_url", "source_record_id"}
    for csv_path in output_dir.glob("*.csv"):
        assert forbidden.isdisjoint(set(pd.read_csv(csv_path).columns))

    manifest = json.loads((output_dir / "chinese_specific_insights_manifest.json").read_text(encoding="utf-8"))
    assert manifest["kind"] == "chinese_specific_insights"
    assert manifest["metrics"]["figure_count"] == 4
    assert manifest["metrics"]["minimum_theme_slice_rows_for_rates"] == 10
    assert "secondary baseline" in " ".join(manifest["caveats"])
    assert "No row-level text" in " ".join(manifest["caveats"])

    theme_summary = pd.read_csv(output_dir / "theme_sentiment_summary.csv")
    travel = theme_summary[
        (theme_summary["theme"] == "travel")
        & (theme_summary["source_platform"] == "all")
    ].iloc[0]
    assert travel["theme_slice_status"] == "suppressed_small_n"
    assert pd.isna(travel["positive_pct"])
    unclassified = theme_summary[
        (theme_summary["theme"] == "unclassified")
        & (theme_summary["source_platform"] == "all")
    ].iloc[0]
    assert unclassified["theme_slice_status"] == "ok"
