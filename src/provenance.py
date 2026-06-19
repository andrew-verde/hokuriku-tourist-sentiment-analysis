"""Shared provenance helpers for reproducible research outputs."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable


SCHEMA_VERSION = "research_provenance.v1"

FORBIDDEN_ROW_LEVEL_COLUMNS = {
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


class ProvenanceError(RuntimeError):
    pass


def utc_now_iso() -> str:
    return dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_record(path: Path, role: str, required: bool = False) -> dict[str, Any]:
    record: dict[str, Any] = {
        "role": role,
        "path": str(path),
        "exists": path.exists(),
    }
    if not path.exists():
        if required:
            raise ProvenanceError(f"Required provenance file missing: {path}")
        return record
    if path.is_file():
        record["bytes"] = path.stat().st_size
        record["sha256"] = sha256_file(path)
    return record


def assert_no_forbidden_columns(
    columns: Iterable[str],
    forbidden: set[str] | None = None,
    context: str = "aggregate output",
) -> None:
    blocked = sorted((forbidden or FORBIDDEN_ROW_LEVEL_COLUMNS) & set(columns))
    if blocked:
        raise ProvenanceError(
            f"{context} contains forbidden row-level/PII columns: {', '.join(blocked)}"
        )


def research_manifest(
    kind: str,
    command: str | None,
    inputs: list[dict[str, Any]],
    outputs: list[dict[str, Any]],
    filters: dict[str, Any] | None = None,
    metrics: dict[str, Any] | None = None,
    caveats: list[str] | None = None,
    extra: dict[str, Any] | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    manifest: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": kind,
        "generated_at": generated_at or utc_now_iso(),
        "command": command,
        "inputs": inputs,
        "outputs": outputs,
        "filters": filters or {},
        "metrics": metrics or {},
        "caveats": caveats or [],
    }
    if extra:
        manifest["extra"] = extra
    return manifest


def write_json(path: Path, payload: dict[str, Any] | list[dict[str, Any]]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
