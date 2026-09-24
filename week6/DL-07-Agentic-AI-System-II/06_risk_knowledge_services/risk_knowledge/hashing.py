"""Content hash for a retrieved passage.

Module 07's emergency catalog matches a reviewed procedure to retrieved evidence by
comparing this hash, so the match no longer depends on how this module lays out the
excerpt for display. This is a deliberate copy of `decision_engine/hashing.py`: Module 06
does not import Module 07 at runtime, and both copies must stay byte-identical in
behaviour. Module 07's `tests/test_sibling_contracts.py` checks that they agree.
"""

from __future__ import annotations

import hashlib
import unicodedata

CONTENT_HASH_VERSION = "content-sha256-v1"


def normalise_text(text: str) -> str:
    """NFC, collapse every run of whitespace to one space, strip the ends."""
    return " ".join(unicodedata.normalize("NFC", text).split())


def content_sha256(text: str) -> str:
    """The hash a reviewer records for this passage and Module 07 compares against."""
    return hashlib.sha256(normalise_text(text).encode("utf-8")).hexdigest()
