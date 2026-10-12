"""Remove students' voices and names from a webinar transcript before it is indexed.

Takshashila policy: student comments and names never enter Yaxa's libraries.

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
    ... python scripts/yaxa/redact_transcript.py redact segments.json audio.flac header.md out.md \\
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
FACULTY = {"Nitin Pai", "Pranay Kotasthane", "Anupam Manur", "Sarthak Pradhan", "Ameya Naik",
           "Ashish Kulkarni", "Manoj Kewalramani", "Suman Joshi", "Shambhavi Naik", "Aditya Ramanathan",
           "Mihir Mahajan", "Bharath Reddy", "Anwesha Sen", "Lokendra Sharma", "Ganesh", "Vanshika",
           "Aishwaria", "Kautilya", "Chanakya"}

sys.path.insert(0, str(Path(__file__).parent))
from transcribe import hms, paragraphs  # noqa: E402  (same paragraphing as the raw transcript)


def _nlp():
    import spacy

    return spacy.load("en_core_web_sm", disable=["lemmatizer"])


# --------------------------------------------------------------- known names
def build_known_names(dirs: list[Path], out: Path) -> None:
    """Names that occur in the course/faculty corpus are public figures.

    Saves {"full": [multi-word names], "single": [one-word names seen at least twice]}.
    """
    from collections import Counter
    import subprocess

    nlp = _nlp()
    nlp.max_length = 3_000_000
    names: set[str] = set()
    singles: Counter[str] = Counter()
    for d in dirs:
        for f in sorted(d.rglob("*")):
            if f.suffix == ".md" and not f.name.startswith("Webinar"):
                text = f.read_text(errors="ignore")
            elif f.suffix == ".pdf":
                text = subprocess.run(["pdftotext", str(f), "-"], capture_output=True, text=True).stdout
            else:
                continue
            for i in range(0, len(text), 500_000):
                for ent in nlp(text[i : i + 500_000]).ents:
                    name = " ".join(ent.text.split())
                    if ent.label_ != "PERSON" or not name[:1].isupper():
                        continue
                    if len(name.split()) >= 2:
                        names.add(name)
                    else:
                        singles[name] += 1
    single = sorted(n for n, c in singles.items() if c >= 2)
    out.write_text(json.dumps({"full": sorted(names), "single": single}, ensure_ascii=False))
    print(f"{len(names)} full + {len(single)} single public names from {len(dirs)} folders")


# ------------------------------------------------------------------ speakers
def lecturer_mask(segments: list[dict], audio: Path) -> list[bool]:
    import numpy as np
    import soundfile as sf
    import torch
    from speechbrain.inference.speaker import EncoderClassifier

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


# -------------------------------------------------------------------- names
def redact_names(text: str, nlp, public: set[str], keep: set[str], single: set[str] = frozenset()) -> tuple[str, int]:
    # one-word names that are public: surnames of public full names ("Keynes"), and
    # one-word names the corpus itself uses ("Nixon")
    public_last = {n.split()[-1] for n in public} | set(single)
    allowed_tokens = {t for n in keep | FACULTY for t in n.split()}
    doc = nlp(text)
    out, last, count = [], 0, 0
    for ent in doc.ents:
        if ent.label_ != "PERSON":
            continue
        name = " ".join(ent.text.split())
        tokens = name.split()
        if name in public or name in keep or name in FACULTY:
            continue
        if len(tokens) == 1 and (tokens[0] in public_last or tokens[0] in allowed_tokens):
            continue
        if len(tokens) > 1 and all(t in allowed_tokens or t in public_last for t in tokens):
            continue
        out.append(text[last : ent.start_char])
        out.append("a participant")
        last = ent.end_char
        count += 1
    out.append(text[last:])
    return "".join(out), count


def redact(segments_path: Path, audio: Path, header_md: Path, out_md: Path, names: Path, keep: list[str]) -> None:
    segments = json.loads(segments_path.read_text())
    mask = lecturer_mask(segments, audio)

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
    public, single = set(known["full"]), set(known["single"])
    keep_set = set(keep)
    total = 0
    for seg in kept:
        if seg["text"] != OMIT_NOTE:
            seg["text"], n = redact_names(seg["text"], nlp, public, keep_set, single)
            total += n

    header = header_md.read_text().split("\n[00:")[0].rstrip()
    header = header.replace(
        "- Machine transcript (Whisper).",
        "- Lecturer's voice only: student comments and names removed. Machine transcript (Whisper).",
    )
    body = [f"[{hms(start)}] {text}\n" for start, text in paragraphs(kept)]
    out_md.write_text(header + "\n\n" + "\n".join(body), encoding="utf-8")
    print(f"  {total} names replaced -> {out_md.name}")


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    kn = sub.add_parser("known-names")
    kn.add_argument("dirs", nargs="+", type=Path)
    kn.add_argument("--out", type=Path, required=True)
    rd = sub.add_parser("redact")
    rd.add_argument("segments", type=Path)
    rd.add_argument("audio", type=Path)
    rd.add_argument("header_md", type=Path)
    rd.add_argument("out_md", type=Path)
    rd.add_argument("--names", type=Path, required=True)
    rd.add_argument("--keep", action="append", default=[], help="extra names to keep (the speaker)")
    args = ap.parse_args()
    if args.cmd == "known-names":
        build_known_names(args.dirs, args.out)
    else:
        redact(args.segments, args.audio, args.header_md, args.out_md, args.names, args.keep)


if __name__ == "__main__":
    main()
