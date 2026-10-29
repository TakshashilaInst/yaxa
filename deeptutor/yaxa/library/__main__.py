"""Library sync commands (run as the yaxa user with DEEPTUTOR_HOME set).

    python -m deeptutor.yaxa.library sync [--dry-run]   one run now
    python -m deeptutor.yaxa.library seed <ledger.json> mark files already indexed as live
    python -m deeptutor.yaxa.library status             counts by status
    python -m deeptutor.yaxa.library worker             the service: nightly, or when the page asks

Secrets live in <DEEPTUTOR_HOME>/secrets/: drive-service-account.json,
sarvam.env (read by systemd as EnvironmentFile), student-names.txt.
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timedelta, timezone
import json
import logging
import os
from pathlib import Path
import time

from .. import catalog
from . import drive, sync
from .ledger import Ledger, seed
from .redaction import student_names

IST = timezone(timedelta(hours=5, minutes=30))
logger = logging.getLogger("deeptutor.yaxa.library")


def secrets_dir() -> Path:
    return Path(os.environ.get("DEEPTUTOR_HOME", Path.home())) / "secrets"


def _roster() -> list[str]:
    """Display names and logins of Yaxa accounts (students' own names)."""
    from deeptutor.multi_user.identity import load_users

    from .. import store

    names = [u.display_name for u in store.list_users() if u.role != "faculty" and u.display_name]
    names += [login.split("@")[0] for login, rec in (load_users() or {}).items() if rec.get("role") != "admin"]
    return names


def real_deps() -> sync.Deps:
    svc = drive.service(secrets_dir() / "drive-service-account.json")
    root_id = catalog.get_catalog(fresh=True).settings.library.root_folder_id
    public_file = sync.library_root() / "public-names.json"
    return sync.Deps(
        walk=lambda: drive.walk(svc, root_id),
        download=lambda file_id, dest: drive.download(svc, file_id, dest),
        transcribe=_transcribe,
        kb_add=sync.kb_add,
        students=lambda: student_names(secrets_dir() / "student-names.txt", _roster(),
                                       sync.library_root() / "private" / "learned-names.txt"),
        public=lambda: json.loads(public_file.read_text()) if public_file.is_file() else {"full": [], "single": [], "other": []},
        api_key=os.environ.get("SARVAM_API_KEY") or None,
    )


def _transcribe(*args, **kwargs):
    from .transcribe import transcribe

    return transcribe(*args, **kwargs)


def due(now_utc: datetime, last_finished: str, hour_ist: int) -> bool:
    """True once per night, the first time we look after `hour_ist` (IST)."""
    local = now_utc.astimezone(IST)
    tonight = local.replace(hour=hour_ist, minute=0, second=0, microsecond=0)
    if local < tonight:
        return False
    if not last_finished:
        return True
    return datetime.fromisoformat(last_finished).astimezone(IST) < tonight


def _last_finished() -> str:
    path = sync.library_root() / "last_run.json"
    try:
        return json.loads(path.read_text()).get("finished", "")
    except (FileNotFoundError, ValueError):
        return ""


def worker() -> None:
    request = sync.library_root() / "request"
    logger.info("yaxa library worker started")
    while True:
        hour = catalog.get_catalog(fresh=True).settings.library.nightly_hour_ist
        asked = request.exists()
        if asked or due(datetime.now(timezone.utc), _last_finished(), hour):
            request.unlink(missing_ok=True)
            try:
                logger.info("yaxa library sync: %s", sync.run(real_deps()))
            except Exception:
                logger.exception("yaxa library sync failed")
                (sync.library_root() / "last_run.json").write_text(json.dumps(
                    {"finished": datetime.now(timezone.utc).isoformat(timespec="seconds"), "error": "sync failed; see the service log"}))
        time.sleep(30)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser(prog="python -m deeptutor.yaxa.library")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("sync").add_argument("--dry-run", action="store_true")
    sub.add_parser("seed").add_argument("fill_ledger", type=Path)
    sub.add_parser("status")
    sub.add_parser("worker")
    args = ap.parse_args()
    if args.cmd == "sync":
        print(json.dumps(sync.run(real_deps(), dry_run=args.dry_run)))
    elif args.cmd == "seed":
        deps = real_deps()
        md5s = {f.id: f.md5 for f in deps.walk()}
        led = Ledger(sync.library_root() / "ledger.json").load()
        n = seed(led, json.loads(args.fill_ledger.read_text()), md5s)
        led.save()
        print(f"seeded {n} files as live ({len(led.entries)} in the ledger)")
    elif args.cmd == "status":
        led = Ledger(sync.library_root() / "ledger.json").load()
        print(json.dumps(Counter(e.status for e in led.entries.values())))
    else:
        worker()


if __name__ == "__main__":
    main()
