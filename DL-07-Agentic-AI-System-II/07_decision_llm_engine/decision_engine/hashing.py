"""How a reviewed passage is identified by content, for Modules 06, 07 and reviewers.

The emergency catalog used to store a hash of the excerpt string that Module 06 composes
for display. That tied every reviewed procedure to 06's formatting: a changed prefix, a
missing page number or a different Unicode spelling of the same Thai text silently broke
the match, and the decision fell back without anyone noticing.

This module hashes the *content* instead: the passage text after Unicode NFC
normalisation and whitespace collapsing. Module 06 computes it over the passage in its
corpus, the reviewer computes it over the same passage at review time, and Module 07 only
ever compares two hashes. Nobody re-derives a hash from presentation text.

Module 06 cannot import this package, so it keeps a copy of `normalise_text`; both copies
must stay identical, and `tests/test_sibling_contracts.py` checks that they agree.
"""

from __future__ import annotations

import hashlib
import unicodedata

CONTENT_HASH_VERSION = "content-sha256-v1"


def normalise_text(text: str) -> str:
    """NFC, collapse every run of whitespace to one space, strip the ends."""
    return " ".join(unicodedata.normalize("NFC", text).split())


def content_sha256(text: str) -> str:
    """The hash a catalog stores and Module 06 reports for the same passage."""
    return hashlib.sha256(normalise_text(text).encode("utf-8")).hexdigest()
