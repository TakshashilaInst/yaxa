"use client";

/**
 * The Learn session's own pieces, shown inside the tutor chat: the week's case above the
 * conversation, and "Explain it back" below it. Explain-back is never graded: Yaxa says what
 * the learner has got and asks about what is still missing.
 */
import { useState } from "react";

import { yaxa, type CaseView, type ExplainResult } from "@/lib/yaxa-api";

const MIN_WORDS = 25;
const count = (t: string) => t.trim().split(/\s+/).filter(Boolean).length;

export function CaseCard({ c }: { c: CaseView }) {
  const [open, setOpen] = useState(true);
  return (
    <section className="yx-card" style={{ marginBottom: 16 }}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 8, alignItems: "baseline" }}>
        <div className="yx-eyebrow">This session&apos;s case</div>
        <button className="yx-btn yx-btn-sm yx-btn-ghost" onClick={() => setOpen(!open)}>{open ? "Hide" : "Show"}</button>
      </div>
      <h2 style={{ fontSize: 19, margin: "4px 0 6px" }}>{c.title}</h2>
      {open && c.situation.split(/\n{2,}/).map((p, i) => <p key={i} style={{ margin: "0 0 8px" }}>{p}</p>)}
    </section>
  );
}

export function ExplainBack({ module, session, explained }: { module: string; session: string; explained: boolean }) {
  const [text, setText] = useState("");
  const [result, setResult] = useState<ExplainResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(explained);
  const n = count(text);

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      const r = await yaxa.caseExplain(module, session, text);
      setResult(r);
      if (!r.missing.length) setDone(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
    setBusy(false);
  };

  return (
    <section className="yx-card" style={{ margin: "18px 0" }}>
      <div className="yx-eyebrow">Explain it back{done ? " · done ✓" : ""}</div>
      <p className="yx-muted" style={{ margin: "4px 0 8px" }}>
        When you think you have it, put the whole idea in your own words, as if to a colleague. Nothing is graded: Yaxa tells you what
        you&apos;ve got and asks about anything still missing.
      </p>
      {result ? (
        <>
          {!!result.got.length && (
            <>
              <b>You&apos;ve got</b>
              <ul style={{ margin: "4px 0 8px" }}>{result.got.map((g, i) => <li key={i}>{g}</li>)}</ul>
            </>
          )}
          {!!result.missing.length && (
            <>
              <b>Still to think about</b>
              <ul style={{ margin: "4px 0 8px" }}>{result.missing.map((g, i) => <li key={i}>{g}</li>)}</ul>
            </>
          )}
          <p style={{ margin: "0 0 10px" }}>{result.feedback}</p>
          <button className="yx-btn yx-btn-sm yx-btn-ghost" onClick={() => setResult(null)}>Try again</button>
        </>
      ) : (
        <>
          <textarea value={text} rows={5} style={{ width: "100%" }} placeholder="In my own words…" onChange={(e) => setText(e.target.value)} />
          <div style={{ display: "flex", gap: 10, alignItems: "center", marginTop: 6 }}>
            <button className="yx-btn yx-btn-sm yx-btn-primary" disabled={busy || n < MIN_WORDS} onClick={() => void submit()}>
              {busy ? "Reading…" : "Explain it back"}
            </button>
            <span className="yx-muted">{n < MIN_WORDS ? `${MIN_WORDS - n} more words` : `${n} words`}</span>
          </div>
        </>
      )}
      {error && <p className="yx-error" style={{ marginTop: 8 }}>{error}</p>}
    </section>
  );
}
