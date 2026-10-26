"""Command line: gpo-rag ingest | ask | eval | ablate | serve."""

import json
import logging
from typing import Optional

import typer

from gpo_rag.config import get_settings

app = typer.Typer(add_completion=False, help="Baseline RAG over the GPO FY2024/FY2025 Annual Reports.")


@app.callback()
def _main(verbose: bool = typer.Option(False, "--verbose", "-v")) -> None:
    logging.basicConfig(level=logging.INFO if verbose else logging.WARNING,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    for noisy in ("httpx", "httpx2", "anthropic", "huggingface_hub"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


@app.command()
def ingest(rebuild: bool = typer.Option(False, "--rebuild", help="Rebuild even if the index is current")) -> None:
    """Parse PDFs, chunk, embed, and write the index."""
    from gpo_rag.ingest.pipeline import run_ingest

    typer.echo(json.dumps(run_ingest(rebuild=rebuild), indent=2))


@app.command()
def ask(
    question: str,
    top_n: Optional[int] = typer.Option(None, "--k", help="Chunks passed to Claude"),
    mode: Optional[str] = typer.Option(None, help="dense | bm25 | hybrid"),
    show_context: bool = typer.Option(False, "--show-context", help="Print the retrieved chunks"),
    retrieval_only: bool = typer.Option(False, "--retrieval-only", help="Skip Claude; just show retrieval"),
) -> None:
    """Answer a question with citations."""
    from gpo_rag.retrieve import retrieve

    if retrieval_only:
        for r in retrieve(question, top_n=top_n, mode=mode):
            c = r.chunk
            typer.secho(f"#{r.rank} FY{c.fiscal_year} p.{c.page_start} [{c.chunk_type}] {c.section}  "
                        f"(rrf={r.rrf_score}, dense={r.dense_rank}, bm25={r.bm25_rank})", bold=True)
            typer.echo(c.text[:600] + ("..." if len(c.text) > 600 else "") + "\n")
        return

    from gpo_rag.generate import GenerationError
    from gpo_rag.pipeline import ask as run_ask

    try:
        ans = run_ask(question, top_n=top_n, mode=mode)
    except GenerationError as e:
        typer.secho(str(e), fg="red", err=True)
        raise typer.Exit(1)
    typer.echo("\n" + ans.answer + "\n")
    if ans.citations:
        typer.secho("Sources", bold=True)
        for i, c in enumerate(ans.citations, 1):
            typer.echo(f"  [{i}] FY{c.fiscal_year} Annual Report, p.{c.page} — {c.section}")
    if show_context:
        typer.secho("\nRetrieved context", bold=True)
        for r in ans.retrieved:
            typer.echo(f"  #{r.rank} FY{r.chunk.fiscal_year} p.{r.chunk.page_start} {r.chunk.section} (rrf={r.rrf_score})")
    u = ans.usage
    typer.secho(f"\n{ans.latency_ms / 1000:.1f}s · in {u.get('input_tokens')} / out {u.get('output_tokens')} tokens · "
                f"{ans.model}", dim=True)


@app.command("eval")
def eval_cmd(
    mode: Optional[str] = typer.Option(None, help="dense | bm25 | hybrid"),
    top_n: Optional[int] = typer.Option(None, "--k"),
    effort: Optional[str] = typer.Option(None, help="low | medium | high"),
    retrieval_only: bool = typer.Option(False, "--retrieval-only", help="Retrieval metrics only (no API calls)"),
    no_judge: bool = typer.Option(False, "--no-judge", help="Skip the LLM judge"),
    ids: Optional[str] = typer.Option(None, help="Comma-separated question ids"),
    label: str = typer.Option("", help="Suffix for the report filename"),
) -> None:
    """Run the sample-question evaluation and write a report to eval/reports/."""
    from gpo_rag.evaluation.run import run_eval

    if effort:
        get_settings().effort = effort  # type: ignore[assignment]
    result = run_eval(mode=mode, top_n=top_n, retrieval_only=retrieval_only, use_judge=not no_judge,
                      ids=ids.split(",") if ids else None, label=label)
    typer.echo(json.dumps({"config": result["config"], "summary": result["summary"]}, indent=2))


@app.command()
def ablate() -> None:
    """Retrieval-only grid: mode x top_n (no API calls)."""
    from gpo_rag.evaluation.run import run_eval

    typer.echo("| mode | top_n | hit@1 | hit@3 | hit@6 | hit@10 | MRR | cross-year both docs |")
    typer.echo("|---|---|---|---|---|---|---|---|")
    for mode in ("dense", "bm25", "hybrid"):
        for top_n in (4, 6, 10):
            sm = run_eval(mode=mode, top_n=top_n, retrieval_only=True, label="ablate")["summary"]
            typer.echo(f"| {mode} | {top_n} | {sm['hit@1']} | {sm['hit@3']} | {sm.get('hit@6')} | "
                       f"{sm.get('hit@10')} | {sm['mrr']} | {sm['cross_year_hit_all_docs']} |")


@app.command()
def serve(host: str = "127.0.0.1", port: int = 8000) -> None:
    """Start the FastAPI server."""
    import uvicorn

    uvicorn.run("gpo_rag.api:app", host=host, port=port)


if __name__ == "__main__":
    app()
