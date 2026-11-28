"use client";

/**
 * Plain text with links: markdown-style [label](https://…) and bare https:// addresses become
 * links that open in a new tab. Only http(s) addresses are linked, so text can never smuggle in
 * a javascript: or data: link. Everything else stays plain text (React escapes it).
 */
import type { ReactNode } from "react";

const LINK = /\[([^\]\n]{1,200})\]\((https?:\/\/[^\s)]{1,2000})\)|(https?:\/\/[^\s<>()]{1,2000}[^\s<>().,;:!?'"])/g;

export function LinkedText({ text }: { text: string }) {
  const out: ReactNode[] = [];
  let last = 0;
  for (const m of text.matchAll(LINK)) {
    const at = m.index ?? 0;
    if (at > last) out.push(text.slice(last, at));
    const href = m[2] ?? m[3];
    out.push(
      <a key={at} href={href} target="_blank" rel="noopener noreferrer nofollow">
        {m[1] ?? m[3]}
      </a>,
    );
    last = at + m[0].length;
  }
  if (last < text.length) out.push(text.slice(last));
  return <>{out}</>;
}
