"""What's new for a learner since their last visit: messages in their cohort chat, replies and
faculty reviews on discussion questions they asked, and announcements they haven't opened.

Counts only, for a line on Home ("3 new messages in the cohort chat"). Last visits live in the
user's ``seen`` map, next to the announcements one: ``chat:<COHORT>`` and ``discussion:<COHORT>``.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from . import chat, community, store
from .catalog import get_catalog

router = APIRouter()

AREAS = ("chat", "discussion")


class Seen(BaseModel):
    area: str


def _module_for(session: str, v: community.Viewer) -> str | None:
    """The module a session belongs to, preferring the learner's own programme."""
    cat = get_catalog()
    for m in cat.modules.values():
        if any(u.id == session for u in m.units):
            return m.code
    return None


def _chat_count(v: community.Viewer, since: str) -> int:
    n = 0
    for ch in chat._channels(v):
        for m in community.read_jsonl(chat._path(ch["id"])):
            if not m.get("hidden") and m.get("author_id") != v.uid and m.get("created_at", "") > since:
                n += 1
    return n


def _discussion(v: community.Viewer, cohort: str, since: str) -> tuple[int, list[dict]]:
    n, where = 0, []
    folder = community.root("discussion", cohort)
    for path in sorted(folder.glob("*.json")) if folder.exists() else []:
        here = 0
        for t in store._read_json(path) or []:
            if t.get("author_id") != v.uid or t.get("hidden"):
                continue
            here += sum(1 for r in t.get("replies", [])
                        if not r.get("hidden") and r.get("author_id") != v.uid and r.get("created_at", "") > since)
            if (t.get("review") or {}).get("at", "") > since:
                here += 1
        if here:
            n += here
            where.append({"module": _module_for(path.stem, v), "session": path.stem})
    return n, where


@router.get("/whats-new")
async def whats_new() -> dict:
    v = community.viewer(None)
    if not v.cohort:
        return {"cohort": None, "chat": 0, "discussion": 0, "discussion_where": [], "announcements": 0}
    code, seen = v.cohort.code, v.user.seen
    disc, where = _discussion(v, code, seen.get(f"discussion:{code}", ""))
    from .announcements import _all  # late: announcements imports a lot

    ann_seen = seen.get(code, "")
    anns = [i for i in _all(code) if not i.get("hidden") and (v.staff or not i.get("track") or i["track"] == v.track)]
    return {
        "cohort": code,
        "chat": _chat_count(v, seen.get(f"chat:{code}", "")),
        "discussion": disc,
        "discussion_where": where,
        "announcements": sum(1 for i in anns if i["created_at"] > ann_seen),
    }


@router.post("/whats-new/seen")
async def mark_seen(body: Seen) -> dict:
    if body.area not in AREAS:
        raise HTTPException(400, "Unknown area")
    v = community.viewer(None)
    if v.cohort:
        user = store.load_user(v.uid)
        user.seen[f"{body.area}:{v.cohort.code}"] = community.now_iso()
        store.save_user(user)
    return {"ok": True}
