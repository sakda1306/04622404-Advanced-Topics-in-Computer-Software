"""Draft eval/golden_thai.jsonl: Thai questions as fans type them, tied to their documents.

    python -m scripts.build_golden_thai draft            # needs GROQ_API_KEY and GROQ_MODEL
    python -m scripts.build_golden_thai refresh-routed   # after the router rules change

`draft` writes eval/golden_thai.draft.jsonl (not committed). A person reads every item
against its documents, fixes or drops bad ones, and saves eval/golden_thai.jsonl.
`refresh-routed` recomputes each item's `routed` field with the router's rules
(services/03_ai_router_agent) in a subprocess: both services name their package `app`.
"""

from __future__ import annotations

import argparse
import itertools
import json
import os
import random
import subprocess
import sys
from collections import Counter
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.kb.documents import Document
from app.kb.trivia import load_trivia_documents
from scripts.build_golden import allocate
from scripts.eval_retrieval import EVAL_DIR, _jsonl, load_live_documents

SERVICE = Path(__file__).parents[1]
ROUTER_DIR = SERVICE.parent / "03_ai_router_agent"
DRAFT_FILE = EVAL_DIR / "golden_thai.draft.jsonl"
GOLDEN_FILE = EVAL_DIR / "golden_thai.jsonl"
SEED = 20261001
SIZES = {"trivia_th": 40, "match_th": 20, "multi_doc": 10}
LIVE_PAIRS = 6  # multi_doc groups from match reports; the rest pair trivia documents
DOC_CHARS = 1500
GROQ_URL = "https://api.groq.com/openai/v1"
# Same clock as the live fixture: the day after matchweek 5's last game (21 Sep 2026).
ROUTER_CONTEXT = {"season": "2026", "current_matchweek": 5, "now": "2026-09-22T10:00:00+07:00"}

QUESTION_RULES = (
    "เขียนคำถามภาษาไทย 1 ข้อ แบบที่แฟนบอลคนไทยพิมพ์ถามในแชต (ภาษาพูด สั้น ไม่เป็นทางการ)\n"
    "- คำตอบต้องอยู่ในเอกสารที่ให้มา และห้ามใส่คำตอบไว้ในคำถาม\n"
    "- เลี่ยงคำและวลีที่อยู่ในเอกสาร ใช้คำของตัวเองแทน\n"
    "- ถ้ามีทีมพรีเมียร์ลีก ใช้ชื่อเล่นภาษาไทย เช่น ปืนใหญ่ หงส์แดง ผีแดง เรือใบ สิงห์บลู "
    "ไก่เดือยทอง สาลิกาดง สิงห์ผงาด\n"
    '- ตอบเป็น JSON {"question": "..."} เท่านั้น'
)
KIND_RULES = {
    "trivia_th": "เอกสารเป็นคำถาม-คำตอบความรู้ฟุตบอล ถามเรื่องเดียวกันด้วยคำของตัวเอง",
    "match_th": (
        "เอกสารเป็นข้อมูลพรีเมียร์ลีกฤดูกาล 2026/27 วันนี้คือ 22 ก.ย. 2026 นัดล่าสุดคือนัดที่ 5 "
        "ถามแบบ 'เมื่อวาน' 'นัดล่าสุด' 'นัดที่ 4' หรือ 'นัดหน้า' ได้"
    ),
    "multi_doc": (
        "คำถามต้องใช้ข้อมูลจากเอกสารทุกฉบับที่ให้มาจึงตอบได้ครบ เช่น เทียบสองนัด หรือถามสองเรื่องในประโยคเดียว"
    ),
}
ANGLES = (
    "ถามเรื่องหลักของเอกสาร เช่น ผล สกอร์ อันดับ หรือโปรแกรม",
    "ถามรายละเอียดอื่น เช่น คนยิง เวลาที่ยิง สนาม หรือเหตุการณ์ในเกม",
)
# Hand-written: the knowledge base has no answer (other leagues, transfers, not football,
# chatter about the assistant, or questions too vague to point at a document).
OUT_OF_KB_TH = (
    ("ลาลีกาเมื่อคืนบาร์ซ่าชนะใครมา", "football"),
    ("ทีมชาติไทยนัดล่าสุดเจอใคร", "football"),
    ("ค่าตัวฮาลันด์ตอนนี้เท่าไหร่", "football"),
    ("ซาลาห์ต่อสัญญากี่ปี", "football"),
    ("ตั๋วเข้าแอนฟิลด์ราคาเท่าไหร่", "football"),
    ("บุนเดสลีกาตอนนี้ใครนำตาราง", "football"),
    ("พรุ่งนี้ฝนจะตกไหม", "other"),
    ("สูตรต้มยำกุ้งทำยังไง", "other"),
    ("หุ้นตัวไหนน่าซื้อ", "other"),
    ("ช่วยเขียนโค้ด python อ่านไฟล์ csv ให้หน่อย", "other"),
    # meta: greetings and questions about the assistant itself
    ("คุณช่วยอะไรฉันได้มั้ย", "meta"),
    ("ถามอะไรได้บ้าง", "meta"),
    ("นี้ๆ", "meta"),
    ("สวัสดีครับ", "meta"),
    ("บอทนี้เอาข้อมูลมาจากไหน", "meta"),
    # vague: too open to point at any document
    ("ใครวิ่งเร็วสุด", "vague"),
    ("ใครเก่งสุด", "vague"),
    ("ทีมไหนดี", "vague"),
    ("แล้วไงต่อ", "vague"),
    ("ขอข้อมูลหน่อย", "vague"),
)
# Hand-written (v1.11): questions the 07 archive answers. Either listed document answers;
# Blackburn, Leicester and West Ham have no team_id, so they test text-only matching.
HISTORICAL_TH = (
    ("ใครได้แชมป์พรีเมียร์ลีกฤดูกาล 2004/05", ("hist-season-2004",), "season_table"),
    ("พรีเมียร์ลีกปี 2015 ทีมไหนตกชั้นบ้าง", ("hist-season-2015",), "season_table"),
    ("ฤดูกาล 98/99 ใครได้รองแชมป์พรีเมียร์ลีก", ("hist-season-1998",), "season_table"),
    (
        "ตารางคะแนนพรีเมียร์ลีกฤดูกาล 2011/12 ใครเป็นแชมป์ ได้กี่แต้ม",
        ("hist-season-2011",),
        "season_table",
    ),
    ("ฤดูกาลที่แล้วใครได้แชมป์พรีเมียร์ลีก", ("hist-season-2025",), "season_table"),
    ("พรีเมียร์ลีกฤดูกาล 1995/96 แชมป์คือทีมไหน", ("hist-season-1995",), "season_table"),
    (
        "ฤดูกาล 2003/04 ทีมไหนได้แชมป์แบบไม่แพ้ใคร",
        ("hist-season-2003", "hist-team-2003-arsenal"),
        "season_table",
    ),
    (
        "อาร์เซนอลจบอันดับเท่าไหร่ในฤดูกาล 2015/16",
        ("hist-team-2015-arsenal", "hist-season-2015"),
        "team_season",
    ),
    (
        "แมนยูฤดูกาล 2012/13 ได้กี่แต้ม",
        ("hist-team-2012-manchester-united", "hist-season-2012"),
        "team_season",
    ),
    (
        "ลิเวอร์พูลฤดูกาล 2019/20 ชนะกี่นัด",
        ("hist-team-2019-liverpool", "hist-season-2019"),
        "team_season",
    ),
    ("เชลซีฤดูกาล 2016/17 แพ้กี่นัด", ("hist-team-2016-chelsea", "hist-season-2016"), "team_season"),
    (
        "เลสเตอร์ซิตี้ฤดูกาล 2015/16 ได้กี่แต้ม",
        ("hist-team-2015-leicester-city", "hist-season-2015"),
        "team_season no team_id",
    ),
    (
        "แบล็คเบิร์น โรเวอร์ส ฤดูกาล 1994/95 จบอันดับเท่าไหร่",
        ("hist-team-1994-blackburn-rovers", "hist-season-1994"),
        "team_season no team_id",
    ),
    (
        "เวสต์แฮมฤดูกาล 2015/16 จบอันดับที่เท่าไหร่",
        ("hist-team-2015-west-ham", "hist-season-2015"),
        "team_season no team_id",
    ),
    (
        "อาร์เซนอลกับเชลซี สถิติพบกันในพรีเมียร์ลีกเป็นยังไง",
        ("hist-h2h-arsenal-chelsea",),
        "head_to_head",
    ),
    (
        "แมนยูเคยชนะลิเวอร์พูลกี่นัดในพรีเมียร์ลีก",
        ("hist-h2h-liverpool-manchester-united",),
        "head_to_head",
    ),
    ("ลิเวอร์พูลกับเอฟเวอร์ตันเจอกันกี่ครั้ง", ("hist-h2h-everton-liverpool",), "head_to_head"),
    ("สเปอร์สเคยชนะอาร์เซนอลกี่นัด", ("hist-h2h-arsenal-tottenham",), "head_to_head"),
    (
        "แมนซิตี้กับแมนยู head to head ใครชนะมากกว่า",
        ("hist-h2h-manchester-city-manchester-united",),
        "head_to_head",
    ),
    (
        "นิวคาสเซิลกับซันเดอร์แลนด์ สถิติเจอกันในพรีเมียร์ลีก",
        ("hist-h2h-newcastle-sunderland",),
        "head_to_head",
    ),
    # v1.13: questions that need a count across seasons (club and league records).
    (
        "แมนยูได้แชมป์พรีเมียร์ลีกกี่สมัย",
        ("hist-club-manchester-united", "hist-records"),
        "club_record",
    ),
    (
        "สเปอร์สเคยได้แชมป์พรีเมียร์ลีกไหม",
        ("hist-club-tottenham", "hist-records"),
        "club_record",
    ),
    ("ทีมไหนได้แชมป์พรีเมียร์ลีกมากที่สุด", ("hist-records",), "league_records"),
    ("มีกี่ทีมที่เคยได้แชมป์พรีเมียร์ลีก", ("hist-records",), "league_records"),
    ("ทีมไหนอยู่พรีเมียร์ลีกครบทุกฤดูกาล", ("hist-records",), "league_records"),
    ("นิวคาสเซิลเคยตกชั้นจากพรีเมียร์ลีกกี่ครั้ง", ("hist-club-newcastle",), "club_record"),
    (
        "ลิเวอร์พูลเคยจบอันดับแย่ที่สุดในพรีเมียร์ลีกอันดับเท่าไหร่",
        ("hist-club-liverpool",),
        "club_record",
    ),
    ("ทีมไหนเก็บแต้มรวมในพรีเมียร์ลีกมากที่สุดตลอดกาล", ("hist-records",), "league_records"),
    # v1.14: English top-flight titles in all eras (First Division before 1992).
    (
        "ลิเวอร์พูลได้แชมป์ลีกสูงสุดของอังกฤษทั้งหมดกี่สมัยรวมยุคก่อนพรีเมียร์ลีก",
        ("hist-club-liverpool", "hist-records"),
        "club_record",
    ),
    ("ใครเป็นแชมป์ดิวิชั่น 1 อังกฤษฤดูกาล 1989/90", ("hist-records",), "league_records"),
    ("ทีมไหนได้แชมป์ลีกสูงสุดอังกฤษมากที่สุดทุกยุค", ("hist-records",), "league_records"),
    (
        "เชลซีเคยได้แชมป์ลีกสูงสุดก่อนยุคพรีเมียร์ลีกไหม",
        ("hist-club-chelsea", "hist-records"),
        "club_record",
    ),
)
ROUTER_SNIPPET = """
import json, sys
from pathlib import Path
from app.decisions import decide, normalize_thai
from app.teams import TeamDirectory
payload = json.loads(sys.stdin.read())
teams = TeamDirectory.from_file(Path("data/team_aliases.json"))
out = []
for text in payload["queries"]:
    d = decide(normalize_thai(text), payload["context"], [], teams)
    out.append(None if d is None else {"route": d.route, "intent": d.intent,
               "filters": d.filters, "rewritten_query": d.rewritten_query})
sys.stdout.write(json.dumps(out, ensure_ascii=False))
"""


def pick_trivia(documents: Sequence[Document], size: int, *, seed: int) -> list[Document]:
    """Trivia documents in proportion to each topic's share of the knowledge base."""
    by_topic: dict[str, list[Document]] = {}
    for document in documents:
        by_topic.setdefault(document.topic or "", []).append(document)
    shares = allocate(Counter({t: len(docs) for t, docs in by_topic.items()}), size)
    rng = random.Random(seed)  # noqa: S311 - a repeatable sample, not a secret
    chosen: list[Document] = []
    for topic in sorted(by_topic):
        chosen += rng.sample(sorted(by_topic[topic], key=lambda d: d.doc_id), shares[topic])
    return sorted(chosen, key=lambda d: d.doc_id)


def pick_matches(documents: Sequence[Document], size: int) -> list[tuple[Document, int]]:
    """Every live document once, then match reports again with the second angle."""
    ordered = sorted(documents, key=lambda d: d.doc_id)
    again = [d for d in ordered if d.category == "match_report"]
    return [*((d, 0) for d in ordered), *((d, 1) for d in again)][:size]


def pick_groups(
    live: Sequence[Document], trivia: Sequence[Document], size: int, *, seed: int
) -> list[tuple[Document, Document]]:
    """Pairs of match reports that share a team, then pairs of Premier League trivia."""
    reports = sorted((d for d in live if d.category == "match_report"), key=lambda d: d.doc_id)
    pairs = [
        (a, b) for a, b in itertools.combinations(reports, 2) if set(a.team_ids) & set(b.team_ids)
    ]
    groups = pairs[:LIVE_PAIRS]
    league = sorted(
        (d for d in trivia if d.topic == "English Premier League"), key=lambda d: d.doc_id
    )
    rng = random.Random(seed)  # noqa: S311 - a repeatable sample, not a secret
    picked = rng.sample(league, 2 * (size - len(groups)))
    groups += [(picked[i], picked[i + 1]) for i in range(0, len(picked), 2)]
    return groups


def question_prompt(kind: str, documents: Sequence[Document], *, angle: int = 0) -> str:
    parts = [QUESTION_RULES, KIND_RULES[kind]]
    if kind == "match_th":
        parts.append(ANGLES[angle % len(ANGLES)])
    for number, document in enumerate(documents, start=1):
        text = document.text[:DOC_CHARS]
        parts.append(f"<document {number}>\n{document.title}\n{text}\n</document {number}>")
    return "\n\n".join(parts)


def parse_question(reply: str) -> str:
    try:
        question = json.loads(reply).get("question")
    except (json.JSONDecodeError, AttributeError) as exc:
        raise ValueError("reply is not a JSON object") from exc
    if not isinstance(question, str) or not question.strip():
        raise ValueError("reply has no question")
    return question.strip()


def _item(kind: str, number: int, question: str, documents: Sequence[Document]) -> dict[str, Any]:
    return {
        "id": f"th-{kind.removesuffix('_th')}-{number:03d}",
        "kind": kind,
        "query_th": question,
        "expected_doc_ids": [d.doc_id for d in documents],
        "need_all": kind == "multi_doc",
        "answerable": bool(documents),
        "routed": None,
        "note": " | ".join(d.title for d in documents),
    }


def historical_items() -> list[dict[str, Any]]:
    return [
        {
            "id": f"th-hist-{number:03d}",
            "kind": "historical_th",
            "query_th": question,
            "expected_doc_ids": list(doc_ids),
            "need_all": False,
            "answerable": True,
            "note": note,
        }
        for number, (question, doc_ids, note) in enumerate(HISTORICAL_TH, 1)
    ]


def draft_items(
    trivia: Sequence[Document],
    live: Sequence[Document],
    ask: Callable[[str], str],
    *,
    seed: int = SEED,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for n, document in enumerate(pick_trivia(trivia, SIZES["trivia_th"], seed=seed), start=1):
        question = parse_question(ask(question_prompt("trivia_th", [document])))
        items.append(_item("trivia_th", n, question, [document]))
    for n, (document, angle) in enumerate(pick_matches(live, SIZES["match_th"]), start=1):
        question = parse_question(ask(question_prompt("match_th", [document], angle=angle)))
        items.append(_item("match_th", n, question, [document]))
    groups = pick_groups(live, trivia, SIZES["multi_doc"], seed=seed)
    for n, group in enumerate(groups, start=1):
        question = parse_question(ask(question_prompt("multi_doc", group)))
        items.append(_item("multi_doc", n, question, group))
    for n, (question, kind) in enumerate(OUT_OF_KB_TH, start=1):
        item = _item("out_of_kb_th", n, question, [])
        item["note"] = kind
        items.append(item)
    return items


def routed_batch(queries: Sequence[str]) -> list[dict[str, Any] | None]:
    """The router's rules-layer decision for each question, run inside 03's own code."""
    payload = json.dumps({"queries": list(queries), "context": ROUTER_CONTEXT}, ensure_ascii=False)
    result = subprocess.run(  # noqa: S603 - our own interpreter and a fixed script
        [sys.executable, "-c", ROUTER_SNIPPET],
        cwd=ROUTER_DIR,
        input=payload,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        check=True,
    )
    return json.loads(result.stdout)


def routed_field(query_th: str, decision: dict[str, Any] | None) -> dict[str, Any]:
    if decision is None:  # the rules cannot decide; the classifier/LLM would
        return {
            "query": query_th,
            "query_original": query_th,
            "filters": {},
            "route": None,
            "intent": None,
        }
    return {
        "query": decision["rewritten_query"] or query_th,
        "query_original": query_th,
        "filters": decision["filters"],
        "route": decision["route"],
        "intent": decision["intent"],
    }


def refresh_routed(items: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    decisions = routed_batch([item["query_th"] for item in items])
    return [
        {**item, "routed": routed_field(item["query_th"], decision)}
        for item, decision in zip(items, decisions, strict=True)
    ]


def _write(path: Path, items: Sequence[dict[str, Any]]) -> None:
    lines = "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in items)
    path.write_text(lines, encoding="utf-8")


def _groq() -> Callable[[str], str]:
    from openai import OpenAI  # dev-only: the draft step, never the service or CI

    # The free tier allows 8k tokens a minute; the client waits out each 429 and retries.
    client = OpenAI(api_key=os.environ["GROQ_API_KEY"], base_url=GROQ_URL, max_retries=20)
    model = os.environ["GROQ_MODEL"]

    def ask(prompt: str) -> str:
        reply = client.chat.completions.create(
            model=model,
            temperature=0.7,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
        )
        return reply.choices[0].message.content or ""

    return ask


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=("draft", "refresh-routed", "historical"))
    args = parser.parse_args()
    if args.command == "draft":
        trivia, _ = load_trivia_documents(get_settings().trivia_file)
        items = refresh_routed(draft_items(trivia, load_live_documents(EVAL_DIR), _groq()))
        _write(DRAFT_FILE, items)
        print(f"{len(items)} items -> {DRAFT_FILE}")
        print(f"review every item, then save {GOLDEN_FILE.name}")
    elif args.command == "refresh-routed":
        items = refresh_routed(_jsonl(GOLDEN_FILE))
        _write(GOLDEN_FILE, items)
        print(f"routed refreshed for {len(items)} items -> {GOLDEN_FILE}")
    else:
        kept = [item for item in _jsonl(GOLDEN_FILE) if item["kind"] != "historical_th"]
        items = refresh_routed([*kept, *historical_items()])
        _write(GOLDEN_FILE, items)
        print(
            f"{len(historical_items())} historical questions, {len(items)} items -> {GOLDEN_FILE}"
        )


if __name__ == "__main__":
    main()
