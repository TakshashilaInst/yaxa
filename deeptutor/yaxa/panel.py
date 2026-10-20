"""Faculty panel: two or three faculty personas take one question, then respond to each other.

Each panellist is grounded in the module's passages plus their own writing,
and may cite only those. Order: openings, one round of responses, then Yaxa
sums up where they agree and differ. Streamed as server-sent events.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from . import grounding, prompting, store
from .access import _cited_numbers, _me, _public_passage, _require_module, _short, _sse
from .catalog import Faculty, get_catalog
from .llm import ModelUnavailable, resolve_for, stream_text

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/panel")

MODULE_PASSAGES = 5
OWN_PASSAGES = 4
TURNS_CHARGED = 3  # a panel costs about as much as three chat turns

PANEL_RULES = """\
You are on a short panel discussion for Takshashila students with {others}, moderated by Yaxa.
{phase_rules}
- Cite the passages listed for you by number in square brackets, e.g. [3]. Use only those numbers.
- Plain language, Indian context first. No headings, no bullet lists: speak as you would on a panel."""

OPENING_RULES = """\
This is your opening statement on the student's question. Take a clear position and give your main
reason, in under 150 words."""

RESPONSE_RULES = """\
The openings are in. Respond to the other panellists by name: say where you agree, where you disagree
and why. Don't repeat your opening. Under 120 words."""

SUMMARY_PROMPT = """\
You are Yaxa, moderating a Takshashila faculty panel (AI personas based on each faculty member's public
writing). Sum up for the student in under 130 words: where the panellists agree, where they differ and
why, and one question the student should think about next. Name the panellists. Add no new claims and no
citations. Plain prose."""


def allocate(module_passages: list[dict[str, Any]], own: dict[str, list[dict[str, Any]]]) -> tuple[list[dict[str, Any]], dict[str, list[int]]]:
    """One numbered list for the margin, and the numbers each panellist may cite.

    Module passages come first and every panellist may cite them; each
    panellist's own writing follows and only they may cite it.
    """
    numbered = list(module_passages)
    shared = list(range(1, len(module_passages) + 1))
    allowed: dict[str, list[int]] = {}
    for slug, passages in own.items():
        start = len(numbered) + 1
        numbered += passages
        allowed[slug] = shared + list(range(start, start + len(passages)))
    return numbered, allowed


def _passage_block(numbered: list[dict[str, Any]], numbers: list[int], fac: Faculty) -> str:
    out = []
    for n in numbers:
        p = numbered[n - 1]
        by = f" [{p['byline'] or f'by {fac.name}'}]" if p.get("kb") == fac.kb else ""
        out.append(f"[{n}] {p['title']}{by}\n{p['text'].strip()}")
    return "\n\n".join(out) or "(No passages matched.)"


class PanelBody(BaseModel):
    question: str
    module: str | None = None
    faculty: list[str] = []


@router.post("")
async def panel(body: PanelBody) -> StreamingResponse:
    cu, user = _me()
    cat = get_catalog()
    question = body.question.strip()
    if not question:
        raise HTTPException(400, "Ask the panel a question")
    if len(question) > 2000:
        raise HTTPException(413, "Keep the question under 2,000 characters")
    module = _require_module(cat, cu, user, body.module)
    slugs = body.faculty or [f.slug for f in cat.faculty.values() if f.kb]
    panellists = [cat.faculty[s] for s in dict.fromkeys(slugs) if s in cat.faculty]
    if not 2 <= len(panellists) <= 3:
        raise HTTPException(400, "Pick two or three faculty for the panel")
    try:
        config = resolve_for(cu.id)
    except ModelUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    for _ in range(TURNS_CHARGED):
        if not store.count_turn(user, cat.settings.daily_turn_limit):
            raise HTTPException(429, "You've reached today's question limit. It resets tomorrow.")

    conv = store.Conversation(
        user_id=cu.id,
        kind="panel",
        module=module.code if module else None,
        title=_short(question, 70),
    )
    conv.turns.append(store.Turn(role="user", content=question))

    async def events():
        yield _sse(
            "meta",
            {
                "conversation_id": conv.id,
                "panel": [{"slug": f.slug, "name": f.name, "label": f.label} for f in panellists],
            },
        )
        jobs = [grounding.retrieve(module.kb, question, MODULE_PASSAGES, corpus=module.title)] if module and module.kb else []
        jobs += [grounding.retrieve(f.kb, question, OWN_PASSAGES, corpus=f"{f.name}'s work") for f in panellists]
        results = await asyncio.gather(*jobs)
        module_passages = results[0] if module and module.kb else []
        own = dict(zip([f.slug for f in panellists], results[-len(panellists):], strict=True))
        numbered, allowed = allocate(module_passages, own)
        sources = [_public_passage(p, i) for i, p in enumerate(numbered, 1)]
        yield _sse("sources", sources)

        transcript: list[tuple[Faculty, str, str]] = []  # (who, phase, text)

        async def speak(fac: Faculty, phase: str):
            others = " and ".join(f.name for f in panellists if f.slug != fac.slug)
            system = "\n\n".join(
                [
                    prompting._faculty_block(fac),
                    prompting._module_block(module, None),
                    prompting._profile_block(user.profile, user.display_name),
                    prompting.TAKSHASHILA_FRAMING,
                    PANEL_RULES.format(others=others, phase_rules=OPENING_RULES if phase == "opening" else RESPONSE_RULES),
                ]
            )
            said = "\n\n".join(f"{who.name} ({ph}): {text}" for who, ph, text in transcript)
            content = (
                f"Student's question: {question}\n\n"
                + (f"The panel so far:\n\n{said}\n\n" if said else "")
                + f"---\nPassages you may cite:\n\n{_passage_block(numbered, allowed[fac.slug], fac)}"
            )
            yield _sse("turn_start", {"speaker": fac.slug, "name": fac.name, "label": fac.label, "phase": phase})
            text = ""
            async for chunk in stream_text(config, [{"role": "system", "content": system}, {"role": "user", "content": content}], max_tokens=1500):
                text += chunk
                yield _sse("delta", chunk)
            ok = set(allowed[fac.slug])
            citations = [{"n": n, "dangling": n not in ok} for n in _cited_numbers(text)]
            transcript.append((fac, phase, text))
            conv.turns.append(store.Turn(role="assistant", content=text, faculty=fac.slug, phase=phase, sources=sources, citations=citations))
            yield _sse("turn_end", {"speaker": fac.slug, "phase": phase, "citations": citations})

        try:
            for phase in ("opening", "response"):
                for fac in panellists:
                    async for event in speak(fac, phase):
                        yield event
            said = "\n\n".join(f"{who.name} ({ph}): {text}" for who, ph, text in transcript)
            yield _sse("turn_start", {"speaker": "moderator", "name": "Yaxa", "label": "Moderator", "phase": "summary"})
            summary = ""
            async for chunk in stream_text(
                config,
                [{"role": "system", "content": SUMMARY_PROMPT}, {"role": "user", "content": f"Question: {question}\n\n{said}"}],
                max_tokens=1200,
            ):
                summary += chunk
                yield _sse("delta", chunk)
            conv.turns.append(store.Turn(role="assistant", content=summary, phase="summary"))
            yield _sse("turn_end", {"speaker": "moderator", "phase": "summary", "citations": []})
        except Exception as exc:
            logger.exception("yaxa panel stream failed")
            yield _sse("error", f"The panel was cut short: Yaxa couldn't reach its model ({type(exc).__name__}).")
        finally:
            store.save_conversation(conv)
        yield _sse("done", {"conversation_id": conv.id})

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
