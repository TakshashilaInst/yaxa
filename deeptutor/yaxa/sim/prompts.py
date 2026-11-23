"""Prompts for simulations.

Three kinds of caller, with different knowledge:
- an **actor** (a Yaxa-played role) sees only the shared brief, its own card and
  what the student said to it, so private information can surface only if the
  actor chooses to reveal it;
- the **game master** (positions, meeting) sees every card but never shows the
  student another actor's private information unless that actor says it;
- the **debrief** sees everything, including the answer key.
"""

from __future__ import annotations

from typing import Any

from ..prompting import TAKSHASHILA_FRAMING
from .engine import MAX_INTERVENTIONS, RUBRIC
from .scenario import Role, Scenario
from .state import SimRun


def _options(s: Scenario) -> str:
    return "\n".join(f"{o.id}. {o.label}: {o.summary}" for o in s.options)


def _card(r: Role) -> str:
    return (
        f"Role: {r.name}\nWho you are: {r.mandate}\nWhat you want most: {r.wants}\n"
        f"What you would accept instead: {r.secondary}\nRed line: {r.red_line}\n"
        f"What only you know: {r.private}\nIf there is no deal: {r.batna}"
    )


def _shared(s: Scenario) -> str:
    return f"Scenario: {s.title} ({s.setting}).\n\n{s.brief}\n\nThe decision: {s.decision}\nOptions:\n{_options(s)}"


def _shock_text(s: Scenario, run: SimRun) -> str:
    shock = next((x for x in s.shocks if x.id == run.shock), None)
    return f"News that has just broken: {shock.headline}. {shock.body}" if shock and run.stage >= 3 else ""


# ------------------------------------------------------------------ actors
def actor_system(s: Scenario, actor: Role, run: SimRun, *, student_role: Role) -> str:
    position = run.positions.get(actor.id) or actor.leans or s.default_option
    return "\n\n".join(p for p in (
        f"You are playing {actor.name} in a policy simulation for a Takshashila public policy course. "
        f"A student is playing {student_role.name} and has asked to meet you privately before {s.body} decides.",
        _shared(s),
        "Your confidential role card:\n" + _card(actor),
        f"You currently back option {position}. You may move if the student offers something that serves your interests.",
        _shock_text(s, run),
        """How to play:
- Stay in role. Speak as a senior Indian official or representative would: direct, courteous, guarded.
- Argue from your own mandate and interests, not from what is best overall.
- Your private information is a bargaining chip. Reveal it only if the student asks the right question or offers something in return, and then only as much as helps you. Never reveal it all at once in your first reply.
- Never invent facts about other parties' secrets. If you don't know, say so.
- When you use an idea from the numbered course passages, cite it like [2]. Use only numbers given.
- Keep each reply under 150 words. End with what you want from the student, or a question.""",
        TAKSHASHILA_FRAMING,
    ) if p)


# ------------------------------------------------------------- game master
POSITIONS_SYSTEM = """\
You are the game master of a policy simulation. Given every role card, where each Yaxa-played
role stood, and what has just happened, decide which option each Yaxa-played role backs now.
Move a role only for a reason grounded in its interests and what happened; most roles move rarely.
Reply with JSON only: {"positions": {"<role id>": "<option id>", ...}, "note": "<one sentence on who moved and why>"}"""


def positions_context(s: Scenario, run: SimRun, event: str) -> str:
    cards = "\n\n".join(f"[{r.id}]\n{_card(r)}" for r in s.roles if r.id != run.role)
    student = s.role(run.role)
    return "\n\n".join(p for p in (
        _shared(s),
        f"Yaxa-played roles:\n\n{cards}",
        f"The student plays [{run.role}] {student.name if student else ''}. They back option {run.student_option() or '?'}.",
        f"Current positions: {run.positions}",
        _shock_text(s, run),
        f"What just happened:\n{event}",
    ) if p)


def meeting_system(s: Scenario) -> str:
    chair = s.role(s.chair)
    return f"""\
You write the transcript of a meeting of {s.body} in a policy simulation, chaired by {chair.name if chair else 'the chair'}.
Every Yaxa-played member speaks in character, from their own mandate, interests and current position.
A member may hint at or use their private information if it helps them now, but nobody states another member's secrets.
The student's interventions are given; members respond to them directly and may change their position if moved.
Write in the register of an Indian government meeting: formal, terse, with real disagreement.
Format each turn as "**<Member name>:** <what they say>". Keep each turn under 90 words.
{TAKSHASHILA_FRAMING}"""


def meeting_context(s: Scenario, run: SimRun, phase: str, intervention: str = "") -> str:
    cards = "\n\n".join(f"[{r.id}]\n{_card(r)}" for r in s.roles if r.id != run.role)
    student = s.role(run.role)
    so_far = "\n\n".join(f"**{t['speaker']}:** {t['text']}" for t in run.meeting)
    task = {
        "open": "Write the opening of the meeting: the chair frames the decision, then each other member states their position (one turn each). End by inviting the student's ministry to speak.",
        "continue": f"The student ({student.name if student else ''}) has just said the intervention below. Write 2 to 4 turns of members responding to it.",
        "close": f'The chair now closes the discussion and circulates a draft recommendation. Reply with JSON only: {{"option": "<option id>", "text": "<the draft recommendation to {s.decider}, under 150 words, including any conditions>", "closing": "<the chair\'s closing words, under 60 words>"}}',
    }[phase]
    return "\n\n".join(p for p in (
        _shared(s),
        f"Members played by Yaxa:\n\n{cards}",
        f"Current positions: {run.positions}",
        f"The student plays {student.name if student else run.role}. Their latest position: option {run.student_option() or '?'}."
        f" They may intervene up to {MAX_INTERVENTIONS} times.",
        _shock_text(s, run),
        f"Transcript so far:\n{so_far}" if so_far else "",
        f"Student's intervention:\n{intervention}" if intervention else "",
        f"Your task: {task}",
    ) if p)


# ----------------------------------------------------------------- scoring
SCORING_SYSTEM = """\
You score a student's memo in a Takshashila policy simulation against a rubric. Judge the reasoning, not the prose.
For each criterion give 1 (missing), 2 (weak), 3 (sound) or 4 (strong), with a one-line reason that quotes
or points to the memo. Score what is on the page; don't reward length.
Criteria (what 4 looks like):
""" + "\n".join(f'- "{k}": {v["label"]}. {v["strong"]}' for k, v in RUBRIC.items()) + """

Reply with JSON only:
{"scores": {"<criterion>": {"score": <1-4>, "reason": "<one line>"}, ...}, "feedback": "<2-3 sentences to the student, as 'you': the strongest point and the one thing to improve>"}"""


def scoring_context(s: Scenario, run: SimRun, memo_text: str, option: str, day: int, passages: str) -> str:
    role = s.role(run.role)
    return "\n\n".join(p for p in (
        _shared(s),
        "The student's role card:\n" + (_card(role) if role else run.role),
        _shock_text(s, run) if day >= 3 else "",
        f"Course passages the student may draw on:\n{passages}" if passages else "",
        f"Day {day} memo, backing option {option}:\n{memo_text}",
    ) if p)


# ---------------------------------------------------------------- debrief
def outcome_system(s: Scenario) -> str:
    return f"""\
You close a Takshashila policy simulation. You decide what {s.decider} does with the committee's draft and the
members' final notes, narrate the next 12 months, and write the student's debrief.
Decide as the real {s.decider} plausibly would, weighing who backed what and the politics. Have no preferred outcome.
The consequences must follow from the decision and the scenario, including at least one second-order or unintended effect.

The debrief is for the student, addressed as "you", in Markdown, under 450 words, with these sections:
## What you traded  (what your ministry gained and gave up, and what it cost)
## What you didn't know  (the other members' private information that mattered, and whether you could have uncovered it)
## What happened in real life  (from the answer key; connect it to what happened in this run)
## The lesson  (one or two generalisable points)
Cite the numbered course passages like [2] where they support a point. Use only numbers given.

Answer key (real history and takeaways):
{s.answer_key}

{TAKSHASHILA_FRAMING}

Reply with JSON only:
{{"option": "<option id the {s.decider} adopts>", "decision": "<one sentence: what it decided and any conditions>",
"consequences": "<Markdown, under 250 words: the next 12 months>", "debrief": "<Markdown debrief>"}}"""


def outcome_context(s: Scenario, run: SimRun, passages: str = "") -> str:
    cards = "\n\n".join(f"[{r.id}]{' (the student)' if r.id == run.role else ''}\n{_card(r)}" for r in s.roles)
    memos = "\n\n".join(f"Day {m.day} memo (option {m.option}{', ' + m.stance if m.stance else ''}):\n{m.text}" for m in run.memos)
    talks = "\n\n".join(
        f"Corridor talk with {t.role}:\n" + "\n".join(f"{x['who']}: {x['content']}" for x in t.turns) for t in run.talks
    )
    meeting = "\n".join(f"{t['speaker']}: {t['text']}" for t in run.meeting)
    return "\n\n".join(p for p in (
        _shared(s),
        f"All role cards:\n\n{cards}",
        _shock_text(s, run),
        f"Final positions of Yaxa-played members: {run.positions}",
        f"Chair's draft recommendation: {run.draft}" if run.draft else "",
        f"The student's memos:\n\n{memos}" if memos else "",
        talks,
        f"Meeting transcript:\n{meeting}" if meeting else "",
        f"Course passages:\n{passages}" if passages else "",
    ) if p)


def passages_block(passages: list[dict[str, Any]]) -> str:
    from ..prompting import number_passages

    return number_passages(passages) if passages else ""
