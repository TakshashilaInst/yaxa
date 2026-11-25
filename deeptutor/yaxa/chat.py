"""Cohort life, step 4: a light chat for each cohort, and one for each track.

Channels are the cohort (``GCPP45``) and its tracks (``GCPP45.DFA``). A learner
sees their cohort's channel and their own track's; staff see all of a cohort's.
No direct messages, no attachments. Learners can edit or delete their own
message for 15 minutes; staff can hide any. When the cohort closes, its chat
becomes read-only. Stored in ``<data>/yaxa/chat/<CHANNEL>.jsonl``; never indexed.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from . import community
from .catalog import get_catalog

router = APIRouter()

MAX_TEXT = 2000
PER_HOUR = 30
PAGE = 200


class Text(BaseModel):
    text: str


def _path(channel: str):
    return community.root("chat", f"{channel}.jsonl")


def _tracks(programme: str) -> list[tuple[str, str]]:
    prog = get_catalog().programme(programme)
    return [(t.code, t.name) for t in prog.tracks] if prog else []


def _channels(v: community.Viewer) -> list[dict]:
    c = v.cohort
    if not c:
        return []
    out = [{"id": c.code, "name": f"{c.code} · everyone"}]
    for code, name in _tracks(c.programme):
        if v.staff or v.track == code:
            out.append({"id": f"{c.code}.{code}", "name": f"{name}"})
    return out


def _open(channel: str, cohort: str | None, *, write: bool = False) -> community.Viewer:
    # learners always get their own cohort; staff get the one the channel belongs to
    v = community.viewer(cohort or channel.split(".")[0])
    if channel not in {c["id"] for c in _channels(v)}:
        raise HTTPException(403, "You can't see this chat")
    if write and v.cohort and v.cohort.closed:
        raise HTTPException(403, f"{v.cohort.code} is closed; its chat is read-only")
    return v


def _view(m: dict, v: community.Viewer) -> dict:
    return {k: m.get(k) for k in ("id", "author", "staff", "text", "created_at", "edited")} | {"mine": m["author_id"] == v.uid}


@router.get("/chat/channels")
async def channels(cohort: str | None = None) -> list[dict]:
    return _channels(community.viewer(cohort))


@router.get("/chat/{channel}")
async def messages(channel: str, after: str = "", cohort: str | None = None) -> dict:
    v = _open(channel, cohort)
    rows = [m for m in community.read_jsonl(_path(channel)) if not m.get("hidden")]
    if after:
        idx = next((i for i, m in enumerate(rows) if m["id"] == after), None)
        rows = rows[idx + 1:] if idx is not None else rows
    return {"messages": [_view(m, v) for m in rows[-PAGE:]], "closed": bool(v.cohort and v.cohort.closed), "me": v.uid}


@router.post("/chat/{channel}")
async def post(channel: str, body: Text, cohort: str | None = None) -> dict:
    v = _open(channel, cohort, write=True)
    text = community.clean_text(body.text, MAX_TEXT)
    if not community.rate_ok(v.uid, "chat", PER_HOUR):
        raise HTTPException(429, "You've sent a lot of messages this hour. Try again a little later.")
    row = {"id": community.new_id(), "author_id": v.uid, "author": v.name, "staff": v.staff, "text": text,
           "created_at": community.now_iso(), "edited": False, "hidden": False}
    community.append_jsonl(_path(channel), row)
    return _view(row, v)


def _change(channel: str, mid: str, v: community.Viewer, fn) -> dict:
    found: dict = {}

    def apply(rows):
        for m in rows:
            if m["id"] == mid and not m.get("hidden"):
                if not v.staff:
                    if m["author_id"] != v.uid:
                        raise HTTPException(403, "You can only change your own message")
                    if community.age_seconds(m["created_at"]) > community.EDIT_WINDOW:
                        raise HTTPException(403, "Messages can be changed only in the first 15 minutes")
                fn(m)
                found["m"] = m
        return rows

    community.rewrite_jsonl(_path(channel), apply)
    if not found:
        raise HTTPException(404, "No such message")
    return found["m"]


@router.patch("/chat/{channel}/{mid}")
async def edit(channel: str, mid: str, body: Text, cohort: str | None = None) -> dict:
    v = _open(channel, cohort, write=True)
    text = community.clean_text(body.text, MAX_TEXT)
    return _view(_change(channel, mid, v, lambda m: m.update(text=text, edited=True)), v)


@router.delete("/chat/{channel}/{mid}")
async def remove(channel: str, mid: str, cohort: str | None = None) -> dict:
    v = _open(channel, cohort)
    _change(channel, mid, v, lambda m: m.update(hidden=True))
    return {"ok": True}
