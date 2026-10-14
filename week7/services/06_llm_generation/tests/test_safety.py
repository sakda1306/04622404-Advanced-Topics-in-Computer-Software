from app.safety.gambling import check_answer, check_query


def test_query_gambling_request_th():
    assert check_query("ขอทีเด็ดบอลวันนี้หน่อย") == "gambling_request"


def test_query_gambling_request_en():
    assert check_query("who should i bet on tonight?") == "gambling_request"


def test_query_normal_not_blocked():
    assert check_query("อาร์เซนอลเมื่อวานชนะไหม") is None


def test_answer_gambling_tips():
    assert check_answer("วันนี้ควรแทงทีมนี้เลย") == "gambling_tips"


def test_answer_promotion():
    assert check_answer("สมัครสมาชิกเว็บพนันรับโบนัส 100%") == "gambling_promotion"


def test_answer_odds_blocked_in_passthrough():
    assert check_answer("อัตราต่อรอง 5/1", allow_context_odds=False) == "gambling_odds"


def test_answer_odds_allowed_in_grounded_context():
    assert (
        check_answer("ก่อนแชมป์เลสเตอร์ถูกตั้งราคา 5000/1", allow_context_odds=True) is None
    )


def test_spaced_evasion_detected():
    assert check_query("ขอ ที เด็ด หน่อย") == "gambling_request"


def test_normal_answer_not_blocked():
    assert check_answer("อาร์เซนอลชนะเชลซี 2-1 [1]") is None
