# -*- coding: utf-8 -*-
# Problem 01: Vocabulary Mismatch — the words users type vs the words in the KB
#
# This problem was found by actually testing my own week4 system
# (week4/DL-04-RAG System Development I/RAG-Project), not by copying the
# instructor's example. Every number printed below is measured at runtime
# against the real knowledge base, not hard-coded.
#
# What the experiment shows, in order:
#   STEP 1  Slang and abbreviations really do miss the documents.
#   STEP 2  The SLANG_MAP in my week4 query_transform.py fixes that.
#   STEP 3  ...but the way it replaces text also CORRUPTS ordinary words,
#           which makes retrieval much worse than doing nothing at all.
#   STEP 4  Replacing only on word boundaries fixes STEP 3 while keeping STEP 2.
import re

from data_loader import load_qa

DOCS = load_qa()

# Copied verbatim from week4 .../src/query_transform.py for the simulation.
# The week4 file itself is never imported or modified.
SLANG_MAP = {
    "goalie": "goalkeeper",
    "ref": "referee",
    "UCL": "UEFA Champions League",
    "EPL": "English Premier League",
    "VAR": "Video Assistant Referee",
    "gaffer": "manager",
    "pitch": "field",
    "striker": "forward",
}

STOPWORDS = {
    "a", "an", "and", "are", "at", "be", "by", "did", "do", "does", "ever",
    "for", "from", "had", "has", "have", "how", "i", "in", "is", "it", "many",
    "most", "of", "on", "only", "or", "that", "the", "this", "to", "was",
    "were", "what", "when", "where", "which", "who", "with", "you",
}


def tokenize(text):
    return {w for w in re.findall(r"[a-z0-9']+", text.lower()) if w not in STOPWORDS}


DOC_TOKENS = [tokenize(d["text"]) for d in DOCS]


def ranking(query):
    """Rank every document by how many content words it shares with the query."""
    q = tokenize(query)
    return sorted(range(len(DOCS)), key=lambda i: len(q & DOC_TOKENS[i]), reverse=True)


def rank_of(query, doc_ids):
    """Best position (1 = top) that any of the target documents reaches."""
    order = ranking(query)
    return min(order.index(i) + 1 for i in doc_ids)


def normalize_current(query):
    """Exactly what week4 query_transform.normalize_query() does today."""
    for slang, formal in SLANG_MAP.items():
        query = query.replace(slang, formal)
    return query


def normalize_word_boundary(query):
    """Proposed fix: replace a slang term only when it is a whole word."""
    for slang, formal in SLANG_MAP.items():
        query = re.sub(rf"\b{re.escape(slang)}\b", formal, query)
    return query


def run():
    # ---------------------------------------------------------------- STEP 1
    print("STEP 1: Do slang and abbreviations actually miss the documents?")
    slang_q = "Who scored the first ever goal in the EPL?"
    formal_q = "Who scored the first ever goal in the English Premier League?"
    epl_hits = sum(1 for t in DOC_TOKENS if "epl" in t)
    print(f"  Slang question : {slang_q}")
    print(f"     content words: {sorted(tokenize(slang_q))}")
    print(f"  Formal question: {formal_q}")
    print(f"     content words: {sorted(tokenize(formal_q))}")
    print(f"  Documents in the KB containing the token 'epl': {epl_hits}")
    print("  -> The abbreviation the user types appears nowhere in the KB, so it")
    print("     contributes nothing to the search. This is Vocabulary Mismatch.")
    print()

    # ---------------------------------------------------------------- STEP 2
    print("STEP 2: Does the SLANG_MAP in my week4 system help?")
    gaffer_q = "Which gaffer has won the most titles?"
    manager_docs = [i for i, d in enumerate(DOCS) if "manager" in d["text"].lower()]
    raw_rank = rank_of(gaffer_q, manager_docs)
    fixed_rank = rank_of(normalize_current(gaffer_q), manager_docs)
    print(f"  Query: {gaffer_q}")
    print(f"     without normalisation -> best manager document at rank {raw_rank}")
    print(f"     after  normalisation  -> best manager document at rank {fixed_rank}")
    print(f"        (query became: {normalize_current(gaffer_q)!r})")
    print("  -> The mapping earns its place: it moves the right document up.")
    print()

    # ---------------------------------------------------------------- STEP 3
    print("STEP 3: But HOW it replaces text is the bug.")
    print("  SLANG_MAP uses str.replace(), which does not respect word boundaries,")
    print('  so the pair "ref" -> "referee" also rewrites words that merely CONTAIN "ref".')
    for probe in ["Who was the referee in the 1966 World Cup final?",
                  "Who is the preferred penalty taker?"]:
        print(f"     IN : {probe}")
        print(f"     OUT: {normalize_current(probe)}")
    print()

    referee_q = "Who was the referee in the 1966 World Cup final?"
    referee_docs = [i for i, d in enumerate(DOCS) if "referee" in d["text"].lower()]
    before = rank_of(referee_q, referee_docs)
    after = rank_of(normalize_current(referee_q), referee_docs)
    print(f"  Measured damage on the real knowledge base")
    print(f"  ({len(referee_docs)} documents mention a referee):")
    print(f"     original query          -> best referee document at rank {before}")
    print(f"     after normalisation     -> best referee document at rank {after}")
    print(f"  -> The most important word of the question is turned into")
    print(f"     'refereeeree', a token that exists in no document at all, so the")
    print(f"     query loses its only discriminating term. Normalisation made the")
    print(f"     result {after - before} positions WORSE than doing nothing.")
    print(f"     With week4 CANDIDATE_K = 20, rank {after} never enters the candidate")
    print("     pool, so the correct document can never be selected as an answer.")
    print()

    # ---------------------------------------------------------------- STEP 4
    print("STEP 4: The fix — replace only on word boundaries.")
    print(r"     re.sub(rf'\b{slang}\b', formal, query)   instead of   query.replace(slang, formal)")
    print()
    print(f"     referee query -> rank {rank_of(normalize_word_boundary(referee_q), referee_docs)}"
          f"  (was {after} with the current code, {before} with no normalisation)")
    print(f"     gaffer query  -> rank {rank_of(normalize_word_boundary(gaffer_q), manager_docs)}"
          f"  (STEP 2 behaviour is preserved)")
    print()
    print("     Every other mapping still works, and words that merely contain a")
    print("     slang term are left alone:")
    for probe in ["Who won the UCL in 2005?",
                  "Which goalie is the best?",
                  "What is VAR used for?",
                  "Who is the preferred penalty taker?"]:
        print(f"        {probe}")
        print(f"           current  : {normalize_current(probe)}")
        print(f"           fixed    : {normalize_word_boundary(probe)}")
    print()
    print("Cause: a lookup table that rewrites raw substrings cannot tell the")
    print("difference between the word 'ref' and the first three letters of")
    print("'referee' or 'preferred'. The shorter the key, the more words it damages.")
    print()
    print("Status in my week4 system: NOT fixed yet — src/query_transform.py still")
    print("uses str.replace(). This simulation is the evidence for changing it.")


if __name__ == "__main__":
    run()
