"""Split documents into chunks by meaning, never by character count (week5 #3).

- trivia: one question-answer pair is one chunk
- everything else: one chunk per "## " section, each led by the document title
"""

from __future__ import annotations

from app.kb.documents import Chunk, Document

HEADING = "## "


def chunk_document(document: Document) -> list[Chunk]:
    if document.category == "trivia":
        return [_trivia_chunk(document)]
    return _section_chunks(document)


def split_qa(text: str) -> tuple[str, str]:
    question = answer = ""
    for line in text.splitlines():
        if line.startswith("Q:"):
            question = line[2:].strip()
        elif line.startswith("A:"):
            answer = line[2:].strip()
    return question, answer


def _trivia_chunk(document: Document) -> Chunk:
    question, answer = split_qa(document.text)
    return Chunk(
        chunk_id=f"{document.doc_id}#c0",
        doc_id=document.doc_id,
        ord=0,
        text=document.text,
        # Users type questions, so matching the question counts twice (as in week4).
        bm25_text=f"{question} {question} {answer}",
    )


def _section_chunks(document: Document) -> list[Chunk]:
    sections: list[list[str]] = [[]]
    for line in document.text.splitlines():
        if line.startswith(HEADING):
            sections.append([line])
        else:
            sections[-1].append(line)

    chunks: list[Chunk] = []
    for lines in sections:
        body = "\n".join(lines).strip()
        if not body:
            continue
        # The title keeps a cut-out section tied to its match, table or report.
        text = f"{document.title}\n{body}"
        ord_ = len(chunks)
        chunks.append(Chunk(f"{document.doc_id}#c{ord_}", document.doc_id, ord_, text, text))
    return chunks
