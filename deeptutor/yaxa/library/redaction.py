"""Remove student names from a webinar transcript before it is indexed.

Takshashila policy (Pranay, 2026-10-12): student NAMES never enter Yaxa's
libraries. Student questions and comments stay; they are part of the class.

Three layers, strongest first:
1. Zoom speaker labels. Anyone speaking who isn't the lecturer is a participant:
   the line is attributed to "Participant", and every part of their display
   name is removed wherever it is said ("Thanks Ravi").
2. The tagger (spaCy) finds other people's names; a name is kept only if it is
   a public figure (a full name in the course readings or faculty writing) or
   faculty. Anything else becomes "a participant".
3. The student list (cohort sheets + Yaxa accounts + names learned from earlier
   transcripts). A listed name is removed; if it is also part of a public
   figure's name ("Deepak" vs "Deepak Lal") it is flagged for a person to decide
   on the Libraries page, and the transcript waits.

Nothing here logs a name: only counts.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
import json
import logging
import os
from pathlib import Path
import re
from typing import Any, Iterable

logger = logging.getLogger(__name__)

PARAGRAPH_SECONDS = 60
PARTICIPANT = "Participant"
FACULTY = {"Nitin Pai", "Pranay Kotasthane", "Anupam Manur", "Sarthak Pradhan", "Ameya Naik",
           "Ashish Kulkarni", "Manoj Kewalramani", "Suman Joshi", "Shambhavi Naik", "Aditya Ramanathan",
           "Mihir Mahajan", "Bharath Reddy", "Anwesha Sen", "Lokendra Sharma", "Ganesh", "Vanshika",
           "Aishwaria", "Kautilya", "Chanakya",
           # Technology and Policy, and Defence and Foreign Affairs lecturers and guest speakers
           "Prakash Menon", "Kajari Kamal", "Praveen Mehendru", "Vivek Chadha", "Das", "Latha Reddy",
           "Talmiz Ahmad", "Raghavan", "Shivshankar Menon", "Arindam Goswami", "Shobhankita Reddy",
           "Ashwin Prasad", "Srividya", "Rohan Seth"}
# Takshashila's own vocabulary ("Samaj, Sarkar, Bazaar") that the tagger reads as names.
CONCEPTS = {"Samaj", "Sarkar", "Bazaar", "Swachh", "Bharat", "Atmanirbhar", "Kirana",
            "Puliyabaazi", "Takshashila", "Technopolitik"}  # also Takshashila's own shows and newsletters
NOT_NAMES = {"Samad", "Sahel", "Vijayanagara", "Karnatka", "Rameshwaram", "Cafe", "Logos",
             "Oped", "Swatch", "Tilley", "Ostrom", "Eleanor", "Charles", "Nah"}
# words in Zoom display names that aren't names ("Ravi's iPhone", "Guest 2")
DEVICE_WORDS = {"iphone", "ipad", "android", "galaxy", "zoom", "user", "guest", "mobile", "phone", "laptop",
                "admin", "takshashila", "host", "the", "and", "pro", "max", "mac", "macbook", "desktop", "s23"}
NOT_STUDENTS = {"demo", "student", "user", "admin", "test"}
_SPLIT = re.compile(r"[\s._@\-'’,;()]+")


# ------------------------------------------------------------------ helpers
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


def hms(seconds: float) -> str:
    s = int(seconds)
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"


def paragraphs(segments: list[dict]) -> list[tuple[float, str]]:
    """Group segments into ~1-minute paragraphs, keeping start times."""
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


def _tokens(name: str) -> set[str]:
    return {t for t in _SPLIT.split(name) if len(t) >= 3 and t.isalpha()}


# ------------------------------------------------------------ known names
def build_known_names(dirs: list[Path], out: Path) -> None:
    """Names that occur in the course/faculty corpus are public figures.

    Saves {"full": [multi-word names], "single": [one-word names seen at least twice],
    "other": [places / organisations / groups]} -- the last so that a transcript
    entity the tagger mislabels as a person ("Tamil Nadu") is not redacted.
    """
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


# ---------------------------------------------------------- student names
def student_names(secrets_file: Path | None, roster: Iterable[str], learned_file: Path | None) -> set[str]:
    """Every known student name part: the reviewer's list, Yaxa accounts, names learned earlier."""
    words: set[str] = set()
    for path in (secrets_file, learned_file):
        if path and path.is_file():
            for line in path.read_text(encoding="utf-8").splitlines():
                if not line.strip().startswith("#"):
                    words |= _tokens(line)
    for name in roster:
        words |= _tokens(name)
    return {w for w in words if w.lower() not in NOT_STUDENTS}


def learn(learned_file: Path, names: set[str]) -> None:
    """Add names removed from a transcript to the private list future transcripts are checked against."""
    known: dict[str, str] = {}
    if learned_file.is_file():
        known = {w.lower(): w for w in learned_file.read_text(encoding="utf-8").split()}
    for n in names:
        if n.lower() not in known or (n[:1].isupper() and not known[n.lower()][:1].isupper()):
            known[n.lower()] = n
    learned_file.parent.mkdir(parents=True, exist_ok=True)
    learned_file.write_text("\n".join(sorted(known.values(), key=str.lower)) + "\n", encoding="utf-8")
    os.chmod(learned_file, 0o600)


# --------------------------------------------------------------- the tagger
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


def removed_names(raw: str, red: str) -> set[str]:
    """Words of the raw transcript that redaction replaced with 'a participant'."""
    import difflib

    a, b = re.findall(r"\S+", raw), re.findall(r"\S+", red)
    out: set[str] = set()
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if op == "replace" and "participant" in " ".join(b[j1:j2]):
            out.update(re.sub(r"[^\w]", "", w) for w in a[i1:i2])
    return out


def _replace_words(text: str, targets: set[str], public_full: set[str]) -> tuple[str, int]:
    """Whole-word, case-insensitive replace of each target with 'a participant', unless it is
    part of a public figure's full name right there ("Deepak Lal")."""
    if not targets:
        return text, 0
    pattern = re.compile(r"\b(" + "|".join(map(re.escape, sorted(targets, key=len, reverse=True))) + r")(['’]s)?\b",
                         re.IGNORECASE)

    def repl(m: re.Match) -> str:
        nxt = re.match(r"\s+([A-Z]\w+)", text[m.end():])
        prv = re.search(r"([A-Z]\w+)\s+$", text[: m.start()])
        if (nxt and f"{m.group(1)} {nxt.group(1)}" in public_full) or (prv and f"{prv.group(1)} {m.group(1)}" in public_full):
            return m.group(0)
        return "a participant" + (m.group(2) or "")

    return pattern.subn(repl, text)


# ---------------------------------------------------------- one transcript
@dataclass
class Redacted:
    markdown: str
    removed: set[str] = field(default_factory=set)
    flags: list[dict] = field(default_factory=list)


def _speaker_roles(segments: list[dict], lecturer: str) -> dict[str, str]:
    """Map each raw speaker label to the label shown: the lecturer's name, PARTICIPANT, or ""."""
    talk: Counter[str] = Counter()
    for s in segments:
        if s.get("speaker"):
            talk[s["speaker"]] += s["end"] - s["start"]
    if not talk:
        return {}
    anonymous = all(re.fullmatch(r"S\d*", k) for k in talk)  # Sarvam-only: "S0", "S1"
    lect_tokens = {t.lower() for t in _tokens(lecturer)}
    faculty_tokens = {t.lower() for n in FACULTY for t in n.split() if len(t) >= 3}
    roles: dict[str, str] = {}
    for spk in talk:
        toks = {t.lower() for t in _tokens(spk)}
        if not anonymous and (toks & lect_tokens or spk in FACULTY):
            roles[spk] = lecturer or spk
        elif not anonymous and toks and toks <= faculty_tokens:
            roles[spk] = spk  # another faculty member on the call
        else:
            roles[spk] = PARTICIPANT
    if anonymous or lecturer == "" or lecturer not in roles.values():
        main = talk.most_common(1)[0][0]  # whoever talks most is the lecturer
        if roles.get(main) == PARTICIPANT:
            roles[main] = lecturer if lecturer else ""
    return roles


def redact_segments(segments: list[dict], header: str, lecturer: str, public: dict[str, Any], students: set[str], *,
                    allow: Iterable[str] = (), engine: str = "Sarvam (saaras:v4)") -> Redacted:
    roles = _speaker_roles(segments, lecturer)
    public_full = set(public.get("full", []))
    allow_l = {a.lower() for a in allow}
    keep_tokens = {t.lower() for n in FACULTY | ({lecturer} if lecturer else set()) for t in _tokens(n)}

    # 1. names from Zoom display names of participants
    from_labels = {t for spk, role in roles.items() if role == PARTICIPANT for t in _tokens(spk)
                   if t.lower() not in DEVICE_WORDS and t.lower() not in keep_tokens}
    # 3. listed students: certain unless the name is also part of a public figure's name
    public_parts = {t.lower() for n in public_full for t in n.split()}
    listed = {s for s in students if s.lower() not in keep_tokens and s.lower() not in allow_l}
    ambiguous = {s for s in listed if s.lower() in public_parts}
    certain = (from_labels | (listed - ambiguous)) - {a for a in from_labels if a.lower() in allow_l}

    nlp = _nlp()
    words = _dictionary()
    single, other = set(public.get("single", [])), set(public.get("other", []))
    keep = ({lecturer} if lecturer else set()) | set(allow)  # reviewer-approved names survive the tagger too
    tagged = replaced = 0
    out_segments = []
    for s in segments:
        text, n = redact_names(s["text"], nlp, public_full, keep, single, other, words)
        removed_here = removed_names(s["text"], text)
        text, m = _replace_words(text, certain, public_full)
        tagged += n
        replaced += m
        out_segments.append(s | {"text": text, "label": roles.get(s.get("speaker", ""), ""),
                                 "_removed": removed_here})
    # names learned for future transcripts: only what was really removed here, filtered like the
    # old cross-transcript sweep (no dictionary words, public names or Takshashila vocabulary)
    said = " ".join(s["text"] for s in segments)
    found_listed = {n for n in certain - from_labels if re.search(rf"\b{re.escape(n)}\b", said, re.IGNORECASE)}
    public_tokens = public_parts | {w.lower() for w in single}
    not_names = {w.lower() for w in CONCEPTS | NOT_NAMES}
    tagged_names = {w for s in out_segments for w in s["_removed"]
                    if len(w) >= 3 and w[:1].isupper() and not w.isupper() and w.lower() not in words
                    and w.lower() not in public_tokens and w.lower() not in not_names and w.lower() not in keep_tokens}
    removed = from_labels | found_listed | tagged_names

    # body: paragraphs that break when the speaker changes
    body: list[str] = []
    run: list[dict] = []
    for s in out_segments + [{"label": None}]:
        if run and s["label"] != run[-1]["label"]:
            for start, text in paragraphs(run):
                label = run[0]["label"]
                body.append(f"[{hms(start)}] {label + ': ' if label else ''}{text}\n")
            run = []
        if s["label"] is not None:
            run.append(s)
    markdown_body = "\n".join(body)

    # gate: ambiguous listed names still present wait for a person
    flags = []
    for name in sorted(ambiguous):
        for m in re.finditer(rf"\b{re.escape(name)}\b", markdown_body, re.IGNORECASE):
            nxt = re.match(r"\s+([A-Z]\w+)", markdown_body[m.end():])
            if nxt and f"{m.group(0)} {nxt.group(1)}" in public_full:
                continue  # "Deepak Lal": the public figure
            line_start = markdown_body.rfind("\n", 0, m.start()) + 1
            stamp = re.match(r"\[(\d{2}:\d{2}:\d{2})\]", markdown_body[line_start:])
            flags.append({"name": name, "context": markdown_body[max(0, m.start() - 60) : m.end() + 60].replace("\n", " "),
                          "at": stamp.group(1) if stamp else ""})
            break

    note = (f"- Student names replaced with 'a participant'; students' lines marked '{PARTICIPANT}'. "
            f"Machine transcript ({engine}). Names and numbers may be misheard; check the recording before quoting.")
    logger.info("yaxa library redaction: %d tagged, %d listed/speaker names replaced, %d flags", tagged, replaced, len(flags))
    return Redacted(markdown=header.rstrip() + "\n" + note + "\n\n" + markdown_body, removed=removed, flags=flags)


def apply_review(markdown: str, decisions: dict[str, str], public_full: Iterable[str] = ()) -> str:
    """Apply a reviewer's decisions: "remove" replaces the name, "keep" leaves it."""
    head, sep, body = markdown.partition("\n\n")
    targets = {name for name, d in decisions.items() if d == "remove"}
    new_body, _ = _replace_words(body, targets, set(public_full))
    return head + sep + new_body
