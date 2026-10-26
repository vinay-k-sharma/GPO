# SPEC-001 — GPO Annual Report: Baseline RAG

| Field | Value |
|---|---|
| Owner | Devansh Nigam |
| Status | In implementation — Phases 0–5 built, Phase 6 retrieval eval done; answer eval waiting on API credentials |
| Created | 2026-10-13 |
| Objective | Build a solid, measurable **baseline** RAG pipeline over the GPO Annual Report |

---

## 1. Problem statement

We need a question-answering bot over the **U.S. Government Publishing Office (GPO) Annual Report**. Answers must be grounded in the report and must cite where they came from (page and section). This is a **baseline**. It should be simple, reproducible and measured against the sample questions, so later work (reranking, query rewriting, agentic retrieval) can be compared against real numbers.

### In scope
1. Document ingestion (PDF → structured text plus tables, with page numbers)
2. Chunking (structure-aware, with metadata)
3. Embeddings and a vector index
4. Retrieval (dense, plus BM25 hybrid)
5. Response generation with Claude, including citations
6. Validation against the provided sample questions (eval harness and report)
7. Interfaces: CLI and a FastAPI `/ask` endpoint

### Out of scope (future specs)
- Cross-encoder reranking, HyDE or query rewriting, multi-query
- Corpora beyond the FY2024 and FY2025 reports; LLM-based query routing
- Chat memory or multi-turn conversations
- UI, authentication, multi-tenant deployment
- OCR (the report is a digital PDF; we check this in Phase 1)

---

## 2. Source document — what we know

- **Primary:** GPO FY2025 Annual Report (fiscal year ending 30 Sep 2025, published Apr 2026). Public copy: https://www.gpo.gov/docs/default-source/news-content-pdf-files/2025_annualreport.pdf
- **Secondary (in scope):** GPO FY2024 Annual Report (https://www.gpo.gov/docs/default-source/news-content-pdf-files/2024_annualreport.pdf).
- **Delivered:** both PDFs are in `data/raw/` (`2025_annualreport.pdf`, 98 pages; `2024_annualreport.pdf`, 102 pages). Sample questions with gold answers and pages are in `data/eval/sample_questions.jsonl` (see §6.1).
- **Multi-year consequence:** every chunk carries `fiscal_year`; retrieval supports a `fiscal_year` filter; when a question names a year, the pipeline applies that filter (simple regex `FY ?20\d\d|20\d\d`). Questions with no year default to searching both reports, and the answer must name the year of each figure.

**Content characteristics that drive the design:**

| Characteristic | Impact on design |
|---|---|
| Narrative sections (Director's letter, business units, accomplishments) | Heading-aware chunking keeps one topic in each chunk |
| **Audited financial statements and notes** (balance sheet, income, cash flows) | Tables must be extracted as tables, not flattened. A large share of questions will be numeric. |
| Many acronyms and proper nouns (GPO, FDLP, GovInfo, SID, OIG, FY) | BM25 hybrid retrieval, because dense embeddings alone are weak on exact tokens |
| Figures repeated across sections (headcount, net income) | Citations with page numbers so answers can be checked |
| Multiple fiscal years mentioned in one report (FY2025 vs FY2024 comparatives) | The prompt tells the model to state which fiscal year a number belongs to |

---

## 3. Architecture

```
                ┌──────────────────────── OFFLINE (ingest) ────────────────────────┐
 data/raw/*.pdf │ Parse (PyMuPDF + pdfplumber) → Clean → Chunk → Embed (bge) → Index │
                │                                         │                │         │
                │                                    chunks.jsonl     Chroma + BM25 │
                └───────────────────────────────────────────────────────────────────┘

                ┌──────────────────────── ONLINE (ask) ─────────────────────────────┐
  question ───► │ Embed query → Dense top-k ─┐                                      │
                │ BM25 top-k ────────────────┴─► RRF fuse → top-N chunks            │
                │      → Claude (search_result blocks, citations on)                │
                │      → answer + citations [page, section] + retrieved context      │
                └───────────────────────────────────────────────────────────────────┘
```

### Technology choices

| Concern | Choice | Rationale |
|---|---|---|
| Language / packaging | Python 3.11+, `uv`, `pyproject.toml` | Standard for ML/RAG work, with fast reproducible installs |
| PDF text | `pymupdf` / `pymupdf4llm` (Markdown output with headings) | Fast, keeps the heading hierarchy and page numbers |
| PDF tables | `pdfplumber` (fallback: `camelot`) | Reliable table extraction for the financial statements |
| Embeddings | `sentence-transformers` + **`BAAI/bge-base-en-v1.5`** (768-d, normalized) | Strong open model that runs locally, needs no second API key, and is cheap to re-embed. `bge-small` is the fallback for slow machines. |
| Vector store | **ChromaDB** (persistent, local, cosine) | No server to run, stores metadata, and is fine at this scale (about 1–3k chunks) |
| Lexical | `rank_bm25` (BM25Okapi) | Handles exact matches on acronyms and numbers |
| Fusion | Reciprocal Rank Fusion (k=60) | No tuning, and robust across score scales |
| LLM | **Claude Opus 5.5** (`claude-opus-5-5`) through the official `anthropic` Python SDK | Default current model. Lowest rate of citing unsupported figures. |
| Grounding / citations | Claude **`search_result` content blocks** with `citations: {enabled: true}` | Native RAG citations: each claim maps back to a chunk (source = page, title = section) |
| API | FastAPI + Uvicorn | Simple `/ask` endpoint |
| CLI | Typer | `gpo-rag ingest`, `gpo-rag ask`, `gpo-rag eval` |
| Config | `pydantic-settings` plus `.env` | One place for all parameters |
| Tests | `pytest` | Unit tests plus an eval run |

---

## 4. Detailed design

### 4.1 Ingestion (`gpo_rag/ingest/`)
1. **Load** each PDF from `data/raw/`. Record `doc_id` (file stem), `fiscal_year` (from config or filename) and `sha256` (used to skip re-ingest).
2. **Parse text per page** with `pymupdf4llm.to_markdown(page_chunks=True)`. This keeps `#` headings, lists and page numbers.
3. **Extract tables per page** with `pdfplumber`, then:
   - render each table as **Markdown** (header row plus rows) to use as a `table` element, and
   - remove the table's bounding-box text from the page text so it isn't indexed twice.
4. **Clean** the text: remove repeated headers and footers (lines that appear on more than 50% of pages), page numbers, hyphenation at line breaks, and extra whitespace. Normalize Unicode quotes and dashes. Keep `$`, `%` and numbers exactly as they are.
5. **Output** `data/processed/elements.jsonl`. Each element is: `{doc_id, page, section_path:[H1,H2,H3], type: text|table, text}`.
6. **Sanity checks**, which are logged: page count, characters per page (flag pages under 50 chars as possible images that need OCR), and table count.

### 4.2 Chunking (`gpo_rag/chunking.py`)
Structure-aware recursive chunking:

| Parameter | Baseline value |
|---|---|
| Unit of measure | tokens (counted with the embedding model's tokenizer) |
| Target chunk size | **400 tokens** (max 512, the bge limit) |
| Overlap | **60 tokens** (~15%) for text chunks |
| Split hierarchy | section boundary → paragraph → sentence |
| Tables | **One chunk per table.** Large tables are split by row groups, and **the header row is repeated** in every piece. No overlap. |
| Context prefix | Each chunk's embedded text is prefixed with `"{doc title} > {section_path}\n"` (title prepending, a cheap form of contextual chunking) |

Chunk record (`data/processed/chunks.jsonl`):
```json
{
  "chunk_id": "2025_annualreport-p012-c03",
  "doc_id": "2025_annualreport",
  "fiscal_year": 2025,
  "page_start": 12, "page_end": 12,
  "section_path": ["Financial Highlights", "Revenue"],
  "chunk_type": "text",
  "text": "...",            
  "embed_text": "GPO Annual Report FY2025 > Financial Highlights > Revenue\n...",
  "n_tokens": 382
}
```
Chunk IDs are deterministic, so re-ingesting gives stable IDs for eval ground truth.

### 4.3 Embeddings & indexing (`gpo_rag/index.py`)
- Model `BAAI/bge-base-en-v1.5`, `normalize_embeddings=True`, batch size 32, on CPU or MPS.
- **Query instruction:** queries are prefixed with `"Represent this sentence for searching relevant passages: "`. Passages get no prefix (this is the bge convention).
- Chroma collection `gpo_annual_report` with cosine space. Metadata: all chunk fields except the text.
- BM25: tokenize `embed_text` (lowercase, keep numbers and `$`/`%`, simple stopword list), then pickle to `data/index/bm25.pkl`.
- Write an index manifest `data/index/manifest.json` with the embedding model, chunk parameters, doc hashes and a timestamp. Retrieval refuses to run if the configured model doesn't match the manifest.

### 4.4 Retrieval (`gpo_rag/retrieve.py`)
```
dense  = chroma.query(embed(q), k=20)
sparse = bm25.top_k(q, k=20)
fused  = RRF(dense, sparse, k=60)[:TOP_N]        # TOP_N = 6 baseline
```
- Optional metadata filter: `fiscal_year`, `chunk_type`.
- Neighbor expansion is **off** in the baseline (it's a config flag for later).
- Returns `RetrievedChunk{chunk, dense_rank, bm25_rank, rrf_score}`.
- `retrieval.mode` config: `dense | bm25 | hybrid`. All three are evaluated, so we have an ablation.

### 4.5 Generation (`gpo_rag/generate.py`)
**Claude API call** (official `anthropic` SDK, `client.messages.create`):

- `model="claude-opus-5-5"`, `max_tokens=4096`
- `output_config={"effort": "medium"}`. This is set explicitly. Opus 5.5 always uses adaptive thinking (it can't be disabled), and effort is the cost/quality control. We sweep `low` vs `medium` in eval.
- **Refusal fallback:** `betas=["server-side-fallback-2026-07-01"]`, `fallbacks="default"` (through `client.beta.messages.create`). Always check `stop_reason` before reading `content`.
- **System prompt** (static, so it can be cached with `cache_control`):
  - Answer **only** from the provided search results. If the answer isn't there, reply *"The annual report does not contain this information."*
  - For numbers: quote them exactly, include units and the fiscal year, and don't compute totals unless asked (if you do, show the working).
  - Keep it brief: a direct answer first, then supporting detail.
- **User message content** = one `search_result` block per retrieved chunk, followed by the question:
  ```python
  {"type": "search_result",
   "source": f"{doc_id}#page={page_start}",            # used for citation links
   "title": f"{' > '.join(section_path)} (p.{page_start})",
   "content": [{"type": "text", "text": chunk.text}],  # tables: one block per row group
   "citations": {"enabled": True}}                     # must be the same for every block
  ```
- **Response parsing:** join the `text` blocks. Collect `citations[]` of type `search_result_location` and map each one to `{source, title, cited_text, page}`. Return:
  ```json
  {"answer": "...", "citations": [{"page": 12, "section": "...", "quote": "..."}],
   "retrieved": [{"chunk_id": "...", "score": 0.03}], "usage": {...}, "latency_ms": 0}
  ```
- **Errors:** handle `RateLimitError`, `APIStatusError` and `APIConnectionError` separately. SDK retries are set to `max_retries=3`.
- Auth: `ANTHROPIC_API_KEY`, or an `ant auth login` profile (the SDK picks it up automatically).

### 4.6 Interfaces
- **CLI** (`gpo-rag`):
  - `gpo-rag ingest [--rebuild]`
  - `gpo-rag ask "What was GPO's net income in FY2025?" [--k 6] [--mode hybrid] [--show-context]`
  - `gpo-rag eval [--mode dense|bm25|hybrid] [--effort low|medium]`
- **API** (FastAPI):
  - `POST /ask` `{question, top_k?, mode?}` → answer JSON (§4.5)
  - `POST /ingest` → rebuilds the index (admin/local only)
  - `GET /health` → index manifest plus model names

---

## 5. Project layout
```
GPO/
├── specs/SPEC-001-baseline-rag.md        ← this file
├── pyproject.toml
├── .env.example                          # ANTHROPIC_API_KEY, paths, params
├── data/
│   ├── raw/                              # GPO annual report PDF(s)   ← user drops here
│   ├── eval/sample_questions.jsonl       # sample questions (+ gold)  ← user drops here
│   ├── processed/{elements,chunks}.jsonl
│   └── index/{chroma/, bm25.pkl, manifest.json}
├── src/gpo_rag/
│   ├── config.py          # pydantic-settings
│   ├── ingest/{pdf_parser.py, tables.py, cleaner.py}
│   ├── chunking.py
│   ├── embeddings.py
│   ├── index.py
│   ├── retrieve.py
│   ├── prompts.py
│   ├── generate.py
│   ├── pipeline.py        # ask(question) -> Answer
│   ├── cli.py             # Typer
│   └── api.py             # FastAPI
├── eval/
│   ├── run_eval.py
│   ├── judge.py
│   └── reports/           # eval_<timestamp>.{json,md}
└── tests/
    ├── test_chunking.py
    ├── test_retrieve.py
    └── test_generate_parsing.py
```

---

## 6. Validation (sample questions)

### 6.1 Eval set format — `data/eval/sample_questions.jsonl`
45 questions, one JSON object per line:
```json
{"id": "fy25-q03", "question": "How many employees did GPO have at the end of fiscal year 2025?",
 "expected_answer": "1,650 employees as of September 30, 2025 ...",
 "category": "numeric", "fiscal_years": [2025],
 "expected_sources": [{"doc_id": "2025_annualreport", "pages": [8, 6, 18, 28]}],
 "evidence": [{"doc_id": "2025_annualreport", "page": 8, "quote": "..."}]}
```
- `pages` are **1-based physical PDF page indexes** (the same numbering ingestion stores in `page_start`), not printed page numbers. The first page listed is the primary one.
- Retrieval counts as a **hit** when a retrieved chunk matches any `(doc_id, page)` in `expected_sources`. For `cross_year` questions, record both `hit_any` and `hit_all` (every listed document is retrieved).
- `evidence` quotes are verbatim and were checked automatically against the page text.

| Category | Count | What it tests |
|---|---|---|
| `numeric` | 15 | Exact figures (revenue, net income, headcount, passports, GovInfo, Treasury balance) |
| `factual` | 11 | Names, programs, dates, auditor, legislation |
| `narrative` | 6 | Multi-point summaries (strategic goals, AI, workforce, GSID) |
| `table` | 4 | Line items that only appear in the financial-statement tables, with comparative year |
| `cross_year` | 5 | FY2024 vs FY2025 comparisons that need both documents |
| `unanswerable` | 4 | Topics in neither report (`expected_answer` = `NOT_IN_REPORT`). The bot must decline. |

**Known source quirks** (found while building the set; avoid them as exact-match targets and note them in eval failure analysis):
- **Depository library counts disagree within each report:**
  - FY2025: 1,089 / 1,093 / 1,092
  - FY2024: 1,105 / ~1,097 / 1,100
- **"Adjusted net income" excludes different items each year.** Cross-year questions compare the unadjusted figures.
- **The FY2025 "By the Numbers" pages (28–29) carry a "2024 ANNUAL REPORT" running header.** This is a risk for year-filtered retrieval, so the year filter must use the document's `fiscal_year`, not the page text.
- **Some pages have no usable text:**
  - FY2025 performance charts (pp. 56–62) are images with no extractable text.
  - FY2025 pp. 1, 2, 4 and 44 are empty or cover pages.
- **Financial tables come out flattened** (one value per line) in the plain-text extraction. This confirms the need for pdfplumber table extraction in §4.1.

### 6.2 Metrics

| Layer | Metric | How |
|---|---|---|
| Retrieval | **Hit@k** (k=1,3,6), **MRR** | Is a chunk from an `expected_pages` page among the retrieved chunks? |
| Generation | **Answer correctness** (0/1 plus a 1–5 score) | LLM judge compares the answer with `expected_answer`; numeric values are also checked with exact match after normalization |
| Generation | **Faithfulness / groundedness** | LLM judge: is every claim supported by the cited text? |
| Generation | **Citation coverage** | Share of answer sentences with at least one citation; share of citations pointing to an expected page |
| Behaviour | **Refusal accuracy** | `unanswerable` questions → "not contained" response |
| Ops | Latency p50/p95, input/output tokens, cost per question | From `usage` and timers |

- Judge: Claude (`claude-opus-5-5` by default, configurable) using a fixed rubric prompt and structured output (`output_config.format`, JSON schema). The judge call is separate from the answer call because citations and structured outputs can't be combined in one request.
- The report goes to `eval/reports/` as JSON plus a Markdown summary table, with a per-question breakdown and failure tags (`retrieval_miss`, `wrong_number`, `hallucination`, `bad_refusal`).

### 6.3 Baseline acceptance targets (to be confirmed after the first run)

| Metric | Target |
|---|---|
| Retrieval Hit@6 | ≥ 90% |
| Answer correctness | ≥ 85% |
| Faithfulness | ≥ 95% |
| Refusal accuracy (unanswerable) | 100% |
| p95 latency (`/ask`) | < 15 s |

### 6.4 Ablations run in the baseline
`mode ∈ {dense, bm25, hybrid}` × `top_n ∈ {4, 6, 10}` × `effort ∈ {low, medium}` on the full eval set. We record the winning configuration as the **frozen baseline**.

---

## 7. Implementation plan (phased)

| # | Phase | Tasks | Done when |
|---|---|---|---|
| **0** | Setup | `uv init`, `pyproject.toml` deps, `config.py`, `.env.example`, logging, `data/` folders; confirm Claude auth (`ant auth status` or key) | `gpo-rag --help` runs; a 1-line Claude call succeeds |
| **1** | Ingestion | PDF parser, table extractor, cleaner, `elements.jsonl`, sanity report | All pages parsed; financial-statement tables appear as Markdown; no empty pages (or OCR flagged) |
| **2** | Chunking | Structure-aware chunker, table chunker with header repeat, title prefix, deterministic IDs, unit tests | `chunks.jsonl` written; 95% of chunks ≤ 512 tokens; tests pass |
| **3** | Embed & index | bge embeddings, Chroma collection, BM25 pickle, manifest | Index builds in under 5 min on a laptop; re-ingest is idempotent |
| **4** | Retrieval | Dense, BM25, RRF hybrid, filters, `--show-context` CLI | Manual spot check on 5 sample questions shows the right pages in the top-6 |
| **5** | Generation | Prompt, `search_result` blocks, citations parsing, refusal fallback, error handling, `ask` CLI plus `/ask` API | End-to-end answers include page citations; unanswerable questions are refused |
| **6** | Evaluation | Eval loader (gold labels already provided), retrieval metrics, LLM judge, report, ablations | Eval report generated; baseline configuration frozen; results recorded in §9 |
| **7** | Hardening & handoff | README (setup, run, eval), tests in CI (`pytest`), cost/latency notes, list of failure cases for the next spec | A fresh clone gets to an answer by following the README |

**Estimated effort:** about 4–6 dev-days. Phases 1–2 are the riskiest, because of table extraction quality.

---

## 8. Risks & mitigations

| Risk | Mitigation |
|---|---|
| Financial tables parse badly (merged cells, multi-line labels) | Use pdfplumber with tuned `table_settings`, fall back to camelot `lattice`, and manually inspect the 5 key statements in Phase 1 |
| A number is retrieved from the wrong fiscal year (comparative columns) | Keep table headers in every chunk; the prompt requires the fiscal year to be named; eval tag `wrong_number` |
| Dense retrieval misses acronym or number queries | BM25 hybrid (already in the baseline) |
| Hallucinated figures | Only `search_result` grounding, citations required, faithfulness judged in eval, explicit "not contained" path |
| Scanned or image pages | Character-count check in Phase 1; add OCR (`ocrmypdf`) only if pages are flagged |
| Too few sample questions for meaningful metrics | Add 15–25 more questions written by hand from the report (numeric, narrative, unanswerable) |

---

## 8a. Implementation notes and deviations (2026-10-13)

| Spec said | Built | Why |
|---|---|---|
| pdfplumber for tables | **pymupdf4llm layout mode** for both text and tables | Its Markdown tables already reproduce the financial statements cleanly, with the FY2025 and FY2024 columns intact. One parser, so tables are never indexed twice. |
| sentence-transformers | **fastembed (ONNX)**, `BAAI/bge-base-en-v1.5` (Qdrant quantized ONNX) | PyTorch no longer ships Intel-Mac builds. `onnxruntime` is pinned below 1.24 (the last series with Intel-Mac wheels). |
| ChromaDB | **NumPy matrix with exact cosine search**, plus `rank_bm25` | 431 chunks: search is instant and exact, with no extra service. Metadata filtering is a boolean mask. |
| top_n = 6 | **top_n = 8** (provisional) | The retrieval ablation below shows Hit@6 = 100% at top-8 vs 97.6% at top-6. Final choice comes after the end-to-end eval. |
| Year filter | Regex finds the fiscal years named in the question. With 2 or more years, each year gets an equal share of top_n. | Comparison questions see both reports. |
| Heading hierarchy | Heading levels from the layout engine are inconsistent, so a parent heading expires after 3 pages, and TOC and letter-spaced running headers are skipped | Otherwise "TABLE OF CONTENTS" became the parent section of the whole report |

Ingest results:
- 200 pages → 1,114 elements → **431 chunks** (105 tables).
- Token counts: p50 220, p95 458, max 500; 100% of chunks are ≤ 512 tokens.
- A full rebuild takes about 7.5 min on an Intel i7 CPU (~100 s parsing, the rest embedding). This misses the < 5 min target, but it's a one-time cost.
- The first run also downloads the model (~210 MB) into `.cache/fastembed`.

## 9. Results log
_To be filled after Phase 6._

**Retrieval ablation** (2026-10-13, 41 answerable questions; `gpo-rag ablate`):

| mode | top_n | Hit@1 | Hit@3 | Hit@6 | Hit@10 | MRR | Cross-year: both reports retrieved |
|---|---|---|---|---|---|---|---|
| dense | 6 | 0.707 | 0.829 | 0.902 | – | 0.780 | 0.8 |
| dense | 10 | 0.707 | 0.829 | 0.902 | 0.951 | 0.786 | 0.8 |
| bm25 | 6 | 0.585 | 0.878 | 0.951 | – | 0.733 | 0.8 |
| bm25 | 10 | 0.585 | 0.878 | 0.951 | 1.000 | 0.739 | 1.0 |
| **hybrid** | 6 | 0.756 | 0.927 | 0.976 | – | 0.841 | 0.8 |
| **hybrid** | **8** | 0.756 | 0.927 | **1.000** | – | 0.846 | 0.8 |
| **hybrid** | 10 | 0.756 | 0.927 | 1.000 | 1.000 | 0.846 | 1.0 |

What the ablation shows:
- Hybrid search beats dense-only and BM25-only on every metric.
- Remaining weak spots:
  - Two table questions find the statement page only at rank 4.
  - `cross-q01` ranks the narrative "$1.3 billion" pages above the exact-figure pages at top-6/8.

**End-to-end** (to be filled in once credentials are available):

| Date | Config (mode / top_n / effort) | Hit@6 | MRR | Correct | Faithful | Refusal | p95 s | $/q |
|---|---|---|---|---|---|---|---|---|
| | | | | | | | | |

---

## 10. Open questions
1. ~~Which report editions are in scope?~~ **Resolved:** FY2025 and FY2024.
2. ~~Do the sample questions come with expected answers?~~ **Resolved:** generated with gold answers, pages and evidence; a human spot-check is still recommended before freezing the baseline.
3. Deployment target after the baseline: local only, or a container behind an internal gateway?
4. Is there a cost ceiling per query? (This decides whether we drop effort to `low` or try a cheaper model in a later spec.)

## 11. Next-iteration candidates (not in this spec)
Cross-encoder reranker (`bge-reranker-v2-m3`), contextual retrieval (an LLM-written context sentence for each chunk), query rewriting and decomposition for comparison questions, neighbor/parent-chunk expansion, multi-year corpus routing, streaming responses, a Streamlit UI.
