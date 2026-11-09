"""All router layers in order, cheapest first (Design.md §4.6)."""

from __future__ import annotations

import re
from collections.abc import Sequence

from app.infra.jev import JevClient
from app.infra.llm import GroqClient
from app.router.decision import Decision, normalize
from app.router.guards import check_guards
from app.router.llm_decision import ask_router_model
from app.router.rules import RULE_CONFIDENCE, is_question, match_rules
from app.router.small_talk import small_talk_kind

# Answered from cached role data, so a user without a profile can ask them.
_NEEDS_NO_PROFILE = frozenset({"salary", "market"})
_A_SALARY_FIGURE = re.compile(r"\d{4,}")


async def decide(
    message: str,
    *,
    has_profile: bool,
    llm: GroqClient,
    user_id: str | None = None,
    recent: Sequence[dict[str, str]] = (),
    jev: JevClient | None = None,
) -> Decision:
    guarded = check_guards(message)
    if guarded is not None:
        return guarded
    text = normalize(message)
    matched = match_rules(text)
    if not has_profile:  # chat first fills the missing completeness slots (FR-8)
        # "เงินเดือน 35000" answers our goals question, so only a real question goes to salary.
        asks = is_question(text) and not _A_SALARY_FIGURE.search(text)
        if matched is not None and matched.route in _NEEDS_NO_PROFILE and asks:
            return matched
        return Decision(route="gap_question", confidence=RULE_CONFIDENCE, layer="rules")
    kind = small_talk_kind(text)
    # "ลบบัญชี" also reads as an edit, and the profile edit cannot do it.
    if kind is not None and (matched is None or kind == "account"):
        return Decision(route="small_talk", confidence=RULE_CONFIDENCE, layer="rules")
    return matched or await ask_router_model(
        message, llm=llm, jev=jev, user_id=user_id, recent=recent
    )
