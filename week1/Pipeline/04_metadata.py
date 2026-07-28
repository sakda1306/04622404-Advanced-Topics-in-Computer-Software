"""Attach retrieval metadata to every chunk produced by the Chunking stage.

    python Pipeline/04_metadata.py

Reads Pipeline/outputs/chunked_*.json, joins each chunk back to its source
record in the matching cleaned_*.json via (source_file, id), and writes
metadata_*.json next to them. Prints a sample chunk and the checks that
every chunk still carries a full, honest metadata block.
"""

import json
import sys
from pathlib import Path

OUTPUTS = Path(__file__).resolve().parent / "outputs"
PREVIEW = 200

# Jobicy and AIDevBoard name the same concepts differently. Each schema is
# recognised by a field only it has, and mapped onto one shared metadata
# shape below. Fields the source record does not have come back as None
# rather than a guessed value.
JOBICY_MARKER = "jobTitle"


def source_fields(record):
    """Pull (doc_title, author, date, category, location, level) out of one cleaned record."""
    if JOBICY_MARKER in record:
        return (
            record.get("jobTitle"),
            record.get("companyName"),
            record.get("pubDate"),
            list(record.get("jobIndustry") or []),
            record.get("jobGeo"),
            record.get("jobLevel"),
        )
    return (
        record.get("title"),
        record.get("company_name"),
        record.get("published_at"),
        list(record.get("tags") or []),
        record.get("location"),
        record.get("experience_level"),
    )


def build_corpus(outputs=OUTPUTS):
    """Load every cleaned_*.json into a (source_file, id) -> record lookup."""
    corpus = {}
    for path in sorted(outputs.glob("cleaned_*.json")):
        for record in json.loads(path.read_text(encoding="utf-8")):
            corpus[(path.name, record["id"])] = record
    return corpus


def add_metadata(chunk, corpus):
    """Return a new chunk dict carrying a retrieval_metadata block.

    Looks the chunk's source record up by (source_file, id) -- the same
    key Chunking used to cut it -- and never mutates the chunk it was given.
    """
    key = (chunk["source_file"], chunk["id"])
    record = corpus.get(key)
    assert record is not None, f"no source record for {key} (chunk_id={chunk['chunk_id']})"

    doc_title, author, date, category, location, level = source_fields(record)
    enriched = dict(chunk)
    enriched["retrieval_metadata"] = {
        "source": chunk["source"],
        "id": chunk["id"],
        "chunk_index": chunk["chunk_index"],
        "doc_title": doc_title,
        "author": author,
        "date": date,
        "category": category,
        "location": location,
        "level": level,
        "language": "en",
    }
    return enriched


def check_metadata(chunks, original_by_id, corpus):
    """Raise if a chunk lost provenance, missed a field, or gained a fabricated value."""
    required = {
        "source", "id", "chunk_index", "doc_title", "author",
        "date", "category", "location", "level", "language",
    }
    for chunk in chunks:
        # (1) every chunk has a full metadata block
        meta = chunk.get("retrieval_metadata")
        assert meta is not None, f"chunk missing retrieval_metadata: {chunk['chunk_id']}"
        assert required <= meta.keys(), (
            f"retrieval_metadata missing fields on {chunk['chunk_id']}: {required - meta.keys()}"
        )

        # (2) id + source + chunk_index from stage 3 are carried through unchanged
        original = original_by_id[chunk["chunk_id"]]
        assert meta["source"] == original["source"] == chunk["source"], (
            f"source changed on {chunk['chunk_id']}"
        )
        assert meta["id"] == original["id"] == chunk["id"], f"id changed on {chunk['chunk_id']}"
        assert meta["chunk_index"] == original["chunk_index"] == chunk["chunk_index"], (
            f"chunk_index changed on {chunk['chunk_id']}"
        )

        # (3) (source, id) really resolves to a record in the stage-2 output
        key = (chunk["source_file"], chunk["id"])
        assert key in corpus, f"(source_file, id) does not resolve to a real record: {key}"

        # (4) every mapped field matches the source record exactly -- this
        # covers both correctness and "null stays null, nothing is fabricated"
        # in one comparison, since a source value of None only matches None.
        record = corpus[key]
        doc_title, author, date, category, location, level = source_fields(record)
        for field, meta_value, source_value in (
            ("doc_title", meta["doc_title"], doc_title),
            ("author", meta["author"], author),
            ("date", meta["date"], date),
            ("category", meta["category"], category),
            ("location", meta["location"], location),
            ("level", meta["level"], level),
        ):
            assert meta_value == source_value, (
                f"{field} mismatch on {chunk['chunk_id']}: "
                f"metadata={meta_value!r} source={source_value!r}"
            )

        # (5) every chunk has a language
        assert meta["language"] == "en", f"unexpected language on {chunk['chunk_id']}"

    print(f"checks passed: {len(chunks)} chunks all carry a full, honest retrieval_metadata block")


def preview(text):
    """One-line, truncated view of a chunk so it fits on screen."""
    flat = text.replace("\n", " | ")
    return flat[:PREVIEW] + ("..." if len(flat) > PREVIEW else "")


def main():
    # Job text carries curly quotes and dashes, which the Windows console
    # encoding cannot represent.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    corpus = build_corpus()
    file_count = len({key[0] for key in corpus})
    print(f"corpus: {len(corpus)} source records loaded from {file_count} files\n")

    sources = sorted(OUTPUTS.glob("chunked_*.json"))
    all_chunks = []
    all_original = {}
    for path in sources:
        chunks = json.loads(path.read_text(encoding="utf-8"))
        for chunk in chunks:
            all_original[chunk["chunk_id"]] = chunk

        enriched = [add_metadata(chunk, corpus) for chunk in chunks]
        all_chunks.extend(enriched)

        destination = path.with_name(path.name.replace("chunked_", "metadata_"))
        destination.write_text(
            json.dumps(enriched, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"{path.name}  ->  {destination.name}   ({len(enriched)} chunks)")

    check_metadata(all_chunks, all_original, corpus)

    # One chunk end to end, to show the metadata really lines up with a real posting.
    sample = all_chunks[0]
    print("\n" + "=" * 78)
    print(f"sample chunk: {sample['chunk_id']}")
    print(f"  text: {preview(sample['text'])}")
    print("  retrieval_metadata:")
    for field, value in sample["retrieval_metadata"].items():
        print(f"    {field}: {value!r}")


if __name__ == "__main__":
    main()
