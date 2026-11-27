"""Friday brief additions: what the week's Learn sessions and brief layers say about the cohort.

For each session in the window, faculty see: how many students explained the idea back, the common gaps in
their explanations, the common weaknesses across their brief layers, and a suggested debate framing for
Saturday. Everything is anonymised and aggregated:
- no names or ids reach the model or the page;
- brief texts are used only when at least MIN_WRITERS students wrote the layer;
- any pattern that copies five words in a row from a brief, or names a student's problem, is dropped.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
import hashlib
import json
import logging
import re
from typing import Any

from fastapi import APIRouter, HTTPException

from . import brief, cases, community, layers, store
from .access import _me, _privileged, parse_json_reply
from .catalog import get_catalog
from .cohort import _staff_ids
from .llm import ModelUnavailable, complete_text, resolve_for
from .schedule import IST, load_cohort

logger = logging.getLogger(__name__)

DAYS_BACK = 7  # sessions just held, whose Learn week has ended
DAYS_AHEAD = 7  # sessions coming up, whose Learn week is under way
MIN_WRITERS = 3  # fewer than this: counts only, so no one's work can be singled out
MAX_TEXT = 1500  # characters of each layer text sent to the model
QUOTE_RUN = 5  # this many words in a row copied from a brief means a quotation

router = APIRouter(prefix="/sprint")


def _module_of(session: str):
    return next((m for m in get_catalog().modules.values() if any(u.id == session for u in m.units)), None)


def _members(cohort: str) -> list[str]:
    staff = _staff_ids()
    return [u.user_id for u in store.list_users()
            if u.user_id not in staff and any(e.cohort == cohort for e in u.enrolments)]


def sprint_data(cohort: str, now: datetime | None = None) -> list[dict[str, Any]]:
    """Counts per session (no text), for sessions from DAYS_BACK ago to DAYS_AHEAD ahead."""
    c = load_cohort(cohort)
    if not c:
        return []
    today = (now or datetime.now(IST)).astimezone(IST).date()
    members = _members(cohort)
    out = []
    for sess in sorted(c.sessions, key=lambda x: (x.date, x.time)):
        try:
            d = date.fromisoformat(sess.date)
        except ValueError:
            continue
        if not today - timedelta(days=DAYS_BACK) <= d <= today + timedelta(days=DAYS_AHEAD):
            continue
        mod = _module_of(sess.code)
        if not mod:
            continue
        case = cases.approved_case(mod.code, sess.code)
        layer = layers.approved_layer(mod.code, sess.code)
        if not case and not layer:
            continue
        rows = [cases.learn_progress(uid).get(f"{mod.code}/{sess.code}", {}) for uid in members]
        started = [r for r in rows if r.get("status") in ("in_progress", "tried", "explained")]
        written = sum(1 for uid in members if brief.layer_status(uid, mod.code, sess.code)["written"])
        out.append({"module": mod.code, "session": sess.code, "title": next(u.title for u in mod.units if u.id == sess.code),
                    "date": sess.date, "enrolled": len(members),
                    "learn": {"case": bool(case), "started": len(started),
                              "explained": sum(1 for r in started if r.get("status") == "explained")},
                    "layer": {"available": bool(layer), "written": written}})
    return out


# ------------------------------------------------------------------ patterns, via the model
PATTERN_PROMPT = """\
You prepare part of a Friday brief for faculty of a Takshashila public policy course, ahead of Saturday's live
session. You get, for one session: the session's idea, what students' explain-back attempts were still missing
(each line one student's attempt), and, if there are enough, the anonymous texts students wrote for this session's
layer of their own policy brief.
- "gaps": up to 3 common gaps in understanding the idea, each a short phrase with how common it is ("about half
  ...", "several ..."). Empty if there are no attempts.
- "weaknesses": up to 3 common weaknesses across the brief layers ("most named a symptom, not a failure").
  Patterns across students only. Never quote, never paraphrase one student's text, never mention anyone's
  specific problem or topic. Empty if no texts are given.
- "debate": one question that would make a good Saturday debate, built on these gaps and weaknesses, under 30
  words.
Takshashila's usage: "State" means the political institution in Max Weber's sense. Plain text, no markdown.

Reply with JSON only, no other text:
{"gaps": ["..."], "weaknesses": ["..."], "debate": "..."}"""


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9']+", text.lower())


def _runs(text: str, n: int = QUOTE_RUN) -> set[tuple[str, ...]]:
    w = _words(text)
    return {tuple(w[i:i + n]) for i in range(len(w) - n + 1)}


def _safe_items(items: list[str], texts: list[str], titles: list[str]) -> list[str]:
    """Drop anything that quotes a brief or names a student's problem."""
    quoted = set().union(*(_runs(t) for t in texts)) if texts else set()
    titles = [t.lower() for t in titles if len(t) >= 4]
    keep = []
    for item in items:
        if _runs(item) & quoted or any(t in item.lower() for t in titles):
            continue
        keep.append(item)
    return keep


def _cache_path(cohort: str, module: str, session: str):
    return community.root("sprint", store._safe(cohort)) / f"{store._safe(module)}__{store._safe(session)}.json"


async def patterns(cu, cohort: str, sess: dict[str, Any], refresh: bool) -> dict[str, Any]:
    module, session = sess["module"], sess["session"]
    members = _members(cohort)
    missing = []
    for uid in members:
        attempts = cases.learn_progress(uid).get(f"{module}/{session}", {}).get("attempts") or []
        if attempts:
            missing.append([str(m) for m in attempts[-1].get("missing") or []])
    texts = brief.layer_texts(members, module, session)
    titles = [brief.load(uid)["problem"]["title"] for uid in members]
    use_texts = len(texts) >= MIN_WRITERS
    note = "" if use_texts or not texts else f"Fewer than {MIN_WRITERS} students wrote this layer, so their briefs aren't summarised."
    if not missing and not use_texts:
        return {"gaps": [], "weaknesses": [], "debate": "", "note": note or "No explain-back attempts or brief layers yet."}
    fingerprint = hashlib.sha256(json.dumps([missing, texts if use_texts else len(texts)]).encode()).hexdigest()
    path = _cache_path(cohort, module, session)
    cached = store._read_json(path)
    if cached and cached.get("fingerprint") == fingerprint and not refresh:
        return cached["result"]
    case = cases.approved_case(module, session)
    layer = layers.approved_layer(module, session)
    parts = [f"Session {session}: {sess['title']}"]
    if case:
        parts.append("The idea, as faculty described it for the case:\n" + "\n".join(f"- {g}" for g in case.grasp))
    parts.append("Explain-back attempts, still missing:\n" + ("\n".join(
        f"- {'; '.join(m) if m else '(nothing missing)'}" for m in missing) or "(none)"))
    if use_texts and layer:
        parts.append(f"The layer task: {layer.prompt}\n\nBrief layers:\n\n" + "\n\n---\n\n".join(t[:MAX_TEXT] for t in texts))
    try:
        config = resolve_for(cu.id)
    except ModelUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    reply = await complete_text(config, [{"role": "system", "content": PATTERN_PROMPT},
                                         {"role": "user", "content": "\n\n".join(parts)}], max_tokens=1200)
    data = parse_json_reply(reply) or {}
    as_list = lambda k: [str(x).strip() for x in data.get(k) or [] if str(x).strip()][:3]  # noqa: E731
    result = {"gaps": _safe_items(as_list("gaps"), texts, titles),
              "weaknesses": _safe_items(as_list("weaknesses"), texts, titles) if use_texts else [],
              "debate": " ".join(_safe_items([str(data.get("debate") or "").strip()], texts, titles)), "note": note}
    community.update_json(path, lambda _old: {"fingerprint": fingerprint, "result": result})
    return result


@router.get("/brief")
async def sprint(cohort: str, refresh: bool = False) -> dict[str, Any]:
    cu, user = _me()
    if not _privileged(cu, user):
        raise HTTPException(403, "The cohort brief is for faculty")
    if not load_cohort(cohort):
        raise HTTPException(404, "No such cohort")
    sessions = sprint_data(cohort)
    for sess in sessions:
        try:
            sess |= await patterns(cu, cohort, sess, refresh)
            sess["error"] = None
        except Exception as exc:  # noqa: BLE001 - the counts are still worth showing
            logger.warning("yaxa sprint: patterns failed", exc_info=True)
            sess |= {"gaps": [], "weaknesses": [], "debate": "", "note": "", "error": f"Couldn't summarise: {type(exc).__name__}"}
    return {"cohort": cohort, "sessions": sessions}
