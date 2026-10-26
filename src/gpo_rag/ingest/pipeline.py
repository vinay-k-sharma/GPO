"""Offline ingestion: PDFs -> elements.jsonl -> chunks.jsonl -> embeddings + manifest."""

import json
import logging
import time

from gpo_rag.chunking import chunk_elements
from gpo_rag.config import get_settings
from gpo_rag.embeddings import count_tokens, embed_passages
from gpo_rag.index import save_index
from gpo_rag.ingest.pdf_parser import elements_from_pages, file_sha256, parse_pages, sanity_report

log = logging.getLogger(__name__)


def is_up_to_date() -> bool:
    s = get_settings()
    manifest = s.index_dir / "manifest.json"
    if not manifest.exists():
        return False
    m = json.loads(manifest.read_text())
    current = {d: file_sha256(s.raw_dir / f"{d}.pdf") for d in s.documents}
    same_params = (m["embed_model"], m["chunk_size"], m["chunk_max"], m["chunk_overlap"]) == (
        s.embed_model, s.chunk_size, s.chunk_max, s.chunk_overlap)
    return m["documents"] == current and same_params


def run_ingest(rebuild: bool = False) -> dict:
    s = get_settings()
    if not rebuild and is_up_to_date():
        log.info("Index is up to date — skipping (use --rebuild to force).")
        return {"skipped": True}

    s.processed_dir.mkdir(parents=True, exist_ok=True)
    all_elements, reports, hashes = [], [], {}
    t0 = time.time()
    for doc_id, year in s.documents.items():
        pdf = s.raw_dir / f"{doc_id}.pdf"
        if not pdf.exists():
            raise FileNotFoundError(f"Missing {pdf}")
        hashes[doc_id] = file_sha256(pdf)
        log.info("Parsing %s ...", pdf.name)
        pages = parse_pages(pdf)
        elements = elements_from_pages(doc_id, year, pages)
        reports.append(sanity_report(doc_id, pages, elements))
        all_elements += elements

    with open(s.processed_dir / "elements.jsonl", "w") as f:
        for e in all_elements:
            f.write(e.model_dump_json() + "\n")

    chunks = chunk_elements(all_elements, count_tokens, s.chunk_size, s.chunk_max, s.chunk_overlap)
    with open(s.processed_dir / "chunks.jsonl", "w") as f:
        for c in chunks:
            f.write(c.model_dump_json() + "\n")
    log.info("Built %d chunks; embedding ...", len(chunks))

    vectors = embed_passages([c.embed_text for c in chunks])
    save_index(chunks, vectors, hashes)

    sizes = sorted(c.n_tokens for c in chunks)
    stats = {
        "documents": reports,
        "chunks": len(chunks),
        "table_chunks": sum(c.chunk_type == "table" for c in chunks),
        "tokens_p50": sizes[len(sizes) // 2],
        "tokens_p95": sizes[int(len(sizes) * 0.95)],
        "tokens_max": sizes[-1],
        "share_le_512": round(sum(n <= 512 for n in sizes) / len(sizes), 3),
        "seconds": round(time.time() - t0, 1),
    }
    (s.processed_dir / "ingest_report.json").write_text(json.dumps(stats, indent=2))
    return stats
