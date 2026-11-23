"""Simulation scenarios, one YAML file each in content/simulations/.

A server copy in <data>/yaxa/content/simulations/ overrides the packaged one,
so faculty can edit a scenario without a rebuild.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import BaseModel, Field

from ..catalog import _list_yaml, _read_yaml


class Option(BaseModel):
    id: str  # A, B, C, D
    label: str
    summary: str


class Role(BaseModel):
    id: str  # short slug, e.g. "finance"
    name: str  # institution, e.g. "Finance Department"
    mandate: str  # who you are
    wants: str  # primary objective
    secondary: str  # what you'd accept instead
    red_line: str
    private: str  # what only this actor knows
    batna: str  # what happens to you with no agreement
    opening: str  # suggested opening move
    leans: str = ""  # option this actor starts closest to


class Shock(BaseModel):
    id: str
    when: list[str]  # option ids the room leans to, or ["any"]
    headline: str
    body: str


class Scenario(BaseModel):
    id: str
    title: str
    tagline: str
    module: str  # module whose students may play it
    libraries: list[str]  # KBs actors and the debrief draw passages from
    setting: str = ""  # one line: where and when
    brief: str  # shared brief, Markdown
    decision: str  # the question the group must answer
    options: list[Option]
    default_option: str  # what happens with no recommendation
    chair: str  # role id that chairs the Day 4 meeting
    body: str = "the group"  # e.g. "the inter-ministerial group"
    decider: str = "the Cabinet"  # who takes the final decision
    roles: list[Role]
    shocks: list[Shock]
    answer_key: str  # real history and takeaways; only for the debrief and faculty
    days: list[str] = Field(default_factory=lambda: ["Briefing", "Corridor talks", "Shock", "The meeting", "Decision"])

    def role(self, role_id: str) -> Role | None:
        return next((r for r in self.roles if r.id == role_id), None)

    def option(self, option_id: str) -> Option | None:
        return next((o for o in self.options if o.id == option_id), None)


@lru_cache(maxsize=1)
def load_scenarios() -> dict[str, Scenario]:
    out: dict[str, Scenario] = {}
    for rel in _list_yaml("simulations"):
        s = Scenario(**_read_yaml(rel))
        out[s.id] = s
    return out


def get_scenario(scenario_id: str) -> Scenario | None:
    return load_scenarios().get(scenario_id)
