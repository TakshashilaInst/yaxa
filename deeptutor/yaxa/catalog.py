"""Course content: programmes, tracks, modules, units, faculty and source labels.

Content is plain YAML so faculty edit files, not code. The copy shipped in
``deeptutor/yaxa/content`` is the default; a file with the same relative path
under ``<data>/yaxa/content`` overrides it (lets us edit content on the server
without a rebuild).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field
import yaml

from deeptutor.runtime.home import get_runtime_data_root

PACKAGE_CONTENT = Path(__file__).parent / "content"


def override_root() -> Path:
    return get_runtime_data_root() / "yaxa" / "content"


def _read_yaml(rel: str) -> Any:
    """Load a content file, preferring the server-side override."""
    for root in (override_root(), PACKAGE_CONTENT):
        path = root / rel
        if path.is_file():
            return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {}


def _list_yaml(subdir: str) -> list[str]:
    """Relative paths of every YAML file in a content subfolder (both roots)."""
    names: set[str] = set()
    for root in (PACKAGE_CONTENT, override_root()):
        folder = root / subdir
        if folder.is_dir():
            names.update(p.name for p in folder.glob("*.yaml") if not p.name.startswith("."))
    return [f"{subdir}/{n}" for n in sorted(names)]


# ------------------------------------------------------------------ models
class Unit(BaseModel):
    id: str  # the session code from the LMS (CP10, CT31, ...); U01... for modules without one
    title: str
    outcomes: str = ""
    lms_url: str = ""  # the session's page on OpenTakshashila (current cohort)
    aliases: list[str] = Field(default_factory=list)  # older codes the library still uses for this session


class Module(BaseModel):
    code: str
    title: str
    kb: str = ""
    description: str = ""
    units: list[Unit] = Field(default_factory=list)
    available: bool = True  # False for placeholders (no content file yet)

    def unit(self, unit_id: str | None) -> Unit | None:
        return next((u for u in self.units if u.id == unit_id), None)


class Track(BaseModel):
    code: str
    name: str
    core: list[str] = Field(default_factory=list)
    specialisation: list[str] = Field(default_factory=list)

    @property
    def module_codes(self) -> list[str]:
        return [*self.core, *self.specialisation]


class Programme(BaseModel):
    code: str
    name: str
    summary: str = ""
    tracks: list[Track] = Field(default_factory=list)  # GCPP has tracks
    modules: list[str] = Field(default_factory=list)  # PGP / capsules list modules directly

    def track(self, code: str | None) -> Track | None:
        return next((t for t in self.tracks if t.code == code), None)

    def module_codes(self, track_code: str | None = None) -> list[str]:
        """Modules a student on this programme (and track, if any) studies."""
        if self.tracks:
            track = self.track(track_code)
            tracks = [track] if track else self.tracks
            seen: list[str] = []
            for t in tracks:
                seen += [c for c in t.module_codes if c not in seen]
            return seen
        return list(self.modules)


class Faculty(BaseModel):
    slug: str
    name: str
    title: str = ""
    kb: str = ""
    label: str = ""
    style: str = ""


class SourceInfo(BaseModel):
    """Optional per-file labels for the grounding margin."""

    kind: str = "pdf"  # pdf | video | anecdote | note
    title: str = ""
    url: str = ""
    corpus: str = ""
    byline: str = ""  # e.g. "co-written by Pranay Kotasthane & RSJ" for joint work
    retired: bool = False  # taken out of Yaxa (moved to _Retired, deleted or replaced); grounding skips it
    drive_id: str = ""  # set on files the library sync manages
    module: str = ""
    unit: str = ""


class LibrarySettings(BaseModel):
    """The shared-Drive library sync (deeptutor/yaxa/library)."""

    root_folder_id: str = "1lDJWNQMgvf2ccSygdVcyyuLNPCRojut3"  # "0012 Yaxa Library"
    max_audio_hours_per_sync: float = 20  # Sarvam spend cap per run
    nightly_hour_ist: int = 2


class Settings(BaseModel):
    model_mode: str = "shared"
    shared_model: dict[str, str] = Field(default_factory=dict)
    retrieval_top_k: int = 8
    daily_turn_limit: int = 150
    allow_self_enrol: bool = True  # demo: students pick their own programme
    library: LibrarySettings = Field(default_factory=LibrarySettings)


class Catalog(BaseModel):
    programmes: list[Programme]
    modules: dict[str, Module]
    faculty: dict[str, Faculty]
    settings: Settings

    def programme(self, code: str) -> Programme | None:
        return next((p for p in self.programmes if p.code == code), None)

    def module(self, code: str) -> Module | None:
        return self.modules.get(code)


# ----------------------------------------------------------------- loading
def _load() -> Catalog:
    raw = _read_yaml("programmes.yaml")
    programmes = [Programme(**p) for p in raw.get("programmes", [])]
    placeholders: dict[str, str] = raw.get("placeholders", {}) or {}

    modules: dict[str, Module] = {}
    for rel in _list_yaml("modules"):
        m = Module(**_read_yaml(rel))
        modules[m.code] = m
    # Every module a programme references must resolve to something showable.
    for p in programmes:
        for code in p.module_codes():
            if code not in modules:
                modules[code] = Module(
                    code=code, title=placeholders.get(code, code), available=False
                )

    faculty = {}
    for rel in _list_yaml("faculty"):
        f = Faculty(**_read_yaml(rel))
        faculty[f.slug] = f

    return Catalog(
        programmes=programmes,
        modules=modules,
        faculty=faculty,
        settings=Settings(**_read_yaml("config.yaml")),
    )


@lru_cache(maxsize=1)
def _cached() -> Catalog:
    return _load()


def get_catalog(*, fresh: bool = False) -> Catalog:
    if fresh:
        _cached.cache_clear()
    return _cached()


def sources_path(kb: str) -> Path:
    """The server-side label file for a KB (the one the library sync writes)."""
    return override_root() / "sources" / f"{kb}.yaml"


def _sources_mtime(kb: str) -> int:
    for root in (override_root(), PACKAGE_CONTENT):
        path = root / "sources" / f"{kb}.yaml"
        if path.is_file():
            return path.stat().st_mtime_ns
    return 0


@lru_cache(maxsize=64)
def _sources_cached(kb: str, mtime: int) -> dict[str, SourceInfo]:
    raw = _read_yaml(f"sources/{kb}.yaml") or {}
    return {name: SourceInfo(**info) for name, info in (raw.get("files") or {}).items()}


def _sources_for(kb: str) -> dict[str, SourceInfo]:
    # keyed on the file's mtime: the library sync rewrites labels from another process
    return _sources_cached(kb, _sources_mtime(kb))


def source_info(kb: str, file_name: str) -> SourceInfo:
    """Labels for one KB file (kind, title, url); defaults to a plain PDF."""
    return _sources_for(kb).get(file_name, SourceInfo())
