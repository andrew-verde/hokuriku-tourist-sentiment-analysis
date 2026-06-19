#!/usr/bin/env python3
"""Parse manually copied Xiaohongshu note text from a Google Docs Word XML export.

This is a salvage parser for a noisy manual-capture format. It extracts
paragraphs from a Word XML package, anchors post boundaries to an optional
title-only XHS CSV, separates note text from copied comments at "共 N 条评论"
markers, and writes ignored intermediate CSVs for review.
"""

from __future__ import annotations

import argparse
import csv
import dataclasses
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SOURCE = ROOT / "docs" / "codebook_reviews" / "source" / "XHS_NOTES_DATA_v1.xml"
DEFAULT_INDEX = Path("/Users/andrewgreen/Repositories/tourism-data/data/raw/social/fukui_xhs_reviews.csv")
DEFAULT_OUTPUT_DIR = ROOT / "data" / "interim" / "xhs_google_doc_parse"

PKG_NS = "http://schemas.microsoft.com/office/2006/xmlPackage"
W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"pkg": PKG_NS, "w": W_NS}

COMMENT_COUNT_RE = re.compile(r"^共\s*(?P<count>\d+)\s*条评论$")
FULL_DATE_RE = re.compile(r"^(编辑于\s*)?\d{4}-\d{2}-\d{2}$")
DATEISH_RE = re.compile(
    r"^(编辑于\s*)?\d{4}-\d{2}-\d{2}$"
    r"|^\d{1,2}-\d{1,2}[\u4e00-\u9fff]{0,6}$"
    r"|^(今天|昨天|前天)(\s+\d{1,2}:\d{2})?[\u4e00-\u9fff]{0,6}$"
    r"|^\d+\s*(秒前|分钟前|小时前|天前|周前|月前|年前)[\u4e00-\u9fff]{0,6}$"
    r"|^\d+天前\s+\S+$"
)
UI_LINE_RE = re.compile(r"^(赞|回复|作者|展开\s*\d+\s*条回复|\d+)$")
IMAGE_PLACEHOLDER = "\ufffc"


@dataclasses.dataclass
class IndexRow:
    note_id: str = ""
    title: str = ""
    note_url: str = ""
    author: str = ""
    author_url: str = ""


@dataclasses.dataclass
class MatchedStart:
    paragraph_index: int
    index_row: IndexRow | None
    match_type: str


def normalize_text(value: str) -> str:
    # Collapse repeated whitespace so copied lines compare more reliably.
    return re.sub(r"\s+", " ", value).strip()


def normalize_for_match(value: str) -> str:
    # Strip spaces and punctuation before comparing a document title to the index title.
    value = normalize_text(value).lower()
    return re.sub(r"[\s\W_]+", "", value)


def extract_paragraphs(xml_path: Path) -> list[str]:
    # Word XML stores the document body inside a package part, so we read that part only.
    root = ET.parse(xml_path).getroot()
    for part in root.findall(".//pkg:part", NS):
        if part.attrib.get(f"{{{PKG_NS}}}name") != "/word/document.xml":
            continue
        paragraphs: list[str] = []
        for paragraph in part.findall(".//w:body/w:p", NS):
            text = "".join(node.text or "" for node in paragraph.findall(".//w:t", NS))
            text = normalize_text(text)
            if text and text != IMAGE_PLACEHOLDER:
                paragraphs.append(text)
        return paragraphs
    raise ValueError(f"Could not find /word/document.xml in {xml_path}")


def load_xhs_index(path: Path | None) -> list[IndexRow]:
    if path is None:
        return []
    # The index file is an optional anchor for matching noisy Google Doc paragraphs.
    with path.open(encoding="utf-8-sig", newline="") as f:
        return [
            IndexRow(
                note_id=normalize_text(row.get("note_id", "")),
                title=normalize_text(row.get("title", "")),
                note_url=normalize_text(row.get("note_url", "")),
                author=normalize_text(row.get("author", "")),
                author_url=normalize_text(row.get("author_url", "")),
            )
            for row in csv.DictReader(f)
        ]


def _match_title(paragraph: str, index_rows: list[IndexRow]) -> tuple[IndexRow | None, str]:
    normalized_paragraph = normalize_for_match(paragraph)
    if not normalized_paragraph:
        return None, ""
    for row in index_rows:
        normalized_title = normalize_for_match(row.title)
        if normalized_title and normalized_paragraph == normalized_title:
            return row, "exact_title"
    for row in index_rows:
        normalized_title = normalize_for_match(row.title)
        if len(normalized_title) >= 8 and (
            normalized_title in normalized_paragraph or normalized_paragraph in normalized_title
        ):
            return row, "partial_title"
    return None, ""


def find_post_starts(paragraphs: list[str], index_rows: list[IndexRow]) -> list[MatchedStart]:
    starts: list[MatchedStart] = []
    seen_positions: set[int] = set()
    # The first real content block starts after the optional document heading.
    first_content_index = 1 if paragraphs and paragraphs[0].upper() == "XHS NOTES DATA" else 0
    if first_content_index < len(paragraphs):
        starts.append(MatchedStart(first_content_index, None, "document_start"))
        seen_positions.add(first_content_index)

    for i, paragraph in enumerate(paragraphs):
        row, match_type = _match_title(paragraph, index_rows)
        if row is None or i in seen_positions:
            continue
        starts.append(MatchedStart(i, row, match_type))
        seen_positions.add(i)

    return sorted(starts, key=lambda item: item.paragraph_index)


def _post_date(body_lines: list[str]) -> str:
    for line in reversed(body_lines):
        if FULL_DATE_RE.match(line) or DATEISH_RE.match(line):
            return re.sub(r"^编辑于\s*", "", line)
    return ""


def _body_without_terminal_date(body_lines: list[str]) -> list[str]:
    if body_lines and (FULL_DATE_RE.match(body_lines[-1]) or DATEISH_RE.match(body_lines[-1])):
        return body_lines[:-1]
    return body_lines


def split_segment(lines: list[str]) -> tuple[list[str], int | None, list[str]]:
    # A copied note may include a comment-count marker that separates post text from comments.
    for i, line in enumerate(lines):
        match = COMMENT_COUNT_RE.match(line)
        if match:
            return lines[:i], int(match.group("count")), lines[i + 1 :]
    return lines, None, []


def parse_comment_lines(comment_lines: list[str]) -> list[dict[str, str]]:
    comments: list[dict[str, str]] = []
    pending: list[str] = []

    def content_parts(lines: list[str]) -> list[str]:
        # Remove UI labels like "赞" and keep the actual author/text tokens.
        return [line for line in lines if line == "作者" or not UI_LINE_RE.match(line)]

    def flush(date_raw: str) -> None:
        nonlocal pending
        parts = content_parts(pending)
        pending = []
        if not parts:
            return
        author_raw = parts[0]
        is_author_reply = len(parts) > 1 and parts[1] == "作者"
        text_parts = parts[2:] if is_author_reply else parts[1:]
        comment_text = " ".join(text_parts).strip()
        comments.append({
            "comment_author_raw": author_raw,
            "is_author_reply": "true" if is_author_reply else "false",
            "comment_text": comment_text,
            "comment_date_raw": date_raw,
            "comment_parse_quality": "ok" if comment_text else "missing_text",
        })

    for line in comment_lines:
        if DATEISH_RE.match(line):
            flush(line)
            continue
        if UI_LINE_RE.match(line) and not pending:
            continue
        pending.append(line)

    if pending:
        parts = content_parts(pending)
        if parts:
            author_raw = parts[0]
            comment_text = " ".join(parts[1:]).strip()
            comments.append({
                "comment_author_raw": author_raw,
                "is_author_reply": "false",
                "comment_text": comment_text,
                "comment_date_raw": "",
                "comment_parse_quality": "missing_date" if comment_text else "missing_text_and_date",
            })
    return comments


def parse_document(xml_path: Path, index_path: Path | None = DEFAULT_INDEX) -> tuple[list[dict[str, str]], list[dict[str, str]], dict[str, int]]:
    # Build post rows and comment rows from the same paragraph stream.
    paragraphs = extract_paragraphs(xml_path)
    index_rows = load_xhs_index(index_path) if index_path and index_path.exists() else []
    starts = find_post_starts(paragraphs, index_rows)
    if not starts:
        raise ValueError("No post starts found. Provide --xhs-index to anchor noisy Google Doc paragraphs.")

    posts: list[dict[str, str]] = []
    comments: list[dict[str, str]] = []
    for post_seq, start in enumerate(starts, start=1):
        end = starts[post_seq].paragraph_index if post_seq < len(starts) else len(paragraphs)
        segment = paragraphs[start.paragraph_index:end]
        body_lines, copied_comment_count, comment_lines = split_segment(segment)
        clean_body = _body_without_terminal_date(body_lines)
        title = body_lines[0] if body_lines else ""
        body_text = "\n".join(clean_body).strip()
        parsed_comments = parse_comment_lines(comment_lines)

        warnings = []
        if start.index_row is None:
            warnings.append("no_index_match")
        if copied_comment_count is not None and parsed_comments and copied_comment_count != len(parsed_comments):
            warnings.append("copied_comment_count_mismatch")
        if copied_comment_count is None and comment_lines:
            warnings.append("comment_lines_without_marker")
        if len(clean_body) <= 1:
            warnings.append("short_or_missing_body")

        row = start.index_row or IndexRow(title=title)
        post_key = row.note_id or f"doc_post_{post_seq:04d}"
        posts.append({
            "post_seq": str(post_seq),
            "post_key": post_key,
            "note_id": row.note_id,
            "note_url": row.note_url,
            "index_title": row.title,
            "doc_title": title,
            "index_author_raw": row.author,
            "index_author_url": row.author_url,
            "post_date_raw": _post_date(body_lines),
            "post_text": body_text,
            "copied_comment_count": "" if copied_comment_count is None else str(copied_comment_count),
            "parsed_comment_count": str(len(parsed_comments)),
            "boundary_match_type": start.match_type,
            "source_paragraph_start": str(start.paragraph_index + 1),
            "source_paragraph_end": str(end),
            "parser_warnings": ";".join(warnings),
        })

        for comment_seq, comment in enumerate(parsed_comments, start=1):
            comments.append({
                "post_seq": str(post_seq),
                "post_key": post_key,
                "comment_seq": str(comment_seq),
                **comment,
            })

    summary = {
        "paragraphs": len(paragraphs),
        "index_rows": len(index_rows),
        "posts": len(posts),
        "posts_with_index_match": sum(1 for post in posts if post["note_id"]),
        "comments": len(comments),
        "comment_markers": sum(1 for paragraph in paragraphs if COMMENT_COUNT_RE.match(paragraph)),
        "warning_posts": sum(1 for post in posts if post["parser_warnings"]),
    }
    return posts, comments, summary


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    # Write the parsed rows as a normal UTF-8 CSV file, creating parent folders if needed.
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys()) if rows else []
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--xhs-index", type=Path, default=DEFAULT_INDEX)
    parser.add_argument("--no-index", action="store_true", help="Parse without the title-only XHS CSV anchor.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args(argv)

    index_path = None if args.no_index else args.xhs_index
    posts, comments, summary = parse_document(args.source, index_path)
    write_csv(args.output_dir / "xhs_doc_posts.csv", posts)
    write_csv(args.output_dir / "xhs_doc_comments.csv", comments)
    print(
        "Parsed {posts} posts and {comments} comments from {paragraphs} paragraphs; "
        "{warning_posts} posts carry parser warnings.".format(**summary)
    )
    print(f"Wrote {args.output_dir / 'xhs_doc_posts.csv'}")
    print(f"Wrote {args.output_dir / 'xhs_doc_comments.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
