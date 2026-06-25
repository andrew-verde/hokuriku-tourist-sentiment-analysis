#!/usr/bin/env python3
"""
H1: Sentiment Polarity Distribution, JP vs EN Google Reviews.

Research question:
    Do English-language and Japanese-language Fukui Google reviews differ in
    positive/neutral/negative sentiment category prevalence?

Null hypothesis:
    Sentiment category distribution is independent of review language group.

Alternative hypothesis:
    Sentiment category distribution differs by review language group.

Unit of analysis:
    One Fukui Google review row from the ignored scored-review audit file.

Valid interpretation:
    Results compare category shares produced by this VADER/oseti threshold
    pipeline. They do not compare raw VADER compound scores with raw oseti
    document scores as a common scale.

Limitations:
    Review rows are nested in POIs, English/Japanese denominators are imbalanced,
    and language-specific sentiment tools can classify text differently.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.provenance import repo_relative
from scripts.hypothesis_test_common import (
    COMMON_CAVEATS,
    DEFAULT_GROUPS,
    group_denominators,
    holm_adjust,
    load_scored_reviews,
    parse_common_args,
    sha256_file,
    generated_at as generated_at_now,
    default_command,
    write_csv,
    write_manifest,
)

REQUIRED_COLUMNS = {"language_group", "sentiment_category"}
CATEGORY_ORDER = ["negative", "neutral", "positive"]
INPUT_PATH = Path(__file__).resolve().parent.parent / "output" / "sentiment_row_level" / "google_reviews_fukui_japanese-english.csv"
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "output" / "hypothesis_tests"
OUTPUT_CSV = OUTPUT_DIR / "h1_sentiment_category_jp_en.csv"
OUTPUT_MANIFEST = OUTPUT_DIR / "h1_sentiment_category_jp_en_manifest.json"
def _repo_relative_path(path: Path) -> Path:
    return Path(repo_relative(path))

# Define three chi-square tests with different neutral-band definitions:
# - Primary test: neutral band of +/- 0.05
# - Sensitivity tests: wider neutral bands (+/- 0.10, +/- 0.20) to check robustness
ANALYSES = [
    ("primary", "sentiment_category", "neutral band +/-0.05"),
    ("sensitivity", "sentiment_category_neutral_0_10", "neutral band +/-0.10"),
    ("sensitivity", "sentiment_category_neutral_0_20", "neutral band +/-0.20"),
]

H1_CAVEATS = COMMON_CAVEATS + [
    "VADER and oseti scores are different scales; H1 tests category shares only.",
    "Sensitivity rows widen the neutral band and should be interpreted as robustness checks.",
]


def cramers_v(table: pd.DataFrame, chi2: float) -> float:
    """Compute Cramér's V effect size for a chi-square test result.

    Cramér's V measures association strength in a contingency table, ranging from
    0 (no association) to 1 (perfect association). It is the standardized square
    root of the chi-square statistic.
    """
    n = float(table.to_numpy().sum())
    if n == 0:
        return float("nan")
    r, k = table.shape
    denominator = n * min(r - 1, k - 1)
    return float(np.sqrt(chi2 / denominator)) if denominator else float("nan")


def _analysis_rows(
    df: pd.DataFrame,
    *,
    category_column: str,
    analysis_type: str,
    neutral_band_note: str,
    command: str,
    generated_at: str,
    input_path: Path,
) -> tuple[list[dict], float | None]:
    """Conduct chi-square test of sentiment category independence between English and Japanese reviews.

    Tests the null hypothesis that sentiment category distribution (negative, neutral, positive)
    is independent of review language group. Outputs one row per category-language combination,
    plus test summary metrics (chi-square statistic, p-value, Cramér's V effect size).
    """
    denominators = group_denominators(df)
    source_hash = sha256_file(input_path)
    rows: list[dict] = []

    if category_column not in df.columns:
        rows.append({
            "hypothesis": "H1",
            "analysis_type": analysis_type,
            "test_name": "chi_square_sentiment_category",
            "status": "skipped",
            "category_source_column": category_column,
            "category": None,
            "language_group": None,
            "observed_count": None,
            "expected_count": None,
            "standardized_residual": None,
            "category_share": None,
            "statistic": None,
            "p_value": None,
            "p_value_holm": None,
            "degrees_of_freedom": None,
            "effect_cramers_v": None,
            "min_expected_count": None,
            "sparse_expected_warning": True,
            "english_n": denominators["english"],
            "japanese_n": denominators["japanese"],
            "source_input_path": str(_repo_relative_path(input_path)),
            "source_input_sha256": source_hash,
            "command": command,
            "generated_at": generated_at,
            "neutral_band_note": neutral_band_note,
            "caveat": "; ".join(H1_CAVEATS),
            "details_json": json.dumps({"reason": f"missing column {category_column}"}),
        })
        return rows, None

    # Build a 2x3 contingency table: rows are language groups, columns are sentiment categories
    table = pd.crosstab(df["language_group"], df[category_column])
    table = table.reindex(index=list(DEFAULT_GROUPS), columns=CATEGORY_ORDER, fill_value=0)
    # Remove sentiment categories with zero counts to avoid chi-square validity issues
    nonzero_table = table.loc[:, table.sum(axis=0) > 0]
    # Chi-square requires at least 2 rows and 2 columns; skip test if not met
    if nonzero_table.shape[0] < 2 or nonzero_table.shape[1] < 2:
        rows.append({
            "hypothesis": "H1",
            "analysis_type": analysis_type,
            "test_name": "chi_square_sentiment_category",
            "status": "skipped",
            "category_source_column": category_column,
            "category": None,
            "language_group": None,
            "observed_count": None,
            "expected_count": None,
            "standardized_residual": None,
            "category_share": None,
            "statistic": None,
            "p_value": None,
            "p_value_holm": None,
            "degrees_of_freedom": None,
            "effect_cramers_v": None,
            "min_expected_count": None,
            "sparse_expected_warning": True,
            "english_n": denominators["english"],
            "japanese_n": denominators["japanese"],
            "source_input_path": str(_repo_relative_path(input_path)),
            "source_input_sha256": source_hash,
            "command": command,
            "generated_at": generated_at,
            "neutral_band_note": neutral_band_note,
            "caveat": "; ".join(H1_CAVEATS),
            "details_json": json.dumps({"reason": "fewer than two non-empty sentiment categories"}),
        })
        return rows, None

    # Perform chi-square test of independence between language group and sentiment category
    chi2, p_value, dof, expected = stats.chi2_contingency(nonzero_table)
    expected_frame = pd.DataFrame(expected, index=nonzero_table.index, columns=nonzero_table.columns)
    min_expected = float(np.min(expected))
    # Flag if minimum expected frequency < 5 (chi-square assumption violation)
    sparse_warning = bool(min_expected < 5)
    # Compute Cramér's V effect size (0 = no association, 1 = perfect association)
    effect = cramers_v(nonzero_table, float(chi2))
    details = {
        "observed_counts": nonzero_table.to_dict(),
        "expected_counts": expected_frame.round(6).to_dict(),
        "interpretation": "Chi-square test of language_group x sentiment_category share differences.",
    }
    if sparse_warning:
        details["sparse_expected_warning"] = "Minimum expected count below 5; interpret chi-square cautiously."

    # Generate one output row per category-language combination with observed/expected counts
    for language in DEFAULT_GROUPS:
        for category in CATEGORY_ORDER:
            observed = int(table.loc[language, category])
            expected_value = (
                float(expected_frame.loc[language, category])
                if category in expected_frame.columns
                else 0.0
            )
            # Standardized residual: (observed - expected) / sqrt(expected)
            # Large residuals indicate deviations from independence
            residual = (
                (observed - expected_value) / np.sqrt(expected_value)
                if expected_value > 0
                else None
            )
            rows.append({
                "hypothesis": "H1",
                "analysis_type": analysis_type,
                "test_name": "chi_square_sentiment_category",
                "status": "ok",
                "category_source_column": category_column,
                "category": category,
                "language_group": language,
                "observed_count": observed,
                "expected_count": round(expected_value, 6),
                "standardized_residual": None if residual is None else round(float(residual), 6),
                "category_share": round(observed / denominators[language], 6) if denominators[language] else None,
                "statistic": float(chi2),
                "p_value": float(p_value),
                "p_value_holm": None,
                "degrees_of_freedom": int(dof),
                "effect_cramers_v": effect,
                "min_expected_count": min_expected,
                "sparse_expected_warning": sparse_warning,
                "english_n": denominators["english"],
                "japanese_n": denominators["japanese"],
                "source_input_path": str(_repo_relative_path(input_path)),
                "source_input_sha256": source_hash,
                "command": command,
                "generated_at": generated_at,
                "neutral_band_note": neutral_band_note,
                "caveat": "; ".join(H1_CAVEATS),
                "details_json": json.dumps(details, ensure_ascii=False),
            })
    return rows, float(p_value)


def build_h1_sentiment_category(
    input_path: Path = INPUT_PATH,
    output_dir: Path = OUTPUT_DIR,
    command: str | None = None,
) -> dict:
    required = set(REQUIRED_COLUMNS) | {column for _, column, _ in ANALYSES}
    df = load_scored_reviews(input_path, required)
    command = command or default_command("test_h1_sentiment_category_jp_en.py")
    generated_at = generated_at_now()

    all_rows: list[dict] = []
    p_values: list[float | None] = []
    row_ranges: list[tuple[int, int]] = []
    for analysis_type, column, note in ANALYSES:
        start = len(all_rows)
        rows, p_value = _analysis_rows(
            df,
            category_column=column,
            analysis_type=analysis_type,
            neutral_band_note=note,
            command=command,
            generated_at=generated_at,
            input_path=input_path,
        )
        all_rows.extend(rows)
        row_ranges.append((start, len(all_rows)))
        p_values.append(p_value)

    # Apply Holm step-down correction across the three p-values (primary + two sensitivity tests)
    # This controls the family-wise error rate across multiple testing scenarios
    adjusted = holm_adjust(p_values)
    for (start, end), p_adjusted in zip(row_ranges, adjusted):
        for index in range(start, end):
            all_rows[index]["p_value_holm"] = p_adjusted

    out = pd.DataFrame(all_rows)
    output_csv = output_dir / OUTPUT_CSV.name
    output_manifest = output_dir / OUTPUT_MANIFEST.name
    write_csv(out, output_csv)
    manifest = write_manifest(
        kind="hypothesis_h1_sentiment_category_jp_en",
        command=command,
        generated=generated_at,
        input_path=input_path,
        output_csv=output_csv,
        manifest_path=output_manifest,
        metrics={
            "hypothesis": "H1",
            "primary_unit": "one Fukui Google review row",
            "denominators": group_denominators(df),
            "analyses": [column for _, column, _ in ANALYSES],
            "multiple_testing": "Holm adjustment across primary and neutral-band sensitivity category-share tests.",
        },
        caveats=H1_CAVEATS,
    )
    return {"csv": str(output_csv), "manifest": str(output_manifest), "rows": len(out), "provenance": manifest}


def main() -> None:
    args = parse_common_args(__doc__ or "Run H1 JP/EN sentiment category test.")
    report = build_h1_sentiment_category(input_path=args.input, output_dir=args.output_dir)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
