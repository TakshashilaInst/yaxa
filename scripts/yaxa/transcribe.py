"""Transcribe a Takshashila webinar recording into a timestamped Markdown file
that Yaxa can index, cite and link back to the recording.

Runs locally on Apple Silicon with mlx-whisper (free; no audio leaves the Mac):
    uv tool install mlx-whisper   # once
    ~/.local/share/uv/tools/mlx-whisper/bin/python scripts/yaxa/transcribe.py \\
        recording.mp4 out_dir --title "CP21 Introduction to Economic Reasoning" \\
        --speaker "Anupam Manur" --module GCPP-ER1 --unit U01 --cohort "GCPP44 (May 2026)" \\
        --url "https://drive.google.com/file/d/<id>/view"

Output: <out_dir>/<slug>.md (header + paragraphs stamped [hh:mm:ss]) and
<slug>.segments.json (raw Whisper segments, for re-chunking later).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import time

MODEL = "mlx-community/whisper-large-v3-turbo"

# Words Whisper otherwise mangles in Indian policy talk. Whisper treats the
# prompt as "previous text", so a natural sentence works better than a list.
VOCAB_PROMPT = (
    "A Takshashila Institution webinar on Indian public policy, in Indian English. "
    "Nitin Pai, Pranay Kotasthane, Anupam Manur, Sarthak Pradhan, Ameya Naik, Ashish Kulkarni "
    "discuss Kautilya's Arthashastra, the Lok Sabha and Rajya Sabha, panchayats, the RBI, GST, "
    "the Finance Commission, NITI Aayog, MGNREGA, the Union and State Lists, crore and lakh rupees."
)

PARAGRAPH_SECONDS = 60  # start a new timestamped paragraph about once a minute


def hms(seconds: float) -> str:
    s = int(seconds)
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"


def slugify(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-")[:90]


def paragraphs(segments: list[dict]) -> list[tuple[float, str]]:
    """Group Whisper segments into ~1-minute paragraphs, keeping start times."""
    out: list[tuple[float, str]] = []
    start, buf = None, []
    for seg in segments:
        text = seg["text"].strip()
        if not text:
            continue
        if start is None:
            start = seg["start"]
        buf.append(text)
        if seg["end"] - start >= PARAGRAPH_SECONDS and text.endswith((".", "?", "!")):
            out.append((start, " ".join(buf)))
            start, buf = None, []
    if buf:
        out.append((start or 0.0, " ".join(buf)))
    return out


def drop_repetition(segments: list[dict]) -> list[dict]:
    """Whisper sometimes loops on silence ("Thank you. Thank you. ..."); drop repeats."""
    cleaned, last, repeats = [], None, 0
    for seg in segments:
        text = seg["text"].strip()
        repeats = repeats + 1 if text == last else 0
        last = text
        if repeats < 2:
            cleaned.append(seg)
    return cleaned


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("media", type=Path)
    ap.add_argument("out_dir", type=Path)
    ap.add_argument("--title", required=True)
    ap.add_argument("--speaker", default="")
    ap.add_argument("--module", default="")
    ap.add_argument("--unit", default="")
    ap.add_argument("--cohort", default="")
    ap.add_argument("--url", default="")
    args = ap.parse_args()

    import mlx_whisper  # imported late so --help works without the model

    t0 = time.time()
    result = mlx_whisper.transcribe(
        str(args.media),
        path_or_hf_repo=MODEL,
        language="en",
        initial_prompt=VOCAB_PROMPT,
        condition_on_previous_text=False,  # avoids long hallucination loops
        verbose=None,
    )
    segments = drop_repetition(result["segments"])
    duration = segments[-1]["end"] if segments else 0.0

    args.out_dir.mkdir(parents=True, exist_ok=True)
    slug = slugify(args.title)
    header = [
        f"# Webinar transcript: {args.title}",
        "",
        f"- Speaker: {args.speaker or 'Takshashila faculty'}",
        f"- Cohort: {args.cohort}" if args.cohort else "",
        f"- Module: {args.module}{' · ' + args.unit if args.unit else ''}" if args.module else "",
        f"- Recording: {args.url}" if args.url else "",
        f"- Length: {hms(duration)}",
        "- Machine transcript (Whisper). Names and numbers may be misheard; check the recording before quoting.",
        "",
    ]
    body = [f"[{hms(start)}] {text}\n" for start, text in paragraphs(segments)]
    (args.out_dir / f"{slug}.md").write_text(
        "\n".join(line for line in header if line is not None) + "\n" + "\n".join(body), encoding="utf-8"
    )
    (args.out_dir / f"{slug}.segments.json").write_text(
        json.dumps([{k: s[k] for k in ("start", "end", "text")} for s in segments], ensure_ascii=False),
        encoding="utf-8",
    )
    took = time.time() - t0
    print(f"{slug}: {hms(duration)} audio in {took / 60:.1f} min ({duration / max(took, 1):.1f}x realtime)")


if __name__ == "__main__":
    main()
