"""Vector Store and Retrieval stage for the job-posting pipeline.

Input is the Embedding stage output in Pipeline/outputs/embeddings_*.json: one
vector per chunk, each already carrying chunk_id, id, source, source_file,
chunk_index and the retrieval_metadata block Metadata produced.

This stage is the end of the pipeline. It indexes those vectors in a local
Chroma collection, answers a question by searching that collection, and hands
the passages it found to an LLM that must cite them. Nothing is answered from
the model's own knowledge: a claim without a passage behind it is a bug here,
not a feature.

Three things about the input decide the design:

  chunk_id is already "{source}:{id}:{chunk_index}", unique across the whole
  corpus, so it is used as the point id directly rather than rebuilt. id alone
  cannot be used -- Jobicy numbers its postings and AIDevBoard uses UUIDs, so
  the id spaces overlap and collide.

  The vector records keep embedded_text (a metadata header plus the body), not
  the chunk body on its own. The body is what belongs in an answer's context,
  so it is joined back from metadata_*.json by chunk_id.

  retrieval_metadata.category is a list, and Chroma only stores str, int, float
  and bool. Categories are flattened two ways: a readable joined string to show
  in a citation, and one boolean key per category so a category can still be
  filtered on inside the database rather than after the search.

The query is embedded through the Embedding stage's own embed_texts, with the
model and dimension read off the records themselves. A query embedded by a
different model, or at a different width, lands in a different space and
retrieves nothing meaningful, so neither value is hardcoded here.

The API key is read from the environment via the Embedding stage's loader. It
is never taken as an argument, never written to the output, and never logged.
"""

import json
import re
from pathlib import Path

import chromadb

from embedding import (
    PROVIDERS,
    embed_texts,
    load_dotenv,
    post_with_retry,
    read_api_key,
)

PIPELINE = Path(__file__).resolve().parent
OUTPUTS = PIPELINE / "outputs"

# The store is rebuilt from embeddings_*.json whenever it is needed, so it is
# gitignored rather than committed: it is large and derived, not source.
PERSIST_DIR = PIPELINE / "chroma_db"
DEFAULT_COLLECTION = "job_postings"

DEFAULT_TOP_K = 5

# Gemini embeddings come back unit length, so cosine is the metric that matches
# what the Embedding stage produced.
DISTANCE_METRIC = "cosine"

DEFAULT_LLM_MODEL = "gemini-2.5-flash"
LLM_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

# Scalar metadata fields copied onto every point. category is handled
# separately because it is a list; source, id, chunk_index and chunk_count come
# from the record itself rather than from the metadata block.
SCALAR_FIELDS = ("doc_title", "author", "date", "location", "level", "language")

# One citation tag, e.g. [jobicy_software_en:1234#2]. Used both to write the
# instruction given to the model and to check what it wrote back.
CITATION_PATTERN = re.compile(r"\[([^\[\]:]+):([^\[\]#]+)#(\d+)\]")


# --------------------------------------------------------------------------
# loading what the Embedding stage produced
# --------------------------------------------------------------------------

def slugify(value):
    """Turn a category name into a metadata key that is safe to filter on."""
    return re.sub(r"[^a-z0-9]+", "_", str(value).lower()).strip("_")


def load_records(outputs=OUTPUTS):
    """Load the vector records and put the chunk body back on each one.

    The Embedding stage keeps embedded_text -- the header it prepended plus the
    body -- but not the body alone, and the header would otherwise be repeated
    inside every passage the model reads. The body is joined back from
    metadata_*.json on chunk_id, which is the same key both stages wrote.
    """
    text_by_chunk = {}
    for path in sorted(outputs.glob("metadata_*.json")):
        for chunk in json.loads(path.read_text(encoding="utf-8")):
            text_by_chunk[chunk["chunk_id"]] = chunk["text"]

    records = []
    for path in sorted(outputs.glob("embeddings_*.json")):
        for record in json.loads(path.read_text(encoding="utf-8")):
            text = text_by_chunk.get(record["chunk_id"])
            assert text is not None, (
                f"no chunk body for {record['chunk_id']}; "
                f"metadata_*.json and embeddings_*.json are out of step"
            )
            records.append({**record, "text": text})

    assert records, (
        f"no embeddings_*.json in {outputs}. Run Pipeline/05_embedding.py first."
    )
    return records


def embedding_settings(records):
    """Return the (model, dimension) every record was embedded with.

    A collection can only be searched by a query embedded the same way, so a
    corpus that disagrees with itself is a hard error rather than a warning.
    """
    models = {record["model"] for record in records}
    dimensions = {record["dimension"] for record in records}
    assert len(models) == 1, f"records were embedded with several models: {sorted(models)}"
    assert len(dimensions) == 1, f"records have several dimensions: {sorted(dimensions)}"
    return models.pop(), dimensions.pop()


def flatten_metadata(record):
    """Build the Chroma payload for one record.

    Everything needed to point a hit back at the posting it came from stays on
    the point: chunk_id, id, source, source_file and chunk_index. Losing any of
    them would leave a passage that cannot be cited.
    """
    meta = record["retrieval_metadata"]

    # id is a number on Jobicy and a UUID on AIDevBoard. It is stored as a
    # string so one key does not hold two types, and the composite chunk_id
    # remains the thing that identifies a point.
    payload = {
        "chunk_id": record["chunk_id"],
        "id": str(record["id"]),
        "source": record["source"],
        "source_file": record["source_file"],
        "chunk_index": record["chunk_index"],
        "chunk_count": record["chunk_count"],
    }
    for field in SCALAR_FIELDS:
        value = meta.get(field)
        if value is not None:
            payload[field] = value

    categories = list(meta.get("category") or [])
    # Readable form, for showing a hit; and one boolean key per category, so
    # {"category": "llm"} can be answered by the database instead of by
    # filtering the results after the search has already thrown matches away.
    payload["category"] = " | ".join(str(name) for name in categories)
    for name in categories:
        payload[f"category_{slugify(name)}"] = True

    return payload


# --------------------------------------------------------------------------
# the collection
# --------------------------------------------------------------------------

def get_client(persist_dir=PERSIST_DIR):
    """Open the on-disk Chroma store, creating it if this is the first run."""
    return chromadb.PersistentClient(path=str(persist_dir))


def create_collection(client, name=DEFAULT_COLLECTION, dimension=None, model=None,
                      reset=False):
    """Create (or reopen) the collection the vectors are indexed in.

    Chroma takes its width from the first vector added rather than from a
    declared schema, so the dimension the Embedding stage produced is recorded
    in the collection metadata and checked against the vectors on the way in.
    """
    if reset:
        try:
            client.delete_collection(name)
        except Exception:
            # Nothing to delete on a first run.
            pass

    metadata = {"hnsw:space": DISTANCE_METRIC}
    if dimension is not None:
        metadata["dimension"] = dimension
    if model is not None:
        metadata["embedding_model"] = model

    return client.get_or_create_collection(name=name, metadata=metadata)


def upsert(collection, records, batch_size=500):
    """Index the vector records, keyed by chunk_id.

    chunk_id is already unique across the corpus, so re-running replaces a
    point rather than adding a second copy of it.
    """
    expected = collection.metadata.get("dimension") if collection.metadata else None

    for start in range(0, len(records), batch_size):
        batch = records[start:start + batch_size]
        for record in batch:
            assert expected is None or len(record["embedding"]) == expected, (
                f"{record['chunk_id']} is {len(record['embedding'])} wide, "
                f"but the collection indexes on {expected}"
            )
        collection.upsert(
            ids=[record["chunk_id"] for record in batch],
            embeddings=[record["embedding"] for record in batch],
            documents=[record["text"] for record in batch],
            metadatas=[flatten_metadata(record) for record in batch],
        )
    return collection.count()


# --------------------------------------------------------------------------
# search
# --------------------------------------------------------------------------

def build_where(filters):
    """Translate a plain filter dict into a Chroma where clause.

    {"source": "aidevboard_ai", "level": "senior"} filters on two scalars.
    {"category": "llm"} is rewritten to the boolean key the category was
    flattened into, since the list itself cannot be stored or matched.
    """
    if not filters:
        return None

    clauses = []
    for field, value in filters.items():
        if field == "category":
            clauses.append({f"category_{slugify(value)}": True})
        elif isinstance(value, (list, tuple, set)):
            clauses.append({field: {"$in": sorted(value)}})
        else:
            clauses.append({field: value})

    return clauses[0] if len(clauses) == 1 else {"$and": clauses}


def embed_query(query, model, dimension, log=lambda *args: None):
    """Embed one query with the model and width the corpus was embedded with.

    This goes through the Embedding stage's own embed_texts so the query cannot
    drift onto a different model, a different width, or a different provider
    than the vectors it is being compared against.
    """
    vectors, _ = embed_texts(
        [query], provider="gemini", model=model, dimension=dimension, log=log
    )
    return vectors[0]


def search(collection, query, top_k=DEFAULT_TOP_K, filters=None, model=None,
           dimension=None):
    """Return the top_k passages for a query, newest hit first.

    filters is a plain dict of metadata conditions; see build_where. Each hit
    carries the passage, its full payload and a similarity score, which is what
    build_prompt needs to write a citation.
    """
    if model is None or dimension is None:
        stored = collection.metadata or {}
        model = model or stored.get("embedding_model")
        dimension = dimension or stored.get("dimension")

    vector = embed_query(query, model, dimension)
    result = collection.query(
        query_embeddings=[vector],
        n_results=top_k,
        where=build_where(filters),
        include=["documents", "metadatas", "distances"],
    )

    hits = []
    for point_id, document, metadata, distance in zip(
        result["ids"][0],
        result["documents"][0],
        result["metadatas"][0],
        result["distances"][0],
    ):
        hits.append({
            "chunk_id": point_id,
            "text": document,
            "metadata": metadata,
            # Chroma reports cosine distance; similarity reads better in output.
            "score": 1.0 - distance,
        })
    return hits


def citation_of(hit):
    """The tag a passage is cited by: [source:id#chunk_index]."""
    meta = hit["metadata"]
    return f"[{meta['source']}:{meta['id']}#{meta['chunk_index']}]"


# --------------------------------------------------------------------------
# prompt and answer
# --------------------------------------------------------------------------

INSTRUCTION = """You answer questions about job postings using only the passages below.

Rules:
- Use only these passages. Do not use anything you know from outside them.
- If the passages do not contain the answer, say plainly that you do not know.
  Do not guess, and do not fill a gap with a plausible-sounding detail.
- Support every claim with the tag printed above the passage it came from,
  written inline, for example [jobicy_software_en:1234#2].
- Never write a tag that does not appear above one of the passages.
"""


def build_prompt(query, hits):
    """Assemble the instruction, the retrieved passages, and the question.

    Each passage is printed under its own citation tag and a short provenance
    line, so the model is choosing between labelled sources rather than reading
    one undifferentiated wall of text.
    """
    blocks = []
    for hit in hits:
        meta = hit["metadata"]
        provenance = " | ".join(
            str(value) for value in (
                meta.get("doc_title"), meta.get("author"), meta.get("location")
            ) if value
        )
        blocks.append(
            f"{citation_of(hit)} {provenance}\n{hit['text']}"
        )

    context = "\n\n".join(blocks) if blocks else "(no passages were retrieved)"
    return f"{INSTRUCTION}\nPassages:\n\n{context}\n\nQuestion: {query}\n\nAnswer:"


def call_llm(prompt, model=DEFAULT_LLM_MODEL, temperature=0.0, log=print):
    """Send one prompt to the LLM and return the text it wrote.

    Reuses the Embedding stage's retrying POST, so a rate limit is waited out
    here the same way it is there. The key travels in the headers and nothing
    from the request is logged.
    """
    api_key = read_api_key(PROVIDERS["gemini"])
    url = LLM_ENDPOINT.format(model=model)
    headers = {"Content-Type": "application/json", "x-goog-api-key": api_key}
    body = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": temperature,
            # Grounded extraction from passages that are already in front of
            # the model does not need a reasoning budget.
            "thinkingConfig": {"thinkingBudget": 0},
        },
    }
    payload = post_with_retry(url, headers, body, log=log)

    candidates = payload.get("candidates") or []
    assert candidates, f"the model returned no answer: {payload.get('promptFeedback')}"
    parts = candidates[0].get("content", {}).get("parts") or []
    return "".join(part["text"] for part in parts if "text" in part).strip()


def cited_tags(text):
    """Every citation tag written in an answer, as (source, id, chunk_index)."""
    return {
        (source, ident, int(index))
        for source, ident, index in CITATION_PATTERN.findall(text)
    }


def answer(query, collection, top_k=DEFAULT_TOP_K, filters=None,
           model=DEFAULT_LLM_MODEL, log=print):
    """Search, build the prompt, ask the model, and report what it cited.

    Returns the answer text, the passages it was given, the tags it actually
    used, and any tag it wrote that was not among them -- an invented citation
    is the one failure that looks like a good answer.
    """
    hits = search(collection, query, top_k=top_k, filters=filters)
    prompt = build_prompt(query, hits)
    text = call_llm(prompt, model=model, log=log)

    offered = {
        (hit["metadata"]["source"], hit["metadata"]["id"], hit["metadata"]["chunk_index"])
        for hit in hits
    }
    used = cited_tags(text)
    return {
        "query": query,
        "answer": text,
        "hits": hits,
        "citations": sorted(used & offered),
        "invented": sorted(used - offered),
    }


def open_store(persist_dir=PERSIST_DIR, name=DEFAULT_COLLECTION):
    """Open an already-built store, for a caller that only wants to ask it things."""
    load_dotenv()
    collection = get_client(persist_dir).get_collection(name)
    assert collection.count() > 0, (
        f"collection {name!r} is empty. Run Pipeline/06_vector_store.py first."
    )
    return collection
