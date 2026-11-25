"""Module page: one module's units, each with its readings, webinar transcripts and the student's progress.

Readings come from the module's library (the files Yaxa answers from), so the
reading list and the tutor always agree. Files open through /api/yaxa/files,
which only serves a student's own modules. Webinar recordings link to their
transcript, never to the staff-only Drive library.
"""

from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter

from . import practice
from .access import _me, _require_module
from .catalog import Module, SourceInfo, _sources_for, get_catalog
from .grounding import _title_from_file, admin_kb_base_dir

router = APIRouter(prefix="/module")

_CODE = re.compile(r"^[A-Z]{2}\d+[a-z]?$", re.I)  # session codes such as CT31, CP44, CT4x
# Course files named "GCPP173LU02 - RR01 Fiscal deficits.pdf": learning unit 2, reading RR01.
_LU_FILE = re.compile(r"^[A-Z]+\d*LU\s*(\d+)\s*-\s*(?:[A-Z]{1,3}\d+\s+)?(.+)$", re.I)


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def _files(kb: str) -> dict[str, SourceInfo]:
    """Every file in the library's raw folder, with its labels (if any)."""
    raw = admin_kb_base_dir() / kb / "raw"
    if not raw.is_dir():
        return {}
    labels = _sources_for(kb)
    return {p.name: labels.get(p.name, SourceInfo()) for p in sorted(raw.iterdir()) if p.is_file()}


def _reading(kb: str, file_name: str, info: SourceInfo) -> dict[str, Any]:
    m = _LU_FILE.match(file_name.rsplit(".", 1)[0])
    title = info.title or (m.group(2).strip() if m else re.sub(r"^[A-Z]+\d+\s*-\s*", "", _title_from_file(file_name)[0]))
    own = f"/api/yaxa/files/{kb}/{file_name}"
    if info.kind == "video":
        link = own  # the transcript; the recording itself sits in the staff-only Drive library
    elif file_name.lower().endswith(".pdf") or not info.url:
        link = own
    else:
        link = info.url  # articles and op-eds: the published page
    return {"title": title, "kind": info.kind or "pdf", "open": link, "corpus": info.corpus, "byline": info.byline}


def group_readings(module: Module, files: dict[str, SourceInfo], *, shared_kb: bool) -> dict[str, list[dict[str, Any]]]:
    """Readings by unit id, plus "other" for those not tied to a unit.

    A file belongs to a unit when its unit tag is the unit id, or its title
    names the unit, or (for libraries tagged by session code, e.g. CT31) its
    code's rank among the module's codes matches the unit's position.
    """
    groups: dict[str, list[dict[str, Any]]] = {u.id: [] for u in module.units}
    groups["other"] = []
    kb = module.kb or ""
    mine: list[tuple[str, SourceInfo]] = []
    for name, info in files.items():
        if info.retired:
            continue
        if info.module and info.module != module.code:
            continue
        if shared_kb and not info.module:
            continue  # a library shared by several modules: untagged files can't be placed
        mine.append((name, info))

    ids = {u.id for u in module.units}
    codes = sorted({i.unit for _, i in mine if i.unit and i.unit not in ids and _CODE.match(i.unit)})
    by_rank = dict(zip(codes, [u.id for u in module.units])) if len(codes) == len(module.units) else {}
    titles = [(u.id, _norm(u.title)) for u in module.units if u.title]

    for name, info in mine:
        unit = info.unit if info.unit in ids else None
        if not unit:
            t = _norm(info.title or name)
            unit = next((uid for uid, ut in titles if ut and ut in t), None)
        if not unit and info.unit in by_rank:
            unit = by_rank[info.unit]
        if not unit and (m := _LU_FILE.match(name.rsplit(".", 1)[0])):
            lu = f"U{int(m.group(1)):02d}"
            unit = lu if lu in ids else None
        groups[unit or "other"].append(_reading(kb, name, info))
    for rows in groups.values():
        rows.sort(key=lambda r: (r["kind"] == "video", r["title"].lower()))  # readings first, then recordings
    return groups


@router.get("/{code}")
async def module_view(code: str) -> dict[str, Any]:
    cu, user = _me()
    cat = get_catalog()
    module = _require_module(cat, cu, user, code)
    assert module is not None
    shared = sum(1 for m in cat.modules.values() if m.kb and m.kb == module.kb) > 1
    groups = group_readings(module, _files(module.kb) if module.kb else {}, shared_kb=shared)
    progress = {row["id"]: row for row in practice._progress(cu.id, module)}
    return {
        "code": module.code,
        "title": module.title,
        "description": module.description,
        "units": [
            {
                "id": u.id,
                "title": u.title,
                "outcomes": u.outcomes,
                "readings": groups.get(u.id, []),
                "progress": {k: progress[u.id][k] for k in ("status", "answered", "last_scores", "review")} if u.id in progress else None,
            }
            for u in module.units
        ],
        "other_readings": groups["other"],
    }
