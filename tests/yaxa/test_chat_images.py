"""Images in the cohort chat: upload, attach to a message, served only to people who can see the channel."""

from __future__ import annotations

import asyncio
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

from fastapi import HTTPException
from PIL import Image
import pytest
from starlette.datastructures import UploadFile

from deeptutor.yaxa import catalog, chat, community, schedule, store
from deeptutor.yaxa.schedule import Cohort


@pytest.fixture(autouse=True)
def _tmp_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEEPTUTOR_HOME", str(tmp_path))
    catalog.get_catalog(fresh=True)
    community._RATE.clear()
    schedule.save_cohort(Cohort(code="GCPP45", programme="GCPP"))
    for uid, track in (("asha", "DFA"), ("ravi", "TP")):
        u = store.load_user(uid, display_name=uid.title())
        u.enrolments = [store.Enrolment(programme="GCPP", track=track, cohort="GCPP45")]
        store.save_user(u)
    yield
    catalog.get_catalog(fresh=True)


def as_(monkeypatch, uid, staff=False):
    monkeypatch.setattr(community, "_me", lambda: (SimpleNamespace(id=uid, is_admin=staff), store.load_user(uid)))


def picture(fmt="PNG", size=(40, 30), exif=False) -> bytes:
    buf = BytesIO()
    img = Image.new("RGB", size, (98, 13, 60))
    if exif:
        ex = Image.Exif()
        ex[0x010F] = "SecretCamera"  # Make
        img.save(buf, fmt, exif=ex)
    else:
        img.save(buf, fmt)
    return buf.getvalue()


def upload(channel, data, name="a.png"):
    return asyncio.run(chat.upload_image(channel, UploadFile(file=BytesIO(data), filename=name), None))


def test_upload_then_attach_to_a_message(monkeypatch):
    as_(monkeypatch, "asha")
    up = upload("GCPP45", picture())
    assert up["image"].endswith(".png")
    m = asyncio.run(chat.post("GCPP45", chat.Text(text="", image=up["image"]), None))
    assert m["image"] == up["image"] and m["text"] == ""
    msgs = asyncio.run(chat.messages("GCPP45", "", None))["messages"]
    assert msgs[-1]["image"] == up["image"]


def test_message_needs_text_or_image(monkeypatch):
    as_(monkeypatch, "asha")
    with pytest.raises(HTTPException):
        asyncio.run(chat.post("GCPP45", chat.Text(text="  "), None))


def test_attaching_an_unknown_image_is_400(monkeypatch):
    as_(monkeypatch, "asha")
    with pytest.raises(HTTPException) as e:
        asyncio.run(chat.post("GCPP45", chat.Text(text="hi", image="nope.png"), None))
    assert e.value.status_code == 400


def test_not_an_image_is_400(monkeypatch):
    as_(monkeypatch, "asha")
    with pytest.raises(HTTPException) as e:
        upload("GCPP45", b"%PDF-1.4 not a picture", "x.png")
    assert e.value.status_code == 400


def test_too_big_is_413(monkeypatch):
    as_(monkeypatch, "asha")
    monkeypatch.setattr(chat, "MAX_IMAGE_BYTES", 100)
    with pytest.raises(HTTPException) as e:
        upload("GCPP45", picture(size=(200, 200)))
    assert e.value.status_code == 413


def test_camera_details_are_dropped(monkeypatch):
    as_(monkeypatch, "asha")
    up = upload("GCPP45", picture("JPEG", exif=True), "p.jpg")
    saved = chat._image_path("GCPP45", up["image"])
    assert b"SecretCamera" not in saved.read_bytes()


def test_served_only_to_people_who_see_the_channel(monkeypatch):
    as_(monkeypatch, "asha")
    up = upload("GCPP45.DFA", picture())
    resp = asyncio.run(chat.image("GCPP45.DFA", up["image"], None))
    assert Path(resp.path).exists()
    as_(monkeypatch, "ravi")  # TP track: can't see the DFA channel
    with pytest.raises(HTTPException) as e:
        asyncio.run(chat.image("GCPP45.DFA", up["image"], None))
    assert e.value.status_code == 403


def test_path_tricks_are_404(monkeypatch):
    as_(monkeypatch, "asha")
    with pytest.raises(HTTPException) as e:
        asyncio.run(chat.image("GCPP45", "../../users/asha.json", None))
    assert e.value.status_code == 404
