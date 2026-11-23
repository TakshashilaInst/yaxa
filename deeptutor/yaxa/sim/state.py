"""Simulation runs: one JSON file per student run, plus per-scenario settings.

    <data>/yaxa/simulations/<user_id>/<run_id>.json
    <data>/yaxa/simulations/settings.json        {"<scenario>": {"open_all": true}}
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import uuid

from pydantic import BaseModel, Field

from ..store import _read_json, _safe, _write_json, yaxa_root


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Memo(BaseModel):
    day: int  # 1 opening, 3 revised, 5 final
    option: str
    text: str
    stance: str = ""  # day 5: concur | conditions | dissent (with the chair's draft)
    scores: dict[str, dict[str, Any]] = Field(default_factory=dict)  # criterion -> {score, reason}
    override: dict[str, int] = Field(default_factory=dict)  # criterion -> faculty score
    at: str = Field(default_factory=_now)


class Talk(BaseModel):
    role: str  # the actor the student met
    turns: list[dict[str, Any]] = Field(default_factory=list)  # {who: student|actor, content, sources?}


class SimRun(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    user_id: str
    scenario: str
    role: str
    started: str  # IST date the run began, YYYY-MM-DD
    cohort: str | None = None
    stage: int = 1  # the day the student is on; 6 = finished
    positions: dict[str, str] = Field(default_factory=dict)  # Yaxa-played role -> option it backs now
    history: list[dict[str, Any]] = Field(default_factory=list)  # {day, positions, student}
    memos: list[Memo] = Field(default_factory=list)
    talks: list[Talk] = Field(default_factory=list)
    shock: str | None = None
    meeting: list[dict[str, str]] = Field(default_factory=list)  # {speaker, text}
    interventions: int = 0
    draft: dict[str, str] = Field(default_factory=dict)  # chair's draft {option, text}
    outcome: dict[str, Any] = Field(default_factory=dict)  # {option, consequences, debrief, sources}
    created_at: str = Field(default_factory=_now)
    updated_at: str = ""

    def memo(self, day: int) -> Memo | None:
        return next((m for m in self.memos if m.day == day), None)

    def student_option(self) -> str | None:
        return self.memos[-1].option if self.memos else None


def _root() -> Path:
    return yaxa_root() / "simulations"


def _path(user_id: str, run_id: str) -> Path:
    return _root() / _safe(user_id) / f"{_safe(run_id)}.json"


def save_run(run: SimRun) -> None:
    run.updated_at = _now()
    _write_json(_path(run.user_id, run.id), run.model_dump())


def load_run(user_id: str, run_id: str) -> SimRun | None:
    try:
        data = _read_json(_path(user_id, run_id))
    except ValueError:  # unsafe id
        return None
    return SimRun(**data) if data else None


def list_runs(*, user_id: str | None = None, scenario: str | None = None) -> list[SimRun]:
    folder = _root()
    if not folder.is_dir():
        return []
    dirs = [folder / _safe(user_id)] if user_id else [d for d in folder.iterdir() if d.is_dir()]
    runs = []
    for d in dirs:
        for f in sorted(d.glob("*.json")) if d.is_dir() else []:
            data = _read_json(f)
            if data and (scenario is None or data.get("scenario") == scenario):
                runs.append(SimRun(**data))
    return sorted(runs, key=lambda r: r.created_at)


def _settings() -> dict[str, Any]:
    return _read_json(_root() / "settings.json") or {}


def open_all(scenario: str) -> bool:
    return bool(_settings().get(scenario, {}).get("open_all"))


def set_open_all(scenario: str, value: bool) -> None:
    data = _settings()
    data.setdefault(scenario, {})["open_all"] = bool(value)
    _write_json(_root() / "settings.json", data)
