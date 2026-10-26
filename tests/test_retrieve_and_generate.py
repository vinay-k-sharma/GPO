from types import SimpleNamespace

from gpo_rag.evaluation.run import declined, retrieval_metrics
from gpo_rag.generate import build_messages, parse_response
from gpo_rag.index import bm25_tokenize
from gpo_rag.models import Chunk, RetrievedChunk
from gpo_rag.prompts import NOT_FOUND
from gpo_rag.retrieve import detect_years, rrf_fuse


def make_chunk(doc="2025_annualreport", page=39, text="Revenue totaled $1,329.7 million.", year=2025):
    return Chunk(chunk_id=f"{doc}-p{page:03d}-c00", doc_id=doc, fiscal_year=year, page_start=page, page_end=page,
                 section_path=["Financial Results"], chunk_type="text", text=text, embed_text=text, n_tokens=5)


def rc(chunk, rank):
    return RetrievedChunk(chunk=chunk, rank=rank, rrf_score=1 / rank)


def test_rrf_rewards_agreement():
    scores = rrf_fuse([[1, 2, 3], [3, 1, 4]], k=60)
    assert max(scores, key=scores.get) == 1
    assert scores[3] > scores[2] and 4 in scores


def test_detect_years():
    assert detect_years("Compare FY 2024 and FY2025 revenue", {2024, 2025}) == [2024, 2025]
    assert detect_years("What was revenue in 2023?", {2024, 2025}) == []
    assert detect_years("How many employees?", {2024, 2025}) == []


def test_bm25_tokenize_numbers_and_years():
    toks = bm25_tokenize("FY2025 revenue was $1,329.7 million")
    assert "1329.7" in toks and "2025" in toks and "revenue" in toks and "the" not in toks


def test_build_messages_uses_search_results_with_citations():
    msgs = build_messages("Q?", [rc(make_chunk(), 1)])
    blocks = msgs[0]["content"]
    assert blocks[0]["type"] == "search_result" and blocks[0]["citations"] == {"enabled": True}
    assert "p.39" in blocks[0]["title"] and blocks[-1] == {"type": "text", "text": "Q?"}


def test_parse_response_maps_citations_to_pages():
    retrieved = [rc(make_chunk(page=39), 1), rc(make_chunk(page=72, text="Total operating revenues 1,329,746"), 2)]
    cit = SimpleNamespace(search_result_index=1, cited_text="Total operating revenues 1,329,746")
    response = SimpleNamespace(content=[
        SimpleNamespace(type="thinking", thinking=""),
        SimpleNamespace(type="text", text="Revenue was $1,329.7 million", citations=[cit]),
        SimpleNamespace(type="text", text=" in FY2025.", citations=None),
    ])
    answer, citations = parse_response(response, retrieved)
    assert answer == "Revenue was $1,329.7 million[1] in FY2025."
    assert citations[0].page == 72 and citations[0].fiscal_year == 2025


def test_retrieval_metrics_cross_year():
    q = {"expected_sources": [{"doc_id": "2025_annualreport", "pages": [39]},
                              {"doc_id": "2024_annualreport", "pages": [43]}]}
    got = [rc(make_chunk(page=10), 1), rc(make_chunk(page=39), 2),
           rc(make_chunk(doc="2024_annualreport", page=43, year=2024), 3)]
    m = retrieval_metrics(q, got)
    assert m["first_hit_rank"] == 2 and m["hit@1"] is False and m["hit@3"] is True and m["hit_all_docs"]


def test_declined_detection():
    assert declined(NOT_FOUND + " The excerpts cover revenue only.")
    assert not declined("Revenue was $1,329.7 million.")
