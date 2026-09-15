# -*- coding: utf-8 -*-
# Problem 02: Data Quality — duplicates, contradictions and noise in the KB
#
# Found by testing my own week4 knowledge base
# (week4/DL-04-RAG System Development I/RAG-Project/data/football_trivia_qa.txt),
# which was converted from trivia_questions.csv. Every number printed below is
# measured at runtime against the real data, not hard-coded.
#
# What the experiment shows, in order:
#   STEP 1  How much of the KB is duplicated, and at which matching level.
#   STEP 2  What duplicates cost at query time: they eat the Top-K budget.
#   STEP 3  Worse than redundancy — some duplicated questions disagree with
#           each other, so the LLM is handed two contradictory sources.
#   STEP 4  Whitespace noise, and how it wastes the character budget that
#           decides whether an entry gets split into chunks.
#   STEP 5  Cleaning the data before indexing, and what it does and does not fix.
import re
from collections import defaultdict

from data_loader import load_qa

DOCS = load_qa()

# Values copied from week4 config.py so the simulation matches the real system.
TOP_K = 3
CHUNK_SIZE = 400

STOPWORDS = {
    "a", "an", "and", "are", "at", "be", "by", "did", "do", "does", "ever",
    "for", "from", "had", "has", "have", "how", "i", "in", "is", "it", "many",
    "most", "of", "on", "only", "or", "that", "this", "the", "to", "was",
    "were", "what", "when", "where", "which", "who", "with", "you",
}


def tokenize(text):
    return {w for w in re.findall(r"[a-z0-9']+", text.lower()) if w not in STOPWORDS}


DOC_TOKENS = [tokenize(d["text"]) for d in DOCS]


def search(query, k=TOP_K, pool=None):
    """Return the ids of the k documents sharing the most content words."""
    pool = range(len(DOCS)) if pool is None else pool
    q = tokenize(query)
    return sorted(pool, key=lambda i: len(q & DOC_TOKENS[i]), reverse=True)[:k]


def collapse_spaces(text):
    return re.sub(r"\s+", " ", text).strip()


def normalize(text):
    """Cleaning rule used by STEP 5: collapse whitespace, then lowercase."""
    return collapse_spaces(text).lower()


def full_text(doc, clean=False):
    """The string week4 text_splitter.build_chunks() measures against CHUNK_SIZE."""
    q, a = doc["question"], doc["answer"]
    if clean:
        q, a = collapse_spaces(q), collapse_spaces(a)
    return f"Question: {q} Answer: {a}"


# Queries whose subject really is duplicated in the KB.
DUPLICATE_QUERIES = [
    "Who scored the first ever goal in the UEFA Champions League?",
    "Who is the only goalkeeper to have won the Ballon d'Or?",
    "Who scored the fastest goal in World Cup history?",
]


def run():
    total = len(DOCS)

    # ---------------------------------------------------------------- STEP 1
    print("STEP 1: How much of the knowledge base is duplicated?")
    raw = len({d["question"] for d in DOCS})
    spaced = len({collapse_spaces(d["question"]) for d in DOCS})
    lowered = len({normalize(d["question"]) for d in DOCS})
    print(f"  Entries loaded from football_trivia_qa.txt : {total}")
    print(f"  Unique questions, compared as-is           : {raw}   -> {total - raw} duplicates")
    print(f"  Unique questions, whitespace collapsed     : {spaced}   -> {total - spaced} duplicates")
    print(f"  Unique questions, also lowercased          : {lowered}   -> {total - lowered} duplicates")
    print(f"  -> {total - lowered} of {total} entries are repeats. {lowered - spaced and abs(lowered - spaced)} of them")
    print("     hide behind capitalisation alone, so an exact string comparison")
    print("     never finds them.")
    print()

    # ---------------------------------------------------------------- STEP 2
    print(f"STEP 2: What duplicates cost at query time (week4 TOP_K = {TOP_K}).")
    wasted = 0
    for query in DUPLICATE_QUERIES:
        answers = [DOCS[i]["answer"] for i in search(query)]
        unique = len(set(answers))
        wasted += TOP_K - unique
        print(f"  Q: {query}")
        print(f"     answers handed to the LLM : {answers}")
        print(f"     distinct facts            : {unique} of {TOP_K}")
    print(f"  -> Across these {len(DUPLICATE_QUERIES)} questions, {wasted} of the"
          f" {TOP_K * len(DUPLICATE_QUERIES)} context slots carry")
    print("     a fact the LLM had already been given. The retriever did its job;")
    print("     the data wasted the budget.")
    print()

    # ---------------------------------------------------------------- STEP 3
    print("STEP 3: Some duplicated questions disagree with each other.")
    by_question = defaultdict(set)
    for d in DOCS:
        by_question[normalize(d["question"])].add(d["answer"].strip())
    conflicts = {q: a for q, a in by_question.items() if len(a) > 1}
    print(f"  Questions that appear more than once with different answers: {len(conflicts)}")
    for question, answers in conflicts.items():
        print(f"     {question[:66]}")
        for a in sorted(answers):
            print(f"        - {a}")
    print()
    demo = "Who scored the first ever goal in the FIFA Women's World Cup?"
    print(f"  What the pipeline actually sends to the LLM for:")
    print(f"  {demo}")
    for n, i in enumerate(search(demo), start=1):
        print(f"     [{n}] {DOCS[i]['answer']}")
    print("  -> Two numbered sources contradict each other. The prompt tells the")
    print("     LLM to answer only from the context and to cite it, so whichever")
    print("     one it picks, it will produce a confidently cited answer that has")
    print("     a 50/50 chance of being wrong. Note that not every case here is a")
    print("     real disagreement: some pairs are only spelling or word-order")
    print("     variants of the same answer, which is a different defect.")
    print()

    # ---------------------------------------------------------------- STEP 4
    print("STEP 4: Whitespace noise left over from the CSV conversion.")
    doubled = [d for d in DOCS if "  " in d["question"] or "  " in d["answer"]]
    excess = sum(len(full_text(d)) - len(full_text(d, clean=True)) for d in DOCS)
    print(f"  Entries containing a run of two or more spaces: {len(doubled)}"
          f" ({len(doubled) * 100 // total}% of the KB)")
    for d in doubled[:2]:
        print(f"     {d['question'][:70]!r}")
    print(f"  Excess space characters across the whole KB   : {excess}")
    over_now = sum(1 for d in DOCS if len(full_text(d)) > CHUNK_SIZE)
    over_clean = sum(1 for d in DOCS if len(full_text(d, clean=True)) > CHUNK_SIZE)
    print(f"  Entries longer than CHUNK_SIZE ({CHUNK_SIZE}) now      : {over_now}")
    print(f"  Entries longer than CHUNK_SIZE after cleaning  : {over_clean}")
    print(f"  -> week4 measures chunk length in characters, so padding counts")
    print(f"     against the budget. Collapsing runs of spaces alone keeps")
    print(f"     {over_now - over_clean} more entries whole instead of splitting them.")
    print()

    # ---------------------------------------------------------------- STEP 5
    print("STEP 5: Cleaning before indexing — and what it does not fix.")
    seen, kept = set(), []
    for i, d in enumerate(DOCS):
        key = normalize(d["question"])
        if key not in seen:
            seen.add(key)
            kept.append(i)
    print(f"  Normalise the question, then keep the first of each: {total} -> {len(kept)}"
          f" entries ({total - len(kept)} removed)")
    for query in DUPLICATE_QUERIES:
        before = len({DOCS[i]["answer"] for i in search(query)})
        after = len({DOCS[i]["answer"] for i in search(query, pool=kept)})
        print(f"     {query[:56]}")
        print(f"        distinct facts in Top-{TOP_K}: {before} -> {after}")
    print()
    print("  Two limits worth stating honestly:")
    print("     1. De-duplicating by question does not remove every repeated")
    print("        fact, because the same answer can be reached from two")
    print("        differently worded questions.")
    print(f"     2. It cannot resolve the {len(conflicts)} contradictions from STEP 3."
          " Keeping")
    print("        whichever copy came first just picks an answer at random;")
    print("        those entries need a person to check the source.")
    print()
    print("Cause: football_trivia_qa.txt was converted from trivia_questions.csv")
    print("and indexed as-is. week4 src/document_loader.py only strips each line,")
    print("and build_index.py embeds whatever it is handed, so there is no point")
    print("in the pipeline where duplicates, contradictions or padding are caught.")
    print()
    print("Status in my week4 system: NOT fixed — no normalisation or")
    print("de-duplication step exists between loading the file and building the")
    print("index. This simulation is the evidence for adding one.")


if __name__ == "__main__":
    run()
