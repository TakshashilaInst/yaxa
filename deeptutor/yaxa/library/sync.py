"""One run of the library sync: Drive folder -> Yaxa libraries.

walk Drive -> place each file (layout.py) -> diff against the ledger -> act:
readings are downloaded and staged; recordings are transcribed, stripped of
student names and staged, or held for review if a name is doubtful; then each
library with staged files gets one ``deeptutor kb add`` and its labels are
written. Every file's outcome is recorded in the ledger, and one bad file never
stops the rest.

Working folders under ``<data>/yaxa/library/``:
  ledger.json      what happened to each Drive file
  private/         raw media and transcripts while they're processed (0700), plus
                   learned-names.txt, the names removed from earlier transcripts
  staging/<KB>/    files ready for ``kb add``
  last_run.json    the last run's summary, for the Libraries page
"""

from __future__ import annotations

from collections import Counter
from contextlib import contextmanager
from dataclasses import dataclass
import fcntl
import json
import logging
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
from typing import Any, Callable, Iterator

from deeptutor.runtime.home import get_runtime_data_root

from .. import catalog
from . import labels
from .drive import DriveFile
from .layout import Placement, place
from .ledger import Action, Entry, Ledger, diff, indexed_name, now
from .redaction import CONCEPTS, FACULTY, hms, learn, redact_segments

logger = logging.getLogger(__name__)


def library_root() -> Path:
    return get_runtime_data_root() / "yaxa" / "library"


def _private() -> Path:
    path = library_root() / "private"
    path.mkdir(parents=True, exist_ok=True)
    os.chmod(path, 0o700)
    return path


@dataclass
class Deps:
    walk: Callable[[], list[DriveFile]]
    download: Callable[[str, Path], Path]
    transcribe: Callable[..., tuple[list[dict], str]]
    kb_add: Callable[[str, Path], None]
    students: Callable[[], set[str]]
    public: Callable[[], dict[str, Any]]
    api_key: str | None = None


@contextmanager
def lock() -> Iterator[bool]:
    library_root().mkdir(parents=True, exist_ok=True)
    fh = open(library_root() / "sync.lock", "w")
    try:
        fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        fh.close()
        yield False
        return
    try:
        yield True
    finally:
        fcntl.flock(fh, fcntl.LOCK_UN)
        fh.close()


# ------------------------------------------------------------------ labels
def _label(placement: Placement, file: DriveFile) -> dict[str, Any]:
    info: dict[str, Any] = {"title": placement.title, "corpus": placement.corpus, "drive_id": file.id}
    if placement.module:
        info["module"] = placement.module
    if placement.unit:
        info["unit"] = placement.unit
    if placement.kind == "recording":
        info |= {"kind": "video", "url": f"https://drive.google.com/file/d/{file.id}/view"}
    else:
        info["kind"] = "pdf" if file.name.lower().endswith(".pdf") else "note"
    return info


def _keyterms(placement: Placement) -> list[str]:
    module = catalog.get_catalog().module(placement.module)
    terms = [placement.speaker, module.title if module else ""]
    terms += [u.title for u in (module.units if module else [])]
    terms += sorted(FACULTY) + sorted(CONCEPTS)
    return [t for t in terms if t]


def _header(placement: Placement, file: DriveFile, duration: float) -> str:
    unit = f" · {placement.unit}" if placement.unit else ""
    return "\n".join([
        f"# Webinar transcript: {placement.title.removeprefix('Webinar: ')}",
        "",
        f"- Speaker: {placement.speaker or 'Takshashila faculty'}",
        f"- Cohort: {placement.cohort or 'not given'}",
        f"- Module: {placement.module}{unit}",
        f"- Recording: https://drive.google.com/file/d/{file.id}/view",
        f"- Length: {hms(duration)}",
    ])


# ------------------------------------------------------------------- actions
class _Run:
    def __init__(self, deps: Deps) -> None:
        self.deps = deps
        self.ledger = Ledger(library_root() / "ledger.json").load()
        self.staged: dict[str, list[tuple[Entry, Placement, DriveFile]]] = {}
        self.counts: Counter[str] = Counter()
        self.audio_left = catalog.get_catalog().settings.library.max_audio_hours_per_sync * 3600
        self._students: set[str] | None = None
        self._public: dict[str, Any] | None = None

    @property
    def students(self) -> set[str]:
        if self._students is None:
            self._students = self.deps.students()
        return self._students

    @property
    def public(self) -> dict[str, Any]:
        if self._public is None:
            self._public = self.deps.public()
        return self._public

    def _entry(self, action: Action) -> Entry:
        """The ledger entry for an add, keeping a name it already reserved in this library."""
        file, placement, old = action.file, action.placement, action.entry
        if old and old.kb == placement.kb and old.indexed_as and old.status not in ("retired", "skipped"):
            entry = old
        else:
            # a name once indexed stays in the index (retired or not), so it is never reused
            taken = self.ledger.names_in(placement.kb) | set(labels.names(placement.kb))
            entry = Entry(drive_id=file.id, kb=placement.kb, kind=placement.kind,
                          indexed_as=indexed_name(placement, file, taken))
        entry.kb, entry.kind, entry.md5 = placement.kb, placement.kind, file.md5
        entry.path, entry.placement, entry.error = "/".join(file.path + (file.name,)), dict(placement.__dict__), ""
        entry.vtt_id = action.extra.get("vtt_id", entry.vtt_id)
        self.ledger.entries[file.id] = entry
        return entry

    def _stage(self, entry: Entry, placement: Placement, file: DriveFile, source: Path | None = None) -> None:
        dest = library_root() / "staging" / entry.kb / entry.indexed_as
        if source is None:
            self.deps.download(file.id, dest)
        else:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, dest)
        self.staged.setdefault(entry.kb, []).append((entry, placement, file))

    def add(self, action: Action) -> None:
        entry = self._entry(action)
        entry.status, entry.updated = "processing", now()
        self.ledger.save()
        if action.placement.kind == "recording":
            self._recording(entry, action.placement, action.file)
        else:
            self._stage(entry, action.placement, action.file)

    def _recording(self, entry: Entry, placement: Placement, file: DriveFile) -> None:
        work = _private() / file.id
        redacted = work / "redacted.md"
        if redacted.is_file() and not entry.flags:  # transcribed in an earlier run; indexing failed
            self._stage(entry, placement, file, source=redacted)
            return
        if self.audio_left <= 0:
            entry.status = "new"  # over this run's Sarvam budget; next run
            self.counts["waiting"] += 1
            return
        work.mkdir(parents=True, exist_ok=True)
        media = self.deps.download(file.id, work / f"media{PurePosixPath(file.name).suffix.lower()}")
        vtt = self.deps.download(entry.vtt_id, work / "zoom.vtt") if entry.vtt_id else None
        try:
            segments, engine = self.deps.transcribe(media, vtt, _keyterms(placement), self.deps.api_key, work)
        finally:
            media.unlink(missing_ok=True)
            shutil.rmtree(work / "audio", ignore_errors=True)
        duration = max((s["end"] for s in segments), default=0.0)
        self.audio_left -= duration
        engine_label = {"sarvam+zoom": "Sarvam (saaras:v4), speakers from Zoom", "sarvam": "Sarvam (saaras:v4)",
                        "zoom": "Zoom's own transcript"}.get(engine, engine)
        result = redact_segments(segments, _header(placement, file, duration), placement.speaker, self.public,
                                 self.students, allow=entry.allow, engine=engine_label)
        learn(_private() / "learned-names.txt", result.removed)
        redacted.write_text(result.markdown, encoding="utf-8")
        if vtt:
            vtt.unlink(missing_ok=True)
        if result.flags:
            entry.status, entry.flags = "review", result.flags
            self.counts["review"] += 1
            return
        self._stage(entry, placement, file, source=redacted)

    def index_approved(self, action: Action) -> None:
        entry = action.entry
        redacted = _private() / entry.drive_id / "redacted.md"
        if not redacted.is_file():
            raise FileNotFoundError("approved transcript is missing; it will be redone")
        self._stage(entry, action.placement, action.file, source=redacted)

    def retire(self, entry: Entry) -> None:
        if entry.kb and entry.indexed_as and entry.status == "live":
            labels.retire(entry.kb, entry.indexed_as)
        entry.status, entry.updated = "retired", now()

    def relabel(self, action: Action) -> None:
        entry, file, placement = action.entry, action.file, action.placement
        same_name = PurePosixPath(entry.path).name == file.name if entry.path else True
        labels.upsert(entry.kb, entry.indexed_as, _label(placement, file), keep_curated=same_name)
        entry.path, entry.placement, entry.updated = "/".join(file.path + (file.name,)), dict(placement.__dict__), now()

    def index_staged(self) -> None:
        for kb, items in self.staged.items():
            folder = library_root() / "staging" / kb
            try:
                self.deps.kb_add(kb, folder)
            except Exception as exc:
                for entry, _, _ in items:
                    entry.status, entry.error, entry.updated = "failed", f"indexing failed: {str(exc)[-300:]}", now()
                    self.counts["failed"] += 1
                logger.warning("yaxa library: kb add %s failed", kb, exc_info=True)
            else:
                for entry, placement, file in items:
                    labels.upsert(kb, entry.indexed_as, _label(placement, file))
                    entry.status, entry.flags, entry.updated = "live", [], now()
                    shutil.rmtree(_private() / entry.drive_id, ignore_errors=True)
                    self.counts["added"] += 1
            shutil.rmtree(folder, ignore_errors=True)
            self.ledger.save()


def _placements(files: list[DriveFile]) -> dict[str, Any]:
    cat = catalog.get_catalog(fresh=True)
    return {f.id: place(f.path, f.name, f.mime, cat) for f in files}


def run(deps: Deps, *, dry_run: bool = False) -> dict[str, Any]:
    with lock() as got:
        if not got:
            return {"busy": True}
        files = deps.walk()
        placements = _placements(files)
        r = _Run(deps)
        actions = diff(files, placements, r.ledger)
        if dry_run:
            return dict(Counter(a.kind for a in actions))
        started = now()
        with labels.batch():
            _apply(r, actions)
            r.index_staged()
        r.ledger.save()
        summary = {k: r.counts.get(k, 0) for k in ("added", "relabelled", "replaced", "retired", "review", "failed",
                                                   "skipped", "waiting")}
        (library_root() / "last_run.json").write_text(json.dumps({"started": started, "finished": now(), "summary": summary}))
        # "replaced" files are also counted in "added" once indexed
        summary["added"] -= summary["replaced"]
        return summary


def _apply(r: _Run, actions: list[Action]) -> None:
    for action in actions:
        entry = action.entry
        try:
            if action.kind == "skip":
                entry = entry or Entry(drive_id=action.file.id, kb="", kind="", indexed_as="")
                entry.status, entry.error, entry.md5 = "skipped", action.reason, action.file.md5
                entry.path, entry.updated = "/".join(action.file.path + (action.file.name,)), now()
                r.ledger.entries[action.file.id] = entry
                r.counts["skipped"] += 1
            elif action.kind == "retire":
                r.retire(entry)
                r.counts["retired"] += 1
            elif action.kind == "relabel":
                r.relabel(action)
                r.counts["relabelled"] += 1
            elif action.kind == "replace":
                r.retire(entry)
                r.ledger.entries.pop(entry.drive_id, None)
                r.add(Action("add", file=action.file, placement=action.placement, extra=action.extra))
                r.counts["replaced"] += 1
            elif action.kind == "index":
                r.index_approved(action)
            else:
                r.add(action)
        except Exception as exc:
            target = r.ledger.entries.get(action.file.id if action.file else entry.drive_id) or entry
            if target is not None:
                target.status, target.error, target.updated = "failed", f"{type(exc).__name__}: {str(exc)[:200]}", now()
            r.counts["failed"] += 1
            logger.warning("yaxa library: %s failed for one file", action.kind, exc_info=True)
        r.ledger.save()


# -------------------------------------------------------------- real deps
def kb_add(kb: str, docs: Path) -> None:
    """`deeptutor kb add <kb> --docs-dir <docs>` in a subprocess; raises with the log's tail on failure."""
    exe = Path(sys.executable).with_name("deeptutor")
    log = library_root() / f"kb-add-{kb}.log"
    with log.open("w") as fh:
        code = subprocess.run([str(exe), "kb", "add", kb, "--docs-dir", str(docs)], stdout=fh, stderr=subprocess.STDOUT).returncode
    if code != 0:
        raise RuntimeError(log.read_text(errors="replace")[-300:])
