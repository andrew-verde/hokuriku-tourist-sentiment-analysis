#!/usr/bin/env python3
"""
H2: Common-Scale Star Rating Difference, JP vs EN Google Reviews.

Research question:
    Do English-language and Japanese-language Fukui Google reviews differ in
    Google star ratings?

Null hypothesis:
    Mean review_rating is equal across English-language and Japanese-language
    Google reviews.

Alternative hypothesis:
    Mean review_rating differs by review language group.

Unit of analysis:
    Primary test uses one Fukui Google review row. POI-level sensitivity uses
    one POI-language mean rating.

Valid interpretation:
    Google review_rating is a common 1-to-5 scale across groups, so mean
    differences are interpretable as star-rating differences. This does not
    replace text sentiment analysis.

Limitations:
    Ratings can be ceiling-bound, rows are nested in POIs, and POI mix/date
    windows may differ by language group.
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
    load_scored_reviews,
    parse_common_args,
    sha256_file,
    generated_at as generated_at_now,
    default_command,
    safe_float,
    write_csv,
    write_manifest,
)

REQUIRED_COLUMNS = {"language_group", "review_rating", "poi_id"}
INPUT_PATH = Path(__file__).resolve().parent.parent / "output" / "sentiment_row_level" / "google_reviews_fukui_japanese-english.csv"
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "output" / "hypothesis_tests"
OUTPUT_CSV = OUTPUT_DIR / "h2_review_rating_jp_en.csv"
OUTPUT_MANIFEST = OUTPUT_DIR / "h2_review_rating_jp_en_manifest.json"
def _repo_relative_path(path: Path) -> Path:
    return Path(repo_relative(path))

H2_CAVEATS = COMMON_CAVEATS + [
    "Google review_rating is common-scale companion outcome evidence, not a replacement for text sentiment.",
    "Ceiling effects are possible on 1-to-5 ratings.",
]


def _group_arrays(df: pd.DataFrame, value_column: str) -> dict[str, np.ndarray]:
    """Extract numeric values by language group (English and Japanese), dropping missing values."""
    return {
        language: pd.to_numeric(
            df.loc[df["language_group"] == language, value_column],
            errors="coerce",
        ).dropna().to_numpy(dtype=float)
        for language in DEFAULT_GROUPS
    }


def _welch_df(left: np.ndarray, right: np.ndarray) -> float | None:
    """Compute degrees of freedom for Welch's t-test (accounts for unequal variances and sample sizes).

    Uses the Welch-Satterthwaite equation to adjust degrees of freedom when
    variances between groups are unequal.
    """
    if len(left) < 2 or len(right) < 2:
        return None
    # Compute sample variances with Bessel correction (ddof=1)
    var_left = float(np.var(left, ddof=1))
    var_right = float(np.var(right, ddof=1))
    n_left = float(len(left))
    n_right = float(len(right))
    # Standard errors from unequal variances
    se_left = var_left / n_left
    se_right = var_right / n_right
    numerator = (se_left + se_right) ** 2
    # Welch-Satterthwaite formula
    denominator = 0.0
    if n_left > 1:
        denominator += (se_left**2) / (n_left - 1)
    if n_right > 1:
        denominator += (se_right**2) / (n_right - 1)
    if denominator == 0:
        return None
    return numerator / denominator


def _welch_ci(left: np.ndarray, right: np.ndarray) -> tuple[float | None, float | None, float | None]:
    """Compute the 95% confidence interval for the difference in means (Welch's method).

    Returns a tuple of (degrees_of_freedom, lower_bound, upper_bound).
    """
    df = _welch_df(left, right)
    if df is None:
        return None, None, None
    # Mean difference: English rating minus Japanese rating
    diff = float(np.mean(left) - np.mean(right))
    # Standard error of the difference (accounts for unequal variances)
    se = float(np.sqrt(np.var(left, ddof=1) / len(left) + np.var(right, ddof=1) / len(right)))
    if se == 0:
        return df, diff, diff
    # Critical value from t-distribution for 95% CI (two-tailed, alpha=0.05)
    critical = float(stats.t.ppf(0.975, df))
    return df, diff - critical * se, diff + critical * se


def _rating_distribution(values: pd.Series) -> str:
    """Count reviews at each star level (1-5) and return as JSON string.

    Used for descriptive summaries and to check for ceiling effects.
    """
    numeric = pd.to_numeric(values, errors="coerce").dropna()
    counts = {str(star): int((numeric == star).sum()) for star in range(1, 6)}
    return json.dumps(counts, sort_keys=True)


def _base_row(command: str, generated_at: str, input_path: Path, df: pd.DataFrame) -> dict:
    denominators = group_denominators(df)
    return {
        "hypothesis": "H2",
        "source_input_path": str(_repo_relative_path(input_path)),
        "source_input_sha256": sha256_file(input_path),
        "command": command,
        "generated_at": generated_at,
        "english_n": denominators["english"],
        "japanese_n": denominators["japanese"],
        "caveat": "; ".join(H2_CAVEATS),
    }


def _summary_rows(df: pd.DataFrame, command: str, generated_at: str, input_path: Path) -> list[dict]:
    """Generate descriptive statistics (mean, SD, median, distribution) for each language group."""
    rows = []
    base = _base_row(command, generated_at, input_path, df)
    for language in DEFAULT_GROUPS:
        chunk = df[df["language_group"] == language].copy()
        # Extract numeric ratings and separate present from missing
        ratings = pd.to_numeric(chunk["review_rating"], errors="coerce")
        present = ratings.dropna()
        rows.append({
            **base,
            "analysis_type": "group_summary",
            "test_name": "rating_descriptives",
            "status": "ok",
            "language_group": language,
            "unit": "one Google review row",
            "n_rating_present": int(present.size),
            "n_rating_missing": int(ratings.isna().sum()),
            "mean_review_rating": safe_float(present.mean()),
            "sd_review_rating": safe_float(present.std(ddof=1)) if present.size >= 2 else None,
            "median_review_rating": safe_float(present.median()),
            "poi_count": int(chunk["poi_id"].dropna().astype(str).nunique()),
            "rating_distribution_json": _rating_distribution(chunk["review_rating"]),
            "statistic": None,
            "p_value": None,
            "effect_mean_difference": None,
            "ci_95_lower": None,
            "ci_95_upper": None,
            "degrees_of_freedom": None,
            "details_json": json.dumps({"measurement_scale": "common_google_1_to_5_star_rating"}),
        })
    return rows


def _welch_row(
    df: pd.DataFrame,
    arrays: dict[str, np.ndarray],
    command: str,
    generated_at: str,
    input_path: Path,
    *,
    test_name: str,
    unit: str,
) -> dict:
    """Conduct Welch's t-test comparing mean ratings between English and Japanese reviews.

    Welch's t-test does not assume equal variances, making it robust for comparing
    groups with different dispersions. Returns test statistic, p-value, mean difference,
    and 95% confidence interval.
    """
    base = _base_row(command, generated_at, input_path, df)
    left = arrays["english"]
    right = arrays["japanese"]
    if len(left) < 2 or len(right) < 2:
        return {
            **base,
            "analysis_type": "test",
            "test_name": test_name,
            "status": "skipped",
            "language_group": None,
            "unit": unit,
            "n_rating_present": None,
            "n_rating_missing": None,
            "mean_review_rating": None,
            "sd_review_rating": None,
            "median_review_rating": None,
            "poi_count": None,
            "rating_distribution_json": None,
            "statistic": None,
            "p_value": None,
            "effect_mean_difference": None,
            "ci_95_lower": None,
            "ci_95_upper": None,
            "degrees_of_freedom": None,
            "details_json": json.dumps({
                "reason": "fewer than 2 ratings per language group",
                "english_n": int(len(left)),
                "japanese_n": int(len(right)),
            }),
        }
    # Welch's independent t-test: two-tailed hypothesis test of equal means
    # equal_var=False allows unequal variances; alternative="two-sided" tests both directions
    result = stats.ttest_ind(left, right, equal_var=False, alternative="two-sided")
    # Compute 95% confidence interval for the mean difference
    df_welch, ci_lower, ci_upper = _welch_ci(left, right)
    return {
        **base,
        "analysis_type": "test",
        "test_name": test_name,
        "status": "ok",
        "language_group": None,
        "unit": unit,
        "n_rating_present": None,
        "n_rating_missing": None,
        "mean_review_rating": None,
        "sd_review_rating": None,
        "median_review_rating": None,
        "poi_count": None,
        "rating_distribution_json": None,
        "statistic": safe_float(result.statistic),
        "p_value": safe_float(result.pvalue),
        "effect_mean_difference": float(np.mean(left) - np.mean(right)),
        "ci_95_lower": ci_lower,
        "ci_95_upper": ci_upper,
        "degrees_of_freedom": df_welch,
        "details_json": json.dumps({
            "left": "english",
            "right": "japanese",
            "effect": "english_mean_rating_minus_japanese_mean_rating",
            "english_n": int(len(left)),
            "japanese_n": int(len(right)),
            "measurement_scale": "common_google_1_to_5_star_rating",
        }),
    }


def build_h2_review_rating(
    input_path: Path = INPUT_PATH,
    output_dir: Path = OUTPUT_DIR,
    command: str | None = None,
) -> dict:
    df = load_scored_reviews(input_path, REQUIRED_COLUMNS)
    df = df.copy()
    df["review_rating"] = pd.to_numeric(df["review_rating"], errors="coerce")
    command = command or default_command("test_h2_review_rating_jp_en.py")
    generated_at = generated_at_now()

    # Add descriptive statistics by language group
    rows = _summary_rows(df, command, generated_at, input_path)
    # Extract ratings by language group for row-level test
    rating_arrays = _group_arrays(df, "review_rating")
    # Conduct Welch's t-test on row-level reviews (primary test)
    rows.append(_welch_row(
        df,
        rating_arrays,
        command,
        generated_at,
        input_path,
        test_name="welch_t_review_rating",
        unit="one Google review row",
    ))

    # Sensitivity test: aggregate reviews by POI and language to account for POI-level nesting
    # (reviews within the same POI may be correlated)
    poi_rating = (
        df[["language_group", "poi_id", "review_rating"]]
        .dropna()
        .assign(poi_id=lambda frame: frame["poi_id"].astype(str))
        .groupby(["language_group", "poi_id"], as_index=False)
        .agg(mean_review_rating=("review_rating", "mean"))
    )
    # Conduct Welch's t-test on POI-language aggregates
    poi_arrays = _group_arrays(poi_rating, "mean_review_rating")
    rows.append(_welch_row(
        df,
        poi_arrays,
        command,
        generated_at,
        input_path,
        test_name="poi_level_welch_t_mean_review_rating",
        unit="one POI-language mean Google rating",
    ))

    # Sensitivity test: Mann-Whitney U test (non-parametric rank test of distribution differences)
    # This does not assume normality and tests whether rating distributions differ
    left = rating_arrays["english"]
    right = rating_arrays["japanese"]
    if len(left) >= 1 and len(right) >= 1:
        # Two-tailed Mann-Whitney U test (null: distributions are equal)
        mann = stats.mannwhitneyu(left, right, alternative="two-sided")
        status = "ok"
        statistic = safe_float(mann.statistic)
        p_value = safe_float(mann.pvalue)
        details = {"interpretation": "Rank/distribution sensitivity; not a mean-rating replacement."}
    else:
        status = "skipped"
        statistic = None
        p_value = None
        details = {"reason": "no ratings in one or both language groups"}
    rows.append({
        **_base_row(command, generated_at, input_path, df),
        "analysis_type": "sensitivity",
        "test_name": "mann_whitney_u_review_rating",
        "status": status,
        "language_group": None,
        "unit": "one Google review row",
        "n_rating_present": None,
        "n_rating_missing": None,
        "mean_review_rating": None,
        "sd_review_rating": None,
        "median_review_rating": None,
        "poi_count": None,
        "rating_distribution_json": None,
        "statistic": statistic,
        "p_value": p_value,
        "effect_mean_difference": None,
        "ci_95_lower": None,
        "ci_95_upper": None,
        "degrees_of_freedom": None,
        "details_json": json.dumps(details),
    })

    # Sensitivity test: Chi-square test of rating distribution independence
    # Build a 2x5 contingency table: rows are language groups, columns are star ratings (1-5)
    distribution = pd.crosstab(df["language_group"], df["review_rating"]).reindex(
        index=list(DEFAULT_GROUPS), columns=[1, 2, 3, 4, 5], fill_value=0
    )
    # Remove star levels with zero counts
    nonzero_distribution = distribution.loc[:, distribution.sum(axis=0) > 0]
    # Chi-square test requires at least 2 columns (rating levels)
    if nonzero_distribution.shape[1] >= 2:
        # Chi-square test of independence between language group and star rating
        chi2, p_value, dof, expected = stats.chi2_contingency(nonzero_distribution)
        status = "ok"
        statistic = float(chi2)
        details = {
            "observed": nonzero_distribution.to_dict(),
            "expected": np.round(expected, 6).tolist(),
            "min_expected_count": float(np.min(expected)),
        }
    else:
        status = "skipped"
        statistic = None
        p_value = None
        dof = None
        details = {"reason": "fewer than two observed rating levels"}
    rows.append({
        **_base_row(command, generated_at, input_path, df),
        "analysis_type": "sensitivity",
        "test_name": "chi_square_rating_distribution",
        "status": status,
        "language_group": None,
        "unit": "one Google review row",
        "n_rating_present": None,
        "n_rating_missing": None,
        "mean_review_rating": None,
        "sd_review_rating": None,
        "median_review_rating": None,
        "poi_count": None,
        "rating_distribution_json": None,
        "statistic": statistic,
        "p_value": safe_float(p_value) if status == "ok" else None,
        "effect_mean_difference": None,
        "ci_95_lower": None,
        "ci_95_upper": None,
        "degrees_of_freedom": int(dof) if status == "ok" else None,
        "details_json": json.dumps(details, ensure_ascii=False),
    })

    out = pd.DataFrame(rows)
    output_csv = output_dir / OUTPUT_CSV.name
    output_manifest = output_dir / OUTPUT_MANIFEST.name
    write_csv(out, output_csv)
    manifest = write_manifest(
        kind="hypothesis_h2_review_rating_jp_en",
        command=command,
        generated=generated_at,
        input_path=input_path,
        output_csv=output_csv,
        manifest_path=output_manifest,
        metrics={
            "hypothesis": "H2",
            "primary_unit": "one Fukui Google review row",
            "sensitivity_unit": "one POI-language mean Google rating",
            "denominators": group_denominators(df),
            "measurement_scale": "common_google_1_to_5_star_rating",
        },
        caveats=H2_CAVEATS,
    )
    return {"csv": str(output_csv), "manifest": str(output_manifest), "rows": len(out), "provenance": manifest}


def main() -> None:
    args = parse_common_args(__doc__ or "Run H2 JP/EN review-rating test.")
    report = build_h2_review_rating(input_path=args.input, output_dir=args.output_dir)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
