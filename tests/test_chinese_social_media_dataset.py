import datetime as dt
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.build_chinese_social_media_dataset import (
    build_chinese_social_outputs,
    discover_input_files,
    load_theme_annotations,
    normalize_social_csv,
    parse_author_and_date,
)

REFERENCE_DATE = dt.date(2026, 6, 12)


def test_chinese_social_builder_handles_schema_only_csv(tmp_path):
    xhs = tmp_path / "fukui_xhs_reviews.csv"
    xhs.write_text("note_id,title,note_url,author,author_url\n", encoding="utf-8")

    report = build_chinese_social_outputs(
        input_dir=tmp_path,
        output_dir=tmp_path / "out",
        input_files=[xhs],
        review_friction_path=tmp_path / "missing_review_friction.csv",
    )

    assert report["input_files_discovered"] == 1
    assert report["rows_retained"] == 0
    assert (tmp_path / "out" / "chinese_social_posts.csv").exists()
    assert (tmp_path / "out" / "chinese_social_readiness.md").exists()


def test_normalize_social_csv_maps_xhs_schema_to_review_like_rows(tmp_path):
    xhs = tmp_path / "fukui_xhs_reviews.csv"
    xhs.write_text(
        "note_id,title,note_url,author,author_url\n"
        "n1,福井交通不便 但是东寻坊很美,https://xhs.example/n1,旅行者,https://xhs.example/u1\n",
        encoding="utf-8",
    )

    df = normalize_social_csv(xhs)

    assert len(df) == 1
    assert df.loc[0, "city"] == "Fukui"
    assert df.loc[0, "source_platform"] == "xiaohongshu"
    assert df.loc[0, "text_content"] == "福井交通不便 但是东寻坊很美"
    assert df.loc[0, "content_language"] == "zh"
    assert 0 <= df.loc[0, "sentiment_norm"] <= 1


def test_chinese_social_builder_tags_and_compares_populated_rows(tmp_path):
    xhs = tmp_path / "fukui_xhs_reviews.csv"
    xhs.write_text(
        "note_id,title,note_url,author,author_url\n"
        "n1,福井交通不便 公交班次少,https://xhs.example/n1,a,\n"
        "n2,东寻坊很美 推荐,https://xhs.example/n2,b,\n",
        encoding="utf-8",
    )
    douyin = tmp_path / "kanazawa_douyin_reviews.csv"
    douyin.write_text(
        "video_id,title,video_url,author\n"
        "v1,金泽交通便利 但门票贵,https://dy.example/v1,c\n",
        encoding="utf-8",
    )
    review_friction = tmp_path / "friction_by_city_language_group.csv"
    review_friction.write_text(
        "city,language_group,code,label,count,denominator_reviews,pct_reviews\n"
        "Fukui,english,transport_access,Transport / Access,1,10,10.0\n",
        encoding="utf-8",
    )

    report = build_chinese_social_outputs(
        input_dir=tmp_path,
        output_dir=tmp_path / "out",
        input_files=[xhs, douyin],
        review_friction_path=review_friction,
    )

    assert report["rows_retained"] == 3

    tagged = pd.read_csv(tmp_path / "out" / "tagged_chinese_social_posts.csv")
    fukui = tagged[tagged["city"] == "Fukui"].iloc[0]
    assert bool(fukui["transport_access"]) is True
    assert bool(fukui["any_friction"]) is True

    friction = pd.read_csv(tmp_path / "out" / "chinese_friction_by_city_platform.csv")
    row = friction[
        (friction["city"] == "Fukui")
        & (friction["source_platform"] == "xiaohongshu")
        & (friction["friction_code"] == "transport_access")
    ].iloc[0]
    assert row["count"] == 1
    assert row["denominator_posts"] == 2

    comparison = pd.read_csv(tmp_path / "out" / "chinese_vs_review_language_friction_comparison.csv")
    assert comparison.loc[0, "comparison_group"] == "google_english"
    assert set(comparison["chinese_subset"]) == {"all_posts", "excluding_fan"}


def test_parse_author_and_date_handles_xhs_display_forms():
    assert parse_author_and_date("Juunae 2025-08-14", REFERENCE_DATE) == ("Juunae", "2025-08-14", "exact")
    assert parse_author_and_date("momo 05-25", REFERENCE_DATE) == ("momo", "2026-05-25", "year_inferred")
    # Month-day later than the scrape date belongs to the previous year.
    assert parse_author_and_date("li 09-01", REFERENCE_DATE) == ("li", "2025-09-01", "year_inferred")
    assert parse_author_and_date("姐妹你误会了 昨天 22:03", REFERENCE_DATE) == ("姐妹你误会了", "2026-06-11", "relative_inferred")
    assert parse_author_and_date("某人 3天前", REFERENCE_DATE) == ("某人", "2026-06-09", "relative_inferred")
    assert parse_author_and_date("无日期作者", REFERENCE_DATE) == ("无日期作者", "", "none")


def test_discover_input_files_searches_raw_social_layout(tmp_path):
    social_dir = tmp_path / "data" / "raw" / "social"
    social_dir.mkdir(parents=True)
    (social_dir / "fukui_xhs_reviews.csv").write_text("note_id,title,note_url,author,author_url\n", encoding="utf-8")
    (social_dir / "README.md").write_text("not a csv", encoding="utf-8")
    (tmp_path / "unrelated.csv").write_text("a,b\n", encoding="utf-8")

    files = discover_input_files(tmp_path)

    assert [path.name for path in files] == ["fukui_xhs_reviews.csv"]


def test_theme_annotations_join_from_processed_csv(tmp_path):
    social_dir = tmp_path / "data" / "raw" / "social"
    social_dir.mkdir(parents=True)
    raw = social_dir / "fukui_xhs_reviews.csv"
    raw.write_text(
        "note_id,title,note_url,author,author_url\n"
        "n1,福井交通不便,https://xhs.example/n1,a 2025-08-14,\n"
        "n2,走Riku走过的道路,https://xhs.example/n2,b 2025-09-05,\n",
        encoding="utf-8",
    )
    processed_dir = tmp_path / "data" / "processed"
    processed_dir.mkdir(parents=True)
    (processed_dir / "fukui_xhs_analysis.csv").write_text(
        "note_id,title,theme,fan_score,travel_score\n"
        "n1,福井交通不便,travel,0,1\n"
        "n2,走Riku走过的道路,fan,1,0\n",
        encoding="utf-8",
    )

    themes = load_theme_annotations(tmp_path)
    assert len(themes) == 2

    report = build_chinese_social_outputs(
        input_dir=tmp_path,
        output_dir=tmp_path / "out",
        review_friction_path=tmp_path / "missing.csv",
    )
    assert report["rows_retained"] == 2
    assert report["theme_counts"] == {"travel": 1, "fan": 1}

    tagged = pd.read_csv(tmp_path / "out" / "tagged_chinese_social_posts.csv")
    fan_row = tagged[tagged["source_record_id"] == "n2"].iloc[0]
    assert fan_row["theme"] == "fan"
    assert fan_row["post_date_precision"] == "exact"
    assert fan_row["author"] == "b"

    theme_summary = pd.read_csv(tmp_path / "out" / "chinese_theme_by_city_platform.csv")
    assert set(theme_summary["theme"]) == {"travel", "fan"}


def test_unmatched_rows_fall_back_to_unclassified_theme(tmp_path):
    social_dir = tmp_path / "data" / "raw" / "social"
    social_dir.mkdir(parents=True)
    (social_dir / "fukui_xhs_reviews.csv").write_text(
        "note_id,title,note_url,author,author_url\n"
        "n9,东寻坊很美,https://xhs.example/n9,c,\n",
        encoding="utf-8",
    )

    report = build_chinese_social_outputs(
        input_dir=tmp_path,
        output_dir=tmp_path / "out",
        review_friction_path=tmp_path / "missing.csv",
    )
    assert report["theme_counts"] == {"unclassified": 1}
