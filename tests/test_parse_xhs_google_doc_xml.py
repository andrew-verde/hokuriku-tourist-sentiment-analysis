import csv
from pathlib import Path

from scripts.parse_xhs_google_doc_xml import parse_document


def _write_word_xml(path: Path, paragraphs: list[str]) -> None:
    body = "".join(
        f'<w:p><w:r><w:t>{text}</w:t></w:r></w:p>'
        for text in paragraphs
    )
    path.write_text(
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<pkg:package xmlns:pkg="http://schemas.microsoft.com/office/2006/xmlPackage">'
        '<pkg:part pkg:name="/word/document.xml">'
        '<pkg:xmlData>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{body}</w:body>"
        "</w:document>"
        "</pkg:xmlData>"
        "</pkg:part>"
        "</pkg:package>",
        encoding="utf-8",
    )


def test_parse_document_splits_posts_and_comments_with_index_anchor(tmp_path):
    xml_path = tmp_path / "xhs.xml"
    _write_word_xml(
        xml_path,
        [
            "XHS NOTES DATA",
            "福井一日游",
            "东寻坊很美",
            "#福井",
            "2025-10-01",
            "共 2 条评论",
            "旅人甲",
            "真好看",
            "2025-10-02",
            "赞",
            "作者号",
            "作者",
            "谢谢",
            "2025-10-02",
            "回复",
            "永平寺慢旅行",
            "寺庙很安静",
            "编辑于 2025-09-01",
        ],
    )
    index_path = tmp_path / "index.csv"
    with index_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["note_id", "title", "note_url", "author", "author_url"])
        writer.writeheader()
        writer.writerow({
            "note_id": "n2",
            "title": "永平寺慢旅行",
            "note_url": "https://example.test/n2",
            "author": "author 2025-09-01",
            "author_url": "https://example.test/u2",
        })

    posts, comments, summary = parse_document(xml_path, index_path)

    assert summary["posts"] == 2
    assert posts[0]["doc_title"] == "福井一日游"
    assert posts[0]["post_date_raw"] == "2025-10-01"
    assert posts[0]["parsed_comment_count"] == "2"
    assert posts[0]["parser_warnings"] == "no_index_match"
    assert posts[1]["note_id"] == "n2"
    assert posts[1]["boundary_match_type"] == "exact_title"
    assert comments[0]["comment_author_raw"] == "旅人甲"
    assert comments[0]["comment_text"] == "真好看"
    assert comments[1]["is_author_reply"] == "true"
    assert comments[1]["comment_text"] == "谢谢"
