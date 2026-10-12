"""Apply Yaxa's small code patches on top of upstream DeepTutor. Idempotent:
re-run after every `git merge upstream/main` (after brand.py).

Everything Yaxa-specific lives in `deeptutor/yaxa/` and `web/app/(learn)/`,
which upstream never touches. This script only makes the few edits to
upstream files that Yaxa cannot avoid:

  1. deeptutor/api/main.py          - mount the Yaxa API at /api/yaxa
  2. llamaindex pipeline            - return each passage's full text (upstream
                                       truncates it to 200 chars), so the
                                       grounding margin can show and highlight it
  3. web/next.config.js             - the site root opens Yaxa Learn, not /chat

Every patch looks for an exact anchor string. If upstream moved the anchor the
script stops with an error instead of silently skipping the patch.

    python scripts/yaxa/overlay.py          # apply
    python scripts/yaxa/overlay.py --check  # exit 1 if any patch is missing
"""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
CHECK = "--check" in sys.argv
pending: list[str] = []


def patch(rel: str, marker: str, anchor: str, replacement: str) -> None:
    """Replace `anchor` with `replacement` in a file unless `marker` is present."""
    path = ROOT / rel
    text = path.read_text(encoding="utf-8")
    if marker in text:
        return  # already applied
    if anchor not in text:
        sys.exit(f"overlay: anchor not found in {rel} - upstream changed, update overlay.py")
    pending.append(rel)
    if not CHECK:
        path.write_text(text.replace(anchor, replacement, 1), encoding="utf-8")


# ------------------------------------------------------- 1. mount Yaxa API
# Mounted with plain require_auth (not `_auth`): `_auth` is the learning-surface
# gate, which would block accounts with a learning policy from /api/yaxa.
API_ANCHOR = (
    'app.include_router(plugins.router, prefix="/api/plugins", tags=["plugins"])\n'
)
patch(
    "deeptutor/api/main.py",
    "# yaxa-overlay: api",
    API_ANCHOR,
    API_ANCHOR
    + "# yaxa-overlay: api\n"
    + "from deeptutor.yaxa.api import router as yaxa_router  # noqa: E402\n\n"
    + 'app.include_router(yaxa_router, prefix="/api/yaxa", tags=["yaxa"], '
    + "dependencies=[Depends(require_auth)])\n",
)

# ----------------------------------------------- 2. full passage text in RAG
RAG_ANCHOR = '                    "content": node.node.text[:200],\n'
patch(
    "deeptutor/services/rag/pipelines/llamaindex/pipeline.py",
    '"text": node.node.text,  # yaxa-overlay',
    RAG_ANCHOR,
    RAG_ANCHOR + '                    "text": node.node.text,  # yaxa-overlay\n',
)

# ------------------------------------------------ 3. root opens Yaxa Learn
patch(
    "web/next.config.js",
    'destination: "/learn", permanent: false }, // yaxa-overlay',
    '{ source: "/", destination: "/chat", permanent: false },',
    '{ source: "/", destination: "/learn", permanent: false }, // yaxa-overlay',
)

# ------------------------------------------------------------------ report
verb = "would patch" if CHECK else "patched"
print(f"{verb} {len(pending)} files")
for p in pending:
    print("  ", p)
sys.exit(1 if CHECK and pending else 0)
