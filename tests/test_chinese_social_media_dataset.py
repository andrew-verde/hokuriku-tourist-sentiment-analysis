import datetime as dt
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.build_chinese_social_media_dataset import (
    InputSchemaError,
    build_chinese_social_outputs,
    discover_input_files,
    load_chinese_codebook,
    load_theme_annotations,
    normalize_social_csv,
    parse_author_and_date,
    parse_douyin_relative_time,
)

REFERENCE_DATE = dt.date(2026, 6, 12)


def test_chinese_social_builder_handles_schema_only_csv(tmp_path):
    # A header-only input is valid during early data collection: it should build
    # empty output files instead of crashing or inventing sample rows.
    xhs = tmp_path / "fukui_xhs_reviews.csv"
    xhs.write_text("note_id,title,note_url,author,author_url\n", encoding="utf-8")

    report = build_chinese_social_outputs(
        input_dir=tmp_path,
        output_dir=tmp_path / "out",
        input_files=[xhs],
        review_friction_path=tmp_path / "missing_review_friction.csv",
    )

    manifest = json.loads((tmp_path / "out" / "chinese_social_readiness.json").read_text(encoding="utf-8"))
    assert manifest["schema_version"] == "chinese_social_manifest.v2"
    assert manifest["provenance"]["schema_version"] == "research_provenance.v1"
    assert {record["role"] for record in manifest["provenance"]["inputs"]} >= {
        "social_source_input",
        "reviewed_chinese_codebook_template",
        "legacy_yaml_codebook",
    }
    assert report["input_files_discovered"] == 1
    assert report["analysis_variant"] == "xiaohongshu_and_douyin"
    assert report["rows_retained"] == 0
    assert (tmp_path / "out" / "chinese_social_posts.csv").exists()
    assert (tmp_path / "out" / "chinese_social_readiness.md").exists()


def test_chinese_social_builder_fails_when_no_input_files_discovered(tmp_path):
    try:
        build_chinese_social_outputs(
            input_dir=tmp_path,
            output_dir=tmp_path / "out",
            review_friction_path=tmp_path / "missing_review_friction.csv",
        )
    except InputSchemaError as error:
        message = str(error)
        assert "input files not found" in message
        assert "no demo or fallback mode" in message
    else:
        raise AssertionError("Expected InputSchemaError")


def test_combined_discovery_fails_when_douyin_missing(tmp_path):
    social_dir = tmp_path / "data" / "raw" / "social"
    social_dir.mkdir(parents=True)
    (social_dir / "fukui_xhs_reviews.csv").write_text(
        "note_id,title,note_url,author,author_url\n"
        "n1,福井交通不便,https://xhs.example/n1,a,\n",
        encoding="utf-8",
    )

    try:
        build_chinese_social_outputs(
            input_dir=tmp_path,
            output_dir=tmp_path / "out",
            review_friction_path=tmp_path / "missing_review_friction.csv",
        )
    except InputSchemaError as error:
        assert "Combined Chinese social inputs incomplete" in str(error)
        assert "chinese-social-xhs-only" in str(error)
    else:
        raise AssertionError("Expected InputSchemaError")


def test_normalize_social_csv_maps_xhs_schema_to_review_like_rows(tmp_path):
    # Xiaohongshu rows start with social-media column names; the normalizer
    # converts them into the shared row schema used by later summaries.
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
    # This exercises the full mini-pipeline: ingest two platforms, tag friction,
    # write aggregate files, and compare against a tiny Google-review summary.
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
    # `tagged` is row-level and lives under ignored output in real runs; tests
    # read it to prove the boolean evidence columns were created.
    fukui = tagged[tagged["city"] == "Fukui"].iloc[0]
    assert bool(fukui["transport_access"]) is True
    assert bool(fukui["any_friction"]) is True
    assert "topic_codes" in tagged.columns
    assert "enjoyment_evidence_codes" in tagged.columns

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

    topic = pd.read_csv(tmp_path / "out" / "chinese_topic_by_city_platform.csv")
    # Topic output is aggregate-safe: code names and counts only, no source text.
    assert {"code_family", "code", "denominator_posts"}.issubset(topic.columns)

    enjoyment = pd.read_csv(tmp_path / "out" / "chinese_enjoyment_evidence_by_city_platform.csv")
    # "Enjoyment" here means positive/recommendation keyword evidence, not a
    # validated psychology scale.
    positive = enjoyment[
        (enjoyment["city"] == "Fukui")
        & (enjoyment["source_platform"] == "xiaohongshu")
        & (enjoyment["code"] == "positive_sentiment")
    ].iloc[0]
    assert positive["count"] == 1

    codebook_summary = pd.read_csv(tmp_path / "out" / "chinese_reviewed_codebook_runtime_summary.csv")
    assert {"friction", "topic", "sentiment"}.issubset(set(codebook_summary["code_family"]))


def test_xhs_only_variant_excludes_douyin_and_labels_outputs(tmp_path):
    xhs = tmp_path / "fukui_xhs_reviews.csv"
    xhs.write_text(
        "note_id,title,note_url,author,author_url\n"
        "n1,福井交通不便 公交班次少,https://xhs.example/n1,a,\n",
        encoding="utf-8",
    )
    douyin = tmp_path / "fukui_douyin_comments_from_md.csv"
    douyin.write_text(
        "source_record_id,douyin_post_id,author,comment_text,relative_time,parse_confidence,parse_notes,source_start_line,source_end_line\n"
        "comment_000001,,旅行者,福井小众游超赞,2月前,medium,local_record_id_not_platform_comment_id,10,12\n",
        encoding="utf-8",
    )

    report = build_chinese_social_outputs(
        input_dir=tmp_path,
        output_dir=tmp_path / "out_xhs_only",
        input_files=[xhs, douyin],
        review_friction_path=tmp_path / "missing_review_friction.csv",
        xhs_only=True,
    )

    assert report["analysis_variant"] == "xiaohongshu_only"
    assert report["n_total_xhs_rows"] == 1
    assert report["n_total_douyin_rows"] == 0
    assert report["source_platform_counts"] == {"xiaohongshu": 1}
    readiness = (tmp_path / "out_xhs_only" / "chinese_social_readiness.md").read_text(encoding="utf-8")
    assert "xiaohongshu_only" in readiness


def test_normalize_social_csv_maps_douyin_comment_export(tmp_path):
    # Douyin comments use local parser IDs and relative times; the parser keeps
    # those caveats visible in normalized fields.
    douyin = tmp_path / "fukui_douyin_comments_from_md.csv"
    douyin.write_text(
        "source_record_id,douyin_post_id,author,comment_text,relative_time,parse_confidence,parse_notes,source_start_line,source_end_line\n"
        "comment_000001,,旅行者,福井小众游超赞,2月前,medium,local_record_id_not_platform_comment_id,10,12\n",
        encoding="utf-8",
    )

    df = normalize_social_csv(douyin, reference_date=REFERENCE_DATE)

    assert len(df) == 1
    assert df.loc[0, "city"] == "Fukui"
    assert df.loc[0, "source_platform"] == "douyin"
    assert df.loc[0, "source_record_id"] == "comment_000001"
    assert df.loc[0, "title"] == ""
    assert df.loc[0, "text_content"] == "福井小众游超赞"
    assert df.loc[0, "author"] == "旅行者"
    assert df.loc[0, "post_date"] == "2026-04-13"
    assert df.loc[0, "post_date_precision"] == "relative_inferred"


def test_douyin_comment_export_fails_when_provenance_columns_missing(tmp_path):
    # Parsed Douyin files need line-number provenance so another reviewer can
    # trace a row back to the markdown export.
    douyin = tmp_path / "fukui_douyin_comments_from_md.csv"
    douyin.write_text(
        "source_record_id,comment_text,relative_time,parse_confidence,parse_notes\n"
        "comment_000001,福井小众游超赞,2月前,medium,local_record_id_not_platform_comment_id\n",
        encoding="utf-8",
    )

    try:
        normalize_social_csv(douyin, reference_date=REFERENCE_DATE)
    except InputSchemaError as error:
        assert "source_start_line" in str(error)
        assert "source_end_line" in str(error)
    else:
        raise AssertionError("Expected InputSchemaError")


def test_douyin_comment_export_fails_without_parser_id_caveat(tmp_path):
    # The pipeline must not treat local parser IDs like real platform comment IDs.
    douyin = tmp_path / "fukui_douyin_comments_from_md.csv"
    douyin.write_text(
        "source_record_id,douyin_post_id,author,comment_text,relative_time,parse_confidence,parse_notes,source_start_line,source_end_line\n"
        "comment_000001,,旅行者,福井小众游超赞,2月前,medium,parsed_from_markdown,10,12\n",
        encoding="utf-8",
    )

    try:
        normalize_social_csv(douyin, reference_date=REFERENCE_DATE)
    except InputSchemaError as error:
        assert "missing_local_id_caveat" in str(error)
    else:
        raise AssertionError("Expected InputSchemaError")


def test_reviewed_chinese_codebook_supersedes_legacy_yaml_terms():
    # Reviewed CSV decisions are now runtime inputs, so FIX/delete decisions
    # must override older YAML keywords for the same code.
    codebook = load_chinese_codebook()

    assert "都是英语" in codebook["language_information_gap"]["keywords"]
    assert "英语" not in codebook["language_information_gap"]["keywords"]
    assert codebook["scenic_nature"]["type"] == "topic"
    assert "推荐" in codebook["recommendation_intent"]["keywords"]


def test_parse_author_and_date_handles_xhs_display_forms():
    # Xiaohongshu dates appear in several display formats; this verifies the
    # precision label that tells downstream code how trustworthy the date is.
    assert parse_author_and_date("Juunae 2025-08-14", REFERENCE_DATE) == ("Juunae", "2025-08-14", "exact")
    assert parse_author_and_date("momo 05-25", REFERENCE_DATE) == ("momo", "2026-05-25", "year_inferred")
    # Month-day later than the scrape date belongs to the previous year.
    assert parse_author_and_date("li 09-01", REFERENCE_DATE) == ("li", "2025-09-01", "year_inferred")
    assert parse_author_and_date("姐妹你误会了 昨天 22:03", REFERENCE_DATE) == ("姐妹你误会了", "2026-06-11", "relative_inferred")
    assert parse_author_and_date("某人 3天前", REFERENCE_DATE) == ("某人", "2026-06-09", "relative_inferred")
    assert parse_author_and_date("无日期作者", REFERENCE_DATE) == ("无日期作者", "", "none")


def test_parse_douyin_relative_time_marks_approximate_dates():
    # Douyin relative times become approximate dates only; they never become
    # exact monthly-trend evidence.
    assert parse_douyin_relative_time("1周前", REFERENCE_DATE) == ("2026-06-05", "relative_inferred")
    assert parse_douyin_relative_time("2月前", REFERENCE_DATE) == ("2026-04-13", "relative_inferred")
    assert parse_douyin_relative_time("6年前", REFERENCE_DATE) == ("2020-06-13", "relative_inferred")
    assert parse_douyin_relative_time("", REFERENCE_DATE) == ("", "none")


def test_discover_input_files_searches_raw_social_layout(tmp_path):
    # Discovery should find source-like social CSVs and the current parsed
    # Douyin comments export, while ignoring unrelated files.
    social_dir = tmp_path / "data" / "raw" / "social"
    social_dir.mkdir(parents=True)
    (social_dir / "fukui_xhs_reviews.csv").write_text("note_id,title,note_url,author,author_url\n", encoding="utf-8")
    processed_dir = tmp_path / "data" / "processed"
    processed_dir.mkdir(parents=True)
    (processed_dir / "fukui_douyin_comments_from_md.csv").write_text("source_record_id,comment_text\n", encoding="utf-8")
    (social_dir / "README.md").write_text("not a csv", encoding="utf-8")
    (tmp_path / "unrelated.csv").write_text("a,b\n", encoding="utf-8")

    files = discover_input_files(tmp_path)

    assert [path.name for path in files] == ["fukui_douyin_comments_from_md.csv", "fukui_xhs_reviews.csv"]


def test_theme_annotations_join_from_processed_csv(tmp_path):
    # Colleague theme/fan/travel annotations live in processed files and are
    # joined as annotations, not used as the text source of truth.
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
        input_files=[raw],
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
    # Rows without an annotation should still survive; `unclassified` makes the
    # missing theme explicit in denominator reporting.
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
        input_files=[social_dir / "fukui_xhs_reviews.csv"],
        review_friction_path=tmp_path / "missing.csv",
    )
    assert report["theme_counts"] == {"unclassified": 1}
