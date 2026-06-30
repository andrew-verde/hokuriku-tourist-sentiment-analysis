#!/usr/bin/env python3
"""Fail when tracked working-tree files violate public-release guardrails."""

from __future__ import annotations

import csv
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
PRIVATE_SUFFIXES = {".pptx", ".docx"}
PRIVATE_PARTS = {"scratchpad", ".agents", ".codex", ".claude", "architecture_review"}
ROW_LEVEL_COLUMNS = {
    "author", "author_url", "body_text", "comment_text", "note_url", "record_id",
    "review_text", "source_record_id", "text_content", "video_url",
}
PERSONAL_PATH = re.compile(r"/(?:Users|home)/[^/\s]+/")
TEXT_SUFFIXES = {".csv", ".json", ".md", ".py", ".txt", ".yaml", ".yml"}


def tracked_files() -> list[Path]:
    output = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT)
    return [
        ROOT / item.decode()
        for item in output.split(b"\0")
        if item and (ROOT / item.decode()).is_file()
    ]


def violations() -> list[str]:
    failures: list[str] = []
    for path in tracked_files():
        relative = path.relative_to(ROOT)
        if path.suffix.lower() in PRIVATE_SUFFIXES:
            failures.append(f"{relative}: private presentation/document artifact")
        if PRIVATE_PARTS.intersection(relative.parts):
            failures.append(f"{relative}: private agent/review directory")

        if path.suffix.lower() == ".csv":
            with path.open(encoding="utf-8-sig", newline="") as handle:
                header = next(csv.reader(handle), [])
            forbidden = sorted(set(header).intersection(ROW_LEVEL_COLUMNS))
            if forbidden:
                failures.append(
                    f"{relative}: forbidden row-level columns {', '.join(forbidden)}"
                )

        if path.suffix.lower() in TEXT_SUFFIXES:
            text = path.read_text(encoding="utf-8", errors="replace")
            if PERSONAL_PATH.search(text):
                failures.append(f"{relative}: personal absolute path")
    return failures


def main() -> int:
    failures = violations()
    if failures:
        print("Public-release check failed:")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print("Public-release check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
