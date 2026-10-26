"""Structure-aware chunking (SPEC-001 §4.2).

- Text: paragraphs are packed into ~chunk_size-token chunks within one section, split at
  sentence boundaries when needed, with ~chunk_overlap tokens of trailing sentences carried over.
- Tables: one chunk per table; oversized tables are split by row groups with the header repeated.
- Every chunk's embed_text is prefixed with "<doc title> > <section path>".
"""

import re
from collections.abc import Callable, Iterable

from gpo_rag.models import Chunk, Element

TokenCounter = Callable[[str], int]

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"“(])")


def doc_title(fiscal_year: int) -> str:
    return f"GPO Annual Report FY{fiscal_year}"


def split_sentences(text: str) -> list[str]:
    return [s for s in _SENTENCE_SPLIT.split(text.strip()) if s]


def _hard_split(text: str, max_tokens: int, count: TokenCounter) -> list[str]:
    """Last resort for a single 'sentence' longer than max_tokens: split on words."""
    words, out, cur = text.split(), [], []
    for w in words:
        cur.append(w)
        if count(" ".join(cur)) > max_tokens:
            cur.pop()
            out.append(" ".join(cur))
            cur = [w]
    if cur:
        out.append(" ".join(cur))
    return out


def _split_table(table_md: str, max_tokens: int, count: TokenCounter) -> list[str]:
    lines = [ln for ln in table_md.splitlines() if ln.strip()]
    # Markdown table header = first row (+ separator row if present)
    n_header = 2 if len(lines) > 1 and re.fullmatch(r"\|?[\s:\-|]+\|?", lines[1]) else 1
    header, rows = lines[:n_header], lines[n_header:]
    if count(table_md) <= max_tokens or not rows:
        return [table_md]
    parts, cur = [], []
    for row in rows:
        if cur and count("\n".join(header + cur + [row])) > max_tokens:
            parts.append("\n".join(header + cur))
            cur = []
        cur.append(row)
    if cur:
        parts.append("\n".join(header + cur))
    return parts


class _Builder:
    def __init__(self, chunk_size: int, chunk_max: int, overlap: int, count: TokenCounter):
        self.size, self.max, self.overlap, self.count = chunk_size, chunk_max, overlap, count
        self.chunks: list[Chunk] = []
        self._per_page: dict[tuple[str, int], int] = {}

    def emit(self, els: list[Element], text: str, kind: str) -> None:
        text = text.strip()
        if not text:
            return
        first = els[0]
        page_start = min(e.page for e in els)
        key = (first.doc_id, page_start)
        idx = self._per_page.get(key, 0)
        self._per_page[key] = idx + 1
        prefix = doc_title(first.fiscal_year)
        if first.section_path:
            prefix += " > " + " > ".join(first.section_path)
        self.chunks.append(
            Chunk(
                chunk_id=f"{first.doc_id}-p{page_start:03d}-c{idx:02d}",
                doc_id=first.doc_id,
                fiscal_year=first.fiscal_year,
                page_start=page_start,
                page_end=max(e.page for e in els),
                section_path=first.section_path,
                chunk_type=kind,  # type: ignore[arg-type]
                text=text,
                embed_text=f"{prefix}\n{text}",
                n_tokens=self.count(text),
            )
        )

    def add_section(self, els: list[Element]) -> None:
        """Pack the text elements of one section; tables are emitted as their own chunks."""
        buf: list[tuple[str, Element]] = []  # (sentence, source element)
        fresh = False  # buf holds text not yet emitted in any chunk

        def flush(keep_overlap: bool) -> None:
            nonlocal buf, fresh
            if buf and fresh:
                self.emit([e for _, e in buf], " ".join(s for s, _ in buf), "text")
            fresh = False
            tail: list[tuple[str, Element]] = []
            if keep_overlap:
                for item in reversed(buf):
                    if self.count(" ".join(s for s, _ in [item, *tail])) > self.overlap:
                        break
                    tail.insert(0, item)
            buf = tail

        for el in els:
            if el.type == "table":
                flush(keep_overlap=False)
                for part in _split_table(el.text, self.max, self.count):
                    self.emit([el], part, "table")
                continue
            for sent in split_sentences(el.text):
                pieces = [sent] if self.count(sent) <= self.max else _hard_split(sent, self.size, self.count)
                for piece in pieces:
                    buf.append((piece, el))
                    fresh = True
                    if self.count(" ".join(s for s, _ in buf)) >= self.size:
                        flush(keep_overlap=True)
        flush(keep_overlap=False)


def chunk_elements(
    elements: Iterable[Element],
    count_tokens: TokenCounter,
    chunk_size: int = 400,
    chunk_max: int = 500,
    overlap: int = 60,
) -> list[Chunk]:
    builder = _Builder(chunk_size, chunk_max, overlap, count_tokens)
    section: list[Element] = []
    current_key: tuple | None = None
    for el in elements:
        key = (el.doc_id, tuple(el.section_path))
        if current_key is not None and key != current_key:
            builder.add_section(section)
            section = []
        current_key = key
        section.append(el)
    if section:
        builder.add_section(section)
    return builder.chunks
