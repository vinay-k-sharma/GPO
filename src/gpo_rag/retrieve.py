"""Dense + BM25 retrieval fused with Reciprocal Rank Fusion (SPEC-001 §4.4)."""

import re
from typing import Literal

import numpy as np

from gpo_rag.config import get_settings
from gpo_rag.embeddings import embed_query
from gpo_rag.index import Index, bm25_tokenize, load_index
from gpo_rag.models import RetrievedChunk

Mode = Literal["dense", "bm25", "hybrid"]

_YEAR = re.compile(r"\b(?:FY\s?)?(20\d{2})\b", re.I)


def detect_years(question: str, available: set[int]) -> list[int]:
    """Fiscal years named in the question that exist in the corpus (e.g. 'FY 2025', '2024')."""
    return sorted({int(y) for y in _YEAR.findall(question)} & available)


def rrf_fuse(rankings: list[list[int]], k: int = 60) -> dict[int, float]:
    scores: dict[int, float] = {}
    for ranking in rankings:
        for rank, idx in enumerate(ranking):
            scores[idx] = scores.get(idx, 0.0) + 1.0 / (k + rank + 1)
    return scores


def _ranked(scores: np.ndarray, mask: np.ndarray, k: int) -> list[int]:
    idx = np.flatnonzero(mask)
    order = idx[np.argsort(-scores[idx], kind="stable")]
    return order[:k].tolist()


def _search(index: Index, question: str, mask: np.ndarray, mode: Mode, top_n: int) -> list[RetrievedChunk]:
    s = get_settings()
    dense: list[int] = []
    sparse: list[int] = []
    if mode in ("dense", "hybrid"):
        dense = _ranked(index.vectors @ embed_query(question), mask, s.candidate_k)
    if mode in ("bm25", "hybrid"):
        bm = index.bm25.get_scores(bm25_tokenize(question))
        sparse = [i for i in _ranked(bm, mask, s.candidate_k) if bm[i] > 0]

    fused = rrf_fuse([r for r in (dense, sparse) if r], k=s.rrf_k)
    best = sorted(fused, key=lambda i: -fused[i])[:top_n]
    return [
        RetrievedChunk(
            chunk=index.chunks[i],
            rank=r + 1,
            rrf_score=round(fused[i], 6),
            dense_rank=dense.index(i) + 1 if i in dense else None,
            bm25_rank=sparse.index(i) + 1 if i in sparse else None,
        )
        for r, i in enumerate(best)
    ]


def retrieve(
    question: str,
    top_n: int | None = None,
    mode: Mode | None = None,
    fiscal_years: list[int] | None = None,
) -> list[RetrievedChunk]:
    """Return the top_n chunks for a question.

    If fiscal_years is None and auto_year_filter is on, years named in the question restrict the search.
    When several years apply, each year gets an equal share of top_n so comparisons see both reports.
    """
    s = get_settings()
    index = load_index()
    top_n = top_n or s.top_n
    mode = mode or s.retrieval_mode
    if fiscal_years is None and s.auto_year_filter:
        fiscal_years = detect_years(question, set(index.years.tolist()))

    if not fiscal_years:
        return _search(index, question, np.ones(len(index.chunks), bool), mode, top_n)

    per_year = max(1, top_n // len(fiscal_years))
    results: list[RetrievedChunk] = []
    for year in fiscal_years:
        results += _search(index, question, index.years == year, mode, per_year)
    results.sort(key=lambda r: -r.rrf_score)
    for r, item in enumerate(results):
        item.rank = r + 1
    return results
