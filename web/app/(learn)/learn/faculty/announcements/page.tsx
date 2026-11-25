"use client";

/**
 * Staff: post an announcement to a cohort (or one track). It appears at the top
 * of learners' home pages and goes out as one email to the cohort's group
 * address. Until email is set up, Yaxa gives a ready-made email to send.
 */
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { AnnouncementItem } from "@/features/yaxa/announcements";
import { FullPageMessage, LearnHeader, useMe } from "@/features/yaxa/common";
import { yaxa, type Announcement, type AnnouncementResult, type CohortDetail, type CohortRow } from "@/lib/yaxa-api";

const errText = (e: unknown) => (e instanceof Error ? e.message : String(e));

function EmailState({ r, onRetry }: { r: AnnouncementResult | null; onRetry: () => void }) {
  if (!r) return null;
  if (r.email === "sent") return <p className="yx-muted">Posted, and emailed to {r.to}.</p>;
  const why = {
    not_configured: "Posted in Yaxa. Email sending isn't set up yet, so send it to the group yourself:",
    no_group: "Posted in Yaxa. This cohort has no email group set (add it on the schedule page).",
    failed: "Posted in Yaxa, but the email didn't go out.",
  }[r.email as "not_configured" | "no_group" | "failed"];
  return (
    <p className="yx-muted">
      {why}{" "}
      {r.mailto && <a href={r.mailto}>Open it as an email</a>}
      {r.email === "failed" && <> · <button type="button" className="yx-linklike" onClick={onRetry}>Try sending again</button></>}
    </p>
  );
}

export default function FacultyAnnouncements() {
  const { me, error: meError } = useMe();
  const [rows, setRows] = useState<CohortRow[]>([]);
  const [cohort, setCohort] = useState("");
  const [detail, setDetail] = useState<CohortDetail | null>(null);
  const [items, setItems] = useState<Announcement[]>([]);
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [track, setTrack] = useState("");
  const [session, setSession] = useState("");
  const [result, setResult] = useState<AnnouncementResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!me) return;
    yaxa.cohorts().then((r) => { setRows(r); setCohort((c) => c || r[r.length - 1]?.code || ""); }).catch((e) => setError(errText(e)));
  }, [me]);
  const load = useCallback(() => {
    if (!cohort) return;
    yaxa.announcements(cohort).then((l) => setItems(l.items)).catch((e) => setError(errText(e)));
    yaxa.cohort(cohort).then(setDetail).catch(() => setDetail(null));
  }, [cohort]);
  useEffect(load, [load]);

  async function post() {
    setBusy(true);
    setError(null);
    try {
      setResult(await yaxa.postAnnouncement({ cohort, title, body, track: track || null, session: session || null }));
      setTitle(""); setBody(""); setSession("");
      load();
    } catch (e) {
      setError(errText(e));
    } finally {
      setBusy(false);
    }
  }

  if (meError || (error && !rows.length)) return <div className="yx"><FullPageMessage><p className="yx-error">{meError || error}</p></FullPageMessage></div>;
  if (!me) return <div className="yx"><FullPageMessage><p className="yx-muted">Loading…</p></FullPageMessage></div>;
  const tracks = Object.keys(detail?.track_email_groups ?? {}).length ? Object.keys(detail!.track_email_groups) : ["APP", "TP", "DFA"];

  return (
    <div className="yx">
      <LearnHeader me={me} center={<span className="yx-header-title">Announcements</span>} />
      <main className="yx-page" style={{ maxWidth: 820 }}>
        <p style={{ margin: 0 }}><Link href="/learn/faculty">← Faculty</Link></p>
        <h1 style={{ margin: "10px 0 4px" }}>Announcements</h1>
        <div className="yx-sched-toolbar">
          <select value={cohort} onChange={(e) => { setCohort(e.target.value); setResult(null); }} aria-label="Cohort">
            {rows.map((r) => <option key={r.code} value={r.code}>{r.code}</option>)}
          </select>
          {detail && <span className="yx-muted" style={{ fontSize: 15 }}>Email group: {detail.email_group || "not set"}</span>}
        </div>
        <section className="yx-card" style={{ display: "grid", gap: 8 }}>
          <input value={title} maxLength={200} onChange={(e) => setTitle(e.target.value)} placeholder="Title, e.g. CS12 moves to 2 pm this Saturday" aria-label="Title" />
          <textarea rows={5} value={body} maxLength={4000} onChange={(e) => setBody(e.target.value)} placeholder="The message" aria-label="Message" />
          <div className="yx-sched-toolbar" style={{ margin: 0 }}>
            <label>For <select value={track} onChange={(e) => setTrack(e.target.value)}>
              <option value="">Everyone in {cohort}</option>
              {tracks.map((t) => <option key={t} value={t}>{t} only</option>)}
            </select></label>
            <label>About session <select value={session} onChange={(e) => setSession(e.target.value)}>
              <option value="">None</option>
              {(detail?.modules ?? []).map((m) => (
                <optgroup key={m.code} label={m.title}>{m.sessions.map((s) => <option key={s.code} value={s.code}>{s.code} {s.title}</option>)}</optgroup>
              ))}
            </select></label>
            <button type="button" className="yx-btn yx-btn-primary" disabled={busy || !cohort || !title.trim() || !body.trim()} onClick={post}>
              {busy ? "Posting…" : "Post and email"}
            </button>
          </div>
          {error && <p className="yx-error">{error}</p>}
          <EmailState r={result} onRetry={() => result && yaxa.emailAnnouncement(cohort, result.item.id).then(setResult).catch((e) => setError(errText(e)))} />
        </section>
        <h2 className="yx-section-title" style={{ marginTop: 22 }}>Posted to {cohort}</h2>
        {!items.length && <p className="yx-muted">Nothing yet.</p>}
        <div style={{ display: "grid", gap: 12 }}>
          {items.map((a) => (
            <div key={a.id}>
              <AnnouncementItem a={a} />
              <p className="yx-muted" style={{ margin: "4px 2px 0", fontSize: 14 }}>
                {a.emailed_at ? `Emailed to ${a.email_to}` : "Not emailed"}
                {!a.emailed_at && <> · <button type="button" className="yx-linklike" onClick={() => yaxa.emailAnnouncement(cohort, a.id).then((r) => { setResult(r); load(); }).catch((e) => setError(errText(e)))}>Email it now</button></>}
                {" · "}<button type="button" className="yx-linklike" onClick={() => yaxa.hideAnnouncement(cohort, a.id).then(load)}>Remove</button>
              </p>
            </div>
          ))}
        </div>
      </main>
    </div>
  );
}
