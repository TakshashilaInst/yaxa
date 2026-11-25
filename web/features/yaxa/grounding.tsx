"use client";

/**
 * The answer text with clickable citation chips, and the "Grounding" margin
 * that shows the passages an answer cites, like marginalia.
 */
import { useMemo, useState, type ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import type { Citation, Passage } from "@/lib/yaxa-api";

// -------------------------------------------------------- answer + cites
const CITE = /\[(\d{1,2}(?:\s*,\s*\d{1,2})*)\](?!\()/g;

/** "[1, 3]" -> markdown links "[1](#cite-1)[3](#cite-3)" rendered as chips. */
function linkCites(markdown: string): string {
  return markdown.replace(CITE, (_m, group: string) =>
    group
      .split(",")
      .map((n) => `[${n.trim()}](#cite-${n.trim()})`)
      .join(""),
  );
}

export function AnswerText({
  text,
  sources,
  citations,
  activeCite,
  onCite,
}: {
  text: string;
  sources: Passage[];
  citations?: Citation[];
  activeCite?: number | null;
  onCite: (n: number) => void;
}) {
  const byN = useMemo(() => new Map(sources.map((s) => [s.n, s])), [sources]);
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{
        a({ href, children }) {
          const m = /^#cite-(\d+)$/.exec(href ?? "");
          if (!m) {
            return (
              <a href={href} target="_blank" rel="noreferrer">
                {children}
              </a>
            );
          }
          const n = Number(m[1]);
          const src = byN.get(n);
          // While streaming, sources exist but citations aren't final yet:
          // only flag a cite as dangling once we know it has no source.
          const dangling = !src && (citations !== undefined || sources.length > 0);
          if (dangling) {
            return (
              <span className="yx-cite yx-cite-dangling" title="This source is not among the passages retrieved for this answer">
                {n}
              </span>
            );
          }
          const anecdote = src?.kind === "anecdote";
          return (
            <button
              type="button"
              className={`yx-cite${anecdote ? " yx-cite-anecdote" : ""}`}
              data-active={activeCite === n}
              title={`Show ${anecdote ? "the professor's anecdote" : "source"} ${n} in the grounding panel`}
              onClick={() => onCite(n)}
            >
              {n}
            </button>
          );
        },
      }}
    >
      {linkCites(text)}
    </ReactMarkdown>
  );
}

// ----------------------------------------------------- quote highlighting
/** Phrases the answer quotes ("..." or “...”), longest first. */
export function quotedPhrases(answer: string): string[] {
  const out: string[] = [];
  const re = /["“]([^"“”]{12,}?)["”]/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(answer)) !== null) out.push(m[1].trim());
  return out.sort((a, b) => b.length - a.length);
}

const escapeRe = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

/** Find a quoted phrase in the passage, tolerating whitespace/punctuation drift. */
function findQuote(text: string, phrases: string[]): { start: number; end: number } | null {
  for (const phrase of phrases) {
    let words = phrase.split(/\W+/).filter(Boolean);
    while (words.length >= 4) {
      const re = new RegExp(words.map(escapeRe).join("\\W+"), "i");
      const m = re.exec(text);
      if (m) return { start: m.index, end: m.index + m[0].length };
      words = words.slice(0, -1);
    }
  }
  return null;
}

const WINDOW = 420;

function Excerpt({ text, phrases }: { text: string; phrases: string[] }) {
  const [full, setFull] = useState(false);
  const hit = findQuote(text, phrases);
  let start = 0;
  let end = Math.min(text.length, WINDOW);
  if (hit && !full) {
    start = Math.max(0, hit.start - 160);
    end = Math.min(text.length, Math.max(hit.end + 200, start + WINDOW));
  }
  if (full) {
    start = 0;
    end = text.length;
  }
  const parts: ReactNode[] = [];
  if (start > 0) parts.push("…");
  if (hit && hit.start >= start && hit.end <= end) {
    parts.push(text.slice(start, hit.start), <mark key="q">{text.slice(hit.start, hit.end)}</mark>, text.slice(hit.end, end));
  } else {
    parts.push(text.slice(start, end));
  }
  if (end < text.length) parts.push("…");
  return (
    <div className="yx-src-text">
      {parts}
      {text.length > WINDOW && (
        <div>
          <button
            type="button"
            className="yx-btn yx-btn-ghost yx-btn-sm"
            style={{ marginTop: 6 }}
            onClick={(e) => {
              e.stopPropagation();
              setFull((f) => !f);
            }}
          >
            {full ? "Show less" : "Show the whole passage"}
          </button>
        </div>
      )}
    </div>
  );
}

// ------------------------------------------------------------- the margin
export interface MarginEntry {
  question: string;
  answer: string;
  sources: Passage[];
  citations?: Citation[];
  worth?: Passage[];
}

function SourceRow({
  src,
  label,
  domId,
  open,
  onToggle,
  phrases,
}: {
  src: Passage;
  label: number;
  domId: string;
  open: boolean;
  onToggle: () => void;
  phrases: string[];
}) {
  return (
    <div className="yx-src" data-open={open} onClick={onToggle} id={domId}>
      <div className="yx-src-head">
        <span className="yx-src-n">{label}</span>
        <span className="yx-src-title">
          {src.title}
          {src.kind === "video" && <span className="yx-badge">{src.timestamp ? "WEBINAR" : "VIDEO"}</span>}
          {src.kind === "anecdote" && <span className="yx-badge">ANECDOTE</span>}
        </span>
      </div>
      <div className="yx-src-meta">
        {src.corpus}
        {src.byline && !src.corpus?.includes(src.byline) ? ` · ${src.byline}` : ""}
        {src.unit ? ` · ${src.unit}` : ""}
        {src.page ? ` · page ${src.page}` : ""}
        {src.timestamp ? ` · at ${src.timestamp}` : ""}
        {src.url && src.kind !== "video" && (
          <>
            {" · "}
            <a href={`${src.url}${src.page ? `#page=${src.page}` : ""}`} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()}>
              Read →
            </a>
          </>
        )}
        {(src.kind === "video" ? [src.url] : src.videos).filter(Boolean).map((v) => (
          <span key={v}>
            {" · "}
            <a href={v} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()}>
              Watch ▶
            </a>
          </span>
        ))}
      </div>
      {open && <Excerpt text={src.text} phrases={phrases} />}
    </div>
  );
}

export function GroundingMargin({
  entries,
  openKey,
  setOpenKey,
}: {
  entries: MarginEntry[];
  openKey: string | null;
  setOpenKey: (key: string | null) => void;
}) {
  return (
    <aside className="yx-margin">
      <h4>Grounding</h4>
      {entries.length === 0 && <p className="yx-margin-empty">Ask a question and the passages the answer cites appear here, like marginalia.</p>}
      {entries.map((entry, qi) => {
        const cited = (entry.citations ?? []).filter((c) => !c.dangling).map((c) => c.n);
        const shown = entry.citations === undefined ? [] : cited;
        const phrases = quotedPhrases(entry.answer);
        return (
          <div key={qi}>
            <div className="yx-margin-q">
              <span>{qi + 1}</span>
              {entry.question}
            </div>
            {entry.citations !== undefined && shown.length === 0 && (
              <p className="yx-margin-empty">This answer doesn&apos;t cite any passages from the course material.</p>
            )}
            {shown.map((n) => {
              const src = entry.sources.find((s) => s.n === n);
              if (!src) return null;
              const key = `${qi}:${n}`;
              return (
                <SourceRow
                  key={key}
                  src={src}
                  label={n}
                  domId={`yx-src-${qi}-${n}`}
                  open={openKey === key}
                  onToggle={() => setOpenKey(openKey === key ? null : key)}
                  phrases={phrases}
                />
              );
            })}
            {!!entry.worth?.length && (
              <div className="yx-worth">
                <b>Worth reading</b>
                {entry.worth.map((src) => {
                  const key = `${qi}:w${src.n}`;
                  return (
                    <SourceRow
                      key={key}
                      src={src}
                      label={src.n}
                      domId={`yx-src-${qi}-w${src.n}`}
                      open={openKey === key}
                      onToggle={() => setOpenKey(openKey === key ? null : key)}
                      phrases={[]}
                    />
                  );
                })}
              </div>
            )}
          </div>
        );
      })}
    </aside>
  );
}
