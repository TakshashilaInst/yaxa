"""Cohort life, step 2: announcements from the programme office.

Staff post a notice to a cohort (or one track of it). It shows at the top of
each learner's home page until seen, stays in a list, and goes out as one email
to the cohort's group address (never to individual learners). An announcement
that has been emailed is never emailed again.

Stored in ``<data>/yaxa/announcements/<COHORT>.json``.
"""

from __future__ import annotations

import os
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from . import community, mailer, schedule, store

router = APIRouter()

MAX_BODY = 4000
SITE = os.environ.get("YAXA_SITE_URL", "https://yaxa-deeptutor.takshashila.org.in")


class NewAnnouncement(BaseModel):
    cohort: str
    title: str
    body: str
    track: str | None = None
    session: str | None = None


def _path(cohort: str):
    return community.root("announcements", f"{cohort}.json")


def _all(cohort: str) -> list[dict]:
    return store._read_json(_path(cohort)) or []


def session_module(programme: str, code: str | None) -> str | None:
    if not code:
        return None
    for mcode, sessions in schedule._session_codes(programme).items():
        if any(s["code"] == code for s in sessions):
            return mcode
    return None


def _group(c: schedule.Cohort, track: str | None) -> str:
    return (c.track_email_groups.get(track, "") if track else "") or c.email_group


def _email_text(item: dict) -> tuple[str, str]:
    subject = f"[{item['cohort']}] {item['title']}"
    text = f"{item['body']}\n\n— {item['author']}\n\nSee it in Yaxa: {SITE}/learn/announcements\n"
    return subject, text


def _try_email(c: schedule.Cohort, item: dict) -> dict[str, Any]:
    """Send if possible; returns {email: sent|not_configured|no_group|failed, mailto?}."""
    to = _group(c, item.get("track"))
    subject, text = _email_text(item)
    mailto = f"mailto:{to}?subject={quote(subject)}&body={quote(text)}" if to else ""
    if not to:
        return {"email": "no_group", "mailto": mailto}
    if not mailer.configured():
        return {"email": "not_configured", "mailto": mailto}
    try:
        mailer.send(to, subject, text)
    except Exception:  # noqa: BLE001 - surfaced to staff as "failed"; they can retry
        return {"email": "failed", "mailto": mailto}
    return {"email": "sent", "to": to}


def _mark_emailed(cohort: str, aid: str, to: str) -> dict:
    def fn(items):
        for i in items or []:
            if i["id"] == aid:
                i["emailed_at"] = community.now_iso()
                i["email_to"] = to
        return items

    items = community.update_json(_path(cohort), fn)
    return next(i for i in items if i["id"] == aid)


def _staff_viewer(cohort: str | None) -> community.Viewer:
    v = community.viewer(cohort)
    if not v.staff:
        raise HTTPException(403, "Faculty and staff only")
    return v


@router.post("/announcements")
async def create(body: NewAnnouncement) -> dict:
    v = _staff_viewer(body.cohort)
    c = v.require_cohort()
    item = {
        "id": community.new_id(),
        "cohort": c.code,
        "title": community.clean_text(body.title, 200, "title"),
        "body": community.clean_text(body.body, MAX_BODY, "message"),
        "track": body.track or None,
        "session": body.session or None,
        "module": session_module(c.programme, body.session),
        "author": v.name,
        "created_at": community.now_iso(),
        "emailed_at": "",
        "email_to": "",
        "hidden": False,
    }
    community.update_json(_path(c.code), lambda items: (items or []) + [item])
    result = _try_email(c, item)
    if result["email"] == "sent":
        item = _mark_emailed(c.code, item["id"], result["to"])
    return {"item": item, **result}


@router.get("/announcements")
async def listing(cohort: str | None = None) -> dict:
    v = community.viewer(cohort)
    if not v.cohort:
        return {"cohort": None, "items": [], "unread": 0}
    items = [i for i in _all(v.cohort.code) if not i.get("hidden")]
    if not v.staff:
        items = [i for i in items if not i.get("track") or i["track"] == v.track]
    items.sort(key=lambda i: i["created_at"], reverse=True)
    seen = v.user.seen.get(v.cohort.code, "")
    return {"cohort": v.cohort.code, "items": items, "unread": sum(1 for i in items if i["created_at"] > seen)}


@router.post("/announcements/seen")
async def mark_seen() -> dict:
    v = community.viewer(None)
    if v.cohort:
        user = store.load_user(v.uid)
        user.seen[v.cohort.code] = community.now_iso()
        store.save_user(user)
    return {"ok": True}


def _find(cohort: str, aid: str) -> dict:
    item = next((i for i in _all(cohort) if i["id"] == aid), None)
    if not item:
        raise HTTPException(404, "No such announcement")
    return item


@router.post("/announcements/{cohort}/{aid}/email")
async def email_again(cohort: str, aid: str) -> dict:
    v = _staff_viewer(cohort)
    c = v.require_cohort()
    item = _find(c.code, aid)
    if item.get("emailed_at"):
        raise HTTPException(409, "This announcement has already been emailed")
    result = _try_email(c, item)
    if result["email"] == "sent":
        item = _mark_emailed(c.code, aid, result["to"])
    return {"item": item, **result}


@router.delete("/announcements/{cohort}/{aid}")
async def hide(cohort: str, aid: str) -> dict:
    v = _staff_viewer(cohort)
    c = v.require_cohort()
    _find(c.code, aid)

    def fn(items):
        for i in items:
            if i["id"] == aid:
                i["hidden"] = True
        return items

    community.update_json(_path(c.code), fn)
    return {"ok": True}
