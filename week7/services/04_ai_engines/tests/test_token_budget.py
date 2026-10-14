from app.token_budget import estimate_tokens, trim_history_to_budget


def test_estimate_tokens_scales_with_length():
    assert estimate_tokens("") == 0
    assert estimate_tokens("hi") >= 1
    assert estimate_tokens("a" * 220) > estimate_tokens("a" * 22)


def test_trim_history_keeps_most_recent_first():
    history = [
        {"role": "user", "content": "message " + str(i) * 50}
        for i in range(20)
    ]
    trimmed = trim_history_to_budget(
        history, system_prompt="sys", query="q", max_input_tokens=200
    )
    # เหลือน้อยกว่าเดิม และข้อความสุดท้าย (ใหม่สุด) ต้องยังอยู่
    assert len(trimmed) < len(history)
    assert trimmed[-1] == history[-1]


def test_trim_history_noop_when_under_budget():
    history = [{"role": "user", "content": "short"}]
    trimmed = trim_history_to_budget(
        history, system_prompt="sys", query="q", max_input_tokens=5000
    )
    assert trimmed == history


def test_trim_history_can_drop_everything_if_query_alone_is_huge():
    history = [{"role": "user", "content": "short message"}]
    trimmed = trim_history_to_budget(
        history, system_prompt="sys", query="x" * 5000, max_input_tokens=200
    )
    assert trimmed == []
