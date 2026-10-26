"""Online path: question -> retrieve -> generate -> Answer."""

import time

from gpo_rag.generate import generate
from gpo_rag.models import Answer
from gpo_rag.retrieve import Mode, retrieve


def ask(question: str, top_n: int | None = None, mode: Mode | None = None,
        fiscal_years: list[int] | None = None) -> Answer:
    t0 = time.perf_counter()
    retrieved = retrieve(question, top_n=top_n, mode=mode, fiscal_years=fiscal_years)
    out = generate(question, retrieved)
    return Answer(
        question=question,
        retrieved=retrieved,
        latency_ms=int((time.perf_counter() - t0) * 1000),
        **out,
    )
