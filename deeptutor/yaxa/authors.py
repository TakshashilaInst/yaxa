"""Who wrote which part of a multi-author file.

Newsletter editions such as Anticipating the Unintended hold several articles,
each opened by an author line under its title:

    India Policy Watch #1: The Truth Is Not Out There
    Insights on burning policy issues in India
    - RSJ

The search index cuts an edition into passages, and a passage from the middle
of an article no longer contains that line. `author_at` finds where a passage
sits in the raw file and returns the nearest author line above it, so each
passage can be credited to its real author without re-indexing.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
import re

# One name: "RSJ" or two to four capitalised words ("Sridhar Krishna").
_NAME = r"(?:RSJ|[A-Z][a-zA-Z.']+(?: [A-Z][a-zA-Z.']+){1,3})"
_AUTHOR_LINE = re.compile(rf"^\s*(?:—|–|--|-)\s*({_NAME}(?:\s*(?:&|and|,)\s*{_NAME})*)\s*$")
_DASH_ITEM = re.compile(r"^\s*(?:—|–|--|-)\s")
_QUOTE_START = ("…", "...", '"', "“", "‘", "'")
_SPLIT = re.compile(r"\s*(?:&|\band\b|,)\s*")

# Spellings that name the same person.
ALIASES = {
    "Raghu Sanjaylal Jaitley": "RSJ",
    "Pranay Kotashane": "Pranay Kotasthane",
}


def _norm_names(raw: str) -> str:
    names: list[str] = []
    for part in _SPLIT.split(raw.strip()):
        name = ALIASES.get(part.strip(), part.strip())
        if name and name not in names:
            names.append(name)
    return " & ".join(names)


def _is_author_line(lines: list[str], i: int) -> str | None:
    """The normalised author if lines[i] is an article's author line, else None.

    Skips list items (a dash line next to other dash lines) and quote
    attributions (a dash line right after a quotation).
    """
    m = _AUTHOR_LINE.match(lines[i])
    if not m:
        return None
    prev = next((x for x in reversed(lines[:i]) if x.strip()), "")
    nxt = next((x for x in lines[i + 1 :] if x.strip()), "")
    if _DASH_ITEM.match(prev) or _DASH_ITEM.match(nxt):
        return None
    p = prev.strip()
    if p.startswith(_QUOTE_START) or p.endswith(("”", '"')):
        return None
    return _norm_names(m.group(1))


def _flat(text: str) -> str:
    return " ".join(text.split())


def _index(text: str) -> tuple[str, list[tuple[int, str]]]:
    """The file as one whitespace-normalised string, and (offset, author) for each section start."""
    lines = text.splitlines()
    flat_parts: list[str] = []
    sections: list[tuple[int, str]] = []
    pos = 0
    for i, line in enumerate(lines):
        author = _is_author_line(lines, i)
        if author:
            sections.append((pos, author))
        words = _flat(line)
        if words:
            flat_parts.append(words)
            pos += len(words) + 1
    return " ".join(flat_parts), sections


def parse_sections(text: str) -> list[tuple[int, str]]:
    """(offset, author) for each article that opens with an author line, in file order."""
    return _index(text)[1]


def _find(flat: str, chunk: str) -> int:
    """Where the chunk sits in the flattened file, or -1. Tries a few probes in case its ends were trimmed."""
    c = _flat(chunk)
    if not c:
        return -1
    probes = [c[:60], c[len(c) // 2 : len(c) // 2 + 60], c[-60:]]
    for probe in probes:
        if len(probe) >= 20 and (at := flat.find(probe)) >= 0:
            return at
    return -1


def _author_for(flat: str, sections: tuple[tuple[int, str], ...] | list[tuple[int, str]], chunk: str) -> str | None:
    """The last section author that starts at or before where the chunk sits."""
    if not sections or (at := _find(flat, chunk)) < 0:
        return None
    author = None
    for start, name in sections:
        if start > at:
            break
        author = name
    return author


def author_at(text: str, chunk: str) -> str | None:
    """The author of the article that contains `chunk`, or None when not marked or not found."""
    flat, sections = _index(text)
    return _author_for(flat, sections, chunk)


@lru_cache(maxsize=256)
def _indexed_file(path: str, mtime: float) -> tuple[str, tuple[tuple[int, str], ...]]:
    flat, sections = _index(Path(path).read_text(encoding="utf-8", errors="replace"))
    return flat, tuple(sections)


def author_in_file(path: Path, chunk: str) -> str | None:
    """`author_at` for a file on disk, cached per file version. Text files only."""
    if path.suffix.lower() not in {".md", ".txt"}:
        return None
    try:
        flat, sections = _indexed_file(str(path), path.stat().st_mtime)
    except OSError:
        return None
    return _author_for(flat, sections, chunk)


def byline(author: str) -> str:
    """'by RSJ', or 'co-written by A & B' for joint articles."""
    return f"co-written by {author}" if " & " in author else f"by {author}"
