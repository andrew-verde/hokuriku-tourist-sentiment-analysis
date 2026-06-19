#!/usr/bin/env python3
"""
Build Chinese social-media tourism text analysis outputs.

The input layer is schema-first and empty-data-safe. It normalizes Xiaohongshu
rows and parsed Douyin comment exports from the companion tourism-data project into a
review-like row schema, then applies SnowNLP plus reviewed Chinese
friction/topic/sentiment evidence terms for comparison with Google-review layers.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import subprocess
import sys
from itertools import combinations
from pathlib import Path

import pandas as pd
import yaml
from dotenv import load_dotenv
from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.utils.logger import setup_logger

load_dotenv()

logger = setup_logger(__name__)

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INPUT_DIR = Path(
    os.getenv("TOURISM_DATA_DIR", "/home/andrewgreen/Repositories/external/tourism-data")
)
OUTPUT_DIR = ROOT / "output" / "chinese_social_media_analysis"
CODEBOOK_PATH = ROOT / "config" / "chinese_social_friction_codebook.yaml"
REVIEWED_CODEBOOK_PATH = ROOT / "docs" / "codebook_templates" / "chinese_reviewed_codebook_template.csv"
DEFAULT_XHS_MANUAL_WORKBOOK = ROOT / "docs" / "codebook_reviews" / "source" / "fukui_xhs_reviews_manual.xlsx"
MULTILINGUAL_FRICTION_PATH = ROOT / "output" / "multilingual_review_analysis" / "friction_by_city_language_group.csv"

SOURCE_COLUMNS = [
    "city",
    "source_platform",
    "source_file",
    "source_record_id",
    "source_url",
    "author",
    "author_url",
    "title",
    "text_content",
    "source_relative_time",
    "source_parse_confidence",
    "source_parse_notes",
]

SCHEMA_COLUMNS = [
    *SOURCE_COLUMNS,
    "post_date",
    "post_date_precision",
    "content_language",
    "record_id",
    "sentiment_score",
    "sentiment_norm",
    "emotional_intensity_score",
]

THEME_COLUMNS = ["theme", "fan_score", "travel_score"]

POSITIVE_TERMS = [
    "好", "方便", "便利", "推荐", "值得", "喜欢", "美", "震撼", "舒服", "干净",
    "热情", "新鲜", "便宜", "顺利", "梦幻", "完善", "直达",
]

NEGATIVE_TERMS = [
    "不便", "不方便", "差", "贵", "拥挤", "排队", "少", "旧", "脏", "难",
    "堵", "累", "坑", "售罄", "关门", "没开", "找不到", "看不懂",
]

REVIEWED_SENTIMENT_CODES = {
    "positive_sentiment": "reviewed_positive_terms_matched",
    "negative_sentiment": "reviewed_negative_terms_matched",
    "recommendation_intent": "reviewed_recommendation_terms_matched",
}

DOUYIN_COMMENT_REQUIRED_COLUMNS = {
    "source_record_id",
    "comment_text",
    "relative_time",
    "parse_confidence",
    "parse_notes",
    "source_start_line",
    "source_end_line",
}

DOUYIN_LOCAL_ID_RE = re.compile(r"^comment_\d{6,}$")

REVIEWED_CODEBOOK_REQUIRED_COLUMNS = {
    "source_sheet",
    "source_row_id",
    "language",
    "code_family",
    "code",
    "label_en",
    "reviewer",
    "review_decision",
    "keyword_original",
    "keyword_final",
    "reviewed_at",
}

VALID_REVIEW_DECISIONS = {"no change", "fix", "delete"}
EVIDENCE_CODE_TYPES = {"friction", "topic", "sentiment"}
ENJOYMENT_EVIDENCE_CODES = {"positive_sentiment", "recommendation_intent"}

CITY_ALIASES = {
    "fukui": "Fukui",
    "福井": "Fukui",
    "kanazawa": "Kanazawa",
    "金泽": "Kanazawa",
    "金沢": "Kanazawa",
    "toyama": "Toyama",
    "富山": "Toyama",
}

PLATFORM_ALIASES = {
    "xhs": "xiaohongshu",
    "xiaohongshu": "xiaohongshu",
    "小红书": "xiaohongshu",
    "douyin": "douyin",
    "抖音": "douyin",
}


class InputSchemaError(RuntimeError):
    pass


class CodebookImportError(RuntimeError):
    pass


def load_chinese_codebook(
    path: Path = CODEBOOK_PATH,
    reviewed_path: Path = REVIEWED_CODEBOOK_PATH,
) -> dict:
    with path.open(encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    codebook = {}
    for code, attrs in raw.get("friction_codes", {}).items():
        codebook[code] = {
            "label": attrs["label"],
            "type": attrs["type"],
            "keywords": [str(keyword) for keyword in attrs.get("keywords", [])],
            "source": "yaml_legacy_friction",
            "reviewed_rows": [],
        }
    if reviewed_path.exists():
        reviewed = load_reviewed_codebook_config(reviewed_path)
        # Reviewed rows supersede YAML terms for matching codes. This preserves
        # delete/FIX decisions instead of appending reviewed terms onto stale YAML.
        codebook.update(reviewed)
    return codebook


def _clean_text(value: object) -> str:
    if pd.isna(value):
        return ""
    text = str(value).strip()
    if text.lower() == "nan":
        return ""
    return re.sub(r"\s+", " ", text)


# Xiaohongshu search results render the post date inside the author cell:
# "name YYYY-MM-DD" for prior years, "name MM-DD" for the scrape year, and
# relative forms ("昨天 22:03", "3天前") for very recent posts. Year and
# relative inference are anchored to the scrape reference date, and every
# parsed value carries a precision flag so downstream trend outputs can
# disclose or filter by date quality.
_DATE_FULL_RE = re.compile(r"^(?P<author>.*?)\s*(?P<date>\d{4}-\d{2}-\d{2})$")
_DATE_MONTH_DAY_RE = re.compile(r"^(?P<author>.*?)\s*(?P<month>\d{2})-(?P<day>\d{2})$")
_DATE_RELATIVE_DAY_RE = re.compile(r"^(?P<author>.*?)\s*(?P<word>今天|昨天|前天)(\s*\d{1,2}:\d{2})?$")
_DATE_DAYS_AGO_RE = re.compile(r"^(?P<author>.*?)\s*(?P<days>\d{1,2})\s*天前$")
_DATE_HOURS_AGO_RE = re.compile(r"^(?P<author>.*?)\s*\d{1,2}\s*(小时前|分钟前)$")
_DOUYIN_RELATIVE_RE = re.compile(r"^(?P<count>\d+)\s*(?P<unit>分钟前|小时前|天前|周前|月前|年前)$")


def scrape_reference_date(path: Path) -> dt.date:
    """Date the scrape file was committed (preferred) or last modified.

    Anchors year/relative date inference. Override with CN_SCRAPE_REFERENCE_DATE
    (YYYY-MM-DD) when analyzing a file outside its git checkout.
    """
    override = os.getenv("CN_SCRAPE_REFERENCE_DATE", "").strip()
    if override:
        return dt.date.fromisoformat(override)
    try:
        committed = subprocess.run(
            ["git", "-C", str(path.parent), "log", "-1", "--format=%cs", "--", path.name],
            capture_output=True, text=True, timeout=10,
        ).stdout.strip()
        if committed:
            return dt.date.fromisoformat(committed)
    except (OSError, ValueError, subprocess.SubprocessError):
        pass
    return dt.date.fromtimestamp(path.stat().st_mtime)


def parse_author_and_date(raw: str, reference_date: dt.date) -> tuple[str, str, str]:
    """Split an author cell into (author, post_date ISO string, precision)."""
    value = _clean_text(raw)
    if not value:
        return "", "", "none"
    match = _DATE_FULL_RE.match(value)
    if match:
        try:
            parsed = dt.date.fromisoformat(match.group("date"))
        except ValueError:
            return value, "", "none"
        return match.group("author").strip(), parsed.isoformat(), "exact"
    match = _DATE_MONTH_DAY_RE.match(value)
    if match:
        try:
            parsed = dt.date(reference_date.year, int(match.group("month")), int(match.group("day")))
        except ValueError:
            return value, "", "none"
        if parsed > reference_date:
            parsed = parsed.replace(year=reference_date.year - 1)
        return match.group("author").strip(), parsed.isoformat(), "year_inferred"
    match = _DATE_RELATIVE_DAY_RE.match(value)
    if match:
        offset = {"今天": 0, "昨天": 1, "前天": 2}[match.group("word")]
        parsed = reference_date - dt.timedelta(days=offset)
        return match.group("author").strip(), parsed.isoformat(), "relative_inferred"
    match = _DATE_DAYS_AGO_RE.match(value)
    if match:
        parsed = reference_date - dt.timedelta(days=int(match.group("days")))
        return match.group("author").strip(), parsed.isoformat(), "relative_inferred"
    match = _DATE_HOURS_AGO_RE.match(value)
    if match:
        return match.group("author").strip(), reference_date.isoformat(), "relative_inferred"
    return value, "", "none"


def parse_douyin_relative_time(raw: object, reference_date: dt.date) -> tuple[str, str]:
    """Parse Douyin relative comment time into an approximate date.

    Douyin comment exports currently expose relative times only. Month/year
    offsets are approximate calendar-free offsets so outputs carry precision
    as relative-inferred, not exact.
    """
    value = _clean_text(raw)
    if not value:
        return "", "none"
    match = _DOUYIN_RELATIVE_RE.match(value)
    if not match:
        return "", "none"
    count = int(match.group("count"))
    unit = match.group("unit")
    if unit == "分钟前" or unit == "小时前":
        days = 0
    elif unit == "天前":
        days = count
    elif unit == "周前":
        days = count * 7
    elif unit == "月前":
        days = count * 30
    elif unit == "年前":
        days = count * 365
    else:
        return "", "none"
    return (reference_date - dt.timedelta(days=days)).isoformat(), "relative_inferred"


def _infer_city(path: Path, row: pd.Series) -> str:
    explicit = _clean_text(row.get("city", ""))
    haystack = " ".join([explicit, path.stem, path.name]).lower()
    for token, city in CITY_ALIASES.items():
        if token.lower() in haystack:
            return city
    return explicit or "Unknown"


def _infer_platform(path: Path, row: pd.Series) -> str:
    explicit = _clean_text(row.get("source_platform", "")) or _clean_text(row.get("platform", ""))
    haystack = " ".join([explicit, path.stem, path.name]).lower()
    for token, platform in PLATFORM_ALIASES.items():
        if token.lower() in haystack:
            return platform
    return explicit or "unknown"


def _source_record_id(row: pd.Series, platform: str) -> str:
    candidates = ["source_record_id", "note_id", "video_id", "id", "note_url", "video_url", "url"]
    for field in candidates:
        value = _clean_text(row.get(field, ""))
        if value:
            return value
    raw = "|".join(_clean_text(row.get(field, "")) for field in row.index)
    return hashlib.sha256(f"{platform}|{raw}".encode()).hexdigest()[:12]


def _source_url(row: pd.Series) -> str:
    for field in ["source_url", "note_url", "video_url", "url"]:
        value = _clean_text(row.get(field, ""))
        if value:
            return value
    return ""


def _record_id(city: str, platform: str, source_record_id: str, text: str) -> str:
    raw = f"{city}|{platform}|{source_record_id}|{text}"
    return hashlib.sha256(raw.encode()).hexdigest()[:12]


def _lexicon_sentiment(text: str) -> tuple[float, float, float]:
    if not text:
        return 0.0, 0.5, 0.0
    positive = sum(text.count(term) for term in POSITIVE_TERMS)
    negative = sum(text.count(term) for term in NEGATIVE_TERMS)
    total = positive + negative
    score = (positive - negative) / total if total else 0.0
    return round(score, 6), round((score + 1.0) / 2.0, 6), round(abs(score), 6)


def _read_input_csv(path: Path) -> pd.DataFrame:
    try:
        return pd.read_csv(path)
    except pd.errors.EmptyDataError:
        return pd.DataFrame()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _require_columns(df: pd.DataFrame, required: set[str], context: str) -> None:
    missing = sorted(required - set(df.columns))
    if missing:
        raise InputSchemaError(f"{context} missing required columns: {missing}")


def load_reviewed_codebook_config(path: Path = REVIEWED_CODEBOOK_PATH) -> dict:
    if not path.exists():
        raise CodebookImportError(f"Reviewed Chinese codebook template not found: {path}")
    reviewed = pd.read_csv(path, encoding="utf-8-sig")
    missing = sorted(REVIEWED_CODEBOOK_REQUIRED_COLUMNS - set(reviewed.columns))
    if missing:
        raise CodebookImportError(f"Reviewed Chinese codebook missing required columns: {missing}")

    blank_decisions = reviewed["review_decision"].map(_clean_text).eq("")
    if blank_decisions.any():
        rows = reviewed.loc[blank_decisions, "source_row_id"].astype(str).head(5).tolist()
        raise CodebookImportError(f"Reviewed Chinese codebook has blank review_decision rows: {rows}")

    invalid_decisions = ~reviewed["review_decision"].map(_clean_text).str.lower().isin(VALID_REVIEW_DECISIONS)
    if invalid_decisions.any():
        rows = reviewed.loc[invalid_decisions, "source_row_id"].astype(str).head(5).tolist()
        raise CodebookImportError(f"Reviewed Chinese codebook has invalid review_decision rows: {rows}")

    chinese = reviewed[reviewed["language"].map(_clean_text) == "Chinese"].copy()
    codebook: dict[str, dict] = {}
    for _, row in chinese.iterrows():
        family = _clean_text(row.get("code_family", "")).lower()
        if family not in EVIDENCE_CODE_TYPES:
            continue
        code = _clean_text(row.get("code", ""))
        if not code:
            raise CodebookImportError(f"Reviewed Chinese codebook row missing code: {row.get('source_row_id')}")
        decision = _clean_text(row.get("review_decision", "")).lower()
        keyword = _clean_text(row.get("keyword_final", ""))
        if decision in {"no change", "fix"} and not keyword:
            raise CodebookImportError(
                f"Reviewed Chinese codebook row missing keyword_final: {row.get('source_row_id')}"
            )
        entry = codebook.setdefault(
            code,
            {
                "label": _clean_text(row.get("label_en", "")) or code,
                "type": family,
                "keywords": [],
                "source": "reviewed_chinese_codebook_template",
                "reviewed_rows": [],
            },
        )
        if entry["type"] != family:
            raise CodebookImportError(f"Reviewed Chinese codebook code has mixed families: {code}")
        if decision != "delete" and keyword and keyword not in entry["keywords"]:
            entry["keywords"].append(keyword)
        entry["reviewed_rows"].append({
            "source_sheet": _clean_text(row.get("source_sheet", "")),
            "source_row_id": _clean_text(row.get("source_row_id", "")),
            "review_decision": _clean_text(row.get("review_decision", "")),
            "keyword_original": _clean_text(row.get("keyword_original", "")),
            "keyword_final": keyword,
            "reviewer": _clean_text(row.get("reviewer", "")),
            "reviewed_at": _clean_text(row.get("reviewed_at", "")),
        })

    empty_codes = [code for code, attrs in codebook.items() if not attrs["keywords"]]
    if empty_codes:
        raise CodebookImportError(f"Reviewed Chinese codebook has no kept keywords for codes: {empty_codes}")
    return codebook


def reviewed_codebook_summary(codebook: dict) -> list[dict]:
    rows = []
    for code, attrs in sorted(codebook.items()):
        reviewed_rows = attrs.get("reviewed_rows", [])
        decisions: dict[str, int] = {}
        reviewers = set()
        reviewed_dates = set()
        for row in reviewed_rows:
            decision = _clean_text(row.get("review_decision", ""))
            if decision:
                decisions[decision] = decisions.get(decision, 0) + 1
            reviewer = _clean_text(row.get("reviewer", ""))
            if reviewer:
                reviewers.add(reviewer)
            reviewed_at = _clean_text(row.get("reviewed_at", ""))
            if reviewed_at:
                reviewed_dates.add(reviewed_at)
        rows.append({
            "code_family": attrs["type"],
            "code": code,
            "label": attrs["label"],
            "keyword_count": len(attrs.get("keywords", [])),
            "reviewed_row_count": len(reviewed_rows),
            "review_decision_counts": json.dumps(decisions, ensure_ascii=False, sort_keys=True),
            "reviewers": "|".join(sorted(reviewers)),
            "reviewed_at": "|".join(sorted(reviewed_dates)),
            "source": attrs.get("source", ""),
        })
    return rows


def _read_input_table(path: Path) -> pd.DataFrame:
    if path.suffix.lower() in {".xlsx", ".xls"}:
        return pd.read_excel(path, sheet_name="fukui_xhs_reviews")
    return _read_input_csv(path)


def is_douyin_comment_source(path: Path, df: pd.DataFrame) -> bool:
    name = path.name.lower()
    return "douyin" in name and ("comments" in name or "comment_text" in df.columns)


def validate_douyin_comment_source(path: Path, source: pd.DataFrame) -> dict:
    context = f"Douyin comment source {path}"
    _require_columns(source, DOUYIN_COMMENT_REQUIRED_COLUMNS, context)
    if source.empty:
        return {
            "source_file": str(path),
            "source_sha256": sha256_file(path),
            "rows": 0,
            "status": "empty_schema_validated",
        }

    checks = {}
    for column in DOUYIN_COMMENT_REQUIRED_COLUMNS:
        checks[f"missing_{column}"] = int(source[column].map(_clean_text).eq("").sum())
    bad_columns = {key: value for key, value in checks.items() if value}
    if bad_columns:
        raise InputSchemaError(f"{context} has blank provenance fields: {bad_columns}")

    source_ids = source["source_record_id"].map(_clean_text)
    duplicate_count = int(source_ids.duplicated().sum())
    invalid_local_ids = int((~source_ids.str.match(DOUYIN_LOCAL_ID_RE)).sum())
    notes = source["parse_notes"].map(_clean_text)
    missing_parser_caveat = int((~notes.str.contains("local_record_id_not_platform_comment_id", regex=False)).sum())
    confidence = source["parse_confidence"].map(_clean_text).str.lower()
    unsupported_confidence = int((~confidence.isin({"medium", "high"})).sum())
    start_lines = pd.to_numeric(source["source_start_line"], errors="coerce")
    end_lines = pd.to_numeric(source["source_end_line"], errors="coerce")
    invalid_line_spans = int((start_lines.isna() | end_lines.isna() | (end_lines < start_lines)).sum())

    failures = {
        "duplicate_source_record_id": duplicate_count,
        "invalid_local_parser_id": invalid_local_ids,
        "missing_local_id_caveat": missing_parser_caveat,
        "unsupported_parse_confidence": unsupported_confidence,
        "invalid_source_line_span": invalid_line_spans,
    }
    failures = {key: value for key, value in failures.items() if value}
    if failures:
        raise InputSchemaError(f"{context} provenance checks failed: {failures}")

    parseable_time = source["relative_time"].apply(
        lambda value: parse_douyin_relative_time(value, dt.date(2000, 1, 1))[1] != "none"
    )
    parse_notes_counts = source["parse_notes"].fillna("").astype(str).value_counts().to_dict()
    return {
        "source_file": str(path),
        "source_sha256": sha256_file(path),
        "rows": int(len(source)),
        "status": "validated",
        "source_record_id_kind": "local_parser_id_not_platform_comment_id",
        "parse_confidence_counts": {
            str(k): int(v) for k, v in source["parse_confidence"].fillna("").astype(str).value_counts().items()
        },
        "parse_notes_counts": {str(k): int(v) for k, v in parse_notes_counts.items()},
        "relative_time_parseable_rows": int(parseable_time.sum()),
        "relative_time_unparseable_rows": int((~parseable_time).sum()),
        "post_id_available_rows": int(source.get("douyin_post_id", pd.Series(dtype=object)).map(_clean_text).ne("").sum())
        if "douyin_post_id" in source.columns else 0,
        "source_line_span_present_rows": int((start_lines.notna() & end_lines.notna()).sum()),
    }


def discover_input_files(input_dir: Path) -> list[Path]:
    """Find raw social scrape CSVs in the companion tourism-data checkout.

    Raw scrapes are preferred for source text. The current Douyin comment export
    is parsed from markdown into data/processed and is also an ingestion source.
    Other processed CSVs are consumed only as annotations.
    """
    if not input_dir.exists():
        return []
    search_dirs = [input_dir, input_dir / "data" / "raw" / "social"]
    files = []
    use_repo_workbook = input_dir == DEFAULT_INPUT_DIR or input_dir.name == "tourism-data"
    if use_repo_workbook and DEFAULT_XHS_MANUAL_WORKBOOK.exists():
        files.append(DEFAULT_XHS_MANUAL_WORKBOOK)
    for directory in search_dirs:
        if not directory.exists():
            continue
        for path in directory.glob("*.csv"):
            name = path.name.lower()
            if any(token in name for token in ["xhs", "xiaohongshu", "douyin", "小红书", "抖音"]):
                if use_repo_workbook and DEFAULT_XHS_MANUAL_WORKBOOK.exists() and any(token in name for token in ["xhs", "xiaohongshu", "小红书"]):
                    continue
                files.append(path)
    processed_dir = input_dir / "data" / "processed"
    if processed_dir.exists():
        for path in processed_dir.glob("*douyin*comments*.csv"):
            files.append(path)
    return sorted(set(files))


def discover_theme_files(input_dir: Path) -> list[Path]:
    processed_dir = input_dir / "data" / "processed"
    if not processed_dir.exists():
        return []
    return sorted(processed_dir.glob("*.csv"))


def load_theme_annotations(input_dir: Path) -> pd.DataFrame:
    """Collect colleague theme classifications keyed by source record id.

    The processed CSVs in tourism-data carry theme / fan_score / travel_score
    per note_id (or video_id). Raw scrapes stay the text source of truth;
    these columns are joined on as annotations only.
    """
    frames = []
    for path in discover_theme_files(input_dir):
        df = _read_input_csv(path)
        if df.empty or "theme" not in df.columns:
            continue
        id_col = next((c for c in ["note_id", "video_id", "id"] if c in df.columns), None)
        if id_col is None:
            continue
        annotation = pd.DataFrame({"source_record_id": df[id_col].map(_clean_text)})
        annotation["theme"] = df["theme"].map(_clean_text)
        for column in ["fan_score", "travel_score"]:
            annotation[column] = pd.to_numeric(df[column], errors="coerce") if column in df.columns else pd.NA
        frames.append(annotation[annotation["source_record_id"] != ""])
    if not frames:
        return pd.DataFrame(columns=["source_record_id", *THEME_COLUMNS])
    merged = pd.concat(frames, ignore_index=True)
    return merged.drop_duplicates(subset=["source_record_id"], keep="first").reset_index(drop=True)


def normalize_social_csv(path: Path, reference_date: dt.date | None = None) -> pd.DataFrame:
    source = _read_input_table(path)
    if is_douyin_comment_source(path, source):
        validate_douyin_comment_source(path, source)
    if source.empty:
        return pd.DataFrame(columns=SCHEMA_COLUMNS)
    if reference_date is None:
        reference_date = scrape_reference_date(path)

    rows = []
    for _, row in source.iterrows():
        title = _clean_text(row.get("title", ""))
        body = (
            _clean_text(row.get("body_text", ""))
            or _clean_text(row.get("comment_text", ""))
            or _clean_text(row.get("text", ""))
            or _clean_text(row.get("description", ""))
            or _clean_text(row.get("content", ""))
        )
        text_content = " ".join(part for part in [title, body] if part).strip()
        if not text_content:
            continue

        city = _infer_city(path, row)
        platform = _infer_platform(path, row)
        source_record_id = _source_record_id(row, platform)
        sentiment_score, sentiment_norm, intensity = _lexicon_sentiment(text_content)
        if platform == "douyin" and "relative_time" in source.columns:
            author = _clean_text(row.get("author", ""))
            post_date, post_date_precision = parse_douyin_relative_time(
                row.get("relative_time", ""), reference_date
            )
        else:
            author, post_date, post_date_precision = parse_author_and_date(
                row.get("author", ""), reference_date
            )
        rows.append({
            "city": city,
            "source_platform": platform,
            "source_file": str(path),
            "source_record_id": source_record_id,
            "source_url": _source_url(row),
            "author": author,
            "author_url": _clean_text(row.get("author_url", "")),
            "title": title,
            "text_content": text_content,
            "source_relative_time": _clean_text(row.get("relative_time", "")),
            "source_parse_confidence": _clean_text(row.get("parse_confidence", "")),
            "source_parse_notes": _clean_text(row.get("parse_notes", "")),
            "post_date": post_date,
            "post_date_precision": post_date_precision,
            "content_language": "zh",
            "record_id": _record_id(city, platform, source_record_id, text_content),
            "sentiment_score": sentiment_score,
            "sentiment_norm": sentiment_norm,
            "emotional_intensity_score": intensity,
        })
    return pd.DataFrame(rows, columns=SCHEMA_COLUMNS)


def _snownlp_sentiment(text: str) -> tuple[float, float, str]:
    if not text:
        return 0.5, 0.0, "neutral"
    try:
        from snownlp import SnowNLP
    except ImportError as error:
        raise RuntimeError(
            "Required dependency not importable: snownlp. "
            "Install it with `.venv/bin/pip install -r requirements.txt`."
        ) from error
    positive_prob = float(SnowNLP(text).sentiments)
    centered = (positive_prob * 2.0) - 1.0
    if centered >= 0.05:
        category = "positive"
    elif centered <= -0.05:
        category = "negative"
    else:
        category = "neutral"
    return round(positive_prob, 6), round(centered, 6), category


def _reviewed_terms_from_codebook(codebook: dict) -> dict[str, list[str]]:
    return {
        code: list(codebook.get(code, {}).get("keywords", []))
        for code in REVIEWED_SENTIMENT_CODES
    }


def _append_sentiment_fields(df: pd.DataFrame, reviewed_terms: dict[str, list[str]]) -> pd.DataFrame:
    scored = df.copy()
    if scored.empty:
        for column in [
            "title_has_text",
            "body_has_text",
            "text_scope",
            "text_length_chars",
            "snownlp_positive_prob",
            "snownlp_centered_score",
            "sentiment_category",
            *REVIEWED_SENTIMENT_CODES.values(),
        ]:
            scored[column] = pd.Series(dtype=object)
        return scored
    title_text = scored["title"].fillna("").astype(str).str.strip()
    text_text = scored["text_content"].fillna("").astype(str).str.strip()
    body_text = [
        text[len(title):].strip() if title and text.startswith(title) else text
        for title, text in zip(title_text, text_text, strict=False)
    ]
    scored["title_has_text"] = title_text != ""
    scored["body_has_text"] = [bool(str(value).strip()) for value in body_text]
    scored["text_scope"] = scored["body_has_text"].map(lambda value: "title_and_body" if value else "title_only")
    scored["text_length_chars"] = text_text.str.len()
    snow = scored["text_content"].apply(_snownlp_sentiment)
    scored["snownlp_positive_prob"] = snow.apply(lambda value: value[0])
    scored["snownlp_centered_score"] = snow.apply(lambda value: value[1])
    scored["sentiment_category"] = snow.apply(lambda value: value[2])
    scored["sentiment_norm"] = scored["snownlp_positive_prob"]
    scored["sentiment_score"] = scored["snownlp_centered_score"]
    scored["emotional_intensity_score"] = scored["snownlp_centered_score"].abs()
    for code, column in REVIEWED_SENTIMENT_CODES.items():
        keywords = reviewed_terms.get(code, [])
        scored[column] = scored["text_content"].apply(
            lambda text, keywords=keywords: "|".join(keyword for keyword in keywords if keyword in str(text))
        )
    return scored


def _tag_chinese_dataframe(df: pd.DataFrame, codebook: dict) -> pd.DataFrame:
    tagged = df.copy()
    for code, attrs in codebook.items():
        keywords = attrs["keywords"]
        tagged[code] = tagged["text_content"].apply(
            lambda text, keywords=keywords: any(keyword in str(text) for keyword in keywords)
        )
    friction_codes = [code for code, attrs in codebook.items() if attrs["type"] == "friction"]
    topic_codes = [code for code, attrs in codebook.items() if attrs["type"] == "topic"]
    enjoyment_codes = [code for code in ENJOYMENT_EVIDENCE_CODES if code in codebook]
    if friction_codes:
        tagged["friction_codes"] = tagged[friction_codes].apply(
            lambda row: [code for code in friction_codes if bool(row[code])],
            axis=1,
        )
        tagged["any_friction"] = tagged[friction_codes].any(axis=1)
    else:
        tagged["friction_codes"] = [[] for _ in range(len(tagged))]
        tagged["any_friction"] = False
    if topic_codes:
        tagged["topic_codes"] = tagged[topic_codes].apply(
            lambda row: [code for code in topic_codes if bool(row[code])],
            axis=1,
        )
        tagged["any_topic"] = tagged[topic_codes].any(axis=1)
    else:
        tagged["topic_codes"] = [[] for _ in range(len(tagged))]
        tagged["any_topic"] = False
    if enjoyment_codes:
        tagged["enjoyment_evidence_codes"] = tagged[enjoyment_codes].apply(
            lambda row: [code for code in enjoyment_codes if bool(row[code])],
            axis=1,
        )
        tagged["any_enjoyment_evidence"] = tagged[enjoyment_codes].any(axis=1)
    else:
        tagged["enjoyment_evidence_codes"] = [[] for _ in range(len(tagged))]
        tagged["any_enjoyment_evidence"] = False
    return tagged


def _code_summary(
    tagged: pd.DataFrame,
    codebook: dict,
    code_family: str,
    group_cols: list[str] | None = None,
    codes: list[str] | None = None,
) -> pd.DataFrame:
    group_cols = group_cols or ["city", "source_platform"]
    rows = []
    codes = codes or [code for code, attrs in codebook.items() if attrs["type"] == code_family]
    grouped = tagged.groupby(group_cols, dropna=False)
    for keys, group in grouped:
        if not isinstance(keys, tuple):
            keys = (keys,)
        denominator = len(group)
        for code in codes:
            count = int(group[code].sum()) if code in group.columns else 0
            rows.append({
                **dict(zip(group_cols, keys)),
                "code_family": codebook[code]["type"],
                "code": code,
                "label": codebook[code]["label"],
                "count": count,
                "denominator_posts": denominator,
                "pct_posts": round(100 * count / denominator, 3) if denominator else 0.0,
            })
    return pd.DataFrame(rows)


def _friction_summary(
    tagged: pd.DataFrame, codebook: dict, group_cols: list[str] | None = None
) -> pd.DataFrame:
    summary = _code_summary(tagged, codebook, "friction", group_cols)
    if summary.empty:
        return summary
    return summary.rename(columns={"code": "friction_code", "label": "friction_label"}).drop(
        columns=["code_family"]
    )


def _topic_summary(
    tagged: pd.DataFrame, codebook: dict, group_cols: list[str] | None = None
) -> pd.DataFrame:
    return _code_summary(tagged, codebook, "topic", group_cols)


def _enjoyment_evidence_summary(
    tagged: pd.DataFrame, codebook: dict, group_cols: list[str] | None = None
) -> pd.DataFrame:
    codes = [code for code in ENJOYMENT_EVIDENCE_CODES if code in codebook]
    return _code_summary(tagged, codebook, "sentiment", group_cols, codes)


def _theme_summary(df: pd.DataFrame) -> pd.DataFrame:
    columns = ["city", "source_platform", "theme", "count", "pct_posts", "sentiment_norm_mean"]
    if df.empty:
        return pd.DataFrame(columns=columns)
    score_col = "snownlp_positive_prob" if "snownlp_positive_prob" in df.columns else "sentiment_norm"
    rows = []
    for (city, platform), group in df.groupby(["city", "source_platform"], dropna=False):
        denominator = len(group)
        for theme, theme_group in group.groupby("theme", dropna=False):
            rows.append({
                "city": city,
                "source_platform": platform,
                "theme": theme,
                "count": len(theme_group),
                "pct_posts": round(100 * len(theme_group) / denominator, 3) if denominator else 0.0,
                "sentiment_norm_mean": round(float(theme_group[score_col].mean()), 6),
            })
    return pd.DataFrame(rows, columns=columns)


def _sentiment_summary(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["city", "source_platform", "count", "mean", "median", "std"])
    score_col = "snownlp_positive_prob" if "snownlp_positive_prob" in df.columns else "sentiment_norm"
    grouped = df.groupby(["city", "source_platform"], dropna=False)[score_col]
    return grouped.agg(["count", "mean", "median", "std"]).reset_index()


def _binary_group_test(df: pd.DataFrame, group_col: str, code: str) -> list[dict]:
    rows = []
    groups = sorted(str(value) for value in df[group_col].dropna().unique())
    for a, b in combinations(groups, 2):
        ga = df[df[group_col].astype(str) == a]
        gb = df[df[group_col].astype(str) == b]
        a_count = int(ga[code].sum())
        b_count = int(gb[code].sum())
        table = [[a_count, len(ga) - a_count], [b_count, len(gb) - b_count]]
        fisher_p = None
        odds_ratio = None
        if len(ga) and len(gb):
            try:
                odds_ratio, fisher_p = stats.fisher_exact(table, alternative="two-sided")
            except Exception:
                pass
        rows.append({
            "comparison_type": group_col,
            "group_a": a,
            "group_b": b,
            "friction_code": code,
            "group_a_count": a_count,
            "group_a_n": int(len(ga)),
            "group_b_count": b_count,
            "group_b_n": int(len(gb)),
            "group_a_pct": round(100 * a_count / len(ga), 3) if len(ga) else 0.0,
            "group_b_pct": round(100 * b_count / len(gb), 3) if len(gb) else 0.0,
            "group_b_minus_group_a_pp": round(
                (100 * b_count / len(gb) if len(gb) else 0.0)
                - (100 * a_count / len(ga) if len(ga) else 0.0),
                3,
            ),
            "odds_ratio": None if odds_ratio is None else float(odds_ratio),
            "fisher_exact_p": None if fisher_p is None else float(fisher_p),
        })
    return rows


def _within_chinese_tests(tagged: pd.DataFrame, codebook: dict) -> pd.DataFrame:
    columns = [
        "comparison_type",
        "group_a",
        "group_b",
        "friction_code",
        "group_a_count",
        "group_a_n",
        "group_b_count",
        "group_b_n",
        "group_a_pct",
        "group_b_pct",
        "group_b_minus_group_a_pp",
        "odds_ratio",
        "fisher_exact_p",
    ]
    rows = []
    codes = [code for code, attrs in codebook.items() if attrs["type"] == "friction"]
    for code in codes:
        rows.extend(_binary_group_test(tagged, "city", code))
        rows.extend(_binary_group_test(tagged, "source_platform", code))
    return pd.DataFrame(rows, columns=columns)


def _review_language_comparison(
    friction_summary: pd.DataFrame, review_path: Path, chinese_subset: str = "all_posts"
) -> pd.DataFrame:
    columns = [
        "city", "friction_code", "friction_label", "comparison_group", "chinese_subset",
        "chinese_count", "chinese_n", "chinese_pct_posts",
        "review_count", "review_n", "review_pct_reviews",
        "review_minus_chinese_pp",
    ]
    if friction_summary.empty or not review_path.exists():
        return pd.DataFrame(columns=columns)
    reviews = pd.read_csv(review_path)
    if reviews.empty:
        return pd.DataFrame(columns=columns)
    rows = []
    chinese = friction_summary.groupby(["city", "friction_code", "friction_label"], dropna=False).agg(
        chinese_count=("count", "sum"),
        chinese_n=("denominator_posts", "sum"),
    ).reset_index()
    chinese["chinese_pct_posts"] = chinese.apply(
        lambda row: round(100 * row["chinese_count"] / row["chinese_n"], 3) if row["chinese_n"] else 0.0,
        axis=1,
    )
    for _, row in chinese.iterrows():
        comparable = reviews[
            (reviews["city"] == row["city"])
            & (reviews["code"] == row["friction_code"])
            & (reviews["language_group"].isin(["english", "japanese"]))
        ]
        for _, review_row in comparable.iterrows():
            rows.append({
                "city": row["city"],
                "friction_code": row["friction_code"],
                "friction_label": row["friction_label"],
                "comparison_group": f"google_{review_row['language_group']}",
                "chinese_subset": chinese_subset,
                "chinese_count": int(row["chinese_count"]),
                "chinese_n": int(row["chinese_n"]),
                "chinese_pct_posts": float(row["chinese_pct_posts"]),
                "review_count": int(review_row["count"]),
                "review_n": int(review_row["denominator_reviews"]),
                "review_pct_reviews": float(review_row["pct_reviews"]),
                "review_minus_chinese_pp": round(float(review_row["pct_reviews"]) - float(row["chinese_pct_posts"]), 3),
            })
    return pd.DataFrame(rows, columns=columns)


def _write_readiness(report: dict, path: Path) -> None:
    lines = [
        "# Chinese Social Media Analysis Readiness",
        "",
        "This layer treats Xiaohongshu notes and Douyin comments as Chinese-language tourism text, analogous to the role Google reviews play for English-language review analysis. It is not a nationality inference.",
        "",
        f"- Input directory: `{report['input_dir']}`",
        f"- Input files discovered: {report['input_files_discovered']}",
        f"- Input SHA256: `{report['input_sha256']}`",
        f"- Rows before deduplication: {report['rows_before_dedup']}",
        f"- Duplicate record rows removed: {report['duplicates_removed']}",
        f"- Rows retained: {report['rows_retained']}",
        f"- Source platform mix: {report['source_platform_counts']}",
        f"- Rows with body text: {report['n_with_body_text']}",
        f"- Title-only rows excluded from primary comparison: {report['n_title_only_excluded']}",
        f"- Non-fan rows for primary comparison: {report['n_non_fan_compared']}",
        f"- Theme mix: {report['theme_counts']}",
        f"- Post-date precision mix: {report['post_date_precision_counts']}",
        f"- Row-level output SHA256: `{report['row_level_output_sha256']}`",
        f"- Reviewed codebook template: `{report['reviewed_codebook_path']}`",
        f"- Reviewed codebook SHA256: `{report['reviewed_codebook_sha256']}`",
        f"- Reviewed codebook rows promoted: {report['reviewed_codebook_rows_promoted']}",
        f"- Runtime codebook counts by family: {report['runtime_codebook_counts_by_family']}",
        f"- Douyin provenance sources validated: {report['douyin_provenance_sources_validated']}",
        f"- Douyin provenance report: `{report['douyin_provenance_report']}`",
        "",
        "## Caveats",
        "",
        "- Unit of analysis is one social-media source row: one Xiaohongshu note or one Douyin comment, not a full travel itinerary or confirmed visit.",
        "- Douyin comments come from `tourism-data/data/processed/fukui_douyin_comments_from_md.csv` because the current source was parsed from markdown; keep that row-level file external.",
        "- Douyin comment ids are local parser ids, not platform comment ids; use input hashes and parser notes for provenance.",
        "- Douyin comment dates are inferred from relative timestamps anchored to the parsed CSV reference date, so they are not exact publication dates.",
        "- Primary Chinese sentiment rows require post body text or comment text; rows without that text are smoke-test material only.",
        "- Chinese friction/topic/positive-evidence tags are substring keyword matches from reviewed Chinese codebook rows; they are audit evidence, not a validated causal explanation.",
        "- Chinese sentiment fields use SnowNLP as the canonical current baseline (`sentiment_norm`, `sentiment_score`, and `sentiment_category`); reviewed term matches remain transparent evidence columns.",
        "- Positive/recommendation evidence is labeled as enjoyment evidence for presentation scanning only; do not treat it as a psychometric enjoyment scale.",
        "- Compare Chinese social-media rates with Google review-language rates descriptively because source platform behavior and text length differ.",
        "- Theme labels (fan / travel / ordinary) come from the companion tourism-data processed CSVs, joined on note id; rows without a label are `unclassified`.",
        "- `post_date` is parsed from the Xiaohongshu author cell; `post_date_precision` marks exact vs year-inferred vs relative-inferred values (inference anchored to the scrape commit date).",
        "- Group project layer: these outputs feed the cross-language trends comparison only and are not thesis evidence.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def build_chinese_social_outputs(
    input_dir: Path = DEFAULT_INPUT_DIR,
    output_dir: Path = OUTPUT_DIR,
    input_files: list[Path] | None = None,
    review_friction_path: Path = MULTILINGUAL_FRICTION_PATH,
) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    input_files = input_files if input_files is not None else discover_input_files(input_dir)
    codebook = load_chinese_codebook()
    reviewed_terms = _reviewed_terms_from_codebook(codebook)

    frames = [normalize_social_csv(path) for path in input_files]
    df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=SCHEMA_COLUMNS)
    rows_before_dedup = len(df)
    if not df.empty:
        df = df.drop_duplicates(subset=["record_id"], keep="first").reset_index(drop=True)
    duplicates_removed = rows_before_dedup - len(df)

    themes = load_theme_annotations(input_dir)
    if not df.empty:
        df = df.merge(themes, on="source_record_id", how="left")
        df["theme"] = df["theme"].fillna("unclassified").replace("", "unclassified")
    else:
        for column in THEME_COLUMNS:
            df[column] = pd.Series(dtype=object)

    df = _append_sentiment_fields(df, reviewed_terms)
    tagged = _tag_chinese_dataframe(df, codebook) if not df.empty else df.copy()
    for code in codebook:
        if code not in tagged.columns:
            tagged[code] = pd.Series(dtype=bool)
    if "friction_codes" not in tagged.columns:
        tagged["friction_codes"] = pd.Series(dtype=object)
    if "any_friction" not in tagged.columns:
        tagged["any_friction"] = pd.Series(dtype=bool)
    if "topic_codes" not in tagged.columns:
        tagged["topic_codes"] = pd.Series(dtype=object)
    if "any_topic" not in tagged.columns:
        tagged["any_topic"] = pd.Series(dtype=bool)
    if "enjoyment_evidence_codes" not in tagged.columns:
        tagged["enjoyment_evidence_codes"] = pd.Series(dtype=object)
    if "any_enjoyment_evidence" not in tagged.columns:
        tagged["any_enjoyment_evidence"] = pd.Series(dtype=bool)

    normalized_path = output_dir / "chinese_social_posts.csv"
    tagged_path = output_dir / "tagged_chinese_social_posts.csv"
    friction_summary_path = output_dir / "chinese_friction_by_city_platform.csv"
    friction_theme_path = output_dir / "chinese_friction_by_city_platform_theme.csv"
    topic_summary_path = output_dir / "chinese_topic_by_city_platform.csv"
    topic_theme_path = output_dir / "chinese_topic_by_city_platform_theme.csv"
    enjoyment_summary_path = output_dir / "chinese_enjoyment_evidence_by_city_platform.csv"
    enjoyment_theme_path = output_dir / "chinese_enjoyment_evidence_by_city_platform_theme.csv"
    theme_summary_path = output_dir / "chinese_theme_by_city_platform.csv"
    sentiment_summary_path = output_dir / "chinese_sentiment_by_city_platform.csv"
    within_tests_path = output_dir / "chinese_city_platform_friction_tests.csv"
    review_comparison_path = output_dir / "chinese_vs_review_language_friction_comparison.csv"
    codebook_summary_path = output_dir / "chinese_reviewed_codebook_runtime_summary.csv"
    douyin_provenance_path = output_dir / "douyin_provenance_report.json"
    report_json_path = output_dir / "chinese_social_readiness.json"
    report_md_path = output_dir / "chinese_social_readiness.md"

    friction_columns = ["city", "source_platform", "friction_code", "friction_label", "count", "denominator_posts", "pct_posts"]
    evidence_columns = ["city", "source_platform", "code_family", "code", "label", "count", "denominator_posts", "pct_posts"]
    evidence_theme_columns = ["city", "source_platform", "theme", *evidence_columns[2:]]
    friction_summary = _friction_summary(tagged, codebook) if not tagged.empty else pd.DataFrame(columns=friction_columns)
    friction_by_theme = _friction_summary(tagged, codebook, ["city", "source_platform", "theme"]) if not tagged.empty else pd.DataFrame(
        columns=["city", "source_platform", "theme", *friction_columns[2:]]
    )
    topic_summary = _topic_summary(tagged, codebook) if not tagged.empty else pd.DataFrame(columns=evidence_columns)
    topic_by_theme = _topic_summary(tagged, codebook, ["city", "source_platform", "theme"]) if not tagged.empty else pd.DataFrame(columns=evidence_theme_columns)
    enjoyment_summary = _enjoyment_evidence_summary(tagged, codebook) if not tagged.empty else pd.DataFrame(columns=evidence_columns)
    enjoyment_by_theme = _enjoyment_evidence_summary(tagged, codebook, ["city", "source_platform", "theme"]) if not tagged.empty else pd.DataFrame(columns=evidence_theme_columns)
    theme_summary = _theme_summary(df)
    sentiment_summary = _sentiment_summary(df)
    within_tests = _within_chinese_tests(tagged, codebook) if not tagged.empty else pd.DataFrame()
    codebook_summary = pd.DataFrame(reviewed_codebook_summary(codebook))
    douyin_provenance = []
    for path in input_files:
        if not path.exists():
            continue
        source_table = _read_input_table(path)
        if is_douyin_comment_source(path, source_table):
            douyin_provenance.append(validate_douyin_comment_source(path, source_table))

    # Fan-pilgrimage notes are a distinct travel motivation, so the EN/JP
    # review comparison is reported both for all posts and excluding them.
    excluding_fan = tagged[tagged["theme"] != "fan"] if not tagged.empty else tagged
    friction_excluding_fan = _friction_summary(excluding_fan, codebook) if not excluding_fan.empty else pd.DataFrame(columns=friction_columns)
    review_comparison = pd.concat(
        [
            _review_language_comparison(friction_summary, review_friction_path, "all_posts"),
            _review_language_comparison(friction_excluding_fan, review_friction_path, "excluding_fan"),
        ],
        ignore_index=True,
    )

    df.to_csv(normalized_path, index=False)
    tagged.to_csv(tagged_path, index=False)
    friction_summary.to_csv(friction_summary_path, index=False)
    friction_by_theme.to_csv(friction_theme_path, index=False)
    topic_summary.to_csv(topic_summary_path, index=False)
    topic_by_theme.to_csv(topic_theme_path, index=False)
    enjoyment_summary.to_csv(enjoyment_summary_path, index=False)
    enjoyment_by_theme.to_csv(enjoyment_theme_path, index=False)
    theme_summary.to_csv(theme_summary_path, index=False)
    sentiment_summary.to_csv(sentiment_summary_path, index=False)
    within_tests.to_csv(within_tests_path, index=False)
    review_comparison.to_csv(review_comparison_path, index=False)
    codebook_summary.to_csv(codebook_summary_path, index=False)
    douyin_provenance_path.write_text(json.dumps(douyin_provenance, ensure_ascii=False, indent=2), encoding="utf-8")
    row_level_hash = sha256_file(tagged_path)
    input_hashes = {str(path): sha256_file(path) for path in input_files if path.exists()}
    reviewed_hash = sha256_file(REVIEWED_CODEBOOK_PATH) if REVIEWED_CODEBOOK_PATH.exists() else None
    n_with_body_text = int(df["body_has_text"].sum()) if "body_has_text" in df.columns else 0
    n_title_only = int((~df["body_has_text"]).sum()) if "body_has_text" in df.columns else len(df)
    n_non_fan = int(((df["body_has_text"]) & (df["theme"] != "fan")).sum()) if not df.empty else 0
    runtime_counts_by_family = {
        str(k): int(v) for k, v in codebook_summary["code_family"].value_counts().items()
    } if not codebook_summary.empty else {}
    promoted_rows = int(codebook_summary["reviewed_row_count"].sum()) if not codebook_summary.empty else 0

    report = {
        "input_dir": str(input_dir),
        "input_files": [str(path) for path in input_files],
        "input_sha256": input_hashes,
        "input_files_discovered": len(input_files),
        "rows_before_dedup": rows_before_dedup,
        "duplicates_removed": duplicates_removed,
        "rows_retained": len(df),
        "n_total_xhs_rows": int(len(df[df["source_platform"] == "xiaohongshu"])) if not df.empty else 0,
        "n_total_douyin_rows": int(len(df[df["source_platform"] == "douyin"])) if not df.empty else 0,
        "n_with_body_text": n_with_body_text,
        "n_title_only_excluded": n_title_only,
        "n_non_fan_compared": n_non_fan,
        "source_platform_counts": {str(k): int(v) for k, v in df["source_platform"].value_counts().items()} if not df.empty else {},
        "city_counts": {str(k): int(v) for k, v in df["city"].value_counts().items()} if not df.empty else {},
        "theme_counts": {str(k): int(v) for k, v in df["theme"].value_counts().items()} if not df.empty else {},
        "post_date_precision_counts": {str(k): int(v) for k, v in df["post_date_precision"].value_counts().items()} if not df.empty else {},
        "row_level_output_sha256": row_level_hash,
        "reviewed_codebook_path": str(REVIEWED_CODEBOOK_PATH),
        "reviewed_codebook_sha256": reviewed_hash,
        "reviewed_codebook_rows_promoted": promoted_rows,
        "runtime_codebook_counts_by_family": runtime_counts_by_family,
        "codebook_evidence_status": "reviewed_chinese_template_promoted_for_friction_topic_sentiment_evidence",
        "douyin_provenance_sources_validated": len(douyin_provenance),
        "douyin_provenance_report": str(douyin_provenance_path),
        "douyin_provenance": douyin_provenance,
        "outputs": {
            "chinese_social_posts": str(normalized_path),
            "tagged_chinese_social_posts": str(tagged_path),
            "chinese_friction_by_city_platform": str(friction_summary_path),
            "chinese_friction_by_city_platform_theme": str(friction_theme_path),
            "chinese_topic_by_city_platform": str(topic_summary_path),
            "chinese_topic_by_city_platform_theme": str(topic_theme_path),
            "chinese_enjoyment_evidence_by_city_platform": str(enjoyment_summary_path),
            "chinese_enjoyment_evidence_by_city_platform_theme": str(enjoyment_theme_path),
            "chinese_theme_by_city_platform": str(theme_summary_path),
            "chinese_sentiment_by_city_platform": str(sentiment_summary_path),
            "chinese_city_platform_friction_tests": str(within_tests_path),
            "chinese_vs_review_language_friction_comparison": str(review_comparison_path),
            "chinese_reviewed_codebook_runtime_summary": str(codebook_summary_path),
            "douyin_provenance_report": str(douyin_provenance_path),
            "chinese_social_readiness": str(report_md_path),
        },
    }
    report_json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_readiness(report, report_md_path)
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--input-file", type=Path, action="append", default=None, help="Specific CSV file to include; can be repeated.")
    parser.add_argument("--review-friction-path", type=Path, default=MULTILINGUAL_FRICTION_PATH)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_chinese_social_outputs(
        input_dir=args.input_dir,
        output_dir=args.output_dir,
        input_files=args.input_file,
        review_friction_path=args.review_friction_path,
    )
    logger.info("Rows retained: %s", report["rows_retained"])
    logger.info("Output written: %s", args.output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
