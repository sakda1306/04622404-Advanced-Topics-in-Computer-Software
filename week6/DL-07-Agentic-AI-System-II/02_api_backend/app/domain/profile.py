"""The user's profile and consents (docs/02_api_spec.md section 7.4, D-76, D-80).

`ProfileChanges` fields that are `None` keep the current value; `explicit_nulls` names
the fields the client set to `null` (optional ones are cleared, required ones rejected).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from datetime import datetime
from zoneinfo import available_timezones

from app.domain.errors import FieldIssue, InvalidInput
from app.domain.normalization import SUPPORTED_LANGUAGES
from app.domain.sanitizer import clean_text

DISPLAY_NAME_MAX_CHARS = 100
_REGION = re.compile(r"^[A-Z]{2}(-[A-Z0-9]{1,3})?$")
_REQUIRED = ("language", "timezone", "consents.live_alerts", "consents.analytics")


@dataclass(frozen=True, slots=True)
class Consents:
    live_alerts: bool
    live_alerts_at: datetime | None
    analytics: bool
    analytics_at: datetime | None


@dataclass(frozen=True, slots=True)
class Profile:
    display_name: str | None
    language: str
    timezone: str
    home_region: str | None
    consents: Consents


@dataclass(frozen=True, slots=True)
class ConsentChanges:
    live_alerts: bool | None = None
    analytics: bool | None = None


@dataclass(frozen=True, slots=True)
class ProfileChanges:
    display_name: str | None = None
    language: str | None = None
    timezone: str | None = None
    home_region: str | None = None
    consents: ConsentChanges | None = None
    explicit_nulls: frozenset[str] = frozenset()


def _consent(
    current: bool, since: datetime | None, change: bool | None, now: datetime
) -> tuple[bool, datetime | None]:
    if change is None:
        return current, since
    if not change:
        return False, None
    return True, since if current and since is not None else now


def _consents(current: Consents, changes: ConsentChanges | None, now: datetime) -> Consents:
    changes = changes or ConsentChanges()
    live, live_at = _consent(current.live_alerts, current.live_alerts_at, changes.live_alerts, now)
    analytics, analytics_at = _consent(
        current.analytics, current.analytics_at, changes.analytics, now
    )
    return Consents(live, live_at, analytics, analytics_at)


def apply_profile_changes(current: Profile, changes: ProfileChanges, *, now: datetime) -> Profile:
    nulls = changes.explicit_nulls
    issues = [
        FieldIssue(name, "required", "this field cannot be null")
        for name in _REQUIRED
        if name in nulls
    ]

    display_name = current.display_name
    if "display_name" in nulls:
        display_name = None
    elif changes.display_name is not None:
        display_name = clean_text(changes.display_name)
        if display_name is not None and len(display_name) > DISPLAY_NAME_MAX_CHARS:
            issues.append(
                FieldIssue(
                    "display_name", "too_long", f"at most {DISPLAY_NAME_MAX_CHARS} characters"
                )
            )

    language = current.language
    if changes.language is not None:
        language = changes.language.strip().lower()
        if language not in SUPPORTED_LANGUAGES:
            issues.append(
                FieldIssue(
                    "language", "unsupported", f"use one of {', '.join(SUPPORTED_LANGUAGES)}"
                )
            )

    timezone = changes.timezone if changes.timezone is not None else current.timezone
    if changes.timezone is not None and changes.timezone not in available_timezones():
        issues.append(FieldIssue("timezone", "unknown_timezone", "use an IANA timezone name"))

    home_region = current.home_region
    if "home_region" in nulls:
        home_region = None
    elif changes.home_region is not None:
        home_region = changes.home_region
        if not _REGION.fullmatch(home_region):
            issues.append(
                FieldIssue("home_region", "invalid", "use an ISO 3166 code such as TH or TH-50")
            )

    if issues:
        raise InvalidInput(issues)
    return replace(
        current,
        display_name=display_name,
        language=language,
        timezone=timezone,
        home_region=home_region,
        consents=_consents(current.consents, changes.consents, now),
    )


def consent_changes(before: Consents, after: Consents) -> dict[str, bool]:
    changed: dict[str, bool] = {}
    if before.live_alerts != after.live_alerts:
        changed["live_alerts"] = after.live_alerts
    if before.analytics != after.analytics:
        changed["analytics"] = after.analytics
    return changed


def mask_email(email: str | None) -> str | None:
    """`sakda@example.com` -> `s***@example.com`; the address itself is never stored."""
    if not email or email.count("@") != 1:
        return None
    local, domain = email.split("@")
    if not local or not domain:
        return None
    return f"{local[0]}***@{domain}"
