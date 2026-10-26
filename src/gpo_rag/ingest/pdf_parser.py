"""PDF -> structural elements (SPEC-001 §4.1).

pymupdf4llm (layout mode) gives per-page Markdown with `#` headings and `|` tables, which is
good enough for the financial statements that pdfplumber was originally planned for.
"""

import hashlib
import logging
import re
from pathlib import Path

import pymupdf
import pymupdf4llm

from gpo_rag.ingest.cleaner import BoilerplateFilter, clean_heading, clean_table, clean_text
from gpo_rag.models import Element

log = logging.getLogger(__name__)

_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
_CAPTION_MAX_WORDS = 25
_LETTER_SPACED = re.compile(r"^(?:\S \.? ?){6,}")  # "U . S . G O V E R N M E N T ..."
_SKIP_HEADINGS = {"table of contents", "contents"}
# Heading levels from the layout engine are font-size based and inconsistent across pages, so an
# ancestor heading is dropped once it is more than this many pages older than a new heading.
_ANCESTOR_MAX_PAGES = 3


def _usable_heading(title: str) -> bool:
    return bool(title) and title.lower() not in _SKIP_HEADINGS and not _LETTER_SPACED.match(title) \
        and not title.replace(" ", "").isdigit()


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_pages(pdf_path: Path) -> list[tuple[int, str]]:
    """Return [(1-based page number, markdown)] for every page."""
    with pymupdf.open(pdf_path) as doc:
        pages = pymupdf4llm.to_markdown(doc, page_chunks=True, show_progress=False)
    return [(p["metadata"].get("page_number") or i + 1, p["text"]) for i, p in enumerate(pages)]


def _blocks(markdown: str) -> list[tuple[str, str]]:
    """Split one page of markdown into ("heading"|"table"|"text", raw) blocks."""
    out: list[tuple[str, str]] = []
    para: list[str] = []
    table: list[str] = []

    def end_para():
        if para:
            out.append(("text", " ".join(para)))
            para.clear()

    def end_table():
        if table:
            out.append(("table", "\n".join(table)))
            table.clear()

    for line in markdown.splitlines():
        s = line.strip()
        if s.startswith("|"):
            end_para()
            table.append(s)
            continue
        end_table()
        if not s:
            end_para()
        elif m := _HEADING.match(s):
            end_para()
            out.append(("heading", line))
        else:
            para.append(s)
    end_para()
    end_table()
    return out


def elements_from_pages(doc_id: str, fiscal_year: int, pages: list[tuple[int, str]]) -> list[Element]:
    bp = BoilerplateFilter([md for _, md in pages])
    elements: list[Element] = []
    stack: list[tuple[int, str, int]] = []  # (heading level, title, page)
    last_was_heading = False

    for page_no, md in pages:
        for kind, raw in _blocks(bp.strip(md)):
            if kind == "heading":
                m = _HEADING.match(raw.strip())
                level, title = len(m.group(1)), clean_heading(m.group(2))
                if not _usable_heading(title):
                    continue
                # Consecutive same-level headings (title + subtitle) are merged into one level
                if last_was_heading and stack and stack[-1][0] == level:
                    stack[-1] = (level, f"{stack[-1][1]} — {title}", page_no)
                else:
                    stack = [h for h in stack if h[0] < level and page_no - h[2] <= _ANCESTOR_MAX_PAGES]
                    stack.append((level, title, page_no))
                last_was_heading = True
                continue

            last_was_heading = False
            section = [t for _, t, _ in stack]
            if kind == "table":
                text = clean_table(raw)
                if not text:
                    continue
                # Attach a short preceding caption (e.g. "(Dollars in Thousands)") to the table
                prev = elements[-1] if elements else None
                if prev and prev.type == "text" and prev.page == page_no and len(prev.text.split()) <= _CAPTION_MAX_WORDS:
                    text = f"{prev.text}\n{text}"
                elements.append(Element(doc_id=doc_id, fiscal_year=fiscal_year, page=page_no,
                                        section_path=section, type="table", text=text))
            else:
                text = clean_text(raw)
                if text:
                    elements.append(Element(doc_id=doc_id, fiscal_year=fiscal_year, page=page_no,
                                            section_path=section, type="text", text=text))
    return elements


def sanity_report(doc_id: str, pages: list[tuple[int, str]], elements: list[Element]) -> dict:
    chars = {p: 0 for p, _ in pages}
    for e in elements:
        chars[e.page] += len(e.text)
    low = [p for p, c in chars.items() if c < 50]
    report = {
        "doc_id": doc_id,
        "pages": len(pages),
        "elements": len(elements),
        "tables": sum(e.type == "table" for e in elements),
        "low_text_pages": low,
    }
    log.info("Parsed %s: %s", doc_id, report)
    return report
