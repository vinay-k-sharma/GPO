from gpo_rag.generate_gemini import build_prompt, parse_answer
from tests.test_retrieve_and_generate import make_chunk, rc


def test_build_prompt_numbers_sources():
    prompt = build_prompt("What was revenue?", [rc(make_chunk(page=39), 1), rc(make_chunk(page=40), 2)])
    assert "[1] FY2025" in prompt and "[2] FY2025" in prompt and "(p.40)" in prompt
    assert prompt.endswith("Question: What was revenue?")


def test_parse_answer_renumbers_and_drops_invalid():
    retrieved = [rc(make_chunk(page=p), i) for i, p in enumerate([10, 20, 30], 1)]
    answer, cits = parse_answer("A [3]. B [1, 3]. C [9].", retrieved)
    assert answer == "A [1]. B [2][1]. C ."
    assert [c.page for c in cits] == [30, 10]


def test_parse_answer_not_found_has_no_citations():
    from gpo_rag.prompts import NOT_FOUND
    answer, cits = parse_answer(f"{NOT_FOUND} The excerpts cover GPO operations [1][2].", [rc(make_chunk(), 1)])
    assert cits == [] and "[" not in answer
