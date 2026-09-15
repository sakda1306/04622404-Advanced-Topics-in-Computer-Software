# -*- coding: utf-8 -*-
# Problem 05: Retrieval Evaluation — the test set measures its own defects
#
# Found by testing my own week4 evaluation step
# (week4/DL-04-RAG System Development I/RAG-Project/evaluation/build_golden_set.py).
# This script rebuilds the golden set from the real knowledge base using the
# same logic and seed as week4, so the items below are the same 56 that are
# actually used to score the system. Every number is measured at runtime.
#
# What the experiment shows, in order:
#   STEP 1  The test set is smaller than the config asks for.
#   STEP 2  Its category mix does not resemble the knowledge base.
#   STEP 3  One of the four query styles is barely present.
#   STEP 4  The scores say the system collapses on short queries.
#   STEP 5  It does not. The generator built the short queries wrong, and a
#           correct version of the same test scores twice as high.
import random
import re
from collections import Counter

from data_loader import load_qa

DOCS = load_qa()

# Values copied from week4 config.py and evaluation/build_golden_set.py.
GOLDEN_SET_SIZE = 60
SEED = 42
TOP_K = 3
GS_STOPWORDS = {"is", "are", "what", "where", "who", "when", "why", "how", "do",
                "does", "the", "a", "an", "and", "or", "of", "in", "on", "at",
                "to", "for", "with", "by", "about"}
TO_SLANG = {
    "goalkeeper": "goalie", "referee": "ref", "UEFA Champions League": "UCL",
    "English Premier League": "EPL", "Video Assistant Referee": "VAR",
    "manager": "gaffer", "field": "pitch", "forward": "striker",
}
PREFIXES = ["I want to know", "Could you tell me", "I wonder", ""]
SUFFIXES = [" please", " thanks", " mate", ""]

STOPWORDS = {
    "a", "an", "and", "are", "at", "be", "by", "did", "do", "does", "ever",
    "for", "from", "had", "has", "have", "how", "i", "in", "is", "it", "many",
    "most", "of", "on", "only", "or", "that", "this", "the", "to", "was",
    "were", "what", "when", "where", "which", "who", "with", "you",
}


def tokenize(text):
    return {w for w in re.findall(r"[a-z0-9']+", text.lower()) if w not in STOPWORDS}


DOC_TOKENS = [tokenize(d["text"]) for d in DOCS]


def ranking(query):
    q = tokenize(query)
    return sorted(range(len(DOCS)), key=lambda i: len(q & DOC_TOKENS[i]), reverse=True)


def content_words(question, lowercase_compare):
    """Word list after stripping stopwords — the step the partial variant uses."""
    stripped = re.sub(r"\(.*?\)", "", question)
    words = []
    for w in re.split(r"[\s()/]+", stripped):
        if not w or len(w) <= 1:
            continue
        probe = w.lower().strip("?,.") if lowercase_compare else w
        if probe not in GS_STOPWORDS:
            words.append(w)
    return words


def make_variants(question, rng):
    """Copied from week4 evaluation/build_golden_set.py."""
    variants = {"verbatim": question}

    slang = question
    for formal, casual in TO_SLANG.items():
        slang = slang.replace(formal, casual)
    if slang != question:
        variants["slang"] = slang

    words = content_words(question, lowercase_compare=False)
    if len(words) >= 2:
        variants["partial"] = " ".join(words[:max(2, int(len(words) * 0.6))])

    core = re.sub(r"^(what is|who is|where is|how to)\s*", "", question,
                  flags=re.IGNORECASE).strip()
    variants["natural"] = f"{rng.choice(PREFIXES)} {core}{rng.choice(SUFFIXES)}".strip()
    return variants


def build_golden_set():
    """Copied selection logic from week4 build_golden_set.py, same SEED."""
    rng = random.Random(SEED)
    by_category = {}
    for d in DOCS:
        by_category.setdefault(d["category"], []).append(d)

    selected = []
    per_category = max(1, GOLDEN_SET_SIZE // len(by_category))
    for pool in by_category.values():
        rng.shuffle(pool)
        selected.extend(pool[:per_category])
    selected = sorted(selected, key=lambda d: d["id"])[:GOLDEN_SET_SIZE]

    return [{"doc": d, "variants": make_variants(d["question"], rng)} for d in selected], \
        len(by_category), per_category


def measure(items, make_query):
    """Hit@1, Hit@3 and MRR for one way of phrasing the test questions."""
    hit1 = hit3 = counted = 0
    reciprocal = 0.0
    for item in items:
        query = make_query(item)
        if not query:
            continue
        counted += 1
        rank = ranking(query).index(item["doc"]["id"]) + 1
        hit1 += rank == 1
        hit3 += rank <= TOP_K
        reciprocal += 1.0 / rank
    if not counted:
        return 0, 0.0, 0.0, 0.0
    return counted, hit1 / counted, hit3 / counted, reciprocal / counted


def run():
    items, n_categories, per_category = build_golden_set()

    # ---------------------------------------------------------------- STEP 1
    print("STEP 1: The test set is smaller than the config asks for.")
    print(f"  config.GOLDEN_SET_SIZE            : {GOLDEN_SET_SIZE}")
    print(f"  Categories in the knowledge base  : {n_categories}")
    print(f"  Items per category the code takes : {GOLDEN_SET_SIZE} // {n_categories}"
          f" = {per_category}")
    print(f"  Test questions actually produced  : {len(items)}"
          f"  ({per_category} x {n_categories})")
    print(f"  -> The integer division quietly drops"
          f" {GOLDEN_SET_SIZE - len(items)} questions. Nothing warns that the")
    print("     test set is not the size that was asked for.")
    print()

    # ---------------------------------------------------------------- STEP 2
    print("STEP 2: The category mix does not resemble the knowledge base.")
    real = Counter(d["category"] for d in DOCS)
    gold = Counter(i["doc"]["category"] for i in items)
    print(f"  {'category':34}{'in test':>10}{'in KB':>16}{'weight':>9}")
    factors = {}
    for category, count in real.most_common():
        share_test = gold.get(category, 0) / len(items) * 100
        share_kb = count / len(DOCS) * 100
        factors[category] = share_test / share_kb
        print(f"  {category[:34]:34}{gold.get(category, 0):>4} ({share_test:4.1f}%)"
              f"{count:>7} ({share_kb:5.2f}%){factors[category]:>8.1f}x")
    biggest = max(factors, key=factors.get)
    smallest = min(factors, key=factors.get)
    print(f"  -> Every category gets {per_category} questions regardless of its real size,")
    print(f"     so {biggest} counts {factors[biggest] / factors[smallest]:.0f} times more")
    print(f"     per question than {smallest} does. A score from this test is not")
    print("     a score for the traffic the system will actually see.")
    print()

    # ---------------------------------------------------------------- STEP 3
    print("STEP 3: One of the four query styles barely exists.")
    coverage = Counter()
    for item in items:
        for name in item["variants"]:
            coverage[name] += 1
    for name, count in coverage.most_common():
        print(f"     {name:10} {count:>3} of {len(items)} questions"
              f" ({count * 100 // len(items)}%)")
    print("  -> The slang variant only appears when a question happens to contain")
    print("     one of the words in TO_SLANG, so the robustness-to-slang claim")
    print(f"     rests on {coverage['slang']} questions.")
    print()

    # ---------------------------------------------------------------- STEP 4
    print("STEP 4: What the scores say.")
    print(f"  {'variant':12}{'questions':>11}{'Hit@1':>9}{'Hit@3':>9}{'MRR':>9}")
    for name in ["verbatim", "slang", "partial", "natural"]:
        n, h1, h3, mrr = measure(items, lambda it, v=name: it["variants"].get(v))
        print(f"  {name:12}{n:>11}{h1:>9.3f}{h3:>9.3f}{mrr:>9.3f}")
    print("  -> Read at face value, this says the system is strong on full")
    print("     questions and falls apart on short keyword queries.")
    print()

    # ---------------------------------------------------------------- STEP 5
    print("STEP 5: The short queries were built wrong.")
    print("  build_golden_set.py compares each word against a lowercase STOPWORDS")
    print("  set without lowercasing the word first:")
    for w in ["Who", "What", "Which", "who", "what"]:
        print(f"     {w!r:8} in STOPWORDS -> {w in GS_STOPWORDS}")
    print("  So the capitalised question word survives, and then the code keeps the")
    print("  FIRST 60% of what is left — which is the generic opening, not the topic:")
    for item in items[:3]:
        print(f"     full   : {item['doc']['question'][:58]}")
        print(f"     partial: {item['variants']['partial']}")
    print()

    def partial_all(item):
        words = content_words(item["doc"]["question"], lowercase_compare=True)
        return " ".join(words) if len(words) >= 2 else None

    def partial_tail(item):
        words = content_words(item["doc"]["question"], lowercase_compare=True)
        if len(words) < 2:
            return None
        return " ".join(words[-max(2, int(len(words) * 0.6)):])

    print("  The same 56 questions, with the short query built correctly:")
    print(f"  {'variant of the test':34}{'Hit@1':>9}{'Hit@3':>9}{'MRR':>9}")
    rows = [
        ("partial as week4 builds it", lambda it: it["variants"].get("partial")),
        ("partial, keeping the topic tail", partial_tail),
        ("partial, all content words", partial_all),
        ("verbatim (the ceiling)", lambda it: it["variants"]["verbatim"]),
    ]
    for label, fn in rows:
        _, h1, h3, mrr = measure(items, fn)
        print(f"  {label:34}{h1:>9.3f}{h3:>9.3f}{mrr:>9.3f}")
    print("  -> The retriever never changed. Keeping the end of the question")
    print("     instead of the beginning nearly doubles the reported Hit@1, and")
    print("     the middle row is the honest one: still a genuinely short query,")
    print("     still below the ceiling, but now failing for real reasons rather")
    print("     than because the topic was deleted from the question.")
    print()
    print("Cause: the test generator has three independent defects — integer")
    print("division for the sample size, one fixed quota per category regardless")
    print("of how large the category is, and a case-sensitive stopword comparison")
    print("that keeps the question word while discarding the subject.")
    print()
    print("Status in my week4 system: NOT fixed — evaluation/build_golden_set.py")
    print("still produces this test set, so every retrieval score reported from it")
    print("carries these three distortions.")


if __name__ == "__main__":
    run()
