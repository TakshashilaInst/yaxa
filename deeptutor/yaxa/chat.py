"""Cohort life, step 4: a light chat for each cohort, and one for each track.

Channels are the cohort (``GCPP45``) and its tracks (``GCPP45.DFA``). A learner
sees their cohort's channel and their own track's; staff see all of a cohort's.
No direct messages. A message may carry one image (JPEG, PNG or WebP, up to 5 MB): it is
re-encoded on upload, which proves it is an image and drops camera and location details,
and it is served only to people who can see the channel. Learners can edit or delete their
own message for 15 minutes; staff can hide any. When the cohort closes, its chat becomes
read-only. Stored in ``<data>/yaxa/chat/<CHANNEL>.jsonl`` and images in
``<data>/yaxa/chat-files/<CHANNEL>/``; never indexed.
"""

from __future__ import annotations

from io import BytesIO
import re

from fastapi import APIRouter, HTTPException, UploadFile
from fastapi.responses import FileResponse
from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import BaseModel

from . import community
from .catalog import get_catalog

router = APIRouter()

MAX_TEXT = 2000
PER_HOUR = 30
PAGE = 200


MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_PIXELS = 40_000_000  # refuse decompression bombs before decoding
MAX_SIDE = 2000  # larger photos are scaled down
IMAGES_PER_HOUR = 20
FORMATS = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp"}
_IMAGE_NAME = re.compile(r"^[A-Za-z0-9_-]{6,64}\.(jpg|png|webp)$")


class Text(BaseModel):
    text: str = ""
    image: str = ""


def _path(channel: str):
    return community.root("chat", f"{channel}.jsonl")


def _image_path(channel: str, name: str):
    return community.root("chat-files", channel) / name


def _tracks(programme: str) -> list[tuple[str, str]]:
    prog = get_catalog().programme(programme)
    return [(t.code, t.name) for t in prog.tracks] if prog else []


def _channels(v: community.Viewer) -> list[dict]:
    c = v.cohort
    if not c:
        return []
    out = [{"id": c.code, "name": f"{c.code} · everyone"}]
    for code, name in _tracks(c.programme):
        if v.staff or v.track == code:
            out.append({"id": f"{c.code}.{code}", "name": f"{name}"})
    return out


def _open(channel: str, cohort: str | None, *, write: bool = False) -> community.Viewer:
    # learners always get their own cohort; staff get the one the channel belongs to
    v = community.viewer(cohort or channel.split(".")[0])
    if channel not in {c["id"] for c in _channels(v)}:
        raise HTTPException(403, "You can't see this chat")
    if write and v.cohort and v.cohort.closed:
        raise HTTPException(403, f"{v.cohort.code} is closed; its chat is read-only")
    return v


def _view(m: dict, v: community.Viewer) -> dict:
    return {k: m.get(k) for k in ("id", "author", "staff", "text", "created_at", "edited")} | {
        "image": m.get("image") or "", "mine": m["author_id"] == v.uid}


@router.get("/chat/channels")
async def channels(cohort: str | None = None) -> list[dict]:
    return _channels(community.viewer(cohort))


@router.get("/chat/{channel}")
async def messages(channel: str, after: str = "", cohort: str | None = None) -> dict:
    v = _open(channel, cohort)
    rows = [m for m in community.read_jsonl(_path(channel)) if not m.get("hidden")]
    if after:
        idx = next((i for i, m in enumerate(rows) if m["id"] == after), None)
        rows = rows[idx + 1:] if idx is not None else rows
    return {"messages": [_view(m, v) for m in rows[-PAGE:]], "closed": bool(v.cohort and v.cohort.closed), "me": v.uid}


@router.post("/chat/{channel}")
async def post(channel: str, body: Text, cohort: str | None = None) -> dict:
    v = _open(channel, cohort, write=True)
    image = body.image.strip()
    if image and (not _IMAGE_NAME.match(image) or not _image_path(channel, image).exists()):
        raise HTTPException(400, "That image isn't uploaded to this chat")
    text = community.clean_text(body.text, MAX_TEXT) if (body.text.strip() or not image) else ""
    if not community.rate_ok(v.uid, "chat", PER_HOUR):
        raise HTTPException(429, "You've sent a lot of messages this hour. Try again a little later.")
    row = {"id": community.new_id(), "author_id": v.uid, "author": v.name, "staff": v.staff, "text": text,
           "image": image, "created_at": community.now_iso(), "edited": False, "hidden": False}
    community.append_jsonl(_path(channel), row)
    return _view(row, v)


def _change(channel: str, mid: str, v: community.Viewer, fn) -> dict:
    found: dict = {}

    def apply(rows):
        for m in rows:
            if m["id"] == mid and not m.get("hidden"):
                if not v.staff:
                    if m["author_id"] != v.uid:
                        raise HTTPException(403, "You can only change your own message")
                    if community.age_seconds(m["created_at"]) > community.EDIT_WINDOW:
                        raise HTTPException(403, "Messages can be changed only in the first 15 minutes")
                fn(m)
                found["m"] = m
        return rows

    community.rewrite_jsonl(_path(channel), apply)
    if not found:
        raise HTTPException(404, "No such message")
    return found["m"]


@router.patch("/chat/{channel}/{mid}")
async def edit(channel: str, mid: str, body: Text, cohort: str | None = None) -> dict:
    v = _open(channel, cohort, write=True)
    text = community.clean_text(body.text, MAX_TEXT)
    return _view(_change(channel, mid, v, lambda m: m.update(text=text, edited=True)), v)


@router.delete("/chat/{channel}/{mid}")
async def remove(channel: str, mid: str, cohort: str | None = None) -> dict:
    v = _open(channel, cohort)
    _change(channel, mid, v, lambda m: m.update(hidden=True))
    return {"ok": True}


@router.post("/chat/{channel}/image")
async def upload_image(channel: str, file: UploadFile, cohort: str | None = None) -> dict:
    """Store one image for a message in this channel; the message itself is posted separately."""
    v = _open(channel, cohort, write=True)
    data = await file.read(MAX_IMAGE_BYTES + 1)
    if len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(413, "That image is over 5 MB. Try a smaller one or a screenshot.")
    if not community.rate_ok(v.uid, "chat-image", IMAGES_PER_HOUR):
        raise HTTPException(429, "You've shared a lot of images this hour. Try again a little later.")
    try:
        with Image.open(BytesIO(data)) as probe:
            fmt = probe.format or ""
            if probe.width * probe.height > MAX_PIXELS:
                raise HTTPException(400, "That image is too large to show")
        if fmt not in FORMATS:
            raise HTTPException(400, "Share a JPEG, PNG or WebP image")
        with Image.open(BytesIO(data)) as img:
            img = ImageOps.exif_transpose(img)  # keep the photo upright once orientation data is gone
            img.thumbnail((MAX_SIDE, MAX_SIDE))
            if fmt == "JPEG" and img.mode not in ("RGB", "L"):
                img = img.convert("RGB")
            out = BytesIO()
            img.save(out, fmt)  # a fresh encode: no EXIF, GPS or other metadata carried over
    except (UnidentifiedImageError, OSError, ValueError):
        raise HTTPException(400, "That file isn't an image Yaxa can read") from None
    name = f"{community.new_id()}.{FORMATS[fmt]}"
    path = _image_path(channel, name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(out.getvalue())
    return {"image": name}


@router.get("/chat/{channel}/image/{name}")
async def image(channel: str, name: str, cohort: str | None = None) -> FileResponse:
    if not _IMAGE_NAME.match(name):
        raise HTTPException(404, "No such image")
    _open(channel, cohort)
    path = _image_path(channel, name)
    if not path.exists():
        raise HTTPException(404, "No such image")
    return FileResponse(path, headers={"Cache-Control": "private, max-age=86400", "X-Content-Type-Options": "nosniff"})
