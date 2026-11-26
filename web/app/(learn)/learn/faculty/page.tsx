"use client";

/**
 * Faculty cohort brief: what students asked about a module, where they struggled
 * in practice, and what the course material didn't answer. Anonymised.
 */
import Link from "next/link";
import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { FullPageMessage, LearnHeader, Thinking, useMe } from "@/features/yaxa/common";
import { yaxa, type CheckBriefSession, type CohortBrief, type CohortRow } from "@/lib/yaxa-api";

const PERIODS = [
  { days: 7, label: "Last 7 days" },
  { days: 30, label: "Last 30 days" },
  { days: 90, label: "Last 90 days" },
];

function Stat({ value, label }: { value: number; label: string }) {
  return (
    <div className="yx-card yx-stat">
      <b>{value}</b>
      <span>{label}</span>
    </div>
  );
}

/** Before this week's webinars: what each cohort got wrong in the session checks. Anonymised. */
function WebinarPrep() {
  const [cohorts, setCohorts] = useState<CohortRow[]>([]);
  const [cohort, setCohort] = useState("");
  const [data, setData] = useState<{ cohort: string; sessions: CheckBriefSession[] } | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    yaxa.cohorts().then((c) => { setCohorts(c); setCohort((x) => x || c[0]?.code || ""); }).catch((e) => setError(String(e?.message ?? e)));
  }, []);
  useEffect(() => {
    if (!cohort) return;
    yaxa.checkBrief(cohort).then(setData).catch((e) => setError(String(e?.message ?? e)));
  }, [cohort]);
  const shown = data && data.cohort === cohort ? data : null;
  if (!cohorts.length) return null;
  return (
    <section style={{ margin: "8px 0 28px" }}>
      <div className="yx-tools" style={{ gap: 8, alignItems: "baseline" }}>
        <h2 style={{ fontSize: 20, margin: 0 }}>Before this week&apos;s webinars</h2>
        <select value={cohort} onChange={(e) => setCohort(e.target.value)}>
          {cohorts.map((c) => <option key={c.code} value={c.code}>{c.code}</option>)}
        </select>
      </div>
      {error && <p className="yx-error">{error}</p>}
      {!shown && !error && <p className="yx-muted">Loading…</p>}
      {shown && !shown.sessions.length && (
        <p className="yx-muted">No sessions with an approved check in the next 7 days. <Link href="/learn/faculty/checks">Set up session checks →</Link></p>
      )}
      {shown?.sessions.map((s) => (
        <div key={s.session} className="yx-card" style={{ margin: "10px 0" }}>
          <b>{s.session} · {s.title}</b> <span className="yx-muted">· {s.date}{s.time ? ` ${s.time}` : ""}</span>
          <p style={{ margin: "4px 0" }}>
            {s.took} of {s.enrolled || "?"} took the check · {s.ready} ready (4 or 5 out of 5)
          </p>
          {s.took > 0 && s.took < 3 && <p className="yx-muted" style={{ margin: 0 }}>Too few answers yet to say what the class got wrong.</p>}
          {!!s.misconceptions.length && (
            <ul style={{ margin: "6px 0 0" }}>
              {s.misconceptions.slice(0, 6).map((m, i) => {
                const tip = s.suggestions.find((x) => x.misconception === m.name);
                return (
                  <li key={i} style={{ marginBottom: 6 }}>
                    <b>{Math.round(m.share * 100)}%</b> {m.name} <span className="yx-muted">(on “{m.question}”)</span>
                    {tip && <div>In class: {tip.suggestion}</div>}
                  </li>
                );
              })}
            </ul>
          )}
          {s.suggestions_error && <p className="yx-muted">{s.suggestions_error}</p>}
        </div>
      ))}
    </section>
  );
}

export default function CohortBriefPage() {
  const { me, error: meError } = useMe();
  const [modules, setModules] = useState<{ code: string; title: string }[]>([]);
  const [moduleCode, setModuleCode] = useState("");
  const [days, setDays] = useState(7);
  const [loadedBrief, setBrief] = useState<CohortBrief | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<{ key: string; message: string } | null>(null);

  const privileged = !!me && (me.is_admin || me.role === "faculty");
  useEffect(() => {
    if (!privileged) return;
    yaxa
      .cohortModules()
      .then((m) => {
        setModules(m);
        setModuleCode((c) => c || m[0]?.code || "");
      })
      .catch((e) => setError({ key: "modules", message: e instanceof Error ? e.message : String(e) }));
  }, [privileged]);

  // the brief for the chosen module and period; `loading` is derived, not stored
  const key = `${moduleCode}:${days}`;
  useEffect(() => {
    if (!moduleCode) return;
    yaxa
      .cohortBrief(moduleCode, days)
      .then(setBrief)
      .catch((e) => setError({ key: `${moduleCode}:${days}`, message: e instanceof Error ? e.message : String(e) }));
  }, [moduleCode, days]);
  const refresh = async () => {
    setRefreshing(true);
    try {
      setBrief(await yaxa.cohortBrief(moduleCode, days, true));
    } catch (e) {
      setError({ key, message: e instanceof Error ? e.message : String(e) });
    }
    setRefreshing(false);
  };
  // only show the brief that matches the current choice of module and period
  const brief = loadedBrief && `${loadedBrief.module}:${loadedBrief.days}` === key ? loadedBrief : null;
  const errorText = error && (error.key === key || error.key === "modules") ? error.message : null;
  const loading = refreshing || (!!moduleCode && !brief && !errorText);

  if (meError) return <div className="yx"><FullPageMessage><p className="yx-error">{meError}</p></FullPageMessage></div>;
  if (!me) return <div className="yx"><FullPageMessage><p className="yx-muted">Loading…</p></FullPageMessage></div>;
  if (!privileged) {
    return <div className="yx"><FullPageMessage><p>The cohort brief is for faculty. <Link href="/learn">Back to your modules</Link></p></FullPageMessage></div>;
  }

  const empty = brief && !brief.stats.questions && !brief.stats.practice_attempts;
  const weakest = brief?.units.filter((u) => u.practice_avg !== null).sort((a, b) => (a.practice_avg ?? 0) - (b.practice_avg ?? 0))[0];

  return (
    <div className="yx">
      <LearnHeader me={me} center={<span className="yx-header-title">Cohort brief</span>} />
      <main className="yx-page">
        <p style={{ margin: "0 0 12px", fontSize: 15 }}>
          <Link href="/learn/faculty/discussion">Class questions to review →</Link>
          {" · "}<Link href="/learn/faculty/announcements">Announcements →</Link>
          {" · "}<Link href="/learn/faculty/schedule">Cohort schedules and join links →</Link>
          {" · "}<Link href="/learn/faculty/checks">Session checks →</Link>
        </p>
        <WebinarPrep />
        <div className="yx-eyebrow">For faculty · anonymised</div>
        <h1 style={{ margin: "4px 0 6px" }}>What your students are asking</h1>
        <p className="yx-lede" style={{ marginTop: 0 }}>
          A summary of students&apos; questions to Yaxa and their practice results for one module. Names are removed, and your own and other
          staff questions aren&apos;t counted.
        </p>

        <div className="yx-tools" style={{ gap: 8, margin: "12px 0 20px" }}>
          <select value={moduleCode} onChange={(e) => setModuleCode(e.target.value)}>
            {modules.map((m) => (
              <option key={m.code} value={m.code}>{m.code} · {m.title}</option>
            ))}
          </select>
          <select value={days} onChange={(e) => setDays(Number(e.target.value))}>
            {PERIODS.map((p) => (
              <option key={p.days} value={p.days}>{p.label}</option>
            ))}
          </select>
          <button className="yx-btn yx-btn-sm yx-btn-ghost" onClick={() => void refresh()} disabled={loading} title="Write the summary again from the latest data">
            Refresh summary
          </button>
        </div>

        {loading && <Thinking socratic={false} />}
        {errorText && <p className="yx-error">{errorText}</p>}

        {brief && !loading && (
          <>
            <div className="yx-grid yx-stats">
              <Stat value={brief.stats.students} label="students active" />
              <Stat value={brief.stats.questions} label="questions asked" />
              <Stat value={brief.stats.practice_attempts} label="practice answers" />
              <Stat value={brief.stats.unsupported} label="answers the readings didn't support" />
            </div>

            {empty ? (
              <p className="yx-muted" style={{ marginTop: 20 }}>No student activity on {brief.title} in this period yet.</p>
            ) : (
              <>
                <section className="yx-card yx-brief">
                  {brief.summary ? (
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>{brief.summary}</ReactMarkdown>
                  ) : (
                    <p className="yx-muted">{brief.summary_error ?? "No summary yet."}</p>
                  )}
                </section>

                <section style={{ marginTop: 24 }}>
                  <h2 style={{ fontSize: 20 }}>By learning unit</h2>
                  {weakest && weakest.practice_avg !== null && weakest.practice_avg < 2 && (
                    <p className="yx-muted">Weakest in practice: {weakest.id.replace("U", "U.")} {weakest.title} (average {weakest.practice_avg} out of 3).</p>
                  )}
                  {brief.units.reduce((n, u) => n + u.questions, 0) < brief.stats.questions && (
                    <p className="yx-muted" style={{ marginTop: 0 }}>
                      {brief.stats.questions - brief.units.reduce((n, u) => n + u.questions, 0)} of the {brief.stats.questions} questions were asked about the module as a whole, not a particular unit.
                    </p>
                  )}
                  <table className="yx-table">
                    <thead>
                      <tr>
                        <th>Unit</th>
                        <th>Questions</th>
                        <th>Practice answers</th>
                        <th>Average score (0–3)</th>
                      </tr>
                    </thead>
                    <tbody>
                      {brief.units.map((u) => (
                        <tr key={u.id}>
                          <td><span className="yx-unit-id">{u.id.replace("U", "U.")}</span> {u.title}</td>
                          <td>{u.questions}</td>
                          <td>{u.practice_attempts}</td>
                          <td>{u.practice_avg ?? "–"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </section>

                {!!brief.gaps.length && (
                  <section style={{ marginTop: 24 }}>
                    <h2 style={{ fontSize: 20 }}>Questions the readings didn&apos;t answer</h2>
                    <p className="yx-muted" style={{ marginTop: 0 }}>Yaxa found nothing to cite for these. Worth covering in class or adding a reading.</p>
                    <ul className="yx-gaps">
                      {brief.gaps.map((g, i) => (
                        <li key={i}>{g}</li>
                      ))}
                    </ul>
                  </section>
                )}
              </>
            )}
          </>
        )}
      </main>
    </div>
  );
}
