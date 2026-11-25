"""Sending announcement emails to a cohort's group address.

Config lives outside the repo, in ``<DEEPTUTOR_HOME>/secrets/yaxa-mail.json``:
``{"host", "port", "username", "password", "from"}`` (SMTP with STARTTLS, e.g.
Google Workspace with an app password). Without it, Yaxa still posts the
announcement and offers a ready-made email for staff to send themselves.
"""

from __future__ import annotations

from email.message import EmailMessage
import json
import smtplib
from typing import Any

from deeptutor.runtime.home import get_runtime_home


def _config() -> dict[str, Any] | None:
    path = get_runtime_home() / "secrets" / "yaxa-mail.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None
    return data if data.get("host") and data.get("from") else None


def configured() -> bool:
    return _config() is not None


def send(to: str, subject: str, text: str) -> None:
    cfg = _config()
    if not cfg:
        raise RuntimeError("Email is not set up")
    msg = EmailMessage()
    msg["From"] = cfg["from"]
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(text)
    with smtplib.SMTP(cfg["host"], int(cfg.get("port", 587)), timeout=30) as smtp:
        smtp.starttls()
        if cfg.get("username"):
            smtp.login(cfg["username"], cfg.get("password", ""))
        smtp.send_message(msg)
