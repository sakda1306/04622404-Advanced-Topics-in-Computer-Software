# -*- coding: utf-8 -*-
# Main script for demonstrating RAG problem scenarios on MY OWN system
# (same structure as the instructor's DL-05 main.py, but using my own week4
# football trivia RAG system and its own dataset/fixes instead of the
# instructor's sample project)
#
# Run:
#     python main.py
#
# Or select a problem directly:
#     python main.py 1
#
# Problems are added one at a time. More entries will be added to PROBLEMS
# below as each one is built, following the same 9-problem structure as the
# instructor's DL-05-RAG System Development II.

import sys

from problem01_hallucination import run as problem01

PROBLEMS = {
    1: ("Hallucination / Context", problem01),
    # 2: ("Vocabulary Mismatch / Position", problem02),   # planned
    # 3: ("Data Quality", problem03),                     # planned
    # 4: ("Chunk Size / Overlap", problem04),              # planned
    # 5: ("Metadata Filtering", problem05),                # planned
    # 6: ("Top-k / Re-ranking", problem06),                # planned
    # 7: ("Retrieval Correct, Generation Wrong", problem07),  # planned
    # 8: ("RAG Configuration", problem08),                 # planned
    # 9: ("Chunk & Retrieval Evaluation", problem09),       # planned
}


def show_menu():
    print("*" * 65)
    print("   My RAG System — Problem-Based Simulations (Football Trivia)")
    print("*" * 65)
    for no, (name, _) in PROBLEMS.items():
        print(f"{no:2}. {name}")
    print("*" * 65)


def execute(number):
    if number not in PROBLEMS:
        print(f"Problem {number} is not implemented yet.")
        return

    name, func = PROBLEMS[number]
    print("\n" + "*" * 65)
    print(f"PROBLEM {number}: {name}")
    print("*" * 65)
    func()


def main_loop():
    while True:
        show_menu()
        available = "/".join(str(k) for k in PROBLEMS)
        choice = input(f"Select a problem to simulate [{available}] or Q to exit: ").strip()

        if choice.upper() == "Q":
            print("Exiting the program")
            break

        try:
            number = int(choice)
        except ValueError:
            print(f"Please enter a number ({available}) or Q\n")
            continue

        execute(number)
        print()


if __name__ == "__main__":
    if len(sys.argv) > 1:
        arg = sys.argv[1].strip()
        if arg.upper() == "Q":
            sys.exit(0)
        try:
            execute(int(arg))
        except ValueError:
            print("Please enter a valid problem number or Q")
    else:
        main_loop()
