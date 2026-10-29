"""Remove student names from a webinar transcript before it is indexed.

Takshashila policy (Pranay, 2026-10-12): student NAMES never enter Yaxa's
libraries. Student questions and comments stay; they are part of the class.

Default: names only. Optional --lecturer-only also drops every voice but the
lecturer's (not used by default):

1. Speakers. Whisper doesn't know who spoke, so each transcript segment gets a
   voice fingerprint (SpeechBrain ECAPA). The lecturer is the dominant voice:
   start from the duration-weighted average, keep segments close to it, refine.
   Everything else (student questions, comments, clips played in class) is
   dropped and marked "[participant discussion omitted]".
2. Names. In what remains, people's names are kept only if they are public
   figures (they appear as a full name in the course readings or faculty
   writing) or faculty; any other name becomes "a participant".

    uv run --no-project --with speechbrain --with torchaudio --with soundfile \\
      --with scikit-learn --with spacy --with <en_core_web_sm wheel> \\
      python scripts/yaxa/redact_transcript.py known-names <dir>... --out names.json
    ... python scripts/yaxa/redact_transcript.py redact segments.json header.md out.md \\
      --names names.json --keep "Anupam Manur"
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys

LECTURER_SIM = 0.45  # cosine similarity to the lecturer's voice needed to keep a segment
MIN_EMBED_SECONDS = 1.0
OMIT_NOTE = "[participant discussion omitted]"
# Shared with the server-side library sync (deeptutor/yaxa/library/redaction.py).
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from deeptutor.yaxa.library.redaction import (  # noqa: E402
    CONCEPTS,
    FACULTY,
    NOT_NAMES,
    _dictionary,
    _nlp,
    build_known_names,
    hms,
    paragraphs,
    redact_names,
    removed_names,
)


# ------------------------------------------------------------------ speakers
def lecturer_mask(segments: list[dict], audio: Path) -> list[bool]:
    import numpy as np
    import soundfile as sf
    from speechbrain.inference.speaker import EncoderClassifier
    import torch

    wav, sr = sf.read(str(audio), dtype="float32")
    enc = EncoderClassifier.from_hparams(
        source="speechbrain/spkrec-ecapa-voxceleb",
        savedir=str(Path.home() / ".cache" / "yaxa-ecapa"),
        run_opts={"device": "cpu"},
    )
    emb: dict[int, np.ndarray] = {}
    for i, seg in enumerate(segments):
        dur = seg["end"] - seg["start"]
        if dur < MIN_EMBED_SECONDS:
            continue
        mid = (seg["start"] + seg["end"]) / 2
        a, b = int(max(seg["start"], mid - 5) * sr), int(min(seg["end"], mid + 5) * sr)
        b = min(b, len(wav))
        if b - a < int(0.5 * sr):  # timestamps past the end of the audio, or too short
            continue
        with torch.no_grad():
            e = enc.encode_batch(torch.from_numpy(wav[a:b]).unsqueeze(0)).squeeze().numpy()
        emb[i] = e / (np.linalg.norm(e) + 1e-9)

    idx = list(emb)
    vecs = np.stack([emb[i] for i in idx])
    weights = np.array([segments[i]["end"] - segments[i]["start"] for i in idx])
    centroid = (vecs * weights[:, None]).sum(0)
    for _ in range(4):  # refine toward the dominant voice
        centroid /= np.linalg.norm(centroid) + 1e-9
        sims = vecs @ centroid
        keep = sims >= LECTURER_SIM
        centroid = (vecs[keep] * weights[keep, None]).sum(0)
    sims = vecs @ (centroid / (np.linalg.norm(centroid) + 1e-9))

    mask = [False] * len(segments)
    for i, s in zip(idx, sims):
        mask[i] = bool(s >= LECTURER_SIM)
    # very short segments follow their neighbours (too short to fingerprint)
    for i, seg in enumerate(segments):
        if i not in emb:
            prev = mask[i - 1] if i > 0 else True
            nxt = next((mask[j] for j in range(i + 1, len(segments)) if j in emb), prev)
            mask[i] = prev and nxt
    kept = sum(segments[i]["end"] - segments[i]["start"] for i in range(len(segments)) if mask[i])
    total = sum(s["end"] - s["start"] for s in segments) or 1
    print(f"  lecturer voice: {kept / total:.0%} of speech kept")
    return mask


def redact(segments_path: Path, audio: Path | None, header_md: Path, out_md: Path, names: Path,
           keep: list[str], lecturer_only: bool = False) -> None:
    segments = json.loads(segments_path.read_text())
    if lecturer_only:
        if audio is None:
            raise SystemExit("--lecturer-only needs --audio")
        mask = lecturer_mask(segments, audio)
    else:
        mask = [True] * len(segments)

    kept: list[dict] = []
    gap_start = None
    for seg, ok in zip(segments, mask):
        if ok:
            if gap_start is not None and seg["start"] - gap_start >= 5:
                kept.append({"start": gap_start, "end": gap_start, "text": OMIT_NOTE})
            gap_start = None
            kept.append(seg)
        elif gap_start is None:
            gap_start = seg["start"]

    nlp = _nlp()
    known = json.loads(names.read_text())
    public, single, other = set(known["full"]), set(known["single"]), set(known.get("other", []))
    words = _dictionary()
    keep_set = set(keep)
    total = 0
    for seg in kept:
        if seg["text"] != OMIT_NOTE:
            seg["text"], n = redact_names(seg["text"], nlp, public, keep_set, single, other, words)
            total += n

    header = header_md.read_text().split("\n[00:")[0].rstrip()
    note = ("Lecturer's voice only; student names removed." if lecturer_only
            else "Student names replaced with 'a participant'.")
    header = header.replace("- Machine transcript (Whisper).", f"- {note} Machine transcript (Whisper).")
    body = [f"[{hms(start)}] {text}\n" for start, text in paragraphs(kept)]
    out_md.write_text(header + "\n\n" + "\n".join(body), encoding="utf-8")
    print(f"  {total} names replaced -> {out_md.name}")


# ------------------------------------------------------------------- sweep
# The tagger catches a name in one sentence and misses it in the next ("Ravi
# asked..." vs "thanks Ravi"). So after redacting, every name redacted in ANY
# transcript is removed from ALL transcripts, wherever it appears.
def sweep(raw_dir: Path, red_dir: Path, names: Path, extra: Path | None = None) -> None:
    known = json.loads(names.read_text())
    public = set(known["single"]) | {t for n in known["full"] for t in n.split()} | set(known.get("other", []))
    keep = public | {t for n in FACULTY for t in n.split()} | NOT_NAMES | CONCEPTS
    full = set(known["full"])
    words = _dictionary()
    pairs = [(raw_dir / r.name, r) for r in sorted(red_dir.glob("*.md")) if (raw_dir / r.name).exists()]
    found: set[str] = set()
    for raw, red in pairs:
        found |= removed_names(raw.read_text(), red.read_text())
    targets = sorted(
        w for w in found
        if len(w) >= 3 and w[:1].isupper() and not w.isupper() and w not in keep and w.lower() not in words
    )
    if extra:  # names a human reviewer spotted that the tagger never caught (kept out of git)
        targets = sorted(set(targets) | set(extra.read_text().split()))
    print(f"{len(targets)} student names to remove everywhere")
    pattern = re.compile(r"\b(" + "|".join(map(re.escape, targets)) + r")(['’]s)?\b", re.IGNORECASE)
    for _, red in pairs:
        text = red.read_text()
        head, sep, body = text.partition("\n\n[")  # leave the header (title, speaker, links) alone
        def repl(m: re.Match) -> str:
            nxt = re.match(r"\s+([A-Z]\w+)", body[m.end():])
            prv = re.search(r"([A-Z]\w+)\s+$", body[:m.start()])
            if (nxt and f"{m.group(1)} {nxt.group(1)}" in full) or (prv and f"{prv.group(1)} {m.group(1)}" in full):
                return m.group(0)  # part of a public figure's full name
            return "a participant"

        new_body, n = pattern.subn(repl, body)
        if n:
            red.write_text(head + sep + new_body, encoding="utf-8")
        print(f"  {n:3} more removed -> {red.name}")


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    kn = sub.add_parser("known-names")
    kn.add_argument("dirs", nargs="+", type=Path)
    kn.add_argument("--out", type=Path, required=True)
    rd = sub.add_parser("redact")
    rd.add_argument("segments", type=Path)
    rd.add_argument("header_md", type=Path)
    rd.add_argument("out_md", type=Path)
    rd.add_argument("--names", type=Path, required=True)
    rd.add_argument("--keep", action="append", default=[], help="extra names to keep (the speaker)")
    rd.add_argument("--lecturer-only", action="store_true", help="also drop all non-lecturer speech")
    rd.add_argument("--audio", type=Path, help="16 kHz mono audio (needed for --lecturer-only)")
    sw = sub.add_parser("sweep", help="remove every name redacted anywhere from all transcripts")
    sw.add_argument("raw_dir", type=Path)
    sw.add_argument("red_dir", type=Path)
    sw.add_argument("--names", type=Path, required=True)
    sw.add_argument("--extra", type=Path, help="whitespace-separated extra student names to remove")
    args = ap.parse_args()
    if args.cmd == "known-names":
        build_known_names(args.dirs, args.out)
    elif args.cmd == "sweep":
        sweep(args.raw_dir, args.red_dir, args.names, args.extra)
    else:
        redact(args.segments, args.audio, args.header_md, args.out_md, args.names, args.keep, args.lecturer_only)


if __name__ == "__main__":
    main()
