"use client";

/**
 * Staff: each cohort's schedule. Pick a cohort, set its sessions (by session
 * code) with date, time, host and webinar link, add other key dates, share the
 * join link, and put members on their tracks. A new cohort can start as a copy
 * of the last one, shifted by some weeks. All times are IST.
 */
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { FullPageMessage, LearnHeader, useMe } from "@/features/yaxa/common";
import {
  yaxa,
  type CohortDetail,
  type CohortMember,
  type CohortRow,
  type CohortSchedule,
  type CohortSession,
} from "@/lib/yaxa-api";

const BLANK_SESSION: CohortSession = { code: "", date: "", time: "11:30", host: "", webinar_url: "", note: "" };
const errText = (e: unknown) => (e instanceof Error ? e.message : String(e));

function NewCohort({ rows, onMade }: { rows: CohortRow[]; onMade: (code: string) => void }) {
  const [code, setCode] = useState("");
  const [from, setFrom] = useState("");
  const [weeks, setWeeks] = useState(12);
  const [error, setError] = useState<string | null>(null);
  async function make() {
    setError(null);
    const to = code.trim().toUpperCase();
    try {
      if (from) await yaxa.copyCohort(from, to, weeks);
      else
        await yaxa.saveCohort({ code: to, programme: "GCPP", start: "", email_group: "", track_email_groups: {}, join_code: "",
          join_open: true, sessions: [], dates: [] });
      onMade(to);
      setCode("");
    } catch (e) {
      setError(errText(e));
    }
  }
  return (
    <div className="yx-sched-toolbar">
      <input placeholder="New cohort code, e.g. GCPP46" value={code} onChange={(e) => setCode(e.target.value)} />
      <select value={from} onChange={(e) => setFrom(e.target.value)} aria-label="Copy from">
        <option value="">Start empty</option>
        {rows.map((r) => <option key={r.code} value={r.code}>Copy from {r.code}</option>)}
      </select>
      {from && (
        <label>shifted by <input type="number" min={0} max={104} value={weeks} onChange={(e) => setWeeks(Number(e.target.value))} style={{ width: 64 }} /> weeks</label>
      )}
      <button type="button" className="yx-btn yx-btn-ghost yx-btn-sm" disabled={!code.trim()} onClick={make}>Create</button>
      {error && <span className="yx-error">{error}</span>}
    </div>
  );
}

function Members({ cohort, rows, tracks }: { cohort: string; rows: CohortRow[]; tracks: string[] }) {
  const [members, setMembers] = useState<CohortMember[]>([]);
  const load = useCallback(() => { yaxa.cohortMembers(cohort).then(setMembers).catch(() => setMembers([])); }, [cohort]);
  useEffect(load, [load]);
  if (!members.length) return <p className="yx-muted">No one has joined yet. Send the join link in the welcome email.</p>;
  return (
    <div className="yx-sched-scroll">
      <table className="yx-sched-table">
        <thead><tr><th>Name</th><th>Track</th><th>Cohort</th></tr></thead>
        <tbody>
          {members.map((m) => (
            <tr key={m.user_id}>
              <td>{m.display_name}</td>
              <td>
                <select value={m.track ?? ""} onChange={(e) => yaxa.setMember(cohort, m.user_id, cohort, e.target.value || null).then(load)}>
                  <option value="">Not chosen</option>
                  {tracks.map((t) => <option key={t} value={t}>{t}</option>)}
                </select>
              </td>
              <td>
                <select value={cohort} onChange={(e) => yaxa.setMember(cohort, m.user_id, e.target.value, m.track).then(load)}>
                  {rows.map((r) => <option key={r.code} value={r.code}>{r.code}</option>)}
                </select>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function SchedulePage() {
  const { me, error: meError } = useMe();
  const [rows, setRows] = useState<CohortRow[]>([]);
  const [code, setCode] = useState("");
  const [detail, setDetail] = useState<CohortDetail | null>(null);
  const [draft, setDraft] = useState<CohortSchedule | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadRows = useCallback(() => yaxa.cohorts().then((r) => { setRows(r); return r; }), []);
  useEffect(() => {
    if (!me) return;
    loadRows().then((r) => setCode((c) => c || r[r.length - 1]?.code || "")).catch((e) => setError(errText(e)));
  }, [me, loadRows]);
  useEffect(() => {
    if (!code) return;
    yaxa.cohort(code).then((d) => { setDetail(d); setDraft(d); setStatus(null); }).catch((e) => setError(errText(e)));
  }, [code]);

  if (meError || error) return <div className="yx"><FullPageMessage><p className="yx-error">{meError || error}</p><p><Link href="/learn/faculty">Back</Link></p></FullPageMessage></div>;
  if (!me) return <div className="yx"><FullPageMessage><p className="yx-muted">Loading…</p></FullPageMessage></div>;

  const sessionNames = new Map((detail?.modules ?? []).flatMap((m) => m.sessions.map((s) => [s.code, s.title] as const)));
  const set = (patch: Partial<CohortSchedule>) => draft && setDraft({ ...draft, ...patch });
  const setSession = (i: number, patch: Partial<CohortSession>) =>
    draft && set({ sessions: draft.sessions.map((s, j) => (j === i ? { ...s, ...patch } : s)) });
  const joinUrl = draft?.join_code ? `${window.location.origin}/learn/join/${draft.join_code}` : "";
  const tracks = Object.keys(draft?.track_email_groups ?? {}).length ? Object.keys(draft!.track_email_groups) : ["APP", "TP", "DFA"];

  async function save() {
    if (!draft) return;
    setStatus("Saving…");
    try {
      const sorted = { ...draft, sessions: [...draft.sessions].sort((a, b) => `${a.date}${a.time}`.localeCompare(`${b.date}${b.time}`)) };
      const saved = await yaxa.saveCohort(sorted);
      setDraft(saved);
      setStatus("Saved");
      loadRows();
    } catch (e) {
      setStatus(errText(e));
    }
  }

  return (
    <div className="yx">
      <LearnHeader me={me} center={<span className="yx-header-title">Cohort schedules</span>} />
      <main className="yx-page">
        <p style={{ margin: 0 }}><Link href="/learn/faculty">← Faculty</Link></p>
        <h1 style={{ margin: "10px 0 4px" }}>Cohort schedules</h1>
        <p className="yx-lede" style={{ marginTop: 0 }}>Learners see their next seven days on their home page, with each session&apos;s readings. All times are IST.</p>

        <div className="yx-sched-toolbar">
          <select value={code} onChange={(e) => setCode(e.target.value)} aria-label="Cohort">
            {!rows.length && <option value="">No cohorts yet</option>}
            {rows.map((r) => <option key={r.code} value={r.code}>{r.code} · {r.members} joined · {r.sessions} sessions</option>)}
          </select>
        </div>
        <NewCohort rows={rows} onMade={(c) => loadRows().then(() => setCode(c))} />

        {draft && detail && (
          <>
            <section className="yx-card" style={{ marginTop: 16 }}>
              <h2 style={{ fontSize: 19, margin: 0 }}>Join link</h2>
              <p className="yx-muted" style={{ margin: "4px 0 8px", fontSize: 15 }}>Send this once, in the welcome email to the group. It works only while open.</p>
              <div className="yx-week-calendar-row">
                <input readOnly value={joinUrl || "Save to create the link"} onFocus={(e) => e.currentTarget.select()} aria-label="Join link" />
                {joinUrl && <button type="button" className="yx-btn yx-btn-ghost yx-btn-sm" onClick={() => navigator.clipboard.writeText(joinUrl)}>Copy</button>}
              </div>
              <label style={{ display: "inline-flex", gap: 6, marginTop: 8 }}>
                <input type="checkbox" checked={draft.join_open} onChange={(e) => set({ join_open: e.target.checked })} /> Open for joining
              </label>
              <div className="yx-sched-toolbar">
                <label>Programme <input value={draft.programme} onChange={(e) => set({ programme: e.target.value.toUpperCase() })} style={{ width: 90 }} /></label>
                <label>Starts <input type="date" value={draft.start} onChange={(e) => set({ start: e.target.value })} /></label>
                <label>Email group <input type="email" value={draft.email_group} onChange={(e) => set({ email_group: e.target.value })} placeholder="gcpp45@…" /></label>
              </div>
            </section>

            <section className="yx-card" style={{ marginTop: 14 }}>
              <h2 style={{ fontSize: 19, margin: 0 }}>Sessions</h2>
              <div className="yx-sched-scroll" style={{ marginTop: 8 }}>
                <table className="yx-sched-table">
                  <thead><tr><th style={{ width: "26%" }}>Session</th><th>Date</th><th>Time</th><th>Host</th><th>Webinar link</th><th>Note</th><th /></tr></thead>
                  <tbody>
                    {draft.sessions.map((s, i) => (
                      <tr key={i}>
                        <td>
                          <select value={s.code} onChange={(e) => setSession(i, { code: e.target.value })} title={sessionNames.get(s.code) ?? ""}>
                            <option value="">Pick…</option>
                            {detail.modules.map((m) => (
                              <optgroup key={m.code} label={m.title}>
                                {m.sessions.map((u) => <option key={u.code} value={u.code}>{u.code} {u.title}</option>)}
                              </optgroup>
                            ))}
                          </select>
                        </td>
                        <td><input type="date" value={s.date} onChange={(e) => setSession(i, { date: e.target.value })} /></td>
                        <td><input type="time" value={s.time} onChange={(e) => setSession(i, { time: e.target.value })} /></td>
                        <td><input value={s.host} onChange={(e) => setSession(i, { host: e.target.value })} /></td>
                        <td><input type="url" value={s.webinar_url} onChange={(e) => setSession(i, { webinar_url: e.target.value })} placeholder="https://zoom…" /></td>
                        <td><input value={s.note} onChange={(e) => setSession(i, { note: e.target.value })} /></td>
                        <td><button type="button" className="yx-linklike" onClick={() => set({ sessions: draft.sessions.filter((_, j) => j !== i) })}>Remove</button></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <button type="button" className="yx-btn yx-btn-ghost yx-btn-sm" style={{ marginTop: 8 }} onClick={() => set({ sessions: [...draft.sessions, { ...BLANK_SESSION }] })}>
                Add session
              </button>
            </section>

            <section className="yx-card" style={{ marginTop: 14 }}>
              <h2 style={{ fontSize: 19, margin: 0 }}>Other dates</h2>
              <p className="yx-muted" style={{ margin: "4px 0 8px", fontSize: 15 }}>Deadlines, debates, the capstone. Leave the track empty for everyone.</p>
              <table className="yx-sched-table">
                <thead><tr><th>Date</th><th>What</th><th>Track</th><th /></tr></thead>
                <tbody>
                  {draft.dates.map((d, i) => (
                    <tr key={i}>
                      <td><input type="date" value={d.date} onChange={(e) => set({ dates: draft.dates.map((x, j) => (j === i ? { ...x, date: e.target.value } : x)) })} /></td>
                      <td><input value={d.label} onChange={(e) => set({ dates: draft.dates.map((x, j) => (j === i ? { ...x, label: e.target.value } : x)) })} /></td>
                      <td>
                        <select value={d.track ?? ""} onChange={(e) => set({ dates: draft.dates.map((x, j) => (j === i ? { ...x, track: e.target.value || null } : x)) })}>
                          <option value="">Everyone</option>
                          {tracks.map((t) => <option key={t} value={t}>{t}</option>)}
                        </select>
                      </td>
                      <td><button type="button" className="yx-linklike" onClick={() => set({ dates: draft.dates.filter((_, j) => j !== i) })}>Remove</button></td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <button type="button" className="yx-btn yx-btn-ghost yx-btn-sm" style={{ marginTop: 8 }} onClick={() => set({ dates: [...draft.dates, { date: "", label: "", track: null }] })}>
                Add date
              </button>
            </section>

            <div className="yx-sched-toolbar">
              <button type="button" className="yx-btn yx-btn-primary" onClick={save}>Save {draft.code}</button>
              {status && <span className={status === "Saved" || status === "Saving…" ? "yx-muted" : "yx-error"}>{status}</span>}
            </div>

            <section className="yx-card" style={{ marginTop: 6 }}>
              <h2 style={{ fontSize: 19, margin: "0 0 8px" }}>Members</h2>
              <Members cohort={draft.code} rows={rows} tracks={tracks} />
            </section>
          </>
        )}
      </main>
    </div>
  );
}
