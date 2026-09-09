# -*- coding: utf-8 -*-
# Problem 01: Hallucination / No evidence in Retrieved Context
#
# Same problem as the instructor's DL-05 problem01_hallucination.py, but
# demonstrated on MY OWN real dataset (football_trivia_qa.txt, from my
# week4 RAG-Project) instead of the instructor's sample data. This is a
# problem I actually ran into and already fixed in my real system — the
# second half of run() below shows exactly where the fix lives in
# week4/DL-04-RAG System Development I/RAG-Project/src/.
from data_loader import load_qa

DOCS = load_qa()


def retrieve(question, top_k=3):
    words = question.lower().split()
    scored = [(sum(w in d["text"].lower() for w in words), d) for d in DOCS]
    scored = [s for s in scored if s[0] > 0]
    scored.sort(key=lambda x: x[0], reverse=True)
    return [d for _, d in scored[:top_k]]


def bad_generate(question, context):
    if not context:
        # Simulated failure: the model still fabricates an answer even
        # without any evidence in the KB — a false, football-flavored
        # "fact" that sounds plausible but never happened.
        return ("The 1954 World Cup final was played in Bangkok, and "
                "Thailand won 3-1 against Brazil. "
                "(This fact does not exist in the Knowledge Base)")
    return context[0]["answer"]


def grounded_generate(question, context):
    if not context:
        return "No information found to support this answer in the Knowledge Base."
    return context[0]["answer"]


def run():
    q_in_kb = "Who scored the first ever goal in the English Premier League?"
    q_out_of_kb = "What is the boiling point of water in Celsius?"

    for label, q in [("Out of KB scope", q_out_of_kb), ("In KB", q_in_kb)]:
        ctx = retrieve(q)
        print(f"--- Query ({label}): {q}")
        print("Retrieved   :", [d["question"] for d in ctx] or "Not found")
        print("Bad answer  :", bad_generate(q, ctx))
        print("Fixed answer:", grounded_generate(q, ctx))
        print()

    print("Cause: The generator answers even though the Retrieved Context has no")
    print("supporting evidence, e.g. a question that is completely outside the scope")
    print("of the Knowledge Base (football_trivia_qa.txt).")
    print()
    print("=" * 70)
    print("How this is ALREADY fixed in my real system")
    print("(week4/DL-04-RAG System Development I/RAG-Project):")
    print("=" * 70)
    print("1. src/generator.py -> Generator.generate():")
    print('     if not chunks:')
    print('         return {"answer": config.NO_CONTEXT_MESSAGE, "sources": [], "no_context": True}')
    print("   The LLM is never even called when retrieval finds nothing, so it")
    print("   cannot hallucinate an answer to a question with no supporting chunk.")
    print()
    print("2. src/prompt_templates.py -> SYSTEM_PROMPT, rule 2:")
    print('     "If the information is not sufficient, reply with \\"{no_context}\\". Do not guess."')
    print("   Even when some context IS retrieved but it does not really answer the")
    print("   question, the LLM is explicitly told to refuse instead of guessing.")
    print()
    print("Verified on my own system: asking an out-of-scope question through")
    print("main.py (week4) returns config.NO_CONTEXT_MESSAGE, not a fabricated")
    print("football fact like the 'bad answer' simulated above.")


if __name__ == "__main__":
    run()
