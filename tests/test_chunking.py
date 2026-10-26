from gpo_rag.chunking import chunk_elements, split_sentences
from gpo_rag.ingest.cleaner import BoilerplateFilter, clean_table
from gpo_rag.models import Element


def words(text: str) -> int:
    return len(text.split())


def el(text, page=1, section=("Finance",), kind="text", doc="2025_annualreport"):
    return Element(doc_id=doc, fiscal_year=2025, page=page, section_path=list(section), type=kind, text=text)


def test_split_sentences_keeps_numbers():
    s = split_sentences("Revenue was $1,329.7 million. Net income was $32.8 million. Done.")
    assert s == ["Revenue was $1,329.7 million.", "Net income was $32.8 million.", "Done."]


def test_text_chunks_respect_size_and_overlap():
    sentences = [f"Sentence number {i} has exactly seven words." for i in range(60)]
    chunks = chunk_elements([el(" ".join(sentences))], words, chunk_size=70, chunk_max=90, overlap=15)
    assert len(chunks) > 3
    assert all(c.n_tokens <= 90 for c in chunks)
    # consecutive chunks share overlapping sentences
    assert chunks[1].text.split(". ")[0] in chunks[0].text
    # every sentence appears somewhere
    joined = " ".join(c.text for c in chunks)
    assert all(s in joined for s in sentences)


def test_sections_are_not_mixed_and_prefix_present():
    chunks = chunk_elements([el("Alpha text.", section=("A",)), el("Beta text.", section=("B",))], words)
    assert [c.section_path for c in chunks] == [["A"], ["B"]]
    assert chunks[0].embed_text.startswith("GPO Annual Report FY2025 > A\n")


def test_large_table_split_repeats_header():
    header = "| Item | 2025 | 2024 |\n| --- | --- | --- |"
    rows = "\n".join(f"| Line item {i} | {i},000 | {i},500 |" for i in range(40))
    chunks = chunk_elements([el(f"{header}\n{rows}", kind="table")], words, chunk_size=60, chunk_max=80)
    assert len(chunks) > 1
    assert all(c.chunk_type == "table" and c.text.startswith("| Item | 2025 | 2024 |") for c in chunks)


def test_chunk_ids_deterministic_and_unique():
    els = [el("One. Two. Three.", page=3), el("| a | b |", page=3, kind="table"), el("Four.", page=4)]
    a = chunk_elements(els, words)
    b = chunk_elements(els, words)
    assert [c.chunk_id for c in a] == [c.chunk_id for c in b]
    assert len({c.chunk_id for c in a}) == len(a)


def test_boilerplate_filter_drops_running_header_and_page_numbers():
    header = "U . S . G O V E R N M E N T P U B L I S H I N G O F F I C E | 2 0 2 5 A N N U A L R E P O R T"
    pages = [f"{header}\nUnique content {i} about passports.\n{i + 10}" for i in range(10)]
    bp = BoilerplateFilter(pages)
    cleaned = bp.strip(pages[0])
    assert "G O V E R N M E N T" not in cleaned and "10" not in cleaned.split()
    assert "Unique content 0" in cleaned


def test_clean_table_moves_dollar_sign_and_strips_markup():
    md = "||**2025**|**2024**|\n|---|---|---|\n|Printing and binding|1,193,036<br>$|1,134,111<br>$|"
    out = clean_table(md)
    assert "| Printing and binding | $1,193,036 | $1,134,111 |" in out
    assert "**" not in out and "<br>" not in out
