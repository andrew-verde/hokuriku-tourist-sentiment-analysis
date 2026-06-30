#!/usr/bin/env python3
"""
Build nudge opportunity analysis from reviewed tourist-review aspect codes.

Research purpose:
    Rank exploratory, hypothesis-generating "nudge opportunities" by combining
    how often an aspect appears with its adjusted association with low star
    ratings. The primary outcome is Google star rating, not language-specific
    sentiment tools.

Methods:
    - Wilson score intervals for binomial prevalence, using the standard 95%
      score interval (Wilson, 1927).
    - Firth penalized logistic regression, using Jeffreys-prior penalized
      likelihood to avoid separation artifacts in rare aspect codes (Firth,
      1993; Heinze and Schemper, 2002).
    - Benjamini-Hochberg False Discovery Rate correction across aspect tests in
      each analysis family (Benjamini and Hochberg, 1995).
    - Gated opportunity score for friction aspects only:
      pooled_prevalence * max(0, ln(odds_ratio)), counted only when the
      aspect is FDR-significant and the odds ratio is above 1.

Valid interpretation:
    These are exploratory associations for ranking next-semester intervention
    hypotheses. They are not causal estimates and do not estimate nudge
    effectiveness.
"""

from __future__ import annotations

import argparse
import math
import sys
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.special import expit
from scipy.stats import chi2

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.hypothesis_test_common import (  # noqa: E402
    assert_safe_aggregate,
    default_command,
    generated_at as generated_at_now,
    safe_float,
)
from scripts.within_language_sentiment_common import apply_bh  # noqa: E402
from src.provenance import file_record, research_manifest, write_json  # noqa: E402


ROOT = Path(__file__).resolve().parent.parent
# Analysis reads the Chinese-folded tagged file (zh promoted to language_group='chinese');
# produced by build_chinese_folded_multilingual.py from the external tagged_reviews_multilingual.csv.
TAGGED_INPUT = ROOT / "output" / "multilingual_review_analysis" / "tagged_reviews_multilingual_chinese_folded.csv"
SENTIMENT_INPUT = ROOT / "output" / "sentiment_row_level" / "google_reviews_fukui_japanese-english.csv"
OUTPUT_DIR = ROOT / "output" / "nudge_analysis"
OUTPUT_CSV = OUTPUT_DIR / "aspect_opportunity_map.csv"
OUTPUT_MANIFEST = OUTPUT_DIR / "aspect_opportunity_map_manifest.json"

PRIMARY_LANGUAGES = ("english", "japanese", "chinese")
SECONDARY_LANGUAGES = ("english", "japanese")
INBOUND_LANGUAGES = ("english", "chinese")
CITY_TO_PREFECTURE = {
    "Fukui": "Fukui",
    "Kanazawa": "Ishikawa",
    "Toyama": "Toyama",
}
MIN_POOLED_POSITIVE = 20
FIRTH_TOL = 1e-6
FIRTH_MAX_ITER = 50
MAX_ABS_LOG_OR = 12.0
MIN_VALID_P_VALUE = 1e-40
PROBABILITY_EPSILON = 1e-12

FRICTION_ASPECTS = [
    "transport_access",
    "wayfinding_signage",
    "english_information_gap",
    "staff_communication",
    "booking_ticketing",
    "waiting_crowding",
    "price_value",
    "cleanliness_comfort",
    "opening_hours_availability",
    "itinerary_fit_time_cost",
    "accessibility_mobility",
    "food_amenities_gap",
]
DRAW_ASPECTS = [
    "scenic_value",
    "worthwhile_destination",
    "friendly_service",
    "underpromoted_feature",
    "easy_if_guided",
    "good_for_itinerary_bundle",
]
ASPECTS = FRICTION_ASPECTS + DRAW_ASPECTS
SIGNAL_TYPE = {aspect: "friction" for aspect in FRICTION_ASPECTS} | {
    aspect: "draw" for aspect in DRAW_ASPECTS
}
METHOD_C_ASPECTS = [
    "english_information_gap",
    "wayfinding_signage",
    "transport_access",
]


class NudgeAnalysisError(RuntimeError):
    """Raised when a required input, schema, or model condition is invalid."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build aggregate nudge opportunity scores from aspect-coded tourist reviews."
    )
    parser.add_argument("--tagged-input", type=Path, default=TAGGED_INPUT)
    parser.add_argument("--sentiment-input", type=Path, default=SENTIMENT_INPUT)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    return parser.parse_args()


def dependency_versions() -> dict[str, str]:
    """Record library versions needed to reproduce the statistical estimates."""
    versions = {}
    for package in ["pandas", "numpy", "scipy", "statsmodels", "patsy"]:
        try:
            versions[package] = metadata.version(package)
        except metadata.PackageNotFoundError:
            versions[package] = "missing"
    return versions


def require_columns(df: pd.DataFrame, path: Path, columns: set[str]) -> None:
    missing = sorted(columns - set(df.columns))
    if missing:
        raise NudgeAnalysisError(f"Required columns missing from {path}: {', '.join(missing)}")


def load_csv_fail_loud(path: Path, required_columns: set[str], producer: str) -> pd.DataFrame:
    if not path.exists():
        raise NudgeAnalysisError(
            f"Required input not found: {path}\nRun `{producer}` first. No demo mode."
        )
    df = pd.read_csv(path)
    require_columns(df, path, required_columns)
    return df.copy()


def strict_binary(series: pd.Series, column: str) -> pd.Series:
    """Convert reviewed aspect-code columns to 0/1, failing on invalid values."""
    if series.isna().any():
        raise NudgeAnalysisError(f"Aspect column contains missing values: {column}")
    if series.dtype == bool:
        return series.astype(int)
    text = series.astype(str).str.strip().str.lower()
    allowed = {"true", "false", "1", "0", "yes", "no", "y", "n", "t", "f"}
    bad = sorted(set(text) - allowed)
    if bad:
        raise NudgeAnalysisError(f"Aspect column {column} has non-binary values: {bad[:10]}")
    return text.isin({"true", "1", "yes", "y", "t"}).astype(int)


def add_text_length(df: pd.DataFrame, path: Path) -> pd.DataFrame:
    """Ensure a text-length covariate exists.

    The tagged review file currently stores review_text, not text_length_chars.
    We compute character length for modeling, then exclude review_text from all
    aggregate outputs.
    """
    df = df.copy()
    if "text_length_chars" in df.columns:
        df["text_length_chars"] = pd.to_numeric(df["text_length_chars"], errors="coerce")
        if df["text_length_chars"].isna().any():
            raise NudgeAnalysisError(f"text_length_chars contains missing/non-numeric values in {path}")
        return df
    if "review_text" not in df.columns:
        raise NudgeAnalysisError(
            f"{path} lacks text_length_chars and review_text, so text length cannot be derived"
        )
    if df["review_text"].isna().any():
        raise NudgeAnalysisError(f"review_text contains missing values in {path}")
    df["text_length_chars"] = df["review_text"].astype(str).str.len()
    return df


def load_tagged(path: Path) -> tuple[pd.DataFrame, dict]:
    required = {
        "poi_id",
        "review_rating",
        "language_group",
        "city",
        "review_text",
        "review_id",
    } | set(ASPECTS)
    df = load_csv_fail_loud(
        path,
        required,
        "make multilingual-reviews",
    )
    df = add_text_length(df, path)
    df["language_group"] = df["language_group"].astype(str).str.strip().str.lower()
    df["prefecture"] = df["city"].map(CITY_TO_PREFECTURE)

    # Unknown cities would make the prefecture adjustment undocumented, so stop.
    unmapped_cities = sorted(df.loc[df["prefecture"].isna(), "city"].dropna().unique())
    if unmapped_cities:
        raise NudgeAnalysisError(f"Unmapped city values in {path}: {', '.join(unmapped_cities)}")

    for aspect in ASPECTS:
        df[aspect] = strict_binary(df[aspect], aspect)

    df["review_rating"] = pd.to_numeric(df["review_rating"], errors="coerce")

    language_counts = df["language_group"].value_counts(dropna=False).to_dict()
    primary = df[df["language_group"].isin(PRIMARY_LANGUAGES)].copy()
    dropped_language = int(len(df) - len(primary))

    missing_rating = int(primary["review_rating"].isna().sum())
    primary_model = primary.dropna(
        subset=["review_rating", "text_length_chars", "language_group", "prefecture", "poi_id"]
    ).copy()
    primary_model["low_rating"] = (primary_model["review_rating"] <= 3).astype(int)

    metrics = {
        "tagged_input_rows": int(len(df)),
        "tagged_language_group_counts": {str(k): int(v) for k, v in language_counts.items()},
        "primary_supported_language_rows": int(len(primary)),
        "dropped_unsupported_language_rows": dropped_language,
        "dropped_missing_rating_primary_rows": missing_rating,
        "primary_model_rows": int(len(primary_model)),
        "primary_low_rating_rows": int(primary_model["low_rating"].sum()),
    }
    return primary_model, metrics


def load_secondary_join(tagged_path: Path, sentiment_path: Path) -> tuple[pd.DataFrame, dict]:
    sentiment_required = {"review_id", "language_group", "sentiment_category", "text_length_chars"}
    tagged_required = {"review_id", "city", "language_group"} | set(ASPECTS)
    sentiment = load_csv_fail_loud(sentiment_path, sentiment_required, "make sentiment-analysis")
    tagged = load_csv_fail_loud(
        tagged_path,
        tagged_required,
        "make multilingual-reviews",
    )

    if sentiment["review_id"].duplicated().any():
        raise NudgeAnalysisError(f"Duplicate review_id values in {sentiment_path}")
    if tagged["review_id"].duplicated().any():
        raise NudgeAnalysisError(f"Duplicate review_id values in {tagged_path}")

    for aspect in ASPECTS:
        tagged[aspect] = strict_binary(tagged[aspect], aspect)

    # Join only the aspect flags from the tagged file onto the already-scored
    # JP/EN Fukui sentiment rows. This avoids cross-tool language comparison.
    sentiment = sentiment.copy()
    sentiment["language_group"] = sentiment["language_group"].astype(str).str.strip().str.lower()
    sentiment["text_length_chars"] = pd.to_numeric(sentiment["text_length_chars"], errors="coerce")
    sentiment["negative"] = (sentiment["sentiment_category"].astype(str).str.lower() == "negative").astype(int)
    tagged_subset = tagged[["review_id", "city", "language_group", *ASPECTS]].copy()
    tagged_subset["tagged_language_group"] = tagged_subset.pop("language_group").astype(str).str.strip().str.lower()
    joined = sentiment.merge(tagged_subset, on="review_id", how="inner")
    joined = joined[joined["language_group"].isin(SECONDARY_LANGUAGES)].copy()
    joined = joined.dropna(subset=["text_length_chars", "sentiment_category"])

    metrics = {
        "secondary_sentiment_input_rows": int(len(sentiment)),
        "secondary_join_rows": int(len(joined)),
        "secondary_unmatched_sentiment_rows": int(len(sentiment) - len(joined)),
        "secondary_language_group_counts": {
            str(k): int(v) for k, v in joined["language_group"].value_counts(dropna=False).to_dict().items()
        },
        "secondary_negative_rows": int(joined["negative"].sum()),
    }
    return joined, metrics


def wilson_interval(n_positive: int, n: int, z: float = 1.959963984540054) -> tuple[float | None, float | None, float | None]:
    """Return prevalence and Wilson 95% CI for a binomial proportion."""
    if n <= 0:
        return None, None, None
    p_hat = n_positive / n
    # Wilson score interval:
    # center = (p + z^2/(2n)) / (1 + z^2/n)
    # half-width = z * sqrt((p(1-p) + z^2/(4n))/n) / (1 + z^2/n)
    denom = 1 + (z * z / n)
    center = (p_hat + (z * z) / (2 * n)) / denom
    half_width = z * math.sqrt((p_hat * (1 - p_hat) + (z * z) / (4 * n)) / n) / denom
    return safe_float(p_hat), safe_float(max(0.0, center - half_width)), safe_float(min(1.0, center + half_width))


def safe_exp(value: float) -> float | None:
    """Exponentiate a log-odds value without crashing on extreme estimates."""
    try:
        return safe_float(math.exp(float(value)))
    except OverflowError:
        return None


@dataclass
class FirthFit:
    """Container for one Firth penalized logistic regression fit."""

    beta: np.ndarray
    covariance: np.ndarray
    penalized_loglik: float
    fitted_probability_min: float
    fitted_probability_max: float
    n_iter: int
    converged: bool
    reason: str


def penalized_loglikelihood(X: np.ndarray, y: np.ndarray, beta: np.ndarray) -> float:
    """Compute Firth penalized log-likelihood.

    The penalty is 0.5 * log(det(X' W X)), the Jeffreys-prior term used by
    Firth (1993, Biometrika 80:27). Heinze and Schemper (2002, Statistics in
    Medicine 21:2409) describe this as a practical remedy for separation in
    logistic regression.
    """
    p = np.clip(expit(X @ beta), PROBABILITY_EPSILON, 1 - PROBABILITY_EPSILON)
    w = p * (1 - p)
    information = X.T @ (w[:, None] * X)
    sign, logdet = np.linalg.slogdet(information)
    if sign <= 0 or not np.isfinite(logdet):
        return -math.inf
    ordinary = float(np.sum(y * np.log(p) + (1 - y) * np.log1p(-p)))
    return ordinary + 0.5 * float(logdet)


def fit_firth_penalized_logistic(
    X: np.ndarray,
    y: np.ndarray,
    *,
    max_iter: int = FIRTH_MAX_ITER,
    tol: float = FIRTH_TOL,
) -> FirthFit:
    """Fit Firth penalized logistic regression with Newton-Raphson.

    Modified score:
        U*_j = sum_i (y_i - p_i + h_i * (0.5 - p_i)) * X_ij

    where h_i is the diagonal of the logistic-regression hat matrix. This
    Jeffreys-prior adjustment shrinks infinite/separated logit estimates back
    to finite values while retaining the same covariate design.
    """
    beta = np.zeros(X.shape[1], dtype=float)
    if np.linalg.matrix_rank(X) < X.shape[1]:
        return FirthFit(beta, np.full((X.shape[1], X.shape[1]), np.nan), -math.inf, 0.0, 1.0, 0, False, "design matrix is rank deficient")

    current = penalized_loglikelihood(X, y, beta)
    covariance = np.full((X.shape[1], X.shape[1]), np.nan)
    for iteration in range(1, max_iter + 1):
        p = np.clip(expit(X @ beta), PROBABILITY_EPSILON, 1 - PROBABILITY_EPSILON)
        w = p * (1 - p)
        information = X.T @ (w[:, None] * X)
        try:
            information_inv = np.linalg.inv(information)
        except np.linalg.LinAlgError:
            return FirthFit(beta, covariance, current, float(p.min()), float(p.max()), iteration, False, "information matrix is singular")

        # Hat diagonal: h_i = w_i * x_i' (X'WX)^-1 x_i.
        hat_diag = w * np.einsum("ij,jk,ik->i", X, information_inv, X)
        modified_residual = y - p + hat_diag * (0.5 - p)
        modified_score = X.T @ modified_residual

        if float(np.linalg.norm(modified_score, ord=np.inf)) < tol:
            covariance = information_inv
            return FirthFit(beta, covariance, current, float(p.min()), float(p.max()), iteration, True, "converged")

        step = information_inv @ modified_score
        # Step-halving protects against overshooting in rare-event designs.
        accepted = False
        for halves in range(26):
            candidate = beta + step / (2**halves)
            candidate_loglik = penalized_loglikelihood(X, y, candidate)
            if np.isfinite(candidate_loglik) and candidate_loglik >= current - 1e-10:
                beta = candidate
                current = candidate_loglik
                accepted = True
                break
        if not accepted:
            return FirthFit(beta, information_inv, current, float(p.min()), float(p.max()), iteration, False, "step halving failed")

    p = np.clip(expit(X @ beta), PROBABILITY_EPSILON, 1 - PROBABILITY_EPSILON)
    w = p * (1 - p)
    information = X.T @ (w[:, None] * X)
    try:
        covariance = np.linalg.inv(information)
    except np.linalg.LinAlgError:
        return FirthFit(beta, covariance, current, float(p.min()), float(p.max()), max_iter, False, "information matrix is singular after max iterations")
    return FirthFit(beta, covariance, current, float(p.min()), float(p.max()), max_iter, False, "maximum iterations reached")


def build_design_matrix(
    df: pd.DataFrame,
    *,
    aspect: str,
    outcome: str,
    adjusted: bool,
) -> tuple[np.ndarray, np.ndarray, list[str], pd.DataFrame]:
    """Create the model matrix used for one aspect model.

    All models include an intercept, the aspect code, and log review length.
    Adjusted models add language and prefecture dummy variables only when more
    than one level is present in the analysis slice.
    """
    columns = [outcome, aspect, "text_length_chars"]
    if adjusted:
        columns += ["language_group", "prefecture"]
    work = df[columns].dropna().copy()
    work[aspect] = work[aspect].astype(int)
    work[outcome] = work[outcome].astype(int)

    design = pd.DataFrame({
        "intercept": 1.0,
        aspect: work[aspect].astype(float),
        "log1p_text_length_chars": np.log1p(work["text_length_chars"].astype(float)),
    })
    if adjusted:
        for covariate in ["language_group", "prefecture"]:
            if work[covariate].nunique(dropna=True) > 1:
                dummies = pd.get_dummies(work[covariate], prefix=covariate, drop_first=True, dtype=float)
                design = pd.concat([design, dummies], axis=1)

    X = design.to_numpy(dtype=float)
    y = work[outcome].to_numpy(dtype=float)
    return X, y, list(design.columns), work


def prevalence_row(
    *,
    df: pd.DataFrame,
    aspect: str,
    analysis: str,
    segment: str,
    command: str,
    generated: str,
    underpowered: bool,
    status: str,
    status_reason: str,
    multiple_testing_family: str | None,
) -> dict:
    n = int(len(df))
    n_positive = int(df[aspect].sum()) if n else 0
    prevalence, ci_low, ci_high = wilson_interval(n_positive, n)
    return {
        "analysis": analysis,
        "aspect": aspect,
        "signal_type": SIGNAL_TYPE[aspect],
        "segment": segment,
        "n": n,
        "n_positive": n_positive,
        "prevalence": prevalence,
        "prevalence_ci_low": ci_low,
        "prevalence_ci_high": ci_high,
        "odds_ratio": None,
        "or_ci_low": None,
        "or_ci_high": None,
        "p_value": None,
        "p_value_bh_fdr": None,
        "fdr_significant": False,
        "opportunity_score": None,
        "reward_direction": None,
        "ci_method": None,
        "underpowered": bool(underpowered),
        "status": status,
        "status_reason": status_reason,
        "multiple_testing_family": multiple_testing_family,
        "command": command,
        "generated_at": generated,
    }


def fit_logistic(
    *,
    df: pd.DataFrame,
    aspect: str,
    outcome: str,
    adjusted: bool,
) -> dict:
    """Fit one aspect model with Firth penalized logistic regression."""
    X, y, names, work = build_design_matrix(df, aspect=aspect, outcome=outcome, adjusted=adjusted)
    aspect_index = names.index(aspect)

    # Logistic regression needs variation in the outcome and predictor.
    if len(work) < 10:
        return {"status": "skipped", "reason": "fewer than 10 complete rows", "n_model": int(len(work))}
    if work[aspect].nunique() < 2:
        return {"status": "skipped", "reason": "aspect has no variation", "n_model": int(len(work))}
    if work[outcome].nunique() < 2:
        return {"status": "skipped", "reason": "outcome has no variation", "n_model": int(len(work))}

    try:
        full = fit_firth_penalized_logistic(X, y)
        reduced_X = np.delete(X, aspect_index, axis=1)
        reduced = fit_firth_penalized_logistic(reduced_X, y)
        if not full.converged:
            return {"status": "separation_unstable", "reason": full.reason, "n_model": int(len(work))}
        if not reduced.converged:
            return {"status": "separation_unstable", "reason": f"reduced model: {reduced.reason}", "n_model": int(len(work))}

        coef = float(full.beta[aspect_index])
        if abs(coef) > MAX_ABS_LOG_OR:
            return {"status": "separation_unstable", "reason": "absolute Firth log-OR exceeds validation threshold", "n_model": int(len(work))}
        if full.fitted_probability_min <= PROBABILITY_EPSILON or full.fitted_probability_max >= 1 - PROBABILITY_EPSILON:
            return {"status": "separation_unstable", "reason": "Firth fitted probability reached numerical boundary", "n_model": int(len(work))}

        variance = float(full.covariance[aspect_index, aspect_index])
        if not np.isfinite(variance) or variance <= 0:
            return {"status": "separation_unstable", "reason": "invalid penalized covariance for aspect term", "n_model": int(len(work))}
        se = math.sqrt(variance)
        lr_stat = max(0.0, 2 * (full.penalized_loglik - reduced.penalized_loglik))
        p_value = safe_float(chi2.sf(lr_stat, df=1))
        if p_value is not None and p_value < MIN_VALID_P_VALUE:
            return {"status": "separation_unstable", "reason": "penalized LRT p-value below validation threshold", "n_model": int(len(work))}

        return {
            "status": "ok",
            "reason": "firth_fit",
            "n_model": int(len(work)),
            "coef": safe_float(coef),
            "odds_ratio": safe_exp(coef),
            "or_ci_low": safe_exp(coef - 1.959963984540054 * se),
            "or_ci_high": safe_exp(coef + 1.959963984540054 * se),
            "p_value": p_value,
            "ci_method": "wald_penalized_information",
            "firth_iterations": int(full.n_iter),
            "fitted_probability_min": safe_float(full.fitted_probability_min),
            "fitted_probability_max": safe_float(full.fitted_probability_max),
        }
    except Exception as error:
        return {"status": "separation_unstable", "reason": f"{type(error).__name__}: {error}", "n_model": int(len(work))}


def attach_model_to_row(row: dict, fit: dict, pooled_prevalence: float | None) -> None:
    row["status"] = fit["status"]
    row["status_reason"] = fit["reason"]
    row["model_n"] = fit.get("n_model")
    if fit["status"] != "ok":
        return
    row["odds_ratio"] = fit["odds_ratio"]
    row["or_ci_low"] = fit["or_ci_low"]
    row["or_ci_high"] = fit["or_ci_high"]
    row["p_value"] = fit["p_value"]
    row["ci_method"] = fit.get("ci_method")
    row["firth_iterations"] = fit.get("firth_iterations")
    row["fitted_probability_min"] = fit.get("fitted_probability_min")
    row["fitted_probability_max"] = fit.get("fitted_probability_max")


def apply_fdr_gate(rows: list[dict], family: str, *, score_opportunities: bool) -> None:
    """Apply BH-FDR and compute only defensible gated scores.

    Prevalence, OR, CI, and p-values remain visible for all fitted rows. The
    opportunity score is set to zero unless a friction aspect is significant
    after FDR correction and points in the harmful direction.
    """
    apply_bh(rows, family)
    for row in rows:
        if row.get("multiple_testing_family") != family:
            continue
        p_adjusted = row.get("p_value_bh_fdr")
        row["fdr_significant"] = bool(p_adjusted is not None and p_adjusted < 0.05)
        if row["signal_type"] == "draw" and row.get("odds_ratio") is not None:
            row["reward_direction"] = "reward_or_lt_1" if row["odds_ratio"] < 1 else "not_reward_or_ge_1"
            if not row["fdr_significant"]:
                row["status_reason"] = f"{row['status_reason']}; draw not FDR-significant"
            continue
        if row["signal_type"] != "friction" or not score_opportunities:
            continue
        if row["status"] != "ok":
            row["opportunity_score"] = None
            continue
        if row["underpowered"]:
            row["opportunity_score"] = 0.0
            row["status_reason"] = f"{row['status_reason']}; underpowered so score gated to zero"
            continue
        if not row["fdr_significant"]:
            row["opportunity_score"] = 0.0
            row["status_reason"] = f"{row['status_reason']}; not FDR-significant so score gated to zero"
            continue
        if row.get("odds_ratio") is None or row["odds_ratio"] <= 1:
            row["opportunity_score"] = 0.0
            row["status_reason"] = f"{row['status_reason']}; OR not above 1 so score gated to zero"
            continue
        row["opportunity_score"] = safe_float(row["prevalence"] * math.log(row["odds_ratio"]))


def build_method_a_rows(df: pd.DataFrame, command: str, generated: str, analysis: str = "A_primary") -> tuple[list[dict], dict]:
    rows: list[dict] = []
    fit_count = 0
    skipped_count = 0
    for aspect in ASPECTS:
        pooled_positive = int(df[aspect].sum())
        underpowered = pooled_positive < MIN_POOLED_POSITIVE
        pooled = prevalence_row(
            df=df,
            aspect=aspect,
            analysis=analysis,
            segment="pooled",
            command=command,
            generated=generated,
            underpowered=underpowered,
            status="pending",
            status_reason="model not fit yet",
            multiple_testing_family=analysis,
        )
        fit = fit_logistic(df=df, aspect=aspect, outcome="low_rating", adjusted=True)
        if fit["status"] == "ok":
            fit_count += 1
        else:
            skipped_count += 1
        attach_model_to_row(pooled, fit, pooled["prevalence"])
        rows.append(pooled)

        # Language-specific rows show prevalence only. The adjusted penalty is
        # estimated once in the pooled model above for power and stable controls.
        for language in PRIMARY_LANGUAGES:
            segment_df = df[df["language_group"] == language]
            if len(segment_df) == 0:
                continue
            rows.append(prevalence_row(
                df=segment_df,
                aspect=aspect,
                analysis=analysis,
                segment=language,
                command=command,
                generated=generated,
                underpowered=underpowered,
                status="prevalence_only",
                status_reason="adjusted penalty estimated in pooled segment row",
                multiple_testing_family=None,
            ))
    apply_fdr_gate(rows, analysis, score_opportunities=True)
    return rows, {f"{analysis}_models_fit": fit_count, f"{analysis}_models_skipped": skipped_count}


def build_method_c_rows(df: pd.DataFrame, command: str, generated: str) -> tuple[list[dict], dict]:
    rows: list[dict] = []
    fit_count = 0
    skipped_count = 0
    inbound = df[df["language_group"].isin(INBOUND_LANGUAGES)].copy()
    present_languages = [language for language in INBOUND_LANGUAGES if language in set(inbound["language_group"])]
    if len(inbound) == 0:
        raise NudgeAnalysisError("No inbound rows available for Method C")

    for aspect in METHOD_C_ASPECTS:
        pooled_positive = int(inbound[aspect].sum())
        underpowered = pooled_positive < MIN_POOLED_POSITIVE
        pooled = prevalence_row(
            df=inbound,
            aspect=aspect,
            analysis="C_inbound",
            segment="inbound_pooled",
            command=command,
            generated=generated,
            underpowered=underpowered,
            status="pending",
            status_reason="model not fit yet",
            multiple_testing_family="C_inbound",
        )
        fit = fit_logistic(df=inbound, aspect=aspect, outcome="low_rating", adjusted=True)
        if fit["status"] == "ok":
            fit_count += 1
        else:
            skipped_count += 1
        attach_model_to_row(pooled, fit, pooled["prevalence"])
        rows.append(pooled)

        for language in present_languages:
            segment_df = inbound[inbound["language_group"] == language]
            rows.append(prevalence_row(
                df=segment_df,
                aspect=aspect,
                analysis="C_inbound",
                segment=language,
                command=command,
                generated=generated,
                underpowered=underpowered,
                status="prevalence_only",
                status_reason="adjusted penalty estimated in inbound_pooled segment row",
                multiple_testing_family=None,
            ))
    apply_fdr_gate(rows, "C_inbound", score_opportunities=True)
    return rows, {
        "C_inbound_rows": int(len(inbound)),
        "C_inbound_languages_present": present_languages,
        "C_inbound_models_fit": fit_count,
        "C_inbound_models_skipped": skipped_count,
    }


def build_secondary_rows(df: pd.DataFrame, command: str, generated: str) -> tuple[list[dict], dict]:
    rows: list[dict] = []
    metrics: dict[str, int] = {}
    for language in SECONDARY_LANGUAGES:
        language_df = df[df["language_group"] == language].copy()
        analysis = f"A_secondary_{'en' if language == 'english' else 'jp'}"
        fit_count = 0
        skipped_count = 0
        if len(language_df) == 0:
            raise NudgeAnalysisError(f"No secondary sentiment rows for language: {language}")
        for aspect in ASPECTS:
            n_positive = int(language_df[aspect].sum())
            row = prevalence_row(
                df=language_df,
                aspect=aspect,
                analysis=analysis,
                segment=language,
                command=command,
                generated=generated,
                underpowered=n_positive < MIN_POOLED_POSITIVE,
                status="pending",
                status_reason="model not fit yet",
                multiple_testing_family=analysis,
            )
            fit = fit_logistic(
                df=language_df,
                aspect=aspect,
                outcome="negative",
                adjusted=False,
            )
            if fit["status"] == "ok":
                fit_count += 1
            else:
                skipped_count += 1
            attach_model_to_row(row, fit, row["prevalence"])
            # Secondary rows are within-language checks, so they do not rank
            # friction opportunities across languages.
            row["opportunity_score"] = None
            rows.append(row)
        apply_fdr_gate(rows, analysis, score_opportunities=False)
        metrics[f"{analysis}_rows"] = int(len(language_df))
        metrics[f"{analysis}_negative_rows"] = int(language_df["negative"].sum())
        metrics[f"{analysis}_models_fit"] = fit_count
        metrics[f"{analysis}_models_skipped"] = skipped_count
    return rows, metrics


def plain_logit_or_for_sanity(df: pd.DataFrame, aspect: str, outcome: str, adjusted: bool) -> float | None:
    """Fit ordinary logit only for sanity comparison on well-behaved aspects."""
    try:
        import statsmodels.api as sm

        X, y, names, _ = build_design_matrix(df, aspect=aspect, outcome=outcome, adjusted=adjusted)
        result = sm.Logit(y, X).fit(disp=False, maxiter=100)
        return safe_exp(float(result.params[names.index(aspect)]))
    except Exception:
        return None


def run_validation_checks(primary_df: pd.DataFrame, rows: list[dict]) -> dict:
    """Validate that Firth removed separation artifacts before output ships."""
    metrics: dict[str, object] = {}
    sanity_aspects = [
        "opening_hours_availability",
        "price_value",
        "cleanliness_comfort",
        "itinerary_fit_time_cost",
    ]
    sanity: dict[str, dict[str, float | None]] = {}
    primary_by_aspect = {
        row["aspect"]: row
        for row in rows
        if row["analysis"] == "A_primary" and row["segment"] == "pooled"
    }
    for aspect in sanity_aspects:
        firth_or = primary_by_aspect.get(aspect, {}).get("odds_ratio")
        plain_or = plain_logit_or_for_sanity(primary_df, aspect, "low_rating", adjusted=True)
        log_abs_diff = None
        if firth_or is not None and plain_or is not None and firth_or > 0 and plain_or > 0:
            log_abs_diff = abs(math.log(firth_or) - math.log(plain_or))
            if log_abs_diff > 1.5:
                raise NudgeAnalysisError(
                    f"Firth/plain sanity check too far apart for {aspect}: {firth_or} vs {plain_or}"
                )
        sanity[aspect] = {
            "firth_or": safe_float(firth_or),
            "plain_logit_or": safe_float(plain_or),
            "log_abs_diff": safe_float(log_abs_diff),
        }

    # Synthetic 2x2 zero-cell check: ordinary logit separates, Firth stays finite.
    X = np.array(
        [
            [1.0, 0.0],
            [1.0, 0.0],
            [1.0, 0.0],
            [1.0, 0.0],
            [1.0, 1.0],
            [1.0, 1.0],
            [1.0, 1.0],
            [1.0, 1.0],
        ]
    )
    y = np.array([0.0, 0.0, 1.0, 1.0, 0.0, 0.0, 0.0, 0.0])
    synthetic = fit_firth_penalized_logistic(X, y)
    if not synthetic.converged or safe_exp(float(synthetic.beta[1])) is None:
        raise NudgeAnalysisError("Synthetic zero-cell Firth validation failed")
    metrics["synthetic_zero_cell_firth_or"] = safe_exp(float(synthetic.beta[1]))

    fitted_rows = [row for row in rows if row.get("status") == "ok" and row.get("odds_ratio") is not None]
    if any(abs(math.log(float(row["odds_ratio"]))) > MAX_ABS_LOG_OR for row in fitted_rows):
        raise NudgeAnalysisError("Validation failed: output contains |ln(OR)| above threshold")
    finite_p = [float(row["p_value"]) for row in fitted_rows if row.get("p_value") is not None]
    if any(p < MIN_VALID_P_VALUE for p in finite_p):
        raise NudgeAnalysisError("Validation failed: output contains p-value below threshold")
    if any(
        row.get("fitted_probability_min") is not None
        and row.get("fitted_probability_max") is not None
        and (
            float(row["fitted_probability_min"]) <= PROBABILITY_EPSILON
            or float(row["fitted_probability_max"]) >= 1 - PROBABILITY_EPSILON
        )
        for row in fitted_rows
    ):
        raise NudgeAnalysisError("Validation failed: fitted probability reached boundary")

    metrics["plain_vs_firth_sanity"] = sanity
    metrics["max_abs_ln_or"] = safe_float(max((abs(math.log(float(row["odds_ratio"]))) for row in fitted_rows), default=0.0))
    metrics["min_model_p_value"] = safe_float(min(finite_p) if finite_p else None)
    return metrics


def add_output_metrics(rows: list[dict], metrics: dict) -> None:
    """Add status and CI-method counts to the manifest metrics."""
    out = pd.DataFrame(rows)
    metrics["status_counts"] = {str(k): int(v) for k, v in out["status"].value_counts(dropna=False).to_dict().items()}
    if "ci_method" in out.columns:
        metrics["ci_method_counts"] = {str(k): int(v) for k, v in out["ci_method"].dropna().value_counts().to_dict().items()}
    metrics["total_firth_fit_rows"] = int((out["status"] == "ok").sum())
    metrics["total_firth_non_converged_or_unstable_rows"] = int((out["status"] == "separation_unstable").sum())


def write_outputs(
    *,
    rows: list[dict],
    output_csv: Path,
    output_manifest: Path,
    command: str,
    generated: str,
    tagged_input: Path,
    sentiment_input: Path,
    metrics: dict,
) -> dict:
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    out = pd.DataFrame(rows)
    # Enforce the project's aggregate-only guard before writing any file that
    # could later feed the dashboard or a paper table.
    assert_safe_aggregate(out, str(output_csv))
    out.to_csv(output_csv, index=False)

    versions = dependency_versions()
    manifest = research_manifest(
        kind="nudge_aspect_opportunity_analysis",
        command=command,
        generated_at=generated,
        filters={
            "primary_languages": list(PRIMARY_LANGUAGES),
            "secondary_languages": list(SECONDARY_LANGUAGES),
            "inbound_languages": list(INBOUND_LANGUAGES),
            "city_to_prefecture": CITY_TO_PREFECTURE,
            "low_rating_definition": "review_rating <= 3",
            "secondary_negative_definition": "sentiment_category == 'negative'",
            "min_pooled_positive_for_ranking": MIN_POOLED_POSITIVE,
        },
        inputs=[
            file_record(tagged_input, "aspect_tagged_multilingual_reviews", required=True),
            file_record(sentiment_input, "jp_en_fukui_row_level_sentiment_for_secondary_join", required=True),
        ],
        outputs=[
            file_record(output_csv, "aggregate_nudge_aspect_opportunity_map", required=True),
        ],
        metrics=metrics,
        caveats=[
            "Exploratory and hypothesis-generating; not causal.",
            "Opportunity scores rank candidate follow-up experiments, not intervention effectiveness.",
            "Primary estimates use low star rating and Firth penalized logistic regression adjusted for text length, language, and prefecture when multiple levels are present.",
            "POI-level clustering not modeled under Firth; row-level estimates may understate uncertainty from POI nesting; exploratory ranking only.",
            "Secondary sentiment checks are within-language only and do not compare sentiment tools across languages.",
            "Small-n inbound and rare-aspect estimates may be unstable; underpowered flags identify pooled positives below 20.",
            "Opportunity scores are gated to zero unless pain point aspects are FDR-significant and harmful (odds ratio above 1).",
            "Firth implementation is hand-coded in this repository; no external Firth package is used.",
            "Language groups describe review language, not reviewer nationality.",
        ],
        extra={"dependency_versions": versions},
    )
    # Keep dependency versions top-level too, matching the mission checklist.
    manifest["dependency_versions"] = versions
    write_json(output_manifest, manifest)
    return manifest


def build(
    *,
    tagged_input: Path = TAGGED_INPUT,
    sentiment_input: Path = SENTIMENT_INPUT,
    output_dir: Path = OUTPUT_DIR,
    command: str | None = None,
) -> dict:
    command = command or default_command("build_nudge_opportunity_analysis.py")
    generated = generated_at_now()
    output_csv = output_dir / "aspect_opportunity_map.csv"
    output_manifest = output_dir / "aspect_opportunity_map_manifest.json"

    primary_df, primary_metrics = load_tagged(tagged_input)
    secondary_df, secondary_metrics = load_secondary_join(tagged_input, sentiment_input)

    rows: list[dict] = []
    metrics = {**primary_metrics, **secondary_metrics}

    method_a_rows, method_a_metrics = build_method_a_rows(primary_df, command, generated)
    rows.extend(method_a_rows)
    metrics.update(method_a_metrics)

    secondary_rows, secondary_model_metrics = build_secondary_rows(secondary_df, command, generated)
    rows.extend(secondary_rows)
    metrics.update(secondary_model_metrics)

    method_c_rows, method_c_metrics = build_method_c_rows(primary_df, command, generated)
    rows.extend(method_c_rows)
    metrics.update(method_c_metrics)

    metrics.update(run_validation_checks(primary_df, rows))
    add_output_metrics(rows, metrics)
    metrics["total_output_rows"] = int(len(rows))
    metrics["total_models_fit"] = int(sum(value for key, value in metrics.items() if key.endswith("_models_fit")))
    metrics["total_models_skipped"] = int(sum(value for key, value in metrics.items() if key.endswith("_models_skipped")))

    return write_outputs(
        rows=rows,
        output_csv=output_csv,
        output_manifest=output_manifest,
        command=command,
        generated=generated,
        tagged_input=tagged_input,
        sentiment_input=sentiment_input,
        metrics=metrics,
    )


def main() -> None:
    args = parse_args()
    try:
        manifest = build(
            tagged_input=args.tagged_input,
            sentiment_input=args.sentiment_input,
            output_dir=args.output_dir,
        )
    except Exception as error:
        raise SystemExit(str(error)) from error
    print(f"wrote {OUTPUT_CSV}")
    print(f"wrote {OUTPUT_MANIFEST}")
    print(
        "models fit/skipped: "
        f"{manifest['metrics']['total_models_fit']}/{manifest['metrics']['total_models_skipped']}"
    )
    print(
        "firth validation: "
        f"max_abs_ln_or={manifest['metrics']['max_abs_ln_or']}, "
        f"min_p={manifest['metrics']['min_model_p_value']}, "
        f"synthetic_zero_cell_or={manifest['metrics']['synthetic_zero_cell_firth_or']}"
    )
    for aspect, values in manifest["metrics"]["plain_vs_firth_sanity"].items():
        print(
            "sanity plain_vs_firth: "
            f"{aspect} plain={values['plain_logit_or']} firth={values['firth_or']}"
        )


if __name__ == "__main__":
    main()
