"""Render one figure comparing the two Chinese-language anchors side by side.

The project carries two complementary Chinese sources:
  - Xiaohongshu (XHS): Fukui-only mainland social posts, pre-trip, promotional.
  - Chinese-language Google reviews: Hokuriku-wide, post-visit, star-rated.

Both are SnowNLP-scored with the same instrument, so their sentiment bars are
comparable. This figure draws both CN bars (labeled by source + scope) alongside
the English/Japanese review volumes for context. Every number is read live from
the two cross-language baseline snapshots — none is hand-typed.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from build_presentation_safe_outputs import _write_multilingual_volume_context  # noqa: E402

XHS_BASELINE = ROOT / "output" / "cross_language_trends" / "cross_language_baseline_snapshot.csv"
GOOGLE_BASELINE = ROOT / "output" / "cross_language_trends_hokuriku" / "cross_language_baseline_snapshot.csv"
OUTPUT = ROOT / "output" / "presentation_safe" / "multilingual" / "figure_cn_anchor_comparison.svg"


def _agg(df: pd.DataFrame, mask: pd.Series, label: str, source_kind: str) -> dict:
    chunk = df[mask]
    volume = int(chunk["volume"].sum())

    def _wmean(col: str) -> float | None:
        valid = chunk[chunk[col].notna()]
        if valid.empty:
            return None
        return round(float(np.average(valid[col], weights=valid["volume"])), 4)

    return {
        "group": label,
        "source_kind": source_kind,
        "volume": volume,
        "rating_mean": _wmean("rating_mean"),
        "sentiment_norm_mean": _wmean("sentiment_norm_mean"),
        "positive_pct": None,
        "neutral_pct": None,
        "negative_pct": None,
    }


def build(output: Path = OUTPUT) -> Path:
    xhs = pd.read_csv(XHS_BASELINE)
    goo = pd.read_csv(GOOGLE_BASELINE)
    rows = [
        _agg(xhs, xhs["source_kind"] == "chinese_social_post", "Chinese · Xiaohongshu (Fukui, social)", "chinese_social_post"),
        _agg(goo, goo["source_kind"] == "chinese_social_post", "Chinese · Google reviews (Hokuriku)", "chinese_social_post"),
        _agg(goo, goo["group"] == "english", "english", "google_review"),
        _agg(goo, goo["group"] == "japanese", "japanese", "google_review"),
    ]
    combined = pd.DataFrame(rows)
    output.parent.mkdir(parents=True, exist_ok=True)
    _write_multilingual_volume_context(combined, output)
    print(f"Wrote two-anchor CN comparison figure -> {output}")
    for r in rows:
        metric = f"rating {r['rating_mean']}" if r["source_kind"] == "google_review" else f"SnowNLP {r['sentiment_norm_mean']}"
        print(f"  {r['group']:<42} n={r['volume']:<5} {metric}")
    return output


if __name__ == "__main__":
    build()
