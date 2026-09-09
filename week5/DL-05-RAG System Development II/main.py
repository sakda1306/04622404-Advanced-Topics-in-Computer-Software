# -*- coding: utf-8 -*-
# Main script for demonstrating RAG problem scenarios found in MY OWN system
# (same structure as the instructor's DL-05 main.py, but every problem here
# comes from actually testing my week4 football trivia RAG system)
#
# Run:
#     python main.py
#
# Or select a problem directly:
#     python main.py 1
#
# Problems are added one at a time.

import sys

from problem01_vocabulary_mismatch import run as problem01

PROBLEMS = {
    1: ("Vocabulary Mismatch / Query Normalisation", problem01),
    # 2: ("Data Quality / Duplicates", problem02),          # planned
    # 3: ("Chunk Size / Overlap", problem03),               # planned
    # 4: ("Conversation Memory / Follow-up", problem04),    # planned
    # 5: ("Retrieval Evaluation", problem05),               # planned
}


def show_menu():
    print("*" * 65)
    print("   My RAG System — Problem-Based Simulations (Football Trivia)")
    print("*" * 65)
    for no, (name, _) in sorted(PROBLEMS.items()):
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
        available = "/".join(str(k) for k in sorted(PROBLEMS))
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
