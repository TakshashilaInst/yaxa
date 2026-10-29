"""Turn a recording into timed, speaker-labelled segments.

Sarvam (batch speech-to-text, ``saaras:v4``) writes the words: it handles
Indian English and Hindi-English mixing better than Zoom. Zoom's own transcript
(.vtt, when staff upload it next to the recording) says who spoke when: each
Sarvam segment takes the Zoom speaker it overlaps most. If Sarvam fails, Zoom's
transcript is used on its own; with neither, the recording waits.

Segments are dicts: {"start": s, "end": s, "text": str, "speaker": str}; speaker
is a Zoom display name, "S0"/"S1"… (Sarvam's anonymous speakers) or "".
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
import re
import subprocess
from typing import Any

logger = logging.getLogger(__name__)

SARVAM_MODEL = "saaras:v4"
CHUNK_SECONDS = 6900.0  # Sarvam's batch limit is 2 h per file; stay under it
MAX_KEYTERMS = 50
_CUE = re.compile(r"(\d+):(\d{2}):(\d{2})[.,](\d{3})\s*-->\s*(\d+):(\d{2}):(\d{2})[.,](\d{3})")
_SPEAKER = re.compile(r"^([^:]{1,60}):\s+(.*)$", re.S)

Segment = dict[str, Any]


class TranscribeError(RuntimeError):
    pass


# ------------------------------------------------------------------- Zoom
def _secs(h: str, m: str, s: str, ms: str) -> float:
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000


def parse_vtt(text: str) -> list[Segment]:
    """Zoom's WebVTT transcript: cues of 'Name: words' become speaker-labelled segments."""
    segments: list[Segment] = []
    for block in re.split(r"\n\s*\n", text.replace("\r\n", "\n")):
        lines = [ln for ln in block.strip().split("\n") if ln.strip()]
        for i, line in enumerate(lines):
            m = _CUE.search(line)
            if not m:
                continue
            body = " ".join(lines[i + 1 :]).strip()
            if not body:
                break
            speaker, words = "", body
            sm = _SPEAKER.match(body)
            if sm:
                speaker, words = sm.group(1).strip(), sm.group(2).strip()
            segments.append({"start": _secs(*m.groups()[:4]), "end": _secs(*m.groups()[4:]), "text": words, "speaker": speaker})
            break
    return segments


# ------------------------------------------------------------------ audio
def chunks_for(duration_s: float, limit_s: float = CHUNK_SECONDS) -> list[tuple[float, float]]:
    out, start = [], 0.0
    while start < duration_s:
        end = min(start + limit_s, duration_s)
        out.append((float(start), float(end)))
        start = end
    return out


def extract_audio(media: Path, out_dir: Path) -> tuple[list[tuple[Path, float]], float]:
    """16 kHz mono mp3 parts under Sarvam's 2-hour limit, with each part's start offset."""
    out_dir.mkdir(parents=True, exist_ok=True)
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(media)],
        capture_output=True, text=True, check=True,
    )
    duration = float(probe.stdout.strip() or 0)
    parts = []
    for n, (start, end) in enumerate(chunks_for(duration)):
        part = out_dir / f"chunk_{n:03d}.mp3"
        subprocess.run(
            ["ffmpeg", "-nostdin", "-y", "-loglevel", "error", "-ss", str(start), "-t", str(end - start),
             "-i", str(media), "-vn", "-ac", "1", "-ar", "16000", "-b:a", "48k", str(part)],
            check=True,
        )
        parts.append((part, start))
    return parts, duration


# ----------------------------------------------------------------- Sarvam
def _segments_from_output(data: dict, offset: float) -> list[Segment]:
    entries = (data.get("diarized_transcript") or {}).get("entries") or []
    if entries:
        return [
            {"start": float(e["start_time_seconds"]) + offset, "end": float(e["end_time_seconds"]) + offset,
             "text": str(e.get("transcript", "")).strip(), "speaker": f"S{e.get('speaker_id', '')}"}
            for e in entries if str(e.get("transcript", "")).strip()
        ]
    ts = data.get("timestamps") or {}
    return [
        {"start": float(s) + offset, "end": float(e) + offset, "text": str(t).strip(), "speaker": ""}
        for t, s, e in zip(ts.get("chunks") or [], ts.get("start_time_seconds") or [], ts.get("end_time_seconds") or [])
        if str(t).strip()
    ]


def sarvam_transcribe(chunks: list[tuple[Path, float]], keyterms: list[str], api_key: str, *,
                      client: Any = None, work: Path | None = None) -> list[Segment]:
    """One Sarvam batch job for all parts (≤20 per job); returns segments on the recording's clock."""
    if client is None:
        from sarvamai import SarvamAI

        client = SarvamAI(api_subscription_key=api_key)
    terms = [t[:64] for t in dict.fromkeys(k.strip() for k in keyterms if k and k.strip())][:MAX_KEYTERMS]
    out_dir = (work or chunks[0][0].parent) / "sarvam-out"
    out_dir.mkdir(parents=True, exist_ok=True)
    segments: list[Segment] = []
    for batch_start in range(0, len(chunks), 20):
        batch = chunks[batch_start : batch_start + 20]
        job = client.speech_to_text_job.create_job(
            model=SARVAM_MODEL, mode="transcribe", language_code="en-IN", with_diarization=True, keyterms=terms,
        )
        job.upload_files(file_paths=[str(p) for p, _ in batch], timeout=900)  # ~40 MB per 2-hour part
        job.start()
        status = job.wait_until_complete(poll_interval=15, timeout=4 * 3600)
        if str(getattr(status, "job_state", "completed")).lower() == "failed":
            raise TranscribeError("Sarvam job failed")
        job.download_outputs(output_dir=str(out_dir))
        for part, offset in batch:
            out = out_dir / f"{part.name}.json"  # the SDK saves each result as "<input file>.json"
            if not out.is_file():
                raise TranscribeError(f"Sarvam returned no transcript for part {part.name}")
            segments += _segments_from_output(json.loads(out.read_text()), offset)
            out.unlink()
    return segments


# ---------------------------------------------------------------- merging
def merge_speakers(sarvam: list[Segment], zoom: list[Segment]) -> list[Segment]:
    """Give each Sarvam segment the Zoom speaker whose cues overlap it most ("" if none)."""
    out = []
    for seg in sarvam:
        overlap: dict[str, float] = {}
        for cue in zoom:
            if cue["end"] <= seg["start"] or cue["start"] >= seg["end"] or not cue["speaker"]:
                continue
            overlap[cue["speaker"]] = overlap.get(cue["speaker"], 0.0) + (
                min(cue["end"], seg["end"]) - max(cue["start"], seg["start"])
            )
        out.append(seg | {"speaker": max(overlap, key=overlap.get) if overlap else ""})
    return out


def transcribe(media: Path, vtt: Path | None, keyterms: list[str], api_key: str | None,
               work: Path) -> tuple[list[Segment], str]:
    """(segments, engine) with engine "sarvam+zoom", "sarvam" or "zoom"."""
    zoom = parse_vtt(vtt.read_text(encoding="utf-8", errors="replace")) if vtt and vtt.is_file() else []
    if api_key:
        try:
            chunks, _ = extract_audio(media, work / "audio")
            words = sarvam_transcribe(chunks, keyterms, api_key, work=work)
            if words:
                return (merge_speakers(words, zoom), "sarvam+zoom") if zoom else (words, "sarvam")
        except Exception as exc:  # fall back to Zoom's transcript when there is one
            logger.warning("yaxa library: Sarvam failed for %s: %s", media.name, type(exc).__name__)
            if not zoom:
                raise TranscribeError(f"Sarvam failed ({type(exc).__name__}) and there's no Zoom transcript") from exc
    if zoom:
        return zoom, "zoom"
    raise TranscribeError("no Sarvam key and no Zoom transcript")
