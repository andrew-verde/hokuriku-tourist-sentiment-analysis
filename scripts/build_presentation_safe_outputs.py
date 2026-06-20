#!/usr/bin/env python3
"""
Build presentation-safe aggregate tables and captions.

This stage consumes tracked JP-EN aggregate sentiment outputs plus the ignored
scored-review audit file named in the sentiment manifest. It reads only safe
metadata from that audit file to aggregate date ranges and POI-category mix; it
does not write row-level text, POI IDs, author fields, URLs, screenshots, or
manual capture files.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.provenance import (
    ProvenanceError,
    assert_no_forbidden_columns,
    file_record,
    research_manifest,
    sha256_file,
    write_json,
)
from src.utils.logger import setup_logger

logger = setup_logger(__name__)

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SENTIMENT_SUMMARY_PATH = (
    ROOT / "output" / "sentiment_aggregates" / "source_group_sentiment_summary.csv"
)
DEFAULT_SENTIMENT_TESTS_PATH = (
    ROOT / "output" / "sentiment_aggregates" / "source_group_sentiment_tests.csv"
)
DEFAULT_SENTIMENT_MANIFEST_PATH = ROOT / "output" / "sentiment_aggregates" / "sentiment_manifest.json"
DEFAULT_OUTPUT_DIR = ROOT / "output" / "presentation_safe"

REQUIRED_SUMMARY_COLUMNS = {
    "source_group",
    "language_group",
    "prefecture_normalized",
    "city",
    "n_reviews",
    "n_scored",
    "mean_sentiment_score",
    "mean_review_rating",
    "negative_count",
    "negative_pct",
    "neutral_count",
    "neutral_pct",
    "positive_count",
    "positive_pct",
}

REQUIRED_TEST_COLUMNS = {
    "test_name",
    "comparison",
    "status",
    "statistic",
    "p_value",
    "effect",
    "details_json",
}

REQUIRED_ROW_LEVEL_COLUMNS = {
    "city",
    "prefecture_normalized",
    "poi_category",
    "review_date",
    "language_group",
}

FORBIDDEN_PRESENTATION_COLUMNS = {
    "review_text",
    "text_content",
    "review_author",
    "author",
    "author_url",
    "note_url",
    "source_url",
    "url",
    "place_id",
    "poi_id",
    "review_id",
    "source_review_id",
    "source_record_id",
}

FORBIDDEN_PRESENTATION_VALUES = {
    "dummy",
    "fixture",
    "placeholder",
    "sample",
    "synthetic",
    "test data",
    "test-only",
    "unavailable_in_aggregate_input",
}


class PresentationOutputError(RuntimeError):
    pass


class MissingInputError(PresentationOutputError):
    pass


class MissingColumnsError(PresentationOutputError):
    pass


def _require_input(path: Path, make_target: str) -> None:
    if not path.exists():
        raise MissingInputError(
            f"Required input not found: {path}\n"
            f"Generate it first with `make {make_target}`. This pipeline has no demo mode."
        )


def _read_manifest(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise PresentationOutputError(f"Invalid JSON manifest: {path}") from error


def _require_columns(df: pd.DataFrame, required: set[str], path: Path) -> None:
    missing = sorted(required - set(df.columns))
    if missing:
        raise MissingColumnsError(f"Required columns missing from {path}: {', '.join(missing)}")


def _input_hashes(manifest: dict) -> dict[str, str]:
    review_input = manifest.get("input", {})
    hashes = {
        "reviews_input_sha256": str(review_input.get("sha256", "")),
        "poi_metadata_sha256": str(review_input.get("poi_metadata_sha256", "")),
    }
    invalid = []
    for key, value in hashes.items():
        if len(value) != 64:
            invalid.append(key)
    if invalid:
        raise PresentationOutputError(
            "Sentiment manifest is missing valid input hashes: " + ", ".join(sorted(invalid))
        )
    return hashes


def _row_level_path(manifest: dict, override: Path | None) -> Path:
    if override is not None:
        return override
    row_level = manifest.get("outputs", {}).get("row_level_path")
    if not row_level:
        raise MissingInputError(
            "Sentiment manifest does not name outputs.row_level_path; rerun `make sentiment-analysis`."
        )
    return Path(row_level)


def build_metadata_summary(row_level: pd.DataFrame) -> pd.DataFrame:
    assert_no_forbidden_columns(
        row_level.columns,
        forbidden={
            "review_text",
            "text_content",
            "review_author",
            "author",
            "author_url",
            "note_url",
            "source_url",
            "url",
            "place_id",
            "source_review_id",
            "source_record_id",
        },
        context="presentation metadata input",
    )
    work = row_level[list(REQUIRED_ROW_LEVEL_COLUMNS)].copy()
    work["review_date"] = pd.to_datetime(work["review_date"], errors="coerce", utc=True)
    work["poi_category"] = work["poi_category"].fillna("unknown").astype(str)
    rows = []
    for keys, chunk in work.groupby(["prefecture_normalized", "city", "language_group"], dropna=False):
        prefecture, city, language = keys
        dated = chunk[chunk["review_date"].notna()]
        if dated.empty:
            raise PresentationOutputError(
                f"No parseable review_date values for {prefecture} {city} {language}."
            )
        mix = chunk["poi_category"].value_counts().sort_index()
        rows.append({
            "prefecture_normalized": prefecture,
            "city": city,
            "language_group": language,
            "date_range_start": dated["review_date"].min().date().isoformat(),
            "date_range_end": dated["review_date"].max().date().isoformat(),
            "review_date_parseable_count": int(chunk["review_date"].notna().sum()),
            "review_date_missing_count": int(chunk["review_date"].isna().sum()),
            "poi_mix": "; ".join(f"{category}={int(count)}" for category, count in mix.items()),
        })
    return pd.DataFrame(rows)


def _assert_no_fake_or_placeholder_values(df: pd.DataFrame, context: str) -> None:
    text = "\n".join(str(value) for value in df.to_numpy().ravel()).lower()
    blocked = sorted(value for value in FORBIDDEN_PRESENTATION_VALUES if value in text)
    if blocked:
        raise PresentationOutputError(
            f"{context} contains dummy/placeholder-like values: {', '.join(blocked)}"
        )


def build_sentiment_chart_data(
    summary: pd.DataFrame,
    metadata_summary: pd.DataFrame,
    manifest: dict,
) -> pd.DataFrame:
    assert_no_forbidden_columns(
        summary.columns,
        forbidden=FORBIDDEN_PRESENTATION_COLUMNS,
        context="presentation sentiment input",
    )
    hashes = _input_hashes(manifest)
    metadata = metadata_summary.set_index(["prefecture_normalized", "city", "language_group"])
    rows = []
    for _, row in summary.sort_values(["language_group", "city"]).iterrows():
        key = (row["prefecture_normalized"], row["city"], row["language_group"])
        if key not in metadata.index:
            raise PresentationOutputError(
                "Missing date range / POI mix metadata for "
                f"{row['prefecture_normalized']} {row['city']} {row['language_group']}"
            )
        meta = metadata.loc[key]
        denominator = int(row["n_reviews"])
        rows.append({
            "figure_id": "jp_en_library_sentiment_secondary_check",
            "prefecture": row["prefecture_normalized"],
            "city": row["city"],
            "source_group": row["source_group"],
            "language_source_group": f"{row['language_group']}-language Google reviews",
            "sentiment_tool": "VADER" if row["language_group"] == "english" else "oseti",
            "n_reviews": denominator,
            "n_scored": int(row["n_scored"]),
            "positive_pct": round(float(row["positive_pct"]) * 100, 3),
            "neutral_pct": round(float(row["neutral_pct"]) * 100, 3),
            "negative_pct": round(float(row["negative_pct"]) * 100, 3),
            "positive_count": int(row["positive_count"]),
            "neutral_count": int(row["neutral_count"]),
            "negative_count": int(row["negative_count"]),
            "mean_sentiment_score": round(float(row["mean_sentiment_score"]), 6),
            "mean_review_rating": round(float(row["mean_review_rating"]), 6),
            "date_range_start": meta["date_range_start"],
            "date_range_end": meta["date_range_end"],
            "review_date_parseable_count": int(meta["review_date_parseable_count"]),
            "review_date_missing_count": int(meta["review_date_missing_count"]),
            "poi_mix": meta["poi_mix"],
            "source_hashes": json.dumps(hashes, sort_keys=True),
            "caveat": (
                "Secondary library-score check only; reviewed JP/EN codebook evidence pending. "
                "Groups are language/source labels, not nationalities."
            ),
        })
    output = pd.DataFrame(rows)
    assert_no_forbidden_columns(
        output.columns,
        forbidden=FORBIDDEN_PRESENTATION_COLUMNS,
        context="presentation sentiment output",
    )
    _assert_no_fake_or_placeholder_values(output, "presentation sentiment output")
    return output


def build_test_summary(tests: pd.DataFrame, manifest: dict) -> pd.DataFrame:
    assert_no_forbidden_columns(
        tests.columns,
        forbidden=FORBIDDEN_PRESENTATION_COLUMNS,
        context="presentation statistical input",
    )
    rows = []
    for _, row in tests.sort_values(["test_name"]).iterrows():
        rows.append({
            "table_id": "jp_en_statistical_sensitivity",
            "test_name": row["test_name"],
            "comparison": row["comparison"],
            "status": row["status"],
            "statistic": row["statistic"],
            "p_value": row["p_value"],
            "effect": row["effect"],
            "presentation_use": (
                "descriptive_sensitivity_only"
                if str(row["status"]) == "ok"
                else "not_for_slide_claim"
            ),
            "caveat": (
                "Rows are nested in POIs and language groups are imbalanced; "
                "treat p-values as descriptive unless clustered/covariate model is justified."
            ),
            "reviews_input_sha256": _input_hashes(manifest)["reviews_input_sha256"],
        })
    output = pd.DataFrame(rows)
    assert_no_forbidden_columns(
        output.columns,
        forbidden=FORBIDDEN_PRESENTATION_COLUMNS,
        context="presentation statistical output",
    )
    _assert_no_fake_or_placeholder_values(output, "presentation statistical output")
    return output


def _write_readiness(
    path: Path,
    chart: pd.DataFrame,
    tests: pd.DataFrame,
    sentiment_manifest: dict,
    outputs: dict[str, Path],
) -> None:
    total_reviews = int(chart["n_reviews"].sum()) if not chart.empty else 0
    caveats = sentiment_manifest.get("provenance", {}).get("caveats", [])
    if not caveats:
        raise PresentationOutputError(
            "Sentiment manifest has no caveats; rerun `make sentiment-analysis` before presenting."
        )
    hashes = _input_hashes(sentiment_manifest)
    lines = [
        "# Presentation-Safe Readiness",
        "",
        "Fukui-only JP-EN Google review aggregate scaffold for slides.",
        "",
        "## Use Status",
        "",
        "- Ready for presentation as a secondary library sentiment check.",
        "- Not ready as primary JP/EN sentiment evidence until reviewed codebook evidence is promoted.",
        "- Statistical rows are descriptive sensitivity checks, not confirmatory claims.",
        "",
        "## Denominators",
        "",
        f"- Total Google review rows represented: {total_reviews}",
    ]
    for _, row in chart.iterrows():
        lines.append(
            f"- {row['language_source_group']}: n={int(row['n_reviews'])}, "
            f"scored={int(row['n_scored'])}, city={row['city']}, "
            f"dated={int(row['review_date_parseable_count'])}, "
            f"undated={int(row['review_date_missing_count'])}"
        )
    lines.extend([
        "",
        "## Provenance Required On Slides",
        "",
        f"- Reviews input SHA256: {hashes['reviews_input_sha256']}",
        f"- POI metadata SHA256: {hashes['poi_metadata_sha256']}",
        f"- Sentiment summary SHA256: {sha256_file(outputs['chart_data'])}",
        f"- Statistical summary SHA256: {sha256_file(outputs['statistical_summary'])}",
        "- Date range: derived from parseable review_date values in ignored scored-review audit file; aggregate only.",
        "- Date coverage: chart data includes parseable and missing review_date counts.",
        "- POI mix: derived from ignored scored-review audit file; aggregate category counts only.",
        "",
        "## Captions",
        "",
        "Figure JP-EN library sentiment: Fukui Google reviews only. Bars show "
        "VADER English-language and oseti Japanese-language sentiment category "
        "shares as secondary checks. Denominators and hashes are in the chart "
        "data; language labels are not nationality claims.",
        "",
        "Table statistical sensitivity: Review-row, POI-level, and cluster "
        "bootstrap checks summarize robustness. Because review rows are nested "
        "within POIs and group sizes are imbalanced, use as descriptive "
        "sensitivity only.",
        "",
        "## Caveats From Upstream Manifest",
        "",
    ])
    lines.extend(f"- {caveat}" for caveat in caveats)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_presentation_safe_outputs(
    sentiment_summary_path: Path = DEFAULT_SENTIMENT_SUMMARY_PATH,
    sentiment_tests_path: Path = DEFAULT_SENTIMENT_TESTS_PATH,
    sentiment_manifest_path: Path = DEFAULT_SENTIMENT_MANIFEST_PATH,
    row_level_path: Path | None = None,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    command: str | None = None,
) -> dict:
    _require_input(sentiment_summary_path, "sentiment-analysis")
    _require_input(sentiment_tests_path, "sentiment-analysis")
    _require_input(sentiment_manifest_path, "sentiment-analysis")

    summary = pd.read_csv(sentiment_summary_path)
    tests = pd.read_csv(sentiment_tests_path)
    manifest = _read_manifest(sentiment_manifest_path)
    audit_path = _row_level_path(manifest, row_level_path)
    _require_input(audit_path, "sentiment-analysis")
    row_level = pd.read_csv(audit_path)
    _require_columns(summary, REQUIRED_SUMMARY_COLUMNS, sentiment_summary_path)
    _require_columns(tests, REQUIRED_TEST_COLUMNS, sentiment_tests_path)
    _require_columns(row_level, REQUIRED_ROW_LEVEL_COLUMNS, audit_path)

    if set(summary["prefecture_normalized"].dropna().astype(str)) != {"Fukui"}:
        raise PresentationOutputError("Presentation-safe defaults require Fukui-only aggregate inputs.")
    if set(summary["language_group"].dropna().astype(str)) - {"english", "japanese"}:
        raise PresentationOutputError("Presentation-safe JP-EN output accepts only English/Japanese review groups.")

    output_dir.mkdir(parents=True, exist_ok=True)
    chart_path = output_dir / "jp_en_library_sentiment_chart_data.csv"
    test_summary_path = output_dir / "jp_en_statistical_sensitivity_summary.csv"
    readiness_path = output_dir / "presentation_readiness.md"
    manifest_path = output_dir / "presentation_manifest.json"

    metadata_summary = build_metadata_summary(row_level)
    chart = build_sentiment_chart_data(summary, metadata_summary, manifest)
    test_summary = build_test_summary(tests, manifest)
    chart.to_csv(chart_path, index=False)
    test_summary.to_csv(test_summary_path, index=False)

    outputs = {
        "chart_data": chart_path,
        "statistical_summary": test_summary_path,
        "readiness": readiness_path,
    }
    _write_readiness(readiness_path, chart, test_summary, manifest, outputs)

    report = research_manifest(
        kind="presentation_safe_jp_en_sentiment",
        command=command or " ".join(sys.argv),
        inputs=[
            file_record(sentiment_summary_path, "tracked_aggregate_summary", required=True),
            file_record(sentiment_tests_path, "tracked_statistical_tests", required=True),
            file_record(sentiment_manifest_path, "tracked_sentiment_manifest", required=True),
            file_record(audit_path, "ignored_scored_review_audit_file", required=True),
        ],
        outputs=[
            file_record(chart_path, "presentation_chart_data", required=True),
            file_record(test_summary_path, "presentation_statistical_summary", required=True),
            file_record(readiness_path, "presentation_readiness_markdown", required=True),
        ],
        filters={"prefecture": "Fukui", "groups": ["english", "japanese"]},
        metrics={
            "review_rows_represented": int(chart["n_reviews"].sum()) if not chart.empty else 0,
            "codebook_evidence_status": manifest.get("codebook_evidence_status", "unknown"),
            "date_range_status": "derived_from_scored_review_audit_file",
            "poi_mix_status": "derived_from_scored_review_audit_file",
        },
        caveats=[
            "Presentation files are aggregate-only and must not be used as row-level evidence.",
            "Library sentiment is a secondary check until reviewed JP/EN codebook evidence is promoted.",
            "Language/source groups are not nationality groups.",
            "Date range and POI mix are aggregate metadata derived from the ignored scored-review audit file.",
        ],
        extra={"source_hashes": _input_hashes(manifest)},
    )
    write_json(manifest_path, report)
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sentiment-summary-path", type=Path, default=DEFAULT_SENTIMENT_SUMMARY_PATH)
    parser.add_argument("--sentiment-tests-path", type=Path, default=DEFAULT_SENTIMENT_TESTS_PATH)
    parser.add_argument("--sentiment-manifest-path", type=Path, default=DEFAULT_SENTIMENT_MANIFEST_PATH)
    parser.add_argument("--row-level-path", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        report = build_presentation_safe_outputs(
            sentiment_summary_path=args.sentiment_summary_path,
            sentiment_tests_path=args.sentiment_tests_path,
            sentiment_manifest_path=args.sentiment_manifest_path,
            row_level_path=args.row_level_path,
            output_dir=args.output_dir,
        )
    except (PresentationOutputError, ProvenanceError) as error:
        logger.error(str(error))
        return 1
    logger.info("Presentation-safe rows represented: %s", report["metrics"]["review_rows_represented"])
    logger.info("Output written: %s", args.output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
