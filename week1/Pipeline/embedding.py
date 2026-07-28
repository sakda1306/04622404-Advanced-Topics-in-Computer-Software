"""Embedding stage for the job-posting pipeline.

Input is the Metadata stage output in Pipeline/outputs/metadata_*.json: chunks
that already carry their source record's "id", the file they came from, their
position in that record, and a retrieval_metadata block.

Every chunk becomes one vector, and every vector keeps the provenance it came
in with. The id spaces do not line up across sources (Jobicy numbers its
postings, AIDevBoard uses a UUID), so "id" alone cannot resolve a vector back
to a posting -- (source, id) can, and chunk_id is that pair plus the chunk
index, already unique across the whole corpus.

Two providers are supported behind one interface, chosen per call:

    gemini   gemini-embedding-001, output dimension configurable
    openai   text-embedding-3-small / -3-large, dimensions configurable

Both are reached over plain HTTP through urllib, so the stage adds no
dependency to the pipeline. The API key is read from the environment only; it
is never taken as an argument, never written to the output, and never logged.

The text handed to the provider is not the chunk body alone: a short header
built from the chunk's own metadata is prepended, so a chunk cut from the
middle of a posting still carries the job title and company it belongs to. The
body itself is passed through untouched -- Cleaning already normalized it.

Requests are batched, paced against a tokens-per-minute budget, and retried
with exponential backoff, because a free-tier key is metered in tokens per
minute and answers 429 for a whole batch once that window is full.

Repeated runs are cheap. Each vector is cached on disk under a key covering the
exact text, provider, model and dimension, so re-running only pays for chunks
that are new or whose settings changed.
"""

import hashlib
import json
import math
import os
import random
import time
import urllib.error
import urllib.request
from pathlib import Path

# Must match the dimension the Vector Store stage creates its index with. A
# mismatch is not a quality problem, it is a failed upsert.
DEFAULT_DIMENSION = 1536

# One request carries many chunks. 100 is the largest batch the Gemini endpoint
# accepts, and is comfortably inside the OpenAI request size limit.
DEFAULT_BATCH_SIZE = 100

# The count above is not the binding limit: a free-tier key is metered in
# tokens per minute, and 100 chunks of this corpus is around 45k tokens, well
# over the 30k/minute the Gemini free tier allows. So a batch is capped by
# estimated tokens as well as by count, and requests are paced against a
# per-minute budget kept under the real one. Raise both on a paid key.
DEFAULT_MAX_BATCH_TOKENS = 12000
DEFAULT_TOKENS_PER_MINUTE = 25000

# Rough token count without pulling in tiktoken, which this stage otherwise
# does not need. English prose runs about four characters per token; the
# estimate only has to be close enough to keep batches under a limit, and
# erring high is the safe direction.
CHARS_PER_TOKEN = 4

DEFAULT_MAX_RETRIES = 5
DEFAULT_BACKOFF = 1.0
DEFAULT_TIMEOUT = 60

CACHE_PATH = Path(__file__).resolve().parent / "embedding_cache" / "vectors.jsonl"

# Status codes worth trying again: rate limiting and the transient server-side
# failures. Anything else (401, 400, ...) is a real error and is raised at once
# rather than retried five times.
RETRY_STATUS = frozenset({408, 409, 429, 500, 502, 503, 504})

# Fields prepended to the chunk body, in order. Values come from the chunk's
# own retrieval_metadata, so the header can never disagree with the metadata
# the Vector Store stage will filter on.
HEADER_FIELDS = ("doc_title", "author", "location")


# --------------------------------------------------------------------------
# what actually gets embedded
# --------------------------------------------------------------------------

def embedding_text(chunk):
    """Return the string to embed for one chunk: metadata header + body.

    Chunk 3 of a posting is a paragraph of requirements with nothing in it
    naming the job or the company, which makes it unreachable by a query like
    "DevOps role at Reddit". Prepending the title, the company and the location
    puts that back without touching the body Cleaning produced.
    """
    meta = chunk.get("retrieval_metadata") or {}
    title, author, location = (meta.get(field) for field in HEADER_FIELDS)

    lines = []
    if title:
        lines.append(str(title).strip())
    # Company and location read as one line; either may be missing.
    subtitle = " | ".join(str(value).strip() for value in (author, location) if value)
    if subtitle:
        lines.append(subtitle)

    header = "\n".join(lines)
    return f"{header}\n\n{chunk['text']}" if header else chunk["text"]


# --------------------------------------------------------------------------
# providers
# --------------------------------------------------------------------------

class GeminiProvider:
    """Google Generative Language embeddings (batchEmbedContents)."""

    name = "gemini"
    key_env = "GEMINI_API_KEY"
    default_model = "gemini-embedding-001"
    endpoint = "https://generativelanguage.googleapis.com/v1beta/models/{model}:batchEmbedContents"

    # Only the full 3072-wide output comes back unit length; every truncated
    # dimension has to be normalized here before cosine similarity means
    # anything downstream.
    native_dimension = 3072

    def request(self, texts, model, dimension, api_key):
        body = {
            "requests": [
                {
                    "model": f"models/{model}",
                    "content": {"parts": [{"text": text}]},
                    "taskType": "RETRIEVAL_DOCUMENT",
                    "outputDimensionality": dimension,
                }
                for text in texts
            ]
        }
        headers = {"Content-Type": "application/json", "x-goog-api-key": api_key}
        return self.endpoint.format(model=model), headers, body

    def parse(self, payload, dimension):
        vectors = [item["values"] for item in payload["embeddings"]]
        if dimension != self.native_dimension:
            vectors = [l2_normalize(vector) for vector in vectors]
        return vectors


class OpenAIProvider:
    """OpenAI embeddings (/v1/embeddings)."""

    name = "openai"
    key_env = "OPENAI_API_KEY"
    default_model = "text-embedding-3-small"
    endpoint = "https://api.openai.com/v1/embeddings"

    def request(self, texts, model, dimension, api_key):
        body = {"model": model, "input": list(texts), "dimensions": dimension}
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
        return self.endpoint, headers, body

    def parse(self, payload, dimension):
        # The API may return the batch out of order; index says where each one
        # belongs, so the vectors line up with the texts that were sent.
        items = sorted(payload["data"], key=lambda item: item["index"])
        return [item["embedding"] for item in items]


PROVIDERS = {provider.name: provider() for provider in (GeminiProvider, OpenAIProvider)}


def get_provider(name):
    """Look a provider up by name, with a readable error for a typo."""
    try:
        return PROVIDERS[name]
    except KeyError:
        raise ValueError(f"unknown provider {name!r}, expected one of {sorted(PROVIDERS)}") from None


def l2_normalize(vector):
    """Scale a vector to unit length, leaving an all-zero vector alone."""
    length = math.sqrt(sum(value * value for value in vector))
    return vector if length == 0 else [value / length for value in vector]


# --------------------------------------------------------------------------
# transport: batching, retry, and a cache that survives between runs
# --------------------------------------------------------------------------

def read_api_key(provider):
    """Read the provider's key from the environment, or explain what is missing.

    The value is returned, never printed, and never stored anywhere the output
    or the logs can reach.
    """
    key = os.environ.get(provider.key_env, "").strip()
    if not key:
        raise RuntimeError(
            f"{provider.key_env} is not set. Put it in Pipeline/.env "
            f"(see .env.example) or export it; it must never be hardcoded."
        )
    return key


def load_dotenv(path=None):
    """Load KEY=value lines from Pipeline/.env into the environment.

    Values already in the environment win, so an exported key is not silently
    replaced by a stale file. Missing file is not an error: the key may well
    come from the environment alone.
    """
    path = Path(path) if path else Path(__file__).resolve().parent / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def cache_key(text, provider_name, model, dimension):
    """Identity of one embedding: the exact text and the exact settings.

    Changing the model, the dimension or a single character of the text has to
    produce a different key, otherwise a re-run would serve a vector that no
    longer describes what was asked for.
    """
    payload = f"{provider_name}|{model}|{dimension}|{text}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def load_cache(path=CACHE_PATH):
    """Read the on-disk cache into a key -> vector dict."""
    path = Path(path)
    if not path.exists():
        return {}
    cache = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            entry = json.loads(line)
            cache[entry["key"]] = entry["vector"]
    return cache


def append_cache(entries, path=CACHE_PATH):
    """Append newly computed vectors to the cache file.

    One line per vector, appended rather than rewritten, so a run interrupted
    half way still keeps everything it had already paid for.
    """
    if not entries:
        return
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for key, vector in entries:
            handle.write(json.dumps({"key": key, "vector": vector}) + "\n")


def estimate_tokens(text):
    """Approximate the token count of a string, rounding up."""
    return max(1, -(-len(text) // CHARS_PER_TOKEN))


def batched(items, size, max_tokens=None, text_of=lambda item: item):
    """Split a list into batches bounded by item count and by estimated tokens.

    A batch is closed as soon as adding the next item would break either
    limit, so a single oversized item still goes out on its own rather than
    being dropped.
    """
    batch = []
    tokens = 0
    for item in items:
        cost = estimate_tokens(text_of(item))
        full = len(batch) >= size or (max_tokens is not None and tokens + cost > max_tokens)
        if batch and full:
            yield batch
            batch, tokens = [], 0
        batch.append(item)
        tokens += cost
    if batch:
        yield batch


class RateLimiter:
    """Hold requests back so a rolling minute never exceeds a token budget.

    The free tier meters tokens per minute, not requests, and answers 429 for
    the whole batch once the window is full. Waiting for room is cheaper than
    sending, failing, and backing off.
    """

    def __init__(self, tokens_per_minute, log=print):
        self.budget = tokens_per_minute
        self.log = log
        self.window = []

    def take(self, tokens):
        """Block until the last 60 seconds have room for this many tokens."""
        if not self.budget:
            return
        while True:
            now = time.monotonic()
            self.window = [(at, cost) for at, cost in self.window if now - at < 60]
            used = sum(cost for _, cost in self.window)
            if used + tokens <= self.budget or not self.window:
                self.window.append((now, tokens))
                return
            wait = 60 - (now - self.window[0][0]) + 0.5
            self.log(f"    {used}/{self.budget} tokens used this minute, waiting {wait:.0f}s")
            time.sleep(wait)


def post_json(url, headers, body, timeout=DEFAULT_TIMEOUT):
    """POST a JSON body and return the decoded response."""
    data = json.dumps(body).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def post_with_retry(url, headers, body, max_retries=DEFAULT_MAX_RETRIES,
                    backoff=DEFAULT_BACKOFF, timeout=DEFAULT_TIMEOUT, log=print):
    """POST with exponential backoff on rate limits and transient failures.

    Waits backoff, 2x, 4x ... with a little jitter so retries from several
    machines do not line up. Nothing from the request -- url aside -- is
    logged: the headers carry the API key.
    """
    for attempt in range(max_retries + 1):
        try:
            return post_json(url, headers, body, timeout=timeout)
        except urllib.error.HTTPError as error:
            retriable = error.code in RETRY_STATUS
            reason = f"HTTP {error.code}"
        except (urllib.error.URLError, TimeoutError) as error:
            retriable = True
            reason = type(error).__name__

        if not retriable or attempt == max_retries:
            raise RuntimeError(
                f"embedding request failed after {attempt + 1} attempt(s): {reason}"
            ) from None

        delay = backoff * (2 ** attempt) * (1 + random.random() * 0.1)
        log(f"    {reason}, retry {attempt + 1}/{max_retries} in {delay:.1f}s")
        time.sleep(delay)


def embed_texts(texts, provider="gemini", model=None, dimension=DEFAULT_DIMENSION,
                batch_size=DEFAULT_BATCH_SIZE, max_batch_tokens=DEFAULT_MAX_BATCH_TOKENS,
                tokens_per_minute=DEFAULT_TOKENS_PER_MINUTE, max_retries=DEFAULT_MAX_RETRIES,
                backoff=DEFAULT_BACKOFF, cache_path=CACHE_PATH, use_cache=True, log=print):
    """Embed a list of strings and return (vectors, stats).

    Vectors come back in the order the texts were given. Texts already in the
    cache are not sent, and a text repeated within the input is only sent once.
    stats reports how many were served from cache, how many were requested, and
    how many requests that took.
    """
    provider = get_provider(provider) if isinstance(provider, str) else provider
    model = model or provider.default_model

    keys = [cache_key(text, provider.name, model, dimension) for text in texts]
    cache = load_cache(cache_path) if use_cache else {}

    # Deduplicate before spending anything: identical text under identical
    # settings is one request, however often it appears in the input.
    pending = {}
    for key, text in zip(keys, texts):
        if key not in cache:
            pending.setdefault(key, text)

    if pending:
        api_key = read_api_key(provider)
        log(f"  embedding {len(pending)} new text(s) with {provider.name}/{model} "
            f"at dimension {dimension}, batch size {batch_size}")

    fresh = []
    limiter = RateLimiter(tokens_per_minute, log=log)
    batches = list(batched(list(pending.items()), batch_size,
                           max_tokens=max_batch_tokens, text_of=lambda item: item[1]))
    for number, batch in enumerate(batches, start=1):
        batch_keys = [key for key, _ in batch]
        batch_texts = [text for _, text in batch]

        limiter.take(sum(estimate_tokens(text) for text in batch_texts))
        url, headers, body = provider.request(batch_texts, model, dimension, api_key)
        payload = post_with_retry(url, headers, body, max_retries=max_retries,
                                  backoff=backoff, log=log)
        vectors = provider.parse(payload, dimension)

        assert len(vectors) == len(batch_texts), (
            f"provider returned {len(vectors)} vectors for {len(batch_texts)} texts"
        )
        for key, vector in zip(batch_keys, vectors):
            assert len(vector) == dimension, (
                f"provider returned a {len(vector)}-wide vector, expected {dimension}"
            )
            cache[key] = vector
            fresh.append((key, vector))

        log(f"  batch {number}/{len(batches)}  {len(batch_texts)} texts  "
            f"~{sum(estimate_tokens(text) for text in batch_texts)} tokens  ok")

    if use_cache:
        append_cache(fresh, cache_path)

    fresh_keys = {key for key, _ in fresh}
    stats = {
        "total": len(texts),
        "from_cache": sum(1 for key in keys if key not in fresh_keys),
        "requested": len(pending),
        "requests": len(batches),
        "model": model,
        "provider": provider.name,
        "dimension": dimension,
    }
    return [cache[key] for key in keys], stats


# --------------------------------------------------------------------------
# chunks in, vector records out
# --------------------------------------------------------------------------

def embed_chunks(chunks, **options):
    """Turn metadata-stage chunks into vector records, and return (records, stats).

    Every record keeps chunk_id, id, source, source_file and chunk_index, so
    the Vector Store stage can point any hit back at the posting it came from,
    and carries retrieval_metadata through untouched for filtering. The text
    that was actually embedded is kept as well, since a vector whose input
    cannot be reproduced cannot be debugged.
    """
    texts = [embedding_text(chunk) for chunk in chunks]
    vectors, stats = embed_texts(texts, **options)

    records = []
    for chunk, text, vector in zip(chunks, texts, vectors):
        records.append({
            "chunk_id": chunk["chunk_id"],
            "id": chunk["id"],
            "source": chunk["source"],
            "source_file": chunk["source_file"],
            "chunk_index": chunk["chunk_index"],
            "chunk_count": chunk["chunk_count"],
            "model": stats["model"],
            "provider": stats["provider"],
            "dimension": stats["dimension"],
            "embedded_text": text,
            "embedding": vector,
            "retrieval_metadata": chunk["retrieval_metadata"],
        })
    return records, stats


def check_embeddings(records, chunks, dimension):
    """Raise if a vector lost its provenance, its width, or its chunk.

    These are the four ways this stage can quietly break the stages after it:
    a vector that cannot be traced back to a posting, a vector of the wrong
    width, a chunk that was dropped, and a chunk that was embedded twice.
    """
    for record in records:
        # (1) the source record's id and (2) the file it came from. Either one
        # missing leaves a vector that cannot be resolved back to a posting.
        assert record.get("id") not in (None, ""), f"vector without id: {record['chunk_id']}"
        assert record.get("source"), f"vector without source: {record['chunk_id']}"
        assert record.get("source_file"), f"vector without source_file: {record['chunk_id']}"

        # (3) position inside the record, so the posting can be reassembled.
        assert isinstance(record.get("chunk_index"), int), (
            f"vector without chunk_index: {record['chunk_id']}"
        )

        # (4) the width the Vector Store stage indexes on. One wrong vector
        # fails the whole upsert.
        assert record["dimension"] == dimension, (
            f"wrong dimension recorded on {record['chunk_id']}: {record['dimension']}"
        )
        assert len(record["embedding"]) == dimension, (
            f"{record['chunk_id']} is {len(record['embedding'])} wide, expected {dimension}"
        )
        assert all(
            isinstance(value, (int, float)) and not isinstance(value, bool)
            for value in record["embedding"]
        ), f"non-numeric value in embedding: {record['chunk_id']}"

    # (5) one vector per chunk, no chunk dropped and none embedded twice.
    assert len(records) == len(chunks), (
        f"{len(records)} vectors for {len(chunks)} chunks"
    )
    vector_ids = [record["chunk_id"] for record in records]
    assert len(set(vector_ids)) == len(vector_ids), "duplicate chunk_id among the vectors"
    assert set(vector_ids) == {chunk["chunk_id"] for chunk in chunks}, (
        "the vectors do not cover exactly the chunks that came in"
    )
