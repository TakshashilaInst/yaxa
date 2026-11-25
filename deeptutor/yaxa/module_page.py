"""Module page: one module's units, each with its readings, webinar transcripts and the student's progress.

Readings come from the module's library (the files Yaxa answers from), so the
reading list and the tutor always agree. Files open through /api/yaxa/files,
which only serves a student's own modules. Webinars open as transcripts; the
Drive recording link goes to staff only (Drive shares recordings with staff),
and every session links to its OpenTakshashila page, where students watch.
"""

from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter

from . import practice
from .access import _me, _require_module
from .catalog import Module, SourceInfo, Unit, _sources_for, get_catalog
from .grounding import _title_from_file, admin_kb_base_dir

router = APIRouter(prefix="/module")

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


# A session code at the start of a title, tag or file name: "CP10 reading", "Webinar: CP22 and CP23 ...", "CT3x - x.pdf".
_SESSION = re.compile(r"^(?:Webinar:\s*)?(C[A-Z])\s?-?(\d{1,2}[a-z]?)\b", re.I)


def session_code(*texts: str) -> str | None:
    """The first session code found, normalised (CP10, CT3x), or None."""
    for text in texts:
        if text and (m := _SESSION.match(text.strip())):
            return m.group(1).upper() + m.group(2).lower()
    return None


def _reading(kb: str, file_name: str, info: SourceInfo) -> dict[str, Any]:
    m = _LU_FILE.match(file_name.rsplit(".", 1)[0])
    title = info.title or (m.group(2).strip() if m else re.sub(r"^[A-Z]+\d+\s*-\s*", "", _title_from_file(file_name)[0]))
    own = f"/api/yaxa/files/{kb}/{file_name}"
    row: dict[str, Any] = {"title": title, "kind": info.kind or "pdf", "corpus": info.corpus, "byline": info.byline}
    if info.kind == "video":
        row["open"] = own  # the transcript
        if info.url:
            row["watch"] = info.url  # the recording, on Drive
    elif file_name.lower().endswith(".pdf") or not info.url:
        row["open"] = own
    else:
        row["open"] = info.url  # articles and op-eds: the published page
    return row


def _codes(unit: Unit) -> set[str]:
    return {c for c in [unit.id, *unit.aliases] if session_code(c)}


def group_readings(
    module: Module,
    files: dict[str, SourceInfo],
    *,
    shared_kb: bool,
    owners: dict[str, set[str]] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Readings and recordings by unit, plus "other" for the module's files not tied to one unit.

    A file goes to the unit whose session code (or an older alias) it carries,
    from its tag, title or file name. A file tagged to another module still
    comes here when that module has no session with the code (`owners` maps
    module -> its codes). Files without a usable code that belong to this
    module match a unit by title, or by an LU number in the file name, and
    otherwise are readings for the whole module.
    """
    owners = owners or {}
    groups: dict[str, list[dict[str, Any]]] = {u.id: [] for u in module.units}
    groups["other"] = []
    by_code = {c: u.id for u in module.units for c in _codes(u)}
    ids = {u.id for u in module.units}
    titles = [(u.id, _norm(u.title)) for u in module.units if u.title]
    kb = module.kb or ""

    for name, info in files.items():
        if info.retired:
            continue
        code = session_code(info.unit, info.title, name)
        mine = info.module == module.code or (not info.module and not shared_kb)
        unit = by_code.get(code or "")
        if unit and not mine and info.module and code in owners.get(info.module, set()):
            unit = None  # its own module has this session
        if not unit and not mine:
            continue
        if not unit and code and any(code in c for m, c in owners.items() if m != module.code):
            continue  # its session belongs to a sibling module, which lists it
        if not unit and info.unit in ids:
            unit = info.unit
        if not unit:
            t = _norm(info.title or name)
            unit = next((uid for uid, ut in titles if ut and ut in t), None)
        if not unit:  # a short webinar title inside the session's longer one: "Implementation Frameworks"
            core = _norm(re.sub(r"^Webinar:\s*", "", info.title or "").split(",")[0])
            if len(core) >= 12:
                unit = next((uid for uid, ut in titles if core in ut), None)
        if not unit and (m := _LU_FILE.match(name.rsplit(".", 1)[0])):
            lu = f"U{int(m.group(1)):02d}"
            unit = lu if lu in ids else None
        groups[unit or "other"].append(_reading(kb, name, info))
    for rows in groups.values():
        rows.sort(key=lambda r: (r["kind"] == "video", r["title"].lower()))  # readings first, then recordings
    return groups


def module_groups(cat: Any, module: Module) -> dict[str, list[dict[str, Any]]]:
    """The module's readings grouped by unit, from its library on disk."""
    siblings = [m for m in cat.modules.values() if m.kb and m.kb == module.kb]
    owners = {m.code: {c for u in m.units for c in _codes(u)} for m in siblings}  # modules sharing this library
    return group_readings(module, _files(module.kb) if module.kb else {}, shared_kb=len(siblings) > 1, owners=owners)


@router.get("/{code}")
async def module_view(code: str) -> dict[str, Any]:
    cu, user = _me()
    cat = get_catalog()
    module = _require_module(cat, cu, user, code)
    assert module is not None
    groups = module_groups(cat, module)
    if not (cu.is_admin or getattr(user, "role", "") == "faculty"):
        # Recordings on Drive are shared with staff only; students watch them on the LMS session page.
        for rows in groups.values():
            for r in rows:
                r.pop("watch", None)
    progress = {row["id"]: row for row in practice._progress(cu.id, module)}
    from . import schedule  # here, not at the top: schedule imports this module

    cohort = schedule.learner_cohort(user)
    dated = {s.code: s for s in cohort.sessions} if cohort else {}
    return {
        "code": module.code,
        "title": module.title,
        "description": module.description,
        "units": [
            {
                "id": u.id,
                "title": u.title,
                "outcomes": u.outcomes,
                "lms_url": u.lms_url,
                "session": {"starts_at": schedule.starts_at(dated[u.id]).isoformat(), "host": dated[u.id].host}
                if u.id in dated
                else None,
                "readings": groups.get(u.id, []),
                "progress": {k: progress[u.id][k] for k in ("status", "answered", "last_scores", "review")} if u.id in progress else None,
            }
            for u in module.units
        ],
        "other_readings": groups["other"],
    }
