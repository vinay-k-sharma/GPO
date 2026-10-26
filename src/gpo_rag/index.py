"""Build and load the search index: chunks.jsonl + normalised embedding matrix + BM25 (SPEC-001 §4.3).

At ~1-2k chunks an exact cosine search over a NumPy matrix is instant, so no vector DB is needed.
"""

import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache

import numpy as np
from rank_bm25 import BM25Okapi

from gpo_rag.config import Settings, get_settings
from gpo_rag.models import Chunk

log = logging.getLogger(__name__)

_STOPWORDS = frozenset(
    "a an and are as at be by for from has have in is it its of on or that the this to was were will with "
    "what which who how did does do gpo's".split()
)
_TOKEN = re.compile(r"\$?\d[\d,.]*%?|[a-z][a-z0-9'&.-]*", re.I)


def bm25_tokenize(text: str) -> list[str]:
    tokens = []
    for t in _TOKEN.findall(text.lower()):
        t = t.strip(".,'-")
        if not t or t in _STOPWORDS:
            continue
        tokens.append(t)
        # Index numbers both with and without separators/currency so "$1,329.7" matches "1329.7"
        bare = t.replace("$", "").replace(",", "").rstrip("%")
        if bare != t and bare:
            tokens.append(bare)
        if t.startswith("fy") and t[2:].isdigit():  # "fy2025" -> also "2025"
            tokens.append(t[2:])
    return tokens


def save_index(chunks: list[Chunk], vectors: np.ndarray, doc_hashes: dict[str, str], s: Settings | None = None) -> None:
    s = s or get_settings()
    s.index_dir.mkdir(parents=True, exist_ok=True)
    np.save(s.index_dir / "embeddings.npy", vectors)
    with open(s.index_dir / "chunks.jsonl", "w") as f:
        for c in chunks:
            f.write(c.model_dump_json() + "\n")
    manifest = {
        "embed_model": s.embed_model,
        "chunk_size": s.chunk_size,
        "chunk_max": s.chunk_max,
        "chunk_overlap": s.chunk_overlap,
        "documents": doc_hashes,
        "n_chunks": len(chunks),
        "dim": int(vectors.shape[1]),
        "built_at": datetime.now(timezone.utc).isoformat(),
    }
    (s.index_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    load_index.cache_clear()


@dataclass
class Index:
    chunks: list[Chunk]
    vectors: np.ndarray
    bm25: BM25Okapi
    manifest: dict
    years: np.ndarray  # fiscal_year per chunk, for filtering


@lru_cache
def load_index() -> Index:
    s = get_settings()
    manifest_path = s.index_dir / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError("Index not found — run `gpo-rag ingest` first.")
    manifest = json.loads(manifest_path.read_text())
    if manifest["embed_model"] != s.embed_model:
        raise RuntimeError(
            f"Index was built with {manifest['embed_model']} but config uses {s.embed_model}; re-run ingest."
        )
    chunks = [Chunk.model_validate_json(line) for line in open(s.index_dir / "chunks.jsonl")]
    vectors = np.load(s.index_dir / "embeddings.npy")
    bm25 = BM25Okapi([bm25_tokenize(c.embed_text) for c in chunks])
    years = np.array([c.fiscal_year for c in chunks])
    return Index(chunks=chunks, vectors=vectors, bm25=bm25, manifest=manifest, years=years)
