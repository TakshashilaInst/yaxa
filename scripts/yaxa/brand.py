"""Apply Yaxa branding on top of upstream DeepTutor. Idempotent: re-run after
every `git merge upstream/main`.

What it changes (user-visible only):
  1. web/locales/*/*.json  - translated VALUES ("DeepTutor" -> "Yaxa"). Keys are
     left alone, because the i18n key is the English source string in the TSX.
  2. web .tsx/.ts         - page title, favicons, logo images, alt/aria labels,
     bare JSX brand text, agent-name fallback, co-writer sample template.
  3. deeptutor/**/prompts - the assistant introduces itself as Yaxa.
  4. About page           - Yaxa repo link + "Built on DeepTutor" credit row.
  5. README.md            - Yaxa header with credit to DeepTutor (HKUDS).

What it deliberately does NOT change: the `deeptutor` Python package, CLI name,
API routes, storage keys, env vars, comments. Renaming those would break every
upstream merge for no user-visible gain.

    python scripts/yaxa/brand.py          # apply
    python scripts/yaxa/brand.py --check  # exit 1 if anything is still unbranded
"""

from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "web"
CHECK = "--check" in sys.argv
changed: dict[str, int] = {}


def rewrite(path: Path, fn) -> None:
    """Apply fn(text)->text to a file; record how many files changed."""
    old = path.read_text(encoding="utf-8")
    new = fn(old)
    if new != old:
        changed[str(path.relative_to(ROOT))] = 1
        if not CHECK:
            path.write_text(new, encoding="utf-8")


# ---------------------------------------------------------------- 1. locales
LOGIN_TAGLINE_KEY = '"DeepTutor · Agent-Native Learning"'
LINE = re.compile(r'^(\s*"(?:[^"\\]|\\.)*"\s*:\s*)(".*)$')


def brand_locale(text: str) -> str:
    out = []
    for raw in text.splitlines(keepends=True):
        line = raw.rstrip("\r\n")
        eol = raw[len(line):]  # keep the original line ending
        if line.lstrip().startswith(LOGIN_TAGLINE_KEY):
            # Login/register footer doubles as the visible credit line.
            line = re.sub(r':\s*".*"', ': "Yaxa · Built on DeepTutor"', line, count=1)
        else:
            m = LINE.match(line)
            if m:
                line = m.group(1) + m.group(2).replace("DeepTutor", "Yaxa")
        out.append(line + eol)
    return "".join(out)


for f in sorted((WEB / "locales").glob("*/*.json")):
    rewrite(f, brand_locale)

# ------------------------------------------------------------ 2. web sources
TSX_RULES = [
    (r'src="/(?:logo|logo_black)\.png"', 'src="/yaxa-logo.png"'),
    (r'src="/banner\.png"', 'src="/yaxa-banner.png"'),
    (r'(alt|aria-label)="DeepTutor"', r'\1="Yaxa"'),
    (r'(?m)^(\s*)DeepTutor(\s*)$', r"\1Yaxa\2"),            # bare JSX brand text
    (r'\|\| "DeepTutor"', '|| "Yaxa"'),                        # agent-name fallback
]
for f in sorted(list(WEB.rglob("*.tsx")) + list(WEB.rglob("*.ts"))):
    if "node_modules" in f.parts or ".next" in f.parts or "tests" in f.parts:
        continue
    def apply_rules(t: str) -> str:
        for pat, rep in TSX_RULES:
            t = re.sub(pat, rep, t)
        return t
    rewrite(f, apply_rules)


def brand_layout(t: str) -> str:
    t = t.replace('title: "DeepTutor"', 'title: "Yaxa"')
    t = re.sub(r'"/(favicon-(?:16x16|32x32))\.png"', r'"/yaxa-\1.png"', t)
    return t.replace('"/apple-touch-icon.png"', '"/yaxa-apple-touch-icon.png"')


rewrite(WEB / "app" / "layout.tsx", brand_layout)


def brand_cowriter_sample(t: str) -> str:
    t = t.replace("#deeptutor-", "#yaxa-")
    return re.sub(r"DeepTutor(?! Website)", "Yaxa", t)


rewrite(WEB / "app" / "(workspace)" / "co-writer" / "sampleTemplate.ts", brand_cowriter_sample)

# ------------------------------------------------------------ 3. AI prompts
# Upstream credits HKU as the developer; Yaxa's assistant must not claim that.
PROMPT_FIXES = [
    ("developed by the Data Intelligence Lab at HKU",
     "built by the Takshashila Institution on DeepTutor (HKU Data Intelligence Lab)"),
    ("由香港大学数据智能实验室开发的",
     "由 Takshashila Institution 基于 DeepTutor（香港大学数据智能实验室）构建的"),
]


def brand_prompt(t: str) -> str:
    # Rename, but keep the credit phrase "DeepTutor (HKU ..." / "DeepTutor（香港..." intact
    t = re.sub(r"DeepTutor(?! \(HKU|（香港)", "Yaxa", t)
    for old, new in PROMPT_FIXES:
        t = t.replace(old, new)
    return t


for f in sorted(ROOT.joinpath("deeptutor").rglob("*")):
    if f.suffix in {".yaml", ".yml", ".md"} and "prompts" in f.parts:
        rewrite(f, brand_prompt)

# ------------------------------------------------------------- 4. About page
CREDIT_ROW = """        <ResourceRow
          title="Built on DeepTutor"
          description="Yaxa is a fork of DeepTutor by HKUDS (University of Hong Kong), used under the Apache License 2.0"
          href="https://github.com/HKUDS/DeepTutor"
          icon={<Github className="h-4 w-4" />}
        />
"""


def brand_about(t: str) -> str:
    t = t.replace(
        'description={t("Source code, issues, and contributions")}\n          href="https://github.com/HKUDS/DeepTutor"',
        'description={t("Source code, issues, and contributions")}\n          href="https://github.com/TakshashilaInst/yaxa"',
    )
    if 'title="Built on DeepTutor"' not in t:
        t = t.replace(
            '        <ResourceRow\n          title={t("Documentation")}',
            CREDIT_ROW + '        <ResourceRow\n          title={t("Documentation")}',
            1,
        )
    return t


rewrite(WEB / "features" / "settings" / "sections" / "AboutSettingsSection.tsx", brand_about)

# ----------------------------------------------------------------- 5. README
README_HEADER = """<!-- yaxa-header -->
# Yaxa

**Yaxa** is an AI-native learning platform for public policy education, built as a fork of
[DeepTutor](https://github.com/HKUDS/DeepTutor) by the Data Intelligence Lab at the University
of Hong Kong (HKUDS). DeepTutor is licensed under the Apache License 2.0; this fork keeps that
license and its notices (see `LICENSE`, `NOTICE` and `THIRD_PARTY_NOTICES.md`). Yaxa-specific
changes live under `scripts/yaxa/` and are applied with `python scripts/yaxa/brand.py`.

The original DeepTutor README follows.

---
<!-- /yaxa-header -->

"""


def brand_readme(t: str) -> str:
    return t if "<!-- yaxa-header -->" in t else README_HEADER + t


rewrite(ROOT / "README.md", brand_readme)

# ------------------------------------------------------------------ 6. tests
# Upstream tests that read the real prompt files assert the product identity.
for rel in ("tests/agents/chat/test_language_prompts.py",
            "tests/capabilities/test_mastery_loop_pipeline.py"):
    rewrite(ROOT / rel, lambda t: t.replace('你是 DeepTutor"', '你是 Yaxa"')
                                   .replace('You are DeepTutor"', 'You are Yaxa"'))

# ----------------------------------------------------------------- report
verb = "would change" if CHECK else "changed"
print(f"{verb} {len(changed)} files")
for p in sorted(changed):
    print("  ", p)
sys.exit(1 if CHECK and changed else 0)
