"""Run the Embedding stage over the Metadata stage output.

    python Pipeline/05_embedding.py
    python Pipeline/05_embedding.py --limit 20            # a cheap trial run
    python Pipeline/05_embedding.py --provider openai --model text-embedding-3-small
    python Pipeline/05_embedding.py --dimension 768 --batch-size 50

Reads Pipeline/outputs/metadata_*.json, writes embeddings_*.json next to them,
and prints the cost of the run, the checks that every vector can still be
traced back to the posting it came from, and a nearest-neighbour sample so the
vectors can be seen to mean something.

The API key is read from Pipeline/.env or the environment. If metadata_*.json
is missing, run Pipeline/04_metadata.py first.
"""

import argparse
import json
import math
import sys
from pathlib import Path

from embedding import (
    DEFAULT_BACKOFF,
    DEFAULT_BATCH_SIZE,
    DEFAULT_DIMENSION,
    DEFAULT_MAX_BATCH_TOKENS,
    DEFAULT_MAX_RETRIES,
    DEFAULT_TOKENS_PER_MINUTE,
    PROVIDERS,
    check_embeddings,
    embed_chunks,
    load_dotenv,
)

OUTPUTS = Path(__file__).resolve().parent / "outputs"
PREVIEW = 200


def preview(text):
    """One-line, truncated view of a chunk so it fits on screen."""
    flat = text.replace("\n", " | ")
    return flat[:PREVIEW] + ("..." if len(flat) > PREVIEW else "")


def cosine(left, right):
    """Cosine similarity between two vectors."""
    dot = sum(a * b for a, b in zip(left, right))
    left_length = math.sqrt(sum(a * a for a in left))
    right_length = math.sqrt(sum(b * b for b in right))
    if left_length == 0 or right_length == 0:
        return 0.0
    return dot / (left_length * right_length)


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", choices=sorted(PROVIDERS), default="gemini")
    parser.add_argument("--model", default=None, help="defaults to the provider's model")
    parser.add_argument(
        "--dimension",
        type=int,
        default=DEFAULT_DIMENSION,
        help="must match the width the Vector Store stage indexes on",
    )
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    parser.add_argument(
        "--max-batch-tokens",
        type=int,
        default=DEFAULT_MAX_BATCH_TOKENS,
        help="close a batch once it reaches this many estimated tokens",
    )
    parser.add_argument(
        "--tokens-per-minute",
        type=int,
        default=DEFAULT_TOKENS_PER_MINUTE,
        help="pace requests against this budget; 0 disables pacing",
    )
    parser.add_argument("--max-retries", type=int, default=DEFAULT_MAX_RETRIES)
    parser.add_argument("--backoff", type=float, default=DEFAULT_BACKOFF)
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="embed only the first N chunks of each file, for a trial run",
    )
    parser.add_argument(
        "--no-cache",
        dest="cache",
        action="store_false",
        help="ignore the on-disk cache and re-embed everything",
    )
    return parser.parse_args()


def main():
    # Job text carries curly quotes and dashes, which the Windows console
    # encoding cannot represent.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    args = parse_args()
    load_dotenv()

    sources = sorted(OUTPUTS.glob("metadata_*.json"))
    assert sources, (
        f"no metadata_*.json in {OUTPUTS}. Run Pipeline/04_metadata.py first."
    )

    options = {
        "provider": args.provider,
        "model": args.model,
        "dimension": args.dimension,
        "batch_size": args.batch_size,
        "max_batch_tokens": args.max_batch_tokens,
        "tokens_per_minute": args.tokens_per_minute,
        "max_retries": args.max_retries,
        "backoff": args.backoff,
        "use_cache": args.cache,
    }
    print(f"provider:  {args.provider}   model: {args.model or 'provider default'}")
    print(f"settings:  dimension={args.dimension} batch_size={args.batch_size} "
          f"max_batch_tokens={args.max_batch_tokens} max_retries={args.max_retries} "
          f"cache={args.cache}")
    print(f"pacing:    {args.tokens_per_minute or 'off'} tokens/minute\n")

    all_records = []
    all_chunks = []
    cached_total = 0
    request_total = 0
    for path in sources:
        chunks = json.loads(path.read_text(encoding="utf-8"))
        if args.limit is not None:
            chunks = chunks[:args.limit]

        print(f"{path.name}  ({len(chunks)} chunks)")
        records, stats = embed_chunks(chunks, **options)
        check_embeddings(records, chunks, args.dimension)

        destination = path.with_name(path.name.replace("metadata_", "embeddings_"))
        destination.write_text(
            json.dumps(records, ensure_ascii=False), encoding="utf-8"
        )
        print(f"  -> {destination.name}   {stats['from_cache']} from cache, "
              f"{stats['requested']} embedded in {stats['requests']} request(s)\n")

        all_records.extend(records)
        all_chunks.extend(chunks)
        cached_total += stats["from_cache"]
        request_total += stats["requests"]

    # The checks are run per file above and once more over everything, because
    # chunk_id has to stay unique across files, not only inside one.
    check_embeddings(all_records, all_chunks, args.dimension)
    print("=" * 78)
    print(f"checks passed: {len(all_records)} vectors over {len(sources)} files, "
          f"each {args.dimension} wide and carrying its id + source + chunk_index")
    print(f"  {cached_total} served from cache, {request_total} request(s) sent")

    # What went into the model, header and all.
    sample = all_records[0]
    print("\n" + "=" * 78)
    print(f"sample vector: {sample['chunk_id']}")
    print(f"  embedded text: {preview(sample['embedded_text'])}")
    print(f"  embedding[:6]: {[round(value, 4) for value in sample['embedding'][:6]]}")
    print(f"  model: {sample['model']}   dimension: {sample['dimension']}")

    # A vector nobody can search is not finished work: the nearest neighbours
    # of a chunk should be about the same kind of job, not a random posting.
    if len(all_records) > 1:
        scored = sorted(
            (
                (cosine(sample["embedding"], record["embedding"]), record)
                for record in all_records
                if record["chunk_id"] != sample["chunk_id"]
            ),
            key=lambda pair: pair[0],
            reverse=True,
        )
        print("\n" + "=" * 78)
        print("nearest neighbours of the sample, by cosine similarity")
        print(f"  query: {sample['retrieval_metadata']['doc_title']}")
        for score, record in scored[:5]:
            meta = record["retrieval_metadata"]
            print(f"  {score:.3f}  {record['chunk_id']}")
            print(f"         {meta['doc_title']} - {meta['author']}")


if __name__ == "__main__":
    main()
