# Week 5 — RAG System Problems & Fixes (My Own System)

This project follows the same structure as the instructor's [`DL-05-RAG System Development II`](https://github.com/aproot-en/Advanced-Topic-in-Computer-Software-Course/tree/main/DL-05-RAG%20System%20Development%20II), which demonstrates common problems in LLM and RAG (Retrieval-Augmented Generation) systems. The difference is that every problem here was found by actually testing my own RAG system built in [`week4/DL-04-RAG System Development I/RAG-Project`](../../week4/DL-04-RAG%20System%20Development%20I/RAG-Project), using my own dataset, football_trivia_qa.txt. Each `problemXX_*.py` reproduces the failure mode on the real knowledge base through a small simulation script and measures the damage at runtime, then reports the status of that problem in my week4 code. Problems are added one at a time.

# Structure:

```text
DL-05-RAG System Development II/
├── football_trivia_qa.txt              # Raw data / RAG Knowledge Base (copied from week4)
├── data_loader.py                      # Shared parser: football_trivia_qa.txt -> list of dict
├── main.py                             # Main menu for running each problem
├── problem01_vocabulary_mismatch.py    # Slang/abbreviation mismatch and the query normalisation bug
├── problem02_data_quality.py           # Duplicate entries, contradictory answers and whitespace noise
├── problem03_chunking.py               # Entries split by character count into unreadable fragments
├── problem04_memory.py                 # Follow-up questions searched without their conversation context
└── problem05_evaluation.py             # A golden set whose size, category mix and query variants are all skewed
```

# Dataset:
The project uses one shared Knowledge Base containing English questions and answers about football trivia, copied from `week4/DL-04-RAG System Development I/RAG-Project/data/football_trivia_qa.txt`.

The dataset contains 1,996 entries, covering 14 categories: General Football Trivia, World Cup, UEFA Champions League, Player Nationality & Background, English Premier League, UEFA European Championship, Copa America, Ballon d'Or, Serie A, MLS, La Liga, Bundesliga, Copa Libertadores, and Ligue 1.

Each entry has three lines:
```text

[หมวด: <category>]

Q: <question>
A: <answer>

```

Unlike the instructor's dataset, this one has no language variants — every entry is a single, plainly worded trivia question.

# Summary:

| # | Problem | Main Idea | Status |
|---|---------|-----------|--------|
| 1 | Vocabulary Mismatch | Slang and abbreviations do not match the words stored in the KB, and the normalisation that fixes it corrupts ordinary words. | Done |
| 2 | Data Quality | Duplicate entries fill every Top-K slot with the same answer, and some duplicated questions contradict each other. | Done |
| 3 | Chunking | Long entries are split by character count into fragments that start mid-word, and the main chunk loses the end of its answer. | Done |
| 4 | Conversation Memory | Follow-up questions are detected by a rule that misses most of them, and the history never reaches the query transformer. | Done |
| 5 | Retrieval Evaluation | The golden set's size, category mix and query variants are all skewed, so its scores blame the retriever for the test's own defects. | Done |

All simulations use the same real Knowledge Base through `data_loader.py`.
This allows different LLM and RAG problems to be tested using the same dataset and pipeline.
