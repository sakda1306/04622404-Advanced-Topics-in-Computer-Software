"""Run the Chunking stage over the Cleaning stage output.

    python Pipeline/03_data_chunking.py
    python Pipeline/03_data_chunking.py --strategy fixed --max-tokens 300 --overlap 30
    python Pipeline/03_data_chunking.py --heading-mode strict --no-pack

Reads Pipeline/outputs/cleaned_*.json, writes chunked_*.json next to them, and
prints how the three strategies compare, a sample chunk, and the checks that
every chunk can still be traced back to the posting it came from.
"""

import argparse
import json
import sys
from pathlib import Path

from chunking import (
    DEFAULT_ENCODING,
    DEFAULT_MAX_TOKENS,
    DEFAULT_MIN_HEADING_DOCS,
    DEFAULT_MIN_TOKENS,
    DEFAULT_OVERLAP,
    body_of,
    chunk_records,
    collect_headings,
    token_counter,
)

OUTPUTS = Path(__file__).resolve().parent / "outputs"
PREVIEW = 320


def source_name(path):
    """Short source label from a file name: cleaned_jobicy_devops_infra.json -> jobicy_devops_infra."""
    return path.stem.replace("cleaned_", "")


def preview(text):
    """One-line, truncated view of a chunk so it fits on screen."""
    flat = text.replace("\n", " | ")
    return flat[:PREVIEW] + ("..." if len(flat) > PREVIEW else "")


def flatten(text):
    """Whitespace-insensitive form, for comparing a chunk against its source.

    The fixed-size splitter rejoins words with single spaces, so a chunk that
    crossed a line break is not a literal substring of the record even though
    every word of it came from there in order.
    """
    return " ".join(text.split())


def check_chunks(chunks, corpus, max_tokens):
    """Raise if a chunk lost its provenance, its ordering, or its text.

    corpus maps (source, id) -> the record body the chunks were cut from.
    """
    per_record = {}
    for chunk in chunks:
        # (1) the source record's id, (2) the file it came from. Either one
        # missing makes the chunk impossible to resolve back to a posting.
        assert chunk.get("id") not in (None, ""), f"chunk without id: {chunk['chunk_id']}"
        assert chunk.get("source"), f"chunk without source: {chunk['chunk_id']}"
        assert chunk.get("source_file"), f"chunk without source_file: {chunk['chunk_id']}"

        # (3) the id really belongs to a record in that source, and the text
        # really came out of that record. An id that merely looks valid is the
        # failure this catches: Jobicy ints and AIDevBoard UUIDs share no id
        # space, so the source has to be part of the lookup.
        key = (chunk["source"], chunk["id"])
        assert key in corpus, f"chunk points at a record that does not exist: {key}"
        assert flatten(chunk["text"]) in flatten(corpus[key]), (
            f"chunk text is not part of record {key}: {chunk['chunk_id']}"
        )

        assert chunk["text"].strip(), f"empty chunk: {chunk['chunk_id']}"
        assert chunk["token_count"] <= max_tokens, (
            f"chunk over the limit ({chunk['token_count']} > {max_tokens}): {chunk['chunk_id']}"
        )
        per_record.setdefault(key, []).append(chunk)

    # (4) chunk_index runs 0..n-1 with nothing missing or repeated, so a record
    # can be reassembled in order and a gap is not mistaken for a short posting.
    for key, group in per_record.items():
        indexes = sorted(chunk["chunk_index"] for chunk in group)
        assert indexes == list(range(len(group))), f"chunk_index gap on {key}: {indexes}"
        for chunk in group:
            assert chunk["chunk_count"] == len(group), f"wrong chunk_count on {chunk['chunk_id']}"

    # Every record that has text produced at least one chunk, so nothing was
    # dropped silently on the way in.
    missing = sorted(set(corpus) - set(per_record))
    assert not missing, f"{len(missing)} records produced no chunk, first: {missing[:3]}"

    return per_record


def describe(chunks):
    """One line of shape statistics for a set of chunks."""
    if not chunks:
        return "no chunks"
    tokens = sorted(chunk["token_count"] for chunk in chunks)
    return (
        f"{len(chunks):5d} chunks   tokens min/median/max = "
        f"{tokens[0]:4d}/{tokens[len(tokens) // 2]:4d}/{tokens[-1]:4d}"
    )


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strategy", choices=("fixed", "paragraph", "heading"), default="heading")
    parser.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS)
    parser.add_argument("--overlap", type=int, default=DEFAULT_OVERLAP)
    parser.add_argument(
        "--min-tokens",
        type=int,
        default=DEFAULT_MIN_TOKENS,
        help="chunks smaller than this are folded into a neighbour",
    )
    parser.add_argument(
        "--heading-mode",
        choices=("corpus", "strict"),
        default="corpus",
        help="corpus: only short lines reused across postings are headings. "
        "strict: every line of 4 words or fewer is a boundary.",
    )
    parser.add_argument("--min-heading-docs", type=int, default=DEFAULT_MIN_HEADING_DOCS)
    parser.add_argument("--encoding", default=DEFAULT_ENCODING, help="tiktoken encoding name")
    parser.add_argument(
        "--no-pack",
        dest="pack",
        action="store_false",
        help="do not merge neighbouring paragraphs/sections up to max_tokens",
    )
    return parser.parse_args()


def main():
    # Job text carries curly quotes and dashes, which the Windows console
    # encoding cannot represent.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    args = parse_args()

    count = token_counter(args.encoding)
    tokenizer = "tiktoken " + args.encoding if count.__name__ != "estimate_tokens" else "word estimate (tiktoken unavailable)"

    sources = sorted(OUTPUTS.glob("cleaned_*.json"))
    corpus = {path: json.loads(path.read_text(encoding="utf-8")) for path in sources}
    bodies = [body_of(r) for records in corpus.values() for r in records if body_of(r)]

    # Headings are collected over every file at once: the same section title is
    # reused by postings that landed in different files, and a heading seen
    # once is a bullet.
    headings = collect_headings(bodies, min_docs=args.min_heading_docs)
    options = {
        "strategy": args.strategy,
        "max_tokens": args.max_tokens,
        "overlap": args.overlap,
        "min_tokens": args.min_tokens,
        "headings": None if args.heading_mode == "strict" else headings,
        "pack": args.pack,
    }

    records_total = sum(len(records) for records in corpus.values())
    print(f"tokenizer: {tokenizer}")
    print(f"corpus:    {records_total} records in {len(sources)} files")
    print(
        f"headings:  {len(headings)} short lines reused in >= {args.min_heading_docs} documents"
        f"   (mode: {args.heading_mode})"
    )
    print(
        f"settings:  strategy={args.strategy} max_tokens={args.max_tokens} "
        f"overlap={args.overlap} min_tokens={args.min_tokens} pack={args.pack}\n"
    )

    # (source, id) -> body, the lookup the checks resolve every chunk against.
    lookup = {}
    all_chunks = []
    for path, records in corpus.items():
        source = source_name(path)
        for record in records:
            body = body_of(record)
            if body is not None:
                lookup[(source, record["id"])] = body

        chunks = chunk_records(records, source, path.name, count=count, **options)
        all_chunks.extend(chunks)

        destination = path.with_name(path.name.replace("cleaned_", "chunked_"))
        destination.write_text(
            json.dumps(chunks, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"{path.name}  ->  {destination.name}")
        print(f"  {len(records):3d} records   {describe(chunks)}")

    per_record = check_chunks(all_chunks, lookup, args.max_tokens)
    print(
        f"\nchecks passed: {len(all_chunks)} chunks over {len(per_record)} records "
        f"keep their id + source, sit inside their source record, and are indexed 0..n-1"
    )

    # Same records through every strategy, so the choice can be made on numbers
    # rather than on the description of each one.
    print("\n" + "=" * 78)
    print("strategy comparison (same corpus, same limits)")
    for strategy in ("fixed", "paragraph", "heading"):
        variants = [("", options["headings"])]
        if strategy == "heading":
            variants = [(" corpus headings", headings), (" strict <=4 words", None)]
        for label, heading_set in variants:
            trial = []
            for path, records in corpus.items():
                trial.extend(
                    chunk_records(
                        records,
                        source_name(path),
                        path.name,
                        count=count,
                        strategy=strategy,
                        max_tokens=args.max_tokens,
                        overlap=args.overlap,
                        min_tokens=args.min_tokens,
                        headings=heading_set,
                        pack=args.pack,
                    )
                )
            print(f"  {strategy + label:24s} {describe(trial)}")

    # One record end to end, to show the chunks really are consecutive pieces
    # of the same posting.
    sample_key = next(iter(per_record))
    sample = sorted(per_record[sample_key], key=lambda chunk: chunk["chunk_index"])
    print("\n" + "=" * 78)
    print(f"sample record: source={sample[0]['source']} id={sample[0]['id']!r}")
    print(f"  title: {sample[0]['metadata'].get('title', '-')}")
    print(f"  {len(sample)} chunks from {count(lookup[sample_key])} tokens of source text\n")
    for chunk in sample:
        print(f"  [{chunk['chunk_index']}/{chunk['chunk_count'] - 1}] "
              f"{chunk['token_count']} tokens  chunk_id={chunk['chunk_id']}")
        print(f"      {preview(chunk['text'])}\n")


if __name__ == "__main__":
    main()
