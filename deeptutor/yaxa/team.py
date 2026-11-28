"""The faculty team: who teaches each module, and which Yaxa login belongs to which faculty member.

The roster (module -> faculty names, main faculty first) starts from ``content/teaching.yaml``
and lives in ``<data>/yaxa/team.json`` after the first edit. Linking a login to a name makes
that login faculty; unlinking returns it to a student. Faculty can read the team; only
admins change it. Module pages show the roster; faculty tools default to the modules a
faculty member teaches.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from . import store
from .access import _me, _privileged
from .catalog import _read_yaml, get_catalog

router = APIRouter()
MAX_NAMES = 12


class Names(BaseModel):
    faculty: list[str]


class Link(BaseModel):
    name: str = ""  # empty unlinks


def _path():
    return store.yaxa_root() / "team.json"


def roster() -> dict[str, list[str]]:
    saved = store._read_json(_path())
    raw = saved if isinstance(saved, dict) else _read_yaml("teaching.yaml")
    return {str(k): [str(n) for n in (v or [])] for k, v in (raw or {}).items()}


def faculty_for(module: str) -> list[str]:
    return roster().get(module, [])


def teaches(user: store.YaxaUser) -> list[str]:
    """Module codes this login teaches (by its linked faculty name)."""
    if user.role != "faculty" or not user.faculty_name:
        return []
    return [code for code, names in roster().items() if user.faculty_name in names]


def _clean(names: list[str]) -> list[str]:
    out: list[str] = []
    for n in names:
        n = " ".join(str(n).split())[:80]
        if n and n not in out:
            out.append(n)
    return out[:MAX_NAMES]


def _staff() -> tuple[Any, store.YaxaUser]:
    cu, user = _me()
    if not _privileged(cu, user):
        raise HTTPException(403, "Faculty and staff only")
    return cu, user


def _admin() -> None:
    cu, _ = _me()
    if not cu.is_admin:
        raise HTTPException(403, "Only an admin can change the faculty team")


@router.get("/team")
async def get_team() -> dict[str, Any]:
    _staff()
    r = roster()
    cat = get_catalog()
    modules = [{"code": code, "title": m.title, "faculty": r.get(code, [])} for code, m in cat.modules.items()]
    accounts = [{"user_id": u.user_id, "display_name": u.display_name or u.user_id, "faculty_name": u.faculty_name,
                 "faculty": u.role == "faculty"} for u in store.list_users() if not u.demo]
    names = sorted({n for v in r.values() for n in v})
    return {"modules": modules, "accounts": accounts, "names": names}


@router.put("/team/modules/{code}")
async def set_module(code: str, body: Names) -> dict[str, Any]:
    _admin()
    if code not in get_catalog().modules:
        raise HTTPException(404, "Unknown module")
    r = roster()
    r[code] = _clean(body.faculty)
    store._write_json(_path(), r)
    return {"code": code, "faculty": r[code]}


@router.put("/team/accounts/{user_id}")
async def set_account(user_id: str, body: Link) -> dict[str, Any]:
    _admin()
    if not any(u.user_id == user_id for u in store.list_users()):
        raise HTTPException(404, "No such login")
    u = store.load_user(user_id)
    name = " ".join(body.name.split())[:80]
    u.faculty_name = name
    u.role = "faculty" if name else "student"
    store.save_user(u)
    return {"user_id": user_id, "faculty_name": name, "faculty": bool(name), "teaches": teaches(u)}
