"""
Shared provenance helpers for reproducible research outputs.

This module provides utilities to record where every output comes from, what was
computed to produce it, and the data integrity hashes (SHA256) of input and output
files. The goal is reproducibility: anyone should be able to trace an output table
back to its source data and understand exactly which parameters and code created it.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable


REPO_ROOT = Path(__file__).resolve().parent.parent
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
    # Return the current UTC time as an ISO string (for use in manifest timestamps).
    return dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat()


def sha256_file(path: Path) -> str:
    # Compute the SHA256 hash of a file in streaming fashion (reading in 1 MB chunks)
    # so large files don't exhaust memory.
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def repo_relative(path: Path | str) -> str:
    record_path = Path(path)
    if not record_path.is_absolute():
        return record_path.as_posix()
    try:
        return record_path.resolve().relative_to(REPO_ROOT.resolve()).as_posix()
    except ValueError:
        return record_path.as_posix()


def repo_relative_command(command: str | None) -> str | None:
    if command is None:
        return None
    return str(command).replace(f"{REPO_ROOT.resolve().as_posix()}/", "")


def resolve_repo_path(path: Path | str) -> Path:
    record_path = Path(path)
    if record_path.is_absolute():
        return record_path
    return REPO_ROOT / record_path


def file_record(path: Path, role: str, required: bool = False) -> dict[str, Any]:
    # Create a provenance record for a single file: its path, size, and SHA256 hash.
    # If the file is required and missing, raise an error. If it's optional and
    # missing, still include it in the record (marked as not existing).
    record: dict[str, Any] = {
        "role": role,
        "path": repo_relative(path),
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
    # Check that the output table does not contain sensitive row-level columns
    # (review text, author names, IDs, URLs, etc.) that should never be aggregated
    # or published. Raise an error if any are found.
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
    # Create the core provenance manifest: a structured record that documents
    # what operation ran, what inputs it read, what outputs it wrote, any filters
    # or parameters applied, and key metrics/caveats about the result.
    manifest: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": kind,
        "generated_at": generated_at or utc_now_iso(),
        "command": repo_relative_command(command),
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
    # Write a data structure to a JSON file with proper UTF-8 encoding and
    # human-readable indentation.
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
