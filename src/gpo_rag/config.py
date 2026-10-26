"""Central configuration. Every value can be overridden with a GPO_RAG_* env var or .env entry."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]
# Export .env (e.g. ANTHROPIC_API_KEY) to the process so the Anthropic SDK can see it; real env vars win.
load_dotenv(ROOT / ".env", override=False)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="GPO_RAG_", env_file=ROOT / ".env", extra="ignore")

    # Paths
    raw_dir: Path = ROOT / "data" / "raw"
    processed_dir: Path = ROOT / "data" / "processed"
    index_dir: Path = ROOT / "data" / "index"
    eval_file: Path = ROOT / "data" / "eval" / "sample_questions.jsonl"
    reports_dir: Path = ROOT / "eval" / "reports"

    # Documents: file stem -> fiscal year
    documents: dict[str, int] = {"2025_annualreport": 2025, "2024_annualreport": 2024}

    # Chunking (tokens, measured with the embedding model's tokenizer)
    chunk_size: int = 400
    chunk_max: int = 500
    chunk_overlap: int = 60

    # Embeddings
    embed_model: str = "BAAI/bge-base-en-v1.5"
    embed_cache_dir: Path = ROOT / ".cache" / "fastembed"
    embed_batch_size: int = 32
    query_instruction: str = "Represent this sentence for searching relevant passages: "

    # Retrieval
    retrieval_mode: Literal["dense", "bm25", "hybrid"] = "hybrid"
    candidate_k: int = 20
    top_n: int = 8
    rrf_k: int = 60
    auto_year_filter: bool = True

    # Generation
    llm_provider: Literal["claude", "gemini"] = "claude"
    llm_model: str = "claude-opus-5-5"
    gemini_model: str = "gemini-3.5-flash"
    gemini_fallback_models: list[str] = ["gemini-3.1-flash-lite"]  # tried in order on 429/5xx/timeout
    gemini_timeout: float = 60.0
    effort: Literal["low", "medium", "high", "xhigh", "max"] = "medium"
    max_tokens: int = 4096
    use_refusal_fallback: bool = True
    max_retries: int = 3

    # Evaluation
    judge_model: str = "claude-opus-5-5"
    eval_workers: int = 4


@lru_cache
def get_settings() -> Settings:
    return Settings()
