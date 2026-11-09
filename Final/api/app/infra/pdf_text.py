"""Text lines from a PDF CV (PRD FR-2, FR-4). OCR is out of scope: no text layer → CV_UNREADABLE.

The PDF comes from the user, so parsing is bounded (page count, characters) and any parser
error is reported as unreadable instead of a 500.
"""

from __future__ import annotations

import io
import logging
import re
import unicodedata

from pypdf import PdfReader

from app.core.errors import AppError, ErrorCode

# A CV with less text than this is treated as scanned (images only).
MIN_TEXT_CHARS = 30
MAX_TEXT_CHARS = 100_000
_SPACES = re.compile(r"[ \t ]+")
_THAI = r"[฀-๿]"
_SPACE_BEFORE_THAI_DOT = re.compile(rf"(?<={_THAI})\s+\.")
_SPACE_AFTER_THAI_DOT = re.compile(rf"\.\s+(?={_THAI})")

# pypdf logs warnings about odd PDFs; they would carry nothing useful and may be noisy.
logging.getLogger("pypdf").setLevel(logging.ERROR)


def clean_line(text: str) -> str:
    """Make one extracted line safe to store and easier to parse.

    - NUL is dropped: some Thai fonts map upper vowels and tone marks to it ("ชื" + NUL + "อ"),
      and Postgres JSONB refuses it. The mark is lost; the user fixes it in the confirm step.
    - Other control characters become spaces; zero-width characters are dropped.
    - NIKHAHIT + SARA AA ("ํา") becomes SARA AM ("ำ").
    - Spaces around the dots of Thai abbreviations are closed ("เม . ย ." → "เม.ย.").
    """
    chars = []
    for ch in text:
        category = unicodedata.category(ch)
        if ch == "\x00" or category == "Cf":
            continue
        chars.append(" " if category == "Cc" else ch)
    line = "".join(chars).replace("ํา", "ำ")
    line = _SPACE_BEFORE_THAI_DOT.sub(".", line)
    line = _SPACE_AFTER_THAI_DOT.sub(".", line)
    return _SPACES.sub(" ", line).strip()


def extract_lines(data: bytes, *, max_pages: int) -> list[str]:
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted or len(reader.pages) > max_pages:
            raise AppError(ErrorCode.CV_UNREADABLE)
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
    except AppError:
        raise
    except Exception as exc:  # any parser error on user input means "cannot read it"
        raise AppError(ErrorCode.CV_UNREADABLE) from exc

    lines = [clean_line(line) for line in text[:MAX_TEXT_CHARS].splitlines()]
    lines = [line for line in lines if line]
    if sum(len(line) for line in lines) < MIN_TEXT_CHARS:
        raise AppError(ErrorCode.CV_UNREADABLE)
    return lines
