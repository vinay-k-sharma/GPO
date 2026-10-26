"""Data records shared across the pipeline."""

from typing import Literal

from pydantic import BaseModel


class Element(BaseModel):
    """One structural block parsed from a PDF page."""

    doc_id: str
    fiscal_year: int
    page: int  # 1-based physical PDF page
    section_path: list[str]
    type: Literal["text", "table"]
    text: str


class Chunk(BaseModel):
    chunk_id: str
    doc_id: str
    fiscal_year: int
    page_start: int
    page_end: int
    section_path: list[str]
    chunk_type: Literal["text", "table"]
    text: str
    embed_text: str
    n_tokens: int

    @property
    def section(self) -> str:
        return " > ".join(self.section_path) or "(untitled section)"


class RetrievedChunk(BaseModel):
    chunk: Chunk
    rank: int
    rrf_score: float
    dense_rank: int | None = None
    bm25_rank: int | None = None


class Citation(BaseModel):
    doc_id: str
    fiscal_year: int
    page: int
    section: str
    quote: str


class Answer(BaseModel):
    question: str
    answer: str
    citations: list[Citation]
    retrieved: list[RetrievedChunk]
    stop_reason: str | None = None
    model: str | None = None
    usage: dict = {}
    latency_ms: int = 0
