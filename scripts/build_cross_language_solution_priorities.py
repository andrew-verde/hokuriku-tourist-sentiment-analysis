#!/usr/bin/env python3
"""Build provenance-locked cross-language nudge priorities.

Outputs stay aggregate-only. Evidence remains source-specific; sentiment scores,
prevalence, and denominators are never pooled across platforms or tools.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.provenance import (  # noqa: E402
    assert_no_forbidden_columns,
    file_record,
    research_manifest,
    repo_relative,
    sha256_file,
    utc_now_iso,
    write_json,
)


ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config" / "cross_language_solution_mapping.yaml"
ASPECT_INPUT = ROOT / "output" / "nudge_analysis" / "aspect_opportunity_map.csv"
H3_INPUT = ROOT / "output" / "hypothesis_tests" / "h3_reviewed_evidence_jp_en.csv"
CN_FRICTION_INPUT = (
    ROOT
    / "output"
    / "chinese_social_media_analysis"
    / "chinese_vs_review_language_friction_comparison.csv"
)
CN_ENJOYMENT_INPUT = (
    ROOT
    / "output"
    / "chinese_social_media_analysis"
    / "chinese_enjoyment_evidence_by_city_platform.csv"
)
CN_WITHIN_INPUT = (
    ROOT / "output" / "within_language_sentiment" / "cn_within_source_sentiment_drivers.csv"
)
OUTPUT_DIR = ROOT / "output" / "nudge_analysis"
PRIORITY_OUTPUT = OUTPUT_DIR / "cross_language_solution_priorities.csv"
EVIDENCE_OUTPUT = OUTPUT_DIR / "cross_language_solution_evidence.csv"
MANIFEST_OUTPUT = OUTPUT_DIR / "cross_language_solution_priorities_manifest.json"
COMMAND = "scripts/build_cross_language_solution_priorities.py"
LANGUAGES = ("english", "japanese", "chinese")


class SolutionPriorityError(RuntimeError):
    """Raised when required aggregate evidence is missing or invalid."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=CONFIG)
    parser.add_argument("--aspect-input", type=Path, default=ASPECT_INPUT)
    parser.add_argument("--h3-input", type=Path, default=H3_INPUT)
    parser.add_argument("--cn-friction-input", type=Path, default=CN_FRICTION_INPUT)
    parser.add_argument("--cn-enjoyment-input", type=Path, default=CN_ENJOYMENT_INPUT)
    parser.add_argument("--cn-within-input", type=Path, default=CN_WITHIN_INPUT)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    return parser.parse_args()


def _load_csv(path: Path, required: set[str]) -> pd.DataFrame:
    if not path.exists():
        raise SolutionPriorityError(f"Required input missing: {path}")
    data = pd.read_csv(path)
    missing = sorted(required - set(data.columns))
    if missing:
        raise SolutionPriorityError(f"Required columns missing from {path}: {', '.join(missing)}")
    return data


def _one(data: pd.DataFrame, mask: pd.Series, description: str) -> pd.Series:
    rows = data.loc[mask]
    if len(rows) != 1:
        raise SolutionPriorityError(f"Expected exactly one row for {description}; found {len(rows)}")
    return rows.iloc[0]


def _evidence_row(
    solution_id: str,
    language: str,
    code: str,
    count: int,
    denominator: int,
    evidence_type: str,
    effect_direction: str,
    p_value_bh_fdr: float | None,
    source_path: Path,
) -> dict[str, Any]:
    if denominator <= 0 or count < 0 or count > denominator:
        raise SolutionPriorityError(
            f"Invalid aggregate count for {solution_id}/{language}/{code}: {count}/{denominator}"
        )
    p_value = None if p_value_bh_fdr is None or pd.isna(p_value_bh_fdr) else float(p_value_bh_fdr)
    return {
        "solution_id": solution_id,
        "language_source_group": language,
        "evidence_code": code,
        "count": int(count),
        "denominator": int(denominator),
        "prevalence": float(count / denominator),
        "evidence_type": evidence_type,
        "effect_direction": effect_direction,
        "p_value_bh_fdr": p_value,
        "fdr_significant": bool(p_value is not None and p_value < 0.05),
        "source_path": repo_relative(source_path),
        "source_sha256": sha256_file(source_path),
    }


def _review_aspect_evidence(
    solution_id: str, code: str, language: str, aspects: pd.DataFrame, source_path: Path
) -> dict[str, Any]:
    row = _one(
        aspects,
        (aspects["analysis"] == "A_primary")
        & (aspects["segment"] == language)
        & (aspects["aspect"] == code),
        f"A_primary/{language}/{code}",
    )
    return _evidence_row(
        solution_id,
        language,
        code,
        int(row["n_positive"]),
        int(row["n"]),
        "reviewed_aspect_prevalence",
        "descriptive",
        None,
        source_path,
    )


def _cn_friction_evidence(
    solution_id: str, code: str, cn_friction: pd.DataFrame, source_path: Path
) -> dict[str, Any]:
    row = _one(
        cn_friction,
        (cn_friction["city"] == "Fukui")
        & (cn_friction["friction_code"] == code)
        & (cn_friction["comparison_group"] == "google_english")
        & (cn_friction["chinese_subset"] == "all_posts"),
        f"Fukui/all_posts/{code}",
    )
    return _evidence_row(
        solution_id,
        "chinese",
        code,
        int(row["chinese_count"]),
        int(row["chinese_n"]),
        "reviewed_xhs_friction_prevalence",
        "descriptive",
        None,
        source_path,
    )


def _localized_evidence(
    solution_id: str,
    language: str,
    h3: pd.DataFrame,
    cn_enjoyment: pd.DataFrame,
    h3_source_path: Path,
    cn_enjoyment_source_path: Path,
) -> dict[str, Any]:
    if language in {"english", "japanese"}:
        row = _one(
            h3,
            (h3["analysis_type"] == "evidence_family_test")
            & (h3["evidence_family"] == "enjoyment")
            & (h3["status"] == "ok"),
            "H3 enjoyment evidence family",
        )
        return _evidence_row(
            solution_id,
            language,
            "any_enjoyment_evidence",
            int(row[f"{language}_present_count"]),
            int(row[f"{language}_n"]),
            "reviewed_enjoyment_prevalence",
            "descriptive",
            None,
            h3_source_path,
        )
    row = _one(
        cn_enjoyment,
        (cn_enjoyment["city"] == "Fukui")
        & (cn_enjoyment["source_platform"] == "xiaohongshu")
        & (cn_enjoyment["code"] == "positive_sentiment"),
        "Fukui/xiaohongshu/positive_sentiment",
    )
    return _evidence_row(
        solution_id,
        language,
        "positive_sentiment",
        int(row["count"]),
        int(row["denominator_posts"]),
        "reviewed_xhs_positive_evidence_prevalence",
        "descriptive",
        None,
        cn_enjoyment_source_path,
    )


def _confirmatory(
    solution: dict[str, Any], aspects: pd.DataFrame, cn_within: pd.DataFrame
) -> tuple[list[str], float | None, bool]:
    evidence = solution["evidence"]
    significant_codes: list[str] = []
    p_values: list[float] = []
    harmful = False
    for code in evidence.get("review_aspects", []):
        row = _one(
            aspects,
            (aspects["analysis"] == "A_primary")
            & (aspects["segment"] == "pooled")
            & (aspects["aspect"] == code),
            f"A_primary/pooled/{code}",
        )
        if bool(row["fdr_significant"]) and float(row["odds_ratio"]) > 1:
            significant_codes.append(code)
            p_values.append(float(row["p_value_bh_fdr"]))
            harmful = True
    for code in evidence.get("chinese_topic_codes", []):
        row = _one(
            cn_within,
            (cn_within["predictor"] == code)
            & (cn_within["outcome"] == "sentiment_category=positive")
            & (cn_within["status"] == "ok"),
            f"Chinese positive sentiment/{code}",
        )
        if float(row["p_value_bh_fdr"]) < 0.05 and float(row["effect_size"]) > 0:
            significant_codes.append(code)
            p_values.append(float(row["p_value_bh_fdr"]))
    return significant_codes, min(p_values) if p_values else None, harmful


def build_cross_language_solution_priorities(
    config_path: Path = CONFIG,
    aspect_path: Path = ASPECT_INPUT,
    h3_path: Path = H3_INPUT,
    cn_friction_path: Path = CN_FRICTION_INPUT,
    cn_enjoyment_path: Path = CN_ENJOYMENT_INPUT,
    cn_within_path: Path = CN_WITHIN_INPUT,
    output_dir: Path = OUTPUT_DIR,
    command: str = COMMAND,
) -> dict[str, Path]:
    if not config_path.exists():
        raise SolutionPriorityError(f"Required config missing: {config_path}")
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    solutions = config.get("solutions", [])
    if not solutions:
        raise SolutionPriorityError("Solution mapping contains no solutions")

    aspects = _load_csv(
        aspect_path,
        {
            "analysis",
            "segment",
            "aspect",
            "n",
            "n_positive",
            "odds_ratio",
            "p_value_bh_fdr",
            "fdr_significant",
        },
    )
    h3 = _load_csv(
        h3_path,
        {
            "analysis_type",
            "evidence_family",
            "status",
            "english_n",
            "english_present_count",
            "japanese_n",
            "japanese_present_count",
        },
    )
    cn_friction = _load_csv(
        cn_friction_path,
        {
            "city",
            "friction_code",
            "comparison_group",
            "chinese_subset",
            "chinese_count",
            "chinese_n",
        },
    )
    cn_enjoyment = _load_csv(
        cn_enjoyment_path,
        {"city", "source_platform", "code", "count", "denominator_posts"},
    )
    cn_within = _load_csv(
        cn_within_path,
        {"predictor", "outcome", "status", "effect_size", "p_value_bh_fdr"},
    )

    evidence_rows: list[dict[str, Any]] = []
    priority_rows: list[dict[str, Any]] = []
    generated_at = utc_now_iso()

    for solution in solutions:
        solution_id = str(solution["solution_id"])
        mapped = solution["evidence"]
        if "review_family" in mapped:
            selected = [
                _localized_evidence(
                    solution_id,
                    language,
                    h3,
                    cn_enjoyment,
                    h3_path,
                    cn_enjoyment_path,
                )
                for language in LANGUAGES
            ]
        else:
            review_code = str(mapped["primary_review_aspect"])
            cn_code = str(mapped["primary_chinese_code"])
            selected = [
                _review_aspect_evidence(
                    solution_id, review_code, "english", aspects, aspect_path
                ),
                _review_aspect_evidence(
                    solution_id, review_code, "japanese", aspects, aspect_path
                ),
                _cn_friction_evidence(
                    solution_id, cn_code, cn_friction, cn_friction_path
                ),
            ]
        evidence_rows.extend(selected)
        language_support = {
            row["language_source_group"] for row in selected if int(row["count"]) > 0
        }
        significant_codes, fdr_min, harmful = _confirmatory(solution, aspects, cn_within)
        impact_tier = "High" if len(language_support) == 3 and significant_codes else "Medium"
        support_rule = (
            "all_three"
            if len(language_support) == 3
            else ("two_of_three_fallback" if len(language_support) == 2 else "excluded")
        )
        primary = {row["language_source_group"]: row for row in selected}
        priority_rows.append(
            {
                "solution_id": solution_id,
                "solution_label_en": solution["solution_label_en"],
                "solution_label_ja": solution["solution_label_ja"],
                "nudge_type": solution["nudge_type"],
                "impact_tier": impact_tier,
                "impact_order": 1 if impact_tier == "High" else 2,
                "ease_tier": solution["ease_tier"],
                "ease_order": int(solution["ease_order"]),
                "evidence_breadth": len(selected),
                "language_support_count": len(language_support),
                "support_rule": support_rule,
                "english_codes": primary["english"]["evidence_code"],
                "english_count": primary["english"]["count"],
                "english_n": primary["english"]["denominator"],
                "japanese_codes": primary["japanese"]["evidence_code"],
                "japanese_count": primary["japanese"]["count"],
                "japanese_n": primary["japanese"]["denominator"],
                "chinese_codes": primary["chinese"]["evidence_code"],
                "chinese_count": primary["chinese"]["count"],
                "chinese_n": primary["chinese"]["denominator"],
                "confirmatory_aspects": ";".join(significant_codes),
                "confirmatory_fdr_min": fdr_min,
                "harmful_rating_association": harmful,
                "evidence_summary_en": solution["evidence_summary_en"],
                "evidence_summary_ja": solution["evidence_summary_ja"],
                "experiment_hypothesis_en": solution["experiment_hypothesis_en"],
                "experiment_hypothesis_ja": solution["experiment_hypothesis_ja"],
                "intervention_en": solution["intervention_en"],
                "intervention_ja": solution["intervention_ja"],
                "randomization_unit": solution["randomization_unit"],
                "primary_outcomes": solution["primary_outcomes"],
                "secondary_outcomes": solution["secondary_outcomes"],
                "evidence_caveat": (
                    "Source-specific aggregate evidence only. Chinese-language XHS posts have no "
                    "star rating. SnowNLP associations are within XHS only. No cross-tool score "
                    "comparison or causal claim. Chinese friction/topic codes are keyword "
                    "topic-presence (a topic was mentioned), not polarity or severity, so where "
                    "the impact tier relies on Chinese language-support it is directional, not "
                    "confirmatory."
                ),
                "command": command,
                "generated_at": generated_at,
            }
        )

    candidates = [row for row in priority_rows if row["support_rule"] == "all_three"]
    fallback_used = False
    if not candidates:
        candidates = [row for row in priority_rows if row["support_rule"] == "two_of_three_fallback"]
        fallback_used = True
    if not candidates:
        raise SolutionPriorityError("No solution has support from at least two language/source groups")
    priorities = pd.DataFrame(candidates).sort_values(
        ["impact_order", "ease_order", "evidence_breadth", "solution_id"],
        ascending=[True, True, False, True],
        kind="stable",
    )
    priorities.insert(0, "rank", range(1, len(priorities) + 1))
    evidence = pd.DataFrame(evidence_rows)
    assert_no_forbidden_columns(priorities.columns, context="solution priority output")
    assert_no_forbidden_columns(evidence.columns, context="solution evidence output")

    output_dir.mkdir(parents=True, exist_ok=True)
    priority_output = output_dir / PRIORITY_OUTPUT.name
    evidence_output = output_dir / EVIDENCE_OUTPUT.name
    manifest_output = output_dir / MANIFEST_OUTPUT.name
    priorities.to_csv(priority_output, index=False)
    evidence.to_csv(evidence_output, index=False)

    inputs = [
        file_record(path, role, required=True)
        for path, role in [
            (config_path, "solution mapping config"),
            (aspect_path, "review aspect opportunity aggregates"),
            (h3_path, "reviewed JP-EN evidence aggregates"),
            (cn_friction_path, "reviewed Chinese friction aggregates"),
            (cn_enjoyment_path, "reviewed Chinese enjoyment aggregates"),
            (cn_within_path, "within-XHS association aggregates"),
        ]
    ]
    manifest = research_manifest(
        kind="cross_language_solution_priorities",
        command=command,
        inputs=inputs,
        outputs=[
            file_record(priority_output, "ranked aggregate priorities", required=True),
            file_record(evidence_output, "source-specific aggregate evidence", required=True),
        ],
        filters={
            "prefecture": "Fukui",
            "groups": list(LANGUAGES),
            "all_three_required_when_available": True,
            "two_of_three_fallback_only_when_no_all_three": True,
        },
        metrics={
            "candidate_solutions": len(priority_rows),
            "ranked_solutions": len(priorities),
            "evidence_rows": len(evidence),
            "fallback_used": fallback_used,
            "ranked_solution_ids": priorities["solution_id"].tolist(),
        },
        caveats=[
            "Language/source groups do not imply nationality.",
            "Counts and denominators remain source-specific and are not pooled.",
            "VADER, oseti, and SnowNLP raw scores are not compared across languages.",
            "Chinese-language XHS posts have no star-rating outcome.",
            "Associations rank hypotheses for future experiments and are not causal effects.",
        ],
        extra={
            "ranking_rule": [
                "impact tier",
                "implementation ease",
                "evidence breadth",
                "stable solution ID",
            ],
            "impact_rule": {
                "High": "all-three support plus FDR-supported harmful-rating or within-XHS positive association",
                "Medium": "all-three descriptive support without qualifying FDR association",
            },
            "mapping_schema_version": config.get("schema_version"),
        },
        generated_at=generated_at,
    )
    write_json(manifest_output, manifest)
    return {
        "priorities": priority_output,
        "evidence": evidence_output,
        "manifest": manifest_output,
    }


def main() -> None:
    args = parse_args()
    build_cross_language_solution_priorities(
        config_path=args.config,
        aspect_path=args.aspect_input,
        h3_path=args.h3_input,
        cn_friction_path=args.cn_friction_input,
        cn_enjoyment_path=args.cn_enjoyment_input,
        cn_within_path=args.cn_within_input,
        output_dir=args.output_dir,
    )


if __name__ == "__main__":
    main()
