import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.build_cross_language_trends import (
    MissingInputError,
    build_cross_language_trends,
)


def _write_inputs(tmp_path: Path) -> tuple[Path, Path]:
    reviews = tmp_path / "reviews_multilingual.csv"
    reviews.write_text(
        "city,language_group,review_date,review_rating,review_text\n"
        "Fukui,english,2025-08-03T10:00:00Z,5,Great cliffs\n"
        "Fukui,english,2025-08-20T10:00:00Z,3,Hard to reach\n"
        "Fukui,japanese,2025-08-05T10:00:00Z,4,良かった\n"
        "Fukui,other_non_english_non_japanese,2025-08-05T10:00:00Z,4,bra\n",
        encoding="utf-8",
    )
    chinese = tmp_path / "tagged_chinese_social_posts.csv"
    chinese.write_text(
        "city,source_platform,text_content,post_date,post_date_precision,sentiment_norm,theme\n"
        "Fukui,xiaohongshu,福井交通不便,2025-08-14,exact,0.0,travel\n"
        "Fukui,xiaohongshu,走Riku走过的道路,2025-08-30,year_inferred,0.5,fan\n"
        "Fukui,xiaohongshu,无日期帖子,,none,0.5,ordinary\n",
        encoding="utf-8",
    )
    return reviews, chinese


def test_monthly_trends_keeps_group_sentiment_scales_separate(tmp_path):
    reviews, chinese = _write_inputs(tmp_path)

    report = build_cross_language_trends(
        reviews_path=reviews,
        chinese_path=chinese,
        output_dir=tmp_path / "out",
    )

    trends = pd.read_csv(tmp_path / "out" / "monthly_trends.csv")
    assert set(trends["group"]) == {"english", "japanese", "chinese_social"}

    english = trends[(trends["group"] == "english") & (trends["month"] == "2025-08")].iloc[0]
    assert english["volume"] == 2
    assert english["rating_mean"] == 4.0
    assert pd.isna(english["sentiment_norm_mean"])

    chinese_row = trends[(trends["group"] == "chinese_social") & (trends["month"] == "2025-08")].iloc[0]
    assert chinese_row["volume"] == 2  # undated post excluded
    assert pd.isna(chinese_row["rating_mean"])
    assert chinese_row["sentiment_norm_mean"] == 0.25

    assert report["chinese_rows_total"] == 3
    assert report["chinese_rows_dated"] == 2


def test_chinese_theme_mix_monthly(tmp_path):
    reviews, chinese = _write_inputs(tmp_path)

    build_cross_language_trends(
        reviews_path=reviews,
        chinese_path=chinese,
        output_dir=tmp_path / "out",
    )

    mix = pd.read_csv(tmp_path / "out" / "chinese_theme_mix_monthly.csv")
    august = mix[mix["month"] == "2025-08"]
    assert set(august["theme"]) == {"travel", "fan"}
    assert august["pct_posts"].sum() == 100.0


def test_missing_inputs_fail_with_make_target_hint(tmp_path):
    reviews, chinese = _write_inputs(tmp_path)

    with pytest.raises(MissingInputError, match="make multilingual-reviews"):
        build_cross_language_trends(
            reviews_path=tmp_path / "absent.csv",
            chinese_path=chinese,
            output_dir=tmp_path / "out",
        )
    with pytest.raises(MissingInputError, match="make chinese-social"):
        build_cross_language_trends(
            reviews_path=reviews,
            chinese_path=tmp_path / "absent.csv",
            output_dir=tmp_path / "out",
        )
    assert not (tmp_path / "out").exists()
