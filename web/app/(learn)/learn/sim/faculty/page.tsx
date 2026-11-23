"use client";

/**
 * Faculty view of a simulation: every student's run, rubric scores (with
 * override), how the final decisions split, and the answer key. Faculty can
 * also open all five days at once for an in-class run.
 */
import Link from "next/link";
import { Fragment, useCallback, useEffect, useState } from "react";

import { FullPageMessage, LearnHeader, useMe } from "@/features/yaxa/common";
import { AnswerText } from "@/features/yaxa/grounding";
import { yaxa, type SimFacultyView, type SimMemo, type SimScenarioCard } from "@/lib/yaxa-api";

const msg = (e: unknown) => (e instanceof Error ? e.message : String(e));

function MemoScores({
  memo, rubric, onOverride,
}: { memo: SimMemo; rubric: Record<string, string>; onOverride: (criterion: string, score: number) => Promise<void> }) {
  return (
    <div className="yx-card" style={{ padding: 12, margin: "8px 0" }}>
      <b>Day {memo.day} · option {memo.option}{memo.stance ? ` · ${memo.stance}` : ""} · {memo.total}/{Object.keys(rubric).length * 4}</b>
      <p style={{ whiteSpace: "pre-wrap", fontSize: 14 }}>{memo.text}</p>
      <table className="yx-table" style={{ fontSize: 13 }}>
        <tbody>
          {Object.entries(rubric).map(([k, label]) => (
            <tr key={k}>
              <td>{label}</td>
              <td>
                <select
                  value={memo.override?.[k] ?? 0}
                  onChange={(e) => void onOverride(k, Number(e.target.value))}
                  title="Override Yaxa's score"
                >
                  <option value={0}>Yaxa: {memo.scores[k]?.score ?? "–"}</option>
                  {[1, 2, 3, 4].map((n) => <option key={n} value={n}>Faculty: {n}</option>)}
                </select>
              </td>
              <td className="yx-muted">{memo.scores[k]?.reason}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function SimFacultyPage() {
  const { me, error: meError } = useMe();
  const [scenarios, setScenarios] = useState<SimScenarioCard[]>([]);
  const [scenario, setScenario] = useState("");
  const [data, setData] = useState<SimFacultyView | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const staff = !!me && (me.is_admin || me.role === "faculty");

  useEffect(() => {
    if (!staff) return;
    yaxa.simScenarios()
      .then((s) => {
        setScenarios(s);
        if (s.length) setScenario((cur) => cur || s[0].id);
      })
      .catch((e) => setError(msg(e)));
  }, [staff]);

  const load = useCallback((id: string) => {
    yaxa.simFacultyRuns(id).then(setData).catch((e) => setError(msg(e)));
  }, []);
  useEffect(() => {
    if (scenario) load(scenario);
  }, [scenario, load]);

  if (meError) return <div className="yx"><FullPageMessage><p className="yx-error">{meError}</p></FullPageMessage></div>;
  if (!me) return <div className="yx"><FullPageMessage><p className="yx-muted">Loading…</p></FullPageMessage></div>;
  if (!staff) return <div className="yx"><FullPageMessage><p>This page is for faculty. <Link href="/learn/sim">Back to simulations</Link></p></FullPageMessage></div>;

  const options = data?.scenario.options ?? [];
  const finals = data?.runs.filter((r) => r.outcome_option) ?? [];
  const avg = (day: number) => {
    const totals = data?.runs.map((r) => r.memos.find((m) => m.day === day)?.total).filter((t): t is number => t !== undefined) ?? [];
    return totals.length ? (totals.reduce((a, b) => a + b, 0) / totals.length).toFixed(1) : "–";
  };
  const override = async (userId: string, runId: string, day: number, criterion: string, score: number) => {
    try {
      await yaxa.simOverride({ user_id: userId, run_id: runId, day, scores: { [criterion]: score } });
      load(scenario);
    } catch (e) {
      setError(msg(e));
    }
  };
  const toggleOpenAll = async () => {
    if (!data) return;
    try {
      await yaxa.simSettings(scenario, !data.open_all);
      load(scenario);
    } catch (e) {
      setError(msg(e));
    }
  };

  return (
    <div className="yx">
      <LearnHeader me={me} center={<span className="yx-header-title">Simulations · faculty</span>} />
      <main className="yx-page">
        <p style={{ margin: 0 }}><Link href="/learn/sim">← Simulations</Link></p>
        <h1 style={{ margin: "8px 0" }}>Simulation runs</h1>
        <div className="yx-tools" style={{ gap: 12, alignItems: "center", flexWrap: "wrap" }}>
          <select value={scenario} onChange={(e) => setScenario(e.target.value)}>
            {scenarios.map((s) => <option key={s.id} value={s.id}>{s.title} ({s.module})</option>)}
          </select>
          {data && (
            <label title="For an in-class run: students can play all five days today">
              <input type="checkbox" checked={data.open_all} onChange={() => void toggleOpenAll()} /> Open all five days now
            </label>
          )}
        </div>
        {error && <p className="yx-error">{error}</p>}

        {data && (
          <>
            <section style={{ marginTop: 18 }}>
              <p>
                <b>{data.runs.length}</b> runs · <b>{finals.length}</b> finished · average memo score: day 1 <b>{avg(1)}</b>, day 3 <b>{avg(3)}</b>, day 5 <b>{avg(5)}</b> (out of {Object.keys(data.rubric).length * 4})
              </p>
              {!!finals.length && (
                <p>
                  Final decisions:{" "}
                  {options.map((o) => `${o.id}. ${o.label}: ${finals.filter((r) => r.outcome_option === o.id).length}`).join(" · ")}
                </p>
              )}
            </section>

            <table className="yx-table">
              <thead>
                <tr><th>Student</th><th>Cohort</th><th>Role</th><th>Day</th><th>Memo scores (1 / 3 / 5)</th><th>Decision</th><th /></tr>
              </thead>
              <tbody>
                {data.runs.map((r) => {
                  const key = `${r.user_id}/${r.run_id}`;
                  const score = (d: number) => r.memos.find((m) => m.day === d)?.total ?? "–";
                  return (
                    <Fragment key={key}>
                      <tr>
                        <td>{r.student}</td>
                        <td>{r.cohort ?? "–"}</td>
                        <td>{r.role_name}</td>
                        <td>{r.stage > 5 ? "Finished" : r.stage}</td>
                        <td>{score(1)} / {score(3)} / {score(5)}</td>
                        <td>{r.outcome_option ?? r.draft?.option ?? "–"}</td>
                        <td><button className="yx-btn yx-btn-sm yx-btn-ghost" onClick={() => setOpen(open === key ? null : key)}>{open === key ? "Hide" : "Memos"}</button></td>
                      </tr>
                      {open === key && (
                        <tr>
                          <td colSpan={7}>
                            {r.memos.length ? r.memos.map((m) => (
                              <MemoScores key={m.day} memo={m} rubric={data.rubric}
                                onOverride={(c, s) => override(r.user_id, r.run_id, m.day, c, s)} />
                            )) : <p className="yx-muted">No memos yet.</p>}
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  );
                })}
              </tbody>
            </table>
            {!data.runs.length && <p className="yx-muted">No one has started this simulation yet.</p>}

            <details className="yx-card" style={{ padding: 14, marginTop: 20 }}>
              <summary><b>Answer key</b> (real history and takeaways, for the live debrief)</summary>
              <AnswerText text={data.scenario.answer_key} sources={[]} onCite={() => {}} />
            </details>
          </>
        )}
      </main>
    </div>
  );
}
