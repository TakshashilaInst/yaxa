"use client";

/**
 * Libraries: what's in Yaxa's course libraries, the last sync from the shared
 * Drive folder, recordings waiting for a student-name check, and files Yaxa
 * couldn't use. Staff only.
 */
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { FullPageMessage, LearnHeader, useMe } from "@/features/yaxa/common";
import { yaxa, type LibraryStatus, type ReviewItem } from "@/lib/yaxa-api";

const DRIVE_FOLDER = "https://drive.google.com/drive/folders/1lDJWNQMgvf2ccSygdVcyyuLNPCRojut3";
const LIBRARY_NAMES: Record<string, string> = {
  "GCPP-PAC": "Policy Analysis and Concepts",
  "GCPP-ER1": "Economic Reasoning I",
  "GCPP-COMM": "Communication",
  GCPP173: "Public Finance capsule",
  APP: "Advanced Public Policy",
  TP: "Technology and Policy",
  DFA: "Defence and Foreign Affairs",
  "FACULTY-PRANAY": "Pranay Kotasthane's writing",
  "FACULTY-NITIN": "Nitin Pai's writing",
  "FACULTY-ANUPAM": "Anupam Manur's writing",
};

function when(iso?: string): string {
  if (!iso) return "never";
  return new Date(iso).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" });
}

function summaryLine(s?: Record<string, number>): string {
  if (!s) return "";
  const parts = [
    s.added && `${s.added} added`,
    s.replaced && `${s.replaced} updated`,
    s.relabelled && `${s.relabelled} renamed or moved`,
    s.retired && `${s.retired} removed`,
    s.review && `${s.review} waiting for a name check`,
    s.waiting && `${s.waiting} recordings left for tonight (transcription budget)`,
    s.failed && `${s.failed} failed`,
    s.skipped && `${s.skipped} couldn't be used`,
  ].filter(Boolean);
  return parts.length ? parts.join(" · ") : "nothing new";
}

function ReviewCard({ item, onDone }: { item: ReviewItem; onDone: () => void }) {
  const [choice, setChoice] = useState<Record<string, "keep" | "remove">>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const allDecided = item.flags.every((f) => choice[f.name]);
  const submit = async (reject: boolean) => {
    setBusy(true);
    setError(null);
    try {
      await yaxa.libraryDecide(item.drive_id, reject ? { reject: true } : { decisions: choice });
      onDone();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setBusy(false);
    }
  };
  return (
    <div className="yx-card" style={{ padding: 16, marginBottom: 12 }}>
      <div className="yx-eyebrow">{item.path}</div>
      <h3 style={{ margin: "4px 0 10px", fontSize: 17 }}>{item.title || "Recording"}</h3>
      <p className="yx-muted" style={{ marginTop: 0 }}>
        These names are on the student list but are also part of a public figure&apos;s name. Is each one a student (remove it) or the
        public figure (keep it)?
      </p>
      {item.flags.map((f) => (
        <div key={f.name} style={{ borderTop: "1px solid var(--yx-line)", padding: "10px 0" }}>
          <div>
            <b>{f.name}</b> <span className="yx-muted">at {f.at}</span>
          </div>
          <p style={{ margin: "4px 0 8px", fontStyle: "italic" }}>“…{f.context}…”</p>
          <div style={{ display: "flex", gap: 8 }}>
            <button className={`yx-btn yx-btn-sm ${choice[f.name] === "keep" ? "yx-btn-primary" : "yx-btn-ghost"}`}
              onClick={() => setChoice((c) => ({ ...c, [f.name]: "keep" }))} disabled={busy}>
              Public name, keep
            </button>
            <button className={`yx-btn yx-btn-sm ${choice[f.name] === "remove" ? "yx-btn-maroon" : "yx-btn-ghost"}`}
              onClick={() => setChoice((c) => ({ ...c, [f.name]: "remove" }))} disabled={busy}>
              Student, remove
            </button>
          </div>
        </div>
      ))}
      {error && <p className="yx-error">{error}</p>}
      <div style={{ display: "flex", gap: 8, marginTop: 10 }}>
        <button className="yx-btn yx-btn-primary" onClick={() => void submit(false)} disabled={!allDecided || busy}
          title={allDecided ? "Add this recording to the library" : "Decide on every name first"}>
          Approve
        </button>
        <button className="yx-btn yx-btn-ghost" onClick={() => void submit(true)} disabled={busy}>
          Don&apos;t use this recording
        </button>
      </div>
    </div>
  );
}

export default function LibraryPage() {
  const { me, error: meError } = useMe();
  const [status, setStatus] = useState<LibraryStatus | null>(null);
  const [review, setReview] = useState<ReviewItem[]>([]);
  const [error, setError] = useState<string | null>(null);
  const privileged = !!me && (me.is_admin || me.role === "faculty");

  const load = useCallback(async () => {
    try {
      const [s, r] = await Promise.all([yaxa.library(), yaxa.libraryReview()]);
      setStatus(s);
      setReview(r);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, []);

  useEffect(() => {
    if (!privileged) return;
    Promise.all([yaxa.library(), yaxa.libraryReview()])
      .then(([s, r]) => {
        setStatus(s);
        setReview(r);
      })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, [privileged]);

  // while a sync is queued or running, check every 10 seconds
  const busy = !!status && (status.running || status.queued);
  useEffect(() => {
    if (!busy) return;
    const t = setInterval(() => void load(), 10_000);
    return () => clearInterval(t);
  }, [busy, load]);

  const syncNow = async () => {
    try {
      await yaxa.librarySync();
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  if (meError) return <div className="yx"><FullPageMessage><p className="yx-error">{meError}</p></FullPageMessage></div>;
  if (!me) return <div className="yx"><FullPageMessage><p className="yx-muted">Loading…</p></FullPageMessage></div>;
  if (!privileged) {
    return <div className="yx"><FullPageMessage><p>This page is for Takshashila staff. <Link href="/learn">Back to your modules</Link></p></FullPageMessage></div>;
  }

  const last = status?.last_run;
  return (
    <div className="yx">
      <LearnHeader me={me} center={<span className="yx-header-title">Libraries</span>} />
      <main className="yx-page">
        <div className="yx-eyebrow">For staff</div>
        <h1 style={{ margin: "4px 0 6px" }}>Yaxa&apos;s course libraries</h1>
        <p className="yx-lede" style={{ marginTop: 0 }}>
          Everything Yaxa cites comes from the shared Drive folder <a href={DRIVE_FOLDER} target="_blank" rel="noreferrer">0012 Yaxa Library</a>.
          Yaxa checks it every night; press Sync now to check straight away.
        </p>

        <div className="yx-tools" style={{ gap: 12, margin: "12px 0 20px", alignItems: "center" }}>
          <button className="yx-btn yx-btn-primary" onClick={() => void syncNow()} disabled={busy}>
            {status?.running ? "Syncing…" : status?.queued ? "Starting…" : "Sync now"}
          </button>
          <span className="yx-muted">
            {last?.error ? <span className="yx-error">{last.error}</span> : <>Last sync {when(last?.finished)}{last?.summary ? `: ${summaryLine(last.summary)}` : ""}</>}
          </span>
        </div>
        {error && <p className="yx-error">{error}</p>}

        {!!review.length && (
          <section style={{ marginBottom: 28 }}>
            <h2 style={{ fontSize: 20 }}>Needs a name check ({review.length})</h2>
            {review.map((item) => (
              <ReviewCard key={item.drive_id} item={item} onDone={() => void load()} />
            ))}
          </section>
        )}

        {status && (
          <section style={{ marginBottom: 28 }}>
            <h2 style={{ fontSize: 20 }}>Libraries</h2>
            <table className="yx-table">
              <thead>
                <tr>
                  <th>Library</th>
                  <th>In Yaxa</th>
                  <th>Being processed</th>
                  <th>Waiting for a check</th>
                  <th>Failed</th>
                </tr>
              </thead>
              <tbody>
                {status.libraries.map(({ kb, counts }) => (
                  <tr key={kb}>
                    <td>{LIBRARY_NAMES[kb] ?? kb}</td>
                    <td>{counts.live ?? 0}</td>
                    <td>{(counts.new ?? 0) + (counts.processing ?? 0) + (counts.approved ?? 0)}</td>
                    <td>{counts.review ?? 0}</td>
                    <td>{counts.failed ?? 0}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        )}

        {!!status?.problems.length && (
          <section style={{ marginBottom: 28 }}>
            <h2 style={{ fontSize: 20 }}>Files Yaxa couldn&apos;t use ({status.problems.length})</h2>
            <p className="yx-muted" style={{ marginTop: 0 }}>Fix the file in Drive (rename it, move it, or save it as PDF) and the next sync will try again.</p>
            <table className="yx-table">
              <thead>
                <tr>
                  <th>File</th>
                  <th>Why</th>
                </tr>
              </thead>
              <tbody>
                {status.problems.map((p) => (
                  <tr key={p.drive_id}>
                    <td style={{ wordBreak: "break-word" }}>{p.path}</td>
                    <td>{p.error || p.status}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        )}

        <section className="yx-card" style={{ padding: 16 }}>
          <h2 style={{ fontSize: 18, marginTop: 0 }}>How to add files</h2>
          <ul style={{ margin: 0, paddingLeft: 18 }}>
            <li>Put readings in the module&apos;s <b>Readings</b> folder, for example <i>GCPP › DFA Defence and Foreign Affairs › DFA-AS Introduction to Arthashastra › Readings</i>.</li>
            <li>Put recordings in <b>Recordings › &lt;cohort&gt;</b>, for example <i>Recordings › DFA27 Oct 2026</i>. Add Zoom&apos;s transcript (.vtt) with the same name: it tells Yaxa who is speaking, so student names come out reliably.</li>
            <li>Name files <b>&lt;code&gt; - &lt;title&gt; - &lt;speaker&gt;</b>, for example <i>CS22 - Concept Cluster I - Kajari Kamal.mp4</i>. Readings don&apos;t need a speaker.</li>
            <li>PDF, Word (.docx), Markdown and text files work. Google Docs and Slides don&apos;t yet: download them as PDF first.</li>
            <li>To take something out of Yaxa, move it to <b>_Retired</b>. Anything in <b>_Not for Yaxa</b> is never read.</li>
          </ul>
        </section>
      </main>
    </div>
  );
}
