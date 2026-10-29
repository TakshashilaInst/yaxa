"""Where a file in the shared Drive library belongs.

The folder a file sits in says which library (KB) and module it feeds; its
name carries the labels: ``<code> - <title>[ - <speaker>].<ext>``. Recordings
sit in ``Recordings/<cohort>/``. See the "How to add files" box on the
Libraries page for the same rules in plain words.

``place`` returns a Placement, None for files in folders Yaxa must ignore
(``_Retired``, ``_Not for Yaxa``), or a short reason string for a file Yaxa
can't use, which the Libraries page shows so staff can fix it.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
import re

from ..catalog import Catalog

EXCLUDED = ("_Retired", "_Not for Yaxa")
READING_EXT = {".pdf", ".md", ".txt", ".docx"}
MEDIA_EXT = {".mp4", ".m4a", ".mp3", ".wav", ".webm", ".mov", ".aac", ".ogg"}
TRANSCRIPT_EXT = {".vtt"}
GOOGLE_TYPES = {
    "application/vnd.google-apps.document": "Google Doc",
    "application/vnd.google-apps.spreadsheet": "Google Sheet",
    "application/vnd.google-apps.presentation": "Google Slides",
}
_CODE = re.compile(r"^(C[PST]\d+\w*|U\d{1,2})$")  # CS22, CT4x, CP21, U02
_MODULE_LIKE = re.compile(r"^([A-Z]+[A-Z0-9]*(?:-[A-Z0-9]+)*)\s")  # "DFA-AS ...", "GCPP173 ..."
_COHORT = re.compile(r"^(\S+)\s+([A-Z][a-z]{2}\s+\d{4})$")  # "DFA26 Jun 2026"


@dataclass(frozen=True)
class Placement:
    kb: str
    kind: str  # reading | recording | transcript (Zoom .vtt) | writing
    module: str = ""
    unit: str = ""
    cohort: str = ""
    title: str = ""
    speaker: str = ""
    corpus: str = ""


def _clean(text: str) -> str:
    text = re.sub(r"\s*\(\d+\)$", "", text)  # "... (1)" download duplicates
    return re.sub(r"\s+", " ", text.replace("_", " ")).strip()


def _cohort_label(folder: str) -> str:
    m = _COHORT.match(folder.strip())
    return f"{m.group(1)} ({m.group(2)})" if m else folder.strip()


def _split_name(stem: str) -> tuple[str, list[str]]:
    """('CS22', ['Concept Cluster I', 'Kajari Kamal']) from 'CS22 - Concept Cluster I - Kajari Kamal'."""
    pieces = [p.strip() for p in stem.split(" - ") if p.strip()]
    if pieces and _CODE.match(pieces[0]):
        return pieces[0], pieces[1:]
    return "", pieces


def _track_kb(parts: list[str], cat: Catalog) -> str:
    """The one library every specialisation module of the track folder in `parts` shares, else ""."""
    for part in reversed(parts):
        code = part.split(" ", 1)[0]
        for prog in cat.programmes:
            track = prog.track(code)
            if track:
                kbs = {m.kb for c in track.specialisation if (m := cat.modules.get(c))}
                return kbs.pop() if len(kbs) == 1 else ""
    return ""


def place(path: list[str] | tuple[str, ...], name: str, mime: str, cat: Catalog) -> Placement | str | None:
    parts = list(path)
    if any(p.startswith(EXCLUDED) for p in parts):
        return None
    if mime == "shortcut/unreadable":
        return "shortcut to a file Yaxa can't open"
    if mime in GOOGLE_TYPES:
        return f"unsupported type {GOOGLE_TYPES[mime]} (download it as PDF and upload that)"
    ext = PurePosixPath(name).suffix.lower()
    stem = name[: -len(ext)] if ext else name
    if ext not in READING_EXT | MEDIA_EXT | TRANSCRIPT_EXT:
        return f"unsupported type {ext or mime}"

    if parts and parts[0] == "Faculty":
        who = parts[1] if len(parts) > 1 else ""
        fac = next((f for f in cat.faculty.values() if f.name == who and f.kb), None)
        if not fac:
            return f"no faculty library for {who or '(no name)'}"
        if ext not in READING_EXT:
            return f"unsupported type {ext} in a faculty folder"
        return Placement(kb=fac.kb, kind="writing", title=_clean(stem), speaker=fac.name, corpus=f"{fac.name}'s writing")

    module = None
    for part in parts:
        m = _MODULE_LIKE.match(part + " ")
        if not m:
            continue
        code = m.group(1)
        module = cat.modules.get(code)
        if module:
            break
        # "GCPP", "TP Technology and Policy" are programme/track folders; a code with a
        # dash or digit ("GCPP-XX", "TP-ZZ", "GCPP174") is a module folder we don't know
        if "-" in code or re.search(r"\d", code):
            return f"unknown module {code}"
    if module is None:
        kb = _track_kb(parts, cat)
        if kb and ext in READING_EXT:  # a track-wide guide, e.g. "GCPP › APP Advanced Public Policy › APP - Module guide.md"
            return Placement(kb=kb, kind="reading", title=_clean(stem), corpus="Course readings")
        return "not inside a module folder"
    if not module.kb:
        return f"module {module.code} has no library yet"

    code, rest = _split_name(stem)
    if ext in TRANSCRIPT_EXT:
        return Placement(kb=module.kb, kind="transcript", module=module.code, unit=code)
    if ext in MEDIA_EXT:
        after = parts[parts.index("Recordings") + 1 :] if "Recordings" in parts else []
        cohort = _cohort_label(after[0]) if after else ""
        speaker = rest[-1] if len(rest) >= 2 else ""
        topic = _clean(" - ".join(rest[:-1] if speaker else rest)) or module.title
        title = f"Webinar: {code + ' ' if code else ''}{topic}" + (f", {speaker}" if speaker else "")
        corpus = f"Webinar recording, {cohort}" if cohort else "Webinar recording"
        return Placement(kb=module.kb, kind="recording", module=module.code, unit=code, cohort=cohort,
                         title=title, speaker=speaker, corpus=corpus)
    topic = _clean(" - ".join(rest))
    title = f"{code} {module.title}: {topic}" if code else topic
    return Placement(kb=module.kb, kind="reading", module=module.code, unit=code, title=title, corpus="Course readings")
