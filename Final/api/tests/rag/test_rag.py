"""Chunking, the retrieval store and hybrid search (Design.md §5, §6), with a fake embedder."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Sequence
from pathlib import Path

import numpy as np
import pytest

from app.rag.chunking import load_chunks
from app.rag.embedder import prefixed
from app.rag.hybrid import rrf
from app.rag.index import RagIndex
from app.rag.tokenize import tokenize

REAL_DATA = Path(__file__).parents[3] / "data"
ROLE = """---
role_id: {role_id}
title_th: {title_th}
title_en: {title_en}
author: a
reviewer: b
status: draft
---

# {title_th} ({title_en})

## Role description

{description}

## Learning path

{learning}

## Sources

- https://example.com/{role_id}
- https://example.com/shared
"""


class FakeEmbedder:
    """Words hashed into a small vector: the same words give close vectors."""

    dimension = 64

    def __init__(self, model_name: str = "fake-model") -> None:
        self.model_name = model_name
        self.embedded: list[str] = []

    def _encode(self, text: str) -> np.ndarray:
        vector = np.zeros(self.dimension, dtype=np.float32)
        for token in tokenize(text):
            vector[hashlib.sha256(token.encode()).digest()[0] % self.dimension] += 1.0
        norm = float(np.linalg.norm(vector))
        return vector / norm if norm else vector

    def encode_passages(self, texts: Sequence[str]) -> np.ndarray:
        self.embedded.extend(texts)
        return np.array([self._encode(t) for t in texts], dtype=np.float32).reshape(
            len(texts), self.dimension
        )

    def encode_query(self, text: str) -> np.ndarray:
        return self._encode(text)


def write_role(
    data: Path,
    role_id: str,
    description: str = "งานทั่วไป",
    learning: str = "เรียนพื้นฐาน",
) -> None:
    folder = data / "roles"
    folder.mkdir(parents=True, exist_ok=True)
    text = ROLE.format(
        role_id=role_id,
        title_th=f"ไทย-{role_id}",
        title_en=role_id.title(),
        description=description,
        learning=learning,
    )
    (folder / f"{role_id}.md").write_text(text, encoding="utf-8")


@pytest.fixture
def data(tmp_path: Path) -> Path:
    folder = tmp_path / "data"
    write_role(folder, "network", "ดูแล firewall และ router ขององค์กร", "เรียน CCNA")
    write_role(folder, "frontend", "เขียน React ให้หน้าเว็บ", "เรียน JavaScript และ CSS")
    write_role(folder, "database", "สำรองข้อมูล backup ให้ฐานข้อมูล", "เรียน SQL")
    return folder


def make_index(data: Path, embedder: FakeEmbedder | None = None) -> RagIndex:
    return RagIndex(
        data_dir=str(data), db_path=str(data.parent / "rag.db"), embedder=embedder or FakeEmbedder()
    )


# --- chunking


def test_a_role_gives_one_chunk_per_indexed_section(data: Path) -> None:
    chunks = {c.chunk_id: c for c in load_chunks(str(data)) if c.role_id == "network"}
    assert set(chunks) == {"role-network#role_description", "role-network#learning_path"}
    chunk = chunks["role-network#learning_path"]
    assert (chunk.doc_id, chunk.category) == ("role-network", "learning_path")
    assert chunk.sources == ("https://example.com/network", "https://example.com/shared")


def test_chunk_text_leads_with_the_role_and_leaves_out_the_rest(data: Path) -> None:
    chunk = next(c for c in load_chunks(str(data)) if c.chunk_id == "role-network#role_description")
    assert chunk.title == "ไทย-network (Network)"
    assert chunk.text.startswith("ไทย-network (Network)\n")
    assert "firewall" in chunk.text
    assert "CCNA" not in chunk.text  # the next section
    assert "reviewer" not in chunk.text  # front matter
    assert "example.com" not in chunk.text  # sources are metadata


def test_a_role_without_a_required_section_is_an_error(data: Path) -> None:
    (data / "roles" / "broken.md").write_text(
        "---\nrole_id: broken\ntitle_th: x\ntitle_en: y\n---\n\n## Role description\n\ntext\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="broken"):
        load_chunks(str(data))


def test_notes_are_chunked_by_heading_with_their_category(data: Path) -> None:
    (data / "rag").mkdir()
    (data / "rag" / "work_style.md").write_text(
        "# สไตล์การทำงาน\n\n## ทำงานเป็นทีม\n\nคุยกันบ่อย\n\n## ทำงานคนเดียว\n\nมีสมาธิ\n\n"
        "## Sources\n\n- https://example.com/ws\n",
        encoding="utf-8",
    )
    (data / "rag" / "soft_skills.md").write_text(
        "# ทักษะด้านบุคคล\n\n## การสื่อสาร\n\nอธิบายงาน\n", encoding="utf-8"
    )
    chunks = {c.chunk_id: c for c in load_chunks(str(data)) if c.role_id is None}
    assert set(chunks) == {"work_style#0", "work_style#1", "soft_skills#0"}
    assert chunks["work_style#1"].category == "work_style"
    assert chunks["work_style#1"].title == "สไตล์การทำงาน"
    assert chunks["work_style#1"].sources == ("https://example.com/ws",)
    assert "มีสมาธิ" in chunks["work_style#1"].text
    assert "คุยกันบ่อย" not in chunks["work_style#1"].text
    assert chunks["soft_skills#0"].category == "soft_skill"


def test_missing_notes_are_fine_until_they_are_written(data: Path) -> None:
    assert len(load_chunks(str(data))) == 6


def test_the_real_role_files_load() -> None:
    chunks = load_chunks(str(REAL_DATA))
    roles = [c for c in chunks if c.role_id is not None]
    assert len(roles) == 52  # 26 roles, 2 sections each
    assert all(c.sources for c in roles)
    assert len({c.chunk_id for c in chunks}) == len(chunks)


# --- tokens and fusion


def test_the_real_notes_cover_every_trait_and_every_soft_skill() -> None:
    chunks = load_chunks("../data")
    work_style = [c for c in chunks if c.category == "work_style"]
    soft = [c for c in chunks if c.category == "soft_skill"]
    for trait in ("teamwork", "structure", "ambiguity", "pressure", "innovation", "leadership"):
        assert sum(f"({trait})" in c.text for c in work_style) == 1, trait
    skills = json.loads(Path("../data/skills.json").read_text(encoding="utf-8"))
    names = [s["name_th"] for s in skills if s["type"] == "soft"]
    for name in names:
        assert sum(f"\n{name} (" in c.text for c in soft) == 1, name
    assert len(soft) == len(names)
    assert all(c.sources for c in work_style + soft)


def test_thai_is_split_into_words_and_latin_is_lower_cased() -> None:
    tokens = tokenize("ฐานข้อมูลของ PostgreSQL")
    assert "postgresql" in tokens
    assert len(tokens) > 2
    assert "ฐานข้อมูลของ" not in tokens


def test_tokens_are_found_next_to_thai_without_a_space() -> None:
    assert "react" in tokenize("เรียนReactก่อน")


def test_rrf_adds_one_over_k_plus_rank_for_each_list() -> None:
    assert rrf([[1, 2], [2, 3]], k=60) == [
        (2, pytest.approx(1 / 62 + 1 / 61)),
        (1, pytest.approx(1 / 61)),
        (3, pytest.approx(1 / 62)),
    ]


def test_rrf_breaks_ties_by_position() -> None:
    assert [position for position, _ in rrf([[5], [4]], k=60)] == [4, 5]


# --- e5 prefixes


def test_e5_models_get_their_prefixes() -> None:
    model = "intfloat/multilingual-e5-base"
    assert prefixed(model, ["ก"], "query") == ["query: ก"]
    assert prefixed(model, ["ก"], "passage") == ["passage: ก"]


def test_other_models_get_no_prefix() -> None:
    assert prefixed("BAAI/bge-m3", ["ก"], "query") == ["ก"]


# --- search


def test_search_finds_the_matching_chunk(data: Path) -> None:
    index = make_index(data)
    index.build()
    hits = index.search("firewall", top_k=1)
    assert [hit.chunk.chunk_id for hit in hits] == ["role-network#role_description"]
    assert hits[0].score == pytest.approx(2 / 61)  # first in both lists
    assert hits[0].bm25_score is not None
    assert hits[0].vector_score is not None


def test_top_k_limits_the_results(data: Path) -> None:
    index = make_index(data)
    index.build()
    assert len(index.search("เรียน", top_k=2)) == 2


def test_filters_keep_other_chunks_out_of_the_top_k(data: Path) -> None:
    index = make_index(data)
    index.build()
    hits = index.search("firewall", top_k=3, role_id="frontend")
    assert {hit.chunk.role_id for hit in hits} == {"frontend"}
    assert len(hits) == 2
    hits = index.search("firewall", top_k=3, category="learning_path")
    assert {hit.chunk.category for hit in hits} == {"learning_path"}
    hits = index.search("firewall", top_k=3, role_id="network", category="learning_path")
    assert [hit.chunk.chunk_id for hit in hits] == ["role-network#learning_path"]


def test_a_filter_nothing_passes_finds_nothing(data: Path) -> None:
    index = make_index(data)
    index.build()
    assert index.search("firewall", role_id="no-such-role") == []


@pytest.mark.parametrize("mode", ["bm25", "vector"])
def test_single_modes_use_one_method(data: Path, mode: str) -> None:
    index = make_index(data)
    index.build()
    [hit] = index.search("firewall", top_k=1, mode=mode)  # type: ignore[arg-type]
    assert (hit.bm25_score is None) == (mode == "vector")
    assert (hit.vector_score is None) == (mode == "bm25")


def test_a_blank_query_finds_nothing(data: Path) -> None:
    embedder = FakeEmbedder()
    index = make_index(data, embedder)
    index.build()
    assert index.search("   ") == []


def test_words_no_chunk_has_are_not_a_bm25_hit(data: Path) -> None:
    index = make_index(data)
    index.build()
    assert index.search("kubernetes", mode="bm25") == []


def test_searching_before_a_build_is_an_error(data: Path) -> None:
    with pytest.raises(RuntimeError):
        make_index(data).search("firewall")


# --- rebuilds


def test_an_unchanged_chunk_is_not_embedded_again(data: Path) -> None:
    make_index(data).build()
    again = FakeEmbedder()
    index = make_index(data, again)
    index.build()
    assert again.embedded == []
    assert index.search("firewall", top_k=1)[0].chunk.role_id == "network"


def test_only_the_changed_chunk_is_embedded_again(data: Path) -> None:
    make_index(data).build()
    write_role(data, "network", "ดูแล switch ขององค์กร", "เรียน CCNA")
    again = FakeEmbedder()
    index = make_index(data, again)
    index.build()
    assert len(again.embedded) == 1
    assert "switch" in again.embedded[0]
    assert index.search("switch", top_k=1, mode="bm25")[0].chunk.role_id == "network"
    assert index.search("firewall", mode="bm25") == []


def test_a_deleted_role_leaves_the_store_and_the_index(data: Path) -> None:
    index = make_index(data)
    index.build()
    (data / "roles" / "network.md").unlink()
    index.build()
    assert index.search("firewall", mode="bm25") == []
    with sqlite3.connect(data.parent / "rag.db") as db:
        assert db.execute("SELECT count(*) FROM chunks WHERE role_id = 'network'").fetchone() == (
            0,
        )


def test_another_model_embeds_everything_again(data: Path) -> None:
    make_index(data).build()
    other = FakeEmbedder("other-model")
    make_index(data, other).build()
    assert len(other.embedded) == 6


def test_a_failed_rebuild_keeps_the_old_index_and_store(data: Path) -> None:
    class Failing(FakeEmbedder):
        fail = False

        def encode_passages(self, texts: Sequence[str]) -> np.ndarray:
            if self.fail:
                raise OSError("model gone")
            return super().encode_passages(texts)

    embedder = Failing()
    index = make_index(data, embedder)
    index.build()
    write_role(data, "network", "ดูแล switch", "เรียน CCNA")
    embedder.fail = True
    with pytest.raises(OSError):
        index.build()
    assert index.search("firewall", top_k=1, mode="bm25")[0].chunk.role_id == "network"
    fresh = FakeEmbedder()
    make_index(data, fresh).build()
    assert len(fresh.embedded) == 1  # the store still held the old vectors
