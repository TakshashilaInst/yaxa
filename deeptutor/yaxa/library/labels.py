"""Source labels the library sync writes into ``<data>/yaxa/content/sources/<KB>.yaml``.

Entries the sync didn't create (hand-written titles, faculty article URLs) are
kept: ``upsert(..., keep_curated=True)`` only fills in what's missing.
"""

from __future__ import annotations

from contextlib import contextmanager
import os
import tempfile
from typing import Any, Iterator

import yaml

from ..catalog import PACKAGE_CONTENT, sources_path

CURATED = ("title", "url", "byline", "kind", "corpus")
_batch: dict[str, dict[str, Any]] | None = None  # kb -> labels, while a sync run batches its writes
_dirty: set[str] = set()


@contextmanager
def batch() -> Iterator[None]:
    """Hold label changes in memory and write each library's file once at the end."""
    global _batch
    _batch = {}
    _dirty.clear()
    try:
        yield
    finally:
        pending, _batch = _batch, None
        for kb in sorted(_dirty):
            _save(kb, pending[kb])
        _dirty.clear()


def _load(kb: str) -> dict[str, Any]:
    if _batch is not None and kb in _batch:
        return _batch[kb]
    data = _read(kb)
    if _batch is not None:
        _batch[kb] = data
    return data


def _store(kb: str, data: dict[str, Any]) -> None:
    if _batch is not None:
        _dirty.add(kb)
    else:
        _save(kb, data)


def _read(kb: str) -> dict[str, Any]:
    for path in (sources_path(kb), PACKAGE_CONTENT / "sources" / f"{kb}.yaml"):
        if path.is_file():
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            data.setdefault("files", {})
            return data
    return {"files": {}}


def _save(kb: str, data: dict[str, Any]) -> None:
    path = sources_path(kb)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{kb}-")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        yaml.safe_dump(data, fh, sort_keys=False, allow_unicode=True, width=140)
    os.replace(tmp, path)


def upsert(kb: str, name: str, info: dict[str, Any], *, keep_curated: bool = False) -> None:
    data = _load(kb)
    old = data["files"].get(name) or {}
    new = dict(old)
    for key, value in info.items():
        if keep_curated and key in CURATED and old.get(key):
            continue
        if key == "unit" and value and str(old.get("unit", "")).startswith(value) and old["unit"] != value:
            continue  # a session tag set by hand (CS22) is more specific than the folder's course code (CS2)
        new[key] = value
    new.pop("retired", None)
    data["files"][name] = new
    _store(kb, data)


def names(kb: str) -> list[str]:
    """Every file name the library's labels know, retired ones included."""
    return list(_load(kb)["files"])


def retire(kb: str, name: str) -> None:
    data = _load(kb)
    data["files"].setdefault(name, {})["retired"] = True
    _store(kb, data)
