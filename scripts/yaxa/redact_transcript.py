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
FACULTY = {"Nitin Pai", "Pranay Kotasthane", "Anupam Manur", "Sarthak Pradhan", "Ameya Naik",
           "Ashish Kulkarni", "Manoj Kewalramani", "Suman Joshi", "Shambhavi Naik", "Aditya Ramanathan",
           "Mihir Mahajan", "Bharath Reddy", "Anwesha Sen", "Lokendra Sharma", "Ganesh", "Vanshika",
           "Aishwaria", "Kautilya", "Chanakya"}
# Takshashila's own vocabulary ("Samaj, Sarkar, Bazaar") that the tagger reads as names.
CONCEPTS = {"Samaj", "Sarkar", "Bazaar", "Swachh", "Bharat", "Atmanirbhar", "Kirana"}

sys.path.insert(0, str(Path(__file__).parent))
from transcribe import hms, paragraphs  # noqa: E402  (same paragraphing as the raw transcript)


def _nlp():
    import spacy

    return spacy.load("en_core_web_sm", disable=["lemmatizer"])


def _norm(text: str) -> str:
    """'the Bretton  Woods' / "Ajay Shah's" -> 'Bretton Woods' / 'Ajay Shah'."""
    name = " ".join(text.split())
    name = re.sub(r"^(the|The)\s+", "", name)
    return re.sub(r"['’]s$", "", name).strip(".,;:!?")


def _dictionary() -> set[str]:
    path = Path("/usr/share/dict/words")
    return {w.strip().lower() for w in path.read_text().split()} if path.exists() else set()


# --------------------------------------------------------------- known names
def build_known_names(dirs: list[Path], out: Path) -> None:
    """Names that occur in the course/faculty corpus are public figures.

    Saves {"full": [multi-word names], "single": [one-word names seen at least twice],
    "other": [places / organisations / groups]} -- the last so that a transcript
    entity the tagger mislabels as a person ("Tamil Nadu") is not redacted.
    """
    from collections import Counter
    import subprocess

    nlp = _nlp()
    nlp.max_length = 3_000_000
    names: set[str] = set()
    singles: Counter[str] = Counter()
    other: set[str] = set()
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
                    name = _norm(ent.text)
                    if ent.label_ in {"GPE", "LOC", "ORG", "NORP", "FAC", "EVENT", "LAW"}:
                        other.add(name)
                        continue
                    if ent.label_ != "PERSON" or not name[:1].isupper():
                        continue
                    if len(name.split()) >= 2:
                        names.add(name)
                    else:
                        singles[name] += 1
    single = sorted(n for n, c in singles.items() if c >= 2)
    out.write_text(json.dumps({"full": sorted(names), "single": single, "other": sorted(other)}, ensure_ascii=False))
    print(f"{len(names)} full + {len(single)} single public names from {len(dirs)} folders")


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


# -------------------------------------------------------------------- names
def redact_names(text: str, nlp, public: set[str], keep: set[str], single: frozenset[str] | set[str] = frozenset(),
                 other: frozenset[str] | set[str] = frozenset(), words: frozenset[str] | set[str] = frozenset()) -> tuple[str, int]:
    # one-word names that are public: surnames of public full names ("Keynes"), and
    # one-word names the corpus itself uses ("Nixon")
    public_last = {n.split()[-1] for n in public} | set(single)
    allowed_tokens = {t for n in keep | FACULTY for t in n.split()} | CONCEPTS
    doc = nlp(text)
    out, last, count = [], 0, 0
    for ent in doc.ents:
        if ent.label_ != "PERSON":
            continue
        name = _norm(ent.text)
        tokens = name.split()
        if not tokens or name in public or name in keep or name in FACULTY or name in other:
            continue
        if name.isupper():  # acronyms the tagger mistakes for names (FRBMA, CAPEX)
            continue
        # ordinary words capitalised only because they open a sentence ("Nah.", "Lobby.");
        # mid-sentence capitals are treated as names (so a student called Rhea is caught)
        if len(tokens) == 1 and tokens[0].lower() in words and ent.start == ent.sent.start:
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
NOT_NAMES = {"Samaj", "Samad", "Sahel", "Vijayanagara", "Karnatka", "Rameshwaram", "Cafe", "Logos",
             "Oped", "Swatch", "Bharat", "Tilley", "Ostrom", "Eleanor", "Charles", "Nah"}


def removed_names(raw: str, red: str) -> set[str]:
    """Words of the raw transcript that redaction replaced with 'a participant'."""
    import difflib

    a, b = re.findall(r"\S+", raw), re.findall(r"\S+", red)
    out: set[str] = set()
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if op == "replace" and "participant" in " ".join(b[j1:j2]):
            out.update(re.sub(r"[^\w]", "", w) for w in a[i1:i2])
    return out


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
