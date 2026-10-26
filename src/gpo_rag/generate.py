"""Answer generation with Claude using search_result blocks + native citations (SPEC-001 §4.5)."""

import logging
from functools import lru_cache

import anthropic

from gpo_rag.config import get_settings
from gpo_rag.models import Citation, RetrievedChunk
from gpo_rag.prompts import NOT_FOUND, SYSTEM_PROMPT

log = logging.getLogger(__name__)

FALLBACK_BETA = "server-side-fallback-2026-07-01"


class GenerationError(RuntimeError):
    pass


@lru_cache
def get_client() -> anthropic.Anthropic:
    return anthropic.Anthropic(max_retries=get_settings().max_retries)


def search_result_block(item: RetrievedChunk) -> dict:
    c = item.chunk
    return {
        "type": "search_result",
        "source": f"{c.doc_id}.pdf#page={c.page_start}",
        "title": f"FY{c.fiscal_year} Annual Report — {c.section} (p.{c.page_start})",
        "content": [{"type": "text", "text": c.text}],
        "citations": {"enabled": True},
    }


def build_messages(question: str, retrieved: list[RetrievedChunk]) -> list[dict]:
    content = [search_result_block(r) for r in retrieved]
    content.append({"type": "text", "text": question})
    return [{"role": "user", "content": content}]


def parse_response(response, retrieved: list[RetrievedChunk]) -> tuple[str, list[Citation]]:
    """Join text blocks, append [n] markers for cited spans, and map citations back to chunks."""
    parts: list[str] = []
    citations: list[Citation] = []
    keys: dict[tuple[str, int, str], int] = {}
    for block in response.content:
        if block.type != "text":
            continue  # thinking / fallback blocks
        parts.append(block.text)
        markers = []
        for cit in getattr(block, "citations", None) or []:
            idx = getattr(cit, "search_result_index", None)
            if idx is None or not (0 <= idx < len(retrieved)):
                continue
            chunk = retrieved[idx].chunk
            key = (chunk.doc_id, chunk.page_start, chunk.chunk_id)
            if key not in keys:
                keys[key] = len(citations) + 1
                citations.append(Citation(
                    doc_id=chunk.doc_id,
                    fiscal_year=chunk.fiscal_year,
                    page=chunk.page_start,
                    section=chunk.section,
                    quote=(cit.cited_text or "").strip()[:500],
                ))
            if f"[{keys[key]}]" not in markers:
                markers.append(f"[{keys[key]}]")
        if markers:
            parts.append("".join(markers))
    return "".join(parts).strip(), citations


def generate(question: str, retrieved: list[RetrievedChunk]) -> dict:
    s = get_settings()
    if not retrieved:
        return {"answer": NOT_FOUND, "citations": [], "stop_reason": "no_context", "model": None, "usage": {}}
    if s.llm_provider == "gemini":
        from gpo_rag.generate_gemini import generate_gemini
        return generate_gemini(question, retrieved)

    params = dict(
        model=s.llm_model,
        max_tokens=s.max_tokens,
        system=SYSTEM_PROMPT,
        messages=build_messages(question, retrieved),
        output_config={"effort": s.effort},
    )
    client = get_client()
    try:
        if s.use_refusal_fallback:
            response = client.beta.messages.create(**params, betas=[FALLBACK_BETA], fallbacks="default")
        else:
            response = client.messages.create(**params)
    except anthropic.AuthenticationError as e:
        raise GenerationError("Claude authentication failed — set ANTHROPIC_API_KEY or run `ant auth login`.") from e
    except TypeError as e:
        # The SDK resolves credentials lazily and raises TypeError when none are configured
        if "authentication" not in str(e).lower():
            raise
        raise GenerationError("No Claude credentials found — set ANTHROPIC_API_KEY in .env or run `ant auth login`.") from e
    except anthropic.RateLimitError as e:
        raise GenerationError(f"Rate limited by the Claude API after retries: {e.message}") from e
    except anthropic.APIStatusError as e:
        raise GenerationError(f"Claude API error {e.status_code}: {e.message} (request {e.request_id})") from e
    except anthropic.APIConnectionError as e:
        raise GenerationError("Could not reach the Claude API — check the network connection.") from e

    if response.stop_reason == "refusal":
        category = getattr(response.stop_details, "category", None) if response.stop_details else None
        log.warning("Request declined (category=%s, request=%s)", category, response._request_id)
        return {"answer": "The model declined to answer this question.", "citations": [],
                "stop_reason": "refusal", "model": response.model, "usage": response.usage.to_dict()}
    if response.stop_reason == "max_tokens":
        log.warning("Answer truncated at max_tokens=%d (request=%s)", s.max_tokens, response._request_id)

    answer, citations = parse_response(response, retrieved)
    return {
        "answer": answer,
        "citations": citations,
        "stop_reason": response.stop_reason,
        "model": response.model,
        "usage": response.usage.to_dict(),
    }
