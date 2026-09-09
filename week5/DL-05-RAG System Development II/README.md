# Week 5 — RAG System Problems & Fixes (My Own System)

This project follows the same structure as the instructor's [`DL-05-RAG System Development II`](https://github.com/aproot-en/Advanced-Topic-in-Computer-Software-Course/tree/main/DL-05-RAG%20System%20Development%20II), which demonstrates common problems in LLM and RAG (Retrieval-Augmented Generation) systems. The difference is that every simulation here uses my own dataset, football_trivia_qa.txt, and my own RAG system built in [`week4/DL-04-RAG System Development I/RAG-Project`](../../week4/DL-04-RAG%20System%20Development%20I/RAG-Project). Each problem is reproduced on real data, then traced back to where it is already handled in my week4 source code. Problems are added one at a time.

# Structure:

```text
DL-05-RAG System Development II/
├── football_trivia_qa.txt          # Raw data / RAG Knowledge Base (copied from week4)
├── data_loader.py                  # Shared parser: football_trivia_qa.txt -> list of dict
├── main.py                         # Main menu for running each problem
└── problem01_hallucination.py      # Hallucination / answer without supporting context
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
| 1 | Hallucination | The LLM answers without supporting context. | Done |
| 2 | Vocabulary Mismatch / Position | BoW cannot handle different wording or word order well. | Planned |
| 3 | Data Quality | Duplicate and noisy data reduce data quality. | Planned |
| 4 | Chunking | Poor chunk size or overlap can lose context. | Planned |
| 5 | Metadata Filtering | Similar content may have the wrong metadata. | Planned |
| 6 | Re-ranking | First-stage retrieval may rank the best document too low. | Planned |
| 7 | Faithfulness | Retrieval is correct, but generation changes important information. | Planned |
| 8 | RAG Configuration | Configuration controls which RAG components are active. | Planned |
| 9 | Evaluation | Measure chunking and retrieval with numerical metrics. | Planned |

All simulations use the same real Knowledge Base through `data_loader.py`.
This allows different LLM and RAG problems to be tested using the same dataset and pipeline.
