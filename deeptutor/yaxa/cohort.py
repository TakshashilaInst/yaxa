"""Faculty cohort brief: what students asked about a module, where they struggled.

Faculty and admins only. Everything shown is anonymised: no names, no user
ids, and students' own names are scrubbed from the questions they typed
before anything reaches the model or the page.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import logging
import re
from typing import Any

from fastapi import APIRouter, HTTPException

from . import store
from .access import _me, _privileged, _short
from .catalog import get_catalog
from .llm import complete_text, resolve_for

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/cohort")

MAX_QUESTIONS_TO_MODEL = 120

BRIEF_PROMPT = """\
You brief Takshashila faculty on what their students asked Yaxa, the course's AI tutor, about one module.
You get the students' questions (anonymised), questions whose answers found no support in the course
material, and practice-question results by learning unit. Write for the faculty member teaching next week.

Markdown, under 350 words, with these sections:
## What students asked about
3 to 5 themes, most common first, each with a rough count and one representative question in quotes.
## Where they seem confused
Misconceptions or recurring difficulties you can see in the questions or the practice scores. Be specific.
## Questions the material didn't answer
Gaps worth covering in class or adding to the readings. Say "None this period" if there are none.
## Suggestions for the next class
2 or 3 concrete things to do in the next webinar.

Only use what is in the data. Never guess who asked what; never include names."""


# ------------------------------------------------------------- anonymising
def _staff_ids() -> set[str]:
    """User ids of admins and faculty: their own questions aren't cohort data."""
    from deeptutor.multi_user.identity import load_users

    ids = {str(r.get("id")) for r in (load_users() or {}).values() if r.get("role") == "admin"}
    ids |= {u.user_id for u in store.list_users() if u.role == "faculty"}
    return ids


def _name_scrubber() -> re.Pattern[str] | None:
    """Every student's display-name parts and login, as one case-insensitive pattern."""
    from deeptutor.multi_user.identity import load_users

    words: set[str] = set()
    for u in store.list_users():
        words |= {w for w in re.split(r"[\s._@-]+", u.display_name or "") if len(w) >= 3}
    for login in (load_users() or {}):
        words |= {w for w in re.split(r"[\s._@-]+", login.split("@")[0]) if len(w) >= 3 and not w.isdigit()}
    words -= {"demo", "student", "user", "admin"}
    if not words:
        return None
    return re.compile(r"\b(" + "|".join(re.escape(w) for w in sorted(words, key=len, reverse=True)) + r")\b", re.I)


def anonymise(text: str, scrubber: re.Pattern[str] | None) -> str:
    text = re.sub(r"[\w.+-]+@[\w-]+\.[\w.]+", "[email]", text)
    return scrubber.sub("[name]", text) if scrubber else text


# ----------------------------------------------------------------- the data
def _since(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


def collect(module_code: str, days: int) -> dict[str, Any]:
    """Anonymised activity for one module over the last `days` days."""
    cat = get_catalog()
    module = cat.module(module_code)
    staff = _staff_ids()
    scrub = _name_scrubber()
    since = _since(days)

    questions: list[dict[str, Any]] = []
    students: set[str] = set()
    socratic = faculty_turns = uncited = 0
    for conv in store.all_conversations():
        if conv.user_id in staff or conv.module != module_code:
            continue
        turns = conv.turns
        for i, t in enumerate(turns):
            if t.role != "user" or t.at < since:
                continue
            reply = next((r for r in turns[i + 1 :] if r.role == "assistant"), None)
            cited = bool(reply and any(not c.get("dangling") for c in reply.citations))
            students.add(conv.user_id)
            socratic += t.socratic
            faculty_turns += bool(t.faculty)
            uncited += not cited
            questions.append(
                {"text": _short(anonymise(t.content, scrub), 300), "unit": conv.unit, "cited": cited, "socratic": t.socratic}
            )

    units: list[dict[str, Any]] = []
    attempts = [
        i
        for i in store.list_practice(module=module_code)
        if i.user_id not in staff and i.score is not None and i.answered_at >= since
    ]
    for u in module.units if module else []:
        scores = [i.score for i in attempts if i.unit == u.id and i.score is not None]
        units.append(
            {
                "id": u.id,
                "title": u.title,
                "questions": sum(q["unit"] == u.id for q in questions),
                "practice_attempts": len(scores),
                "practice_avg": round(sum(scores) / len(scores), 2) if scores else None,
            }
        )
        students |= {i.user_id for i in attempts if i.unit == u.id}

    return {
        "module": module_code,
        "title": module.title if module else module_code,
        "days": days,
        "stats": {
            "students": len(students),
            "questions": len(questions),
            "socratic": socratic,
            "with_faculty_persona": faculty_turns,
            "unsupported": uncited,
            "practice_attempts": len(attempts),
        },
        "units": units,
        "gaps": [q["text"] for q in questions if not q["cited"] and not q["socratic"]][-10:],
        "questions": questions,
    }


# -------------------------------------------------------------- the summary
def _cache_path(module_code: str, days: int, fingerprint: str):
    return store.yaxa_root() / "cache" / "briefs" / f"{module_code}-{days}-{fingerprint}.json"


async def summarise(data: dict[str, Any], user_id: str, refresh: bool) -> str:
    if not data["questions"] and not data["stats"]["practice_attempts"]:
        return ""
    fingerprint = hashlib.sha1(
        json.dumps([date.today().isoformat(), data["stats"], data["units"]], sort_keys=True).encode()
    ).hexdigest()[:12]
    cache = _cache_path(data["module"], data["days"], fingerprint)
    if cache.is_file() and not refresh:
        return json.loads(cache.read_text()).get("summary", "")

    asked = data["questions"][-MAX_QUESTIONS_TO_MODEL:]
    payload = (
        f"Module: {data['title']} ({data['module']}). Period: last {data['days']} days.\n"
        f"Students active: {data['stats']['students']}. Questions: {data['stats']['questions']}.\n\n"
        "Students' questions (anonymised; [S] = asked in Socratic mode):\n"
        + "\n".join(f"- {'[S] ' if q['socratic'] else ''}{q['text']}" for q in asked)
        + "\n\nQuestions the course material couldn't support:\n"
        + ("\n".join(f"- {g}" for g in data["gaps"]) or "- (none)")
        + "\n\nPractice by learning unit (average score 0-3):\n"
        + "\n".join(
            f"- {u['id']} {u['title']}: {u['practice_attempts']} attempts"
            + (f", average {u['practice_avg']}" if u["practice_avg"] is not None else "")
            for u in data["units"]
        )
    )
    summary = await complete_text(
        resolve_for(user_id),
        [{"role": "system", "content": BRIEF_PROMPT}, {"role": "user", "content": payload}],
        max_tokens=2500,
    )
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps({"summary": summary}))
    return summary


# ------------------------------------------------------------------ routes
def _require_staff() -> Any:
    cu, user = _me()
    if not _privileged(cu, user):
        raise HTTPException(403, "The cohort brief is for faculty")
    return cu


@router.get("/modules")
async def modules() -> list[dict[str, Any]]:
    _require_staff()
    cat = get_catalog()
    return [{"code": m.code, "title": m.title} for m in cat.modules.values() if m.available]


@router.get("/brief")
async def brief(module: str, days: int = 7, refresh: bool = False) -> dict[str, Any]:
    cu = _require_staff()
    cat = get_catalog()
    if not cat.module(module):
        raise HTTPException(404, "Unknown module")
    days = max(1, min(days, 120))
    data = collect(module, days)
    summary, summary_error = "", None
    try:
        summary = await summarise(data, cu.id, refresh)
    except Exception as exc:
        logger.warning("yaxa cohort brief: summary failed", exc_info=True)
        summary_error = f"Couldn't write the summary: {type(exc).__name__}"
    data.pop("questions")  # the page shows counts, gaps and the summary, not every question
    return data | {"summary": summary, "summary_error": summary_error}
