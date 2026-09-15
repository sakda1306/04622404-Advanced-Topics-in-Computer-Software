# -*- coding: utf-8 -*-
# Problem 03: Chunking — splitting by raw character count breaks entries apart
#
# Found by testing my own week4 indexing step
# (week4/DL-04-RAG System Development I/RAG-Project/src/text_splitter.py).
# Every number printed below is measured at runtime against the real data.
#
# What the experiment shows, in order:
#   STEP 1  What the splitter actually produces on my knowledge base.
#   STEP 2  The leftover fragments are mostly repeated overlap, and they
#           start in the middle of a word.
#   STEP 3  Every split entry loses the end of its answer from the main chunk.
#   STEP 4  What that costs at query time: a fragment and its parent take
#           two of the three context slots.
#   STEP 5  The fix, measured — and the caveat that goes with it.
import re

from data_loader import load_qa

DOCS = load_qa()

# Values copied from week4 config.py so the simulation matches the real system.
CHUNK_SIZE = 400
CHUNK_OVERLAP = 50
TOP_K = 3

STOPWORDS = {
    "a", "an", "and", "are", "at", "be", "by", "did", "do", "does", "ever",
    "for", "from", "had", "has", "have", "how", "i", "in", "is", "it", "many",
    "most", "of", "on", "only", "or", "that", "this", "the", "to", "was",
    "were", "what", "when", "where", "which", "who", "with", "you",
}


def split_text(text, chunk_size, overlap):
    """Copied verbatim from week4 src/text_splitter.py for the simulation."""
    if len(text) <= chunk_size:
        return [text]

    chunks = []
    start = 0
    while start < len(text):
        chunks.append(text[start:start + chunk_size])
        if start + chunk_size >= len(text):
            break
        start += chunk_size - overlap
    return chunks


def embedded_text(doc):
    """The string week4 build_chunks() embeds — question and answer together."""
    return f"Question: {doc['question']} Answer: {doc['answer']}"


def build_chunks(chunk_size, overlap):
    chunks = []
    for doc in DOCS:
        for part, piece in enumerate(split_text(embedded_text(doc), chunk_size, overlap)):
            chunks.append({"qa_id": doc["id"], "part": part, "text": piece,
                           "question": doc["question"], "answer": doc["answer"]})
    return chunks


def tokenize(text):
    return {w for w in re.findall(r"[a-z0-9']+", text.lower()) if w not in STOPWORDS}


def search(query, chunks, chunk_tokens, k=TOP_K):
    q = tokenize(query)
    return sorted(range(len(chunks)), key=lambda i: len(q & chunk_tokens[i]), reverse=True)[:k]


def run():
    chunks = build_chunks(CHUNK_SIZE, CHUNK_OVERLAP)
    tokens = [tokenize(c["text"]) for c in chunks]
    fragments = [c for c in chunks if c["part"] > 0]
    split_ids = sorted({c["qa_id"] for c in fragments})

    # ---------------------------------------------------------------- STEP 1
    print(f"STEP 1: What the splitter produces (CHUNK_SIZE={CHUNK_SIZE},"
          f" CHUNK_OVERLAP={CHUNK_OVERLAP}).")
    print(f"  Q&A entries in the knowledge base : {len(DOCS)}")
    print(f"  Chunks sent to the index          : {len(chunks)}")
    print(f"  Entries that had to be split      : {len(split_ids)}")
    print(f"  Leftover fragments created        : {len(fragments)}")
    print("  -> Most entries fit in one chunk, so the splitter rarely fires. The")
    print("     problem is what it does on the few entries that do not fit.")
    print()

    # ---------------------------------------------------------------- STEP 2
    print("STEP 2: The fragments carry almost no new information.")
    lengths = sorted(len(c["text"]) for c in fragments)
    print(f"  Fragment length: shortest {lengths[0]}, median"
          f" {lengths[len(lengths) // 2]}, longest {lengths[-1]} characters")
    print(f"  Each fragment repeats the last {CHUNK_OVERLAP} characters of the chunk before it,")
    print("  so its genuinely new content is length minus overlap:")
    for c in fragments[:4]:
        new = max(0, len(c["text"]) - CHUNK_OVERLAP)
        print(f"     entry {c['qa_id']:>5} part {c['part']}: {len(c['text']):>3} characters"
              f" -> {new:>3} new ({new * 100 // len(c['text'])}%)")
    midword = [c for c in fragments if c["text"][:1].isalnum()]
    print(f"  Fragments whose first character is mid-word: {len(midword)} of {len(fragments)}")
    for c in fragments[:3]:
        print(f"     {c['text'][:58]!r}")
    print("  -> These are indexed and embedded as if they were documents, even")
    print("     though a reader could not tell what they are about.")
    print()

    # ---------------------------------------------------------------- STEP 3
    print("STEP 3: Every split entry loses the end of its answer.")
    truncated = [c for c in chunks
                 if c["part"] == 0 and c["qa_id"] in split_ids
                 and f"Answer: {c['answer']}" not in c["text"]]
    print(f"  Entries whose main chunk (part 0) does not contain the whole answer:"
          f" {len(truncated)} of {len(split_ids)}")
    example = truncated[0]
    print(f"  Example — entry {example['qa_id']}:")
    print(f"     the real answer            : {example['answer']!r}")
    print(f"     what part 0 ends with      : ...{example['text'][-32:]!r}")
    tail = next(c for c in fragments if c["qa_id"] == example["qa_id"])
    print(f"     the fragment that holds it : {tail['text'][:58]!r}")
    print("  -> The chunk containing the question no longer contains the complete")
    print("     answer, and the only chunk that does is the unreadable fragment.")
    print("     The damage is limited to the SEARCH side: week4")
    print("     prompt_templates.format_context() builds the LLM context from the")
    print("     chunk's 'answer' field, which still holds the full original answer.")
    print("     So the answer text stays correct; what degrades is the system's")
    print("     ability to find it.")
    print()

    # ---------------------------------------------------------------- STEP 4
    print(f"STEP 4: What this costs at query time (TOP_K = {TOP_K}).")
    both_in_topk = 0
    for qa_id in split_ids:
        question = next(d["question"] for d in DOCS if d["id"] == qa_id)
        hits = search(question, chunks, tokens)
        if sum(1 for i in hits if chunks[i]["qa_id"] == qa_id) > 1:
            both_in_topk += 1
    print(f"  Asking each of the {len(split_ids)} split entries its own question:")
    print(f"     {both_in_topk} of them return the main chunk AND its fragment together,")
    print(f"     so one of the {TOP_K} context slots is spent on the same entry twice.")
    demo_id = split_ids[0]
    demo_q = next(d["question"] for d in DOCS if d["id"] == demo_id)
    print(f"  Example — {demo_q[:58]}")
    for n, i in enumerate(search(demo_q, chunks, tokens), start=1):
        mark = " <- fragment of the same entry" if (
            chunks[i]["qa_id"] == demo_id and chunks[i]["part"] > 0) else ""
        print(f"     [{n}] entry {chunks[i]['qa_id']} part {chunks[i]['part']}:"
              f" {chunks[i]['text'][:38]!r}{mark}")
    print()

    # ---------------------------------------------------------------- STEP 5
    print("STEP 5: The fix, measured.")
    longest = max(len(embedded_text(d)) for d in DOCS)
    print(f"  Longest entry in the whole knowledge base: {longest} characters")
    print(f"  A Q&A pair is one atomic fact, so there is nothing to gain by cutting")
    print(f"  one in half. Raising CHUNK_SIZE above {longest} stops the splitter")
    print("  from ever firing on this dataset:")

    fixed = build_chunks(longest + 15, CHUNK_OVERLAP)
    fixed_tokens = [tokenize(c["text"]) for c in fixed]
    print(f"     chunks produced: {len(chunks)} -> {len(fixed)}"
          f" (one per entry, {len(DOCS)} entries)")

    before = after = 0
    for qa_id in split_ids:
        question = next(d["question"] for d in DOCS if d["id"] == qa_id)
        before += len({chunks[i]["qa_id"] for i in search(question, chunks, tokens)})
        after += len({fixed[i]["qa_id"] for i in search(question, fixed, fixed_tokens)})
    ceiling = len(split_ids) * TOP_K
    print(f"     distinct entries across the {len(split_ids)} affected questions'"
          f" Top-{TOP_K}: {before} -> {after}")
    print(f"     (the ceiling is {ceiling}, so the fix recovers every wasted slot)")
    print()
    print("  One caveat before changing the config: the embedding model has its own")
    print("  input limit, and paraphrase-multilingual-MiniLM-L12-v2 truncates long")
    print("  input silently. Check its max_seq_length first — if an entry is longer")
    print("  than the model accepts, a larger CHUNK_SIZE does not make the model")
    print("  read more of it. A splitter that cuts on sentence boundaries instead of")
    print("  a raw character count is the more general fix, because it never leaves")
    print("  a fragment starting in the middle of a word.")
    print()
    print("Cause: split_text() slices by character position, with no notion of")
    print("words, sentences, or the Question/Answer structure it is cutting through.")
    print("Whenever an entry crosses the limit, it produces a clean first half and a")
    print("fragment that is mostly a copy of the overlap.")
    print()
    print("Status in my week4 system: NOT fixed — src/text_splitter.py still slices")
    print(f"by character count and config.py still sets CHUNK_SIZE = {CHUNK_SIZE}.")


if __name__ == "__main__":
    run()
