"""Seed Yaxa Learn's demo: sample students with learner profiles, enrolled in a programme.

The sample profiles are pseudonymised but describe real Takshashila students, so
they are NOT kept in the repo. Pass the JSON file (kept on the server only):

    DEEPTUTOR_HOME=~/yaxa-home .venv/bin/python scripts/yaxa/seed_demo.py \\
        ~/yaxa-home/data/yaxa/seed/demo_students.json --programme GCPP --track TP

JSON: [{"username", "name", "avatar": {...}, "profile": {<store.PROFILE_FIELDS>}}].
Idempotent: existing accounts keep their password; profile and enrolment are refreshed.
Demo accounts get random passwords nobody needs: the admin enters them from /learn/demo.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import secrets

from deeptutor.multi_user.identity import load_users
from deeptutor.services.auth import add_user
from deeptutor.yaxa import store
from deeptutor.yaxa.catalog import get_catalog


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("students_json", type=Path)
    ap.add_argument("--programme", default="GCPP")
    ap.add_argument("--track", default="TP")
    args = ap.parse_args()

    prog = get_catalog().programme(args.programme)
    if not prog:
        raise SystemExit(f"unknown programme {args.programme}")
    track = args.track if prog.tracks else None

    for item in json.loads(args.students_json.read_text(encoding="utf-8")):
        username = item["username"]
        if username not in load_users():
            add_user(username, secrets.token_urlsafe(18), role="user", preset="standard")
        user_id = str(load_users()[username]["id"])
        user = store.load_user(user_id)
        user.display_name = item["name"]
        user.demo = True
        user.role = "student"
        user.avatar = item.get("avatar") or {}
        user.profile = store.clean_profile(item.get("profile") or {})
        user.enrolments = [store.Enrolment(programme=prog.code, track=track)]
        store.save_user(user)
        print(f"{username:16} {user_id}  {prog.code}{'/' + track if track else ''}")


if __name__ == "__main__":
    main()
