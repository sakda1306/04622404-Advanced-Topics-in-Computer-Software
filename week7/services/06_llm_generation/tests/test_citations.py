from app.citations import (
    extract_cited_refs,
    normalize_citations,
    strip_all_citations,
    strip_invalid_citations,
)


def test_normalize_bracket_list():
    assert normalize_citations("ข้อความ [1, 2] จบ") == "ข้อความ [1][2] จบ"


def test_normalize_fullwidth():
    assert normalize_citations("ข้อความ【1】จบ") == "ข้อความ[1]จบ"


def test_markdown_link_not_touched():
    text = "ดูที่ [กูเกิล](https://google.com) สิ"
    assert normalize_citations(text) == text
    assert extract_cited_refs(text) == []


def test_extract_refs_dedup_order():
    assert extract_cited_refs("a[2]b[1]c[2]") == [2, 1]


def test_strip_invalid_citations():
    text, removed = strip_invalid_citations("สกอร์ [1] และ [9]", {1})
    assert removed == 1
    assert "[9]" not in text
    assert "[1]" in text


def test_strip_all_citations():
    assert "[" not in strip_all_citations("a[1]b[2]")


def test_no_citation_case():
    text = "ไม่มีการอ้างอิงเลย"
    assert extract_cited_refs(text) == []
