#!/usr/bin/env python3
"""
H3: Reviewed Evidence Prevalence, JP vs EN Google Reviews.

Research question:
    Do English-language and Japanese-language Fukui Google reviews differ in
    reviewed keyword evidence prevalence for friction, enjoyment,
    recommendation, and positive sentiment?

Null hypothesis:
    Reviewed evidence prevalence for each evidence family is equal across
    English-language and Japanese-language reviews.

Alternative hypothesis:
    At least one evidence family has different prevalence by review language
    group.

Unit of analysis:
    One Fukui Google review row from the ignored scored-review audit file.

Valid interpretation:
    Results compare audited keyword evidence flags. They support claims about
    what language groups mention, not direct motives or satisfaction.

Limitations:
    Keyword matching can miss synonyms, substring matches can be false
    positives, text length affects match opportunity, and language codebooks may
    differ in coverage.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.hypothesis_test_common import (
    COMMON_CAVEATS,
    DEFAULT_GROUPS,
    benjamini_hochberg,
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

EVIDENCE_COLUMNS = [
    ("friction", "any_friction"),
    ("enjoyment", "any_enjoyment_evidence"),
    ("recommendation", "any_recommendation_evidence"),
    ("positive_sentiment", "any_positive_evidence"),
]
REQUIRED_COLUMNS = {"language_group", "text_length_chars"} | {column for _, column in EVIDENCE_COLUMNS}
INPUT_PATH = Path(__file__).resolve().parent.parent / "output" / "sentiment_row_level" / "google_reviews_fukui_japanese-english.csv"
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "output" / "hypothesis_tests"
OUTPUT_CSV = OUTPUT_DIR / "h3_reviewed_evidence_jp_en.csv"
OUTPUT_MANIFEST = OUTPUT_DIR / "h3_reviewed_evidence_jp_en_manifest.json"

H3_CAVEATS = COMMON_CAVEATS + [
    "Reviewed keyword evidence does not prove motive or satisfaction.",
    "Longer reviews have more opportunity to match keyword evidence.",
    "Language-specific codebook coverage may affect prevalence.",
]


def _bool_series(series: pd.Series) -> pd.Series:
    if series.dtype == bool:
        return series.fillna(False)
    return series.fillna(False).astype(str).str.lower().isin({"true", "1", "yes", "y"})


def _text_length_summary(df: pd.DataFrame) -> dict[str, dict[str, float | int | None]]:
    out = {}
    for language in DEFAULT_GROUPS:
        values = pd.to_numeric(
            df.loc[df["language_group"] == language, "text_length_chars"],
            errors="coerce",
        ).dropna()
        out[language] = {
            "n": int(values.size),
            "mean": safe_float(values.mean()),
            "median": safe_float(values.median()),
            "sd": safe_float(values.std(ddof=1)) if values.size >= 2 else None,
        }
    return out


def _evidence_table(df: pd.DataFrame, column: str) -> pd.DataFrame:
    work = pd.DataFrame({
        "language_group": df["language_group"],
        "present": _bool_series(df[column]),
    })
    table = pd.crosstab(work["language_group"], work["present"]).reindex(
        index=list(DEFAULT_GROUPS), columns=[False, True], fill_value=0
    )
    return table


def _risk_difference_pct(table: pd.DataFrame) -> float | None:
    english_total = float(table.loc["english"].sum())
    japanese_total = float(table.loc["japanese"].sum())
    if english_total == 0 or japanese_total == 0:
        return None
    english_rate = table.loc["english", True] / english_total
    japanese_rate = table.loc["japanese", True] / japanese_total
    return float((english_rate - japanese_rate) * 100)


def _test_evidence(table: pd.DataFrame) -> tuple[str, float | None, float | None, float | None, float, dict]:
    chi2, chi_p, dof, expected = stats.chi2_contingency(table)
    min_expected = float(np.min(expected))
    details = {
        "observed": table.to_dict(),
        "expected": np.round(expected, 6).tolist(),
        "min_expected_count": min_expected,
    }
    if min_expected < 5:
        odds_ratio, fisher_p = stats.fisher_exact(table, alternative="two-sided")
        details["reason_for_fisher"] = "minimum expected count below 5"
        return "fisher_exact_evidence_prevalence", safe_float(odds_ratio), safe_float(fisher_p), safe_float(odds_ratio), min_expected, details
    return "chi_square_evidence_prevalence", safe_float(chi2), safe_float(chi_p), None, min_expected, details


def build_h3_reviewed_evidence(
    input_path: Path = INPUT_PATH,
    output_dir: Path = OUTPUT_DIR,
    command: str | None = None,
) -> dict:
    df = load_scored_reviews(input_path, REQUIRED_COLUMNS)
    command = command or default_command("test_h3_reviewed_evidence_jp_en.py")
    generated_at = generated_at_now()
    denominators = group_denominators(df)
    source_hash = sha256_file(input_path)
    text_lengths = _text_length_summary(df)

    rows = []
    p_values: list[float | None] = []
    for family, column in EVIDENCE_COLUMNS:
        table = _evidence_table(df, column)
        english_n = int(table.loc["english"].sum())
        japanese_n = int(table.loc["japanese"].sum())
        english_present = int(table.loc["english", True])
        japanese_present = int(table.loc["japanese", True])
        if english_n == 0 or japanese_n == 0:
            test_name = "evidence_prevalence"
            status = "skipped"
            statistic = None
            p_value = None
            odds_ratio = None
            min_expected = None
            details = {"reason": "missing denominator in one or both language groups"}
        else:
            test_name, statistic, p_value, odds_ratio, min_expected, details = _test_evidence(table)
            status = "ok"
        p_values.append(p_value)
        rows.append({
            "hypothesis": "H3",
            "analysis_type": "evidence_family_test",
            "evidence_family": family,
            "evidence_column": column,
            "test_name": test_name,
            "status": status,
            "statistic": statistic,
            "p_value": p_value,
            "p_value_bh_fdr": None,
            "odds_ratio": odds_ratio,
            "risk_difference_pct": _risk_difference_pct(table),
            "english_n": english_n,
            "english_present_count": english_present,
            "english_present_pct": round(english_present / english_n, 6) if english_n else None,
            "japanese_n": japanese_n,
            "japanese_present_count": japanese_present,
            "japanese_present_pct": round(japanese_present / japanese_n, 6) if japanese_n else None,
            "min_expected_count": min_expected,
            "sparse_cell_warning": bool(min_expected is not None and min_expected < 5),
            "text_length_summary_json": json.dumps(text_lengths, ensure_ascii=False),
            "source_input_path": str(input_path),
            "source_input_sha256": source_hash,
            "command": command,
            "generated_at": generated_at,
            "caveat": "; ".join(H3_CAVEATS),
            "details_json": json.dumps(details, ensure_ascii=False),
        })

    adjusted = benjamini_hochberg(p_values)
    for row, p_adjusted in zip(rows, adjusted):
        row["p_value_bh_fdr"] = p_adjusted

    rows.append({
        "hypothesis": "H3",
        "analysis_type": "diagnostic",
        "evidence_family": "all",
        "evidence_column": "text_length_chars",
        "test_name": "text_length_summary_by_language_group",
        "status": "ok",
        "statistic": None,
        "p_value": None,
        "p_value_bh_fdr": None,
        "odds_ratio": None,
        "risk_difference_pct": None,
        "english_n": denominators["english"],
        "english_present_count": None,
        "english_present_pct": None,
        "japanese_n": denominators["japanese"],
        "japanese_present_count": None,
        "japanese_present_pct": None,
        "min_expected_count": None,
        "sparse_cell_warning": None,
        "text_length_summary_json": json.dumps(text_lengths, ensure_ascii=False),
        "source_input_path": str(input_path),
        "source_input_sha256": source_hash,
        "command": command,
        "generated_at": generated_at,
        "caveat": "; ".join(H3_CAVEATS),
        "details_json": json.dumps({
            "interpretation": "Longer reviews have more opportunity to contain any reviewed evidence term."
        }),
    })

    out = pd.DataFrame(rows)
    output_csv = output_dir / OUTPUT_CSV.name
    output_manifest = output_dir / OUTPUT_MANIFEST.name
    write_csv(out, output_csv)
    manifest = write_manifest(
        kind="hypothesis_h3_reviewed_evidence_jp_en",
        command=command,
        generated=generated_at,
        input_path=input_path,
        output_csv=output_csv,
        manifest_path=output_manifest,
        metrics={
            "hypothesis": "H3",
            "primary_unit": "one Fukui Google review row",
            "denominators": denominators,
            "evidence_columns": [column for _, column in EVIDENCE_COLUMNS],
            "multiple_testing": "Benjamini-Hochberg FDR across four evidence-family p-values.",
            "text_length_summary": text_lengths,
        },
        caveats=H3_CAVEATS,
    )
    return {"csv": str(output_csv), "manifest": str(output_manifest), "rows": len(out), "provenance": manifest}


def main() -> None:
    args = parse_common_args(__doc__ or "Run H3 JP/EN reviewed-evidence tests.")
    report = build_h3_reviewed_evidence(input_path=args.input, output_dir=args.output_dir)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
