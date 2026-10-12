"""Fetch a faculty member's public articles into Markdown files for a Yaxa knowledge base.

    uv run --with trafilatura python scripts/yaxa/scrape_writings.py urls.txt out_dir --author "Nitin Pai"

urls.txt has one URL per line. Each article becomes <out_dir>/<date>-<slug>.md with a
header (title, author, date, source URL) so answers can cite and link to it.
Polite by design: one request per second, skips what is already saved, and
skips pages that yield under 150 words (index pages, paywalls).
"""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import time

import trafilatura


def slugify(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-").lower()[:80]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("urls", type=Path)
    ap.add_argument("out_dir", type=Path)
    ap.add_argument("--author", required=True)
    ap.add_argument("--delay", type=float, default=1.0)
    args = ap.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    done_log = args.out_dir / ".fetched"
    done = set(done_log.read_text().split()) if done_log.exists() else set()

    urls = [u.strip() for u in args.urls.read_text().splitlines() if u.strip().startswith("http")]
    saved = skipped = 0
    for url in urls:
        if url in done:
            continue
        try:
            html = trafilatura.fetch_url(url)
            doc = trafilatura.bare_extraction(html, url=url, with_metadata=True) if html else None
        except Exception:
            doc = None
        body = (doc.text if doc else "") or ""
        if len(body.split()) < 150:
            skipped += 1
        else:
            title = (doc.title or url).strip()
            date = (doc.date or "").strip()
            name = f"{date or 'undated'}-{slugify(title) or 'article'}.md"
            header = f"# {title}\n\n- Author: {args.author}\n- Date: {date or 'unknown'}\n- Source: {url}\n\n"
            (args.out_dir / name).write_text(header + body.strip() + "\n", encoding="utf-8")
            saved += 1
        with done_log.open("a") as fh:
            fh.write(url + "\n")
        time.sleep(args.delay)
    print(f"{args.author}: saved {saved}, skipped {skipped}, total urls {len(urls)}")


if __name__ == "__main__":
    main()
