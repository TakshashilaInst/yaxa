"use client";

/**
 * After the session: for one cohort's session, a short note students see on the module page:
 * what we discussed, what's still open, and the recording. Yaxa can draft it from a recording
 * transcript in the library; faculty edit and approve. Opened from Prepare next week
 * Opened from a past session on the cohort schedule (?cohort=&module=&session=).
 */
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";

import { Crumbs, FullPageMessage, LearnHeader, Thinking, useMe } from "@/features/yaxa/common";
import { yaxa, type AfterAdmin } from "@/lib/yaxa-api";

const errText = (e: unknown) => (e instanceof Error ? e.message : String(e));
const lines = (t: string) => t.split("\n").map((x) => x.trim()).filter(Boolean);

function AfterEditor() {
  const { me, error: meError } = useMe();
  const params = useSearchParams();
  const cohort = params.get("cohort") || "", mod = params.get("module") || "", session = params.get("session") || "";
  const [n, setN] = useState<AfterAdmin | null>(null);
  const [discussed, setDiscussed] = useState("");
  const [open, setOpen] = useState("");
  const [url, setUrl] = useState("");
  const [file, setFile] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const show = (x: AfterAdmin) => {
    setN((old) => ({ ...x, transcripts: x.transcripts ?? old?.transcripts }));
    setDiscussed(x.discussed.join("\n")); setOpen(x.open.join("\n")); setUrl(x.recording_url);
    if (x.transcripts?.length) setFile((f) => f || x.transcripts![0].file);
  };
  useEffect(() => {
    if (!me || !session) return;
    yaxa.afterGet(cohort, mod, session).then(show).catch((e) => setError(errText(e)));
  }, [me, cohort, mod, session]);

  async function act(label: string, fn: () => Promise<AfterAdmin>, done: string) {
    setBusy(label); setError(null); setNote(null);
    try { show(await fn()); setNote(done); } catch (e) { setError(errText(e)); }
    setBusy(null);
  }

  if (meError) return <div className="yx"><FullPageMessage><p className="yx-error">{meError}</p></FullPageMessage></div>;
  if (!me) return <div className="yx"><FullPageMessage><p className="yx-muted">Loading…</p></FullPageMessage></div>;
  const dirty = !!n && (discussed !== n.discussed.join("\n") || open !== n.open.join("\n") || url !== n.recording_url);
  const STATUS = { none: "Not written", draft: "Draft", approved: "Live for students" } as const;

  return (
    <div className="yx">
      <LearnHeader me={me} />
      <main className="yx-page" style={{ maxWidth: 820 }}>
        <Crumbs items={[{ label: "Cohort brief", href: "/learn/faculty" }, { label: "Cohort schedules", href: "/learn/faculty/schedule" }, { label: `After ${session}` }]} />
        <h1 style={{ margin: "10px 0 4px" }}>After the session: {session}</h1>
        <p className="yx-muted" style={{ marginTop: 0, fontSize: 15 }}>
          {cohort} · {mod}. Students of {cohort} see this under the session once you approve it. {n && <b>{STATUS[n.status]}</b>}
        </p>
        {!session && <p className="yx-error">Open this page from a past session on the cohort schedule.</p>}
        {error && <p className="yx-error">{error}</p>}
        {note && <p className="yx-muted">{note}</p>}
        {n && (
          <>
            <div className="yx-card">
              <h2 style={{ fontSize: 17, margin: "0 0 6px" }}>Draft from a recording</h2>
              {n.transcripts?.length ? (
                <div className="yx-sched-toolbar">
                  <select value={file} onChange={(e) => setFile(e.target.value)} aria-label="Transcript">
                    {n.transcripts.map((t) => <option key={t.file} value={t.file}>{t.title}</option>)}
                  </select>
                  <button type="button" className="yx-btn yx-btn-sm" disabled={!!busy}
                    onClick={() => { if (n.status !== "none" && !window.confirm("Replace the note with a new draft?")) return; void act("draft", () => yaxa.afterDraft(cohort, mod, session, file), "Drafted. Check it against what happened, then approve."); }}>
                    {busy === "draft" ? "Drafting…" : "Draft the note"}
                  </button>
                </div>
              ) : (
                <p className="yx-muted" style={{ margin: 0 }}>No recording transcript for this session in the library yet. Recordings put in the Drive folder are transcribed overnight. You can also write the note yourself below.</p>
              )}
              {busy === "draft" && <Thinking socratic={false} />}
            </div>
            <div className="yx-card" style={{ marginTop: 12 }}>
              <label className="yx-eyebrow" htmlFor="discussed">What we discussed (one point per line)</label>
              <textarea id="discussed" rows={6} style={{ width: "100%" }} value={discussed} onChange={(e) => setDiscussed(e.target.value)} />
              <label className="yx-eyebrow" htmlFor="open" style={{ display: "block", marginTop: 10 }}>Still open (one question per line)</label>
              <textarea id="open" rows={3} style={{ width: "100%" }} value={open} onChange={(e) => setOpen(e.target.value)} />
              <label className="yx-eyebrow" htmlFor="rec" style={{ display: "block", marginTop: 10 }}>Recording link</label>
              <input id="rec" type="url" style={{ width: "100%" }} value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://drive.google.com/…" />
              <div className="yx-study-modes" style={{ marginTop: 12 }}>
                <button type="button" className="yx-btn yx-btn-sm" disabled={!!busy || !dirty}
                  onClick={() => void act("save", () => yaxa.afterSave(cohort, mod, session, { discussed: lines(discussed), open: lines(open), recording_url: url.trim() }), "Saved.")}>
                  {busy === "save" ? "Saving…" : "Save"}
                </button>
                {n.status === "approved" ? (
                  <button type="button" className="yx-btn yx-btn-sm yx-btn-ghost" disabled={!!busy}
                    onClick={() => void act("hide", () => yaxa.afterUnpublish(cohort, mod, session), "Hidden from students.")}>Hide from students</button>
                ) : (
                  <button type="button" className="yx-btn yx-btn-sm yx-btn-primary" disabled={!!busy || dirty || n.status === "none"} title={dirty ? "Save first" : ""}
                    onClick={() => void act("approve", () => yaxa.afterApprove(cohort, mod, session), "Approved: students of this cohort see it now.")}>Approve</button>
                )}
              </div>
            </div>
          </>
        )}
      </main>
    </div>
  );
}

export default function AfterPage() {
  return <Suspense fallback={null}><AfterEditor /></Suspense>;
}
