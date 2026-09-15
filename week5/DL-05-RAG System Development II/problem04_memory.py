# -*- coding: utf-8 -*-
# Problem 04: Conversation Memory — follow-up questions are searched blind
#
# Found by testing my own week4 multi-turn path
# (week4/DL-04-RAG System Development I/RAG-Project/src/memory.py and
# src/query_transform.py). Every number below is measured at runtime.
#
# What the experiment shows, in order:
#   STEP 1  Why a follow-up is dangerous on this dataset: 22 questions differ
#           only by the year, so a question missing its context is ambiguous.
#   STEP 2  is_followup() misses most real follow-ups, and why.
#   STEP 3  What that costs: the correct document falls out of the Top-K and
#           the LLM is handed the answer for the wrong year.
#   STEP 4  Even when detection succeeds, the configured transform mode throws
#           the conversation history away before it is used.
#   STEP 5  Both halves have to be fixed, measured — including the tradeoff.
import re

from data_loader import load_qa

DOCS = load_qa()

TOP_K = 3  # from week4 config.py

STOPWORDS = {
    "a", "an", "and", "are", "at", "be", "by", "did", "do", "does", "ever",
    "for", "from", "had", "has", "have", "how", "i", "in", "is", "it", "many",
    "most", "of", "on", "only", "or", "that", "this", "the", "to", "was",
    "were", "what", "when", "where", "which", "who", "with", "you",
}

# Copied verbatim from week4 src/memory.py.
MARKERS = ("he ", "she ", "it ", "they ", "then", "what about", "how about",
           "this", "that", "why", "and")

# A conversation a real user would have with this knowledge base.
FIRST_TURN = "Who won the FIFA World Cup in 1966?"
FOLLOW_UPS = [
    "Who finished second?",
    "Where was it held?",
    "What about 1970?",
    "Who was their captain?",
    "And third place?",
    "Why was that final controversial?",
    "How many goals were scored in that final?",
    "Who scored in it?",
    "That was in England right?",
    "Did they win again later?",
]

# Words that point at something said earlier instead of naming it.
REFERENTIAL = {"it", "its", "he", "him", "his", "she", "her", "they", "them",
               "their", "that", "this", "those", "these", "there", "then",
               "one", "same", "again"}


def tokenize(text):
    return {w for w in re.findall(r"[a-z0-9']+", text.lower()) if w not in STOPWORDS}


DOC_TOKENS = [tokenize(d["text"]) for d in DOCS]


def ranking(query):
    q = tokenize(query)
    return sorted(range(len(DOCS)), key=lambda i: len(q & DOC_TOKENS[i]), reverse=True)


def is_followup_current(query):
    """Copied verbatim from week4 memory.ConversationMemory.is_followup()."""
    text = query.strip().lower()
    return len(text) < 50 and text.startswith(MARKERS)


def is_followup_fixed(query):
    """Proposed rule: look for a referential word anywhere, not just at the start."""
    text = query.strip().lower()
    if set(re.findall(r"[a-z']+", text)) & REFERENTIAL:
        return True
    if text.startswith(("what about", "how about")):
        return True
    return len(re.findall(r"[a-z0-9']+", text)) <= 4


class RecordingLLM:
    """Stands in for the real LLM so we can see what reaches the prompt."""

    def __init__(self):
        self.prompts = []

    def chat(self, prompt):
        self.prompts.append(prompt)
        return "alternative question"


def transform(query, history, mode, llm):
    """Copied dispatch logic from week4 query_transform.QueryTransformer.transform()."""
    if mode == "rewrite":
        return llm.chat(f"Chat History:\n{history}\n\nOriginal query: {query}")
    if mode == "hyde":
        return llm.chat(f"Question: {query}")      # history parameter never used
    return llm.chat(f"Original question: {query}")  # multi_query: same


def run():
    # ---------------------------------------------------------------- STEP 1
    print("STEP 1: Why follow-ups are dangerous on this knowledge base.")
    family = [d for d in DOCS
              if d["question"].lower().startswith("who finished second in the fifa world cup")]
    target = next(d["id"] for d in family if "1966" in d["question"])
    print(f'  Questions of the form "Who finished second in the FIFA World Cup in ____?"'
          f' in the KB: {len(family)}')
    print(f"  They differ by one token — the year. The correct one for this")
    print(f"  conversation is entry {target}: {DOCS[target]['answer']}")
    print("  -> Drop the year and the question matches all of them equally well.")
    print()

    # ---------------------------------------------------------------- STEP 2
    print("STEP 2: Does is_followup() recognise a follow-up?")
    print(f'  Conversation so far — user asked: "{FIRST_TURN}"')
    detected = 0
    missed_by_length = missed_by_start = 0
    for q in FOLLOW_UPS:
        got = is_followup_current(q)
        detected += got
        if not got:
            text = q.strip().lower()
            if len(text) >= 50:
                missed_by_length += 1
            if not text.startswith(MARKERS):
                missed_by_start += 1
        print(f"     {'detected' if got else 'MISSED  '}  {q}")
    print(f"  -> {detected} of {len(FOLLOW_UPS)} follow-ups are recognised.")
    print(f"     Missed because the text is 50 characters or longer : {missed_by_length}")
    print(f"     Missed because it does not START with a marker word: {missed_by_start}")
    print("     The rule only looks at the beginning of the sentence, so a pronoun")
    print("     sitting anywhere else is invisible to it.")
    print()

    # ---------------------------------------------------------------- STEP 3
    print("STEP 3: What a missed follow-up costs.")
    bare = "Who finished second?"
    resolved = "Who finished second in the FIFA World Cup in 1966?"
    for label, query in [("searched as typed", bare),
                         ("searched with the context filled in", resolved)]:
        order = ranking(query)
        print(f"  {label}: {query!r}")
        print(f"     rank of the correct entry: {order.index(target) + 1}")
        for n, i in enumerate(order[:TOP_K], start=1):
            mark = "  <- correct" if i == target else ""
            print(f"        [{n}] {DOCS[i]['question'][:52]} -> {DOCS[i]['answer'][:20]}{mark}")
    print("  -> Searched as typed, the LLM receives answers for the wrong years and")
    print("     never sees the right one. It then answers confidently with a")
    print("     citation, because the prompt tells it to trust the context it is given.")
    print()

    # ---------------------------------------------------------------- STEP 4
    print("STEP 4: Even a detected follow-up loses its history.")
    history = f"User: {FIRST_TURN}\nAssistant: England."
    for mode in ["multi_query", "rewrite", "hyde"]:
        llm = RecordingLLM()
        transform("Who finished second?", history, mode, llm)
        reached = any("1966" in p for p in llm.prompts)
        note = "" if reached else "   <- history discarded"
        print(f"     QUERY_TRANSFORM_MODE = {mode:12} history reaches the prompt: {reached}{note}")
    print("  -> week4 config.py sets QUERY_TRANSFORM_MODE = 'multi_query', so the")
    print("     history is dropped before it can be used. In the shipped")
    print("     configuration, whatever is_followup() returns changes nothing about")
    print("     the search. (The history does still reach the generator, so the LLM")
    print("     can see the conversation while writing — but by then retrieval has")
    print("     already fetched the wrong documents.)")
    print()

    # ---------------------------------------------------------------- STEP 5
    print("STEP 5: The fix — both halves, measured.")
    print("  Half 1: look for a referential word anywhere in the question.")
    now = sum(is_followup_current(q) for q in FOLLOW_UPS)
    fixed = sum(is_followup_fixed(q) for q in FOLLOW_UPS)
    print(f"     follow-ups recognised: {now} of {len(FOLLOW_UPS)} -> {fixed} of {len(FOLLOW_UPS)}")

    standalone = [d["question"] for d in DOCS[:400] if 35 < len(d["question"]) < 90][:10]
    false_now = sum(is_followup_current(q) for q in standalone)
    false_fixed = sum(is_followup_fixed(q) for q in standalone)
    print(f"     self-contained questions wrongly flagged: {false_now} of"
          f" {len(standalone)} -> {false_fixed} of {len(standalone)}")
    for q in standalone:
        if is_followup_fixed(q) and not is_followup_current(q):
            print(f"        the false positive: {q}")
            print("        (it says 'his', but the person is named in the same sentence)")
    print("     That tradeoff is worth taking: a false positive only passes some")
    print("     extra context to the query rewriter, while a false negative sends")
    print("     an ambiguous question straight to the retriever.")
    print()
    print("  Half 2: pass the history in every mode, not only in 'rewrite'.")
    print("     Fixing the detector alone changes nothing while the configured mode")
    print("     still discards what it detects, as STEP 4 shows.")
    print()
    print("Cause: the follow-up rule is a prefix match against a fixed list of words,")
    print("and the query transformer takes a history argument that two of its three")
    print("modes never read.")
    print()
    print("Status in my week4 system: NOT fixed — memory.py still matches only the")
    print("start of the question, and query_transform.py still passes history to")
    print("rewrite() alone.")


if __name__ == "__main__":
    run()
