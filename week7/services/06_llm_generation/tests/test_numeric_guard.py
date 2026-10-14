from app.numeric_guard import check_score_mismatch, find_score_claims, normalize_text


def test_normalize_thai_digits():
    assert normalize_text("๒-๑") == "2-1"


def test_normalize_dashes():
    assert normalize_text("2–1") == "2-1"
    assert normalize_text("2—1") == "2-1"


def test_normalize_comma():
    assert normalize_text("1,996") == "1996"


def test_score_match_correct():
    assert check_score_mismatch("อาร์เซนอลชนะ 2-1 [1]", {(2, 1)}) == []


def test_score_reversed_ok():
    # กลับด้าน (b-a) ถือว่าตรงตาม spec เพื่อกันความคลุมเครือเหย้า/เยือนใน mismatch check
    assert check_score_mismatch("2-1", {(1, 2)}) == []


def test_score_mismatch_detected():
    mismatches = check_score_mismatch("อาร์เซนอลชนะ 3-0 [1]", {(2, 1)})
    assert (3, 0) in mismatches


def test_year_not_treated_as_score():
    claims = find_score_claims("ฤดูกาล 2026/27 นัดที่ 5")
    assert claims == []


def test_time_not_treated_as_score():
    claims = find_score_claims("นัดเริ่ม 18:30 น.")
    assert claims == []


def test_matchweek_not_treated_as_score():
    claims = find_score_claims("matchweek 5")
    assert claims == []


def test_citation_number_ignored():
    claims = find_score_claims("อ้างอิง [1] เพียงอย่างเดียว")
    assert claims == []
