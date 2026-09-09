# -*- coding: utf-8 -*-
# Load and parse football_trivia_qa.txt into records shared by problem01-xx.
#
# Same file format as the instructor's DL-05 (sex_q_a.txt), but the source
# dataset here is my own week4 football trivia knowledge base instead of the
# instructor's Thai sexual-health data:
#     [หมวด: <category>]
#     Q: <question>
#     A: <answer>
# Lines starting with # are file header/comments and are skipped.
#
# Note: unlike the instructor's dataset, football_trivia_qa.txt has no
# formal/casual/slang "| ภาษา: <variant>" suffix on the category header, so
# there is no "lang" field here.
import os
import re

DATA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "football_trivia_qa.txt")

_HEADER_RE = re.compile(r"\[หมวด:\s*(.+?)\]")


def load_qa(path=DATA_PATH):
    # Returns a list of dict: id, category, question, answer, text
    with open(path, encoding="utf-8") as f:
        raw = f.read()

    entries = []
    for block in raw.split("\n\n"):
        block = block.strip()
        if not block or block.startswith("#"):
            continue

        lines = block.split("\n")
        if len(lines) < 3:
            continue
        header, q_line, a_line = lines[0], lines[1], lines[2]

        m = _HEADER_RE.match(header)
        if not m:
            continue
        category = m.group(1).strip()

        question = q_line[2:].strip() if q_line.startswith("Q:") else q_line.strip()
        answer = a_line[2:].strip() if a_line.startswith("A:") else a_line.strip()
        if not question or not answer:
            continue

        entries.append({
            "id": len(entries),
            "category": category,
            "question": question,
            "answer": answer,
            "text": f"{question} {answer}",
        })
    return entries


def categories(entries=None):
    entries = entries if entries is not None else load_qa()
    return sorted(set(e["category"] for e in entries))


if __name__ == "__main__":
    data = load_qa()
    print("Total Q&A count:", len(data))
    print("Number of categories:", len(categories(data)))
    print("First entry example:", data[0])
