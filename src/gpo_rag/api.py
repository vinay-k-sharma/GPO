"""FastAPI service: chat UI at /, POST /ask, POST /ingest, GET /health, GET /files/<doc>.pdf (SPEC-001 §4.6)."""

import os
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from gpo_rag.config import get_settings
from gpo_rag.generate import GenerationError
from gpo_rag.index import load_index
from gpo_rag.models import Answer
from gpo_rag.pipeline import ask

app = FastAPI(title="GPO Annual Report RAG", version="0.1.0")

WEB_DIR = Path(__file__).parent / "web"


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=2000)
    top_k: int | None = Field(default=None, ge=1, le=20)
    mode: Literal["dense", "bm25", "hybrid"] | None = None
    fiscal_years: list[int] | None = None


@app.get("/health")
def health() -> dict:
    s = get_settings()
    try:
        manifest = load_index().manifest
    except FileNotFoundError:
        manifest = None
    if s.llm_provider == "gemini":
        credentials = bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"))
    else:
        credentials = bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")
                           or (Path.home() / ".config" / "anthropic").exists())
    return {"status": "ok" if manifest else "no_index", "index": manifest,
            "llm_provider": s.llm_provider,
            "llm_model": s.gemini_model if s.llm_provider == "gemini" else s.llm_model, "embed_model": s.embed_model, "credentials": credentials}


@app.get("/", include_in_schema=False)
def chat_ui() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


@app.get("/files/{doc_id}.pdf", include_in_schema=False)
def report_pdf(doc_id: str) -> FileResponse:
    s = get_settings()
    if doc_id not in s.documents:  # only the configured reports are served
        raise HTTPException(404, "Unknown document")
    return FileResponse(s.raw_dir / f"{doc_id}.pdf", media_type="application/pdf",
                        headers={"Content-Disposition": f'inline; filename="{doc_id}.pdf"'})


@app.post("/ask", response_model=Answer)
def ask_endpoint(req: AskRequest) -> Answer:
    try:
        return ask(req.question, top_n=req.top_k, mode=req.mode, fiscal_years=req.fiscal_years)
    except FileNotFoundError as e:
        raise HTTPException(503, str(e))
    except GenerationError as e:
        raise HTTPException(502, str(e))


@app.post("/ingest")
def ingest_endpoint(rebuild: bool = False) -> dict:
    from gpo_rag.ingest.pipeline import run_ingest

    return run_ingest(rebuild=rebuild)
