"""JobThai postings through an Apify actor (Design.md §7, PRD FR-22c, FR-22e, FR-22f).

The source is unofficial and each result is paid for, so only the seed and the scheduled refresh
call this. User actions always read the cache (FR-22b).
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

import httpx

from app.providers.base import Posting, ProviderError

DEFAULT_ACTOR = "mai_amm/jobthai-scraper"
JOB_TYPE_COMPUTER_IT = "7"
PROVINCE_BANGKOK = "bangkok"
RUN_TIMEOUT_S = 300


def _text(item: dict[str, Any], key: str) -> str:
    value = item.get(key)
    return value.strip() if isinstance(value, str) else ""


def _posting(item: dict[str, Any]) -> Posting | None:
    title, url = _text(item, "title"), _text(item, "url")
    if not title or not url:
        return None
    return Posting(
        source="jobthai",
        title=title,
        company=_text(item, "company"),
        location=_text(item, "location"),
        province=_text(item, "province"),
        salary_text=_text(item, "salary"),
        posted_text=_text(item, "updatedAtText"),
        url=url,
        text=f"{_text(item, 'description')}\n{_text(item, 'qualifications')}",
    )


class ApifyJobThaiProvider:
    name = "apify_jobthai"

    def __init__(
        self, token: str, actor: str = "", *, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        self._token = token
        self._actor = actor or DEFAULT_ACTOR
        self._transport = transport

    async def fetch_postings(self, keyword: str, limit: int) -> list[Posting]:
        if not self._token:
            raise ProviderError("no_token")
        actor = quote(self._actor.replace("/", "~"))
        url = (
            f"https://api.apify.com/v2/acts/{actor}/run-sync-get-dataset-items"
            f"?timeout={RUN_TIMEOUT_S}"
        )
        run_input = {
            "mode": "search",
            "keyword": keyword,
            "jobTypes": [JOB_TYPE_COMPUTER_IT],
            "province": PROVINCE_BANGKOK,
            "language": "th",
            "maxItems": limit,
            "maxPages": 1,
            "includeDetails": True,
            "includeContacts": False,
            "proxyConfiguration": {"useApifyProxy": True},
        }
        headers = {"Authorization": f"Bearer {self._token}"}
        try:
            async with httpx.AsyncClient(
                timeout=RUN_TIMEOUT_S + 30, transport=self._transport
            ) as client:
                response = await client.post(url, json=run_input, headers=headers)
        except httpx.TimeoutException as exc:
            raise ProviderError("timeout") from exc
        except httpx.HTTPError as exc:
            raise ProviderError("network") from exc
        if response.status_code >= 300:
            raise ProviderError(f"http_{response.status_code}")
        try:
            items = response.json()
        except ValueError as exc:
            raise ProviderError("bad_response") from exc
        if not isinstance(items, list):
            raise ProviderError("bad_response")
        postings = [_posting(item) for item in items if isinstance(item, dict)]
        return [posting for posting in postings if posting is not None]
