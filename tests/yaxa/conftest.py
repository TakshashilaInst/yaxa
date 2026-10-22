"""Shared fixtures for Yaxa tests: a throwaway data folder per test."""

from __future__ import annotations

from pathlib import Path

import pytest

from deeptutor.yaxa import catalog


@pytest.fixture
def override_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Server-side content folder (<data>/yaxa/content) in a temp dir."""
    monkeypatch.setenv("DEEPTUTOR_HOME", str(tmp_path))
    root = catalog.override_root()
    root.mkdir(parents=True, exist_ok=True)
    catalog.get_catalog(fresh=True)
    yield root
    catalog.get_catalog(fresh=True)
