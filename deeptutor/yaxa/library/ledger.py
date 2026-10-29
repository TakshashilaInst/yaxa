"""What the library sync has done with each Drive file, and what it should do next.

One JSON file (``<data>/yaxa/library/ledger.json``) keyed by Drive file id.
``diff`` compares a fresh walk of the Drive folder with the ledger and returns
the actions for this run. Indexing is append-only in DeepTutor, so a file is
never indexed twice under the same name: moving a file within its library only
changes labels, and new content gets a new name while the old one is retired.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from datetime import datetime, timezone
import json
import os
from pathlib import Path, PurePosixPath
import re
import tempfile
from typing import Any

from .drive import DriveFile
from .layout import Placement

STATUSES = ("new", "processing", "review", "approved", "live", "failed", "skipped", "rejected", "retired")


@dataclass
class Entry:
    drive_id: str
    kb: str
    kind: str  # reading | recording | writing
    indexed_as: str  # file name inside the KB (what grounding sees)
    md5: str = ""
    path: str = ""  # Drive path when last seen, for the Libraries page
    status: str = "new"
    error: str = ""
    placement: dict = field(default_factory=dict)
    updated: str = ""
    flags: list[dict] = field(default_factory=list)  # name-gate hits waiting for a person
    allow: list[str] = field(default_factory=list)  # names a person marked "public, keep"
    vtt_id: str = ""


@dataclass
class Action:
    kind: str  # add | relabel | replace | retire | skip | index
    file: DriveFile | None = None
    entry: Entry | None = None
    placement: Placement | None = None
    reason: str = ""
    extra: dict = field(default_factory=dict)


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Ledger:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.entries: dict[str, Entry] = {}

    def load(self) -> "Ledger":
        if self.path.is_file():
            known = {f.name for f in fields(Entry)}
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            self.entries = {k: Entry(**{a: b for a, b in v.items() if a in known}) for k, v in raw.items()}
        return self

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix=".ledger-")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump({k: asdict(v) for k, v in self.entries.items()}, fh, indent=1, ensure_ascii=False)
        os.replace(tmp, self.path)

    def names_in(self, kb: str) -> set[str]:
        return {e.indexed_as for e in self.entries.values() if e.kb == kb and e.indexed_as}


def _drive_path(file: DriveFile) -> str:
    return "/".join(file.path + (file.name,))


def indexed_name(placement: Placement, file: DriveFile, taken: set[str]) -> str:
    """The name a file gets inside its KB: its Drive name, or 'Webinar - <stem>.md' for recordings."""
    if placement.kind == "recording":
        base = f"Webinar - {PurePosixPath(file.name).stem}.md"
    else:
        base = re.sub(r"[/\\]+", "-", file.name)
    stem, ext = os.path.splitext(base)
    name, n = base, 2
    while name in taken:
        name, n = f"{stem} ({n}){ext}", n + 1
    return name


def diff(files: list[DriveFile], placements: dict[str, Any], ledger: Ledger) -> list[Action]:
    """Actions for this sync run. `placements` maps file id -> Placement | None | reason str."""
    actions: list[Action] = []
    seen: set[str] = set()
    # Zoom transcripts pair with the recording of the same name in the same folder.
    vtts = {
        (f.path, PurePosixPath(f.name).stem): f.id
        for f in files
        if isinstance(placements.get(f.id), Placement) and placements[f.id].kind == "transcript"
    }
    for file in files:
        seen.add(file.id)
        where = placements.get(file.id)
        entry = ledger.entries.get(file.id)
        if isinstance(where, Placement) and where.kind == "transcript":
            continue
        if where is None or isinstance(where, str):
            if entry and entry.status not in ("retired", "skipped"):
                actions.append(Action("retire", file=file, entry=entry))
            if isinstance(where, str) and not (entry and entry.status == "skipped" and entry.error == where
                                               and entry.md5 == file.md5):
                actions.append(Action("skip", file=file, entry=entry, reason=where))
            continue
        extra = {}
        if where.kind == "recording":
            vtt = vtts.get((file.path, PurePosixPath(file.name).stem))
            if vtt:
                extra["vtt_id"] = vtt
        if entry is None or entry.status in ("skipped", "retired"):
            actions.append(Action("add", file=file, placement=where, extra=extra))
        elif entry.status == "review":
            continue  # waiting for a person on the Libraries page
        elif entry.status == "rejected":
            if file.md5 and file.md5 != entry.md5:  # a new upload under the same file: try again
                actions.append(Action("add", file=file, entry=None, placement=where, extra=extra))
            continue
        elif entry.status == "approved":
            actions.append(Action("index", file=file, entry=entry, placement=where))
        elif entry.status in ("new", "processing", "failed"):
            actions.append(Action("add", file=file, entry=entry, placement=where, extra=extra))
        elif entry.kb != where.kb:
            actions.append(Action("retire", file=file, entry=entry))
            actions.append(Action("add", file=file, placement=where, extra=extra))
        elif file.md5 and entry.md5 and file.md5 != entry.md5:
            actions.append(Action("replace", file=file, entry=entry, placement=where, extra=extra))
        elif entry.path != _drive_path(file) or entry.placement != where.__dict__:
            actions.append(Action("relabel", file=file, entry=entry, placement=where))
    for drive_id, entry in ledger.entries.items():
        if drive_id not in seen and entry.status not in ("retired", "skipped", "rejected"):
            actions.append(Action("retire", entry=entry))
    return actions


def seed(ledger: Ledger, fill: dict[str, dict], md5s: dict[str, str]) -> int:
    """Import what's already indexed (work/library/ledger.json from the first fill) as live."""
    added = 0
    for drive_id, info in fill.items():
        if drive_id in ledger.entries:
            continue
        kind = info.get("kind", "file")
        if kind == "file":
            kind = "writing" if info["kb"].startswith("FACULTY-") else "reading"
        ledger.entries[drive_id] = Entry(
            drive_id=drive_id, kb=info["kb"], kind=kind, indexed_as=info["indexed_as"],
            md5=md5s.get(drive_id, ""), path=info.get("path", ""), status="live", updated=now(),
        )
        added += 1
    return added
