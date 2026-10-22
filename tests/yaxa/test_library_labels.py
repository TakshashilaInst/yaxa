"""Source labels the library sync writes: retired files and a cache that follows edits."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest

from deeptutor.yaxa import catalog, grounding


def _write(root: Path, kb: str, body: str) -> Path:
    path = root / "sources" / f"{kb}.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body)
    return path


def test_label_cache_sees_edits_from_another_process(override_dir: Path) -> None:
    path = _write(override_dir, "ZZ", "files:\n  a.pdf: {title: One}\n")
    assert catalog.source_info("ZZ", "a.pdf").title == "One"
    path.write_text("files:\n  a.pdf: {title: Two, retired: true, drive_id: d1}\n")
    os.utime(path, ns=(path.stat().st_atime_ns, path.stat().st_mtime_ns + 1_000_000))
    info = catalog.source_info("ZZ", "a.pdf")
    assert (info.title, info.retired, info.drive_id) == ("Two", True, "d1")


def test_retrieve_skips_retired_files(override_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write(override_dir, "ZZ", "files:\n  old.pdf: {kind: note, retired: true}\n  new.pdf: {kind: note}\n")
    body = "word " * 40

    class FakeRAG:
        def __init__(self, **_: object) -> None:
            pass

        async def search(self, **_: object) -> dict:
            return {"sources": [{"source": "old.pdf", "text": body}, {"source": "new.pdf", "text": body}]}

    monkeypatch.setattr(grounding, "RAGService", FakeRAG)
    files = [p["file"] for p in asyncio.run(grounding.retrieve("ZZ", "q", 5))]
    assert files == ["new.pdf"]


def test_library_settings_default() -> None:
    lib = catalog.get_catalog(fresh=True).settings.library
    assert lib.max_audio_hours_per_sync == 20 and lib.root_folder_id.startswith("1lDJ")
