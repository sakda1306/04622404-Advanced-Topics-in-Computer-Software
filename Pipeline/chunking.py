"""Chunking stage for the job-posting pipeline.

Input is the Cleaning stage output in Pipeline/outputs/cleaned_*.json. The two
schemas from Collection survive into this stage and both are handled:

    Jobicy      id (int)  -> jobDescription, jobExcerpt
    AIDevBoard  id (str)  -> description

Three strategies are available and are chosen per call, not hardcoded:

    fixed       token windows of max_tokens with an overlap tail
    paragraph   one chunk per paragraph, neighbours packed up to max_tokens
    heading     one chunk per section, cut on the short heading lines that the
                Cleaning stage deliberately kept

Whatever the strategy, a unit that is still longer than max_tokens is cut with
the fixed-size splitter, so no chunk can exceed the limit.

Every chunk carries the source record's "id" *and* its source. The id spaces do
not line up across files (Jobicy numbers its postings, AIDevBoard uses a UUID),
so an id on its own cannot be resolved back to a posting; the pair can. The
text itself is passed through untouched, since Cleaning already stripped HTML,
removed boilerplate and normalized Unicode and whitespace.
"""

import functools
import math
import re
from collections import Counter

# Main body field per schema; a record only has the one its source uses.
BODY_FIELDS = ("jobDescription", "description")

# Metadata copied onto every chunk so a retrieved chunk can be displayed and
# traced without reopening the source file. Both schemas map onto the same
# keys. jobExcerpt rides along here rather than being chunked: it is the
# opening of jobDescription, so chunking it would emit a near-duplicate of the
# first chunk and compete with it at retrieval time.
METADATA_ALIASES = {
    "title": ("jobTitle", "title"),
    "company": ("companyName", "company_name"),
    "url": ("url",),
    "excerpt": ("jobExcerpt",),
}

DEFAULT_MAX_TOKENS = 500
DEFAULT_OVERLAP = 50

# A chunk shorter than this is not worth retrieving on its own, see
# _absorb_stubs(). Ten percent of the default chunk size.
DEFAULT_MIN_TOKENS = 50

# The same threshold the Cleaning stage used to protect short lines from
# boilerplate removal. Those lines ("Requirements", "The Role") were kept for
# this stage to cut sections on.
MAX_HEADING_WORDS = 4

# A heading has to be seen in at least this many different documents before it
# counts as one, see collect_headings().
DEFAULT_MIN_HEADING_DOCS = 3

# cl100k_base is the encoding of the OpenAI text-embedding-3 and ada-002
# models, so "500 tokens" here means the same number the embedding stage will
# measure. Swapping this string is enough to retune the whole stage.
DEFAULT_ENCODING = "cl100k_base"

# Used only when tiktoken is not installed. English prose runs at roughly this
# many BPE tokens per whitespace word, so chunk sizes stay in the right
# ballpark instead of silently becoming word counts.
TOKENS_PER_WORD = 1.33

# A short line closing with sentence punctuation is a one-line bullet
# ("Experience with reinforcement learning."), not a heading.
_SENTENCE_END = re.compile(r"[.,;:!?]$")


def estimate_tokens(text):
    """Approximate the token count from the word count.

    Fallback for environments without tiktoken. It over- rather than
    under-estimates, so a chunk sized with it still fits a real tokenizer.
    """
    return math.ceil(len(text.split()) * TOKENS_PER_WORD)


@functools.lru_cache(maxsize=None)
def token_counter(encoding=DEFAULT_ENCODING):
    """Return a function that counts the tokens in a string.

    tiktoken is used when it is importable and knows `encoding`, otherwise
    estimate_tokens() takes over so the stage still runs. The result is cached
    because building an encoding is expensive and every split calls this.
    """
    try:
        import tiktoken

        encoder = tiktoken.get_encoding(encoding)
    except Exception:
        return estimate_tokens

    def count_tokens(text):
        return len(encoder.encode(text))

    return count_tokens


def split_paragraphs(text):
    """Split `text` into paragraphs, dropping empty lines.

    A paragraph here is a line. The Cleaning stage emits one line per HTML
    block and drops blank lines, so 179 of the 180 cleaned records contain no
    blank line at all: splitting on "\\n\\n" would hand back each record as a
    single paragraph and defeat the strategy.
    """
    return [line.strip() for line in text.split("\n") if line.strip()]


def is_short_line(line, max_words=MAX_HEADING_WORDS):
    """True if `line` is short enough to be a heading candidate."""
    words = line.split()
    return bool(words) and len(words) <= max_words


def collect_headings(texts, min_docs=DEFAULT_MIN_HEADING_DOCS, max_words=MAX_HEADING_WORDS):
    """Return the short lines that behave like section headings across the corpus.

    Length alone does not identify a heading: a bullet is often just as short
    ("Gender-Affirming Care", "401k with Employer Match"), and cutting on every
    short line shatters a posting into one- and two-line chunks. What separates
    them is reuse. A heading is part of how job postings are written, so it
    recurs across employers ("Requirements", "About the Role", "Job
    Description"), while a short bullet belongs to one posting. Counting
    documents rather than occurrences picks the headings out without hardcoding
    any vocabulary, the same way the Cleaning stage detects boilerplate.

    Pass the result to split_sections(); pass it None there for the strict
    reading, where every short line is a boundary.
    """
    seen = Counter()
    for text in texts:
        seen.update(
            {
                line
                for line in split_paragraphs(text)
                if is_short_line(line, max_words) and not _SENTENCE_END.search(line)
            }
        )
    return frozenset(line for line, docs in seen.items() if docs >= min_docs)


def split_sections(text, headings=None, max_words=MAX_HEADING_WORDS):
    """Split `text` into sections that each open with a heading line.

    `headings` is the set from collect_headings(). Passing None falls back to
    the strict rule, treating every line of `max_words` words or fewer as a
    boundary. Text that precedes the first heading becomes its own leading
    section, so nothing is dropped.
    """
    sections, current = [], []
    for line in split_paragraphs(text):
        if headings is None:
            boundary = is_short_line(line, max_words)
        else:
            boundary = line in headings
        if boundary and current:
            sections.append("\n".join(current))
            current = []
        current.append(line)
    if current:
        sections.append("\n".join(current))
    return sections


def _longest_fit(words, start, budget, count):
    """Largest end index where words[start:end] still fits `budget` tokens.

    Binary search keeps this to a handful of tokenizer calls per window. The
    lower bound is start + 1 so a single word longer than the budget still
    makes progress instead of looping forever.
    """
    low, high = start + 1, len(words)
    while low < high:
        mid = (low + high + 1) // 2
        if count(" ".join(words[start:mid])) <= budget:
            low = mid
        else:
            high = mid - 1
    return low


def _overlap_size(words, end, budget, count):
    """How many trailing words before `end` fit in `budget` tokens."""
    low, high = 0, end
    while low < high:
        mid = (low + high + 1) // 2
        if count(" ".join(words[end - mid : end])) <= budget:
            low = mid
        else:
            high = mid - 1
    return low


def split_fixed(text, max_tokens=DEFAULT_MAX_TOKENS, overlap=DEFAULT_OVERLAP, count=None):
    """Split `text` into windows of at most `max_tokens`, repeating `overlap` tokens.

    Windows are cut on word boundaries so no chunk ends mid-word, and each one
    reopens with the tail of the previous window so a sentence spanning a cut
    is still readable in both.
    """
    count = count or token_counter()
    if overlap >= max_tokens:
        raise ValueError(f"overlap ({overlap}) must be smaller than max_tokens ({max_tokens})")
    words = text.split()
    if not words:
        return []

    chunks, start = [], 0
    while start < len(words):
        end = _longest_fit(words, start, max_tokens, count)
        chunks.append(" ".join(words[start:end]))
        if end >= len(words):
            break
        # max(..., start + 1) guarantees the window advances even when the
        # overlap tail would cover the whole window just emitted.
        start = max(end - _overlap_size(words, end, overlap, count), start + 1)
    return chunks


def _pack(units, max_tokens, count):
    """Merge neighbouring units while the result still fits `max_tokens`.

    Cut points stay exactly where the strategy put them; this only stops the
    stage emitting a 15-token chunk for every line, which is what paragraph
    splitting would otherwise produce on this corpus (median line: 11 words).
    """
    packed = []
    for unit in units:
        if packed:
            merged = packed[-1] + "\n" + unit
            if count(merged) <= max_tokens:
                packed[-1] = merged
                continue
        packed.append(unit)
    return packed


def _absorb_stubs(units, min_tokens, count):
    """Attach a unit too small to stand on its own to the unit that follows it.

    Greedy packing leaves stubs behind: a one-line section such as
    "Requirements" that arrives when the chunk before it is already full, and
    whose own section is too large to merge into. On its own it retrieves
    nothing and its heading is separated from the text it introduces, so it is
    carried forward into the next unit instead, which is where a heading
    belongs. A stub at the very end has no next unit and joins the previous
    one. Either merge can push a unit past max_tokens; chunk_text() then cuts
    it with the fixed-size splitter, so the ceiling still holds.
    """
    merged, pending = [], ""
    for unit in units:
        if pending:
            unit = pending + "\n" + unit
            pending = ""
        if count(unit) < min_tokens:
            pending = unit
        else:
            merged.append(unit)
    if pending:
        if merged:
            merged[-1] += "\n" + pending
        else:
            merged.append(pending)
    return merged


def chunk_text(
    text,
    strategy="heading",
    max_tokens=DEFAULT_MAX_TOKENS,
    overlap=DEFAULT_OVERLAP,
    min_tokens=DEFAULT_MIN_TOKENS,
    headings=None,
    pack=True,
    count=None,
):
    """Split `text` into chunk strings with the requested strategy.

    `pack` merges adjacent paragraphs or sections up to max_tokens and folds
    away anything left under min_tokens; turn it off to get one chunk per
    paragraph or per section however small. Units still over the limit after
    packing are cut by split_fixed(), so the max_tokens ceiling holds for every
    strategy.
    """
    count = count or token_counter()
    if strategy == "fixed":
        return split_fixed(text, max_tokens, overlap, count)
    if strategy == "paragraph":
        units = split_paragraphs(text)
    elif strategy == "heading":
        units = split_sections(text, headings)
    else:
        raise ValueError(f"unknown strategy: {strategy!r}")

    if pack:
        units = _absorb_stubs(_pack(units, max_tokens, count), min_tokens, count)

    chunks = []
    for unit in units:
        if count(unit) <= max_tokens:
            chunks.append(unit)
        else:
            chunks.extend(split_fixed(unit, max_tokens, overlap, count))
    return chunks


def body_of(record):
    """Return the record's main text field, or None if it has no usable one."""
    for field in BODY_FIELDS:
        value = record.get(field)
        if isinstance(value, str) and value.strip():
            return value
    return None


def metadata_of(record):
    """Pull the display fields both schemas have, under one set of names."""
    metadata = {}
    for key, aliases in METADATA_ALIASES.items():
        for alias in aliases:
            value = record.get(alias)
            if isinstance(value, (str, int)) and value != "":
                metadata[key] = value
                break
    return metadata


def chunk_record(record, source, source_file="", count=None, **options):
    """Turn one cleaned record into its list of chunk dicts.

    `source` is the short name of the file the record came from and is stored
    on every chunk next to "id". Both are required to resolve a chunk back to a
    posting: Jobicy ids are ints and AIDevBoard ids are UUIDs, so the id spaces
    are unrelated and an id alone is ambiguous. `options` is forwarded to
    chunk_text() (strategy, max_tokens, overlap, headings, pack).
    """
    if "id" not in record:
        raise KeyError(f"record from {source!r} has no 'id'; a chunk without one is unusable")

    body = body_of(record)
    if body is None:
        return []

    count = count or token_counter()
    pieces = chunk_text(body, count=count, **options)
    strategy = options.get("strategy", "heading")
    metadata = metadata_of(record)

    return [
        {
            # Unique across the corpus, unlike "id" on its own.
            "chunk_id": f"{source}:{record['id']}:{index}",
            "id": record["id"],
            "source": source,
            "source_file": source_file,
            # Sequential from 0, so the record can be reassembled in order.
            "chunk_index": index,
            "chunk_count": len(pieces),
            "strategy": strategy,
            "token_count": count(piece),
            "text": piece,
            "metadata": metadata,
        }
        for index, piece in enumerate(pieces)
    ]


def chunk_records(records, source, source_file="", count=None, **options):
    """Chunk every record of one source file, in order."""
    count = count or token_counter()
    chunks = []
    for record in records:
        chunks.extend(chunk_record(record, source, source_file, count=count, **options))
    return chunks
