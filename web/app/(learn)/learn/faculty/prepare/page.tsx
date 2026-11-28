"use client";

/**
 * Prepare next week: the cohort's sessions in the next two weeks (or every week), each with
 * its Learn case, Apply layer and Check, marked Missing, Draft or Live. "Draft what's missing"
 * has Yaxa write first drafts of the missing ones; faculty then review and approve each in its
 * editor. Faculty start with the modules they teach.
 */
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { Crumbs, FullPageMessage, LearnHeader, Thinking, useMe } from "@/features/yaxa/common";
import { yaxa, type CohortRow, type PrepRow, type PrepStatus } from "@/lib/yaxa-api";

const errText = (e: unknown) => (e instanceof Error ? e.message : String(e));
const LABEL: Record<PrepStatus, string> = { none: "Missing", draft: "Draft", approved: "Live" };
const STEPS = [
  { key: "case", name: "Learn case", editor: "/learn/faculty/cases" },
  { key: "layer", name: "Apply layer", editor: "/learn/faculty/layers" },
  { key: "check", name: "Check", editor: "/learn/faculty/checks" },
] as const;

const day = (iso: string) =>
  new Date(`${iso}T12:00:00+05:30`).toLocaleDateString("en-IN", { weekday: "short", day: "numeric", month: "short", timeZone: "Asia/Kolkata" });

function Row({ r, onDone }: { r: PrepRow; onDone: () => void }) {
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const missing = STEPS.filter((s) => r[s.key] === "none").length;
  async function draft() {
    setBusy(true); setNote(null);
    try {
      const out = await yaxa.prepareDraft(r.module, r.session);
      setNote(out.errors.length ? `Some drafts failed: ${out.errors.join("; ")}` : "Drafted. Review and approve each one.");
      onDone();
    } catch (e) { setNote(errText(e)); }
    setBusy(false);
  }
  const q = `?module=${encodeURIComponent(r.module)}&session=${encodeURIComponent(r.session)}`;
  return (
    <li className={`yx-prep-row${r.past ? " is-past" : ""}`}>
      <div className="yx-prep-head">
        <b>{r.session}</b> {r.title}
        <span className="yx-meta"> · {r.module} · {day(r.date)}{r.time ? ` ${r.time}` : ""}{r.host ? ` · ${r.host}` : ""}</span>
      </div>
      <div className="yx-prep-steps">
        {STEPS.map((s) => (
          <Link key={s.key} href={`${s.editor}${q}`} className={`yx-prep-chip is-${r[s.key]}`}>
            {s.name}: {LABEL[r[s.key]]}
          </Link>
        ))}
        {missing > 0 && (
          <button type="button" className="yx-btn yx-btn-sm yx-btn-primary" disabled={busy} onClick={draft}>
            {busy ? "Drafting…" : `Draft what's missing (${missing})`}
          </button>
        )}
      </div>
      {busy && <Thinking socratic={false} />}
      {note && <p className="yx-muted" style={{ margin: "6px 0 0" }}>{note}</p>}
    </li>
  );
}

export default function PreparePage() {
  const { me, error: meError } = useMe();
  const [cohorts, setCohorts] = useState<CohortRow[]>([]);
  const [cohort, setCohort] = useState("");
  const [allWeeks, setAllWeeks] = useState(false);
  const [mineOnly, setMineOnly] = useState(true);
  const [rows, setRows] = useState<PrepRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!me) return;
    yaxa.cohorts().then((c) => { setCohorts(c); setCohort((x) => x || c[c.length - 1]?.code || ""); }).catch((e) => setError(errText(e)));
  }, [me]);
  const load = useCallback(() => {
    if (cohort) yaxa.prepare(cohort, allWeeks).then((d) => setRows(d.sessions)).catch((e) => setError(errText(e)));
  }, [cohort, allWeeks]);
  useEffect(load, [load]);

  if (meError) return <div className="yx"><FullPageMessage><p className="yx-error">{meError}</p></FullPageMessage></div>;
  if (!me) return <div className="yx"><FullPageMessage><p className="yx-muted">Loading…</p></FullPageMessage></div>;
  const teaches = me.teaches ?? [];
  const shown = (rows ?? []).filter((r) => !(mineOnly && teaches.length) || teaches.includes(r.module));
  const dates = [...new Set(shown.map((r) => r.date))];

  return (
    <div className="yx">
      <LearnHeader me={me} />
      <main className="yx-page" style={{ maxWidth: 900 }}>
        <Crumbs items={[{ label: "Cohort brief", href: "/learn/faculty" }, { label: "Prepare next week" }]} />
        <h1 style={{ margin: "10px 0 4px" }}>Prepare next week</h1>
        <p className="yx-muted" style={{ marginTop: 0, fontSize: 15 }}>
          Students see Learn, Apply and Check for a session only once you approve them. Yaxa can write first drafts of
          whatever is missing; check the facts and approve each in its editor.
        </p>
        <div className="yx-sched-toolbar">
          <select value={cohort} onChange={(e) => setCohort(e.target.value)} aria-label="Cohort">
            {cohorts.map((c) => <option key={c.code} value={c.code}>{c.code}</option>)}
          </select>
          <label className="yx-meta" style={{ display: "inline-flex", gap: 6, alignItems: "center" }}>
            <input type="checkbox" checked={allWeeks} onChange={(e) => setAllWeeks(e.target.checked)} /> Every week
          </label>
          {teaches.length > 0 && (
            <label className="yx-meta" style={{ display: "inline-flex", gap: 6, alignItems: "center" }}>
              <input type="checkbox" checked={mineOnly} onChange={(e) => setMineOnly(e.target.checked)} /> Only my modules
            </label>
          )}
        </div>
        {error && <p className="yx-error">{error}</p>}
        {rows && !shown.length && (
          <p className="yx-muted">No sessions in the next two weeks{mineOnly && teaches.length ? " for your modules" : ""}. Tick “Every week” to see the whole schedule.</p>
        )}
        {dates.map((d) => (
          <section key={d}>
            <h2 className="yx-prep-date">{day(d)}</h2>
            <ul className="yx-prep-list">{shown.filter((r) => r.date === d).map((r) => <Row key={r.session} r={r} onDone={load} />)}</ul>
          </section>
        ))}
      </main>
    </div>
  );
}
