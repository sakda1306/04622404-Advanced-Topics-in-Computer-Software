

# prompt_templates.py
# Store all prompt templates in one place.
# Makes prompts easier to manage, compare, and update.
# Answers must be based only on the retrieved context.
# Inline citations are required for traceable and verifiable responses.


import config

SYSTEM_PROMPT = """You are a football expert. Answer the question based ONLY on the provided "Reference Information".

Rules:
1. Use ONLY the information in the "Reference Information". Do not add outside knowledge.
2. If the information is not sufficient, reply with "{no_context}". Do not guess.
3. Cite the reference numbers like [1] [2] at the end of the sentence where the information is used.
4. Use polite and conversational language.
5. Keep your answer concise, no more than 5-6 sentences."""

USER_PROMPT = """{history}Reference Information:
{context}

User's Question: {question}

Answer using only the reference information above, and include citations [n]."""


def format_context(chunks, max_chars=6000):
    """
    เรียง chunk เป็นบล็อกอ้างอิงมีหมายเลข

    max_chars กันไม่ให้ prompt ยาวเกิน context window — chunk เรียงจากดีสุดมาก่อน
    การตัดท้ายจึงตัดชิ้นที่เกี่ยวข้องน้อยที่สุดออก
    """
    blocks, used = [], 0
    for i, chunk in enumerate(chunks, start=1):
        block = f"[{i}] {chunk.get('answer') or chunk.get('text', '')}"
        if used + len(block) > max_chars:
            break
        blocks.append(block)
        used += len(block)
    return "\n\n".join(blocks)


def build_messages(question, chunks, history=""):
    """ประกอบเป็น messages list สำหรับส่งให้ LLM"""
    history_block = f"บทสนทนาก่อนหน้า:\n{history}\n\n" if history else ""
    return [
        {"role": "system", "content": SYSTEM_PROMPT.format(no_context=config.NO_CONTEXT_MESSAGE)},
        {
            "role": "user",
            "content": USER_PROMPT.format(
                history=history_block,
                context=format_context(chunks),
                question=question,
            ),
        },
    ]


# --------------------------------------------------- query transform
REWRITE_PROMPT = """Rewrite the user query to make it clearer and more suitable for searching in a football trivia database.
- Correct any spelling mistakes.
- If it's a follow-up question, add context from the conversation history to make it self-contained.
- Output ONLY the rewritten query on a single line, with no explanations.

{history}Original query: {question}

Rewritten query:"""

MULTI_QUERY_PROMPT = """Generate {n} different versions of the given question to improve search coverage.
- Use different wording and synonyms (e.g., slang and formal terms).
- The core meaning must remain the same as the original question.
- Output 1 question per line. Do not number them.

Original question: {question}

Generated questions:"""

HYDE_PROMPT = """Write a hypothetical "fake answer" for the following question.
- Write 3-5 sentences using football terminology that would likely appear in real documents.
- Do not worry about factual accuracy; this is only used as a search proxy.

Question: {question}

Hypothetical answer:"""


# ------------------------------------------- LLM judge (ตอน evaluate)
JUDGE_PROMPT = """Evaluate the "Answer" based on the following criteria: {criteria}. Give a score from 1 to 5.
(5 = Excellent, 3 = Average, 1 = Poor)

{reference}
Question: {question}

Answer:
{answer}

Respond ONLY in JSON format: {{"score": <1-5>, "reason": "<short reason>"}}"""
