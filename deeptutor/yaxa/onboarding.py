"""Bulk onboarding (admins): a CSV with the header ``name,email,role,track,cohort``.

For each row: the login (username = email) is created if it doesn't exist, with a new random
password; the person's name is set; students are put in their cohort and track; faculty are
marked faculty and matched to the teaching roster by name. Rows that fail are reported and
skipped. New passwords are returned once, as a CSV for the admin to download, and are never
stored or logged by Yaxa; optionally each new person is emailed their login instead.
"""

from __future__ import annotations

import csv
import io
import re
import secrets
from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile

from . import mailer, store
from .access import _me
from .announcements import SITE
from .catalog import get_catalog
from .schedule import load_cohort

router = APIRouter()
HEADER = ["name", "email", "role", "track", "cohort"]
MAX_BYTES, MAX_ROWS = 1_000_000, 1000
EMAIL = re.compile(r"^[^@\s,]+@[^@\s,]+\.[^@\s,]+$")


def _existing_logins() -> dict[str, str]:
    from deeptutor.services.auth import list_users

    return {str(u.get("username")): str(u.get("id")) for u in list_users()}


def _create_login(email: str, password: str) -> str:
    from deeptutor.api.routers.auth import AdminCreateUserRequest, _create_admin_user

    return str(_create_admin_user(AdminCreateUserRequest(username=email, password=password, preset="standard"), None)["user_id"])


def _welcome(name: str, email: str, password: str) -> tuple[str, str]:
    return ("Your Yaxa login (Takshashila)",
            f"Hello {name},\n\nYou now have a Yaxa login for your Takshashila course.\n\n"
            f"Sign in at {SITE}/login\nEmail: {email}\nPassword: {password}\n\n"
            f"New to Yaxa? {SITE}/learn/how-it-works\n\n— Takshashila\n")


@router.post("/onboard")
async def onboard(file: UploadFile = File(...), email_logins: bool = False) -> dict[str, Any]:
    cu, _ = _me()
    if not cu.is_admin:
        raise HTTPException(403, "Only an admin can add people in bulk")
    raw = await file.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise HTTPException(413, "The file is over 1 MB")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(400, "Save the sheet as a UTF-8 CSV") from None
    reader = csv.DictReader(io.StringIO(text, newline=""))
    if [str(h or "").strip().lower() for h in reader.fieldnames or []] != HEADER:
        raise HTTPException(422, "The first row must be exactly: name,email,role,track,cohort")
    reader.fieldnames = HEADER
    rows = list(reader)
    if len(rows) > MAX_ROWS:
        raise HTTPException(413, f"At most {MAX_ROWS} people at a time")
    if email_logins and not mailer.configured():
        raise HTTPException(409, "Email isn't set up on the server, so logins can't be emailed. Download them instead.")

    logins = _existing_logins()
    cat = get_catalog()
    out, new = [], []
    for i, r in enumerate(rows, start=2):
        name = " ".join(str(r.get("name") or "").split())[:80]
        email = str(r.get("email") or "").strip().lower()
        role = str(r.get("role") or "student").strip().lower() or "student"
        track = str(r.get("track") or "").strip().upper() or None
        cohort = str(r.get("cohort") or "").strip().upper()
        res: dict[str, Any] = {"row": i, "email": email, "name": name, "ok": False}
        out.append(res)
        if not name or not EMAIL.match(email):
            res["error"] = "Needs a name and a valid email"
            continue
        if role not in ("student", "faculty"):
            res["error"] = "Role is student or faculty"
            continue
        c = None
        if role == "student":
            try:
                c = load_cohort(cohort) if cohort else None
            except ValueError:
                c = None
            if not c:
                res["error"] = f"No cohort {cohort or '(blank)'}"
                continue
            prog = cat.programme(c.programme)
            if prog and prog.tracks and not prog.track(track):
                res["error"] = f"{c.programme} has no track {track or '(blank)'}"
                continue
        uid = logins.get(email)
        password = ""
        if not uid:
            password = secrets.token_urlsafe(12)
            try:
                uid = _create_login(email, password)
            except HTTPException as exc:
                res["error"] = str(exc.detail)
                continue
            logins[email] = uid
            new.append((name, email, password))
        u = store.load_user(uid, display_name=name)
        u.display_name = name
        if role == "faculty":
            u.role, u.faculty_name = "faculty", name
        elif c:
            u.enrolments = [e for e in u.enrolments if e.programme != c.programme]
            u.enrolments.append(store.Enrolment(programme=c.programme, track=track, cohort=c.code))
        store.save_user(u)
        res |= {"ok": True, "user_id": uid, "created": bool(password)}

    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["name", "email", "password"])
    w.writerows(new)
    emailed = 0
    if email_logins:
        for name, email, password in new:
            subject, body = _welcome(name, email, password)
            try:
                mailer.send(email, subject, body)
                emailed += 1
            except Exception:  # noqa: BLE001 - reported as a count; the admin still has the file
                pass
    return {"rows": out, "created": len(new), "emailed": emailed, "logins_csv": buf.getvalue() if new else ""}
