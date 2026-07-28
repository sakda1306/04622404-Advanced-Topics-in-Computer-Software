"""Cleaning + Normalization stage for the job-posting pipeline.

Input is the Collection stage output in Pipeline/outputs/. Two schemas show up
there and both are handled:

    Jobicy      id (int)  -> jobDescription, jobExcerpt
    AIDevBoard  id (str)  -> description

The two entry points are independent and can be called on their own:

    clean(text)     strip HTML, drop boilerplate, drop repeated lines
    normalize(text) Unicode NFC, Thai digits and duplicated Thai marks,
                    whitespace, invisible/control characters

Only the fields in TEXT_FIELDS are rewritten. "id" and every structured field
(title, tags, salary_*, ...) are carried through untouched so the Chunking
stage can map a chunk back to its source posting.
"""

import html
import re
import unicodedata
from collections import Counter

# Text fields across both schemas; a record only has the ones its source uses.
TEXT_FIELDS = ("description", "jobDescription", "jobExcerpt")

# jobExcerpt is the opening of jobDescription, which is usually the company
# blurb, so corpus boilerplate would empty the field out. It still gets HTML
# stripping, in-field dedup and normalization.
KEEP_BOILERPLATE_FIELDS = ("jobExcerpt",)

# A repeated line this short is a section header ("Requirements", "The Role").
# The chunking stage uses those as topic boundaries, so they are kept even
# though they repeat across the corpus.
MAX_HEADING_WORDS = 4

# Job-board tracking codes repeat like boilerplate but carry no meaning, so
# they are dropped regardless of length.
_TRACKING_CODE = re.compile(r"^#[A-Za-z]{2}-\S*$")

# Tags that end a visual block become a line break before all tags are dropped,
# otherwise "<li>a</li><li>b</li>" would collapse into "ab".
_BLOCK_TAG = re.compile(r"</?(?:p|div|br|li|ul|ol|h[1-6]|tr|table|section)\b[^>]*>", re.I)
# Anchored to a tag name or a comment so that prose like "salary < 100k > offer"
# is not mistaken for markup and deleted.
_ANY_TAG = re.compile(r"</?[A-Za-z][^>]*>|<!--.*?-->", re.S)

# Thai digits are folded into Arabic ones, never the other way round, so a
# number reads the same everywhere downstream.
_THAI_DIGITS = str.maketrans("๐๑๒๓๔๕๖๗๘๙", "0123456789")
# Thai vowel signs and tone marks typed more than once ("สวัสดีีี") look the
# same but do not compare equal, and NFC does not merge them.
_DUP_THAI_MARK = re.compile("([ัิ-ฺ็-๎])\\1+")

# Zero-width, bidi marks, line/paragraph separators, soft hyphen, BOM.
_INVISIBLE = re.compile("[­​-‏  ‪-‮⁠﻿]")
# C0/C1 controls, keeping \t and \n.
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")
# Runs of horizontal whitespace, including NBSP and narrow NBSP.
_HORIZONTAL_SPACE = re.compile(r"[^\S\n]+")
_BLANK_LINES = re.compile(r"\n{3,}")


def strip_html(text):
    """Turn an HTML fragment into plain text with one line per block."""
    text = _BLOCK_TAG.sub("\n", text)
    text = _ANY_TAG.sub("", text)
    # Unescape last so that escaped markup is not mistaken for a real tag.
    return html.unescape(text)


def collect_boilerplate(texts, min_docs=5):
    """Return the lines that appear in at least `min_docs` different documents.

    Company blurbs, equal-opportunity statements and benefit lists repeat
    verbatim across postings, so counting documents (not occurrences) picks
    them out without hardcoding any company name. Section headers repeat the
    same way but are structure rather than filler, so short lines are kept
    unless they are a tracking code.
    """
    seen = Counter()
    for text in texts:
        lines = {ln.strip() for ln in strip_html(text).split("\n") if ln.strip()}
        seen.update(lines)
    return frozenset(
        line
        for line, docs in seen.items()
        if docs >= min_docs
        and (len(line.split()) > MAX_HEADING_WORDS or _TRACKING_CODE.match(line))
    )


def clean(text, boilerplate=frozenset()):
    """Strip HTML, drop boilerplate lines, and drop lines repeated in the text.

    `boilerplate` is the set returned by collect_boilerplate() over the whole
    corpus; call clean() without it to skip boilerplate removal.
    """
    kept, seen = [], set()
    for line in strip_html(text).split("\n"):
        line = line.strip()
        if not line or line in boilerplate or line in seen:
            continue
        seen.add(line)
        kept.append(line)
    return "\n".join(kept)


def normalize(text):
    """Unicode NFC, Thai digits and marks, whitespace and invisible characters."""
    text = unicodedata.normalize("NFC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _INVISIBLE.sub("", text)
    text = _CONTROL.sub("", text)
    # After the invisible characters are gone, so that a zero-width space
    # between two identical marks does not hide the repeat.
    text = text.translate(_THAI_DIGITS)
    text = _DUP_THAI_MARK.sub(r"\1", text)
    text = _HORIZONTAL_SPACE.sub(" ", text)
    text = "\n".join(line.strip() for line in text.split("\n"))
    return _BLANK_LINES.sub("\n\n", text).strip()


def process_records(records, boilerplate=frozenset()):
    """Copy `records`, rewriting only the text fields that are present."""
    processed = []
    for record in records:
        updated = dict(record)
        for field in TEXT_FIELDS:
            if isinstance(updated.get(field), str):
                drop = frozenset() if field in KEEP_BOILERPLATE_FIELDS else boilerplate
                updated[field] = normalize(clean(updated[field], drop))
        processed.append(updated)
    return processed
