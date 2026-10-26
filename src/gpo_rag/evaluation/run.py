"""Evaluation harness over data/eval/sample_questions.jsonl (SPEC-001 §6)."""

import json
import logging
import statistics
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

from gpo_rag.config import get_settings
from gpo_rag.models import Answer, RetrievedChunk
from gpo_rag.prompts import NOT_FOUND
from gpo_rag.retrieve import Mode, retrieve

log = logging.getLogger(__name__)

# Claude Opus 5.5 list prices, USD per million tokens
PRICE_IN, PRICE_OUT, PRICE_CACHE_READ = 4.00, 20.00, 0.20
KS = (1, 3, 6, 10)


def load_questions(path: Path | None = None) -> list[dict]:
    path = path or get_settings().eval_file
    return [json.loads(line) for line in open(path) if line.strip()]


def _matches(r: RetrievedChunk, sources: list[dict]) -> str | None:
    """doc_id of the expected source this chunk satisfies, if any."""
    for src in sources:
        if r.chunk.doc_id == src["doc_id"] and any(r.chunk.page_start <= p <= r.chunk.page_end for p in src["pages"]):
            return src["doc_id"]
    return None


def retrieval_metrics(q: dict, retrieved: list[RetrievedChunk]) -> dict:
    sources = q["expected_sources"]
    if not sources:
        return {}
    first_hit = next((r.rank for r in retrieved if _matches(r, sources)), None)
    out = {f"hit@{k}": bool(first_hit and first_hit <= k) for k in KS if k <= len(retrieved) or k == 1}
    out["rr"] = 1.0 / first_hit if first_hit else 0.0
    out["first_hit_rank"] = first_hit
    docs_hit = {_matches(r, sources) for r in retrieved} - {None}
    out["hit_all_docs"] = docs_hit == {s["doc_id"] for s in sources}
    return out


def declined(answer_text: str) -> bool:
    return NOT_FOUND.lower().rstrip(".") in answer_text.lower()


def _cost(usage: dict) -> float:
    return (usage.get("input_tokens", 0) * PRICE_IN
            + usage.get("cache_creation_input_tokens", 0) * PRICE_IN * 1.25
            + usage.get("cache_read_input_tokens", 0) * PRICE_CACHE_READ
            + usage.get("output_tokens", 0) * PRICE_OUT) / 1e6


def evaluate_one(q: dict, mode: Mode, top_n: int, retrieval_only: bool, use_judge: bool) -> dict:
    row = {"id": q["id"], "category": q["category"], "question": q["question"]}
    if retrieval_only:
        retrieved = retrieve(q["question"], top_n=top_n, mode=mode)
        row["retrieved"] = [f"{r.chunk.doc_id}:p{r.chunk.page_start}" for r in retrieved]
        row.update(retrieval_metrics(q, retrieved))
        return row

    from gpo_rag.pipeline import ask  # imported lazily so retrieval-only runs need no API client

    ans: Answer = ask(q["question"], top_n=top_n, mode=mode)
    row["retrieved"] = [f"{r.chunk.doc_id}:p{r.chunk.page_start}" for r in ans.retrieved]
    row.update(retrieval_metrics(q, ans.retrieved))
    row.update(answer=ans.answer, stop_reason=ans.stop_reason, latency_ms=ans.latency_ms,
               cost_usd=round(_cost(ans.usage), 5), citations=[c.model_dump() for c in ans.citations])
    row["declined"] = declined(ans.answer)
    if q["category"] == "unanswerable":
        row["correct"] = row["declined"]
        row["faithful"] = True
        return row

    cited_pages = [(c.doc_id, c.page) for c in ans.citations]
    expected_pages = {(s["doc_id"], p) for s in q["expected_sources"] for p in s["pages"]}
    row["has_citation"] = bool(cited_pages)
    row["citation_on_expected_page"] = any(cp in expected_pages for cp in cited_pages)
    if use_judge:
        from gpo_rag.evaluation.judge import judge

        v = judge(ans, q["expected_answer"])
        row.update(judgement=v.correctness, judge_score=v.score, faithful=v.faithful,
                   unsupported_claims=v.unsupported_claims, judge_reasoning=v.reasoning)
        row["correct"] = v.correctness == "correct"
    return row


def failure_tag(row: dict) -> str | None:
    if row["category"] == "unanswerable":
        return None if row.get("correct") else "bad_refusal"
    if row.get("hit@6") is False and not row.get("correct"):
        return "retrieval_miss"
    if row.get("declined"):
        return "false_refusal"
    if row.get("faithful") is False:
        return "hallucination"
    if row.get("correct") is False:
        return "wrong_or_incomplete"
    return None


def _rate(rows: list[dict], key: str) -> float | None:
    vals = [r[key] for r in rows if r.get(key) is not None]
    return round(sum(map(bool, vals)) / len(vals), 3) if vals else None


def summarize(rows: list[dict]) -> dict:
    answerable = [r for r in rows if r["category"] != "unanswerable"]
    summary = {f"hit@{k}": _rate(answerable, f"hit@{k}") for k in KS}
    rr = [r["rr"] for r in answerable if "rr" in r]
    summary["mrr"] = round(statistics.mean(rr), 3) if rr else None
    cross = [r for r in rows if r["category"] == "cross_year"]
    summary["cross_year_hit_all_docs"] = _rate(cross, "hit_all_docs")
    if any("answer" in r for r in rows):
        lat = sorted(r["latency_ms"] for r in rows)
        summary.update(
            correct=_rate(answerable, "correct"),
            faithful=_rate(answerable, "faithful"),
            citation_coverage=_rate(answerable, "has_citation"),
            citation_on_expected_page=_rate(answerable, "citation_on_expected_page"),
            refusal_accuracy=_rate([r for r in rows if r["category"] == "unanswerable"], "correct"),
            false_refusals=sum(bool(r.get("declined")) for r in answerable),
            latency_p50_s=round(lat[len(lat) // 2] / 1000, 1),
            latency_p95_s=round(lat[min(len(lat) - 1, int(len(lat) * 0.95))] / 1000, 1),
            cost_per_question_usd=round(statistics.mean(r["cost_usd"] for r in rows), 4),
        )
        by_cat: dict[str, dict] = {}
        for cat in sorted({r["category"] for r in rows}):
            rs = [r for r in rows if r["category"] == cat]
            by_cat[cat] = {"n": len(rs), "correct": _rate(rs, "correct"), "hit@6": _rate(rs, "hit@6")}
        summary["by_category"] = by_cat
        tags: dict[str, int] = {}
        for r in rows:
            if t := r.get("failure"):
                tags[t] = tags.get(t, 0) + 1
        summary["failures"] = tags
    return summary


def run_eval(mode: Mode | None = None, top_n: int | None = None, retrieval_only: bool = False,
             use_judge: bool = True, ids: list[str] | None = None, label: str = "") -> dict:
    s = get_settings()
    mode, top_n = mode or s.retrieval_mode, top_n or s.top_n
    questions = [q for q in load_questions() if not ids or q["id"] in ids]
    workers = 1 if retrieval_only else s.eval_workers
    retrieve("warm-up", top_n=1, mode=mode)  # load index + embedding model once, before threads start
    with ThreadPoolExecutor(max_workers=workers) as pool:
        rows = list(pool.map(lambda q: evaluate_one(q, mode, top_n, retrieval_only, use_judge), questions))
    for r in rows:
        r["failure"] = failure_tag(r) if not retrieval_only else None
    config = {"mode": mode, "top_n": top_n, "retrieval_only": retrieval_only,
              "llm_model": None if retrieval_only else s.llm_model,
              "effort": None if retrieval_only else s.effort, "embed_model": s.embed_model,
              "chunk_size": s.chunk_size, "n_questions": len(rows)}
    result = {"config": config, "summary": summarize(rows), "rows": rows}
    write_report(result, label)
    return result


def write_report(result: dict, label: str = "") -> Path:
    s = get_settings()
    s.reports_dir.mkdir(parents=True, exist_ok=True)
    cfg = result["config"]
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    name = f"eval_{stamp}_{cfg['mode']}_n{cfg['top_n']}" + ("_retrieval" if cfg["retrieval_only"] else f"_{cfg['effort']}")
    name += f"_{label}" if label else ""
    (s.reports_dir / f"{name}.json").write_text(json.dumps(result, indent=2, default=str))

    sm = result["summary"]
    lines = [f"# Eval report — {name}", "", "## Config", "", "```json", json.dumps(cfg, indent=2), "```", "",
             "## Summary", "", "| Metric | Value |", "|---|---|"]
    lines += [f"| {k} | {v} |" for k, v in sm.items() if not isinstance(v, dict)]
    if "by_category" in sm:
        lines += ["", "## By category", "", "| Category | n | Correct | Hit@6 |", "|---|---|---|---|"]
        lines += [f"| {c} | {v['n']} | {v['correct']} | {v['hit@6']} |" for c, v in sm["by_category"].items()]
    lines += ["", "## Per question", ""]
    if cfg["retrieval_only"]:
        lines += ["| id | category | first hit rank | top retrieved |", "|---|---|---|---|"]
        lines += [f"| {r['id']} | {r['category']} | {r.get('first_hit_rank')} | {', '.join(r['retrieved'][:3])} |"
                  for r in result["rows"]]
    else:
        lines += ["| id | category | hit@6 | correct | faithful | failure | latency s |", "|---|---|---|---|---|---|---|"]
        lines += [f"| {r['id']} | {r['category']} | {r.get('hit@6')} | {r.get('judgement', r.get('correct'))} | "
                  f"{r.get('faithful')} | {r.get('failure') or ''} | {r['latency_ms'] / 1000:.1f} |" for r in result["rows"]]
    path = s.reports_dir / f"{name}.md"
    path.write_text("\n".join(lines) + "\n")
    log.info("Wrote %s", path)
    return path
