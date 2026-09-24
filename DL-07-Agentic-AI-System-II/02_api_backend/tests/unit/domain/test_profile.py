from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import pytest

from app.domain.errors import InvalidInput
from app.domain.profile import (
    ConsentChanges,
    Consents,
    Profile,
    ProfileChanges,
    apply_profile_changes,
    consent_changes,
    mask_email,
)

NOW = datetime(2026, 9, 18, 8, 0, tzinfo=UTC)
EARLIER = datetime(2026, 9, 1, tzinfo=UTC)
OFF = Consents(live_alerts=False, live_alerts_at=None, analytics=False, analytics_at=None)
BASE = Profile(
    display_name="Sakda", language="th", timezone="Asia/Bangkok", home_region=None, consents=OFF
)


def apply(changes: ProfileChanges, current: Profile = BASE) -> Profile:
    return apply_profile_changes(current, changes, now=NOW)


def issues(changes: ProfileChanges) -> dict[str, str]:
    with pytest.raises(InvalidInput) as info:
        apply(changes)
    return {i.field: i.code for i in info.value.issues}


def test_fields_are_cleaned_and_kept() -> None:
    result = apply(ProfileChanges(display_name="  Nok\x00 ", home_region="TH-50"))

    assert result.display_name == "Nok"
    assert result.home_region == "TH-50"
    assert result.language == "th"
    assert result.timezone == "Asia/Bangkok"


def test_blank_or_null_display_name_clears_it() -> None:
    assert apply(ProfileChanges(display_name="   ")).display_name is None
    assert apply(ProfileChanges(explicit_nulls=frozenset({"display_name"}))).display_name is None


def test_null_home_region_clears_it() -> None:
    current = replace(BASE, home_region="TH")
    changes = ProfileChanges(explicit_nulls=frozenset({"home_region"}))
    assert apply(changes, current).home_region is None


def test_validation() -> None:
    assert issues(
        ProfileChanges(
            display_name="x" * 101, language="fr", timezone="Mars/Base", home_region="thailand"
        )
    ) == {
        "display_name": "too_long",
        "language": "unsupported",
        "timezone": "unknown_timezone",
        "home_region": "invalid",
    }


def test_required_fields_cannot_be_null() -> None:
    nulls = frozenset({"language", "timezone", "consents.analytics"})
    assert issues(ProfileChanges(explicit_nulls=nulls)) == {
        "language": "required",
        "timezone": "required",
        "consents.analytics": "required",
    }


def test_language_is_normalized() -> None:
    assert apply(ProfileChanges(language="EN")).language == "en"


def test_consent_on_off_and_unchanged() -> None:
    on = apply(ProfileChanges(consents=ConsentChanges(live_alerts=True, analytics=True)))
    assert on.consents == Consents(True, NOW, True, NOW)

    earlier = replace(BASE, consents=Consents(True, EARLIER, True, EARLIER))
    still = apply(ProfileChanges(consents=ConsentChanges(live_alerts=True)), earlier)
    assert still.consents.live_alerts_at == EARLIER

    off = apply(ProfileChanges(consents=ConsentChanges(analytics=False)), earlier)
    assert off.consents == Consents(True, EARLIER, False, None)


def test_consent_changes() -> None:
    after = Consents(True, NOW, False, None)
    assert consent_changes(OFF, after) == {"live_alerts": True}
    assert consent_changes(OFF, OFF) == {}


def test_input_is_not_changed() -> None:
    before = replace(BASE)
    apply(ProfileChanges(display_name="Other", consents=ConsentChanges(analytics=True)))
    assert before == BASE


@pytest.mark.parametrize(
    ("email", "masked"),
    [
        ("sakda@example.com", "s***@example.com"),
        ("a@example.com", "a***@example.com"),
        ("not-an-email", None),
        ("@example.com", None),
        (None, None),
    ],
)
def test_mask_email(email: str | None, masked: str | None) -> None:
    assert mask_email(email) == masked
