"""Build the vector store from the Embedding stage output and answer with it.

    python Pipeline/06_vector_store.py
    python Pipeline/06_vector_store.py --query "who is hiring for Kubernetes work?"
    python Pipeline/06_vector_store.py --top-k 8 --source aidevboard_ai
    python Pipeline/06_vector_store.py --no-llm          # index and search only

Reads Pipeline/outputs/embeddings_*.json, indexes every vector in a local
Chroma collection under Pipeline/chroma_db, and prints the checks that the
index is complete and still traceable back to the postings it came from. Then
it runs one question end to end: search, prompt, answer, citations.

The API key is read from Pipeline/.env or the environment. If embeddings_*.json
is missing, run Pipeline/05_embedding.py first.
"""

import argparse
import sys

from vector_store import (
    DEFAULT_COLLECTION,
    DEFAULT_LLM_MODEL,
    DEFAULT_TOP_K,
    PERSIST_DIR,
    answer,
    build_prompt,
    citation_of,
    create_collection,
    embedding_settings,
    get_client,
    load_dotenv,
    load_records,
    search,
    upsert,
)

PREVIEW = 200

DEFAULT_QUERY = "Which senior roles work on large language models, and what do they ask for?"


def preview(text):
    """One-line, truncated view of a passage so it fits on screen."""
    flat = " ".join(text.split())
    return flat[:PREVIEW] + ("..." if len(flat) > PREVIEW else "")


def check_index(collection, records, dimension):
    """Raise if the index lost a vector, its width, or a vector's provenance.

    These are the ways this stage can quietly break the answer built on top of
    it: an index of the wrong width retrieves nothing, a dropped chunk cannot
    be found at all, and a point without provenance produces a passage that
    cannot be cited.
    """
    stored = collection.get(include=["documents", "metadatas", "embeddings"])
    ids = stored["ids"]

    # (1) the collection really indexes on the width the vectors were made at.
    assert len(stored["embeddings"][0]) == dimension, (
        f"the collection indexes on {len(stored['embeddings'][0])}, "
        f"but the Embedding stage produced {dimension}"
    )
    assert collection.metadata["dimension"] == dimension, (
        f"collection metadata claims {collection.metadata['dimension']}, not {dimension}"
    )

    # (2) one point per vector, nothing dropped and nothing added.
    assert collection.count() == len(records), (
        f"{collection.count()} points indexed for {len(records)} vectors"
    )

    # (3) every point can still be pointed back at the posting it came from,
    # and carries the passage an answer would quote.
    for point_id, document, metadata in zip(ids, stored["documents"], stored["metadatas"]):
        assert metadata.get("id") not in (None, ""), f"point without id: {point_id}"
        assert metadata.get("source"), f"point without source: {point_id}"
        assert isinstance(metadata.get("chunk_index"), int), (
            f"point without chunk_index: {point_id}"
        )
        assert document, f"point without text: {point_id}"

    # (4) the composite ids stayed unique. id alone would not have: Jobicy
    # numbers its postings and AIDevBoard uses UUIDs, so the spaces overlap.
    assert len(set(ids)) == len(ids), "duplicate point id in the collection"
    assert set(ids) == {record["chunk_id"] for record in records}, (
        "the points do not cover exactly the vectors that came in"
    )

    print(f"checks passed: {len(ids)} points, each {dimension} wide and carrying "
          f"its id + source + chunk_index + text")


def check_search(collection, filters):
    """Raise if search does not return top-k, or if a metadata filter is ignored.

    A filter that is quietly dropped is worse than one that errors: the answer
    still looks right, but it was built from the wrong postings.
    """
    top_k = 3
    hits = search(collection, "kubernetes and cloud infrastructure", top_k=top_k)
    assert len(hits) == top_k, f"asked for {top_k} hits, got {len(hits)}"
    assert all(hit["text"] for hit in hits), "a hit came back without its passage"

    field, value = next(iter(filters.items()))
    filtered = search(collection, "kubernetes and cloud infrastructure",
                      top_k=top_k, filters=filters)
    assert filtered, f"filter {filters} matched nothing"
    for hit in filtered:
        if field == "category":
            assert value in hit["metadata"]["category"], (
                f"filter {filters} let through {hit['chunk_id']} "
                f"with category {hit['metadata']['category']!r}"
            )
        else:
            assert hit["metadata"][field] == value, (
                f"filter {filters} let through {hit['chunk_id']} "
                f"with {field}={hit['metadata'][field]!r}"
            )

    print(f"checks passed: search returns top-k, and {filters} really narrows it "
          f"({len(filtered)} hit(s), all matching)")


def check_answer(result):
    """Raise if the answer cites nothing, or cites a passage it was never given."""
    assert result["answer"].strip(), "the model returned an empty answer"
    assert not result["invented"], (
        f"the answer cites passages it was never given: {result['invented']}"
    )
    assert result["citations"], (
        "the answer cites nothing; every claim has to point at a passage"
    )
    offered = {hit["chunk_id"] for hit in result["hits"]}
    for source, ident, index in result["citations"]:
        assert f"{source}:{ident}:{index}" in offered, (
            f"citation [{source}:{ident}#{index}] does not resolve to a retrieved passage"
        )

    print(f"checks passed: the answer carries {len(result['citations'])} citation(s), "
          f"all resolving back to a real posting")


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--query", default=DEFAULT_QUERY)
    parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K)
    parser.add_argument("--collection", default=DEFAULT_COLLECTION)
    parser.add_argument("--persist-dir", default=str(PERSIST_DIR))
    parser.add_argument("--model", default=DEFAULT_LLM_MODEL, help="the model that answers")
    parser.add_argument("--source", default=None, help="restrict the demo answer to one source")
    parser.add_argument(
        "--keep",
        dest="reset",
        action="store_false",
        help="add to the existing collection instead of rebuilding it",
    )
    parser.add_argument(
        "--no-llm",
        dest="use_llm",
        action="store_false",
        help="index and search only, without spending a call on an answer",
    )
    return parser.parse_args()


def main():
    # Job text carries curly quotes and dashes, which the Windows console
    # encoding cannot represent.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    args = parse_args()
    load_dotenv()

    records = load_records()
    model, dimension = embedding_settings(records)
    print(f"input:      {len(records)} vectors, {model} at dimension {dimension}")
    print(f"store:      {args.persist_dir}   collection {args.collection!r}\n")

    client = get_client(args.persist_dir)
    collection = create_collection(
        client, name=args.collection, dimension=dimension, model=model, reset=args.reset
    )
    indexed = upsert(collection, records)
    print(f"indexed:    {indexed} points\n")

    print("=" * 78)
    check_index(collection, records, dimension)
    check_search(collection, {"source": "aidevboard_ai"})

    # What the retrieval actually returns, before an LLM is involved.
    filters = {"source": args.source} if args.source else None
    hits = search(collection, args.query, top_k=args.top_k, filters=filters)
    print("\n" + "=" * 78)
    print(f"query: {args.query}")
    if filters:
        print(f"filter: {filters}")
    for hit in hits:
        meta = hit["metadata"]
        print(f"\n  {hit['score']:.3f}  {citation_of(hit)}")
        print(f"         {meta['doc_title']} - {meta['author']} ({meta['location']})")
        print(f"         {preview(hit['text'])}")

    if not args.use_llm:
        print("\n--no-llm: stopping before the answer")
        return

    print("\n" + "=" * 78)
    result = answer(args.query, collection, top_k=args.top_k, filters=filters,
                    model=args.model, log=lambda *values: None)
    print(f"answer ({args.model}):\n")
    print(result["answer"])
    print("\nsources:")
    for source, ident, index in result["citations"]:
        hit = next(h for h in result["hits"] if h["chunk_id"] == f"{source}:{ident}:{index}")
        print(f"  [{source}:{ident}#{index}]  {hit['metadata']['doc_title']} "
              f"- {hit['metadata']['author']}")

    print("\n" + "=" * 78)
    check_answer(result)


if __name__ == "__main__":
    main()
