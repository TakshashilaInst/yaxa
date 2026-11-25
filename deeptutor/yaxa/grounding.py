"""Retrieve course passages and work out where each one lives (file + PDF page).

DeepTutor indexes a PDF as one document, so its passages carry no page number.
Rather than re-index, ``locate_page`` finds the passage inside the PDF text
with PyMuPDF. If it can't place a passage confidently it returns None:
showing no page is better than showing a wrong one.
"""

from __future__ import annotations

import asyncio
from functools import lru_cache
import hashlib
import json
import logging
from pathlib import Path
import re
from typing import Any

from deeptutor.multi_user.knowledge_access import admin_kb_base_dir
from deeptutor.services.rag.service import RAGService

from . import authors
from .catalog import source_info
from .store import yaxa_root

logger = logging.getLogger(__name__)

_WORD = re.compile(r"[a-z0-9]+")
_TIMESTAMP = re.compile(r"\[(\d{2}:\d{2}:\d{2})\]")
_YOUTUBE = re.compile(r"https?://(?:www\.)?(?:youtube\.com/watch\?v=|youtu\.be/)[A-Za-z0-9_-]{11}")


def _words(text: str) -> list[str]:
    return _WORD.findall(text.lower())


# ------------------------------------------------------------------ files
def kb_raw_path(kb: str, file_name: str) -> Path | None:
    """Absolute path of a KB's raw file, refusing anything outside raw/."""
    raw_dir = (admin_kb_base_dir() / kb / "raw").resolve()
    target = (raw_dir / file_name).resolve()
    if raw_dir not in target.parents or not target.is_file():
        return None
    return target


# ------------------------------------------------------------- page finding
@lru_cache(maxsize=32)
def _page_texts(pdf_path: str, mtime: float) -> tuple[str, ...]:
    """Each page's text as a normalised word string (cached per file version)."""
    import pymupdf

    with pymupdf.open(pdf_path) as doc:
        return tuple(" ".join(_words(page.get_text())) for page in doc)


def _cache_file(pdf: Path) -> Path:
    key = hashlib.sha1(str(pdf).encode()).hexdigest()[:16]
    return yaxa_root() / "cache" / "pages" / f"{key}.json"


def locate_page(pdf: Path, passage: str) -> int | None:
    """1-based page number where `passage` appears in `pdf`, or None."""
    words = _words(passage)
    if len(words) < 6:
        return None
    digest = hashlib.sha1(" ".join(words).encode()).hexdigest()[:16]
    cache_path = _cache_file(pdf)
    try:
        cache = json.loads(cache_path.read_text())
    except (FileNotFoundError, ValueError):
        cache = {}
    if digest in cache:
        return cache[digest]

    try:
        pages = _page_texts(str(pdf), pdf.stat().st_mtime)
    except Exception:  # unreadable or scanned PDF
        logger.info("yaxa: cannot read pages of %s", pdf.name, exc_info=True)
        return None

    page: int | None = None
    # 1) exact runs of 10 words from the start, middle and end of the passage
    n = len(words)
    for start in {0, max(0, n // 2 - 5), max(0, n - 10)}:
        probe = " ".join(words[start : start + 10])
        hits = [i for i, text in enumerate(pages) if probe in text]
        if len(hits) == 1:
            page = hits[0] + 1
            break
    # 2) otherwise the page sharing most of the passage's distinctive words
    if page is None:
        distinct = {w for w in words if len(w) > 4}
        if len(distinct) >= 8:
            scores = [
                (len(distinct & set(text.split())) / len(distinct), i)
                for i, text in enumerate(pages)
            ]
            best, idx = max(scores, default=(0.0, 0))
            if best >= 0.6:
                page = idx + 1

    cache[digest] = page
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(cache))
    return page


# ---------------------------------------------------------------- retrieval
_COURSE_FILE = re.compile(r"^[A-Z]+\d+\s*LU\s*(\d+)\s*-\s*(?:RR|AR|R)?\d*\s*-\s*(.+)$", re.I)
MAX_PER_FILE = 2  # keep one long file (e.g. the course outline) from crowding out readings


def _title_from_file(name: str) -> tuple[str, str]:
    """Readable title (and unit label) from names like 'GCPP102LU06 - RR01 - Key-Concepts.pdf'."""
    stem = Path(name).stem
    unit = ""
    m = _COURSE_FILE.match(stem)
    if m:
        unit, stem = f"LU{int(m.group(1)):02d}", m.group(2)
    stem = re.sub(r"\s*\(\d+\)$", "", stem)  # "... (1)" download duplicates
    if " " not in stem:
        stem = stem.replace("-", " ")
    return re.sub(r"[_]+", " ", stem).strip(), unit


async def retrieve(kb: str, query: str, top_k: int, *, corpus: str = "") -> list[dict[str, Any]]:
    """Top passages from one admin KB, as dicts ready for the grounding margin."""
    service = RAGService(kb_base_dir=str(admin_kb_base_dir()))
    try:
        # Ask for extra so the per-file cap still leaves `top_k` passages.
        result = await service.search(query=query, kb_name=kb, top_k=top_k + 4)
    except Exception:
        logger.warning("yaxa: search failed for kb=%s", kb, exc_info=True)
        return []
    if result.get("needs_reindex") or result.get("error_type"):
        logger.warning("yaxa: kb %s not searchable: %s", kb, result.get("answer"))
        return []

    passages: list[dict[str, Any]] = []
    per_file: dict[str, int] = {}
    for src in result.get("sources") or []:
        text = src.get("text") or src.get("content") or ""
        if len(text.strip()) < 80:
            continue  # fragments too short to ground anything
        file_name = Path(str(src.get("source") or src.get("title") or "")).name
        info = source_info(kb, file_name)
        if info.retired:
            continue  # removed from the library; DeepTutor can't drop one document from an index
        per_file[file_name] = per_file.get(file_name, 0) + 1
        if per_file[file_name] > MAX_PER_FILE:
            continue
        title, unit = _title_from_file(file_name)
        # Multi-author files (newsletter editions): credit the article the passage sits in.
        raw = kb_raw_path(kb, file_name) if file_name.lower().endswith((".md", ".txt")) else None
        section_author = authors.author_in_file(raw, text) if raw else None
        passage = {
            "kb": kb,
            "file": file_name,
            "title": info.title or title,
            "unit": unit,
            "corpus": info.corpus or corpus or kb,
            "byline": authors.byline(section_author) if section_author else info.byline,
            "kind": info.kind,
            "url": info.url,
            "page": None,
            "text": text,
            "score": src.get("score"),
            "videos": sorted(set(_YOUTUBE.findall(text)))[:3],
            # webinar transcripts carry [hh:mm:ss] marks; show where the passage starts
            "timestamp": (m.group(1) if (m := _TIMESTAMP.search(text)) else None),
        }
        if file_name.lower().endswith(".pdf") and info.kind == "pdf":
            pdf = kb_raw_path(kb, file_name)
            if pdf:
                passage["page"] = await asyncio.to_thread(locate_page, pdf, text)
                passage["url"] = f"/api/yaxa/files/{kb}/{file_name}"
        passages.append(passage)
    return passages[:top_k]


async def retrieve_across(kbs: list[str], query: str, top_k: int) -> list[dict[str, Any]]:
    """The best `top_k` passages from several libraries, merged by similarity score.

    All libraries share one embedding model, so their cosine scores compare.
    A library that fails to search is skipped; passages without a score sort last.
    """
    per_kb = max(3, top_k // 2)
    results = await asyncio.gather(*(retrieve(kb, query, per_kb) for kb in kbs), return_exceptions=True)
    merged: list[dict[str, Any]] = []
    for kb, group in zip(kbs, results):
        if isinstance(group, BaseException):
            logger.warning("yaxa: programme search skipped kb=%s: %s", kb, group)
            continue
        merged += group

    def score(p: dict[str, Any]) -> float:
        s = p.get("score")
        return float(s) if isinstance(s, (int, float)) else -1.0

    merged.sort(key=score, reverse=True)  # stable: equal scores keep library order
    return merged[:top_k]
