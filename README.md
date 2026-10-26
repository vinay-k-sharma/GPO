# GPO Annual Report — Baseline RAG

A question-answering bot over the U.S. Government Publishing Office **FY2024 and FY2025 Annual Reports**. Every answer cites its source page. The design is in [`specs/SPEC-001-baseline-rag.md`](specs/SPEC-001-baseline-rag.md).

```
PDF ─► pymupdf4llm (layout, Markdown tables) ─► clean ─► structure-aware chunks
    ─► bge-base-en-v1.5 (local ONNX) + BM25 ─► RRF hybrid retrieval (auto fiscal-year filter)
    ─► Claude Opus 5.5 with search_result blocks ─► answer + page citations
```

## Setup

The project needs Python 3.12 and [uv](https://docs.astral.sh/uv/).

```bash
uv sync --group dev
cp .env.example .env        # then set ANTHROPIC_API_KEY (or run `ant auth login`)
                            # or GPO_RAG_LLM_PROVIDER=gemini + GEMINI_API_KEY
```

The PDFs are already in `data/raw/`. The first ingest downloads the embedding model (~210 MB, cached in `.cache/fastembed`).

## Chat UI

```bash
uv run gpo-rag serve        # then open http://127.0.0.1:8000
```

The chat page is served by the same FastAPI app. It has no build step and no frontend dependencies.

- **Answers with numbered citation markers.** Click a marker to jump to its source card. Each card shows the fiscal year, page, section and the quoted text, and has an **Open page ↗** link to the PDF page.
- **Retrieved context** is shown in a collapsible panel, to check what the model saw.
- **Search scope** can be Auto (uses the years named in the question), Both years, FY2025 or FY2024.
- **Other features:** example questions, copy answer with its sources, chat history kept in the browser, light and dark theme, and a mobile layout.
- **Each question is answered independently.** There is no conversational memory yet.

Restart the server after adding `ANTHROPIC_API_KEY` (or `GEMINI_API_KEY` with `GPO_RAG_LLM_PROVIDER=gemini`) to `.env`.

**Gemini provider:** sources are numbered in the prompt and the model cites them as `[n]`; markers are validated and renumbered against the retrieved chunks (`generate_gemini.py`). Default model `gemini-3.5-flash`, falling back to `gemini-3.1-flash-lite` on 429/5xx/timeouts. The eval judge still uses Claude.

## Usage

```bash
uv run gpo-rag ingest                    # parse → chunk → embed → index (skips if up to date; --rebuild to force)
uv run gpo-rag ask "What was GPO's net income in FY 2025?"
uv run gpo-rag ask "..." --show-context  # also list retrieved chunks
uv run gpo-rag ask "..." --retrieval-only  # no Claude call; inspect retrieval
uv run gpo-rag serve                     # FastAPI on http://127.0.0.1:8000  (docs at /docs)
```

API:

```bash
curl -s localhost:8000/ask -H 'content-type: application/json' \
  -d '{"question": "How many passports did GPO produce in FY 2025?"}'
```

`POST /ask` accepts `{question, top_k?, mode?: dense|bm25|hybrid, fiscal_years?: [2024, 2025]}`. It returns `{answer, citations[{doc_id, fiscal_year, page, section, quote}], retrieved[...], usage, latency_ms}`.

## Evaluation

The eval set is `data/eval/sample_questions.jsonl`: 45 questions with reference answers, gold pages and evidence quotes, covering the categories numeric, factual, narrative, table, cross-year and unanswerable.

```bash
uv run gpo-rag eval --retrieval-only     # Hit@k / MRR, no API calls
uv run gpo-rag ablate                    # retrieval grid: mode × top_n
uv run gpo-rag eval                      # full: answers + LLM judge (correctness, faithfulness, citations, refusals)
uv run gpo-rag eval --effort low --label low-effort
uv run gpo-rag eval --ids fy25-q01,cross-q02 --no-judge
```

Each run writes a JSON report and a Markdown report to `eval/reports/`.

## Tests

```bash
uv run pytest -q
```

## Configuration

All settings are in `src/gpo_rag/config.py`. You can override any of them with environment variables prefixed `GPO_RAG_`, e.g. `GPO_RAG_TOP_N=8` or `GPO_RAG_EFFORT=low`.

## Layout

```
src/gpo_rag/
  ingest/{pdf_parser,cleaner,pipeline}.py   PDF → elements → chunks → index
  chunking.py  embeddings.py  index.py       chunking, bge embeddings, NumPy + BM25 index
  retrieve.py                                dense / bm25 / hybrid (RRF), fiscal-year filter
  prompts.py  generate.py  pipeline.py       Claude call with citations; ask()
  evaluation/{run,judge}.py                  eval harness + LLM judge
  cli.py  api.py                             Typer CLI, FastAPI
  web/index.html                             chat UI (served at /)
```

## Notes

- **Intel Mac:** PyTorch no longer ships Intel-Mac builds, so embeddings run on ONNX through fastembed. `onnxruntime` is pinned below 1.24, the last series with Intel-Mac wheels.
- **Page numbers** in citations and in the eval set are physical PDF pages (1-based), not the page numbers printed in the report.
