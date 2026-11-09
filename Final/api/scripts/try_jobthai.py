"""One small Apify JobThai run: check salary coverage and description quality (31 Oct task).

Usage (from api/):
    python scripts/try_jobthai.py                      # keyword "programmer", 20 jobs
    python scripts/try_jobthai.py --keyword "data analyst" --max-items 10

Reads APIFY_TOKEN and APIFY_JOBTHAI_ACTOR from the environment or the root `.env`.
Writes the raw items to var/jobthai_sample.json (git-ignored) and prints a short report.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

API_DIR = Path(__file__).resolve().parents[1]
DEFAULT_ACTOR = "mai_amm/jobthai-scraper"
CONTACT_KEYS = ("contacts", "contact", "email", "phone", "line", "lineId")
NUMBER = re.compile(r"\d[\d,]*")


def load_env() -> None:
    """Fill os.environ from the root .env (only keys that are not set already)."""
    for path in (API_DIR.parent / ".env", API_DIR / ".env"):
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            key, sep, value = line.partition("=")
            if sep and not key.strip().startswith("#"):
                os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def run_actor(token: str, actor: str, run_input: dict, timeout_s: int) -> list[dict]:
    url = (
        f"https://api.apify.com/v2/acts/{urllib.parse.quote(actor.replace('/', '~'))}"
        f"/run-sync-get-dataset-items?timeout={timeout_s}"
    )
    request = urllib.request.Request(
        url,
        data=json.dumps(run_input).encode(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_s + 30) as response:  # noqa: S310
            return json.load(response)
    except urllib.error.HTTPError as exc:
        sys.exit(f"Apify returned HTTP {exc.code}: {exc.read().decode(errors='replace')[:500]}")


def salary_numbers(text: str) -> list[int]:
    return [int(n.replace(",", "")) for n in NUMBER.findall(text or "")]


def report(items: list[dict]) -> None:
    jobs = [i for i in items if i.get("title")]
    total = len(jobs) or 1
    with_salary = [j for j in jobs if str(j.get("salary") or "").strip()]
    parsed = [j for j in with_salary if salary_numbers(str(j["salary"]))]
    with_desc = [j for j in jobs if len(str(j.get("description") or "")) >= 200]
    with_qual = [j for j in jobs if j.get("qualifications")]
    leaked = [j for j in jobs if any(j.get(k) for k in CONTACT_KEYS)]

    print(f"\nitems returned     : {len(items)} ({len(jobs)} with a title)")
    print(f"fields             : {sorted({k for j in jobs for k in j})}")
    print(f"salary text present: {len(with_salary)}/{len(jobs)} ({len(with_salary) / total:.0%})")
    print(f"salary has numbers : {len(parsed)}/{len(jobs)} ({len(parsed) / total:.0%})")
    print(f"description >= 200 : {len(with_desc)}/{len(jobs)} ({len(with_desc) / total:.0%})")
    print(f"qualifications     : {len(with_qual)}/{len(jobs)} ({len(with_qual) / total:.0%})")
    print(f"contact fields set : {len(leaked)} (must be 0, FR-22e)")

    print("\nsalary texts:")
    for j in jobs:
        print(f"  - {str(j.get('salary') or '(none)')[:40]:40} | {str(j.get('title'))[:50]}")

    if jobs:
        sample = jobs[0]
        print(f"\nfirst job: {sample.get('title')} @ {sample.get('company')} ({sample.get('url')})")
        print(f"description (first 400 chars):\n{str(sample.get('description') or '')[:400]}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--keyword", default="programmer")
    parser.add_argument("--max-items", type=int, default=20)
    parser.add_argument("--timeout", type=int, default=300, help="seconds to wait for the run")
    parser.add_argument("--no-details", action="store_true", help="skip detail pages (faster)")
    args = parser.parse_args()

    load_env()
    token = os.environ.get("APIFY_TOKEN", "")
    if not token:
        sys.exit("APIFY_TOKEN is not set (put it in the root .env).")
    actor = os.environ.get("APIFY_JOBTHAI_ACTOR") or DEFAULT_ACTOR

    # Design.md §7: Computer/IT job type, details on, contacts off.
    run_input = {
        "mode": "search",
        "keyword": args.keyword,
        "jobTypes": ["7"],
        "language": "th",
        "maxItems": args.max_items,
        "maxPages": 1,
        "includeDetails": not args.no_details,
        "includeContacts": False,
        "proxyConfiguration": {"useApifyProxy": True},
    }
    print(f"running {actor} with {json.dumps(run_input, ensure_ascii=False)}")
    items = run_actor(token, actor, run_input, args.timeout)

    out = API_DIR / "var" / "jobthai_sample.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"saved raw items to {out}")
    report(items)


if __name__ == "__main__":
    main()
