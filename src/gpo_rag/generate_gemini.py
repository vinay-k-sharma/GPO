"""Answer generation with Google Gemini (REST). Sources are numbered and cited with [n] markers,
which are validated and renumbered against the retrieved chunks."""

import logging
import os
import re
import time

import httpx

from gpo_rag.config import get_settings
from gpo_rag.models import Citation, RetrievedChunk
from gpo_rag.prompts import GEMINI_CITATION_RULES, NOT_FOUND, SYSTEM_PROMPT

log = logging.getLogger(__name__)

API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
MARKER_RE = re.compile(r"\[(\d+(?:\s*,\s*\d+)*)\]")
RETRYABLE = {429, 500, 502, 503, 504}


def build_prompt(question: str, retrieved: list[RetrievedChunk]) -> str:
    parts = []
    for i, r in enumerate(retrieved, 1):
        c = r.chunk
        parts.append(f"[{i}] FY{c.fiscal_year} Annual Report — {c.section} (p.{c.page_start})\n{c.text}")
    return "Search results:\n\n" + "\n\n".join(parts) + f"\n\nQuestion: {question}"


def parse_answer(text: str, retrieved: list[RetrievedChunk]) -> tuple[str, list[Citation]]:
    """Renumber the model's [n] source markers to 1..k in order of first use; drop invalid ones."""
    if text.strip().startswith(NOT_FOUND):
        return re.sub(r"\s*" + MARKER_RE.pattern, "", text).strip(), []
    citations: list[Citation] = []
    remap: dict[int, int] = {}

    def sub(m: re.Match) -> str:
        out = []
        for raw in m.group(1).split(","):
            idx = int(raw) - 1
            if not (0 <= idx < len(retrieved)):
                continue
            if idx not in remap:
                c = retrieved[idx].chunk
                remap[idx] = len(citations) + 1
                citations.append(Citation(doc_id=c.doc_id, fiscal_year=c.fiscal_year, page=c.page_start,
                                          section=c.section, quote=c.text.strip()[:500]))
            marker = f"[{remap[idx]}]"
            if marker not in out:
                out.append(marker)
        return "".join(out)

    return MARKER_RE.sub(sub, text).strip(), citations


def _post(url: str, body: dict, key: str, retries: int) -> httpx.Response | None:
    """POST with short backoff on transient errors; None if every attempt timed out or failed to connect."""
    s = get_settings()
    resp = None
    for attempt in range(retries + 1):
        try:
            resp = httpx.post(url, json=body, headers={"x-goog-api-key": key}, timeout=s.gemini_timeout)
        except httpx.HTTPError:
            resp = None
        if resp is not None and resp.status_code not in RETRYABLE:
            return resp
        if attempt < retries:
            time.sleep(1 + attempt)
    return resp


def generate_gemini(question: str, retrieved: list[RetrievedChunk]) -> dict:
    from gpo_rag.generate import GenerationError

    s = get_settings()
    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not key:
        raise GenerationError("No Gemini credentials found — set GEMINI_API_KEY in .env.")

    body = {
        "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT + GEMINI_CITATION_RULES}]},
        "contents": [{"role": "user", "parts": [{"text": build_prompt(question, retrieved)}]}],
        "generationConfig": {"maxOutputTokens": s.max_tokens, "temperature": 0.2},
    }
    resp = None
    for model in [s.gemini_model, *s.gemini_fallback_models]:
        resp = _post(API_URL.format(model=model), body, key, retries=1)
        if resp is not None and resp.status_code not in RETRYABLE:
            break
        log.warning("Gemini model %s unavailable (%s); trying next", model,
                    resp.status_code if resp is not None else "timeout")
    if resp is None:
        raise GenerationError("Could not reach the Gemini API — check the network connection.")
    if resp.status_code in (401, 403):
        raise GenerationError("Gemini authentication failed — check GEMINI_API_KEY.")
    if resp.status_code != 200:
        msg = resp.json().get("error", {}).get("message", resp.text[:300]) if resp.content else ""
        raise GenerationError(f"Gemini API error {resp.status_code}: {msg}")

    data = resp.json()
    usage = data.get("usageMetadata", {})
    usage_out = {"input_tokens": usage.get("promptTokenCount", 0),
                 "output_tokens": usage.get("candidatesTokenCount", 0) + usage.get("thoughtsTokenCount", 0)}
    model = data.get("modelVersion", s.gemini_model)
    candidates = data.get("candidates") or []
    if not candidates:
        reason = data.get("promptFeedback", {}).get("blockReason", "unknown")
        log.warning("Gemini blocked the prompt (reason=%s)", reason)
        return {"answer": "The model declined to answer this question.", "citations": [],
                "stop_reason": "refusal", "model": model, "usage": usage_out}

    cand = candidates[0]
    finish = cand.get("finishReason", "STOP")
    text = "".join(p.get("text", "") for p in cand.get("content", {}).get("parts", []) if not p.get("thought"))
    if finish in ("SAFETY", "PROHIBITED_CONTENT", "BLOCKLIST", "RECITATION") and not text:
        return {"answer": "The model declined to answer this question.", "citations": [],
                "stop_reason": "refusal", "model": model, "usage": usage_out}
    if finish == "MAX_TOKENS":
        log.warning("Gemini answer truncated at max_tokens=%d", s.max_tokens)

    answer, citations = parse_answer(text, retrieved)
    return {"answer": answer, "citations": citations,
            "stop_reason": {"STOP": "end_turn", "MAX_TOKENS": "max_tokens"}.get(finish, finish.lower()),
            "model": model, "usage": usage_out}
