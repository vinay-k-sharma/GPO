"""LLM judge for answer correctness and faithfulness (SPEC-001 §6.2).

Runs as a separate call from answering: citations and structured outputs cannot be combined.
"""

from typing import Literal

from pydantic import BaseModel, Field

from gpo_rag.config import get_settings
from gpo_rag.generate import get_client
from gpo_rag.models import Answer


class Verdict(BaseModel):
    correctness: Literal["correct", "partially_correct", "incorrect"]
    score: int = Field(description="1-5: 5 = fully matches the reference, 1 = wrong or missing")
    faithful: bool = Field(description="Every factual claim in the answer is supported by the context")
    unsupported_claims: list[str] = Field(description="Claims not supported by the context; empty if none")
    reasoning: str


JUDGE_SYSTEM = """You grade answers from a question-answering system over GPO annual reports.

You receive a question, a reference answer written from the report, the system's answer, and the context excerpts the system was given.

correctness: compare the answer with the reference.
- "correct": it states the key facts and figures in the reference. Extra correct detail is fine; different wording or rounding of the same figure is fine.
- "partially_correct": some key facts are right and others are missing or wrong. For summary questions, about half of the reference points are covered.
- "incorrect": the main fact or figure is wrong or missing, or the system declined to answer even though the reference has an answer.
score: 1-5, consistent with correctness.
faithful: true only if every factual claim in the answer is supported by the context excerpts. Judge this against the context, not against the reference."""


def judge(answer: Answer, expected: str) -> Verdict:
    s = get_settings()
    context = "\n\n".join(
        f"[{i + 1}] FY{r.chunk.fiscal_year} p.{r.chunk.page_start} — {r.chunk.section}\n{r.chunk.text}"
        for i, r in enumerate(answer.retrieved)
    )
    prompt = (
        f"<question>\n{answer.question}\n</question>\n\n"
        f"<reference_answer>\n{expected}\n</reference_answer>\n\n"
        f"<system_answer>\n{answer.answer}\n</system_answer>\n\n"
        f"<context>\n{context}\n</context>"
    )
    response = get_client().messages.parse(
        model=s.judge_model,
        max_tokens=4096,
        system=JUDGE_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
        output_config={"effort": "low"},
        output_format=Verdict,
    )
    if response.parsed_output is None:
        raise RuntimeError(f"Judge returned no verdict (stop_reason={response.stop_reason})")
    return response.parsed_output
